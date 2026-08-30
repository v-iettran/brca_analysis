"""Default 20-node CDK4/6–RB–E2F signed topology (OmniPath-like prior).

NB09 overwrites this with the OmniPath-induced subgraph when the PKN download
succeeds. Edges are signed consensus direction only.
"""

from __future__ import annotations

import json
from pathlib import Path

DEFAULT_EDGES = [
    ("ESR1", "CCND1", 1),
    ("ERBB2", "PIK3CA", 1),
    ("ERBB2", "KRAS", 1),
    ("EGFR", "KRAS", 1),
    ("EGFR", "PIK3CA", 1),
    ("IGF1R", "PIK3CA", 1),
    ("IGF1R", "KRAS", 1),
    ("PIK3CA", "AKT1", 1),
    ("AKT1", "MTOR", 1),
    ("PTEN", "AKT1", -1),
    ("KRAS", "BRAF", 1),
    ("BRAF", "MAP2K1", 1),
    ("MAP2K1", "MAPK1", 1),
    ("MAPK1", "CCND1", 1),
    ("AKT1", "CCND1", 1),
    ("CCND1", "CDK4", 1),
    ("CCND1", "CDK6", 1),
    ("CDK4", "RB1", -1),
    ("CDK6", "RB1", -1),
    ("CDKN2A", "CDK4", -1),
    ("CDKN2A", "CDK6", -1),
    ("CDKN1A", "CDK4", -1),
    ("RB1", "E2F1", -1),
    ("E2F1", "MKI67", 1),
    ("E2F1", "CCND1", 1),
    ("AKT1", "CDKN1A", -1),
    ("MAPK1", "E2F1", 1),
    ("MTOR", "E2F1", 1),
]


def default_topology(nodes: list[str]) -> dict:
    node_set = set(nodes)
    edges = [
        {"source": s, "target": t, "sign": sign, "provenance": "literature_prior"}
        for s, t, sign in DEFAULT_EDGES
        if s in node_set and t in node_set
    ]
    return {"nodes": list(nodes), "edges": edges, "hill_n_fixed": 2.0}


def induced_signed_subgraph(pkn, nodes: list[str]) -> dict:
    """pkn: DataFrame with source, target, sign (or interaction ±1)."""
    node_set = set(nodes)
    sign_col = "sign" if "sign" in pkn.columns else "interaction"
    edges = []
    seen = set()
    for _, row in pkn.iterrows():
        s, t = str(row["source"]), str(row["target"])
        if s not in node_set or t not in node_set:
            continue
        sign = int(row[sign_col])
        key = (s, t, sign)
        if key in seen:
            continue
        seen.add(key)
        edges.append({"source": s, "target": t, "sign": sign, "provenance": "omnipath"})
    return {"nodes": list(nodes), "edges": edges, "hill_n_fixed": 2.0}


def write_topology(topology: dict, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(topology, indent=2))
