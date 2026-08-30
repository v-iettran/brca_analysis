"""Grounding gate for copilot answers.

Phrase matching alone is not a safety gate. `check_safety` catches "we
recommend", but nothing stopped a model from writing "the log-rank p is 0.02"
or naming a drug that is not in this run at all — and an invented statistic in
a clinical-research tool is a worse failure than a clumsy phrase.

The rationale path already grounds numbers against the payload
(`rationale_validator.allowed_values`). This applies the same discipline to
free-text copilot answers, and adds an entity check for the realistic case of a
familiar breast-cancer drug being named from the model's own memory.

Crucially the allowlist is **the context the model was shown**, not the whole
run payload. Measured on this cohort: the payload vouches for 125,137 distinct
numbers, the prompt context for 472. Grounding against the payload therefore
accepts almost any plausible-looking figure, including ones the model never
saw — which is confidence without a check behind it.

The model is treated as untrusted input. Nothing here asks it to behave; it
checks what came back and rejects what cannot be traced.
"""

from __future__ import annotations

import re
from typing import Any

from pipeline_core.safety import check_safety

from app.services.rationale_validator import allowed_values, flatten_payload

try:
    from pipeline_core.nominations import BREAST_CONTEXT_DRUGS
except Exception:  # noqa: BLE001
    BREAST_CONTEXT_DRUGS = set()

_NUMBER_RE = re.compile(r"(?<![A-Za-z0-9._-])(\d+(?:\.\d+)?)\s*%?")

# Ordinary prose numbers that carry no evidential weight, plus the conventional
# significance threshold: "q < 0.05" states a convention, not a result about
# this run, and blocking it would reject correct answers for no gain.
_FREE_NUMBERS = {"0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "100", "0.05", "0.5", "95"}


def _context_values(context: dict[str, Any]) -> tuple[set[str], list[float]]:
    """Numbers this context can vouch for: exact strings, and raw floats.

    The strings cover ids and counts; the floats let a model quote a rounded
    form of a stored value without letting it invent one that merely rounds to
    something nearby.
    """
    texts: set[str] = set()
    numbers: list[float] = []
    for value in flatten_payload(context).values():
        if isinstance(value, bool) or value is None:
            continue
        if isinstance(value, (list, dict)):
            texts.add(str(len(value)))
            continue
        if isinstance(value, (int, float)):
            numbers.append(float(value))
            texts.add(str(value))
            if 0.0 <= float(value) <= 1.0:
                numbers.append(float(value) * 100)
        elif isinstance(value, str):
            texts.add(value.strip().lower())
    return texts, numbers


# Kept for callers that want the raw allowlist size.
def _payload_numbers(context: dict[str, Any]) -> set[str]:
    texts, numbers = _context_values(context)
    return texts | {str(n) for n in numbers}


def _decimals(token: str) -> int:
    return len(token.split(".")[1]) if "." in token else 0


def unsupported_numbers(text: str, context: dict[str, Any]) -> list[str]:
    """Numbers in `text` that no value in `context` supports.

    A quoted figure is accepted when some context value rounds to it *at the
    precision the model used*. Rounding 0.03797 to 0.038 is fair; 0.0021 is not
    excused by a nearby 0.002, because a reader would take those as different
    statistics.
    """
    texts, numbers = _context_values(context)
    found: list[str] = []
    for match in _NUMBER_RE.findall(text or ""):
        token = match.strip().rstrip(".")
        if token in _FREE_NUMBERS or token in texts:
            continue
        try:
            wanted = float(token)
        except ValueError:
            continue
        places = _decimals(token)
        if any(round(value, places) == wanted for value in numbers):
            continue
        found.append(token)
    return sorted(set(found))


def _payload_text(context: dict[str, Any]) -> str:
    parts: list[str] = []
    for value in flatten_payload(context).values():
        if isinstance(value, str):
            parts.append(value.lower())
    return " ".join(parts)


def unsupported_drugs(text: str, payload: dict[str, Any]) -> list[str]:
    """Well-known breast agents named in `text` but absent from this run.

    Scoped to a curated watchlist rather than every drug name in existence: the
    realistic failure is a model reaching for trastuzumab or letrozole because
    the topic is breast cancer, not inventing a novel compound.
    """
    haystack = _payload_text(payload)
    lowered = (text or "").lower()
    missing = []
    for drug in BREAST_CONTEXT_DRUGS:
        name = str(drug).lower()
        if re.search(rf"\b{re.escape(name)}\b", lowered) and name not in haystack:
            missing.append(name)
    return sorted(missing)


_ALL_PASSED = re.compile(
    r"\b(all|every|each)\b[^.]{0,40}\bgates?\b[^.]{0,40}\b(passed|pass|succeeded)\b"
    r"|\bno\b[^.]{0,20}\bgates?\b[^.]{0,20}\b(failed|fail)\b"
    r"|\bgates?\b[^.]{0,30}\ball\b[^.]{0,20}\bpassed\b",
    re.IGNORECASE,
)


def _failed_gates(context: dict[str, Any]) -> list[str]:
    """Gate names whose `passed` flag is False, at any nesting depth."""
    failed: list[str] = []
    for path, value in flatten_payload(context.get("gates") or {}).items():
        if path.endswith("passed") and value is False:
            name = path.rsplit(".passed", 1)[0] or path
            failed.append(name)
    return sorted(set(failed))


def contradicted_gate_claims(text: str, context: dict[str, Any]) -> list[str]:
    """Claims that every gate passed, when the context says otherwise.

    Numeric grounding cannot catch this: "all gates passed" contains no number
    and no entity, yet it reverses the single most important fact the interface
    reports. Gate honesty is the project's whole premise, so the one claim class
    that would undo it is checked directly.
    """
    failed = _failed_gates(context)
    if failed and _ALL_PASSED.search(text or ""):
        return failed
    return []


def review_answer(text: str, context: dict[str, Any]) -> dict[str, Any]:
    """Decide whether a model answer may be shown, and say why if not.

    `context` must be the object handed to the model, not the run payload.
    """
    banned = check_safety(text)
    numbers = unsupported_numbers(text, context)
    drugs = unsupported_drugs(text, context)
    gates = contradicted_gate_claims(text, context)

    reasons: list[str] = []
    if banned:
        reasons.append("used language reserved for clinical recommendations")
    if numbers:
        reasons.append(
            "quoted "
            + ("a figure" if len(numbers) == 1 else "figures")
            + f" not present in this run ({', '.join(numbers[:4])})"
        )
    if drugs:
        reasons.append(f"named a drug that is not part of this analysis ({', '.join(drugs[:3])})")
    if gates:
        reasons.append(
            "said every gate passed when "
            + ", ".join(gates[:3])
            + (" did not" if len(gates) == 1 else " did not")
        )

    return {
        "accepted": not reasons,
        "reasons": reasons,
        "banned_phrases": banned,
        "unsupported_numbers": numbers,
        "unsupported_drugs": drugs,
        "contradicted_gates": gates,
    }
