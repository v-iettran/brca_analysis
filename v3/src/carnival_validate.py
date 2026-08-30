"""Post-hoc checks on solved CARNIVAL networks. Does not run the ILP."""

from __future__ import annotations

import json
import re
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr


def activity_map(obj: dict) -> dict[str, float]:
    out: dict[str, float] = {}
    for row in (obj.get("result") or {}).get("nodesAttributes") or []:
        if not isinstance(row, dict):
            continue
        node = row.get("Node") or row.get("node")
        if node in (None, "Perturbation", "INPUT"):
            continue
        try:
            out[str(node)] = float(row.get("AvgAct") or 0)
        except (TypeError, ValueError):
            continue
    return out


def active_set(obj: dict) -> set[str]:
    return {n for n, v in activity_map(obj).items() if v != 0}


def pairwise_jaccard(sets: list[set[str]]) -> np.ndarray:
    vals = []
    for a, b in combinations(sets, 2):
        u = a | b
        vals.append((len(a & b) / len(u)) if u else 1.0)
    return np.array(vals, dtype=float)


def variation_summary(sets: dict[str, set[str]]) -> dict:
    sizes = np.array([len(s) for s in sets.values()], dtype=float)
    js = pairwise_jaccard(list(sets.values())) if len(sets) >= 2 else np.array([np.nan])
    counts: dict[str, int] = {}
    for s in sets.values():
        for n in s:
            counts[n] = counts.get(n, 0) + 1
    n = len(sets)
    j_mean = float(np.nanmean(js))
    return {
        "n_networks": n,
        "size_mean": float(sizes.mean()) if n else 0.0,
        "size_min": int(sizes.min()) if n else 0,
        "size_max": int(sizes.max()) if n else 0,
        "jaccard_mean": j_mean,
        "jaccard_median": float(np.nanmedian(js)),
        "jaccard_min": float(np.nanmin(js)),
        "jaccard_max": float(np.nanmax(js)),
        "frac_jaccard_gt_0.8": float(np.nanmean(js > 0.8)) if n >= 2 else float("nan"),
        "union": int(len(counts)),
        "core_all_lines": int(sum(1 for v in counts.values() if v == n)),
        "singletons": int(sum(1 for v in counts.values() if v == 1)),
        "informative": bool(n >= 2 and j_mean < 0.8),
    }


def parse_targets(raw) -> list[str]:
    if raw is None or (isinstance(raw, float) and np.isnan(raw)):
        return []
    parts = re.split(r"[,;|/]+", str(raw))
    skip = {"none", "nan", ""}
    return [p.strip().upper() for p in parts if p.strip().lower() not in skip]


def essentiality_positives_per_line(
    ge: pd.DataFrame,
    line_ids: list[str],
    pan_frac: float = 0.5,
    thresh: float = -0.5,
) -> dict:
    """Positives per line after dropping pan-essentials (≥ pan_frac of all DepMap)."""
    pan = (ge < thresh).mean(axis=0) >= pan_frac
    sub = ge.loc[ge.index.intersection(line_ids)]
    if sub.empty:
        return {"n_lines": 0, "median": float("nan"), "min": 0, "n_pan": int(pan.sum())}
    pos = (sub.loc[:, ~pan] < thresh).sum(axis=1)
    return {
        "n_lines": int(len(pos)),
        "median": float(pos.median()),
        "min": int(pos.min()),
        "max": int(pos.max()),
        "n_pan": int(pan.sum()),
        "degenerate": bool(pos.min() < 10),
    }


