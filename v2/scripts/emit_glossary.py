"""One-shot glossary from the latest record of each (notebook, gate) in gates.jsonl."""

from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))
from paths import resolve_v2_root

# Cut stages get no panel entry.
PANEL_GATES = {
    ("NB02", "purity_concordance"): {
        "panel": "sample_quality",
        "plain_language": "Estimates how much of the biopsy is tumour versus surrounding tissue.",
        "method": "BayesPrism deconvolution against a breast single-cell reference",
        "known_limitations": [
            "Breast subtype affects accuracy — normal epithelium can be mis-assigned as cancer.",
        ],
        "reference": "Chu et al., Nature Cancer 2022",
    },
    ("NB04", "vae_vs_mofa_heldout_nll"): {
        "panel": "position",
        "plain_language": "Places this tumour among other breast tumours, with a visible uncertainty region.",
        "method": "Product-of-experts VAE on RNA, CNA, and methylation",
        "known_limitations": [
            "Missing assays widen the ellipse; the point estimate is not a subtype call.",
        ],
        "reference": "Wu & Goodman, NeurIPS 2018",
    },
    ("NB05", "abstention_rate_full_view"): {
        "panel": "abstention",
        "plain_language": "Says when the model should not produce a drug set.",
        "method": "Posterior-width threshold calibrated on held-out full-view samples",
        "known_limitations": [
            "Thresholds are on latent width, not classifier confidence.",
        ],
        "reference": None,
    },
    ("NB06", "estrogen_er_positive_control"): {
        "panel": "molecular_state",
        "plain_language": "Summarises pathway and transcription-factor activity from the tumour RNA.",
        "method": "PROGENy pathways and CollecTRI transcription factors",
        "known_limitations": [
            "Activity scores are relative to the cohort, not clinical IHC.",
        ],
        "reference": "Schubert et al., Nat Commun 2018; Müller-Dott et al., 2023",
    },
    ("NB13", "conformal_coverage_90"): {
        "panel": "prediction_set",
        "plain_language": "A set of agents consistent with the molecular profile — not a ranked recommendation.",
        "method": "Cross-conformal regression on SCAN-B observed survival events; set membership from target-pathway activity",
        "known_limitations": [
            "Endocrine-treatment assignment was dropped from the model after an ER+ refit showed it dominated the weights.",
            "Molecular signal is weak; wider sets are more honest than a short ranked list.",
        ],
        "reference": None,
    },
}


def latest_gates(path: Path) -> dict[tuple[str, str], dict]:
    latest: dict[tuple[str, str], dict] = {}
    if not path.exists():
        return latest
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        latest[(rec["notebook"], rec["gate"])] = rec
    return latest


def revision_note(rec: dict) -> tuple[bool, str | None]:
    note = str(rec.get("note") or "")
    if "revised" in note.lower() or "threshold revised" in note.lower():
        return True, note
    return False, None


def main() -> Path:
    root = resolve_v2_root()
    latest = latest_gates(root / "reports" / "gates.jsonl")
    entries = []
    for key, meta in PANEL_GATES.items():
        rec = latest.get(key)
        if rec is None:
            continue
        revised, rev_note = revision_note(rec)
        entries.append(
            {
                **meta,
                "validation": {
                    "metric": rec["gate"],
                    "value": rec.get("value"),
                    "n": rec.get("n"),
                    "threshold": rec.get("threshold"),
                    "status": rec.get("status") or ("pass" if rec.get("passed") else "fail"),
                    "revised": revised,
                    "revision_note": rev_note,
                },
            }
        )
    out = root / "data" / "reference" / "glossary.json"
    out.write_text(json.dumps({"generated_from": "reports/gates.jsonl", "entries": entries}, indent=2))
    print("wrote", out, "n=", len(entries))
    return out


if __name__ == "__main__":
    main()
