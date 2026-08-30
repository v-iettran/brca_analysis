"""PAM50-adjusted one-vs-rest signatures for the Phase 1 ranking checkpoint."""

from __future__ import annotations

import numpy as np
import pandas as pd
from statsmodels.stats.multitest import multipletests


def vectorized_ols_pvalues(X: np.ndarray, Y: np.ndarray, target_idx: int):
    n, p = X.shape
    xtx_inv = np.linalg.pinv(X.T @ X)
    beta = xtx_inv @ X.T @ Y
    resid = Y - X @ beta
    df = max(n - p, 1)
    sigma2 = (resid ** 2).sum(axis=0) / df
    se = np.sqrt(np.clip(sigma2 * xtx_inv[target_idx, target_idx], 0, None))
    coef = beta[target_idx]
    with np.errstate(divide="ignore", invalid="ignore"):
        tstat = np.where(se > 0, coef / se, 0.0)
    from scipy.stats import t as student_t

    pval = 2 * student_t.sf(np.abs(tstat), df)
    return coef, pval


def build_cluster_signature(
    expr: pd.DataFrame,
    clusters: pd.Series,
    pam50: pd.Series,
    cluster_id: int,
) -> pd.DataFrame:
    samples = [s for s in expr.index if s in clusters.index]
    expr = expr.loc[samples].apply(pd.to_numeric, errors="coerce")
    expr = expr.loc[:, expr.isna().mean() < 0.2].fillna(expr.median())
    in_cluster = (clusters.loc[samples] == cluster_id).astype(int)
    pam = pam50.reindex(samples).fillna("Unknown")
    design = pd.concat(
        [
            pd.Series(1, index=samples, name="intercept"),
            in_cluster.rename("in_cluster"),
            pd.get_dummies(pam, prefix="pam50", drop_first=True),
        ],
        axis=1,
    )
    X = design.to_numpy(float)
    Y = expr.to_numpy(float)
    target_idx = list(design.columns).index("in_cluster")
    coef, pval = vectorized_ols_pvalues(X, Y, target_idx)
    fdr = multipletests(pval, method="fdr_bh")[1]
    return pd.DataFrame(
        {"gene": expr.columns, "coef": coef, "pval": pval, "fdr": fdr}
    ).sort_values("coef")


def rank_correlation_by_drug(
    ranks_a: pd.Series,
    ranks_b: pd.Series,
) -> float:
    common = ranks_a.index.intersection(ranks_b.index)
    if len(common) < 5:
        return float("nan")
    from scipy.stats import spearmanr

    return float(spearmanr(ranks_a.loc[common], ranks_b.loc[common]).statistic)
