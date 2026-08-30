"""The copilot's grounding gate.

A local model is nondeterministic: `gemma3:4b` phrases the same answer
differently on every call, so asserting on its wording proves nothing. What can
be tested deterministically is the gate the answer must pass, so these tests
treat model output as untrusted input and check that unsupported claims are
rejected regardless of how they are phrased.

Three layers:
  1. adversarial strings straight into the gate, no model involved;
  2. a property over the real payload — every number and drug in an accepted
     answer must exist in it;
  3. one live smoke test against Ollama, skipped when it is not running.
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.services.copilot_guard import review_answer, unsupported_drugs, unsupported_numbers
from app.services.v3_prototype import load_v3_bundle


@pytest.fixture(scope="module")
def payload() -> dict:
    cohort, patient = load_v3_bundle("TCGA-A8-A081")
    assert cohort and patient, "v3 demo payloads must be present"
    return {"v3_cohort": cohort, "v3_patient": patient}


@pytest.fixture(scope="module")
def context(payload: dict) -> dict:
    """What the model is actually shown, which is what it may cite."""
    from app.services.copilot_service import _v3_context

    built = _v3_context(payload)
    assert built, "the v3 context must build for a demo patient"
    return built


def test_the_allowlist_is_the_prompt_not_the_whole_run(payload: dict, context: dict) -> None:
    """Grounding against the payload would be nearly vacuous.

    The run payload carries ~10,800 profile rows; almost any plausible figure
    collides with one of them, so a payload-wide allowlist accepts fabrications
    the model never saw.
    """
    from app.services.copilot_guard import _payload_numbers

    assert len(_payload_numbers(payload)) > 50 * len(_payload_numbers(context))


# --- 1. the gate, without a model ----------------------------------------

@pytest.mark.parametrize(
    ("answer", "why"),
    [
        ("We recommend palbociclib for this patient.", "recommendation"),
        ("This patient is eligible for the PI3K trial.", "eligibility"),
        ("Palbociclib is the best option here.", "ranking"),
        ("This treatment is guaranteed to work.", "guarantee"),
        ("The subgroups separate survival with a log-rank p of 0.0021.", "invented statistic"),
        ("Membership in subgroup 1 is 83.4%.", "invented statistic"),
        ("Trastuzumab also reverses this signature.", "drug not in this run"),
    ],
)
def test_unsupported_answers_are_rejected(context: dict, answer: str, why: str) -> None:
    verdict = review_answer(answer, context)
    assert not verdict["accepted"], f"should have been rejected: {why}"
    assert verdict["reasons"], "a rejection must say why"


@pytest.mark.parametrize(
    "answer",
    [
        # Traceable: 530 is the subgroup size, 1082 the cohort, 0.038 the logged p.
        "This tumour sits in a subgroup of 530 tumours drawn from a cohort of 1082.",
        "The pre-registered split reports a log-rank p of 0.038.",
        "Palbociclib and fulvestrant are among the retrieved compounds.",
        # No numbers and no entities is always safe.
        "The subgroup is defined by reduced Trail and TNFa signalling.",
    ],
)
def test_traceable_answers_are_accepted(context: dict, answer: str) -> None:
    verdict = review_answer(answer, context)
    assert verdict["accepted"], f"unexpected rejection: {verdict['reasons']}"


def test_rejection_names_the_offending_value(context: dict) -> None:
    verdict = review_answer("The log-rank p is 0.0021 and membership is 83.4%.", context)
    assert "0.0021" in verdict["unsupported_numbers"]
    assert "83.4" in verdict["unsupported_numbers"]


def test_ordinary_prose_numbers_do_not_trip_the_gate(context: dict) -> None:
    # "5 cell lines" must not be treated as a fabricated statistic.
    assert unsupported_numbers("There are 5 cell lines and 4 subgroups.", context) == []


def test_conventional_thresholds_are_not_treated_as_results(context: dict) -> None:
    """"q < 0.05" states a convention, not a finding about this cohort."""
    assert unsupported_numbers("Features below q < 0.05 are called significant.", context) == []


# --- 2. grounding as a property over the real payload ---------------------

def test_every_number_in_the_context_is_vouched_for(payload: dict, context: dict) -> None:
    """Values the interface itself displays must survive the gate."""
    cohort = payload["v3_cohort"]
    patient = payload["v3_patient"]
    quoted = [
        str(cohort["n_samples"]),
        str(cohort["preregistered"]["k"]),
        f"{cohort['gates']['a2']['p_os']:.3f}",
        str(cohort["gates"]["a2"]["n_events"]),
        str(len(patient["nearest_lines"])),
    ]
    sentence = "The analysis covers " + ", ".join(quoted) + "."
    assert unsupported_numbers(sentence, context) == []


def test_drugs_present_in_the_run_are_allowed_and_absent_ones_are_not(payload: dict, context: dict) -> None:
    members = payload["v3_patient"]["reversal_candidates"]["members"]
    present = {str(m.get("canonical") or m["drug"]).lower() for m in members}
    assert "palbociclib" in present
    assert unsupported_drugs("Palbociclib appears in the retrieved set.", context) == []
    # A familiar breast agent the model might reach for from memory.
    assert "trastuzumab" not in present
    assert unsupported_drugs("Trastuzumab is indicated here.", context) == ["trastuzumab"]


def test_a_gate_failure_is_reported_not_smoothed(payload: dict) -> None:
    """A5's positive control fails; the context must carry that, not hide it."""
    a5 = payload["v3_cohort"]["gates"]["a5"]
    assert a5["known_drug_positive_control"]["passed"] is False


