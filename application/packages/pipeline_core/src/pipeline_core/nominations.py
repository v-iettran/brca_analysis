"""Canonical List 1 ∩ List 2 overlap nominations and evidence tiers."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from pipeline_core.drug_names import normalize_drug_name


BREAST_CONTEXT_DRUGS = {
    "paclitaxel",
    "docetaxel",
    "doxorubicin",
    "epirubicin",
    "5-fluorouracil",
    "cyclophosphamide",
    "carboplatin",
    "cisplatin",
    "gemcitabine",
    "capecitabine",
    "olaparib",
    "talazoparib",
    "niraparib",
    "rucaparib",
    "alpelisib",
    "capivasertib",
    "palbociclib",
    "ribociclib",
    "abemaciclib",
    "lapatinib",
    "trastuzumab",
    "pertuzumab",
    "tamoxifen",
    "letrozole",
    "anastrozole",
    "exemestane",
    "everolimus",
    "sacituzumab govitecan",
}


STRESS_TOXICITY_MARKERS = {
    "heat shock",
    "hsp90",
    "hsp70",
    "proteasome",
    "ubiquitin",
    "oxidative stress",
    "dna damage response",
    "general cytotoxicity",
    "tubulin",
    "hdac",
}

GENERIC_STRESS_DRUGS = {
    "tanespimycin",
    "geldanamycin",
    "17-aag",
    "17-dmag",
    "pu-h71",
    "alsaprazole",
    "withaferin-a",
}


@dataclass
class RobustnessFlags:
    low_coverage: bool = False
    single_cell_line: bool = False
    low_consistency: bool = False
    weak_dual_support: bool = False
    generic_stress_pattern: bool = False
    missing_target_pathway_support: bool = False
    likely_artifact: bool = False
    notes: list[str] | None = None

    def to_dict(self) -> dict:
        return {
            "low_coverage": self.low_coverage,
            "single_cell_line": self.single_cell_line,
            "low_consistency": self.low_consistency,
            "weak_dual_support": self.weak_dual_support,
            "generic_stress_pattern": self.generic_stress_pattern,
            "missing_target_pathway_support": self.missing_target_pathway_support,
            "likely_artifact": self.likely_artifact,
            "notes": self.notes or [],
        }


def _ensure_canonical(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "canonical" not in out.columns:
        out["canonical"] = out["drug"].map(normalize_drug_name)
    else:
        out["canonical"] = out["canonical"].map(normalize_drug_name)
    return out


def _rank_product(p1: float, p2: float) -> float:
    return float(np.sqrt(max(p1, 0.0) * max(p2, 0.0)))


def adjudicate_hit(row: dict, list1_pct: float, list2_pct: float) -> RobustnessFlags:
    notes: list[str] = []
    flags = RobustnessFlags(notes=notes)
    n_cell = row.get("n_cell_lines")
    consistency = row.get("consistency")
    coverage = row.get("coverage_fraction") or row.get("gene_coverage")
    targets = row.get("targets") or []
    canonical = str(row.get("canonical") or row.get("drug") or "").lower()
    min_pct = min(list1_pct, list2_pct)

    if min_pct < 0.55:
        flags.weak_dual_support = True
        notes.append("Weaker of the two list percentiles is below 0.55.")
    if coverage is not None and float(coverage) < 0.5:
        flags.low_coverage = True
        notes.append("Signature gene coverage for this hit is below 50%.")
    if n_cell is not None and int(n_cell) <= 1:
        flags.single_cell_line = True
        notes.append("Supported in only one cell line in the compact artifact.")
    if consistency is not None and float(consistency) < 0.4:
        flags.low_consistency = True
        notes.append("Low directional consistency across signatures.")
    if canonical in GENERIC_STRESS_DRUGS or any(
        marker in " ".join(str(t).lower() for t in targets) for marker in STRESS_TOXICITY_MARKERS
    ):
        flags.generic_stress_pattern = True
        notes.append("Hit resembles a generic stress/toxicity transcriptional pattern.")
    if not targets:
        flags.missing_target_pathway_support = True
        notes.append("No annotated target/pathway support available for this compound.")
    artifact_votes = sum(
        [
            flags.weak_dual_support,
            flags.single_cell_line,
            flags.low_consistency,
            flags.generic_stress_pattern,
            flags.low_coverage,
        ]
    )
    if artifact_votes >= 2 or (flags.weak_dual_support and (flags.single_cell_line or flags.low_consistency)):
        flags.likely_artifact = True
        notes.append("Flagged as possible technical/biological artifact pending literature review.")
    return flags


def indication_bucket(canonical: str) -> str:
    if canonical in BREAST_CONTEXT_DRUGS:
        return "breast_context"
    # Common chemotherapies / targeted agents with other primary indications.
    other_known = {
        "rapamycin",
        "temsirolimus",
        "sirolimus",
        "imatinib",
        "dasatinib",
        "sunitinib",
        "sorafenib",
        "vorinostat",
        "panobinostat",
        "bortezomib",
        "tanespimycin",
    }
    if canonical in other_known:
        return "repurposing_hypothesis"
    return "unclassified_or_investigational"


def evidence_tier(flags: RobustnessFlags, indication: str, has_trial_potential: bool = False) -> str:
    if flags.likely_artifact:
        return "tier_d_artifact_or_insufficient"
    if has_trial_potential:
        return "tier_a_potential_trial_match"
    if indication == "breast_context":
        return "tier_b_breast_preclinical_or_investigational"
    return "tier_c_novel_repurposing_hypothesis"


def nominate_overlap(
    list1: pd.DataFrame,
    list2: pd.DataFrame,
    top_n: int = 25,
    near_consensus_delta: float = 0.05,
) -> dict:
    """Return dual-supported overlap nominations plus near-consensus secondaries.

    Ranking prefers the weaker of the two percentiles so both arms must be strong.
    Rank-product is only a tie-breaker.
    """
    a = _ensure_canonical(list1)
    b = _ensure_canonical(list2)
    a = a.drop_duplicates("canonical", keep="first").set_index("canonical")
    b = b.drop_duplicates("canonical", keep="first").set_index("canonical")

    shared = sorted(set(a.index) & set(b.index))
    overlap_rows = []
    for canonical in shared:
        r1 = a.loc[canonical]
        r2 = b.loc[canonical]
        p1 = float(r1["percentile"])
        p2 = float(r2["percentile"])
        weaker = min(p1, p2)
        stronger = max(p1, p2)
        row = {
            "drug": r1["drug"] if "drug" in r1 else canonical,
            "canonical": canonical,
            "list1_percentile": p1,
            "list2_percentile": p2,
            "weaker_percentile": weaker,
            "stronger_percentile": stronger,
            "rank_product": _rank_product(p1, p2),
            "list1_rank": int(r1["rank"]) if pd.notna(r1.get("rank")) else None,
            "list2_rank": int(r2["rank"]) if pd.notna(r2.get("rank")) else None,
            "list1_score": float(r1["reversal_score"]) if pd.notna(r1.get("reversal_score")) else None,
            "list2_score": float(r2["reversal_score"]) if pd.notna(r2.get("reversal_score")) else None,
            "targets": sorted(
                set((r1["targets"] if isinstance(r1.get("targets"), list) else []) or [])
                | set((r2["targets"] if isinstance(r2.get("targets"), list) else []) or [])
            ),
            "list1_source": r1.get("source"),
            "list2_source": r2.get("source"),
            "n_signatures": r2.get("n_signatures") or r1.get("n_signatures"),
            "n_cell_lines": r2.get("n_cell_lines") or r1.get("n_cell_lines"),
            "consistency": r2.get("consistency") if pd.notna(r2.get("consistency")) else r1.get("consistency"),
        }
        flags = adjudicate_hit(row, p1, p2)
        indication = indication_bucket(canonical)
        row["robustness"] = flags.to_dict()
        row["indication_bucket"] = indication
        row["evidence_tier"] = evidence_tier(flags, indication)
        overlap_rows.append(row)

    overlap = pd.DataFrame(overlap_rows)
    if not overlap.empty:
        overlap = overlap.sort_values(
            ["weaker_percentile", "rank_product"], ascending=[False, False]
        ).reset_index(drop=True)
        overlap["nomination_rank"] = np.arange(1, len(overlap) + 1)
        compact_dual = (overlap["list1_source"] == "compact_gctx") & (
            overlap["list2_source"] == "compact_gctx"
        )
        multi_line = overlap["n_cell_lines"].fillna(0).astype(float) >= 2
        consistent = overlap["consistency"].fillna(0).astype(float) >= 0.5
        artifact = overlap["robustness"].map(lambda flags: bool((flags or {}).get("likely_artifact")))

        overlap["support_class"] = "suggestive"
        overlap.loc[compact_dual & multi_line & consistent & ~artifact, "support_class"] = (
            "breast_cell_line_supported"
        )
        overlap.loc[artifact, "support_class"] = "excluded_low_confidence"

        overlap["support_rank"] = None
        for support_class in ("breast_cell_line_supported", "suggestive", "excluded_low_confidence"):
            mask = overlap["support_class"] == support_class
            overlap.loc[mask, "support_rank"] = np.arange(1, int(mask.sum()) + 1)

    # Near-consensus: high on one list and within delta of the other list's top ranks.
    near_rows = []
    only1 = set(a.index) - set(b.index)
    only2 = set(b.index) - set(a.index)
    for canonical in list(only1)[:50]:
        r1 = a.loc[canonical]
        if float(r1["percentile"]) >= 0.8:
            near_rows.append(
                {
                    "drug": r1["drug"] if "drug" in r1 else canonical,
                    "canonical": canonical,
                    "side": "list1_only",
                    "percentile": float(r1["percentile"]),
                    "note": "Strong cluster-reversal candidate without residual support.",
                }
            )
    for canonical in list(only2)[:50]:
        r2 = b.loc[canonical]
        if float(r2["percentile"]) >= 0.8:
            near_rows.append(
                {
                    "drug": r2["drug"] if "drug" in r2 else canonical,
                    "canonical": canonical,
                    "side": "list2_only",
                    "percentile": float(r2["percentile"]),
                    "note": "Strong residual-reversal candidate without cluster-list support.",
                }
            )

    supported = (
        overlap[overlap["support_class"] == "breast_cell_line_supported"]
        if not overlap.empty
        else overlap
    )
    suggestive = (
        overlap[overlap["support_class"] == "suggestive"]
        if not overlap.empty
        else overlap
    )
    excluded = (
        overlap[overlap["support_class"] == "excluded_low_confidence"]
        if not overlap.empty
        else overlap
    )
    # Return independently ranked, independently capped sublists. Supported
    # compounds are shown first; consumers split by support_class.
    visible = pd.concat(
        [supported.head(top_n), suggestive.head(top_n)], ignore_index=True
    )

    return {
        "overlap": visible.to_dict(orient="records") if not visible.empty else [],
        "supported": supported.head(top_n).to_dict(orient="records") if not supported.empty else [],
        "suggestive": suggestive.head(top_n).to_dict(orient="records") if not suggestive.empty else [],
        "excluded_low_confidence": (
            excluded.head(top_n).to_dict(orient="records") if not excluded.empty else []
        ),
        "near_consensus": near_rows[:20],
        "n_list1": int(len(a)),
        "n_list2": int(len(b)),
        "n_overlap": int(len(shared)),
        "n_supported": int(len(supported)),
        "n_suggestive": int(len(suggestive)),
        "n_excluded_low_confidence": int(len(excluded)),
        "ranking_rule": (
            "Primary key = min(list1_percentile, list2_percentile); "
            "tie-break = sqrt(list1 * list2). Each support class is ranked separately. "
            "Breast-cell-line-supported requires independent compact-GCTX scoring, "
            "at least two breast cell lines, consistency >= 0.5, and no artifact flag."
        ),
    }
