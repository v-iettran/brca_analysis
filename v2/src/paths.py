"""Resolve the v2 tree root from notebooks, tests, or scripts."""

from __future__ import annotations

import sys
from pathlib import Path


def resolve_v2_root(start: Path | None = None) -> Path:
    """Walk upward until a directory containing src/gate.py is found."""
    here = Path(start).resolve() if start is not None else Path.cwd().resolve()
    candidates = [here, *here.parents]
    for path in candidates:
        if (path / "src" / "gate.py").is_file():
            return path
        nested = path / "v2"
        if (nested / "src" / "gate.py").is_file():
            return nested
    raise FileNotFoundError(
        "Could not locate v2 root (expected src/gate.py). "
        "Run notebooks from the repo root or v2/notebooks/."
    )


def ensure_src_on_path(v2_root: Path | None = None) -> Path:
    root = v2_root or resolve_v2_root()
    src = str(root / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    return root
