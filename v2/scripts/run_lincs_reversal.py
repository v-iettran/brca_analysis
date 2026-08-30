#!/usr/bin/env python3
"""Score A5.1 signature reversal against the real LINCS breast trt_cp matrix.

Does not retune k, does not touch any other gate. The cluster labels are read
back from the frozen preregistered k; this script only asks which compounds
reverse each cluster's distance from normal breast epithelium.

The compact artifact is the derived output of `build_compact_gctx_artifact.py`;
the 33 GB raw GCTX it was built from is not needed at runtime.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

V2_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V2_ROOT / "src"))

import pandas as pd  # noqa: E402

from cluster_stats import annotate_clusters  # noqa: E402
from gate import gate  # noqa: E402
from gctx_retrieval import (  # noqa: E402
    known_drug_positive_control,
    load_breast_compact,
    query_signature,
    rank_reversal_by_signature,
)
from v3_payload import copy_payloads_to_app, v3_interim  # noqa: E402
from v3_real import normal_reference, _cluster_signatures  # noqa: E402

COMPACT_DIR = V2_ROOT.parent / "outputs" / "copilot_artifacts" / "compact_gctx"
N_SIDE = 150
TOP_N = 50


def main() -> int:
    interim = V2_ROOT / "data" / "interim"
    dest = v3_interim(V2_ROOT)

    expr = pd.read_parquet(interim / "intrinsic_expression.parquet")
    expr.index = expr.index.astype(str).str[:12]
    expr = expr[~expr.index.duplicated(keep="first")]
    ids = list(expr.index)
    if len(expr) < 800:
        print(f"STOP: intrinsic n={len(expr)} is not full scale")
        return 2

    preg = json.loads((V2_ROOT / "data" / "reference" / "preregistered_k.json").read_text())
    k = preg["k"]
    assign = pd.read_parquet(dest / "cluster_assignments.parquet")
    sub = assign[
        (assign["method"] == preg["method"])
        & (assign["covariance_type"] == preg["covariance_type"])
        & (assign["k"] == k)
    ]
    labels = sub.drop_duplicates("patient_id").set_index("patient_id")["cluster"]
    labels = labels.reindex(ids).dropna().astype(int)
    print(f"frozen k={k} ({preg['method']}/{preg['covariance_type']}) labels n={len(labels)}")

    annotations = annotate_clusters(expr.loc[labels.index], labels.to_numpy())
    roles = {
        int(c): ("er_high" if r.get("er_high") else "her2_amplified" if r.get("her2_amplified") else None)
        for c, r in annotations.items()
    }
    print("cluster roles:", roles)

    print("recomputing cluster-vs-normal signatures at the frozen k ...")
    stats_df, a4_meta = normal_reference(V2_ROOT, list(labels.index), labels.to_numpy())
    if stats_df is None:
        print(f"STOP: normal reference unavailable — {a4_meta.get('reason')}")
        return 3
    sigs = _cluster_signatures(stats_df)
    stats_df.to_parquet(dest / "cluster_vs_normal_signature.parquet")
    print(f"signatures for clusters {sorted(sigs)} · n_normal={a4_meta.get('n_normal')}")

    queries = {c: query_signature(s, N_SIDE) for c, s in sigs.items()}
    gene_union = sorted({g for q in queries.values() for g in q.index})
    print(f"query signature genes (union): {len(gene_union)}")

    mat, meta, source = load_breast_compact(COMPACT_DIR, gene_union)
    if mat.empty:
        print(f"STOP: compact matrix unusable at {COMPACT_DIR} (source={source})")
        return 4
    print(f"perturbation matrix {mat.shape} source={source} · {meta['drug'].nunique()} compounds")

    by_cluster: dict[str, dict] = {}
    positive = {
        "passed": False,
        "hits": [],
        "role": "unavailable",
        "note": "No cluster carried a positive-control role, so the control could not be evaluated.",
    }
    for cluster in sorted(queries):
        ranked = rank_reversal_by_signature(queries[cluster], mat, meta, source=source, top_n=TOP_N)
        members = [
            {
                "drug": str(r["drug"]),
                "canonical": str(r["canonical"]),
                "reversal_score": float(r["reversal_score"]),
                "n_signatures": int(r["n_signatures"]),
                "rank": int(r["rank"]),
                "source": source,
                "validated": False,
            }
            for _, r in ranked.iterrows()
        ]
        by_cluster[str(cluster)] = {
            "members": members,
            "validated": False,
            "threshold_rule": "connectivity_reversal_top_n",
            "order_carries_no_meaning": True,
            "source": source,
        }
        role = roles.get(cluster)
        top = ", ".join(m["canonical"] for m in members[:5])
        print(f"  cluster {cluster} (role={role}): {len(members)} candidates · top: {top}")
        if role:
            control = known_drug_positive_control(ranked, role)
            control["cluster"] = int(cluster)
            print(f"    positive control {role}: hits={control['hits']} passed={control['passed']}")
            if positive["role"] == "unavailable" or control["passed"]:
                positive = control

    ranked_all = pd.DataFrame(
        [{"cluster": int(c), **m} for c, blk in by_cluster.items() for m in blk["members"]]
    )
    ranked_all.to_parquet(dest / "reversal_candidates.parquet")

    cohort_p = dest / "cohort_payload.json"
    cohort = json.loads(cohort_p.read_text())
    a5 = cohort.setdefault("gates", {}).setdefault("a5", {})
    a5["known_drug_positive_control"] = positive
    a5["source"] = source
    cohort["reversal_by_cluster"] = by_cluster
    cohort.setdefault("provenance", {})["reversal"] = source
    cohort_p.write_text(json.dumps(cohort, indent=2))

    patients = {}
    for path in dest.glob("payload_*.json"):
        payload = json.loads(path.read_text())
        cl = str((payload.get("position") or {}).get("cluster", {}).get("label"))
        abstained = payload.get("state") == 3 or (payload.get("abstention") or {}).get("abstained")
        payload["reversal_candidates"] = None if abstained else by_cluster.get(cl)
        path.write_text(json.dumps(payload, indent=2))
        patients[payload["patient_id"]] = payload
    copy_payloads_to_app(cohort, patients, V2_ROOT.parent)

    gate(
        "NB_A5",
        "known_drug_positive_control",
        float(len(positive.get("hits") or [])),
        1,
        cohort=True,
        sample_ids=ids,
        n=len(ids),
        note=(
            f"{positive.get('role')} cluster hits: {positive.get('hits')} "
            f"source={source} n_compounds={meta['drug'].nunique()} "
            f"query={N_SIDE}up/{N_SIDE}down agg=median_over_signatures"
        ),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
