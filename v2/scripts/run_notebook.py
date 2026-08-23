"""Execute v2 notebooks' code cells in-process (no jupyter kernel required)."""

from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

V2 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V2 / "src"))


def run_notebook(path: Path, extra: dict | None = None) -> dict:
    nb = json.loads(path.read_text())
    g = {"__name__": "__main__"}
    if extra:
        g.update(extra)
    for i, cell in enumerate(nb["cells"]):
        if cell.get("cell_type") != "code":
            continue
        src = cell.get("source", "")
        if isinstance(src, list):
            src = "".join(src)
        try:
            exec(compile(src, f"{path.name}:{i}", "exec"), g)
        except Exception:
            traceback.print_exc()
            return {"ok": False, "cell": i, "ns": g}
    return {"ok": True, "ns": g}


if __name__ == "__main__":
    names = sys.argv[1:] or [
        "NB09_ode_topology.ipynb",
        "NB10_ode_gdsc.ipynb",
        "NB11_synergy.ipynb",
        "NB13_conformal.ipynb",
        "NB14_walkthrough.ipynb",
    ]
    failed = []
    for name in names:
        print("=" * 60, name)
        result = run_notebook(V2 / "notebooks" / name)
        if not result["ok"]:
            print(f"FAIL cell {result.get('cell')}")
            failed.append(name)
        else:
            print("OK")
    if failed:
        print("failed:", failed)
        sys.exit(1)
