"""Generate de-identified synthetic demonstration patients from METABRIC.

Three scenarios are produced, exactly as scoped in the plan:

* ``high_confidence`` -- a real METABRIC patient whose true MOFA cluster the
  signature-similarity classifier recovers with high top-cluster probability.
* ``mixed_cluster`` -- a patient whose cluster probabilities are diffuse
  across two or more clusters.
* ``low_quality`` -- a patient with most genes deliberately dropped to
  simulate a low-coverage RNA panel, which should trigger the abstention path.

Patients are de-identified (a synthetic ``SYN-####`` id replaces the METABRIC
id, and a small amount of Gaussian noise is added to expression values so the
demo profile is not a byte-for-byte copy of a real record) while the true
source id/cluster are retained in a separate, clearly-labeled evaluation
field so the demo can be checked against ground truth without leaking it to
the "patient" object the UI renders.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from pipeline_core.cluster_model import predict_cluster_probabilities
from pipeline_core.config import METABRIC_DIR
from pipeline_core.expression import load_metabric_expression, load_mofa_cluster_labels

RNG_SEED = 20260726
DEMO_REGIMEN = ["5-fluorouracil", "doxorubicin", "paclitaxel"]


@dataclass
class SyntheticPatient:
    synthetic_id: str
    scenario: str
    description: str
    expression: dict[str, float]
    metadata: dict
    administered_regimen: list[str]
    ground_truth: dict = field(default_factory=dict)


def _deidentify_id(real_id: str, scenario: str) -> str:
    digest = hashlib.sha256(f"{real_id}:{scenario}:{RNG_SEED}".encode()).hexdigest()[:8]
    return f"SYN-{scenario[:3].upper()}-{digest}"


def _clean_ihc_status(value) -> str | None:
    """Normalize METABRIC IHC labels, including the dataset's 'Positve' typo."""
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return None
    if text.lower() == "positve":
        return "Positive"
    return text


def _infer_pr_status(er_status, subtype: str | None) -> str:
    er = str(er_status or "").lower()
    subtype_l = str(subtype or "").lower()
    if "basal" in subtype_l or "claudin" in subtype_l:
        return "Negative"
    if er.startswith("posit"):
        return "Positive"
    if er.startswith("neg"):
        return "Negative"
    return "Unknown"