def _map_gdsc_to_ach(gdsc: pd.DataFrame, model: pd.DataFrame, activity_ids: set[str]) -> pd.Series:
    sub = model[model["ModelID"].astype(str).isin(activity_ids)].copy()
    sanger = {
        str(r.SangerModelID): str(r.ModelID)
        for r in sub.itertuples()
        if pd.notna(getattr(r, "SangerModelID", None))
    }
    cosmic: dict[str, str] = {}
    if "COSMICID" in sub.columns:
        for r in sub.itertuples():
            if pd.notna(r.COSMICID):
                cosmic[str(int(r.COSMICID))] = str(r.ModelID)
    strip = {
        re.sub(r"[^A-Z0-9]", "", str(r.StrippedCellLineName).upper()): str(r.ModelID)
        for r in sub.itertuples()
        if pd.notna(getattr(r, "StrippedCellLineName", None))
    }
    ach = pd.Series(np.nan, index=gdsc.index, dtype=object)
    if "SANGER_MODEL_ID" in gdsc.columns:
        ach = gdsc["SANGER_MODEL_ID"].astype(str).map(sanger)
    if "COSMIC_ID" in gdsc.columns:
        miss = ach.isna()
        cid = pd.to_numeric(gdsc.loc[miss, "COSMIC_ID"], errors="coerce")
        mapped = cid.dropna().astype(int).astype(str).map(cosmic)
        ach.loc[mapped.index] = mapped
    if "CELL_LINE_NAME" in gdsc.columns:
        miss = ach.isna()
        key = (
            gdsc.loc[miss, "CELL_LINE_NAME"]
            .astype(str)
            .str.upper()
            .str.replace(r"[^A-Z0-9]", "", regex=True)
        )
        mapped = key.map(strip)
        ach.loc[mapped.index] = mapped
    return ach


def map_gdsc_to_ach(gdsc: pd.DataFrame, model: pd.DataFrame, activity_ids: set[str]) -> pd.Series:
    return _map_gdsc_to_ach(gdsc, model, activity_ids)


def gdsc_target_sensitivity(
    activities: dict[str, dict[str, float]],
    gdsc: pd.DataFrame,
    model: pd.DataFrame,
) -> dict:
    """Spearman of inferred |activity| of a drug's targets vs −LN_IC50 across lines."""
    from drug_map import gdsc_ic50_column

    ic_col = gdsc_ic50_column(gdsc.columns)
    target_col = next((c for c in gdsc.columns if str(c).upper() == "PUTATIVE_TARGET"), None)
    if ic_col is None or target_col is None:
        return {"n_pairs": 0, "rho": float("nan"), "note": "GDSC missing IC50 or PUTATIVE_TARGET"}

    ach = _map_gdsc_to_ach(gdsc, model, set(activities))
    ln = pd.to_numeric(gdsc[ic_col], errors="coerce")
    keep = ach.notna() & ln.notna()
    work = pd.DataFrame({"ach": ach[keep], "ln": ln[keep], "raw_t": gdsc.loc[keep, target_col]})
    if work.empty:
        return {"n_pairs": 0, "rho": float("nan"), "note": "no GDSC rows joined to CARNIVAL lines"}

    scores, n_in = [], []
    for ach_id, raw_t in zip(work["ach"].to_numpy(), work["raw_t"].to_numpy()):
        dact = activities[str(ach_id)]
        vals = [abs(dact[t]) for t in parse_targets(raw_t) if t in dact]
        n_in.append(len(vals))
        scores.append(float(np.mean(vals)) if vals else 0.0)
    work["score"] = scores
    work["n_in_net"] = n_in
    in_net = work[work["n_in_net"] > 0]
    if len(in_net) < 20 or in_net["score"].nunique() < 2:
        return {
            "n_pairs": int(len(in_net)),
            "rho": float("nan"),
            "note": "too few target-in-network pairs",
        }
    rho, p = spearmanr(in_net["score"], -in_net["ln"])
    any_active = in_net["score"] > 0
    return {
        "n_pairs": int(len(in_net)),
        "n_all_scored": int(len(work)),
        "n_lines": int(in_net["ach"].nunique()),
        "rho": float(rho),
        "p": float(p),
        "any_active_frac": float(any_active.mean()),
        "note": "Spearman(|target AvgAct|, -LN_IC50) pairs with target in CARNIVAL graph",
    }


def load_network_dir(net_dir: Path) -> dict[str, dict]:
    out = {}
    for p in Path(net_dir).glob("*.json"):
        obj = json.loads(p.read_text())
        if obj.get("mode") == "fallback_threshold":
            continue
        out[str(obj.get("sample_id") or p.stem)] = obj
    return out
