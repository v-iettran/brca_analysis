"""Versioned v3 cohort/patient payload contract and validation."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Iterable

from safety import assert_safe

SCHEMA_VERSION = "v3_cluster"
PREREGISTERED_METHOD = "gmm"
PREREGISTERED_COVARIANCE = "full"

UNSAFE_ENCODER_NLL = {"linear_poe"}


def walk_strings(obj: Any) -> Iterable[str]:
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for value in obj.values():
            yield from walk_strings(value)
    elif isinstance(obj, (list, tuple)):
        for value in obj:
            yield from walk_strings(value)


def assert_payload_safe(payload: dict, context: str) -> None:
    for text in walk_strings(payload):
        assert_safe(text, context=context)


def config_is_exploratory(config: dict, preregistered: dict | None) -> bool:
    if not preregistered or preregistered.get("k") is None:
        return True
    return not (
        config.get("method") == PREREGISTERED_METHOD
        and config.get("covariance_type") == PREREGISTERED_COVARIANCE
        and int(config.get("k") or -1) == int(preregistered["k"])
    )


def validate_cohort(cohort: dict) -> list[str]:
    errors = []
    if cohort.get("schema_version") != SCHEMA_VERSION:
        errors.append("schema_version")
    if "encoder" not in cohort:
        errors.append("encoder")
    clustering = bool(cohort.get("clustering_available", True))
    configs = cohort.get("configurations") or {}
    preg = cohort.get("preregistered") or {}
    if clustering:
        if not preg.get("k"):
            errors.append("preregistered.k")
        preg_id = None
        for cid, cfg in configs.items():
            exploratory = bool(cfg.get("exploratory"))
            expected = config_is_exploratory(cfg, preg)
            if exploratory != expected:
                errors.append(f"exploratory_mismatch:{cid}")
            km = cfg.get("km") or {}
            for endpoint, block in km.items():
                if block.get("p_value") is not None and exploratory:
                    errors.append(f"p_value_on_exploratory:{cid}:{endpoint}")
                if (not exploratory) and "p_value" not in block:
                    errors.append(f"missing_preregistered_p:{cid}:{endpoint}")
            if not expected:
                preg_id = cid
        if preg_id is None and configs:
            errors.append("missing_preregistered_config")
    else:
        if preg.get("k") not in (None, 0):
            errors.append("k_forced_without_structure")
    return errors


def validate_patient(patient: dict, cohort: dict | None = None) -> list[str]:
    errors = []
    if patient.get("schema_version") != SCHEMA_VERSION:
        errors.append("schema_version")
    if not patient.get("patient_id"):
        errors.append("patient_id")
    state = int(patient.get("state") or 1)
    abstained = bool((patient.get("abstention") or {}).get("abstained"))
    if state == 3 and not abstained:
        errors.append("state3_without_abstention")
    if state == 3:
        if patient.get("reversal_candidates"):
            errors.append("state3_has_reversal")
        if patient.get("prognostic_estimate"):
            errors.append("state3_has_prognostic")
        if patient.get("nearest_lines"):
            errors.append("state3_has_nearest_lines")
    if cohort and patient.get("encoder") != cohort.get("encoder"):
        errors.append("encoder_mismatch")
    gates = (cohort or {}).get("gates") or {}
    if gates.get("a4") and not gates["a4"].get("passed"):
        if patient.get("reversal_candidates"):
            errors.append("reversal_present_after_a4_fail")
    return errors


def glossary_allows_nll(encoder: str) -> bool:
    return encoder not in UNSAFE_ENCODER_NLL


def application_data_dir(repo_root: Path) -> Path:
    return Path(repo_root) / "application" / "apps" / "api" / "app" / "data"


def v3_interim(v2_root: Path) -> Path:
    path = Path(v2_root) / "data" / "interim" / "v3"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _json_safe(value):
    """Replace non-finite floats with null.

    `json.dumps` emits bare `NaN` and `Infinity`, which Python reads back but
    which are not valid JSON: a browser's `JSON.parse`, `jq`, and any strict
    validator all reject them. FastAPI happens to sanitise these on the way out,
    so the running app never showed it, but the artifact on disk was unreadable
    to every non-Python consumer.
    """
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return value


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_json_safe(payload), indent=2, allow_nan=False))


def copy_payloads_to_app(cohort: dict, patients: dict[str, dict], repo_root: Path) -> Path:
    dest = application_data_dir(repo_root) / "v3"
    dest.mkdir(parents=True, exist_ok=True)
    write_json(dest / "cohort_payload.json", cohort)
    for pid, payload in patients.items():
        write_json(dest / f"payload_{pid}.json", payload)
    write_json(dest / "demo_payloads_v3.json", {"cohort": cohort, "patients": patients})
    return dest
