"""Rank-normalisation, PoE combination, PRECISE, and harmonisation ladder."""

from __future__ import annotations

import numpy as np
from scipy.special import ndtri
from scipy.stats import rankdata
from sklearn.decomposition import PCA


def inverse_normal_transform(X: np.ndarray) -> np.ndarray:
    """Per-sample within-gene-set rank → normal score.

    X: samples × genes. Restrict to the shared gene set *before* calling so
    the rank denominator is comparable across platforms.
    """
    X = np.asarray(X, dtype=float)
    n = X.shape[1]
    if n < 2:
        raise ValueError("Need at least 2 genes for a rank transform")
    R = np.apply_along_axis(rankdata, 1, X)
    return ndtri((R - 0.5) / n)


def cohort_zscore(X: np.ndarray) -> np.ndarray:
    """Per-gene z-score within one cohort (harmonisation option 2)."""
    X = np.asarray(X, dtype=float)
    mu = np.nanmean(X, axis=0, keepdims=True)
    sd = np.nanstd(X, axis=0, keepdims=True)
    sd = np.where(sd == 0, 1.0, sd)
    return (X - mu) / sd


def product_of_experts(
    mus: np.ndarray,
    logvars: np.ndarray,
    mask: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Gaussian product-of-experts with an always-present N(0, I) prior.

    mus, logvars: (n_views, batch, latent_dim)
    mask: (n_views, batch, 1) — 1 if view present, else 0.
    Absent views contribute zero precision, so the joint posterior widens.
    """
    mus = np.asarray(mus, dtype=float)
    logvars = np.asarray(logvars, dtype=float)
    mask = np.asarray(mask, dtype=float)
    precisions = np.exp(-logvars) * mask
    prior_prec = np.ones_like(precisions[0])
    total_prec = precisions.sum(axis=0) + prior_prec
    weighted_mu = (mus * precisions).sum(axis=0)
    mu_joint = weighted_mu / total_prec
    logvar_joint = -np.log(total_prec)
    return mu_joint, logvar_joint


def sample_view_mask(
    rng: np.random.Generator,
    n_views: int,
    batch: int,
) -> np.ndarray:
    """Wu & Goodman sub-sampling: full-view examples plus random masks."""
    full = np.ones((n_views, batch, 1))
    rand = rng.binomial(1, 0.5, size=(n_views, batch, 1)).astype(float)
    none = rand.sum(axis=0, keepdims=True) == 0
    rand = np.where(none, full, rand)
    return np.concatenate([full, rand], axis=1)


def precise(
    X_source: np.ndarray,
    X_target: np.ndarray,
    n_pc: int = 70,
    n_pv: int = 40,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """PRECISE principal-vector alignment (Mourragui et al. 2019)."""
    X_source = np.asarray(X_source, dtype=float)
    X_target = np.asarray(X_target, dtype=float)
    n_pc = int(min(n_pc, X_source.shape[0] - 1, X_target.shape[0] - 1, X_source.shape[1]))
    n_pv = int(min(n_pv, n_pc))
    if n_pc < 1:
        raise ValueError("Not enough samples/features for PRECISE")
    Ps = PCA(n_pc).fit(X_source).components_
    Pt = PCA(n_pc).fit(X_target).components_
    U, s, Vt = np.linalg.svd(Ps @ Pt.T, full_matrices=False)
    pv_source = U.T @ Ps
    pv_target = Vt @ Pt
    angles = np.arccos(np.clip(s, -1.0, 1.0))
    return pv_source[:n_pv], pv_target[:n_pv], angles
