"""B5b — pathway-matched candidates. A rule, not a conformal set."""

from __future__ import annotations

import numpy as np
import pandas as pd

from scanb_features import pathway_for_target

# Elevated vs the PROGENy cohort centre. Fixed — not a keep-fraction that
# pretends missing views widen a drug set.
ACTIVITY_THRESHOLD = 0.0
BASIS = "pathway_activity_threshold"


def pathway_candidates(pw_row: pd.Series, pk: pd.DataFrame) -> dict:
    members: list[dict] = []
    for rec in pk.itertuples():
        path = pathway_for_target(getattr(rec, "target_gene", ""))
        col = next((c for c in pw_row.index if str(c).lower() == path.lower()), None)
        act = float(pw_row[col]) if col is not None else 0.0
        members.append(
            {
                "drug": str(rec.drug_name),
                "pathway": path,
                "activity": act,
                "evidence_tier": "A" if bool(getattr(rec, "in_ode_topology", False)) else "B",
            }
        )
    kept = [m for m in members if m["activity"] >= ACTIVITY_THRESHOLD]
    kept.sort(key=lambda m: m["drug"].lower())
    return {
        "basis": BASIS,
        "validated": False,
        "threshold_rule": f"target_pathway_activity >= {ACTIVITY_THRESHOLD}",
        "set_members": [{"drug": m["drug"], "evidence_tier": m["evidence_tier"]} for m in kept],
        "excluded_count": int(len(members) - len(kept)),
        "n_scored": int(len(members)),
    }


def pathway_activity(pw_row: pd.Series, name: str, default: float = 0.0) -> float:
    col = next((c for c in pw_row.index if str(c).lower() == name.lower()), None)
    if col is None:
        return default
    val = pw_row[col]
    return float(val) if np.isfinite(val) else default
