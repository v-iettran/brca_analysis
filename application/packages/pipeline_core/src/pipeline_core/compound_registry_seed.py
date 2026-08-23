"""Curated seed records for the human-development compound registry.

These rows cover breast-context therapies, clinical comparators, known
LINCS tool/toxic hits, and a few investigational compounds. Offline jobs
merge optional ChEMBL/DrugCentral dumps and human-approved reviews on top.
"""

from __future__ import annotations

from pipeline_core.nominations import BREAST_CONTEXT_DRUGS, GENERIC_STRESS_DRUGS

CHEMBL_SOURCE = {
    "source": "ChEMBL",
    "version": "chembl_35",
    "url": "https://ftp.ebi.ac.uk/pub/databases/chembl/ChEMBLdb/releases/chembl_35/schema_documentation.html",
    "field_provenance": "max_phase / withdrawn_flag / molecule_type (seeded snapshot)",
}
DRUGCENTRAL_SOURCE = {
    "source": "DrugCentral",
    "version": "2024",
    "url": "https://www.drugcentral.org/about",
    "field_provenance": "approval / off-market status (seeded snapshot)",
}


def _sources(*extra: dict) -> list[dict]:
    return [CHEMBL_SOURCE, DRUGCENTRAL_SOURCE, *extra]


def _approved(
    name: str,
    status: str,
    relevance: str,
    phase: float = 4,
    chembl: str | None = None,
    extra_synonyms: list[str] | None = None,
    reason: str = "approved_human_use",
) -> dict:
    return {
        "canonical": name,
        "display_name": name,
        "synonyms": extra_synonyms or [],
        "chembl_ids": [chembl] if chembl else [],
        "entity_type": "approved_drug",
        "max_clinical_phase": phase,
        "human_development_status": status,
        "breast_oncology_relevance": relevance,
        "withdrawn_or_discontinued": False,
        "display_action": "default_visible",
        "display_gate_reason": reason,
        "sources": _sources(),
        "reviewed_by": "seed",
        "reviewed_at": "2026-08-20",
    }


def _candidate(name: str, relevance: str = "investigational_breast") -> dict:
    return {
        "canonical": name,
        "display_name": name,
        "synonyms": [],
        "entity_type": "clinical_candidate",
        "max_clinical_phase": 2,
        "human_development_status": "investigational",
        "breast_oncology_relevance": relevance,
        "withdrawn_or_discontinued": False,
        "display_action": "exploratory_only",
        "display_gate_reason": "clinical_candidate_not_approved",
        "sources": _sources(),
        "reviewed_by": "seed",
        "reviewed_at": "2026-08-20",
    }


def _tool(name: str, status: str = "tool_compound", reason: str = "preclinical_tool_compound") -> dict:
    return {
        "canonical": name,
        "display_name": name,
        "synonyms": [],
        "entity_type": "preclinical_tool",
        "max_clinical_phase": None,
        "human_development_status": status,
        "breast_oncology_relevance": "unknown",
        "withdrawn_or_discontinued": False,
        "display_action": "technical_excluded",
        "display_gate_reason": reason,
        "sources": _sources(),
        "reviewed_by": "seed",
        "reviewed_at": "2026-08-20",
    }


def _withdrawn(name: str) -> dict:
    return {
        "canonical": name,
        "display_name": name,
        "synonyms": [],
        "entity_type": "withdrawn",
        "max_clinical_phase": 4,
        "human_development_status": "withdrawn",
        "breast_oncology_relevance": "unknown",
        "withdrawn_or_discontinued": True,
        "display_action": "technical_excluded",
        "display_gate_reason": "withdrawn_or_discontinued",
        "sources": _sources(),
        "reviewed_by": "seed",
        "reviewed_at": "2026-08-20",
    }


def _non_drug(name: str) -> dict:
    return {
        "canonical": name,
        "display_name": name,
        "synonyms": [],
        "entity_type": "non_therapeutic_perturbagen",
        "max_clinical_phase": None,
        "human_development_status": "non_drug_perturbagen",
        "breast_oncology_relevance": "non_oncology",
        "withdrawn_or_discontinued": False,
        "display_action": "technical_excluded",
        "display_gate_reason": "non_therapeutic_perturbagen",
        "sources": _sources(),
        "reviewed_by": "seed",
        "reviewed_at": "2026-08-20",
    }


