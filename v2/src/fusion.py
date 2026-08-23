"""Calibrated fusion. v1 Q5 weights are the Bayesian prior / nested special case."""

from __future__ import annotations

import numpy as np

V1_SINGLE_WEIGHTS = {
    "sensitivity": 0.60,
    "q2_reliability": 0.25,
    "q4_support": 0.15,
}

V1_COMBINATION_WEIGHTS = {
    "components": 0.55,
    "almanac": 0.35,
    "q4": 0.10,
}


def v1_nested_score(sensitivity, q2_reliability, q4_support) -> float:
    """Q5 special case: declared weights, not a fitted model."""
    w = V1_SINGLE_WEIGHTS
    return (
        w["sensitivity"] * float(sensitivity)
        + w["q2_reliability"] * float(q2_reliability)
        + w["q4_support"] * float(q4_support)
    )


def empirical_coverage(y_true, lower, upper) -> float:
    y_true = np.asarray(y_true)
    lower = np.asarray(lower)
    upper = np.asarray(upper)
    return float(((y_true >= lower) & (y_true <= upper)).mean())


def kaplan_meier_survival(times, events):
    """Right-censoring survival G(t) = P(C > t). `events` is 1 if the *censoring* time is observed."""
    times = np.asarray(times, dtype=float)
    events = np.asarray(events, dtype=float)
    order = np.argsort(times)
    t = times[order]
    d = events[order]
    n = len(t)
    at_risk = np.arange(n, 0, -1, dtype=float)
    surv = np.ones(n, dtype=float)
    prod = 1.0
    for i in range(n):
        if d[i] > 0 and at_risk[i] > 0:
            prod *= 1.0 - d[i] / at_risk[i]
        surv[i] = prod
    return t, surv


def ipcw_weights(time, event, clip: float = 20.0) -> np.ndarray:
    """Inverse-probability-of-censoring weights. Censored rows get weight 0.

    `event` is 1 if the death/failure is observed. Censoring distribution is
    estimated by KM on the complementary indicator.
    """
    time = np.asarray(time, dtype=float)
    event = np.asarray(event, dtype=float)
    censored = (1.0 - event).astype(float)
    t_g, g = kaplan_meier_survival(time, censored)
    # G(T_i -): survival just before T_i
    g_at = np.interp(time, t_g, g, left=1.0, right=max(g[-1], 1e-6) if len(g) else 1e-6)
    g_at = np.clip(g_at, 1e-3, 1.0)
    w = np.where(event > 0, 1.0 / g_at, 0.0)
    return np.clip(w, 0.0, clip)


def observed_event_mask(event) -> np.ndarray:
    """True where the failure time is observed. Censored times must not be used as y."""
    return np.asarray(event, dtype=float) > 0


def posterior_shift(prior: dict, fitted: dict) -> dict:
    """How far the data moved the v1 stream weights."""
    keys = list(prior)
    return {k: float(fitted.get(k, 0.0) - prior[k]) for k in keys}
