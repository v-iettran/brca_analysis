# Technician guide

## Repository layout

```
person_med_a2/
├── application/
│   ├── packages/pipeline_core/   # deterministic scientific core (pure Python, no network/LLM)
│   ├── apps/api/                 # FastAPI service: orchestration, audit, adapters
│   ├── apps/web/                 # Next.js clinician/technical UI
│   ├── jobs/                     # offline, host-only artifact-generation scripts
│   └── docs/mofa_copilot/        # this documentation set
├── outputs/                      # versioned artifacts read by the API at runtime
└── scripts/Q5.R                  # original R pipeline this system ports/parity-tests against
```

## Request lifecycle (`POST /analysis` and async)

V2 orchestration (`services/analysis_service.py`) runs staged work:

1. validate → normalize/project (cluster + RNA projection)
2. build cluster and residual signatures (`top_up` / `top_down`, default 150)
3. retrieve List 1 / List 2 (`gctx_retrieval`)
4. reconcile canonical overlap (`nominations`)
5. annotate Q2 (annotation only) + ALMANAC pairs
6. enrich evidence (Paperclip batch prefetch + artifact flags already on hits)
7. assemble dashboard payload

Endpoints:

- `POST /analysis` — synchronous (tests/compat)
- `POST /analysis/async` + `GET /analysis/{run_id}/progress` — staged UI path
- `POST /analysis/{run_id}/recalculate` — signature-size revision without re-upload
- `GET /analysis/{run_id}/trials` — run-level Trial Explorer
- `GET|POST /analysis/{run_id}/chat` — persisted Copilot history

Core modules under `pipeline_core`: `embedding`, `residual_signatures`,
`gctx_retrieval`, `nominations`, `q2_annotations`, `almanac_evidence`,
`drug_names`.

## Offline V2 artifacts

```bash
python3 jobs/build_rna_projection_artifacts.py
python3 jobs/build_compact_gctx_artifact.py   # host-only; needs full GCTX + h5py
python3 jobs/generate_synthetic_patients.py   # enriched metadata + provenance
```

Compact GCTX is optional at runtime; without it, List 2 falls back to a
residual proxy over committed cluster drug tables.

## Configuration (environment variables)

All paths are overridable — see `pipeline_core/config.py` and
`apps/api/app/config.py`:

| Variable | Default | Purpose |
| --- | --- | --- |
| `METABRIC_DIR` | `final-project/brca_metabric` | Raw METABRIC (host-only; only read once to build caches) |
| `MOFA_CLUSTERS_DIR` | `outputs/q4/mofa_clusters` | Per-cluster signature/drug tables |
| `Q2_TABLES_DIR` | `outputs/q2/data` | Q2 chemo model tables |
| `Q5_TABLES_DIR` | `outputs/q5/tables` | Q5 committed predictions/metrics |
| `ARTIFACT_DIR` | `outputs/copilot_artifacts` | Cluster classifier, caches, exports |
| `COPILOT_DB_PATH` | `outputs/copilot_artifacts/copilot.db` | SQLite audit store |
| `N_MOFA_CLUSTERS` | `5` | Number of MOFA clusters |
| `MIN_GENE_COVERAGE` | `0.6` | Below this, cluster scoring is not attempted |
| `LOW_CONFIDENCE_THRESHOLD` | `0.40` | Below this top-cluster probability, flagged "low confidence" |
| `ABSTENTION_THRESHOLD` | `0.25` | Below this *and* low coverage, the API abstains entirely |
| `ALLOW_EXTERNAL_QUERIES` | `true` | Master switch for Paperclip/ClinicalTrials.gov calls |
| `PAPERCLIP_API_KEY` | — | Secret; never log or commit |
| `OLLAMA_ENABLED` / `OLLAMA_HOST` / `OLLAMA_MODEL` | `true` / `http://localhost:11434` / `gemma3:4b` | Local LLM for explanations/stance only |

## Extending the scientific core

- New evidence types go in `packages/pipeline_core/src/pipeline_core/`, as a
  pure function taking already-loaded data (or thin file-loading functions
  decorated with `functools.lru_cache` so tests can monkeypatch them by
  attribute, as `q2_evidence.py`/`gctx_evidence.py` do).
- Add both a toy-data unit test (fast, always runs) and, if the function
  touches real artifacts, an integration test in `test_data_integration.py`
  guarded by `pytest.mark.skipif` on artifact presence.
- Never fuse a new signal into `pcr_probability` unless it has been
  refit/validated the way `pcr_model.q5_parity_report` validates the
  Q2-only model — see [`LIMITATIONS.md`](./LIMITATIONS.md) for why the MOFA
  reversal signal is kept separate today.
- Any new evidence-language string surfaced to users should be checked with
  `pipeline_core.safety.check_safety`/`is_safe` (see `test_safety.py` for the
  banned-phrase list) before being added to a template.

## Troubleshooting

| Symptom | Likely cause / fix |
| --- | --- |
| `FileNotFoundError: Q2 coefficients not found` etc. | Run `jobs/train_cluster_classifier.py` / confirm `outputs/q2`, `outputs/q4`, `outputs/q5` exist (see `DATA_PROVENANCE.md`) |
| `ValueError: Input X contains NaN` in classifier | Patient expression has genes missing from the classifier's gene list; coverage is imputed with the column mean — check `genes_found`/`genes_requested` in the response |
| Analysis submits but literature/trials 4xx | `ALLOW_EXTERNAL_QUERIES=false`, or missing `PAPERCLIP_API_KEY`, or no network — the API returns `unavailable_reason` instead of failing the whole run |
| `ModuleNotFoundError: No module named 'app'` running pytest | Run `pytest` from inside `apps/api/`, not the repo root (it's not a package) |
| Next.js dev server can't reach API | Set `NEXT_PUBLIC_API_BASE_URL` in `apps/web/.env.local` |
