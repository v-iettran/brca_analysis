# BRCA analysis (v2)

Research prototype for MOFA-guided breast cancer evidence: a reproducible v2 pipeline plus a local demo web app.

**Not a clinical decision-support tool.** Outputs are prediction *sets*, not drug rankings.

## Repository layout

```
brca_analysis/
├── v2/                 # notebooks, src, scripts, tests, reference data
│   ├── notebooks/      # NB01–NB13 analysis notebooks
│   ├── src/            # shared Python modules
│   ├── scripts/        # emitters, demo payload builder, glossary
│   ├── data/reference/ # small reference tables + demo_patients.json
│   └── env/            # v2_requirements.txt, Julia/R setup stubs
└── application/        # FastAPI + Next.js demo (held-out TCGA patients)
    ├── apps/api/
    └── apps/web/
```

Large artifacts (`data/raw`, `data/interim`, trained `.eqx` / `.pkl` weights) are **not** committed. Rebuild them with the v2 notebooks or copy from your local run.

## Quick start — demo web app

**API** (Python 3.12+, use a dedicated venv — not conda base):

```bash
python3 -m venv .venv_copilot && source .venv_copilot/bin/activate
pip install -e application/packages/pipeline_core
pip install -r application/apps/api/requirements.txt

cd application/apps/api
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

**Web** (Node 22+):

```bash
cd application/apps/web
npm install
npm run dev
```

Open http://localhost:3000 — default mode is **Held-out TCGA** (three demo patients excluded from upstream fits).

Health check: http://127.0.0.1:8000/health

## Quick start — v2 pipeline

```bash
cd v2
python3 -m venv .venv && source .venv/bin/activate
pip install -r env/v2_requirements.txt
pip install -e .  # if you add a pyproject; otherwise PYTHONPATH=src

export SSL_CERT_FILE=/etc/ssl/cert.pem
export REQUESTS_CA_BUNDLE=/etc/ssl/cert.pem

pytest tests/
```

Notebooks live in `v2/notebooks/`. Run in order (NB01 → NB13). Demo patient payloads:

```bash
python scripts/build_demo_payloads.py
```

## Key v2 decisions (product)

- **S4 (ODE simulator):** cut — `cut_s4_no_signal (join not independently verified)`
- **B5 conformal:** endocrine-treatment feature (q4) dropped after ER+ refit; shipped features are molecular only
- **Demo patients:** `TCGA-A8-A081`, `TCGA-OK-A5Q2`, `TCGA-A1-A0SK` — held out of VAE / PRECISE / conformal fits
- **UI:** seven stages (`validate` → `assemble`); no simulate stage; state 3 abstains (sections 4–5 absent)

## License / attribution

Course research project (UC Davis AI for PM). TCGA and SCAN-B data remain subject to their respective access terms.
