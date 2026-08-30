#!/usr/bin/env python3
"""Compose the breast-cancer evidence reference used to tier features.

The tier is a **curated claim**, not a computed result, so it is built from
named sources and written to a committed file with a date. Nothing here is
inferred from this cohort's own data: a tier derived from the same expression
matrix it then annotates would be circular.

Three tiers:

  established      — acts on clinical practice today: the PAM50 subtyping panel,
                     recurrent breast drivers, and the pathways breast therapies
                     are actually aimed at.
  investigational  — real breast-cancer literature, no established clinical action.
  not_established  — no curated breast-cancer role. Absence of evidence in this
                     file, not evidence of absence.
"""

from __future__ import annotations

import datetime
import json
import sys
from pathlib import Path

V2_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V2_ROOT / "src"))

from pam50 import PAM50_GENES  # noqa: E402
from tcga_normals import PROLIF_GENES  # noqa: E402

# Recurrently altered in breast cancer with an established clinical or
# prognostic role. Sources named per group below.
BREAST_DRIVERS = {
    "TP53", "PIK3CA", "BRCA1", "BRCA2", "PALB2", "ATM", "CHEK2", "CDH1",
    "GATA3", "MAP3K1", "PTEN", "AKT1", "RB1", "CCND1", "FGFR1", "MYC",
    "NF1", "ARID1A", "KMT2C", "NCOR1", "TBX3", "RUNX1", "SF3B1", "PTPRD",
    "ERBB2", "ERBB3", "ESR1", "PGR", "AR", "MDM2", "EGFR", "MKI67",
}

# Targets of the standard-of-care agents in pipeline_core.nominations.
SOC_TARGETS = {
    "ESR1", "PGR", "ERBB2", "ERBB3", "EGFR", "CDK4", "CDK6", "PIK3CA",
    "AKT1", "MTOR", "PARP1", "PARP2", "TOP2A", "TUBB", "TYMS", "BRCA1", "BRCA2",
}

# PROGENy pathways. Breast therapy acts directly on the first group.
PATHWAYS_ESTABLISHED = {"Estrogen", "EGFR", "PI3K", "MAPK", "p53"}
PATHWAYS_INVESTIGATIONAL = {
    "Androgen", "JAK-STAT", "NFkB", "Hypoxia", "TGFb", "VEGF", "WNT",
    "Trail", "TNFa",
}

# Transcription factors with substantial breast-cancer literature.
TF_ESTABLISHED = {"ESR1", "FOXA1", "GATA3", "AR", "MYC", "TP53", "E2F1", "RB1"}
TF_INVESTIGATIONAL = {
    "STAT3", "STAT5A", "STAT5B", "NFKB1", "RELA", "SOX10", "TFAP2C", "CEBPB",
    "CEBPD", "CTNNB1", "NR3C1", "FOS", "JUN", "SP1", "HIF1A", "SNAI1",
    "TWIST1", "ZEB1", "NCOA2", "NCOA3", "FOXM1", "ELF5", "EHF",
}


def main() -> int:
    today = datetime.date.today().isoformat()
    entries: dict[str, dict] = {}

    def put(symbol: str, tier: str, source: str, kind: str) -> None:
        symbol = str(symbol).strip()
        if not symbol:
            return
        rank = {"established": 2, "investigational": 1, "not_established": 0}
        current = entries.get(symbol)
        if current and rank[current["tier"]] >= rank[tier]:
            return
        entries[symbol] = {"tier": tier, "source": source, "kind": kind}

    for gene in PAM50_GENES:
        put(gene, "established", "PAM50 intrinsic subtyping panel (Parker et al. 2009)", "gene")
    for gene in PROLIF_GENES:
        put(gene, "established", "Proliferation module used by the A4 known-biology gate", "gene")
    for gene in BREAST_DRIVERS:
        put(gene, "established", "Recurrent breast-cancer driver (TCGA-BRCA / COSMIC consensus)", "gene")
    for gene in SOC_TARGETS:
        put(gene, "established", "Target of a breast standard-of-care agent (pipeline_core.nominations)", "gene")

    for name in PATHWAYS_ESTABLISHED:
        put(name, "established", "PROGENy pathway targeted by breast standard-of-care therapy", "pathway")
    for name in PATHWAYS_INVESTIGATIONAL:
        put(name, "investigational", "PROGENy pathway with breast-cancer literature, no established clinical action", "pathway")

    for name in TF_ESTABLISHED:
        put(name, "established", "Transcription factor with an established breast-cancer role", "tf")
    for name in TF_INVESTIGATIONAL:
        put(name, "investigational", "Transcription factor with breast-cancer literature, no established clinical action", "tf")

    payload = {
        "schema": "breast_evidence_sets_v1",
        "curated_date": today,
        "default_tier": "not_established",
        "tiers": {
            "established": "Acts on breast-cancer practice today: subtyping, prognosis, or a drug target.",
            "investigational": "Real breast-cancer literature, but no established clinical action.",
            "not_established": "No curated breast-cancer role in this reference. Absence of evidence, not evidence of absence.",
        },
        "caveat": (
            "A curated list, not a computed result. It says what is established in the "
            "literature, never that a feature is or is not important in this cohort."
        ),
        "entries": dict(sorted(entries.items())),
    }

    dest = V2_ROOT / "data" / "reference" / "breast_evidence_sets.json"
    dest.write_text(json.dumps(payload, indent=2))
    counts: dict[str, int] = {}
    for row in entries.values():
        counts[row["tier"]] = counts.get(row["tier"], 0) + 1
    print(f"wrote {dest.relative_to(V2_ROOT.parent)} — {len(entries)} symbols {counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
