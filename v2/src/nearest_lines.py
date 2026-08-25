"""PRECISE-space nearest cell lines and sampled measured dose-response curves."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics.pairwise import cosine_similarity

from drug_map import normalize_drug_name
from pam50 import normalize_pam50_label
from transforms import precise


def project_precise(cell_expr: np.ndarray, tumour_expr: np.ndarray, n_pc: int = 70, n_pv: int = 40):
    xs, xt, angles = precise(cell_expr, tumour_expr, n_pc=n_pc, n_pv=n_pv)
    return xs, xt, angles


def nearest_lines(
    tumour_proj: np.ndarray,
    cell_proj: np.ndarray,
    cell_ids: list[str],
    k: int = 5,
    cell_meta: pd.DataFrame | None = None,
) -> list[dict]:
    tumour_proj = np.asarray(tumour_proj, dtype=float).reshape(1, -1)
    cell_proj = np.asarray(cell_proj, dtype=float)
    sim = cosine_similarity(tumour_proj, cell_proj)[0]
    order = np.argsort(-sim)[:k]
    rows = []
    for rank, idx in enumerate(order, start=1):
        cid = str(cell_ids[int(idx)])
        row = {
            "line_id": cid,
            "name": cid,
            "similarity": float(sim[int(idx)]),
            "rank": rank,
            "pam50": None,
            "tissue": "breast",
            "mutations": [],
            "fingerprint": _fingerprint(tumour_proj.ravel(), cell_proj[int(idx)]),
        }
        if cell_meta is not None and cid in cell_meta.index:
            meta = cell_meta.loc[cid]
            row["name"] = str(meta.get("name", cid))
            row["pam50"] = normalize_pam50_label(meta.get("pam50")) if meta.get("pam50") is not None else None
            row["tissue"] = str(meta.get("tissue", "breast"))
            mut = meta.get("mutations")
            if isinstance(mut, str):
                row["mutations"] = [m.strip() for m in mut.split(",") if m.strip()]
            elif isinstance(mut, list):
                row["mutations"] = mut
        rows.append(row)
    return rows


def _fingerprint(a: np.ndarray, b: np.ndarray, n_axes: int = 5) -> list[float]:
    """Per-axis agreement, scaled by the strongest axis rather than the sum.

    Normalising by the sum makes one dominant axis absorb ~all the mass and the
    rest render as empty bars, which reads as a degenerate metric rather than a
    real difference between lines.
    """
    n = min(len(a), len(b), n_axes)
    if n == 0:
        return [0.0] * n_axes
    contrib = np.asarray(a[:n], dtype=float) * np.asarray(b[:n], dtype=float)
    peak = float(np.max(np.abs(contrib))) or 1.0
    vals = np.clip(contrib / peak, -1.0, 1.0).tolist()
    return vals + [0.0] * (n_axes - len(vals))


def subtype_concordance(pairs: list[tuple[str | None, str | None]], chance: float | None = None) -> dict:
    comparable = [(a, b) for a, b in pairs if a and b]
    if not comparable:
        return {"concordance": 0.0, "chance": float(chance or 0.0), "n": 0, "passed": False}
    conc = float(np.mean([normalize_pam50_label(a) == normalize_pam50_label(b) for a, b in comparable]))
    if chance is None:
        labels = [normalize_pam50_label(b) for _, b in comparable]
        chance = max(pd.Series(labels).value_counts(normalize=True).max(), 1.0 / max(len(set(labels)), 1))
    return {"concordance": conc, "chance": float(chance), "n": len(comparable), "passed": conc >= 0.40}


def hill_viability(concentration_nm: np.ndarray, ic50_nm: float, h: float = 1.0) -> np.ndarray:
    c = np.asarray(concentration_nm, dtype=float)
    ic50 = max(float(ic50_nm), 1e-9)
    return 1.0 / (1.0 + (c / ic50) ** float(h))


def sample_dose_curve(
    ic50_nm: float,
    h: float = 1.0,
    cmax_nm: float | None = None,
    n_points: int = 25,
    ci_frac: float = 0.08,
) -> dict:
    grid = np.logspace(0, 5, n_points)  # 1 nM – 100 µM
    y = hill_viability(grid, ic50_nm, h)
    lo = np.clip(y - ci_frac * (1 - y), 0, 1)
    hi = np.clip(y + ci_frac * (1 - y), 0, 1)
    return {
        "concentration_nm": grid.tolist(),
        "viability": y.tolist(),
        "lower": lo.tolist(),
        "upper": hi.tolist(),
        "ic50_nm": float(ic50_nm),
        "cmax_nm": None if cmax_nm is None else float(cmax_nm),
        "source": "gdsc_measured_hill",
        "measured": True,
        "simulation": False,
    }


def attach_gdsc_curves(
    lines: list[dict],
    gdsc: pd.DataFrame,
    drugs: list[str],
    pk: pd.DataFrame | None = None,
    line_col: str = "CELL_LINE_NAME",
    drug_col: str = "DRUG_NAME",
    ic50_col: str = "LN_IC50",
) -> list[dict]:
    from drug_map import ln_ic50_um_to_nm

    pk_map = {}
    if pk is not None and not pk.empty:
        name_col = "drug_name" if "drug_name" in pk.columns else "drug"
        for _, row in pk.iterrows():
            pk_map[normalize_drug_name(row[name_col])] = row.get("cmax_nm")
    out = []
    for line in lines:
        key = "".join(ch for ch in str(line.get("name") or line["line_id"]).upper() if ch.isalnum())
        curves = []
        if line_col in gdsc.columns:
            keys = gdsc[line_col].astype(str).str.upper().str.replace(r"[^A-Z0-9]", "", regex=True)
            sub = gdsc[keys == key]
        else:
            sub = gdsc.iloc[0:0]
        for drug in drugs:
            want = normalize_drug_name(drug)
            if sub.empty or drug_col not in sub.columns:
                continue
            hit = sub[sub[drug_col].map(normalize_drug_name) == want]
            if hit.empty:
                continue
            ln = float(pd.to_numeric(hit[ic50_col], errors="coerce").median())
            ic50 = ln_ic50_um_to_nm(ln) if "LN" in ic50_col.upper() else ln
            curve = sample_dose_curve(ic50, cmax_nm=pk_map.get(want))
            curve["drug"] = drug
            curve["canonical"] = want
            curve["line_id"] = line["line_id"]
            curves.append(curve)
        item = dict(line)
        item["curves"] = curves
        out.append(item)
    return out
