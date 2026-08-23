"""Drug-name and identifier joins, ported from person_med_a2 Q5.R / drug_names.py.

GDSC2 has CELL_LINE_NAME *and* DRUG_NAME. Matching 'name' in the column
title silently joins on cell lines. ALMANAC ComboDrugGrowth is NSC-only;
names come from the Q5 NSC map (CellMiner / NCI companion tables).
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

# Q5.R normalise_drug_name aliases + pipeline_core.drug_names
_ALIASES = {
    "5 fu": "5-fluorouracil",
    "5 fluorouracil": "5-fluorouracil",
    "fluorouracil": "5-fluorouracil",
    "adria": "doxorubicin",
    "adriamycin": "doxorubicin",
    "doxorubicin hydrochloride": "doxorubicin",
    "ellence": "epirubicin",
    "epirubicin hydrochloride": "epirubicin",
    "taxol": "paclitaxel",
    "paclitaxel taxol": "paclitaxel",
    "taxotere": "docetaxel",
    "docetaxel taxotere": "docetaxel",
    "gemzar": "gemcitabine",
    "gemcitabine hydrochloride": "gemcitabine",
    "cis diamminedichloroplatinum": "cisplatin",
    "cis platinum": "cisplatin",
    "cisplatinum": "cisplatin",
    "platinol": "cisplatin",
    "rapamune": "rapamycin",
    "sirolimus": "rapamycin",
    "cci 779": "temsirolimus",
    "torisel": "temsirolimus",
    "tykerb": "lapatinib",
    "tyverb": "lapatinib",
    "lapatinib ditosylate": "lapatinib",
    "lynparza": "olaparib",
    "ibrance": "palbociclib",
}


def normalize_drug_name(name: str) -> str:
    """Q5.R `normalise_drug_name`: lowercase, strip punctuation, apply aliases.

    Also drops a trailing target suffix used in drug_pk.csv (`palbociclib_cdk6`).
    """
    raw = str(name).split("_")[0]
    value = re.sub(r"[^a-z0-9]+", " ", raw.lower()).strip()
    value = re.sub(r"\s+", " ", value)
    return _ALIASES.get(value, value)


def gdsc_drug_name_column(columns) -> str | None:
    """Prefer DRUG_NAME. Never return CELL_LINE_NAME."""
    cols = [str(c) for c in columns]
    exact = {c.upper().replace(" ", "_"): c for c in cols}
    for key in ("DRUG_NAME", "DRUGNAME"):
        if key in exact:
            return exact[key]
    hits = [
        c for c in cols
        if "drug" in c.lower() and "name" in c.lower() and "cell" not in c.lower()
    ]
    return hits[0] if hits else None


def gdsc_ic50_column(columns) -> str | None:
    cols = [str(c) for c in columns]
    exact = {c.upper().replace(" ", "_"): c for c in cols}
    for key in ("LN_IC50", "LNIC50", "IC50_NM", "IC50"):
        if key in exact:
            return exact[key]
    hits = [c for c in cols if "ln_ic50" in c.lower() or c.lower() == "ic50"]
    return hits[0] if hits else None


def ln_ic50_um_to_nm(ln_ic50) -> float:
    """GDSC2 LN_IC50 is ln(IC50 in µM)."""
    return float(np.exp(float(ln_ic50)) * 1000.0)


def median_gdsc_ic50_nm(gdsc: pd.DataFrame, drug: str, breast_only: bool = True) -> float | None:
    """Median observed IC50 (nM) for a canonical drug name, BRCA lines if possible."""
    name_col = gdsc_drug_name_column(gdsc.columns)
    ic_col = gdsc_ic50_column(gdsc.columns)
    if name_col is None or ic_col is None:
        return None
    want = normalize_drug_name(drug)
    names = gdsc[name_col].map(normalize_drug_name)
    sub = gdsc.loc[names == want]
    if sub.empty:
        return None
    if breast_only and "TCGA_DESC" in sub.columns:
        br = sub[sub["TCGA_DESC"].astype(str).str.upper().eq("BRCA")]
        if len(br) >= 3:
            sub = br
    vals = pd.to_numeric(sub[ic_col], errors="coerce").dropna()
    if vals.empty:
        return None
    if str(ic_col).upper().replace(" ", "_") in {"LN_IC50", "LNIC50"}:
        return float(np.median([ln_ic50_um_to_nm(v) for v in vals]))
    return float(vals.median())


def load_pk_table(path: Path) -> pd.DataFrame:
    """Alias for pk_table.load_pk_table so existing readers can share one import."""
    from pk_table import load_pk_table as _load
    return _load(path)


def load_nsc_name_map(ref: Path) -> pd.DataFrame:
    """Union of Q5 `almanac_nsc_name_map.csv` and the PK-table overlay."""
    frames = []
    ref = Path(ref)
    for name in ("almanac_nsc_name_map.csv", "almanac_nsc_map.csv"):
        path = ref / name
        if not path.is_file():
            continue
        df = pd.read_csv(path)
        rename = {}
        if "drug_name" in df.columns and "drug" not in df.columns:
            rename["drug_name"] = "drug"
        df = df.rename(columns=rename)
        if "nsc" not in df.columns or "drug" not in df.columns:
            continue
        part = df[["nsc", "drug"]].copy()
        part["nsc"] = pd.to_numeric(part["nsc"], errors="coerce")
        part = part.dropna(subset=["nsc"])
        part["nsc"] = part["nsc"].astype(int)
        part["drug"] = part["drug"].map(normalize_drug_name)
        frames.append(part.dropna(subset=["drug"]))
    if not frames:
        return pd.DataFrame(columns=["nsc", "drug"])
    out = pd.concat(frames, ignore_index=True)
    out = out[out["drug"].astype(str).str.len() > 0]
    return out.drop_duplicates(subset=["nsc"], keep="first")
