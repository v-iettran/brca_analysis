"""One-vs-rest cluster characterisation and frontend comparison matrix."""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

try:
    from statsmodels.stats.multitest import multipletests
except ImportError:  # pragma: no cover
    def multipletests(pvals, method="fdr_bh"):
        p = np.asarray(pvals, dtype=float)
        n = max(len(p), 1)
        order = np.argsort(p)
        q = np.empty(n)
        prev = 1.0
        ranked = p[order]
        for i in range(n - 1, -1, -1):
            prev = min(prev, ranked[i] * n / (i + 1))
            q[i] = prev
        out = np.empty(n)
        out[order] = np.clip(q, 0, 1)
        return None, out, None, None


def cliffs_delta(x, y) -> float:
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    x = x[np.isfinite(x)]
    y = y[np.isfinite(y)]
    if len(x) == 0 or len(y) == 0:
        return 0.0
    # P(x > y) - P(x < y)
    gt = sum(np.sum(xi > y) for xi in x)
    lt = sum(np.sum(xi < y) for xi in x)
    return float((gt - lt) / (len(x) * len(y)))


def mannwhitney_one_vs_rest(values: pd.DataFrame, labels: np.ndarray, family: str) -> pd.DataFrame:
    labels = np.asarray(labels)
    rows = []
    for feat in values.columns:
        col = pd.to_numeric(values[feat], errors="coerce")
        for lab in sorted(set(labels.tolist())):
            a = col[labels == lab].to_numpy(float)
            b = col[labels != lab].to_numpy(float)
            a = a[np.isfinite(a)]
            b = b[np.isfinite(b)]
            if len(a) < 3 or len(b) < 3:
                p = 1.0
                delta = 0.0
            else:
                try:
                    p = float(stats.mannwhitneyu(a, b, alternative="two-sided").pvalue)
                except ValueError:
                    p = 1.0
                delta = cliffs_delta(a, b)
            rows.append({
                "feature": str(feat),
                "family": family,
                "cluster": int(lab),
                "effect": delta,
                "mean_in": float(np.mean(a)) if len(a) else float("nan"),
                "mean_out": float(np.mean(b)) if len(b) else float("nan"),
                "p": p,
            })
    out = pd.DataFrame(rows)
    if out.empty:
        out["q"] = []
        return out
    _, q, _, _ = multipletests(out["p"].to_numpy(), method="fdr_bh")
    out["q"] = q
    return out


def welch_one_vs_rest(values: pd.DataFrame, labels: np.ndarray, family: str = "gene") -> pd.DataFrame:
    labels = np.asarray(labels)
    rows = []
    for feat in values.columns:
        col = pd.to_numeric(values[feat], errors="coerce")
        for lab in sorted(set(labels.tolist())):
            a = col[labels == lab].to_numpy(float)
            b = col[labels != lab].to_numpy(float)
            a = a[np.isfinite(a)]
            b = b[np.isfinite(b)]
            if len(a) < 3 or len(b) < 3:
                p, lfc = 1.0, 0.0
            else:
                lfc = float(np.mean(a) - np.mean(b))
                try:
                    p = float(stats.ttest_ind(a, b, equal_var=False, nan_policy="omit").pvalue)
                except ValueError:
                    p = 1.0
            rows.append({
                "feature": str(feat),
                "family": family,
                "cluster": int(lab),
                "effect": lfc,
                "log2fc": lfc,
                "p": p,
            })
    out = pd.DataFrame(rows)
    if out.empty:
        out["q"] = []
        return out
    _, q, _, _ = multipletests(out["p"].to_numpy(), method="fdr_bh")
    out["q"] = q
    return out


FAMILY_QUOTAS = {"pathway": 14, "tf": 10, "gene": 30}


