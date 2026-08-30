#!/usr/bin/env python3
"""Recompute PROGENy/CollecTRI on full-n intrinsic and re-log NB06 + A3. Does not retune k."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import certifi

os.environ.setdefault("SSL_CERT_FILE", certifi.where())
os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())

V2_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V2_ROOT / "src"))

import decoupler as dc  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.metrics import roc_auc_score  # noqa: E402

from cluster_stats import mannwhitney_one_vs_rest, per_cluster_significant_pathways, welch_one_vs_rest  # noqa: E402
from gate import gate  # noqa: E402
from io_data import encode_er_status  # noqa: E402
from v3_payload import copy_payloads_to_app, v3_interim  # noqa: E402


def _score(mat: pd.DataFrame, net, method: str) -> pd.DataFrame:
    X = mat.select_dtypes(include=[np.number]).fillna(0)
    X.columns = X.columns.astype(str).str.upper()
    X.index = X.index.astype(str).str[:12]
    fn = dc.mt.mlm if method == "mlm" else dc.mt.ulm
    res = fn(X, net)
    out = pd.DataFrame(res[0] if isinstance(res, tuple) else res)
    if list(out.index) != list(X.index) and list(out.columns) == list(X.index):
        out = out.T
    out.index = X.index
    return out.replace([np.inf, -np.inf], np.nan)


def main() -> int:
    interim = V2_ROOT / "data" / "interim"
    expr = pd.read_parquet(interim / "intrinsic_expression.parquet")
    expr.index = expr.index.astype(str).str[:12]
    expr = expr[~expr.index.duplicated(keep="first")]
    ids = list(expr.index)
    if len(expr) < 800:
        print(f"STOP: intrinsic n={len(expr)} is not full scale")
        return 2

    net = dc.op.progeny(organism="human", top=500)
    tf_net = dc.op.collectri(organism="human")
    pathway = _score(expr, net, "mlm")
    tf = _score(expr, tf_net, "ulm")
    pathway.to_parquet(interim / "pathway_activity.parquet")
    tf.to_parquet(interim / "tf_activity.parquet")
    rel = pd.DataFrame({"tf": list(tf.columns), "reliability": tf.notna().mean().to_numpy()})
    rel.to_parquet(interim / "tf_reliability.parquet")
    print("pathways", pathway.shape, "tfs", tf.shape, "sources", sorted(pathway.columns.astype(str)))

    clin_p = next((V2_ROOT / "data" / "raw" / "tcga_brca").rglob("*clinical_patient.txt"))
    tcga_clin = pd.read_csv(clin_p, sep="\t", comment="#")
    tci = tcga_clin.set_index("PATIENT_ID")
    tci.index = tci.index.astype(str).str[:12]
    sub = tci["SUBTYPE"].astype(str)
    y = pd.Series(np.nan, index=sub.index)
    y[sub.str.contains("LumA|LumB", case=False, na=False)] = 1.0
    y[sub.str.contains("Basal", case=False, na=False)] = 0.0
    est = next(c for c in pathway.columns if str(c).lower() == "estrogen")
    common = pathway.index.intersection(y.dropna().index)
    yy = y.loc[common]
    s = pathway.loc[common, est]
    auroc = float(roc_auc_score(yy, s))
    mb_note = ""
    mb_expr = next((V2_ROOT / "data" / "raw" / "metabric").rglob("data_mrna_illumina_microarray.txt"), None)
    mb_clin_p = next((V2_ROOT / "data" / "raw" / "metabric").rglob("*clinical_patient.txt"), None)
    if mb_expr is not None and mb_clin_p is not None:
        from deconv import read_cbioportal_matrix

        mb_bulk = read_cbioportal_matrix(mb_expr)
        mb_clin = pd.read_csv(mb_clin_p, sep="\t", comment="#").set_index("PATIENT_ID")
        mb_clin.index = mb_clin.index.astype(str)
        if "ER_IHC" in mb_clin.columns:
            y_mb = encode_er_status(mb_clin["ER_IHC"])
            pw_mb = _score(mb_bulk, net, "mlm")
            cmb = pw_mb.index.intersection(y_mb.dropna().index)
            bulk_auroc = float(roc_auc_score(y_mb.loc[cmb], pw_mb.loc[cmb, est]))
            mb_note = f" | METABRIC_bulk_IHC AUROC={bulk_auroc:.3f} n={len(cmb)} (PROGENy)"
    note = (
        f"n={len(common)} source=intrinsic_tcga er_col=SUBTYPE_Lum_vs_Basal "
        f"mean_Estrogen ER+={float(s[yy == 1].mean()):.3f} ER-={float(s[yy == 0].mean()):.3f} "
        f"method=PROGENy_mlm{mb_note}"
    )
    gate(
        "NB06",
        "estrogen_er_positive_control",
        auroc,
        0.70,
        n=len(common),
        min_n=20,
        smoke_test=False,
        sample_ids=ids,
        note=note,
    )

    dest = v3_interim(V2_ROOT)
    assign = pd.read_parquet(dest / "cluster_assignments.parquet")
    k = json.loads((V2_ROOT / "data" / "reference" / "preregistered_k.json").read_text())["k"]
    sub = assign[(assign["method"] == "gmm") & (assign["covariance_type"] == "full") & (assign["k"] == k)]
    labels = sub.drop_duplicates("patient_id").set_index("patient_id")["cluster"]
    shared = labels.index.intersection(pathway.index)
    path_prof = mannwhitney_one_vs_rest(pathway.loc[shared], labels.loc[shared].to_numpy(), "pathway")
    top = tf.loc[shared].var().sort_values(ascending=False).head(40).index
    tf_prof = mannwhitney_one_vs_rest(tf.loc[shared, top], labels.loc[shared].to_numpy(), "tf")
    top_genes = expr.var().sort_values(ascending=False).head(60).index
    gene_prof = welch_one_vs_rest(expr.loc[shared, top_genes], labels.loc[shared].to_numpy(), "gene")
    profiles = pd.concat([path_prof, tf_prof, gene_prof], ignore_index=True)
    counts = per_cluster_significant_pathways(profiles)
    min_sig = min(counts.values()) if counts else 0
    print("A3 pathway counts", counts, "min", min_sig)

    cohort_p = dest / "cohort_payload.json"
    cohort = json.loads(cohort_p.read_text())
    cohort["gates"]["a3"] = {
        "passed": bool(counts) and min_sig >= 3,
        "per_cluster_pathway_counts": {str(k_): int(v) for k_, v in counts.items()},
    }
    cohort["cluster_profiles"] = profiles.to_dict(orient="records")
    cohort_p.write_text(json.dumps(cohort, indent=2))
    patients = {
        p.stem.replace("payload_", ""): json.loads(p.read_text())
        for p in dest.glob("payload_*.json")
    }
    copy_payloads_to_app(cohort, patients, V2_ROOT.parent)
    profiles.to_parquet(dest / "cluster_profiles.parquet")

    gate(
        "NB_A3",
        "cluster_differential_pathways",
        float(min_sig),
        3,
        cohort=True,
        sample_ids=ids,
        n=len(ids),
        note=f"per-cluster significant pathway counts: {counts} method=PROGENy_mlm k={k}",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
