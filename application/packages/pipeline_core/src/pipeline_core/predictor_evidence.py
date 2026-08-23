"""Python runtime port of ``scripts/Predictor/predictor_model.R``.

This module is deliberately a parallel evidence track. It does not nominate
drugs and must not be blended into the List 1/List 2 overlap score because Q4
support already contributes to the expression-reversal workflow.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np
import pandas as pd

from pipeline_core.almanac_evidence import load_eligible_almanac_pairs
from pipeline_core.config import ARTIFACT_DIR, Q5_ALMANAC_DIR, REPO_ROOT
from pipeline_core.drug_names import normalize_drug_name
from pipeline_core.expression import align_patient_expression, load_metabric_expression

PREDICTOR_VERSION = "predictor_r_port_v1"
MINIMUM_SIGNATURE_GENES = 3
MINIMUM_GENE_COVERAGE = 0.70

SINGLE_WEIGHTS = {
    "patient_sensitivity": 0.60,
    "q2_reliability": 0.25,
    "q4_support": 0.15,
}
COMBINATION_WEIGHTS = {
    "components": 0.55,
    "aligned_pair": 0.35,
    "q4_support": 0.10,
}

_Q2_TABLE_DIR = REPO_ROOT / "outputs" / "q2" / "tables"
_REFERENCE_SCORE_CACHE = ARTIFACT_DIR / "predictor_q2_reference_scores_v1.parquet"


@lru_cache(maxsize=1)
def load_predictor_coefficients() -> pd.DataFrame:
    """Load and aggregate the exact elastic-net coefficient slice used by R."""
    raw = pd.read_csv(_Q2_TABLE_DIR / "q2_model_coefficients.csv")
    primary = pd.read_csv(_Q2_TABLE_DIR / "q2_primary_drug_set.csv")
    status = pd.read_csv(Q5_ALMANAC_DIR / "q2_primary_drug_scoring_status.csv")

    primary["drug"] = primary["drug"].map(normalize_drug_name)
    primary["drug_screen"] = (
        primary["primary_screen"].astype(str)
        + ":"
        + primary["drug"].astype(str)
        + ":"
        + primary["primary_drug_id"].astype(str)
    )
    selected = raw[
        (raw["analysis"] == "pan_cancer_augmented") & (raw["model"] == "elastic_net")
    ].merge(
        primary[["drug_screen", "drug", "treatment_class"]],
        on="drug_screen",
        how="inner",
    )
    coefficients = (
        selected.groupby(["drug", "treatment_class", "feature"], as_index=False)["coefficient"]
        .median()
    )
    coefficients["feature"] = coefficients["feature"].astype(str).str.strip().str.upper()
    available = set(
        status.loc[status["patient_projection_available"].astype(bool), "drug"].map(
            normalize_drug_name
        )
    )
    return coefficients[coefficients["drug"].isin(available)].reset_index(drop=True)


@lru_cache(maxsize=1)
def load_predictor_support_tables() -> pd.DataFrame:
    reliability = pd.read_csv(Q5_ALMANAC_DIR / "q2_drug_reliability.csv")
    q4 = pd.read_csv(Q5_ALMANAC_DIR / "q4_support_by_q2_drug.csv")
    for table in (reliability, q4):
        table["canonical"] = table["drug"].map(normalize_drug_name)
    return reliability.merge(
        q4[
            [
                "canonical",
                "q4_target_support",
                "q4_compound_support",
                "q4_drug_support",
                "q4_targets_used",
                "q4_targets_matched",
            ]
        ],
        on="canonical",
        how="left",
    ).set_index("canonical")


def _score_matrix(z_matrix: pd.DataFrame, coefficients: pd.DataFrame) -> np.ndarray:
    weights = coefficients.set_index("feature")["coefficient"]
    matrix = z_matrix.loc[weights.index]
    return matrix.T.to_numpy() @ weights.to_numpy() / np.abs(weights.to_numpy()).sum()


@lru_cache(maxsize=1)
def load_predictor_reference_scores() -> pd.DataFrame:
    """Patient-score reference distributions used for empirical percentiles."""
    if _REFERENCE_SCORE_CACHE.exists():
        return pd.read_parquet(_REFERENCE_SCORE_CACHE)

    expression = load_metabric_expression()
    coefficients = load_predictor_coefficients()
    required = pd.Index(sorted(coefficients["feature"].unique()))
    reference = expression.reindex(required)
    means = reference.mean(axis=1)
    sds = reference.std(axis=1).replace(0, np.nan)
    z_matrix = reference.sub(means, axis=0).div(sds, axis=0).fillna(0.0)

    output: dict[str, np.ndarray] = {}
    for drug, group in coefficients.groupby("drug"):
        usable = group[
            group["coefficient"].notna()
            & (group["coefficient"] != 0)
            & group["feature"].isin(z_matrix.index)
        ]
        if len(usable) < MINIMUM_SIGNATURE_GENES:
            continue
        output[drug] = _score_matrix(z_matrix, usable)

    scores = pd.DataFrame(output, index=expression.columns)
    scores.index.name = "sample_id"
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    scores.to_parquet(_REFERENCE_SCORE_CACHE)
    return scores


def _empirical_percentile(value: float, reference: pd.Series) -> float:
    finite = reference[np.isfinite(reference.to_numpy())].to_numpy()
    if not np.isfinite(value) or len(finite) == 0:
        return float("nan")
    return float(((finite < value).sum() + 0.5 * (finite == value).sum()) / len(finite))


def score_predictor_drugs(patient_expression: dict[str, float]) -> list[dict]:
    """Return the transparent single-drug evidence rows produced by the R logic."""
    coefficients = load_predictor_coefficients()
    support = load_predictor_support_tables()
    reference_scores = load_predictor_reference_scores()
    required = pd.Index(sorted(coefficients["feature"].unique()))
    aligned = align_patient_expression(patient_expression, required)

    rows: list[dict] = []
    for drug, group in coefficients.groupby("drug"):
        nonzero = group[group["coefficient"].notna() & (group["coefficient"] != 0)].copy()
        usable = nonzero[nonzero["feature"].isin(aligned.z_scores.index)]
        coverage = len(usable) / max(len(nonzero), 1)
        raw_score = None
        sensitivity_percentile = None
        if len(usable) >= MINIMUM_SIGNATURE_GENES and coverage >= MINIMUM_GENE_COVERAGE:
            weights = usable.set_index("feature")["coefficient"]
            values = aligned.z_scores.loc[weights.index]
            raw_score = float(np.dot(weights.to_numpy(), values.to_numpy())) / float(
                np.abs(weights.to_numpy()).sum()
            )
            if drug in reference_scores.columns:
                sensitivity_percentile = _empirical_percentile(
                    raw_score, reference_scores[drug]
                )

        evidence = support.loc[drug] if drug in support.index else None
        reliability = (
            float(evidence.get("q2_model_support", 0.0) or 0.0)
            if evidence is not None
            else 0.0
        )
        q4_support = (
            float(evidence.get("q4_drug_support", 0.0) or 0.0)
            if evidence is not None
            else 0.0
        )
        priority = (
            SINGLE_WEIGHTS["patient_sensitivity"] * sensitivity_percentile
            + SINGLE_WEIGHTS["q2_reliability"] * reliability
            + SINGLE_WEIGHTS["q4_support"] * q4_support
            if sensitivity_percentile is not None and np.isfinite(sensitivity_percentile)
            else None
        )
        rows.append(
            {
                "drug": drug,
                "canonical": drug,
                "treatment_class": (
                    str(evidence.get("treatment_class"))
                    if evidence is not None
                    else str(group["treatment_class"].iloc[0])
                ),
                "q2_raw_sensitivity_score": raw_score,
                "reference_cohort_sensitivity_percentile": sensitivity_percentile,
                "q2_model_reliability": reliability,
                "q2_model_spearman": _optional_float(
                    evidence.get("q2_model_spearman") if evidence is not None else None
                ),
                "q2_external_spearman": _optional_float(
                    evidence.get("q2_external_spearman") if evidence is not None else None
                ),
                "q2_evidence_category": (
                    str(evidence.get("q2_evidence_category"))
                    if evidence is not None
                    else None
                ),
                "q4_target_support": _optional_float(
                    evidence.get("q4_target_support") if evidence is not None else None
                ),
                "q4_compound_support": _optional_float(
                    evidence.get("q4_compound_support") if evidence is not None else None
                ),
                "q4_drug_support": q4_support,
                "q4_targets_used": _split_targets(
                    evidence.get("q4_targets_used") if evidence is not None else None
                ),
                "q4_targets_matched": _split_targets(
                    evidence.get("q4_targets_matched") if evidence is not None else None
                ),
                "integrated_single_drug_priority": priority,
                "signature_genes_used": int(len(usable)),
                "signature_genes_total": int(len(nonzero)),
                "gene_coverage": float(coverage),
                "predictor_version": PREDICTOR_VERSION,
                "interpretation": (
                    "Parallel Q2/Q4 clinical-context score. Not used to nominate the "
                    "drug and not a treatment-response probability."
                ),
            }
        )

    scoreable = [row for row in rows if row["integrated_single_drug_priority"] is not None]
    scoreable.sort(
        key=lambda row: float(row["integrated_single_drug_priority"]), reverse=True
    )
    n = len(scoreable)
    for rank, row in enumerate(scoreable, start=1):
        row["within_patient_predictor_rank"] = rank
        row["within_patient_predictor_percentile"] = (
            1.0 - (rank - 1) / max(n - 1, 1)
        )
    for row in rows:
        row.setdefault("within_patient_predictor_rank", None)
        row.setdefault("within_patient_predictor_percentile", None)
        row["reference_cohort"] = "METABRIC"
        row["parity_scope"] = "r_equations_and_committed_support_tables"
    return sorted(
        rows,
        key=lambda row: (
            row["within_patient_predictor_rank"] is None,
            row["within_patient_predictor_rank"] or 10_000,
        ),
    )


def predictor_combinations(single_drug_rows: list[dict]) -> list[dict]:
    """Score all eligible ALMANAC pairs without the overlap-nomination gate."""
    by_drug = {normalize_drug_name(row["drug"]): row for row in single_drug_rows}
    pairs = load_eligible_almanac_pairs()
    rows: list[dict] = []
    for _, pair in pairs.iterrows():
        a = normalize_drug_name(pair["drug_a"])
        b = normalize_drug_name(pair["drug_b"])
        row_a = by_drug.get(a)
        row_b = by_drug.get(b)
        if not row_a or not row_b:
            continue
        priority_a = row_a.get("integrated_single_drug_priority")
        priority_b = row_b.get("integrated_single_drug_priority")
        if priority_a is None or priority_b is None:
            continue
        component = float(np.sqrt(max(priority_a, 0.0) * max(priority_b, 0.0)))
        pair_q4 = float(
            np.mean(
                [
                    float(row_a.get("q4_drug_support") or 0.0),
                    float(row_b.get("q4_drug_support") or 0.0),
                ]
            )
        )
        aligned = float(pair.get("aligned_pair_support", 0.0) or 0.0)
        integrated = (
            COMBINATION_WEIGHTS["components"] * component
            + COMBINATION_WEIGHTS["aligned_pair"] * aligned
            + COMBINATION_WEIGHTS["q4_support"] * pair_q4
        )
        rows.append(
            {
                "drug_a": str(pair["drug_a"]),
                "drug_b": str(pair["drug_b"]),
                "combination": str(
                    pair.get("combination", f"{pair['drug_a']} + {pair['drug_b']}")
                ),
                "component_drug_priority": component,
                "drug_a_priority": float(priority_a),
                "drug_b_priority": float(priority_b),
                "aligned_pair_support": aligned,
                "pair_q4_support": pair_q4,
                "integrated_combination_priority": integrated,
                "aligned_cell_lines": int(pair.get("aligned_cell_lines", 0) or 0),
                "aligned_cell_line_names": pair.get("aligned_cell_line_names"),
                "cell_line_alignment_confidence": pair.get(
                    "cell_line_alignment_confidence"
                ),
                "predictor_version": PREDICTOR_VERSION,
                "interpretation": (
                    "Predictor-supported preclinical comparator context. Not an "
                    "overlap nomination, clinical efficacy probability, or dose recommendation."
                ),
            }
        )
    rows.sort(key=lambda row: row["integrated_combination_priority"], reverse=True)
    for rank, row in enumerate(rows, start=1):
        row["rank"] = rank
    return rows


def attach_predictor_context(
    clinical_comparators: list[dict], predictor_rows: list[dict]
) -> list[dict]:
    by_drug = {normalize_drug_name(row["drug"]): row for row in predictor_rows}
    for comparator in clinical_comparators:
        predictor = by_drug.get(normalize_drug_name(comparator["drug"]))
        comparator["predictor_evidence"] = predictor
        expression_percentile = comparator.get("dual_support_percentile")
        predictor_percentile = (
            predictor.get("within_patient_predictor_percentile") if predictor else None
        )
        expression_high = (
            expression_percentile is not None and expression_percentile >= 0.75
        )
        predictor_high = (
            predictor_percentile is not None and predictor_percentile >= 0.75
        )
        if expression_high and predictor_high:
            concordance = "concordant_high"
        elif expression_high:
            concordance = "expression_only"
        elif predictor_high:
            concordance = "predictor_only"
        else:
            concordance = "low_or_uncertain"
        comparator["evidence_concordance"] = concordance
    return clinical_comparators


def _optional_float(value) -> float | None:
    try:
        output = float(value)
        return output if np.isfinite(output) else None
    except (TypeError, ValueError):
        return None


def _split_targets(value) -> list[str]:
    if value is None or pd.isna(value):
        return []
    return sorted({item for item in str(value).split(";") if item})
