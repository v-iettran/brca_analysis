"""Load held-out TCGA demo payloads and drive the v2 prototype stages."""

from __future__ import annotations

import json
from pathlib import Path

from app.services.v3_prototype import load_v3_bundle

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _payloads() -> dict:
    path = DATA_DIR / "demo_payloads.json"
    if not path.exists():
        return {"patients": {}}
    return json.loads(path.read_text())


def _manifest() -> dict:
    path = DATA_DIR / "demo_patients.json"
    if not path.exists():
        return {"patients": []}
    return json.loads(path.read_text())


def list_demo_patients() -> list[dict]:
    return list(_manifest().get("patients") or [])


def is_demo_patient(patient_id: str | None) -> bool:
    if not patient_id:
        return False
    known = {row["patient_id"] for row in list_demo_patients()}
    return str(patient_id) in known or str(patient_id)[:12] in known


def load_demo_payload(patient_id: str) -> dict:
    patients = _payloads().get("patients") or {}
    if patient_id in patients:
        return patients[patient_id]
    prefix = patient_id[:12]
    for key, row in patients.items():
        if key[:12] == prefix:
            return row
    raise KeyError(f"Unknown demo patient {patient_id!r}")


def load_glossary() -> dict:
    path = DATA_DIR / "glossary.json"
    if not path.exists():
        return {"entries": []}
    return json.loads(path.read_text())


def cluster_prediction_from_prototype(payload: dict) -> dict:
    pos = payload.get("position") or {}
    cluster = pos.get("cluster") or {}
    label = int(cluster.get("label") or 0)
    mass = float(cluster.get("posterior_mass") or 0)
    state = int(payload.get("state") or 1)
    confidence = {1: "high", 2: "moderate", 3: "abstain"}.get(state, "low")
    return {
        "probabilities": {str(label): mass},
        "top_cluster": label,
        "top_probability": mass,
        "confidence_level": confidence,
        "gene_coverage": 1.0 if "rna" in (payload.get("modalities_present") or []) else 0.0,
        "genes_found": 1,
        "genes_requested": 1,
        "method_used": "signature_similarity",
        "warnings": [payload["banner"]] if payload.get("banner") else [],
    }


def result_fields_from_prototype(payload: dict) -> dict:
    abstained = bool((payload.get("abstention") or {}).get("abstained"))
    v3_cohort, v3_patient = load_v3_bundle(str(payload.get("patient_id") or ""))
    schema = "v3_cluster" if v3_patient else "v2_prototype"
    return {
        "schema_version": schema,
        "prototype": payload,
        "v3_cohort": v3_cohort,
        "v3_patient": v3_patient,
        "cluster_prediction": cluster_prediction_from_prototype(payload),
        "analysis_summary": {
            "top_cluster": (payload.get("position") or {}).get("cluster", {}).get("label"),
            "top_probability": (payload.get("position") or {}).get("cluster", {}).get("posterior_mass"),
            "confidence_level": "abstain" if abstained else "high",
            "headline_nominations": [],
            "dominant_uncertainty": (payload.get("abstention") or {}).get("reason_text")
            or payload.get("banner")
            or "Subgroups are chosen from molecular structure. Survival is tested separately.",
        },
        "limitations": payload.get("limitations") or (v3_patient or {}).get("limitations") or [],
        "top_candidate_drugs": [],
        "overlap_nominations": [],
        "almanac_combinations": [],
        "list1_drugs": [],
        "list2_drugs": [],
        "s4_ships": False,
    }
