#!/usr/bin/env bash
# Package runtime artifacts for sharing (excludes local DB and export cache).
#
# Usage (from anywhere):
#   ./application/scripts/package_copilot_artifacts.sh
#   ./application/scripts/package_copilot_artifacts.sh /path/to/copilot_artifacts_bundle.tar.gz
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
ARTIFACTS_DIR="${REPO_ROOT}/outputs/copilot_artifacts"
DEFAULT_OUT="${REPO_ROOT}/copilot_artifacts_bundle.tar.gz"
OUT="${1:-${DEFAULT_OUT}}"

if [[ ! -d "${ARTIFACTS_DIR}" ]]; then
  echo "error: artifacts directory not found: ${ARTIFACTS_DIR}" >&2
  exit 1
fi

required=(
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
  "compact_gctx/breast_trt_cp_matrix.parquet"
  "compact_gctx/breast_trt_cp_signatures.parquet"
)

missing=()
for rel in "${required[@]}"; do
  if [[ ! -e "${ARTIFACTS_DIR}/${rel}" ]]; then
    missing+=("${rel}")
  fi
done

if (( ${#missing[@]} > 0 )); then
  echo "error: cannot package — missing required files:" >&2
  printf '  - %s\n' "${missing[@]}" >&2
  echo "Run application/scripts/setup_copilot_artifacts.sh build first." >&2
  exit 1
fi

tmp_manifest="$(mktemp)"
trap 'rm -f "${tmp_manifest}"' EXIT

(
  cd "${ARTIFACTS_DIR}"
  find . -type f \
    ! -path './exports/*' \
    ! -name 'copilot.db' \
    ! -name '.DS_Store' \
    ! -name 'MANIFEST.sha256' \
    | LC_ALL=C sort \
    | while IFS= read -r path; do
        # strip leading ./
        rel="${path#./}"
        shasum -a 256 "${rel}"
      done
) > "${tmp_manifest}"

cp "${tmp_manifest}" "${ARTIFACTS_DIR}/MANIFEST.sha256"

echo "Creating bundle: ${OUT}"
COPYFILE_DISABLE=1 tar czf "${OUT}" \
  --exclude='copilot_artifacts/exports' \
  --exclude='copilot_artifacts/copilot.db' \
  --exclude='.DS_Store' \
  -C "${REPO_ROOT}/outputs" \
  copilot_artifacts

bytes="$(wc -c < "${OUT}" | tr -d ' ')"
echo "Done."
echo "  archive: ${OUT}"
echo "  size:    $(numfmt --to=iec-i --suffix=B "${bytes}" 2>/dev/null || echo "${bytes} bytes")"
echo "  manifest: outputs/copilot_artifacts/MANIFEST.sha256"
echo ""
echo "Share the .tar.gz with your collaborator, then they run:"
echo "  ./application/scripts/setup_copilot_artifacts.sh install ${OUT}"
