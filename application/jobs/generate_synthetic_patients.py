"""Generate and persist the three synthetic demonstration patients.

Usage:
    python jobs/generate_synthetic_patients.py

Writes one JSON file per patient under SYNTHETIC_PATIENTS_DIR plus an
``index.json`` summary (no expression payload) for fast listing endpoints.
"""

from __future__ import annotations

import json

from pipeline_core.config import SYNTHETIC_PATIENTS_DIR
from pipeline_core.synthetic_patient import generate_synthetic_patients


def main() -> None:
    patients = generate_synthetic_patients()
    index = []
    for patient in patients:
        path = SYNTHETIC_PATIENTS_DIR / f"{patient.synthetic_id}.json"
        path.write_text(
            json.dumps(
                {
                    "synthetic_id": patient.synthetic_id,
                    "scenario": patient.scenario,
                    "description": patient.description,
                    "expression": patient.expression,
                    "metadata": patient.metadata,
                    "administered_regimen": patient.administered_regimen,
                    "ground_truth": patient.ground_truth,
                },
                indent=2,
            )
        )
        print(f"Wrote {patient.scenario} -> {path} ({len(patient.expression)} genes)")
        index.append(
            {
                "synthetic_id": patient.synthetic_id,
                "scenario": patient.scenario,
                "description": patient.description,
                "metadata": patient.metadata,
                "administered_regimen": patient.administered_regimen,
            }
        )

    index_path = SYNTHETIC_PATIENTS_DIR / "index.json"
    index_path.write_text(json.dumps(index, indent=2))
    print(f"Wrote index -> {index_path}")


if __name__ == "__main__":
    main()