def _enrich_demo_fields(real_id: str, base: dict, rng: np.random.Generator) -> dict:
    """Add realistic fictional oncology fields absent from METABRIC.

    Every generated field is tagged under ``field_provenance`` so the UI can
    label METABRIC-derived vs demo-enriched values.
    """
    subtype = str(base.get("claudin_subtype") or "")
    er = base.get("er_status")
    her2 = str(base.get("her2_status") or "").upper()
    nodes = base.get("lymph_nodes_positive") or 0
    age = base.get("age_at_diagnosis") or 60

    # Stage heuristic from nodes / subtype for demo realism only.
    if nodes and nodes >= 4:
        stage = rng.choice(["IIIA", "IIIB", "IIIC"])
    elif nodes and nodes >= 1:
        stage = rng.choice(["IIA", "IIB", "IIIA"])
    elif "basal" in subtype.lower() or "her2" in subtype.lower():
        stage = rng.choice(["IIA", "IIB"])
    else:
        stage = rng.choice(["IA", "IB", "IIA"])

    grade = 3 if any(s in subtype.lower() for s in ("basal", "her2", "claudin")) else int(rng.choice([1, 2, 2, 3]))
    tumor_size_mm = float(rng.integers(8, 55))
    if base.get("nottingham_prognostic_index") is not None:
        npi = float(base["nottingham_prognostic_index"])
        npi_source = "metabric_derived"
    else:
        npi = float(np.clip(0.2 * tumor_size_mm / 10 + grade + (1 if nodes else 0) + rng.normal(0, 0.15), 2.0, 7.0))
        npi_source = "demo_generated"
    ecog = int(rng.choice([0, 0, 1, 1, 2], p=[0.35, 0.25, 0.25, 0.1, 0.05]))
    prior = rng.choice(
        [
            "None (treatment-naive demo profile)",
            "Prior adjuvant endocrine therapy",
            "Prior anthracycline-based chemotherapy",
            "Prior taxane exposure",
        ]
    )
    creatinine = float(np.clip(rng.normal(0.9, 0.2), 0.5, 1.8))
    bilirubin = float(np.clip(rng.normal(0.7, 0.2), 0.2, 2.0))
    alt = float(np.clip(rng.normal(28, 10), 10, 90))
    cities = [
        {"city": "Dublin", "country": "Ireland", "latitude": 53.3498, "longitude": -6.2603},
        {"city": "Cork", "country": "Ireland", "latitude": 51.8985, "longitude": -8.4756},
        {"city": "Galway", "country": "Ireland", "latitude": 53.2707, "longitude": -9.0568},
        {"city": "London", "country": "United Kingdom", "latitude": 51.5074, "longitude": -0.1278},
    ]
    location = cities[int(rng.integers(0, len(cities)))]

    enriched = {
        **base,
        "pr_status": _infer_pr_status(er, subtype),
        "nottingham_prognostic_index": round(npi, 2),
        "tumor_stage": stage,
        "tumor_grade": grade,
        "tumor_size_mm": tumor_size_mm,
        "ecog_status": ecog,
        "prior_therapy": prior,
        "organ_function": {
            "creatinine_mg_dl": round(creatinine, 2),
            "bilirubin_mg_dl": round(bilirubin, 2),
            "alt_u_l": round(alt, 1),
        },
        "location": location,
        "field_provenance": {
            "metabric_derived": [
                "age_at_diagnosis",
                "er_status",
                "her2_status",
                "claudin_subtype",
                "histological_subtype",
                "lymph_nodes_positive",
                "menopausal_state",
            ]
            + (["nottingham_prognostic_index"] if npi_source == "metabric_derived" else []),
            "demo_generated": [
                "pr_status",
                "tumor_stage",
                "tumor_grade",
                "tumor_size_mm",
                "ecog_status",
                "prior_therapy",
                "organ_function",
                "location",
            ]
            + (["nottingham_prognostic_index"] if npi_source == "demo_generated" else []),
            "note": (
                "Demo-generated fields are fictional enrichments for trial-matching "
                "UI transparency. They are not METABRIC observations."
            ),
        },
    }
    # Stable per-patient RNG salt already applied via caller; keep her2 gain label readable.
    if her2 == "GAIN":
        enriched["her2_status"] = "Positive (SNP6 GAIN)"
    elif her2 in {"NEUTRAL", "LOSS"}:
        enriched["her2_status"] = f"Negative (SNP6 {her2})"
    return enriched


def _clinical_metadata(real_id: str, rng: np.random.Generator | None = None) -> dict:
    path = METABRIC_DIR / "data_clinical_patient.txt"
    clinical = pd.read_csv(path, sep="\t", comment="#").set_index("PATIENT_ID")
    if real_id not in clinical.index:
        return {}
    row = clinical.loc[real_id]
    base = {
        "age_at_diagnosis": _safe_float(row.get("AGE_AT_DIAGNOSIS")),
        "er_status": _clean_ihc_status(row.get("ER_IHC")),
        "her2_status": row.get("HER2_SNP6"),
        "claudin_subtype": row.get("CLAUDIN_SUBTYPE"),
        "histological_subtype": row.get("HISTOLOGICAL_SUBTYPE"),
        "lymph_nodes_positive": _safe_float(row.get("LYMPH_NODES_EXAMINED_POSITIVE")),
        "menopausal_state": row.get("INFERRED_MENOPAUSAL_STATE"),
    }
    # Prefer METABRIC NPI when present.
    npi = _safe_float(row.get("NPI"))
    if npi is not None:
        base["nottingham_prognostic_index"] = npi
    local_rng = rng or np.random.default_rng(abs(hash(real_id)) % (2**32))
    return _enrich_demo_fields(real_id, base, local_rng)


def _safe_float(value) -> float | None:
    try:
        f = float(value)
        return f if np.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def _noisy_expression(vector: pd.Series, rng: np.random.Generator, relative_sd: float = 0.03) -> dict:
    noise = rng.normal(0, np.abs(vector.to_numpy()) * relative_sd + 0.01)
    noisy = vector.to_numpy() + noise
    return {gene: float(v) for gene, v in zip(vector.index, noisy)}


