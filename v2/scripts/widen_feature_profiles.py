#!/usr/bin/env python3
"""Recompute cluster profiles over every feature, not a variance-ranked slice.

`run_real_pathways.py` kept the top 40 transcription factors and top 60 genes by
variance, which is a reasonable default for a preview but wrong for a reader who
wants to look up a specific gene: a gene absent from the table is
indistinguishable from a gene with no signal.

This recomputes one-vs-rest for all PROGENy pathways, all CollecTRI regulons and
every gene in the intrinsic set, from artifacts already on disk. It does not
retune k, refit clusters, or touch a gate.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

V2_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V2_ROOT / "src"))

from cluster_stats import mannwhitney_one_vs_rest, per_cluster_significant_pathways, welch_one_vs_rest  # noqa: E402
from v3_payload import copy_payloads_to_app, v3_interim  # noqa: E402


def main() -> int:
    interim = V2_ROOT / "data" / "interim"
    dest = v3_interim(V2_ROOT)

    expr = pd.read_parquet(interim / "intrinsic_expression.parquet")
    expr.index = expr.index.astype(str).str[:12]
    expr = expr[~expr.index.duplicated(keep="first")]

    pathway = pd.read_parquet(interim / "pathway_activity.parquet")
    tf = pd.read_parquet(interim / "tf_activity.parquet")
    for frame in (pathway, tf):
        frame.index = frame.index.astype(str).str[:12]

    preg = json.loads((V2_ROOT / "data" / "reference" / "preregistered_k.json").read_text())
    assign = pd.read_parquet(dest / "cluster_assignments.parquet")
    sub = assign[
        (assign["method"] == preg["method"])
        & (assign["covariance_type"] == preg["covariance_type"])
        & (assign["k"] == preg["k"])
    ]
    labels = sub.drop_duplicates("patient_id").set_index("patient_id")["cluster"]
    shared = labels.index.intersection(expr.index).intersection(pathway.index)
    labels = labels.loc[shared].astype(int)
    print(f"k={preg['k']} · n={len(shared)}")

    frames = []
    frames.append(mannwhitney_one_vs_rest(pathway.loc[shared], labels.to_numpy(), "pathway"))
    print(f"  pathways {pathway.shape[1]}")

    tf_cols = [c for c in tf.columns if tf.loc[shared, c].notna().any()]
    frames.append(mannwhitney_one_vs_rest(tf.loc[shared, tf_cols], labels.to_numpy(), "tf"))
    print(f"  transcription factors {len(tf_cols)}")

    gene_cols = [c for c in expr.columns if expr.loc[shared, c].std() > 1e-9]
    frames.append(welch_one_vs_rest(expr.loc[shared, gene_cols], labels.to_numpy(), "gene"))
    print(f"  genes {len(gene_cols)}")

    profiles = pd.concat(frames, ignore_index=True)
    counts = per_cluster_significant_pathways(profiles)
    print(f"  rows {len(profiles)} · per-cluster significant pathways {counts}")

    cohort_path = dest / "cohort_payload.json"
    cohort = json.loads(cohort_path.read_text())
    cohort["cluster_profiles"] = profiles.to_dict(orient="records")
    cohort["feature_counts"] = {
        "pathway": int(pathway.shape[1]),
        "tf": len(tf_cols),
        "gene": len(gene_cols),
    }
    cohort_path.write_text(json.dumps(cohort, indent=2))
    profiles.to_parquet(dest / "cluster_profiles.parquet")

    patients = {
        p.stem.replace("payload_", ""): json.loads(p.read_text()) for p in sorted(dest.glob("payload_*.json"))
    }
    copy_payloads_to_app(cohort, patients, V2_ROOT.parent)
    print("payloads copied to the app")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
