# Operational runbook

## 1. Prerequisites

- Python 3.12, Node.js 22+, npm.
- (Optional) [Ollama](https://ollama.com) installed locally for evidence
  explanations and citation-stance classification — the app works fully
  without it (`OLLAMA_ENABLED=false`), just with rule-based stance
  classification instead of LLM-assisted.
- (Optional) [Paperclip](https://paperclip.gxl.ai) API key for live
  literature search, and network access for ClinicalTrials.gov. Without
  these, drug detail popups show a clear "unavailable" reason instead of
  failing the whole analysis.
- Raw METABRIC (`final-project/brca_metabric/`) — only needed once, to build
  the cached artifacts in step 3. Not needed for day-to-day API requests
  once those caches exist.

## 2. Secrets

Never commit `.env` files or paste API keys into chat/commits/logs. Copy the
example files and fill in locally:

```bash
cp apps/api/.env.example apps/api/.env      # PAPERCLIP_API_KEY, etc.
cp apps/web/.env.local.example apps/web/.env.local
```

If a key was ever exposed (chat, commit, screenshot), rotate it immediately
at the issuing service before doing anything else.

## 3. One-time artifact preparation (host machine, not Docker)

Helper scripts under `application/scripts/` automate packaging and install:

```bash
# Check what is present / missing
./application/scripts/setup_copilot_artifacts.sh check

# Share a bundle (creates copilot_artifacts_bundle.tar.gz at repo root)
./application/scripts/package_copilot_artifacts.sh

# Install a shared bundle on a fresh clone
./application/scripts/setup_copilot_artifacts.sh install /path/to/copilot_artifacts_bundle.tar.gz
```

These jobs read the *raw* METABRIC/GCTX data once and write small, versioned
artifacts under `outputs/` that the API reads at runtime — after this step,
raw data access is not required again.

```bash
cd application
python3 -m venv ../.venv_copilot && source ../.venv_copilot/bin/activate
pip install -e packages/pipeline_core
pip install -r apps/api/requirements.txt

python3 jobs/train_cluster_classifier.py      # -> ../outputs/copilot_artifacts/cluster_classifier_artifact.json
python3 jobs/generate_synthetic_patients.py   # -> ../outputs/copilot_artifacts/synthetic_patients/
python3 jobs/build_rna_projection_artifacts.py
python3 jobs/build_compound_registry.py       # -> ../outputs/compound_registry/v1/
python3 jobs/build_public_demo_bundle.py      # -> ../outputs/copilot_artifacts/public_demo_bundle/v1/
# Optional (host-only; 33 GB GCTX + h5py):
# python3 jobs/build_compact_gctx_artifact.py
# python3 jobs/scan_unresolved_compounds.py
# python3 jobs/propose_compound_reviews.py
# python3 jobs/approve_compound_review.py <canonical> --reviewer NAME ...
```

`jobs/refresh_gctx_cluster_drugs.py` (regenerates `outputs/q4/mofa_clusters/cluster_{i}_drug_targets.csv`
from the 33 GB GCTX file) and `jobs/refit_pcr_with_mofa.py` (see
[`LIMITATIONS.md`](./LIMITATIONS.md) — currently blocked pending raw-GEO
reprocessing) are also host-only; run them only if you need to regenerate
those specific tables.

Docker smoke should be run with `ALLOW_EXTERNAL_QUERIES=true` and `false`.
Exports (`/analysis/{run_id}/export/{json,csv,pdf}`) must include revision,
overlap nominations, Q2 annotations, ALMANAC pairs, and limitations.

## 4. Local development (no Docker)

```bash
# Terminal 1
cd apps/api && source ../../../.venv_copilot/bin/activate
uvicorn app.main:app --reload

# Terminal 2
cd apps/web
npm install
npm run dev
```

Visit `http://localhost:3000`. API docs at `http://localhost:8000/docs`.

## 5. Testing

```bash
# Scientific core (fast, mostly toy-data unit tests; a few skip without real artifacts)
cd packages/pipeline_core && pytest -q

# API (uses fixtures for Paperclip/ClinicalTrials.gov/Ollama; no network needed)
cd apps/api && pytest -q

# Web (Vitest component tests, then lint + typecheck via build)
cd apps/web && npm run test && npm run lint && npm run build
```

## 6. Docker packaging

```bash
cd application
docker compose up --build                    # local scientific api + web
docker compose --profile llm up              # also start a local Ollama container
docker compose --profile public up --build   # hosted-demo image (bundle + registry only)
```

- `api` (port 8000) and `web` (port 3000) are built from
  `apps/api/Dockerfile` / `apps/web/Dockerfile`.
- The public profile uses `apps/api/Dockerfile.public` and does **not** mount
  raw METABRIC, raw GCTX, or compact GCTX. It includes only the sanitized
  demo bundle, compound registry, and synthetic index.
- Render: `application/render.yaml` exposes the Next.js web service and keeps
  FastAPI private. Browser `/api/*` rewrites to the private API. Set
  `SESSION_SECRET`, `HOSTED_LLM_API_KEY`, and `HOSTED_LLM_BASE_URL` as Render
  secrets. Rollback is a Render deploy of the previous image; retention
  (`RUN_RETENTION_HOURS`) purges demo runs automatically.
- To point the `web` container at a non-default API location, override
  `NEXT_PUBLIC_API_BASE_URL` in `docker-compose.yml` and rebuild (Next.js
  inlines `NEXT_PUBLIC_*` vars at build time). Public hosting should use
  `NEXT_PUBLIC_API_BASE_URL=/api` plus `INTERNAL_API_URL`.

## 7. Reproducibility notes

- The persisted classifier artifact, synthetic patients, and all `outputs/`
  tables are versioned files, not regenerated per-request — re-run the
  relevant `jobs/*.py` script and restart the API to pick up changes.
- Every analysis run's full deterministic tool-call trace (inputs, outputs,
  durations) is queryable at `GET /analysis/{run_id}/audit` and included in
  the JSON export, so any result can be traced back to the exact artifact
  versions and intermediate values that produced it.
