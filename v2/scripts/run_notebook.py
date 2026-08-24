"""Execute v2 notebooks' code cells in-process (no jupyter kernel required)."""

from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

V2 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V2 / "src"))


def run_notebook(path: Path, extra: dict | None = None) -> dict:
    path = Path(path)
    candidates = [path, V2 / path, V2 / "notebooks" / path, V2 / "notebooks" / "v3" / path]
    for cand in candidates:
        if cand.is_file():
            path = cand
            break
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
            return {"ok": False, "cell": i, "ns": g, "path": str(path)}
    return {"ok": True, "ns": g, "path": str(path)}


if __name__ == "__main__":
    names = sys.argv[1:] or [
        "notebooks/v3/NB_A1_latent_and_clusters.ipynb",
        "notebooks/v3/NB_A2_cluster_survival.ipynb",
        "notebooks/v3/NB_A3_cluster_characterisation.ipynb",
        "notebooks/v3/NB_A4_normal_reference.ipynb",
        "notebooks/v3/NB_A5_drug_retrieval.ipynb",
        "notebooks/v3/NB_A6_payloads.ipynb",
    ]
    failed = []
    for name in names:
        print("=" * 60, name)
        result = run_notebook(Path(name))
        if not result["ok"]:
            print(f"FAIL cell {result.get('cell')} {result.get('path')}")
            failed.append(name)
        else:
            print("OK", result.get("path"))
    if failed:
        print("failed:", failed)
        sys.exit(1)
