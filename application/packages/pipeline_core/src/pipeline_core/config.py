"""Central, environment-overridable path configuration.

Nothing in this module reaches out to the network. All paths point at data that
already lives on disk (METABRIC, the Q4 MOFA cluster artifacts, and the Q5
tables). Raw METABRIC and the 33 GB GCTX file are never copied into the app or
Docker images -- they are read from wherever the host has them, configured via
environment variables so the runtime containers can mount a much smaller,
versioned artifact directory instead.
"""

from __future__ import annotations

import os
from pathlib import Path

# `person_med_a2/` repo root (this file lives at application/packages/pipeline_core/src/pipeline_core/config.py)
REPO_ROOT = Path(__file__).resolve().parents[5]

# `final-project/` sibling repo that still hosts the raw METABRIC download and the
# MOFA/L1000CDS2 signature-generation scripts.
FINAL_PROJECT_ROOT = REPO_ROOT.parent / "final-project"


def _env_path(var_name: str, default: Path) -> Path:
    value = os.environ.get(var_name)
    return Path(value).expanduser().resolve() if value else default


# Raw METABRIC multi-omics data (never bundled into Docker images/runtime).
METABRIC_DIR = _env_path("METABRIC_DIR", FINAL_PROJECT_ROOT / "brca_metabric")

# Versioned artifacts produced by the offline GCTX refresh job (jobs/refresh_gctx_cluster_drugs.py)
# and by the MOFA cluster signature pipeline (final-project/mofa_cluster_signatures.py).
MOFA_CLUSTERS_DIR = _env_path(
    "MOFA_CLUSTERS_DIR", REPO_ROOT / "outputs" / "q4" / "mofa_clusters"
)

# Q2 chemotherapy monotherapy artifacts and Q5 validated patient-level tables.
Q2_TABLES_DIR = _env_path("Q2_TABLES_DIR", REPO_ROOT / "outputs" / "q2" / "data")
Q5_TABLES_DIR = _env_path("Q5_TABLES_DIR", REPO_ROOT / "outputs" / "q5" / "tables")

# Model/classifier artifacts trained by jobs/train_cluster_classifier.py.
ARTIFACT_DIR = _env_path("ARTIFACT_DIR", REPO_ROOT / "outputs" / "copilot_artifacts")

# Synthetic demonstration patients (jobs/generate_synthetic_patients.py output).
SYNTHETIC_PATIENTS_DIR = _env_path(
    "SYNTHETIC_PATIENTS_DIR", REPO_ROOT / "outputs" / "copilot_artifacts" / "synthetic_patients"
)

# SQLite audit database used by the API (runs, warnings, external-query caches, exports).
DB_PATH = _env_path("COPILOT_DB_PATH", REPO_ROOT / "outputs" / "copilot_artifacts" / "copilot.db")

N_MOFA_CLUSTERS = int(os.environ.get("N_MOFA_CLUSTERS", "5"))

# Minimum fraction of a patient's genes that must be found in the reference gene
# universe before we attempt cluster scoring at all.
MIN_GENE_COVERAGE = float(os.environ.get("MIN_GENE_COVERAGE", "0.6"))

# Below this top-cluster probability, the run is flagged as "mixed/low-confidence"
# rather than abstained -- it is still shown, but heavily annotated.
LOW_CONFIDENCE_THRESHOLD = float(os.environ.get("LOW_CONFIDENCE_THRESHOLD", "0.40"))

# Below this coverage, cluster assignment is abstained. Elastic-net mean
# imputation of missing classifier genes can otherwise produce a peaked
# top-cluster probability that looks "high confidence" on a sparse panel.
ABSTENTION_THRESHOLD = float(os.environ.get("ABSTENTION_THRESHOLD", "0.25"))

# Default signature arms for List 1 / List 2 GCTX reversal queries.
DEFAULT_TOP_UP = int(os.environ.get("DEFAULT_TOP_UP", "150"))
DEFAULT_TOP_DOWN = int(os.environ.get("DEFAULT_TOP_DOWN", "150"))
MIN_SIGNATURE_GENES = int(os.environ.get("MIN_SIGNATURE_GENES", "10"))
MAX_SIGNATURE_GENES = int(os.environ.get("MAX_SIGNATURE_GENES", "300"))

# Q5 ALMANAC combination tables (cell-line-aligned eligible pairs).
Q5_ALMANAC_DIR = _env_path(
    "Q5_ALMANAC_DIR",
    REPO_ROOT / "outputs" / "q5" / "patient_projection_almanac_combinations" / "tables",
)

# Compact breast-cell-line GCTX artifact for runtime residual scoring.
COMPACT_GCTX_DIR = _env_path(
    "COMPACT_GCTX_DIR", ARTIFACT_DIR / "compact_gctx"
)
COMPACT_GCTX_MATRIX = COMPACT_GCTX_DIR / "breast_trt_cp_matrix.parquet"
COMPACT_GCTX_META = COMPACT_GCTX_DIR / "breast_trt_cp_signatures.parquet"

# RNA-only UMAP projection of METABRIC, colored by MOFA cluster.
UMAP_ARTIFACT_DIR = _env_path("UMAP_ARTIFACT_DIR", ARTIFACT_DIR / "rna_umap")
UMAP_REFERENCE_PATH = UMAP_ARTIFACT_DIR / "reference_coordinates.parquet"
UMAP_TRANSFORM_PATH = UMAP_ARTIFACT_DIR / "transform.joblib"
UMAP_META_PATH = UMAP_ARTIFACT_DIR / "meta.json"

# Cluster RNA centroids on the METABRIC reference-z scale.
CLUSTER_CENTROIDS_PATH = ARTIFACT_DIR / "cluster_rna_centroids.parquet"

# Versioned human-development-status compound registry (display gating only).
COMPOUND_REGISTRY_VERSION = os.environ.get("COMPOUND_REGISTRY_VERSION", "v1")
COMPOUND_REGISTRY_DIR = _env_path(
    "COMPOUND_REGISTRY_DIR",
    REPO_ROOT / "outputs" / "compound_registry" / COMPOUND_REGISTRY_VERSION,
)
COMPOUND_REGISTRY_PATH = COMPOUND_REGISTRY_DIR / "compound_registry.json"
COMPOUND_REGISTRY_PARQUET = COMPOUND_REGISTRY_DIR / "compound_registry.parquet"
COMPOUND_REGISTRY_MANIFEST = COMPOUND_REGISTRY_DIR / "manifest.json"
COMPOUND_REVIEW_QUEUE_DIR = _env_path(
    "COMPOUND_REVIEW_QUEUE_DIR",
    REPO_ROOT / "outputs" / "compound_registry" / "review_queue",
)

# Sanitized, precomputed public-demo analysis payloads (no expression).
PUBLIC_DEMO_BUNDLE_DIR = _env_path(
    "PUBLIC_DEMO_BUNDLE_DIR", ARTIFACT_DIR / "public_demo_bundle" / "v1"
)

for _p in (
    ARTIFACT_DIR,
    SYNTHETIC_PATIENTS_DIR,
    DB_PATH.parent,
    COMPACT_GCTX_DIR,
    UMAP_ARTIFACT_DIR,
    COMPOUND_REGISTRY_DIR,
    COMPOUND_REVIEW_QUEUE_DIR,
    PUBLIC_DEMO_BUNDLE_DIR,
):
    _p.mkdir(parents=True, exist_ok=True)
