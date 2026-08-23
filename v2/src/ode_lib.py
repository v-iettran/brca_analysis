"""20-node HillCube logic-ODE primitives (Wittmann et al. 2009)."""

from __future__ import annotations

from collections.abc import Callable, Sequence

import numpy as np


def hill(x: np.ndarray | float, k: np.ndarray | float, n: float = 2.0) -> np.ndarray:
    """Normalised Hill: hill(0)=0, hill(1)=1, monotone increasing."""
    x = np.asarray(x, dtype=float)
    k = np.asarray(k, dtype=float)
    xn = np.power(np.clip(x, 0.0, None), n)
    kn = np.power(np.clip(k, 1e-12, None), n)
    return (xn * (1.0 + kn)) / (xn + kn)


def boolean_interpolate(
    x: np.ndarray,
    topology: dict,
    k: np.ndarray,
    n: float = 2.0,
) -> np.ndarray:
    """HillCube interpolation of signed incoming edges.

    topology["nodes"] is a list of gene names.
    topology["edges"] is a list of {source, target, sign} with sign in {+1, -1}.
    k is a vector aligned with edges (one sensitivity per edge).
    Activators combine as noisy-OR; inhibitors as noisy-OR of repression.
    """
    nodes: list[str] = list(topology["nodes"])
    index = {name: i for i, name in enumerate(nodes)}
    n_nodes = len(nodes)
    B = np.zeros(n_nodes, dtype=float)
    incoming: list[list[tuple[int, int, float]]] = [[] for _ in range(n_nodes)]
    for e, edge in enumerate(topology["edges"]):
        src = index[edge["source"]]
        tgt = index[edge["target"]]
        sign = int(edge["sign"])
        incoming[tgt].append((src, sign, float(k[e])))

    for i in range(n_nodes):
        acts = [hill(x[src], ki, n) for src, sign, ki in incoming[i] if sign > 0]
        inhs = [hill(x[src], ki, n) for src, sign, ki in incoming[i] if sign < 0]
        if acts:
            prod = 1.0
            for a in acts:
                prod *= 1.0 - float(a)
            activation = 1.0 - prod
        else:
            activation = float(x[i])
        if inhs:
            prod = 1.0
            for h in inhs:
                prod *= 1.0 - float(h)
            inhibition = 1.0 - prod
        else:
            inhibition = 0.0
        B[i] = np.clip(activation * (1.0 - inhibition), 0.0, 1.0)
    return B


def make_rhs(topology: dict, params: dict) -> Callable:
    """dx/dt = tau * (B(x) * drug_mult - x)."""

    def rhs(t, x, args):
        drug_mult = np.asarray(args["drug_mult"], dtype=float)
        k = np.asarray(params["k"], dtype=float)
        tau = np.asarray(params["tau"], dtype=float)
        n = float(params.get("n", 2.0))
        B = boolean_interpolate(x, topology, k, n=n)
        return tau * (B * drug_mult - x)

    return rhs


def drug_multiplier(
    target_idx: int | Sequence[int],
    conc: float,
    ic50: float,
    h: float = 1.0,
    n_nodes: int = 20,
) -> np.ndarray:
    """Hill inhibition at the target node(s). Values stay in (0, 1]."""
    m = np.ones(n_nodes, dtype=float)
    factor = 1.0 / (1.0 + (float(conc) / float(ic50)) ** h)
    if isinstance(target_idx, (list, tuple, np.ndarray)):
        for i in target_idx:
            m[int(i)] = factor
    else:
        m[int(target_idx)] = factor
    return m


def bliss_excess_from_effects(e_a: float, e_b: float, e_ab: float) -> float:
    """Bliss excess: observed combination effect minus independence."""
    return float(e_ab) - (float(e_a) + float(e_b) - float(e_a) * float(e_b))


def simulate_euler(
    rhs: Callable,
    x0: np.ndarray,
    drug_mult: np.ndarray,
    t_end: float = 72.0,
    dt: float = 0.5,
) -> np.ndarray:
    """Simple Euler integrator (CPU fallback when diffrax is unavailable)."""
    x = np.asarray(x0, dtype=float).copy()
    n_steps = int(np.ceil(t_end / dt))
    args = {"drug_mult": drug_mult}
    t = 0.0
    for _ in range(n_steps):
        x = np.clip(x + dt * rhs(t, x, args), 0.0, 1.0)
        t += dt
    return x


def simulate_trajectory(
    rhs: Callable,
    x0: np.ndarray,
    drug_mult: np.ndarray,
    t_span: tuple[float, float] = (0.0, 168.0),
    dt: float = 1.0,
) -> np.ndarray:
    """Return nodes × time trajectory."""
    x = np.asarray(x0, dtype=float).copy()
    times = np.arange(t_span[0], t_span[1] + dt, dt)
    traj = np.zeros((x0.shape[0], times.size), dtype=float)
    args = {"drug_mult": drug_mult}
    traj[:, 0] = x
    for i in range(1, times.size):
        x = np.clip(x + dt * rhs(times[i - 1], x, args), 0.0, 1.0)
        traj[:, i] = x
    return traj


def detect_rebound(
    traj: np.ndarray,
    nodes: Sequence[str],
    min_from_trough: float = 1.5,
    vs_baseline: float = 1.2,
) -> list[str]:
    """Nodes that dip then recover: spec NB11 resistance output."""
    rebound = []
    for i, name in enumerate(nodes):
        series = traj[i]
        trough = float(series.min())
        end = float(series[-1])
        start = float(series[0])
        if trough <= 0:
            continue
        if end > trough * min_from_trough and end > start * vs_baseline:
            rebound.append(str(name))
    return rebound


def identifiability_sensitivity_rank(
    topology: dict,
    params: dict,
    x0: np.ndarray,
    eps: float = 1e-4,
) -> dict:
    """Finite-difference sensitivity rank fallback if Julia is unavailable.

    Parameters whose columns are near-collinear or near-zero are reported
    as non-identifiable so they can be fixed to priors (spec NB09).
    """
    rhs = make_rhs(topology, params)
    n_nodes = len(topology["nodes"])
    drug_mult = np.ones(n_nodes)
    y0 = simulate_trajectory(rhs, x0, drug_mult, t_span=(0.0, 24.0), dt=4.0).ravel()
    k = np.asarray(params["k"], dtype=float).copy()
    tau = np.asarray(params["tau"], dtype=float).copy()
    names = [f"k[{i}]" for i in range(k.size)] + [f"tau[{i}]" for i in range(tau.size)]
    cols = []
    theta = np.concatenate([k, tau])
    for j in range(theta.size):
        pert = theta.copy()
        pert[j] += eps
        k_p, tau_p = pert[: k.size], pert[k.size :]
        rhs_p = make_rhs(topology, {"k": k_p, "tau": tau_p, "n": params.get("n", 2.0)})
        y_p = simulate_trajectory(rhs_p, x0, drug_mult, t_span=(0.0, 24.0), dt=4.0).ravel()
        cols.append((y_p - y0) / eps)
    S = np.stack(cols, axis=1)
    col_norm = np.linalg.norm(S, axis=0)
    nonident = [names[i] for i, nrm in enumerate(col_norm) if nrm < 1e-8]
    rank = int(np.linalg.matrix_rank(S, tol=1e-6))
    return {
        "n_params": int(theta.size),
        "rank": rank,
        "nonidentifiable": nonident,
        "col_norm": col_norm.tolist(),
        "method": "finite_difference_sensitivity",
    }
