"""Held-out TCGA demo patients. Excluded from VAE, PRECISE, and conformal fits."""

from __future__ import annotations

import json
from pathlib import Path

SUFFICIENT = 0.40
MARGINAL = 0.25

ROLE_MASKS = {
    "full_modality": ("rna", "cna", "methylation"),
    "missing_view": ("rna", "cna"),
    "abstain": ("rna",),
}


def demo_manifest_path(ref: Path) -> Path:
    return Path(ref) / "demo_patients.json"


def load_demo_manifest(path: Path | None = None) -> dict:
    if path is None or not Path(path).exists():
        return {"patients": [], "exclude_from_fits": []}
    return json.loads(Path(path).read_text())


def load_demo_exclude_ids(path: Path | None = None) -> list[str]:
    """IDs that must not enter VAE / PRECISE / conformal calibration."""
    man = load_demo_manifest(path)
    ids = list(man.get("exclude_from_fits") or [])
    for row in man.get("patients") or []:
        pid = str(row.get("patient_id") or "")
        if pid and pid not in ids:
            ids.append(pid)
    return ids


def demo_id_prefixes(ids: list[str]) -> set[str]:
    return {str(i)[:12] for i in ids}


def is_excluded(sample_id: str, exclude_ids: list[str]) -> bool:
    sid = str(sample_id)
    prefixes = demo_id_prefixes(exclude_ids)
    return sid in set(map(str, exclude_ids)) or sid[:12] in prefixes


def tumour_verdict(tumour_fraction: float) -> str:
    frac = float(tumour_fraction)
    if frac >= SUFFICIENT:
        return "sufficient"
    if frac >= MARGINAL:
        return "marginal"
    return "insufficient"


def view_mask_for_role(role: str) -> tuple[str, ...]:
    return ROLE_MASKS.get(str(role), ROLE_MASKS["full_modality"])