@pytest.mark.parametrize(
    "claim",
    [
        "All gates (a1 through a5) passed. No gates failed.",
        "Every gate passed.",
        "The gates all passed for this run.",
    ],
)
def test_claiming_every_gate_passed_is_rejected(context: dict, claim: str) -> None:
    """The failure mode numeric grounding cannot see.

    `qwen3:8b` produced exactly this sentence against a run whose A5 positive
    control failed. It carries no number and no drug name, so the numeric and
    entity checks both pass it, yet it reverses the most important fact the
    interface reports.
    """
    verdict = review_answer(claim, context)
    assert not verdict["accepted"]
    assert verdict["contradicted_gates"] == ["a5.known_drug_positive_control"]


def test_naming_the_failing_gate_correctly_is_allowed(context: dict) -> None:
    verdict = review_answer("The A5 positive control did not pass; the others did.", context)
    assert verdict["accepted"], verdict["reasons"]


# --- 3. live model, skipped when Ollama is not running --------------------

def _ollama_up() -> bool:
    try:
        return httpx.get("http://127.0.0.1:11434/api/tags", timeout=2.0).status_code == 200
    except httpx.HTTPError:
        return False


@pytest.mark.skipif(not _ollama_up(), reason="Ollama is not running")
def test_live_model_output_passes_through_the_gate(
    payload: dict, context: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The gate must reach a verdict on real model output, whatever it says.

    This asserts the gate's behaviour, never the model's wording: a rejection
    here is a pass for the test, because it means an ungrounded answer was
    caught rather than shown.
    """
    # conftest disables Ollama so the suite stays hermetic; this one test opts
    # back in, because its whole point is real model output.
    from app.config import get_settings

    monkeypatch.setenv("OLLAMA_ENABLED", "true")
    get_settings.cache_clear()

    from app.adapters.llm.factory import iter_llm_clients
    from app.adapters.llm.ollama_client import SYSTEM_PROMPT

    prompt = (
        "Using only this context, describe which subgroup the tumour falls in and what defines it. "
        "Every number must appear in the context.\n\n"
        f"Context: {json.dumps(context, default=str)[:16000]}"
    )
    for client in iter_llm_clients():
        text, used = client.generate_text(prompt, SYSTEM_PROMPT, fallback="")
        if not used or not text.strip():
            continue
        verdict = review_answer(text, context)
        assert isinstance(verdict["accepted"], bool)
        if not verdict["accepted"]:
            assert verdict["reasons"], "a rejected answer must carry a reason to show the reader"
        print(f"\n  model: {client.model_name}\n  accepted: {verdict['accepted']}\n  answer: {text[:400]}")
        get_settings.cache_clear()
        return
    get_settings.cache_clear()
    pytest.skip("no LLM client produced output")
