"""Propose registry classifications for unresolved compounds.

This job only writes review-queue proposals with citations. It never merges
into the runtime registry. A human must run approve_compound_review.py.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from pipeline_core.config import COMPOUND_REVIEW_QUEUE_DIR


def _heuristic_proposal(canonical: str, anonymous: bool) -> dict:
    if anonymous or canonical.startswith("brd ") or canonical.startswith("sa "):
        return {
            "proposed_entity_type": "non_therapeutic_perturbagen",
            "proposed_human_development_status": "non_drug_perturbagen",
            "proposed_display_action": "technical_excluded",
            "evidence_summary": "Anonymous LINCS identifier without a mapped INN/USAN name.",
        }
    return {
        "proposed_entity_type": "unresolved",
        "proposed_human_development_status": "unresolved",
        "proposed_display_action": "technical_excluded",
        "evidence_summary": "No committed ChEMBL/DrugCentral match; keep excluded until reviewed.",
    }


def propose(limit: int = 50, citations_file: Path | None = None) -> Path:
    queue_path = COMPOUND_REVIEW_QUEUE_DIR / "unresolved_candidates.parquet"
    if not queue_path.exists():
        raise FileNotFoundError(f"Run scan_unresolved_compounds.py first ({queue_path})")
    frame = pd.read_parquet(queue_path).head(limit)
    extra_citations = json.loads(citations_file.read_text()) if citations_file else {}
    out_path = COMPOUND_REVIEW_QUEUE_DIR / "proposals.jsonl"
    with out_path.open("w") as handle:
        for _, row in frame.iterrows():
            canonical = row["canonical"]
            proposal = _heuristic_proposal(canonical, bool(row.get("anonymous_lincs_id")))
            record = {
                "canonical": canonical,
                **proposal,
                "citations": extra_citations.get(canonical, []),
                "proposer": "scan_heuristic",
                "proposed_at": datetime.now(timezone.utc).isoformat(),
                "priority_rank": int(row.get("priority_rank") or 0),
            }
            handle.write(json.dumps(record) + "\n")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--citations", type=Path, default=None)
    args = parser.parse_args()
    path = propose(args.limit, args.citations)
    print(f"Wrote proposals to {path}")


if __name__ == "__main__":
    main()
