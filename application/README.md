# MOFA-Guided Oncology Research Copilot

A local-first **FastAPI + Next.js** research prototype that turns a single patient's RNA + metadata into transparent drug-overlap nominations, Q2/predictor context, literature, and clinical-trial evidence.

**This is a research demo, not a clinical decision-support tool.** See [`docs/mofa_copilot/LIMITATIONS.md`](docs/mofa_copilot/LIMITATIONS.md).

## What you get

- **Patient Analysis** — RNA UMAP placement, MOFA cluster, List 1 / List 2 overlap nominations with human-development gating, standard-of-care comparators, predictor context, grounded evidence rationale, and a safety-constrained Copilot chat.
- **Public demo** — synthetic patients only; hosted RNA is never accepted. See `PUBLIC_DEMO_MODE` and `docs/mofa_copilot/RUNBOOK.md`.
- **Clinical Trials** — trial matches with transparent eligibility criteria.
- **Exports** — JSON, CSV, and PDF per analysis run.

Full system docs: [`docs/mofa_copilot/README.md`](docs/mofa_copilot/README.md)

## Repository layout

```
application/
├── apps/
│   ├── api/              # FastAPI backend (port 8000)
│   └── web/              # Next.js clinician UI (port 3000)
├── packages/
│   └── pipeline_core/    # deterministic scientific core
├── jobs/                 # offline artifact-generation scripts (host-only)
├── docs/mofa_copilot/    # runbook, clinician guide, provenance
├── docker-compose.yml
└── .dockerignore

../outputs/               # versioned analysis tables + runtime artifacts (repo root)
```

## Prerequisites

