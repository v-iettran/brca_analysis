# v2 notebooks

Each notebook is a stage. They talk **only through files** under `v2/data/`
and `v2/artifacts/`. Do not import one notebook from another.

v3 cluster-first notebooks live in `notebooks/v3/` (A1–A6). Emit with
`python v2/scripts/emit_v3_notebooks.py` and smoke-run with
`python v2/scripts/run_notebook.py`.

## Contract (every notebook)

1. Header — purpose, inputs, outputs, gate, expected runtime
2. Config — paths and constants (`V2_ROOT` via `paths.ensure_src_on_path`)
3. Load — from `data/interim/` or `data/raw/`, never recompute upstream
4. Compute
5. Persist — parquet / json / eqx
6. GATE — `gate()` from `src/gate.py`, appends `reports/gates.jsonl`
7. Figures — `reports/figures/`

## How to run

From the class repo root:

```bash
pip install -r v2/env/v2_requirements.txt
# optional R: Rscript v2/env/v2_setup.R
cd v2/notebooks
jupyter lab
```

Run **NB00 → NB01 → …** in order. A FAIL gate means stop that phase.

Heavy stages are three different problems, not one RAM problem:

- **NB02 BayesPrism** — memory-bound. Smoke: `N_SAMPLES=200`, `N_SC_CELLS=25000`. Chunk bulk (samples are independent).
- **NB07 CARNIVAL** — throughput, not memory. One ILP is ~1–2 GB. Smoke: `N_PATIENTS=50`. Full cohort is wall-clock on a VPS, embarrassingly parallel.
- **NB10 ODE** — FLOPs, small memory. Smoke: `N_DRUGS=10`. A GPU helps more than RAM.

`SMOKE_TEST = True` is the default in every config cell. Smoke **passes are provisional**: `gates.jsonl` records `n`, `smoke_test`, and `provisional`. A purity Spearman of 0.71 on 200 samples is not the same evidence as on 2,000.

Sequence: smoke-test NB00→NB14 on a laptop, then one full VPS run to convert provisional gates.

NB01 and NB04 stay full (harmonisation and the VAE are cheap).

## Path rule

`V2_ROOT` is the directory that contains `src/gate.py`. Notebooks resolve it
by walking upward from the working directory, so they work from `v2/notebooks/`
or the repo root.
