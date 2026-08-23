"""Append-only notebook gates. Spec §0.4.

Smoke-test passes are logged as provisional: a purity Spearman of 0.71 on
n=200 is not the same evidence as on n=2,000.

`insufficient_data` is a distinct state from fail: the join never produced
enough rows to test the scientific claim (empty GDSC/ALMANAC/CARNIVAL
identifier join, not "the ODE didn't work").
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path

from paths import resolve_v2_root


def gates_path(v2_root: Path | None = None) -> Path:
    root = v2_root or resolve_v2_root()
    path = root / "reports" / "gates.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def gate(
    notebook: str,
    name: str,
    value: float,
    threshold: float,
    direction: str = "gte",
    note: str = "",
    v2_root: Path | None = None,
    n: int | None = None,
    smoke_test: bool = False,
    min_n: int | None = None,
    insufficient_data: bool = False,
) -> bool:
    if direction == "gte":
        passed = value >= threshold
        cmp = "≥"
    elif direction == "lte":
        passed = value <= threshold
        cmp = "≤"
    else:
        raise ValueError(f"direction must be gte or lte, got {direction!r}")

    n_val = None if n is None else int(n)
    thin = bool(insufficient_data)
    if min_n is not None and (n_val is None or n_val < int(min_n)):
        thin = True

    if thin:
        status = "insufficient_data"
        passed = False
        provisional = False
    elif smoke_test and passed:
        status = "provisional_pass"
        provisional = True
    elif passed:
        status = "pass"
        provisional = False
    else:
        status = "fail"
        provisional = False

    rec = {
        "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "notebook": notebook,
        "gate": name,
        "value": float(value),
        "threshold": float(threshold),
        "direction": direction,
        "passed": bool(passed),
        "status": status,
        "insufficient_data": thin,
        "n": n_val,
        "min_n": None if min_n is None else int(min_n),
        "smoke_test": bool(smoke_test),
        "provisional": provisional,
        "note": note,
    }
    dest = gates_path(v2_root)
    with dest.open("a") as f:
        f.write(json.dumps(rec) + "\n")
    if status == "insufficient_data":
        label = "INSUFFICIENT DATA"
    elif status == "provisional_pass":
        label = "PROVISIONAL PASS"
    elif status == "pass":
        label = "PASS"
    else:
        label = "FAIL"
    n_bit = f" n={n_val}" if n_val is not None else ""
    print(f"{label}  {name}: {value:.4f} ({cmp} {threshold}){n_bit}")
    if note:
        print(f"      {note}")
    if status == "insufficient_data":
        print("      not a scientific fail — identifier join / n too thin to test the claim")
    if provisional:
        print("      smoke-test: convert to a real pass with a full VPS run")
    return passed
