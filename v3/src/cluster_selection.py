"""Structure-first cluster selection. Survival must never enter this module."""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Iterable

import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics import adjusted_rand_score, silhouette_score
from sklearn.mixture import GaussianMixture

K_MIN = 2
K_MAX = 8
BIC_WINDOW = 10.0
STABILITY_THRESHOLD = 0.60
PREREGISTERED_METHOD = "gmm"
PREREGISTERED_COVARIANCE = "full"
GMM_COVARIANCES = ("full", "diag", "tied")
METHODS = ("gmm", "kmeans")


def assert_no_survival(frame_or_cols) -> None:
    """Refuse any outcome columns so A1 cannot accidentally peek at survival."""
    banned = {
        "os_months", "os_status", "pfi_months", "pfi_status",
        "os_event", "pfi_event", "time", "event", "survival",
        "overall_survival", "progression",
    }
    if hasattr(frame_or_cols, "columns"):
        names = [str(c).lower() for c in frame_or_cols.columns]
    else:
        names = [str(c).lower() for c in frame_or_cols]
    hits = [n for n in names if n in banned or "survival" in n]
    if hits:
        raise ValueError(f"Survival columns are forbidden during k selection: {hits}")


def config_id(method: str, covariance_type: str | None, k: int) -> str:
    cov = covariance_type if method == "gmm" else "na"
    return f"{method}:{cov}:k={int(k)}"


def parse_config_id(cid: str) -> dict:
    method, cov, kpart = cid.split(":")
    return {"method": method, "covariance_type": None if cov == "na" else cov, "k": int(kpart.split("=")[1])}


def is_preregistered(method: str, covariance_type: str | None, k: int, k_star: int | None) -> bool:
    return (
        method == PREREGISTERED_METHOD
        and covariance_type == PREREGISTERED_COVARIANCE
        and k_star is not None
        and int(k) == int(k_star)
    )


@dataclass
class FitResult:
    method: str
    covariance_type: str | None
    k: int
    labels: np.ndarray
    membership: np.ndarray
    bic: float | None = None
    silhouette: float | None = None
    stability: float | None = None

    @property
    def config_id(self) -> str:
        return config_id(self.method, self.covariance_type, self.k)


def _gmm(Z: np.ndarray, k: int, covariance_type: str, random_state: int, n_init: int) -> GaussianMixture:
    return GaussianMixture(
        n_components=k,
        covariance_type=covariance_type,
        n_init=n_init,
        random_state=random_state,
    ).fit(Z)


def fit_gmm(
    Z: np.ndarray,
    k: int,
    covariance_type: str = "full",
    random_state: int = 0,
    n_init: int = 10,
) -> FitResult:
    Z = np.asarray(Z, dtype=float)
    model = _gmm(Z, k, covariance_type, random_state, n_init)
    labels = model.predict(Z)
    membership = model.predict_proba(Z)
    sil = float(silhouette_score(Z, labels)) if len(set(labels)) > 1 else 0.0
    return FitResult("gmm", covariance_type, k, labels, membership, bic=float(model.bic(Z)), silhouette=sil)


def fit_kmeans(Z: np.ndarray, k: int, random_state: int = 0, n_init: int = 10) -> FitResult:
    Z = np.asarray(Z, dtype=float)
    model = KMeans(n_clusters=k, n_init=n_init, random_state=random_state)
    labels = model.fit_predict(Z)
    membership = np.zeros((len(Z), k), dtype=float)
    membership[np.arange(len(Z)), labels] = 1.0
    sil = float(silhouette_score(Z, labels)) if len(set(labels)) > 1 else 0.0
    return FitResult("kmeans", None, k, labels, membership, silhouette=sil)


def bootstrap_stability(
    Z: np.ndarray,
    k: int,
    base_labels: np.ndarray,
    *,
    n_boot: int = 50,
    frac: float = 0.8,
    random_state: int = 0,
    covariance_type: str = "full",
    n_init: int = 5,
) -> float:
    Z = np.asarray(Z, dtype=float)
    base_labels = np.asarray(base_labels)
    rng = np.random.RandomState(random_state)
    n = len(Z)
    m = max(k + 1, int(frac * n))
    aris: list[float] = []
    for b in range(n_boot):
        idx = rng.choice(n, m, replace=False)
        lab_b = GaussianMixture(
            n_components=k, covariance_type=covariance_type, n_init=n_init, random_state=b
        ).fit_predict(Z[idx])
        aris.append(float(adjusted_rand_score(base_labels[idx], lab_b)))
    return float(np.mean(aris)) if aris else 0.0


def select_k_star(bic: dict[int, float], silhouette: dict[int, float], stability: dict[int, float]) -> int:
    """Best stability among k with BIC within 10 of the minimum. No survival."""
    if not bic:
        raise ValueError("empty BIC table")
    min_bic = min(bic.values())
    candidates = [k for k, val in bic.items() if val <= min_bic + BIC_WINDOW]
    return int(max(candidates, key=lambda k: (stability[k], silhouette.get(k, 0.0), -bic[k])))


def model_selection_table(
    Z: np.ndarray,
    *,
    n_boot: int = 50,
    n_init: int = 10,
    random_state: int = 0,
) -> list[dict]:
    rows = []
    for k in range(K_MIN, K_MAX + 1):
        fit = fit_gmm(Z, k, PREREGISTERED_COVARIANCE, random_state=random_state, n_init=n_init)
        stab = bootstrap_stability(
            Z, k, fit.labels, n_boot=n_boot, random_state=random_state, covariance_type=PREREGISTERED_COVARIANCE
        )
        rows.append({
            "k": k,
            "bic": fit.bic,
            "silhouette": fit.silhouette,
            "stability": stab,
        })
    return rows


def precompute_configurations(
    Z: np.ndarray,
    k_star: int | None,
    *,
    n_init: int = 10,
    random_state: int = 0,
    methods: Iterable[str] = METHODS,
) -> dict[str, FitResult]:
    out: dict[str, FitResult] = {}
    for k in range(K_MIN, K_MAX + 1):
        if "gmm" in methods:
            for cov in GMM_COVARIANCES:
                fit = fit_gmm(Z, k, cov, random_state=random_state, n_init=n_init)
                out[fit.config_id] = fit
        if "kmeans" in methods:
            fit = fit_kmeans(Z, k, random_state=random_state, n_init=n_init)
            out[fit.config_id] = fit
    return out


def freeze_preregistered_k(k_star: int, row: dict, clustering_available: bool) -> dict:
    return {
        "k": int(k_star) if clustering_available else None,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "selection_rule": "stability_within_10_bic",
        "method": PREREGISTERED_METHOD,
        "covariance_type": PREREGISTERED_COVARIANCE,
        "bic": row.get("bic"),
        "silhouette": row.get("silhouette"),
        "stability": row.get("stability"),
        "clustering_available": bool(clustering_available),
        "stability_threshold": STABILITY_THRESHOLD,
    }
