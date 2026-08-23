"""Download, hash, and manifest helpers for NB00."""

from __future__ import annotations

import hashlib
import shutil
import ssl
import urllib.request
from pathlib import Path

import pandas as pd

MANIFEST_COLUMNS = [
    "dataset",
    "source_key",
    "source_organisation",
    "source_page",
    "release_or_version",
    "retrieval_date",
    "original_filename",
    "local_path",
    "file_size_bytes",
    "sha256",
    "licence_or_access_note",
    "intended_role",
    "required_for_nb00",
    "verified",
    "notes",
]

REQUIRED_NB00 = [
    "metabric",
    "tcga_brca",
    "gtex_breast",
    "omnipath",
    "gdsc2",
    "depmap",
    "wu_scrna",
]


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        while True:
            block = f.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def empty_manifest() -> pd.DataFrame:
    return pd.DataFrame(columns=MANIFEST_COLUMNS)


def load_manifest(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    missing = [c for c in MANIFEST_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Manifest missing columns: {missing}")
    return df


def missing_required(manifest: pd.DataFrame) -> list[str]:
    rows = manifest.loc[manifest["required_for_nb00"].map(lambda x: str(x).lower() in {"true", "1"})]
    present = set(
        rows.loc[rows["verified"].map(lambda x: str(x).lower() in {"true", "1"}), "source_key"].astype(str)
    )
    return [s for s in REQUIRED_NB00 if s not in present]


def register_file(
    manifest: pd.DataFrame,
    *,
    dataset: str,
    source_key: str,
    local_path: Path,
    source_page: str = "",
    source_organisation: str = "",
    release_or_version: str = "",
    retrieval_date: str = "",
    licence_or_access_note: str = "",
    intended_role: str = "",
    required_for_nb00: bool = True,
    notes: str = "",
    v2_root: Path | None = None,
) -> pd.DataFrame:
    path = Path(local_path)
    rel = str(path)
    if v2_root is not None:
        try:
            rel = str(path.resolve().relative_to(Path(v2_root).resolve()))
        except ValueError:
            rel = str(path)
    html = False
    if path.is_file():
        try:
            head = path.read_bytes()[:64].lstrip().lower()
            html = head.startswith(b"<") or b"<html" in head
        except OSError:
            html = False
    verified = (
        path.is_file()
        and "placeholder" not in path.name.lower()
        and path.stat().st_size > 32
        and not html
    )
    rec = {
        "dataset": dataset,
        "source_key": source_key,
        "source_organisation": source_organisation,
        "source_page": source_page,
        "release_or_version": release_or_version,
        "retrieval_date": retrieval_date,
        "original_filename": path.name if verified else "",
        "local_path": rel,
        "file_size_bytes": int(path.stat().st_size) if verified else "",
        "sha256": sha256_file(path) if verified else "",
        "licence_or_access_note": licence_or_access_note,
        "intended_role": intended_role,
        "required_for_nb00": required_for_nb00,
        "verified": verified,
        "notes": notes,
    }
    rest = manifest.loc[manifest["source_key"] != source_key]
    return pd.concat([rest, pd.DataFrame([rec])], ignore_index=True)


def download_url(url: str, dest: Path, timeout: int = 120) -> Path:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file() and dest.stat().st_size > 0:
        return dest
    ctx = ssl.create_default_context()
    try:
        import certifi

        ctx = ssl.create_default_context(cafile=certifi.where())
    except Exception:
        pass
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "person-med-v2/nb00"})
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp, tmp.open("wb") as out:
        shutil.copyfileobj(resp, out)
    tmp.replace(dest)
    return dest


def link_or_copy(src: Path, dest: Path) -> Path:
    src, dest = Path(src), Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() or dest.is_symlink():
        return dest
    try:
        dest.symlink_to(src.resolve())
    except OSError:
        shutil.copy2(src, dest)
    return dest
