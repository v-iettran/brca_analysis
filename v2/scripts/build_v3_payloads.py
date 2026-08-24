"""Write v3 cohort/patient payloads into interim and the in-repo API data dir."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from paths import resolve_v2_root
from v3_smoke import persist_smoke


def main() -> None:
    v2 = resolve_v2_root(ROOT)
    print(persist_smoke(v2, repo_root=v2.parent))


if __name__ == "__main__":
    main()
