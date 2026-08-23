"""Build a sanitized, precomputed public-demo analysis bundle.

Runs the scientific pipeline offline for each synthetic patient when
artifacts are present, then writes expression-free payloads. Use
``--stub-only`` to write metadata-only fixtures for tests or CI without
compact GCTX.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from pipeline_core.cluster_model import ClusterClassifierArtifact
from pipeline_core.config import (
    COMPOUND_REGISTRY_MANIFEST,
    COMPOUND_REGISTRY_VERSION,
    PUBLIC_DEMO_BUNDLE_DIR,
    SYNTHETIC_PATIENTS_DIR,
)
from pipeline_core.display_gating import apply_display_gating
from pipeline_core.drug_names import normalize_drug_name

_API_DIR = Path(__file__).resolve().parents[1] / "apps" / "api"
if str(_API_DIR) not in sys.path:
    sys.path.insert(0, str(_API_DIR))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _stub_result(item: dict) -> dict:
    cluster = 2 if item["scenario"] == "high_confidence" else 1 if item["scenario"] == "mixed_cluster" else 0
    confidence = {"high_confidence": "high", "mixed_cluster": "low", "low_quality": "abstain"}[item["scenario"]]
    probability = {"high_confidence": 0.82, "mixed_cluster": 0.38, "low_quality": 0.22}[item["scenario"]]
    paclitaxel = {
        "drug": "paclitaxel",
        "canonical": "paclitaxel",
        "list1_percentile": 0.91,
        "list2_percentile": 0.84,
        "weaker_percentile": 0.84,
        "stronger_percentile": 0.91,
        "rank_product": 12.0,
        "list1_rank": 4,
        "list2_rank": 7,
        "targets": ["TUBB"],
        "evidence_tier": "tier_b_breast_context",
        "indication_bucket": "standard_breast_context",
        "is_in_administered_regimen": True,
        "nomination_rank": 1,
        "support_class": "breast_cell_line_supported",
        "support_rank": 1,
        "robustness": {"likely_artifact": False, "notes": []},
        "q2_annotation": {"evidence_category": "exploratory", "genes_used": 40},
    }
    brd = {
        "drug": "BRD-K12345678",
        "canonical": "brd-k12345678",
        "list1_percentile": 0.99,
        "list2_percentile": 0.97,
        "weaker_percentile": 0.97,
        "stronger_percentile": 0.99,
        "rank_product": 2.0,
        "list1_rank": 1,
        "list2_rank": 2,
        "targets": [],
        "evidence_tier": "tier_d_artifact_or_insufficient",
        "indication_bucket": "unclassified_or_investigational",
        "is_in_administered_regimen": False,
        "nomination_rank": 2,
        "support_class": "suggestive",
        "support_rank": 2,
        "robustness": {"likely_artifact": False, "notes": []},
    }
    gated = apply_display_gating([paclitaxel, brd] if item["scenario"] != "low_quality" else [])
    limitations = [
        "Cluster signatures are one-vs-rest among METABRIC tumours; there is no normal-breast reference.",
        "Human-development labels are regulatory snapshots for presentation only, not patient suitability.",
    ]
    return {
        "schema_version": "v2",
        "patient_metadata": item.get("metadata") or {},
        "administered_regimen": item.get("administered_regimen") or [],
        "signature_params": {"top_up": 150, "top_down": 150},
        "cluster_prediction": {
            "probabilities": {str(cluster): probability, str((cluster + 1) % 5): round(1 - probability, 2)},
            "top_cluster": cluster,
            "top_probability": probability,
            "confidence_level": confidence,
            "gene_coverage": 0.11 if item["scenario"] == "low_quality" else 0.94,
            "genes_found": 180 if item["scenario"] != "low_quality" else 40,
            "genes_requested": 200,
            "method_used": "signature_similarity",
            "warnings": ["Low gene coverage"] if item["scenario"] == "low_quality" else [],
        },
        "overlap_nominations": gated["visible"],
        "overlap_exploratory": gated["exploratory"],
        "overlap_technical_excluded": gated["technical_excluded"],
        "display_gate_summary": gated["gate_summary"],
        "compound_registry_version": gated["registry_version"],
        "analysis_summary": {
            "top_cluster": cluster,
            "top_probability": probability,
            "confidence_level": confidence,
            "headline_nominations": [
                {
                    "drug": row.get("drug"),
                    "human_development_label": row.get("human_development_label"),
                    "weaker_percentile": row.get("weaker_percentile"),
                    "display_gate_reason": row.get("display_gate_reason"),
                }
                for row in gated["visible"][:3]
            ],
            "dominant_uncertainty": limitations[0],
        },
        "clinical_comparators": [],
        "predictor_single_drugs": [],
        "predictor_combinations": [],
        "predictor_summary": {"role": "parallel_clinical_context_not_nomination"},
        "near_consensus": [],
        "overlap_summary": {"n_overlap": len(gated["visible"]) + len(gated["exploratory"]) + len(gated["technical_excluded"])},
        "almanac_combinations": [],
        "list1_drugs": [],
        "list2_drugs": [],
        "administered_regimen_pcr": None,
        "top_candidate_drugs": gated["visible"],
        "limitations": limitations,
        "precomputed": True,
        "stub": True,
    }


def _run_live(item: dict) -> dict:
    from app.db import SessionLocal, init_db
    from app.schemas.patient import PatientMetadata, PatientProfileIn
    from app.services.analysis_service import run_analysis

    path = SYNTHETIC_PATIENTS_DIR / f"{item['synthetic_id']}.json"
    data = json.loads(path.read_text())
    data.pop("ground_truth", None)
    profile = PatientProfileIn(
        patient_label=data["synthetic_id"],
        expression=data["expression"],
        metadata=PatientMetadata.model_validate(data.get("metadata") or {}),
        administered_regimen=[
            normalize_drug_name(name) for name in data.get("administered_regimen") or []
        ],
    )
    init_db()
    db = SessionLocal()
    try:
        run = run_analysis(db, profile, session_id="public-demo-build")
        payload = dict(run.result_payload or {})
        payload["patient_metadata"] = run.patient_metadata
        payload["administered_regimen"] = run.administered_regimen
        payload["precomputed"] = True
        payload["stub"] = False
        return payload
    finally:
        db.close()


def build_bundle(stub_only: bool = False) -> dict:
    from app.services.demo_bundle import write_bundle_payload
    from app.services.demo_guard import list_synthetic_index

    patients = list_synthetic_index()
    if not patients:
        raise FileNotFoundError("No synthetic patients found.")
    PUBLIC_DEMO_BUNDLE_DIR.mkdir(parents=True, exist_ok=True)
    written = []
    for item in patients:
        synthetic_id = item["synthetic_id"]
        used_stub = stub_only
        if not stub_only:
            try:
                ClusterClassifierArtifact.load()
                result = _run_live(item)
            except Exception:
                result = _stub_result(item)
                used_stub = True
        else:
            result = _stub_result(item)
        path = write_bundle_payload(
            synthetic_id,
            result,
            extra={
                "scenario": item.get("scenario"),
                "description": item.get("description"),
                "stub": used_stub,
            },
        )
        written.append({"synthetic_id": synthetic_id, "path": str(path), "stub": used_stub})

    checksums = {
        f"{row['synthetic_id']}.json": _sha256(PUBLIC_DEMO_BUNDLE_DIR / f"{row['synthetic_id']}.json")
        for row in written
    }
    classifier_version = None
    try:
        classifier_version = ClusterClassifierArtifact.load().version
    except Exception:
        classifier_version = None
    registry_manifest = {}
    if COMPOUND_REGISTRY_MANIFEST.exists():
        registry_manifest = json.loads(COMPOUND_REGISTRY_MANIFEST.read_text())
    manifest = {
        "bundle_version": "v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "patients": [row["synthetic_id"] for row in written],
        "stub": all(row["stub"] for row in written),
        "classifier_version": classifier_version,
        "compound_registry_version": registry_manifest.get("registry_version") or COMPOUND_REGISTRY_VERSION,
        "checksums": checksums,
        "note": "Sanitized public demo payloads. Expression, METABRIC, and GCTX are absent.",
    }
    (PUBLIC_DEMO_BUNDLE_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stub-only", action="store_true")
    args = parser.parse_args()
    print(json.dumps(build_bundle(stub_only=args.stub_only), indent=2))


if __name__ == "__main__":
    main()
