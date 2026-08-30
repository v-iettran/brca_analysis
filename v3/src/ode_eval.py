"""NB10 mechanism-split helpers. Out-of-topology drugs get a constant IC50."""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from scanb_features import pathway_for_target

OUT_OF_SCOPE_IC50_NM = 1.0e4


def sigmoid01(x: np.ndarray, lo: float = -3.0, hi: float = 3.0) -> np.ndarray:
    z = np.clip((np.asarray(x, dtype=float) - lo) / (hi - lo), 0.0, 1.0)
    return z


def x0_from_activity(nodes: list[str], pathway: pd.Series | None, tf: pd.Series | None, default: float = 0.5) -> np.ndarray:
    """Map PROGENy/CollecTRI onto the 20 ODE nodes. Missing activity → default."""
    x0 = np.full(len(nodes), default, dtype=float)
    for i, g in enumerate(nodes):
        if tf is not None and g in tf.index and pd.notna(tf[g]):
            x0[i] = float(sigmoid01(np.array([tf[g]]))[0])
            continue
        pw_name = pathway_for_target(g)
        if pathway is not None:
            col = next((c for c in pathway.index if str(c).lower() == pw_name.lower()), None)
            if col is not None and pd.notna(pathway[col]):
                x0[i] = float(sigmoid01(np.array([pathway[col]]))[0])
    return x0


def hold_out_drugs(names: list[str], test_frac: float = 0.3, seed: int = 0) -> tuple[list[str], list[str]]:
    rng = np.random.default_rng(seed)
    uniq = sorted(set(names))
    rng.shuffle(uniq)
    if len(uniq) < 4:
        return uniq, uniq
    n_te = max(1, int(round(len(uniq) * test_frac)))
    return uniq[n_te:], uniq[:n_te]


def spearman_split(df: pd.DataFrame, pred_col: str = "predicted", obs_col: str = "ln_ic50") -> dict:
    """Spearman(pred, -ln_ic50) overall / in-scope / out-scope on held-out rows."""
    out = {}
    for key, sub in {
        "all": df,
        "in": df[df["in_ode_topology"]] if "in_ode_topology" in df.columns else df,
        "out": df[~df["in_ode_topology"]] if "in_ode_topology" in df.columns else df.iloc[0:0],
    }.items():
        if len(sub) < 3 or sub[pred_col].nunique() < 2 or sub[obs_col].nunique() < 2:
            out[f"rho_{key}"] = float("nan")
            out[f"n_{key}"] = int(len(sub))
            continue
        rho = spearmanr(sub[pred_col], -sub[obs_col]).statistic
        out[f"rho_{key}"] = float(rho) if rho == rho else float("nan")
        out[f"n_{key}"] = int(len(sub))
    return out