| Tool | Version | Required |
|------|---------|----------|
| Python | 3.12+ | Yes |
| Node.js | 22+ | Yes |
| npm | bundled with Node | Yes |
| Docker + Compose | recent | Optional (alternative to local dev) |
| [Ollama](https://ollama.com) | any | Optional — Copilot uses rule-based fallbacks without it |
| Paperclip API key | — | Optional — literature search shows "unavailable" without it |
| Internet | — | Optional — needed only for live literature / trials |

## 1. Clone the repo

```bash
git clone https://github.com/Lifework-Health/person_med_a2.git
cd person_med_a2
```

## 2. Runtime artifacts (read this first)

The app needs a pre-built artifact bundle under `outputs/copilot_artifacts/`. **This folder is not committed to Git** (it contains large `.parquet` and `.db` files).

### Quick setup with the helper script

```bash
cd person_med_a2

# See what's missing
./application/scripts/setup_copilot_artifacts.sh check

# Option A — install a shared bundle (from Luke or a download URL)
./application/scripts/setup_copilot_artifacts.sh install /path/to/copilot_artifacts_bundle.tar.gz
# or:
./application/scripts/setup_copilot_artifacts.sh install --url https://example.com/copilot_artifacts_bundle.tar.gz

# Option B — build locally (needs METABRIC; see below)
./application/scripts/setup_copilot_artifacts.sh build
# full List 1 / List 2 GCTX scoring (slow, needs 33 GB GCTX file):
./application/scripts/setup_copilot_artifacts.sh build --with-gctx
```

**For Luke (packaging to share):**

```bash
./application/scripts/package_copilot_artifacts.sh
# creates copilot_artifacts_bundle.tar.gz at the repo root
```

After a fresh clone you can also set up manually:

### Option A — Use a shared artifact bundle (recommended for the demo)

Ask Luke for the `copilot_artifacts/` folder and place it at:

```
person_med_a2/outputs/copilot_artifacts/
```

Expected contents (approximate sizes):

| File / folder | Purpose |
|---------------|---------|
| `metabric_expression_cache.parquet` (~380 MB) | METABRIC reference expression |
| `cluster_classifier_artifact.json` | RNA → MOFA cluster classifier |
| `cluster_rna_centroids.parquet` | List 2 residual centroids |
| `rna_umap/` | RNA UMAP projection artifacts |
| `compact_gctx/` (~6 GB) | Breast cell-line GCTX for List 1 / List 2 scoring |
| `predictor_q2_reference_scores_v1.parquet` | Predictor reference cohort scores |
| `synthetic_patients/` | Three demo patients |
| `copilot.db` | Created automatically on first API start if missing |

The Q2/Q4/Q5 CSV tables under `outputs/q2/`, `outputs/q4/`, and `outputs/q5/` **are** in Git and come with the clone.

### Option B — Build artifacts yourself

You need the raw METABRIC download. By default the jobs look for it at:

```
../final-project/brca_metabric/
```

Download from [cBioPortal — METABRIC](https://www.cbioportal.org/study/summary?id=brca_metabric) (expression + clinical files), or set `METABRIC_DIR` to your local path.

```bash
cd application
python3 -m venv ../.venv_copilot
source ../.venv_copilot/bin/activate   # Windows: ..\.venv_copilot\Scripts\activate
pip install -e packages/pipeline_core
pip install -r apps/api/requirements.txt

# Core artifacts (~5–15 min depending on machine)
python3 jobs/train_cluster_classifier.py
python3 jobs/generate_synthetic_patients.py
python3 jobs/build_rna_projection_artifacts.py

# Optional but needed for full List 1 / List 2 overlap scoring (~30+ min, needs 33 GB GCTX)
# Place level5_beta_trt_cp_n720216x12328.gctx in ../final-project/ (or set GCTX_PATH)
# python3 jobs/build_compact_gctx_artifact.py
```

Without `compact_gctx/`, the app still runs but overlap nominations fall back to cluster drug tables and suggestive hypotheses only.

## 3. Configure secrets (optional)

```bash
cp apps/api/.env.example apps/api/.env
cp apps/web/.env.local.example apps/web/.env.local
```

Edit `apps/api/.env`:

```bash
ALLOW_EXTERNAL_QUERIES=true          # set false to disable all outbound API calls
PAPERCLIP_API_KEY=your_key_here      # for live literature search
OLLAMA_ENABLED=false                 # set true if you run Ollama locally
```

Never commit `.env` files. If a key was ever shared in chat or a screenshot, rotate it at the issuing service.

## 4. Run locally (recommended for development)

Open **two terminals** from `person_med_a2/application/`:

**Terminal 1 — API**

```bash
source ../.venv_copilot/bin/activate
cd apps/api
uvicorn app.main:app --reload
```

**Terminal 2 — Web UI**

```bash
cd apps/web
npm install
npm run dev
```

Then open:

- App: [http://localhost:3000](http://localhost:3000)
- API docs: [http://localhost:8000/docs](http://localhost:8000/docs)
- Health check: [http://localhost:8000/health](http://localhost:8000/health)

### Try the demo

1. On the home page, pick one of the three **synthetic patients**.
2. Click **Analyze** and wait for the staged pipeline to finish (progress modal with animation).
3. Explore **Patient Analysis** (overlap cards, UMAP, signatures, comparators, Copilot) and **Clinical Trials**.
4. Click a drug or gene name to open the literature popup (requires `PAPERCLIP_API_KEY`).

## 5. Run with Docker (alternative)

Make sure `outputs/copilot_artifacts/` exists on the host **before** starting Docker (see step 2).

```bash
cd application

# Optional: create application/.env with PAPERCLIP_API_KEY=... and ALLOW_EXTERNAL_QUERIES=true
docker compose up --build
```

- API: [http://localhost:8000](http://localhost:8000)
- Web: [http://localhost:3000](http://localhost:3000)

To include a local Ollama container:

```bash
docker compose --profile llm up --build
# and set OLLAMA_ENABLED=true for the api service
```

Docker mounts only `../outputs/` into the API container. Raw METABRIC and the 33 GB GCTX file are never copied into images.

## 6. Run tests (optional)

```bash
# Scientific core
cd packages/pipeline_core && pytest -q

# API (uses fixtures; no network required)
cd apps/api && pytest -q

# Web
cd apps/web && npm run test && npm run lint && npm run build
```

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `METABRIC expression file not found` | Missing raw data or cache | Get the artifact bundle (option A) or download METABRIC and run the jobs (option B) |
| `compact_gctx` / GCTX errors | Compact artifact missing | Run `jobs/build_compact_gctx_artifact.py` or use Luke's bundle |
| Empty literature popups | No Paperclip key or external queries disabled | Set `PAPERCLIP_API_KEY` and `ALLOW_EXTERNAL_QUERIES=true` in `apps/api/.env` |
| `pip install` fails on `gxl-paperclip` | Network or wheel URL issue | Ensure internet access; the wheel installs from `https://paperclip.gxl.ai/paperclip.whl` |
| Web can't reach API | Wrong base URL | Check `apps/web/.env.local` has `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000` |
| SQLite schema errors | Stale local DB | Delete `outputs/copilot_artifacts/copilot.db` and restart the API (it recreates on startup) |

## Further reading

- [`docs/mofa_copilot/RUNBOOK.md`](docs/mofa_copilot/RUNBOOK.md) — detailed operational runbook
- [`docs/mofa_copilot/CLINICIAN_GUIDE.md`](docs/mofa_copilot/CLINICIAN_GUIDE.md) — how to read the dashboard
- [`docs/mofa_copilot/DATA_PROVENANCE.md`](docs/mofa_copilot/DATA_PROVENANCE.md) — where every score comes from
- [`apps/api/README.md`](apps/api/README.md) — API endpoint reference
