"""Kaplan–Meier export and log-rank tests for precomputed cluster configurations."""

from __future__ import annotations

import numpy as np
from scipy import stats

try:
    from statsmodels.stats.multitest import multipletests
except ImportError:  # pragma: no cover
    def multipletests(pvals, method="fdr_bh"):
        p = np.asarray(pvals, dtype=float)
        n = len(p)
        order = np.argsort(p)
        ranked = p[order]
        q = np.empty(n)
        prev = 1.0
        for i in range(n - 1, -1, -1):
            val = ranked[i] * n / (i + 1)
            prev = min(prev, val)
            q[i] = prev
        out = np.empty(n)
        out[order] = np.clip(q, 0, 1)
        return None, out, None, None


def kaplan_meier(times, events) -> dict:
    """KM step function with Greenwood confidence bands and at-risk counts."""
    times = np.asarray(times, dtype=float)
    events = np.asarray(events, dtype=float)
    mask = np.isfinite(times)
    times, events = times[mask], events[mask]
    order = np.argsort(times)
    t = times[order]
    d = events[order]
    n = len(t)
    if n == 0:
        return {"time": [], "survival": [], "lower": [], "upper": [], "at_risk": [], "events": [], "median": None}
    unique = np.unique(t)
    surv = 1.0
    var_sum = 0.0
    out_t, out_s, out_lo, out_hi, out_n, out_d = [], [], [], [], [], []
    for ut in unique:
        at_risk = int(np.sum(t >= ut))
        died = int(np.sum((t == ut) & (d > 0)))
        if at_risk > 0 and died > 0:
            surv *= 1.0 - died / at_risk
            if at_risk > died:
                var_sum += died / (at_risk * (at_risk - died))
        se = surv * np.sqrt(var_sum) if var_sum > 0 else 0.0
        lo = float(max(0.0, surv - 1.96 * se))
        hi = float(min(1.0, surv + 1.96 * se))
        out_t.append(float(ut))
        out_s.append(float(surv))
        out_lo.append(lo)
        out_hi.append(hi)
        out_n.append(at_risk)
        out_d.append(died)
    median = None
    for ti, si in zip(out_t, out_s):
        if si <= 0.5:
            median = float(ti)
            break
    return {
        "time": out_t,
        "survival": out_s,
        "lower": out_lo,
        "upper": out_hi,
        "at_risk": out_n,
        "events": out_d,
        "median": median,
        "n": int(n),
        "n_events": int(events.sum()),
    }


def multivariate_logrank(times, groups, events) -> dict:
    """Mantel–Haenszel multivariate log-rank. Returns statistic, df, p."""
    times = np.asarray(times, dtype=float)
    events = np.asarray(events, dtype=float)
    groups = np.asarray(groups)
    mask = np.isfinite(times) & np.isfinite(events)
    times, events, groups = times[mask], events[mask], groups[mask]
    labels = np.unique(groups)
    k = len(labels)
    if k < 2:
        return {"statistic": 0.0, "df": 0, "p_value": 1.0, "n": int(len(times)), "n_events": int(events.sum())}
    death_times = np.unique(times[events > 0])
    o = np.zeros(k)
    e = np.zeros(k)
    v = np.zeros((k, k))
    for ti in death_times:
        at = groups[times >= ti]
        dmask = (times == ti) & (events > 0)
        died = groups[dmask]
        n_tot = len(at)
        d_tot = len(died)
        if n_tot == 0 or d_tot == 0:
            continue
        n_i = np.array([np.sum(at == lab) for lab in labels], dtype=float)
        d_i = np.array([np.sum(died == lab) for lab in labels], dtype=float)
        o += d_i
        e += n_i * d_tot / n_tot
        frac = n_i / n_tot
        # Greenwood-style covariance for log-rank
        scale = d_tot * (n_tot - d_tot) / (n_tot * n_tot * max(n_tot - 1, 1))
        v += scale * (np.diag(n_i) - np.outer(n_i, n_i) / n_tot)
    stat_vec = o - e
    # drop last group for invertibility
    if k > 1:
        vm = v[:-1, :-1]
        try:
            inv = np.linalg.pinv(vm)
            stat = float(stat_vec[:-1] @ inv @ stat_vec[:-1])
        except np.linalg.LinAlgError:
            stat = 0.0
        df = k - 1
        p = float(stats.chi2.sf(max(stat, 0.0), df))
    else:
        stat, df, p = 0.0, 0, 1.0
    return {"statistic": stat, "df": int(df), "p_value": p, "n": int(len(times)), "n_events": int(events.sum())}


def curves_by_cluster(times, events, labels) -> dict[str, dict]:
    labels = np.asarray(labels)
    out = {}
    for lab in sorted(set(labels.tolist())):
        mask = labels == lab
        km = kaplan_meier(times[mask], events[mask])
        km["cluster"] = int(lab)
        out[str(int(lab))] = km
    return out


def sensitivity_logrank(times, events, assignments_by_k: dict[int, np.ndarray]) -> list[dict]:
    pvals = []
    rows = []
    ks = sorted(assignments_by_k)
    for k in ks:
        res = multivariate_logrank(times, assignments_by_k[k], events)
        pvals.append(res["p_value"])
        rows.append({"k": int(k), "p_value": res["p_value"], "statistic": res["statistic"], "exploratory": True})
    if pvals:
        _, q, _, _ = multipletests(pvals, method="fdr_bh")
        for row, qi in zip(rows, q):
            row["q_value"] = float(qi)
    return rows
