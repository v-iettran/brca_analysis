"""TCGA barcode sample-type parsing, matched-normal pairing, epithelium comparison."""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

PROLIF_GENES = ["MKI67", "CCNB1", "AURKA", "E2F1", "E2F2"]


def sample_type_from_barcode(barcode: str) -> str:
    s = str(barcode)
    if len(s) >= 15:
        return s[13:15]
    return ""


def patient_from_barcode(barcode: str) -> str:
    return str(barcode)[:12]


def split_tumour_normal(index) -> tuple[pd.Index, pd.Index]:
    idx = pd.Index(pd.Index(index).astype(str))
    types = idx.map(sample_type_from_barcode)
    # Also accept already-truncated patient IDs tagged via a sidecar.
    normals = idx[types == "11"]
    tumours = idx[types.isin({"01", "03"})]
    return tumours, normals


def matched_pairs(tumour_ids, normal_ids) -> list[tuple[str, str]]:
    t_map = {}
    for tid in tumour_ids:
        t_map.setdefault(patient_from_barcode(tid), str(tid))
    pairs = []
    for nid in normal_ids:
        pid = patient_from_barcode(nid)
        if pid in t_map:
            pairs.append((t_map[pid], str(nid)))
    return pairs


def intrinsic_normal_epithelium(
    expression: pd.DataFrame,
    deconv: pd.DataFrame | None,
    epithelial_cols: tuple[str, ...] = ("Normal_Epithelial", "malignant"),
) -> pd.DataFrame:
    """Prefer the epithelial compartment; fall back to bulk with a flag."""
    if deconv is None or deconv.empty:
        out = expression.copy()
        out.attrs["comparison_type"] = "bulk_fallback"
        return out
    cols = [c for c in epithelial_cols if c in deconv.columns]
    if not cols:
        out = expression.copy()
        out.attrs["comparison_type"] = "bulk_fallback"
        return out
    share = deconv[cols].sum(axis=1).clip(lower=0.05)
    aligned = expression.reindex(deconv.index).div(share, axis=0)
    aligned.attrs["comparison_type"] = "intrinsic_epithelium_vs_normal_epithelium"
    return aligned


def cluster_vs_normal_signatures(
    tumour: pd.DataFrame,
    normal: pd.DataFrame,
    labels: pd.Series,
) -> tuple[pd.DataFrame, dict]:
    """Paired one-sample test where matched, Welch unpaired otherwise."""
    tumour = tumour.copy()
    normal = normal.copy()
    tumour.index = tumour.index.astype(str)
    normal.index = normal.index.astype(str)
    labels = labels.astype(str) if False else labels
    labels = pd.Series(labels, index=tumour.index[: len(labels)] if len(labels) == len(tumour) else tumour.index)
    if not isinstance(labels, pd.Series):
        labels = pd.Series(labels, index=tumour.index)
    labels.index = labels.index.astype(str)
    pairs = matched_pairs(tumour.index, normal.index)
    paired_t = {patient_from_barcode(t) for t, _ in pairs}
    genes = [g for g in tumour.columns if g in normal.columns]
    rows = []
    cluster_means = {}
    normal_mean = normal[genes].mean()
    for lab in sorted(set(pd.Series(labels).dropna().tolist())):
        members = labels[labels == lab].index
        tsub = tumour.reindex(members)[genes]
        sig = tsub.mean() - normal_mean
        cluster_means[int(lab)] = sig
        paired_members = [idx for idx in members if patient_from_barcode(idx) in paired_t]
        unpaired_members = [idx for idx in members if idx not in paired_members]
        for gene in genes:
            paired_delta = []
            for tid, nid in pairs:
                if tid in tsub.index:
                    paired_delta.append(float(tumour.loc[tid, gene] - normal.loc[nid, gene]))
            p_paired = p_unpaired = 1.0
            if len(paired_delta) >= 3:
                p_paired = float(stats.ttest_1samp(paired_delta, 0.0, nan_policy="omit").pvalue)
            u_t = tsub.loc[unpaired_members, gene].to_numpy(float) if unpaired_members else np.array([])
            u_n = normal[gene].to_numpy(float)
            if len(u_t) >= 3 and len(u_n) >= 3:
                p_unpaired = float(stats.ttest_ind(u_t, u_n, equal_var=False, nan_policy="omit").pvalue)
            rows.append({
                "cluster": int(lab),
                "feature": gene,
                "log2fc": float(sig[gene]),
                "p_paired": p_paired,
                "p_unpaired": p_unpaired,
                "n_paired": len(paired_delta),
                "n_unpaired": int(len(u_t)),
            })
    stats_df = pd.DataFrame(rows)
    meta = {
        "n_normal": int(len(normal)),
        "n_paired_patients": len(pairs),
        "comparison_type": tumour.attrs.get("comparison_type") or normal.attrs.get("comparison_type") or "intrinsic_epithelium_vs_normal_epithelium",
        "caveats": [
            "Adjacent normal can show field effects from neighbouring tumour.",
            "TCGA-BRCA adjacent normals are few (on the order of 100).",
            "The paired subset is smaller still.",
        ],
    }
    return stats_df, meta


def proliferation_gate(cluster_sigs: dict[int, pd.Series], genes: list[str] | None = None) -> dict:
    genes = genes or PROLIF_GENES
    means = {}
    ok = True
    for lab, sig in cluster_sigs.items():
        present = [g for g in genes if g in sig.index]
        val = float(sig[present].mean()) if present else 0.0
        means[str(int(lab))] = val
        if val <= 0:
            ok = False
    return {"passed": ok, "per_cluster_mean_logfc": means, "genes": genes}
