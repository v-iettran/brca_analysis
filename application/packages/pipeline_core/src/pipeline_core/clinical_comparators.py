"""Expression-ranked clinical-context comparators.

These drugs are shown to orient the user against recognizable breast-cancer
treatments. Their presence is not a recommendation and does not imply that
the patient's biomarkers, stage, line of therapy, or regulatory indication
make them applicable.
"""

from __future__ import annotations

import pandas as pd

from pipeline_core.drug_names import normalize_drug_name


CLINICAL_COMPARATORS: dict[str, tuple[str, str]] = {
    # Cytotoxic chemotherapy
    "paclitaxel": ("Chemotherapy", "Taxane used in multiple breast-cancer settings."),
    "docetaxel": ("Chemotherapy", "Taxane used in multiple breast-cancer settings."),
    "doxorubicin": ("Chemotherapy", "Anthracycline used in breast-cancer regimens."),
    "epirubicin": ("Chemotherapy", "Anthracycline used in breast-cancer regimens."),
    "cyclophosphamide": ("Chemotherapy", "Alkylating component of common regimens."),
    "carboplatin": ("Chemotherapy", "Platinum agent used in selected settings."),
    "cisplatin": ("Chemotherapy", "Platinum comparator used in selected settings."),
    "gemcitabine": ("Chemotherapy", "Antimetabolite used in selected advanced settings."),
    "capecitabine": ("Chemotherapy", "Oral fluoropyrimidine used in selected settings."),
    "5-fluorouracil": ("Chemotherapy", "Fluoropyrimidine component of historical regimens."),
    # PARP inhibitors
    "olaparib": ("PARP inhibitor", "Clinical applicability requires qualifying BRCA/HRR and setting."),
    "talazoparib": ("PARP inhibitor", "Clinical applicability requires qualifying BRCA/HRR and setting."),
    "niraparib": ("PARP inhibitor", "Tracked PARP-class comparator; breast indication is setting-dependent."),
    "rucaparib": ("PARP inhibitor", "Tracked PARP-class comparator; breast indication is setting-dependent."),
    "veliparib": ("PARP inhibitor", "Investigational/clinical-study PARP-class comparator."),
    # Endocrine therapy
    "tamoxifen": ("Endocrine therapy", "ER-directed therapy; applicability requires hormone-receptor context."),
    "letrozole": ("Endocrine therapy", "Aromatase inhibitor; applicability requires endocrine context."),
    "anastrozole": ("Endocrine therapy", "Aromatase inhibitor; applicability requires endocrine context."),
    "exemestane": ("Endocrine therapy", "Aromatase inhibitor; applicability requires endocrine context."),
    "fulvestrant": ("Endocrine therapy", "Estrogen-receptor degrader used in selected settings."),
    # Targeted small molecules
    "palbociclib": ("CDK4/6 inhibitor", "HR-positive/HER2-negative context, setting-dependent."),
    "ribociclib": ("CDK4/6 inhibitor", "HR-positive/HER2-negative context, setting-dependent."),
    "abemaciclib": ("CDK4/6 inhibitor", "HR-positive/HER2-negative context, risk/setting-dependent."),
    "alpelisib": ("PI3K/AKT/mTOR inhibitor", "Applicability requires a qualifying PIK3CA context."),
    "capivasertib": ("PI3K/AKT/mTOR inhibitor", "Applicability is alteration- and setting-dependent."),
    "everolimus": ("PI3K/AKT/mTOR inhibitor", "mTOR inhibitor used with endocrine therapy in selected settings."),
    "rapamycin": ("PI3K/AKT/mTOR inhibitor", "Preclinical mTOR-class comparator; not a standard breast-cancer regimen."),
    "temsirolimus": ("PI3K/AKT/mTOR inhibitor", "mTOR-class comparator with setting-dependent investigational context."),
    "lapatinib": ("HER2-targeted small molecule", "Applicability requires HER2-positive disease context."),
    "neratinib": ("HER2-targeted small molecule", "Applicability requires HER2-positive disease context."),
    "tucatinib": ("HER2-targeted small molecule", "Applicability requires HER2-positive disease context."),
}


