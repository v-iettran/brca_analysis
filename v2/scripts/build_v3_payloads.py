"""Write v3 cohort/patient payloads from real NB02 intrinsic expression."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from paths import resolve_v2_root
from v3_real import persist_real


def main() -> None:
    v2 = resolve_v2_root(ROOT)
    print(persist_real(v2, repo_root=v2.parent, n_boot=20, n_init=5))


if __name__ == "__main__":
    main()