def generate_synthetic_patients() -> list[SyntheticPatient]:
    expr = load_metabric_expression()
    labels = load_mofa_cluster_labels()
    common = [s for s in expr.columns if s in labels.index]
    rng = np.random.default_rng(RNG_SEED)

    candidates = rng.choice(common, size=min(400, len(common)), replace=False)
    scored = []
    for sample_id in candidates:
        vector = expr[sample_id].dropna()
        prediction = predict_cluster_probabilities(vector.to_dict())
        scored.append((sample_id, prediction))

    high_confidence = max(scored, key=lambda t: t[1].top_probability)
    high_vector = expr[high_confidence[0]].dropna()
    patients = [
        SyntheticPatient(
            synthetic_id=_deidentify_id(high_confidence[0], "high_confidence"),
            scenario="high_confidence",
            description="High-confidence single-cluster RNA profile (full gene panel).",
            expression=_noisy_expression(high_vector, rng),
            metadata=_clinical_metadata(high_confidence[0], rng),
            administered_regimen=DEMO_REGIMEN,
            ground_truth={
                "true_mofa_cluster": int(labels.loc[high_confidence[0]]),
                "classifier_top_cluster": high_confidence[1].top_cluster,
                "classifier_top_probability": high_confidence[1].top_probability,
                "note": "Retained for internal QA only; never shown to clinician/technical UI.",
            },
        )
    ]

    # Construct a genuinely ambiguous "mixed cluster" profile by averaging two
    # real patients drawn from two different true MOFA clusters (an in-sample
    # classifier trained on real patients is otherwise almost always highly
    # confident on real, full-coverage profiles -- averaging two distinct
    # biological signals is the standard way to demonstrate a legitimately
    # intermediate case rather than searching for a rare, possibly noisy one).
    donor_a = high_confidence[0]
    cluster_a = int(labels.loc[donor_a])
    donor_b_candidates = [
        sid for sid in candidates if int(labels.loc[sid]) != cluster_a and sid != donor_a
    ][:20]

    best = None
    for donor_b in donor_b_candidates:
        common_genes = expr[donor_a].dropna().index.intersection(expr[donor_b].dropna().index)
        candidate_blend = (expr.loc[common_genes, donor_a] + expr.loc[common_genes, donor_b]) / 2.0
        candidate_prediction = predict_cluster_probabilities(candidate_blend.to_dict())
        if best is None or candidate_prediction.top_probability < best[2].top_probability:
            best = (donor_b, candidate_blend, candidate_prediction)
    donor_b, blended_vector, mixed_prediction = best
    patients.append(
        SyntheticPatient(
            synthetic_id=_deidentify_id(f"{donor_a}+{donor_b}", "mixed_cluster"),
            scenario="mixed_cluster",
            description=(
                "Constructed mixed-signal RNA profile (gene-wise average of two donors "
                "from different true MOFA clusters) demonstrating a diffuse "
                "cluster-probability case."
            ),
            expression=_noisy_expression(blended_vector, rng),
            metadata=_clinical_metadata(donor_a, rng),
            administered_regimen=DEMO_REGIMEN,
            ground_truth={
                "true_mofa_cluster": "blended (see donor_clusters)",
                "donor_clusters": [cluster_a, int(labels.loc[donor_b])],
                "classifier_top_cluster": mixed_prediction.top_cluster,
                "classifier_top_probability": mixed_prediction.top_probability,
                "classifier_probabilities": mixed_prediction.probabilities,
                "note": "Retained for internal QA only; never shown to clinician/technical UI.",
            },
        )
    )

    remaining = [t for t in scored if t[0] not in (donor_a, donor_b)]
    low_quality_source = remaining[0]
    low_sample_id, low_prediction = low_quality_source
    full_vector = expr[low_sample_id].dropna()
    kept_genes = rng.choice(
        full_vector.index, size=max(int(len(full_vector) * 0.10), 50), replace=False
    )
    sparse_vector = full_vector.loc[kept_genes]
    patients.append(
        SyntheticPatient(
            synthetic_id=_deidentify_id(low_sample_id, "low_quality"),
            scenario="low_quality",
            description=(
                "Low-coverage RNA panel (~10% of reference genes) simulating a "
                "targeted panel or degraded sample; expected to trigger abstention."
            ),
            expression=_noisy_expression(sparse_vector, rng),
            metadata=_clinical_metadata(low_sample_id, rng),
            administered_regimen=DEMO_REGIMEN,
            ground_truth={
                "true_mofa_cluster": int(labels.loc[low_sample_id]),
                "classifier_top_cluster": low_prediction.top_cluster,
                "classifier_top_probability": low_prediction.top_probability,
                "note": "Retained for internal QA only; never shown to clinician/technical UI.",
            },
        )
    )
    return patients
