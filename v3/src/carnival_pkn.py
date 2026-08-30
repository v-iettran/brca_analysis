"""Signed OmniPath PPI subgraph for InvCARNIVAL.

AllInteractions TF→target dumps are the wrong graph: TFs sit as sources,
signs collapse to inhibition, and the component is often fully cyclic.
InvCARNIVAL then fails when it tries to add a Perturbation node onto an
empty parent list ("replacement has 1 row, data has 0").

Use OmniPath signalling PPI, keep a 2-layer neighbourhood of ODE nodes and
measured TFs, and guarantee at least one source-only node.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from topology import DEFAULT_EDGES

CARNIVAL_COLS = ["source", "interaction", "target"]
INPUT_NODE = "INPUT"


def _as_bool(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series.fillna(False)
    return series.fillna(0).astype(int).astype(bool)


def signed_interactions(raw: pd.DataFrame) -> pd.DataFrame:
    """Consensus-direction edges that are exclusively stimulatory or inhibitory."""
    raw = raw.reset_index(drop=True)
    stim = _as_bool(raw["is_stimulation"]) if "is_stimulation" in raw.columns else pd.Series(True, index=raw.index)
    inh = _as_bool(raw["is_inhibition"]) if "is_inhibition" in raw.columns else ~stim
    if "consensus_direction" in raw.columns:
        cons = _as_bool(raw["consensus_direction"])
    else:
        cons = pd.Series(True, index=raw.index)
    keep = cons.to_numpy() & (stim.to_numpy() != inh.to_numpy())
    src_col = "source_genesymbol" if "source_genesymbol" in raw.columns else "source"
    tgt_col = "target_genesymbol" if "target_genesymbol" in raw.columns else "target"
    nref = raw["n_references"] if "n_references" in raw.columns else pd.Series(1, index=raw.index)
    out = pd.DataFrame({
        "source": raw.loc[keep, src_col].astype(str).to_numpy(),
        "interaction": np.where(stim.to_numpy()[keep], 1, -1).astype(int),
        "target": raw.loc[keep, tgt_col].astype(str).to_numpy(),
        "n_references": pd.to_numeric(nref.loc[keep], errors="coerce").fillna(1).to_numpy(),
    })
    out = out.replace({"source": {"nan": np.nan, "": np.nan}, "target": {"nan": np.nan, "": np.nan}})
    out = out.dropna(subset=["source", "target"])
    out = out[out["source"] != out["target"]]
    return out.drop_duplicates(subset=CARNIVAL_COLS)


def literature_edges() -> pd.DataFrame:
    return pd.DataFrame(
        [{"source": s, "interaction": int(sign), "target": t, "n_references": 10}
         for s, t, sign in DEFAULT_EDGES]
    )


def source_only_nodes(pkn: pd.DataFrame) -> set[str]:
    src = set(pkn["source"].astype(str))
    tgt = set(pkn["target"].astype(str))
    return src - tgt


def ensure_source_only_nodes(pkn: pd.DataFrame, seeds: set[str]) -> pd.DataFrame:
    """InvCARNIVAL requires at least one parent-only node to attach Perturbation."""
    if source_only_nodes(pkn):
        return pkn
    seeds = {str(s) for s in seeds if str(s) in set(pkn["source"].astype(str)) | set(pkn["target"].astype(str))}
    if not seeds:
        seeds = set(pkn["source"].astype(str))
        seeds = set(list(seeds)[: min(8, len(seeds))])
    extra = pd.DataFrame({
        "source": [INPUT_NODE] * len(seeds),
        "interaction": [1] * len(seeds),
        "target": list(seeds),
        "n_references": [1] * len(seeds),
    })
    return pd.concat([pkn, extra], ignore_index=True)


def carnival_frame(pkn: pd.DataFrame) -> pd.DataFrame:
    out = pkn[CARNIVAL_COLS].copy()
    out["source"] = out["source"].astype(str)
    out["target"] = out["target"].astype(str)
    out["interaction"] = out["interaction"].astype(int)
    return out.drop_duplicates()


def two_layer_subgraph(
    pkn: pd.DataFrame,
    core: set[str],
    max_edges: int = 5000,
) -> pd.DataFrame:
    core = {str(x) for x in core}
    incoming = pkn[pkn["target"].astype(str).isin(core)]
    nodes = core | set(incoming["source"].astype(str))
    sub = pkn[pkn["source"].astype(str).isin(nodes) & pkn["target"].astype(str).isin(nodes)].copy()
    if "n_references" not in sub.columns:
        sub["n_references"] = 1
    ode_like = sub[sub["source"].astype(str).isin(core) & sub["target"].astype(str).isin(core)]
    rest = sub.drop(index=ode_like.index, errors="ignore").sort_values("n_references", ascending=False)
    kept = pd.concat([ode_like, rest], ignore_index=True).drop_duplicates(subset=CARNIVAL_COLS)
    if len(kept) > max_edges:
        kept = kept.head(max_edges)
    return kept


def build_carnival_pkn(
    tf_names: list[str],
    ode_nodes: list[str],
    raw: pd.DataFrame | None = None,
    max_edges: int = 5000,
) -> tuple[pd.DataFrame, dict]:
    """Return a 3-column CARNIVAL PKN and a small diagnostic dict."""
    tfs = {str(x) for x in tf_names}
    ode = {str(x) for x in ode_nodes}
    core = tfs | ode
    parts = [literature_edges()]
    if raw is not None and len(raw):
        parts.append(signed_interactions(raw))
    merged = pd.concat(parts, ignore_index=True).drop_duplicates(subset=CARNIVAL_COLS)
    sub = two_layer_subgraph(merged, core, max_edges=max_edges)
    sub = ensure_source_only_nodes(sub, ode or tfs)
    pkn = carnival_frame(sub)
    nodes = set(pkn["source"]) | set(pkn["target"])
    meta = {
        "n_edges": int(len(pkn)),
        "n_nodes": int(len(nodes)),
        "n_tf_in_pkn": int(len(tfs & nodes)),
        "n_ode_in_pkn": int(len(ode & nodes)),
        "n_source_only": int(len(source_only_nodes(pkn))),
        "sign_counts": pkn["interaction"].value_counts().to_dict(),
        "used_omnipath": raw is not None and len(raw) > 0,
    }
    return pkn, meta


def load_omnipath_ppi(cache_path: Path) -> pd.DataFrame:
    cache_path = Path(cache_path)
    if cache_path.exists():
        return pd.read_parquet(cache_path)
    from omnipath.interactions import OmniPath
    raw = OmniPath.get(genesymbols=True)
    raw = raw.reset_index(drop=True)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    raw.to_parquet(cache_path, index=False)
    return raw
