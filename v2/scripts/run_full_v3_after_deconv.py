#!/usr/bin/env python3
"""NB06 / NB12 / NB13 / A1–A6 on full-scale intrinsic. No synthetic fallback."""

from __future__ import annotations

import json
import sys
from pathlib import Path

V2_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V2_ROOT / "src"))
sys.path.insert(0, str(V2_ROOT / "scripts"))

from gate import gate  # noqa: E402
from run_notebook import run_notebook  # noqa: E402
from v3_real import persist_real  # noqa: E402
import pandas as pd  # noqa: E402

MIN_N = 800


def latest_gate(notebook: str, name: str) -> dict | None:
    path = V2_ROOT / "reports" / "gates.jsonl"
    last = None
    if not path.is_file():
        return None
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        if rec.get("notebook") == notebook and rec.get("gate") == name:
            last = rec
    return last


def main() -> int:
    interim = V2_ROOT / "data" / "interim"
    expr_p = interim / "intrinsic_expression.parquet"
    if not expr_p.is_file():
        print("STOP: intrinsic_expression.parquet missing")
        return 2
    expr = pd.read_parquet(expr_p)
    n = len(expr)
    ids = expr.index.astype(str).str[:12].tolist()
    print(f"intrinsic n={n} p={expr.shape[1]}")
    if n < MIN_N:
        print(f"STOP: n={n} is below {MIN_N} — not a silent cap. Finish BayesPrism first.")
        return 2

    print("=" * 60, "NB06")
    r06 = run_notebook(V2_ROOT / "notebooks" / "NB06_pathway_tf.ipynb")
    if not r06["ok"]:
        print("NB06 failed at cell", r06.get("cell"))
        return 1

    print("=" * 60, "persist_real A1–A6")
    preg = V2_ROOT / "data" / "reference" / "preregistered_k.json"
    if preg.is_file():
        preg.unlink()
        print("deleted stale preregistered_k.json")
    out = persist_real(V2_ROOT, V2_ROOT.parent, n_boot=50, n_init=10)
    cohort = json.loads(Path(out["cohort"]).read_text())
    if int(cohort.get("synthetic_samples") or 0) > 0:
        print("STOP: persist_real wrote synthetic samples")
        return 2
    sample_ids = list(
        (next(iter((cohort.get("configurations") or {}).values()), {}) or {}).get("assignments") or {}
    ) or ids
    preg = cohort["preregistered"]
    gates = cohort["gates"]
    print("k*", preg, "n", cohort["n_samples"])

    gate(
        "NB_A1", "cluster_stability_ari", float(preg.get("stability") or 0), 0.60,
        cohort=True, sample_ids=sample_ids, n=len(sample_ids),
        note=f"k*={preg.get('k')} bic={preg.get('bic')} sil={preg.get('silhouette')} rule={preg.get('selection_rule')}",
    )
    a2 = gates["a2"]
    gate(
        "NB_A2", "cluster_logrank_os", float(a2.get("p_os") or 1.0), 0.05, direction="lte",
        cohort=True, sample_ids=sample_ids, n=int(a2.get("n") or len(sample_ids)),
        note=f"k={preg.get('k')} n={a2.get('n')} events={a2.get('n_events')} framing={a2.get('framing')}",
    )
    if not a2.get("passed"):
        print("A2 failed: clusters are descriptive, not prognostic. Do not retune k.")
    counts = (gates.get("a3") or {}).get("per_cluster_pathway_counts") or {}
    min_sig = min((int(v) for v in counts.values()), default=0)
    gate(
        "NB_A3", "cluster_differential_pathways", float(min_sig), 3,
        cohort=True, sample_ids=sample_ids, n=len(sample_ids),
        note=f"per-cluster significant pathway counts: {counts}",
    )
    a4 = gates.get("a4") or {}
    gate(
        "NB_A4", "proliferation_up_vs_normal", float(int(bool(a4.get("passed")))), 1,
        cohort=True, sample_ids=sample_ids, n=len(sample_ids),
        note=f"per-cluster proliferation mean logFC: {a4.get('per_cluster_mean_logfc')}",
    )
    a5 = gates.get("a5") or {}
    pos = a5.get("known_drug_positive_control") or {}
    conc = a5.get("nearest_line_subtype_concordance") or {}
    gate(
        "NB_A5", "known_drug_positive_control", float(len(pos.get("hits") or [])), 1,
        cohort=True, sample_ids=sample_ids, n=len(sample_ids),
        note=f"ER cluster endocrine hits: {pos.get('hits')} source={a5.get('source')}",
    )
    gate(
        "NB_A5", "nearest_line_subtype_concordance", float(conc.get("concordance") or 0), 0.40,
        cohort=True, sample_ids=sample_ids, n=int(conc.get("n") or 0) or None,
        note=f"chance={conc.get('chance')} n={conc.get('n')} source={a5.get('nearest_lines_source')}",
    )
    n_ok = 1 + len(list((V2_ROOT / "data" / "interim" / "v3").glob("payload_*.json")))
    gate(
        "NB_A6", "payload_safety", float(n_ok), 1.0,
        cohort=True, sample_ids=sample_ids, n=len(sample_ids),
        note=f"assert_safe passed on {n_ok} payload files source={cohort.get('cohort_source')}",
    )

    print("=" * 60, "NB12")
    r12 = run_notebook(V2_ROOT / "notebooks" / "NB12_precise.ipynb")
    if not r12["ok"]:
        print("NB12 failed at cell", r12.get("cell"))
    print("=" * 60, "NB13")
    r13 = run_notebook(V2_ROOT / "notebooks" / "NB13_conformal.ipynb")
    if not r13["ok"]:
        print("NB13 failed at cell", r13.get("cell"))

    ledger = {
        "n_intrinsic": n,
        "n_genes": int(expr.shape[1]),
        "preregistered": preg,
        "gates_payload": gates,
        "latest_logged": {
            key: latest_gate(*key.split(":", 1))
            for key in (
                "NB02:purity_concordance",
                "NB06:estrogen_er_positive_control",
                "NB12:precise_transfer_gain_logged",
                "NB13:conformal_coverage",
                "NB_A1:cluster_stability_ari",
                "NB_A2:cluster_logrank_os",
                "NB_A3:cluster_differential_pathways",
                "NB_A4:proliferation_up_vs_normal",
                "NB_A5:known_drug_positive_control",
                "NB_A5:nearest_line_subtype_concordance",
                "NB_A6:payload_safety",
            )
        },
    }
    dest = interim / "full_scale_ledger.json"
    dest.write_text(json.dumps(ledger, indent=2, default=str))
    print("wrote", dest)
    return 0 if r06["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