def seed_records() -> list[dict]:
    records: list[dict] = []

    breast = {
        "paclitaxel": "CHEMBL428647",
        "docetaxel": "CHEMBL92",
        "doxorubicin": "CHEMBL53463",
        "epirubicin": "CHEMBL417",
        "5-fluorouracil": "CHEMBL185",
        "cyclophosphamide": "CHEMBL88",
        "carboplatin": "CHEMBL11359",
        "cisplatin": "CHEMBL11359",
        "gemcitabine": "CHEMBL848",
        "capecitabine": "CHEMBL1773",
        "olaparib": "CHEMBL521686",
        "talazoparib": "CHEMBL3137320",
        "niraparib": "CHEMBL2204920",
        "rucaparib": "CHEMBL1173055",
        "alpelisib": "CHEMBL2396661",
        "capivasertib": "CHEMBL2325741",
        "palbociclib": "CHEMBL189963",
        "ribociclib": "CHEMBL3545110",
        "abemaciclib": "CHEMBL3301610",
        "lapatinib": "CHEMBL554",
        "trastuzumab": None,
        "pertuzumab": None,
        "tamoxifen": "CHEMBL83",
        "letrozole": "CHEMBL1421",
        "anastrozole": "CHEMBL1399",
        "exemestane": "CHEMBL1200374",
        "everolimus": "CHEMBL1201750",
        "sacituzumab govitecan": None,
        "fulvestrant": "CHEMBL1201186",
        "neratinib": "CHEMBL180022",
        "tucatinib": "CHEMBL2103838",
    }
    for name, chembl in breast.items():
        records.append(
            _approved(
                name,
                "approved_breast",
                "approved_breast",
                chembl=chembl,
                extra_synonyms=["5 fu", "fluorouracil"] if name == "5-fluorouracil" else None,
            )
        )

    other_oncology = {
        "imatinib": "CHEMBL941",
        "dasatinib": "CHEMBL1421",
        "sunitinib": "CHEMBL535",
        "sorafenib": "CHEMBL1336",
        "crizotinib": "CHEMBL601719",
        "ceritinib": "CHEMBL2403108",
        "vorinostat": "CHEMBL98",
        "panobinostat": "CHEMBL483254",
        "romidepsin": "CHEMBL434349",
        "bortezomib": "CHEMBL325041",
        "temsirolimus": "CHEMBL1201180",
    }
    for name, chembl in other_oncology.items():
        records.append(
            _approved(name, "approved_oncology", "other_oncology", chembl=chembl, reason="approved_oncology_not_breast_standard")
        )

    other_human = {
        "rapamycin": ("sirolimus", "CHEMBL413"),
        "alogliptin": ("alogliptin", "CHEMBL180815"),
        "phenylephrine": ("phenylephrine", "CHEMBL1215"),
        "etofylline": ("etofylline", None),
    }
    for name, (synonym, chembl) in other_human.items():
        rec = _approved(
            name,
            "approved_human_repurposing",
            "non_oncology",
            chembl=chembl,
            extra_synonyms=[synonym] if synonym != name else [],
            reason="approved_human_non_oncology",
        )
        records.append(rec)

    for name in ("veliparib", "nvp-bez235", "dactolisib", "alvocidib", "at-7519"):
        records.append(_candidate(name))

    for name in GENERIC_STRESS_DRUGS:
        records.append(_tool(name, reason="generic_stress_or_hsp_probe"))

    for name, reason in [
        ("emetine", "known_tool_or_high_toxicity_probe"),
        ("mg-132", "proteasome_probe_not_a_therapeutic"),
        ("wortmannin", "pi3k_tool_compound"),
        ("a-443654", "akt_tool_compound"),
        ("bix-01294", "epigenetic_probe"),
        ("amg-517", "trpv1_probe_not_oncology_standard"),
        ("pha-793887", "cdk_tool_compound"),
        ("pha-848125", "cdk_tool_compound"),
        ("withaferin-a", "natural_product_probe"),
    ]:
        records.append(_tool(name, reason=reason))

    records.append(_non_drug("methylene-blue"))
    records.append(_non_drug("methylene blue"))
    records.append(_withdrawn("troglitazone"))

    # Deduplicate by canonical, first write wins (breast context first).
    by_name: dict[str, dict] = {}
    for row in records:
        by_name.setdefault(row["canonical"], row)
    # Ensure every breast-context drug is present.
    for name in BREAST_CONTEXT_DRUGS:
        by_name.setdefault(
            name,
            _approved(name, "approved_breast", "approved_breast"),
        )
    return list(by_name.values())
