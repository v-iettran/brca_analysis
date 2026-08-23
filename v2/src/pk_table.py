"""PK-table schema, ALMANAC ranking, and coverage counts for A1.

Does not invent NSC IDs. Drugs without an NCI number stay in the table for
the NB10 mechanism split but do not count toward pair coverage.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from drug_map import load_nsc_name_map, normalize_drug_name

PK_COLUMNS = [
    "drug_name",
    "nsc_id",
    "target_gene",
    "in_ode_topology",
    "ic50_nm",
    "ic50_source_doi",
    "cmax_nm",
    "cmax_source_doi",
    "route",
    "curated_by",
    "curated_date",
    "h",
    "notes",
]


def topology_nodes(ode_nodes: Path | pd.DataFrame | list[str]) -> set[str]:
    if isinstance(ode_nodes, (list, set, tuple)):
        return {str(g).upper() for g in ode_nodes}
    if isinstance(ode_nodes, pd.DataFrame):
        col = "gene" if "gene" in ode_nodes.columns else ode_nodes.columns[0]
        return set(ode_nodes[col].astype(str).str.upper())
    df = pd.read_csv(ode_nodes)
    return set(df["gene"].astype(str).str.upper())


def load_pk_table(path: Path) -> pd.DataFrame:
    """Read drug_pk.csv. Accepts legacy `drug` as an alias of `drug_name`."""
    df = pd.read_csv(path)
    if "drug_name" not in df.columns and "drug" in df.columns:
        df = df.rename(columns={"drug": "drug_name"})
    if "drug" not in df.columns and "drug_name" in df.columns:
        df["drug"] = df["drug_name"]
    df["drug_name"] = df["drug_name"].map(lambda x: normalize_drug_name(x) if pd.notna(x) else x)
    df["drug"] = df["drug_name"]
    if "target_gene" in df.columns:
        df["target_gene"] = df["target_gene"].astype(str).str.upper()
    if "in_ode_topology" in df.columns:
        df["in_ode_topology"] = df["in_ode_topology"].map(_as_bool)
    if "nsc_id" in df.columns:
        df["nsc_id"] = pd.to_numeric(df["nsc_id"], errors="coerce")
    if "h" not in df.columns:
        df["h"] = 1.0
    return df


def _as_bool(v) -> bool:
    if isinstance(v, bool):
        return v
    if pd.isna(v):
        return False
    return str(v).strip().lower() in {"1", "true", "yes", "t", "y"}


def load_almanac_named_pairs(
    raw_dir: Path | None = None,
    ref_dir: Path | None = None,
    q5_fallback: Path | None = None,
) -> pd.DataFrame:
    """Named breast pairs: drug_a, drug_b, score. Raw ALMANAC or Q5 summary."""
    from io_data import is_html, load_almanac_pair_scores, pick_data_file

    nsc_map = load_nsc_name_map(ref_dir) if ref_dir is not None else pd.DataFrame()
    if raw_dir is not None:
        path = pick_data_file(Path(raw_dir))
        if path is not None and not is_html(path):
            try:
                got = load_almanac_pair_scores(path, nsc_map=nsc_map, breast_only=True)
                if got is not None and len(got) and "drug_a" in got.columns:
                    return got[["drug_a", "drug_b", "score"]].copy()
            except Exception:
                pass
    candidates = []
    if ref_dir is not None:
        candidates.append(Path(ref_dir) / "almanac_breast_pair_summary.csv")
    if q5_fallback is not None:
        candidates.append(Path(q5_fallback))
    for cand in candidates:
        if cand.is_file() and cand.stat().st_size > 1024:
            return _pairs_from_q5_summary(cand)
    return pd.DataFrame(columns=["drug_a", "drug_b", "score"])


def _pairs_from_q5_summary(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    a = df["drug_a"].map(normalize_drug_name) if "drug_a" in df.columns else None
    b = df["drug_b"].map(normalize_drug_name) if "drug_b" in df.columns else None
    score_col = next(
        (c for c in df.columns if "median_combo" in c.lower() or c.lower() == "score"),
        None,
    )
    if a is None or b is None or score_col is None:
        return pd.DataFrame(columns=["drug_a", "drug_b", "score"])
    out = pd.DataFrame({"drug_a": a, "drug_b": b, "score": pd.to_numeric(df[score_col], errors="coerce")})
    out = out.dropna(subset=["drug_a", "drug_b", "score"])
    out = out[out["drug_a"] != out["drug_b"]]
    return out.reset_index(drop=True)


def rank_almanac_drugs(pairs: pd.DataFrame) -> pd.DataFrame:
    """Rank drugs by how many breast-cell-line pairs they appear in."""
    if pairs.empty:
        return pd.DataFrame(columns=["drug", "n_pairs"])
    stacked = pd.concat([pairs["drug_a"], pairs["drug_b"]], ignore_index=True)
    counts = stacked.value_counts().rename_axis("drug").reset_index(name="n_pairs")
    return counts.sort_values(["n_pairs", "drug"], ascending=[False, True]).reset_index(drop=True)


def count_almanac_pairs_fully_covered(pk: pd.DataFrame, pairs: pd.DataFrame) -> int:
    """Unordered named pairs where both drugs have an NSC in the PK table."""
    have = set(pk.loc[pk["nsc_id"].notna(), "drug_name"].map(normalize_drug_name))
    if pairs.empty or not have:
        return 0
    a = pairs["drug_a"].map(normalize_drug_name)
    b = pairs["drug_b"].map(normalize_drug_name)
    return int(((a.isin(have)) & (b.isin(have)) & (a != b)).sum())


def coverage_note(pk: pd.DataFrame, n_pairs: int) -> str:
    n_in = int(pk["in_ode_topology"].sum()) if "in_ode_topology" in pk.columns else 0
    n_nsc = int(pk["nsc_id"].notna().sum()) if "nsc_id" in pk.columns else 0
    return f"{len(pk)} drugs, {n_in} in topology, {n_nsc} with NSC, n_pairs={n_pairs}"
