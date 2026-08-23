"""Vectorized one-vs-rest differential expression, used both to regenerate
per-fold cluster signatures during cross-validation and to sanity-check the
committed ``cluster_{i}_signature.csv`` artifacts.

This mirrors ``vectorized_ols_pvalues`` in
``final-project/brca_target_pipeline.py`` (a per-gene OLS t-test of cluster
membership vs. expression) but is reimplemented with plain numpy so
``pipeline_core`` has no dependency on the sibling ``final-project`` scripts.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.stats.multitest import multipletests


def one_vs_rest_signature(
    expr: pd.DataFrame, labels: pd.Series, cluster_id: int
) -> pd.DataFrame:
    """Per-gene Welch t-test of ``cluster_id`` vs. all other samples.

    Parameters
    ----------
    expr: genes (rows) x samples (cols), already aligned to ``labels.index``.
    labels: sample -> cluster id.
    """
    samples = [s for s in expr.columns if s in labels.index]
    expr = expr[samples]
    is_in = labels.loc[samples].to_numpy() == cluster_id

    values = expr.to_numpy(dtype=float)
    in_group = values[:, is_in]
    out_group = values[:, ~is_in]

    n_in, n_out = in_group.shape[1], out_group.shape[1]
    mean_in = np.nanmean(in_group, axis=1)
    mean_out = np.nanmean(out_group, axis=1)
    var_in = np.nanvar(in_group, axis=1, ddof=1)
    var_out = np.nanvar(out_group, axis=1, ddof=1)

    se = np.sqrt(var_in / max(n_in, 1) + var_out / max(n_out, 1))
    se[se == 0] = np.nan
    t_stat = (mean_in - mean_out) / se

    # Welch-Satterthwaite degrees of freedom, vectorized.
    with np.errstate(invalid="ignore", divide="ignore"):
        df_num = (var_in / n_in + var_out / n_out) ** 2
        df_den = (var_in**2) / ((n_in**2) * max(n_in - 1, 1)) + (var_out**2) / (
            (n_out**2) * max(n_out - 1, 1)
        )
        dof = df_num / df_den
    dof = np.where(np.isfinite(dof) & (dof > 0), dof, n_in + n_out - 2)

    pvals = 2 * stats.t.sf(np.abs(t_stat), dof)
    pvals = np.where(np.isfinite(pvals), pvals, 1.0)

    finite_mask = np.isfinite(t_stat)
    fdr = np.full(len(pvals), np.nan)
    if finite_mask.any():
        fdr[finite_mask] = multipletests(pvals[finite_mask], method="fdr_bh")[1]

    coef = mean_in - mean_out
    return pd.DataFrame(
        {"gene": expr.index, "coef": coef, "pval": pvals, "fdr": fdr}
    ).set_index("gene")