def expression_ranked_comparators(
    list1: pd.DataFrame,
    list2: pd.DataFrame,
    cluster_reference: pd.DataFrame | None = None,
) -> list[dict]:
    """Return curated clinical comparators with their actual expression ranks."""
    a = list1.copy()
    b = list2.copy()
    if "canonical" not in a.columns:
        a = pd.DataFrame(columns=["canonical", "drug", "rank", "percentile", "targets"])
    if "canonical" not in b.columns:
        b = pd.DataFrame(columns=["canonical", "drug", "rank", "percentile", "targets"])
    a["canonical"] = a["canonical"].map(normalize_drug_name)
    b["canonical"] = b["canonical"].map(normalize_drug_name)
    a = a.drop_duplicates("canonical", keep="first").set_index("canonical")
    b = b.drop_duplicates("canonical", keep="first").set_index("canonical")
    reference = pd.DataFrame()
    if cluster_reference is not None and not cluster_reference.empty:
        reference = cluster_reference.reset_index(drop=True).copy()
        reference["canonical"] = reference["drug"].map(normalize_drug_name)
        reference = reference.sort_values("drug_rank").drop_duplicates("canonical").set_index("canonical")

    rows: list[dict] = []
    for canonical, (category, context) in CLINICAL_COMPARATORS.items():
        if canonical not in a.index and canonical not in b.index and canonical not in reference.index:
            continue
        r1 = a.loc[canonical] if canonical in a.index else None
        r2 = b.loc[canonical] if canonical in b.index else None
        rr = reference.loc[canonical] if canonical in reference.index else None
        p1 = float(r1["percentile"]) if r1 is not None else float(rr["percentile"]) if rr is not None else None
        p2 = float(r2["percentile"]) if r2 is not None else None
        rows.append(
            {
                "drug": (
                    str(r1["drug"])
                    if r1 is not None
                    else str(r2["drug"]) if r2 is not None else str(rr["drug"]) if rr is not None else canonical
                ),
                "canonical": canonical,
                "category": category,
                "clinical_context": context,
                "list1_rank": int(r1["rank"]) if r1 is not None else int(rr["drug_rank"]) if rr is not None else None,
                "list2_rank": int(r2["rank"]) if r2 is not None else None,
                "list1_percentile": p1,
                "list2_percentile": p2,
                "dual_support_percentile": min(p1, p2) if r1 is not None and r2 is not None else None,
                "present_in_both_lists": r1 is not None and r2 is not None,
                "list1_source": "patient_cluster_compact_gctx" if r1 is not None else "mofa_cluster_reference_gctx",
                "list2_source": "patient_residual_compact_gctx" if r2 is not None else None,
                "targets": sorted(
                    set((r1.get("targets") if r1 is not None and isinstance(r1.get("targets"), list) else []) or [])
                    | set((r2.get("targets") if r2 is not None and isinstance(r2.get("targets"), list) else []) or [])
                    | set(
                        str(rr.get("targets")).split(";")
                        if rr is not None and pd.notna(rr.get("targets"))
                        else []
                    )
                ),
                "interpretation": (
                    "Expression-ranked clinical comparator only. "
                    + (
                        "The compact patient-residual artifact did not contain this compound; "
                        "the displayed List 1 rank comes from the expression-derived MOFA cluster table. "
                        if r2 is None
                        else ""
                    )
                    + "Rank is not treatment eligibility, efficacy, approval, or a recommendation."
                ),
            }
        )

    category_order = {
        "Chemotherapy": 0,
        "PARP inhibitor": 1,
        "Endocrine therapy": 2,
        "CDK4/6 inhibitor": 3,
        "PI3K/AKT/mTOR inhibitor": 4,
        "HER2-targeted small molecule": 5,
    }
    rows.sort(
        key=lambda row: (
            category_order.get(row["category"], 99),
            -(row["dual_support_percentile"] if row["dual_support_percentile"] is not None else -1),
            row["drug"].lower(),
        )
    )
    return rows
