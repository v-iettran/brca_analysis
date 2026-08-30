# Cluster-first breast-cancer research panel

A research prototype that groups TCGA-BRCA tumours by **molecular structure**, then
describes each group with measured evidence — pathway and transcription-factor
activity, survival, resemblance to real cell lines, and drug response curves that
were actually run in a lab.

**Not a clinical decision-support tool.** Nothing here should inform the care of a
real patient. It is a course project built to be auditable: every number on screen
traces to a file, and every claim has a gate that could have failed.

---

## What it does

Subgroups are chosen from **BIC and bootstrap stability**, never from survival.
That ordering is the whole point — pick groups from structure, then ask what they
predict. Choosing them from outcome and reporting the outcome would be circular.

| | |
|---|---|
| Cohort | TCGA-BRCA, **n = 1082** |
| Subgroups | **k = 4**, GMM (full covariance) on a product-of-experts VAE latent |
| Selection rule | lowest BIC within a 10-BIC window, broken by bootstrap ARI |
| Features described | 14 PROGENy pathways, 436 CollecTRI TFs, 2247 genes |
| Held-out demo cases | `TCGA-A8-A081`, `TCGA-OK-A5Q2`, `TCGA-A1-A0SK` |

The three demo patients are deliberate: one with all modalities, one missing
methylation, and one the model **abstains** on. A prototype that only shows its
best case is not telling you much.

Upstream of the clustering: BayesPrism deconvolution separates the malignant
compartment from stroma and immune, so subgroups describe tumour cells rather than
how much stroma a biopsy happened to contain.

## What it shows you

- **Subgroup structure** — model selection, cluster projection, membership.
- **Feature profiles** — a heatmap scaled *per family*, because a Mann-Whitney
  effect size and a Welch log2 fold-change are different units and one shared
  colour scale would be misleading.
- **Survival** — Kaplan-Meier with at-risk tables. The pre-registered k = 4 result
  is primary; other k are shown as clearly-labelled exploratory values.
- **Cell lines** — the closest real lines, with GDSC2 dose-response curves. Solid
  where the drug was actually tested, dotted beyond that range, because 10 of 13
  curves have an IC50 extrapolated past the highest tested concentration.
- **Drug candidates** — LINCS connectivity, each tagged standard-of-care /
  investigational / not usable in humans, from a curated registry.
- **A research copilot** — grounded: every number it says is checked against the
  run before you see it. Answers with a hosted model, a local model through Ollama,
  or a deterministic summary when neither is configured.

## What did not work

Kept here on purpose. `v3/reports/gates.jsonl` holds 34 gates and a third of them
fail.

- **A5.1 reversal control failed honestly.** The HER2 control tests against an
  endocrine-like cluster. It was not quietly re-scoped to pass.
- **The panel does not transfer to METABRIC.** External validation on 1,980
  independent samples passed its pre-registered criteria (survival p = 3.3 × 10⁻⁸)
  and then collapsed under controls added afterwards: random gene sets, matched for
  expression and variance, did as well or better. Four comparisons agree. Written
  up in `v3/reports/prereg_a7_metabric_transfer.md` and
  `v3/reports/prereg_a8_within_luminal.md`,
  criteria untouched, outcomes appended.

That second one is the most useful thing in the repository. A pass threshold of
`p < 0.05` was far too weak when the right comparison was a matched random gene
set. Any future gate of this shape should read "beats a matched null".

---

## Layout

```
v3/                       the scientific pipeline
  notebooks/v3/           A1–A6, one stage each, talking only through files
  src/                    shared helpers (clustering, stats, payload assembly)
  scripts/                runnable pipeline stages and validation experiments
  tests/                  50 contract tests
  reports/                gates.jsonl, pre-registrations, results
  data/                   raw/ and interim/ (both gitignored, large)
application/
  apps/api/               FastAPI backend, port 8000
  apps/web/               Next.js panel, port 3000
  packages/pipeline_core/ shared library, installed editable
DEPLOY.md                 putting it online
```

Raw data is not in the repository — TCGA and METABRIC archives are ~1 GB each. The
API serves pre-computed payloads from `application/apps/api/app/data/v3/`, which
**are** committed, so the panel runs without any of it.

---

## Running it locally

Two programs. Both must be up. Set aside about ten minutes the first time.

### 1. The API

```bash
cd application/apps/api
python3 -m venv .venv
.venv/bin/pip install -e ../../packages/pipeline_core
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --reload --port 8000
```

Check it: `curl http://localhost:8000/health` should return JSON with
`"status": "ok"`. Deployed with `PUBLIC_DEMO_MODE=true` it reports `"degraded"`
instead, which is also expected — that flag additionally requires a v1 demo bundle
this panel does not use. Either way the status code is 200.

### 2. The panel

In a second terminal:

```bash
cd application/apps/web
npm install
npm run dev
```

Open **http://localhost:3000**.

> **Use `localhost`, not `127.0.0.1`.** The API's CORS allowlist matches the origin
> string exactly, and the two are different strings. Every panel will sit empty
> otherwise. This is the single most common way local setup goes wrong.

### 3. Optional extras

**Literature search** needs the Paperclip SDK and a key. It is not in
`requirements.txt` because the vendor's URL is not a filename pip can parse:

```bash
.venv/bin/python scripts/install_paperclip.py
export PAPERCLIP_API_KEY=...
```

Without it the literature panels say so plainly rather than showing an empty list.

**A local LLM for the copilot** needs [Ollama](https://ollama.com):

```bash
ollama pull qwen3:8b
export OLLAMA_ENABLED=true
```

Without any model the copilot answers from a deterministic summary, generated
directly from the run and labelled as such. It is correct by construction, and the
grounding tests treat all three modes identically.

### Running the tests

The pipeline has its own environment, which is not in the repository (virtual
environments never are). Build it once:

```bash
python3 -m venv v3/.venv
v3/.venv/bin/pip install -r v3/env/v3_requirements.txt
```

Then:

```bash
# pipeline — 50 contract tests
PYTHONPATH=v3/src v3/.venv/bin/python -m pytest v3/tests/ -q

# api
cd application/apps/api && .venv/bin/python -m pytest tests/ -q

# web — typecheck, lint, unit tests
cd application/apps/web && npx tsc --noEmit && npx eslint src && npm test
```

The web tests regenerate their fixtures from the live payloads first, so a payload
change cannot leave stale fixtures asserting an old contract. That mistake cost
three rounds of debugging before it was fixed at the root.

### Re-running the pipeline

Only if you have the raw archives in `v3/data/raw/`. Stages write to
`v3/data/interim/v3/` and are picked up by the API on the next request:

```bash
PYTHONPATH=v3/src v3/.venv/bin/python v3/scripts/run_real_pathways.py
PYTHONPATH=v3/src v3/.venv/bin/python v3/scripts/run_lincs_reversal.py
```

---

## Deploying

`DEPLOY.md` covers it end to end, with no assumed deployment experience —
including the three build failures this project actually hit and why each happened.

## Ground rules this repo follows

- No synthetic or padded samples, ever.
- No gate threshold revised to accommodate a result.
- `k` is never retuned from survival.
- A failed gate stays in the ledger and stays visible in the interface.
