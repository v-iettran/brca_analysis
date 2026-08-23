"""Approve a compound-registry review decision and rebuild the registry."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from pipeline_core.config import COMPOUND_REVIEW_QUEUE_DIR
from pipeline_core.drug_names import normalize_drug_name

_JOBS_DIR = Path(__file__).resolve().parent
if str(_JOBS_DIR) not in sys.path:
    sys.path.insert(0, str(_JOBS_DIR))

from build_compound_registry import build_registry  # noqa: E402


def approve(
    canonical: str,
    reviewer: str,
    entity_type: str,
    human_development_status: str,
    display_action: str,
    reason: str,
    citations: list[dict] | None = None,
) -> Path:
    if not reviewer.strip():
        raise ValueError("reviewer identity is required")
    if not citations:
        raise ValueError("at least one citation is required")
    COMPOUND_REVIEW_QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    path = COMPOUND_REVIEW_QUEUE_DIR / "approved_decisions.jsonl"
    decision = {
        "canonical": normalize_drug_name(canonical),
        "entity_type": entity_type,
        "human_development_status": human_development_status,
        "display_action": display_action,
        "display_gate_reason": reason,
        "citations": citations,
        "reviewer": reviewer,
        "reviewed_by": reviewer,
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
    }
    with path.open("a") as handle:
        handle.write(json.dumps(decision) + "\n")
    build_registry(approvals_path=path)
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("canonical")
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--entity-type", required=True)
    parser.add_argument("--status", required=True, dest="human_development_status")
    parser.add_argument("--display-action", required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--citations", type=Path, required=True, help="JSON list of citation objects")
    args = parser.parse_args()
    citations = json.loads(args.citations.read_text())
    path = approve(
        args.canonical,
        args.reviewer,
        args.entity_type,
        args.human_development_status,
        args.display_action,
        args.reason,
        citations,
    )
    print(f"Appended approval to {path} and rebuilt registry")


if __name__ == "__main__":
    main()
