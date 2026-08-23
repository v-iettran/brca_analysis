# Copilot API

FastAPI backend for the MOFA-Guided Oncology Research Copilot. It exposes the
deterministic scientific core in [`packages/pipeline_core`](../../packages/pipeline_core)
plus external evidence adapters (Paperclip literature, ClinicalTrials.gov,
local Ollama) over a small set of endpoints, and persists every run and audit
event in SQLite. See [`docs/mofa_copilot/`](../../docs/mofa_copilot/) for the
full system documentation.

## Local development

From the `application/` directory:

```bash
python3 -m venv ../.venv_copilot
source ../.venv_copilot/bin/activate
pip install -e packages/pipeline_core
pip install -r apps/api/requirements.txt

cp apps/api/.env.example apps/api/.env   # fill in secrets locally, never commit

cd apps/api
uvicorn app.main:app --reload
```

The API listens on `http://localhost:8000`; visit `/docs` for interactive
OpenAPI docs, or `/health` for a quick status/dependency check.

### One-time artifact preparation

Before the API can serve real analyses, generate the artifacts it reads
(these read the *raw* METABRIC data once and then never again — see
[`docs/mofa_copilot/DATA_PROVENANCE.md`](../../docs/mofa_copilot/DATA_PROVENANCE.md)):

```bash
python3 jobs/train_cluster_classifier.py
python3 jobs/generate_synthetic_patients.py
```

`jobs/refresh_gctx_cluster_drugs.py` (regenerates the GCTX-derived cluster
drug tables) is host-only and requires the 33 GB
`level5_beta_trt_cp_n720216x12328.gctx` file — see that job's docstring and
`docs/mofa_copilot/RUNBOOK.md`.

## Testing

```bash
cd apps/api
pytest -q
```

Tests use fixtures for Paperclip/ClinicalTrials.gov/Ollama (no live network
or LLM access required) and a temporary SQLite database per test session.

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health` | API/Ollama/external-query status |
| `GET` | `/patients/synthetic` | List demo synthetic patients |
| `GET` | `/patients/synthetic/{id}` | Full synthetic patient (expression + metadata) |
| `POST` | `/analysis` | Submit a patient profile, run the full pipeline |
| `GET` | `/analysis/{run_id}` | Retrieve a completed analysis result |
| `GET` | `/analysis/{run_id}/audit` | Full deterministic tool-call audit trail |
| `GET` | `/analysis/{run_id}/drugs/{drug}/literature` | Paperclip literature for one drug |
| `GET` | `/analysis/{run_id}/drugs/{drug}/trials` | ClinicalTrials.gov matches for one drug |
| `GET` | `/analysis/{run_id}/clusters/{cluster_id}` | PAM50-adjusted positive/negative cluster-signature genes |
| `GET` | `/analysis/{run_id}/clusters/{cluster_id}/genes/{gene}/literature` | On-demand Paperclip context for one signature gene |
| `POST` | `/analysis/{run_id}/chat` | Safety-constrained local explanation of this run's deterministic evidence |
| `GET` | `/analysis/{run_id}/export/{format}` | `json`, `csv`, or `pdf` export |

## Secrets

`PAPERCLIP_API_KEY` is read only from the environment (`.env`, never
committed — see `.gitignore`). Rotate any key that has ever been shared in
chat, a commit, or a log. `ALLOW_EXTERNAL_QUERIES=false` disables all
outbound Paperclip/ClinicalTrials.gov calls; patient RNA/metadata are never
sent externally regardless of this flag — only drug names and synonyms are.
