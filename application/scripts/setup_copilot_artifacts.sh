#!/usr/bin/env bash
# Install, verify, or build MOFA Copilot runtime artifacts.
#
# Usage:
#   ./application/scripts/setup_copilot_artifacts.sh              # check status
#   ./application/scripts/setup_copilot_artifacts.sh check
#   ./application/scripts/setup_copilot_artifacts.sh install BUNDLE.tar.gz
#   ./application/scripts/setup_copilot_artifacts.sh install --url https://example.com/copilot_artifacts_bundle.tar.gz
#   ./application/scripts/setup_copilot_artifacts.sh build          # from METABRIC (core only)
#   ./application/scripts/setup_copilot_artifacts.sh build --with-gctx
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_ROOT="$(cd "${APP_DIR}/.." && pwd)"
ARTIFACTS_DIR="${REPO_ROOT}/outputs/copilot_artifacts"
VENV_DIR="${REPO_ROOT}/.venv_copilot"

REQUIRED=(
  "metabric_expression_cache.parquet"
  "metabric_gene_reference_stats.parquet"
  "cluster_classifier_artifact.json"
  "cluster_rna_centroids.parquet"
  "q2_drug_score_reference_stats.parquet"
  "predictor_q2_reference_scores_v1.parquet"
  "synthetic_patients/index.json"
  "rna_umap/meta.json"
  "rna_umap/reference_coordinates.parquet"
  "rna_umap/transform.joblib"
)

OPTIONAL=(
  "compact_gctx/breast_trt_cp_matrix.parquet"
  "compact_gctx/breast_trt_cp_signatures.parquet"
)

usage() {
  sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//'
}

ensure_artifacts_dir() {
  mkdir -p "${ARTIFACTS_DIR}"
}

check_status() {
  ensure_artifacts_dir
  local ok=0
  echo "Artifact directory: ${ARTIFACTS_DIR}"
  echo ""
  echo "Required:"
  for rel in "${REQUIRED[@]}"; do
    if [[ -e "${ARTIFACTS_DIR}/${rel}" ]]; then
      echo "  [ok] ${rel}"
    else
      echo "  [missing] ${rel}"
      ok=1
    fi
  done
  echo ""
  echo "Optional (full List 1 / List 2 GCTX scoring):"
  for rel in "${OPTIONAL[@]}"; do
    if [[ -e "${ARTIFACTS_DIR}/${rel}" ]]; then
      echo "  [ok] ${rel}"
    else
      echo "  [missing] ${rel}"
    fi
  done
  echo ""
  if [[ -f "${ARTIFACTS_DIR}/MANIFEST.sha256" ]]; then
    echo "Manifest present — run 'verify' to checksum files."
  fi
  if [[ ${ok} -eq 0 ]]; then
    echo "Status: ready to run the app."
    return 0
  fi
  echo "Status: not ready."
  echo "Install a shared bundle:"
  echo "  $0 install /path/to/copilot_artifacts_bundle.tar.gz"
  echo "Or build locally (needs METABRIC at ../final-project/brca_metabric/):"
  echo "  $0 build"
  return 1
}

verify_manifest() {
  if [[ ! -f "${ARTIFACTS_DIR}/MANIFEST.sha256" ]]; then
    echo "warning: MANIFEST.sha256 not found — skipping checksum verification." >&2
    return 0
  fi
  echo "Verifying checksums..."
  (
    cd "${ARTIFACTS_DIR}"
    shasum -a 256 -c MANIFEST.sha256
  )
}

install_bundle() {
  local source_path="${1:-}"
  local from_url=""

  if [[ "${source_path}" == "--url" ]]; then
    from_url="${2:-}"
    if [[ -z "${from_url}" ]]; then
      echo "error: --url requires a download URL" >&2
      exit 1
    fi
    source_path="$(mktemp /tmp/copilot_artifacts_bundle.XXXXXX.tar.gz)"
    trap '[[ -n "${from_url}" ]] && rm -f "${source_path}"' RETURN
    echo "Downloading ${from_url} ..."
    curl -fL --progress-bar -o "${source_path}" "${from_url}"
  fi

  if [[ -z "${source_path}" || ! -f "${source_path}" ]]; then
    echo "error: bundle not found: ${source_path}" >&2
    exit 1
  fi

  ensure_artifacts_dir
  echo "Extracting ${source_path} -> ${REPO_ROOT}/outputs/"
  tar xzf "${source_path}" -C "${REPO_ROOT}/outputs"
  verify_manifest || true
  check_status
}

activate_venv() {
  if [[ ! -d "${VENV_DIR}" ]]; then
    echo "Creating virtualenv at ${VENV_DIR}"
    python3 -m venv "${VENV_DIR}"
  fi
  # shellcheck disable=SC1091
  source "${VENV_DIR}/bin/activate"
  pip install -q -e "${APP_DIR}/packages/pipeline_core"
  pip install -q -r "${APP_DIR}/apps/api/requirements.txt"
}

build_artifacts() {
  local with_gctx="false"
  if [[ "${1:-}" == "--with-gctx" ]]; then
    with_gctx="true"
  fi

  activate_venv
  cd "${APP_DIR}"

  echo "Building core artifacts (classifier, synthetic patients, RNA projection)..."
  python3 jobs/train_cluster_classifier.py
  python3 jobs/generate_synthetic_patients.py
  python3 jobs/build_rna_projection_artifacts.py

  # Warm caches used at runtime (predictor reference + Q2 reference stats).
  python3 - <<'PY'
from pipeline_core.expression import load_metabric_expression, reference_gene_stats
from pipeline_core.predictor_evidence import load_predictor_reference_scores
from pipeline_core.q2_evidence import _compute_drug_score_reference_stats

load_metabric_expression()
reference_gene_stats()
load_predictor_reference_scores()
_compute_drug_score_reference_stats()
print("Warmed expression, Q2, and predictor reference caches.")
PY

  if [[ "${with_gctx}" == "true" ]]; then
    echo "Building compact GCTX artifact (slow; needs 33 GB GCTX file)..."
    python3 jobs/build_compact_gctx_artifact.py
  else
    echo ""
    echo "Skipped compact GCTX (pass --with-gctx to build List 1 / List 2 scoring tables)."
    echo "The app still runs without it, but overlap scoring is limited."
  fi

  check_status
}

cmd="${1:-check}"
shift || true

case "${cmd}" in
  check|status)
    check_status
    ;;
  verify)
    verify_manifest
    ;;
  install)
    if [[ "${1:-}" == "--url" ]]; then
      install_bundle --url "${2:-}"
    else
      install_bundle "${1:-}"
    fi
    ;;
  build)
    build_artifacts "${1:-}"
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    echo "error: unknown command '${cmd}'" >&2
    usage
    exit 1
    ;;
esac
