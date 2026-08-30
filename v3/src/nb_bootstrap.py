"""Shared notebook bootstrap."""

BOOTSTRAP = r'''
from pathlib import Path
import sys
import json
import warnings
warnings.filterwarnings("ignore")

from paths import ensure_src_on_path, resolve_v2_root
# When launched from v3/notebooks, src is a sibling of notebooks.
import pathlib as _p
_here = _p.Path.cwd()
for _cand in [_here, *_here.parents]:
    if (_cand / "src" / "gate.py").is_file():
        sys.path.insert(0, str(_cand / "src"))
        break
    if (_cand / "v3" / "src" / "gate.py").is_file():
        sys.path.insert(0, str(_cand / "v3" / "src"))
        break

from paths import ensure_src_on_path, resolve_v2_root
from gate import gate as _gate_impl
from safety import assert_safe

V2_ROOT = resolve_v2_root()
ensure_src_on_path(V2_ROOT)
REPO_ROOT = V2_ROOT.parent
RAW = V2_ROOT / "data" / "raw"
INTERIM = V2_ROOT / "data" / "interim"
REF = V2_ROOT / "data" / "reference"
ARTIFACTS = V2_ROOT / "artifacts"
FIGURES = V2_ROOT / "reports" / "figures"
for _d in (RAW, INTERIM, REF, ARTIFACTS, FIGURES):
    _d.mkdir(parents=True, exist_ok=True)

# Laptop vs VPS. Smoke passes are provisional until a full run converts them.
SMOKE_TEST = True
N_SAMPLES  = 200    if SMOKE_TEST else None   # NB02 bulk (BayesPrism; memory)
N_SC_CELLS = 25_000 if SMOKE_TEST else None   # NB02 Wu reference (BayesPrism; memory)
N_PATIENTS = 50     if SMOKE_TEST else None   # NB07 CARNIVAL (throughput, not RAM)
N_DRUGS    = 10     if SMOKE_TEST else None   # NB10 ODE (FLOPs, not RAM)

def gate(*args, **kwargs):
    kwargs.setdefault("smoke_test", SMOKE_TEST)
    return _gate_impl(*args, **kwargs)

print("V2_ROOT =", V2_ROOT, "SMOKE_TEST =", SMOKE_TEST)
'''