def comparison_matrix(
    profiles: pd.DataFrame,
    top_n: int = 30,
    per_family: dict[str, int] | None = FAMILY_QUOTAS,
) -> dict:
    """(features × clusters) of signed effects. Non-significant cells stay in the matrix with q.

    Selection is per family, not global. Ranking all families together lets the
    largest family crowd out the others — genes outnumber pathways 4:1 here, so
    a global top-N returned two of fourteen pathways and made the heatmap's
    pathway band unreadable. Rows are ranked by max |effect| within their own
    group, which is also the order spec v3.1 §1.4 asks the heatmap to show.
    """
    if profiles.empty:
        return {"features": [], "families": [], "clusters": [], "effects": [], "q": []}
    pivot = profiles.pivot_table(index="feature", columns="cluster", values="effect", aggfunc="first")
    qtab = profiles.pivot_table(index="feature", columns="cluster", values="q", aggfunc="first")
    fam = profiles.drop_duplicates("feature").set_index("feature")["family"]
    strength = pivot.abs().max(axis=1).fillna(0.0)
    if per_family:
        keep = []
        for family, quota in per_family.items():
            members = [f for f in pivot.index if str(fam.get(f)) == family]
            keep.extend(strength.loc[members].sort_values(ascending=False).head(quota).index.tolist())
        if not keep:
            keep = list(strength.sort_values(ascending=False).head(top_n).index)
    else:
        var = pivot.var(axis=1).fillna(0.0)
        keep = list(var.sort_values(ascending=False).head(top_n).index)
    pivot = pivot.loc[keep]
    qtab = qtab.reindex(index=keep, columns=pivot.columns)
    clusters = [int(c) for c in pivot.columns]
    return {
        "features": [str(f) for f in pivot.index],
        "families": [str(fam.get(f, "unknown")) for f in pivot.index],
        "clusters": clusters,
        "effects": pivot.fillna(0.0).to_numpy(float).tolist(),
        "q": qtab.fillna(1.0).to_numpy(float).tolist(),
    }


def per_cluster_significant_pathways(profiles: pd.DataFrame, q: float = 0.05) -> dict[int, int]:
    path = profiles[(profiles["family"] == "pathway") & (profiles["q"] < q)]
    counts = path.groupby("cluster").size().to_dict()
    clusters = sorted(set(profiles["cluster"].astype(int)))
    return {int(c): int(counts.get(c, 0)) for c in clusters}


def annotate_clusters(expr: pd.DataFrame, labels: np.ndarray, pam50: pd.Series | None = None) -> dict:
    """ER-high / HER2 / basal-enriched from intrinsic means and optional PAM50 majority."""
    labels = np.asarray(labels)
    out = {}
    esr1 = expr["ESR1"] if "ESR1" in expr.columns else pd.Series(0.0, index=expr.index)
    erbb2 = expr["ERBB2"] if "ERBB2" in expr.columns else pd.Series(0.0, index=expr.index)
    prolif = [g for g in ("MKI67", "CCNB1", "AURKA") if g in expr.columns]
    for lab in sorted(set(labels.tolist())):
        mask = labels == lab
        row = {
            "cluster": int(lab),
            "n": int(mask.sum()),
            "esr1_mean": float(esr1[mask].mean()) if mask.any() else 0.0,
            "erbb2_mean": float(erbb2[mask].mean()) if mask.any() else 0.0,
            "prolif_mean": float(expr.loc[mask, prolif].mean().mean()) if prolif and mask.any() else 0.0,
            "pam50_majority": None,
        }
        if pam50 is not None:
            sub = pam50.reindex(expr.index)[mask].dropna().astype(str)
            if len(sub):
                row["pam50_majority"] = str(sub.value_counts().idxmax())
        out[str(int(lab))] = row
    if out:
        _flag_leader(out, "esr1_mean", "er_high")
        _flag_leader(out, "erbb2_mean", "her2_amplified")
        _flag_leader(out, "prolif_mean", "basal_enriched")
    return out


def _flag_leader(rows: dict, metric: str, flag: str, margin: float = 0.25) -> None:
    """Flag the leading cluster only when it clears the runner-up by `margin`.

    A plain argmax always names a winner, so with a flat or all-zero metric one
    cluster would be labelled ER-high, HER2-amplified, and basal at once.
    """
    values = sorted((row[metric] for row in rows.values()), reverse=True)
    leader = max(rows.values(), key=lambda r: r[metric])
    runner_up = values[1] if len(values) > 1 else float("-inf")
    decisive = len(values) > 1 and (leader[metric] - runner_up) >= margin
    for row in rows.values():
        row[flag] = bool(decisive and row["cluster"] == leader["cluster"])
