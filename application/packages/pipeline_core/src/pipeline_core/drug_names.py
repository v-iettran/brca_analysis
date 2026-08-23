"""Canonical compound-name normalization shared by List 1 / List 2 overlap."""

from __future__ import annotations

import re

_ALIASES = {
    "5 fu": "5-fluorouracil",
    "5 fluorouracil": "5-fluorouracil",
    "fluorouracil": "5-fluorouracil",
    "adriamycin": "doxorubicin",
    "taxol": "paclitaxel",
    "taxotere": "docetaxel",
    "gemzar": "gemcitabine",
    "sirolimus": "rapamycin",
    "tykerb": "lapatinib",
    "tyverb": "lapatinib",
}


def normalize_drug_name(name: str) -> str:
    value = re.sub(r"[^a-z0-9]+", " ", str(name).lower()).strip()
    value = re.sub(r"\s+", " ", value)
    return _ALIASES.get(value, value)


def display_drug_name(canonical: str) -> str:
    """Prefer a readable display form for known aliases."""
    special = {
        "5-fluorouracil": "5-fluorouracil",
        "rapamycin": "rapamycin",
    }
    if canonical in special:
        return special[canonical]
    return canonical
