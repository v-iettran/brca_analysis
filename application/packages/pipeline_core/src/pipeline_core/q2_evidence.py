"""Q2 chemotherapy monotherapy evidence, ported from ``scripts/Q5.R``.

``weighted_signature_score`` reproduces the exact formula in Q5.R's function of
the same name:

    score = sum(weight_g * zscore_g) / sum(|weight_g|)

Q5.R z-scores gene expression *within the scored cohort* because it always
scores an entire GEO series at once. A single incoming patient is a cohort of
one, so z-scoring "within cohort" is degenerate; instead we z-score against the
persisted METABRIC reference population (``expression.reference_gene_stats``),
and separately persist the *distribution of drug-level scores* across METABRIC
so a single patient's regimen score can be z-scored/aggregated exactly the way
Q5.R aggregates a regimen across multiple drugs (``mean_available_drugs`` in
Q5.R): z-score each drug's score, then average across the administered drugs.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np
import pandas as pd

from pipeline_core.config import ARTIFACT_DIR, Q5_TABLES_DIR
from pipeline_core.expression import align_patient_expression, load_metabric_expression

MINIMUM_GENES = 3
_DRUG_SCORE_REFERENCE_CACHE = ARTIFACT_DIR / "q2_drug_score_reference_stats.parquet"


@lru_cache(maxsize=1)
def load_q2_coefficients() -> pd.DataFrame:
    path = Q5_TABLES_DIR / "q2_chemotherapy_signature_coefficients.csv"
    if not path.exists():
        raise FileNotFoundError(f"Q2 coefficients not found at {path}")
    df = pd.read_csv(path)
    df["feature"] = df["feature"].str.strip().str.upper()
    return df


@lru_cache(maxsize=1)
def load_q2_evidence_scores() -> pd.DataFrame:
    path = Q5_TABLES_DIR / "q2_chemotherapy_evidence_scores.csv"
    if not path.exists():
        raise FileNotFoundError(f"Q2 evidence scores not found at {path}")
    return pd.read_csv(path).set_index("drug")


def available_drugs() -> list[str]:
    return sorted(load_q2_coefficients()["drug"].unique())


def weighted_signature_score(
    z_scores: pd.Series, drug: str, coefficient_column: str = "coefficient"
) -> tuple[float | None, int]:
    """Score one patient's z-scored expression for a single drug.

    Returns ``(score, genes_used)``; score is ``None`` if fewer than
    ``MINIMUM_GENES`` overlap between the drug's coefficient panel and the
    patient's covered genes (mirrors the ``minimum_genes`` guard in Q5.R).
    """
    coeffs = load_q2_coefficients()
    subset = coeffs[coeffs["drug"] == drug].copy()
    subset["weight"] = pd.to_numeric(subset[coefficient_column], errors="coerce")
    subset = subset[subset["weight"].notna() & (subset["weight"] != 0)]
    subset = subset[subset["feature"].isin(z_scores.index)]

    if len(subset) < MINIMUM_GENES:
        return None, len(subset)

    weights = subset.set_index("feature")["weight"]
    x = z_scores.loc[weights.index]
    score = float(np.dot(weights.to_numpy(), x.to_numpy())) / float(
        np.abs(weights.to_numpy()).sum()
    )
    return score, len(weights)


def _compute_drug_score_reference_stats(force_reload: bool = False) -> pd.DataFrame:
    """Score every METABRIC patient for every Q2 drug once, then take the
    mean/sd -- this is the reference distribution used to z-score a single
    new patient's drug score before regimen averaging."""
    if _DRUG_SCORE_REFERENCE_CACHE.exists() and not force_reload:
        return pd.read_parquet(_DRUG_SCORE_REFERENCE_CACHE)

    expr = load_metabric_expression()
    coeffs = load_q2_coefficients()
    ref_mean = expr.mean(axis=1)
    ref_sd = expr.std(axis=1).replace(0, np.nan)
    z_matrix = expr.sub(ref_mean, axis=0).div(ref_sd, axis=0)

    rows = []
    for drug in sorted(coeffs["drug"].unique()):
        subset = coeffs[coeffs["drug"] == drug].copy()
        subset["weight"] = pd.to_numeric(subset["coefficient"], errors="coerce")
        subset = subset[subset["weight"].notna() & (subset["weight"] != 0)]
        subset = subset[subset["feature"].isin(z_matrix.index)]
        if len(subset) < MINIMUM_GENES:
            continue
        weights = subset.set_index("feature")["weight"]
        sub_z = z_matrix.loc[weights.index]
        scores = sub_z.T.to_numpy() @ weights.to_numpy() / np.abs(weights.to_numpy()).sum()
        rows.append({"drug": drug, "mean": float(np.nanmean(scores)), "sd": float(np.nanstd(scores))})

    stats = pd.DataFrame(rows).set_index("drug")
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    stats.to_parquet(_DRUG_SCORE_REFERENCE_CACHE)
    return stats


def score_patient_all_drugs(patient_expression: dict[str, float]) -> pd.DataFrame:
    """Return a per-drug evidence table for one patient.

    Columns: raw_score, z_score, genes_used, evidence_category, model_support,
    model_spearman, external_spearman.
    """
    coeffs = load_q2_coefficients()
    reference_genes = pd.Index(sorted(coeffs["feature"].unique()))
    aligned = align_patient_expression(patient_expression, reference_genes)
    evidence = load_q2_evidence_scores()
    drug_ref = _compute_drug_score_reference_stats()

    rows = []
    for drug in available_drugs():
        score, genes_used = weighted_signature_score(aligned.z_scores, drug)
        z = None
        if score is not None and drug in drug_ref.index and drug_ref.loc[drug, "sd"] > 0:
            z = (score - drug_ref.loc[drug, "mean"]) / drug_ref.loc[drug, "sd"]
        row = {
            "drug": drug,
            "raw_score": score,
            "z_score": z,
            "genes_used": genes_used,
        }
        if drug in evidence.index:
            row.update(
                {
                    "evidence_category": evidence.loc[drug, "q2_evidence_category"],
                    "model_support": float(evidence.loc[drug, "q2_model_support"]),
                    "model_spearman": float(evidence.loc[drug, "q2_model_spearman"]),
                    "external_spearman": float(evidence.loc[drug, "q2_external_spearman"]),
                }
            )
        rows.append(row)
    return pd.DataFrame(rows).set_index("drug")


def regimen_score(patient_expression: dict[str, float], regimen_drugs: list[str]) -> dict:
    """Aggregate a multi-drug regimen the way ``score_patient_cohort`` in
    Q5.R does: z-score each drug's raw score against the reference
    distribution, then average across whichever regimen drugs are scoreable.
    """
    table = score_patient_all_drugs(patient_expression)
    matched = [d for d in regimen_drugs if d in table.index]
    scored = table.loc[matched].dropna(subset=["z_score"]) if matched else table.iloc[0:0]

    if scored.empty:
        return {
            "regimen_score": None,
            "drugs_requested": regimen_drugs,
            "drugs_scored": [],
            "reason": "None of the requested regimen drugs have a Q2 signature score "
            "for this patient (insufficient gene coverage or drug not modeled in Q2).",
        }

    return {
        "regimen_score": float(scored["z_score"].mean()),
        "drugs_requested": regimen_drugs,
        "drugs_scored": scored.index.tolist(),
        "per_drug": scored[["raw_score", "z_score", "genes_used"]].to_dict(orient="index"),
    }
