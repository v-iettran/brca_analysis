"""JSON/CSV/PDF export of a completed analysis run.

The PDF is a print-ready clinician report; JSON/CSV are the full technical
audit export. All three carry the same persistent "research prototype, not a
clinical device" banner text.
"""

from __future__ import annotations

import csv
import datetime as dt
import json
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from pipeline_core.config import ARTIFACT_DIR

from app.models_orm import AnalysisRun

EXPORT_DIR = ARTIFACT_DIR / "exports"
EXPORT_DIR.mkdir(parents=True, exist_ok=True)

BANNER_TEXT = (
    "RESEARCH PROTOTYPE — NOT A CLINICAL DECISION-SUPPORT DEVICE. All evidence is "
    "exploratory and must be independently reviewed by a qualified clinician."
)


def export_json(run: AnalysisRun) -> Path:
    payload = {
        "banner": BANNER_TEXT,
        "run_id": run.run_id,
        "status": run.status,
        "created_at": run.created_at.isoformat(),
        "patient_label": run.patient_label,
        "patient_metadata": run.patient_metadata,
        "administered_regimen": run.administered_regimen,
        "classifier_method": run.classifier_method,
        "classifier_version": run.classifier_version,
        "revision": int(run.revision or 0),
        "signature_params": {
            "top_up": run.signature_top_up,
            "top_down": run.signature_top_down,
        },
        "warnings": [{"severity": w.severity, "message": w.message} for w in run.warnings],
        "audit_events": [
            {
                "tool_name": e.tool_name,
                "input_summary": e.input_summary,
                "output_summary": e.output_summary,
                "duration_ms": e.duration_ms,
                "created_at": e.created_at.isoformat(),
            }
            for e in run.audit_events
        ],
        "result": run.result_payload,
    }
    path = EXPORT_DIR / f"{run.run_id}.json"
    path.write_text(json.dumps(payload, indent=2, default=str))
    return path


def export_csv(run: AnalysisRun) -> Path:
    path = EXPORT_DIR / f"{run.run_id}_overlap_nominations.csv"
    result = run.result_payload or {}
    nominations = result.get("overlap_nominations") or result.get("top_candidate_drugs") or []
    fieldnames = [
        "nomination_rank",
        "drug",
        "canonical",
        "list1_percentile",
        "list2_percentile",
        "weaker_percentile",
        "rank_product",
        "evidence_tier",
        "indication_bucket",
        "targets",
        "is_in_administered_regimen",
        "likely_artifact",
        "generic_stress_pattern",
        "missing_target_pathway_support",
        "q2_evidence_category",
        "q2_percentile",
        "literature_retrieved_count",
        "literature_dominant_stance",
        "human_development_status",
        "human_development_label",
        "display_action",
        "display_gate_reason",
        "registry_match_key",
        "compound_registry_version",
        "revision",
        "top_up",
        "top_down",
    ]
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for candidate in nominations:
            q2 = candidate.get("q2_annotation") or candidate.get("q2_evidence") or {}
            lit = candidate.get("literature_summary") or {}
            robustness = candidate.get("robustness") or {}
            writer.writerow(
                {
                    "nomination_rank": candidate.get("nomination_rank"),
                    "drug": candidate.get("drug"),
                    "canonical": candidate.get("canonical"),
                    "list1_percentile": candidate.get("list1_percentile"),
                    "list2_percentile": candidate.get("list2_percentile"),
                    "weaker_percentile": candidate.get("weaker_percentile"),
                    "rank_product": candidate.get("rank_product"),
                    "evidence_tier": candidate.get("evidence_tier"),
                    "indication_bucket": candidate.get("indication_bucket"),
                    "targets": ";".join(candidate.get("targets") or []),
                    "is_in_administered_regimen": candidate.get("is_in_administered_regimen"),
                    "likely_artifact": robustness.get("likely_artifact"),
                    "generic_stress_pattern": robustness.get("generic_stress_pattern"),
                    "missing_target_pathway_support": robustness.get("missing_target_pathway_support"),
                    "q2_evidence_category": q2.get("evidence_category"),
                    "q2_percentile": q2.get("sensitivity_percentile") or q2.get("z_score"),
                    "literature_retrieved_count": lit.get("retrieved_relevant_references"),
                    "literature_dominant_stance": lit.get("dominant_stance"),
                    "human_development_status": candidate.get("human_development_status"),
                    "human_development_label": candidate.get("human_development_label"),
                    "display_action": candidate.get("display_action"),
                    "display_gate_reason": candidate.get("display_gate_reason"),
                    "registry_match_key": candidate.get("registry_match_key"),
                    "compound_registry_version": result.get("compound_registry_version"),
                    "revision": int(run.revision or 0),
                    "top_up": (result.get("signature_params") or {}).get("top_up") or run.signature_top_up,
                    "top_down": (result.get("signature_params") or {}).get("top_down") or run.signature_top_down,
                }
            )

    # Secondary CSV for ALMANAC combinations.
    combo_path = EXPORT_DIR / f"{run.run_id}_almanac_combinations.csv"
    combos = result.get("almanac_combinations") or []
    with combo_path.open("w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "combination",
                "drug_a",
                "drug_b",
                "aligned_cell_lines",
                "aligned_pair_support",
                "component_support",
                "combination_priority",
                "interpretation",
            ],
        )
        writer.writeheader()
        for combo in combos:
            writer.writerow({k: combo.get(k) for k in writer.fieldnames})

    comparator_path = EXPORT_DIR / f"{run.run_id}_clinical_comparator_context.csv"
    comparators = result.get("clinical_comparators") or []
    comparator_fields = [
        "drug",
        "category",
        "list1_rank",
        "list2_rank",
        "list1_percentile",
        "list2_percentile",
        "evidence_concordance",
        "reference_cohort_sensitivity_percentile",
        "q2_model_reliability",
        "q4_drug_support",
        "integrated_single_drug_priority",
        "within_patient_predictor_rank",
        "predictor_version",
    ]
    with comparator_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=comparator_fields)
        writer.writeheader()
        for comparator in comparators:
            predictor = comparator.get("predictor_evidence") or {}
            writer.writerow(
                {
                    "drug": comparator.get("drug"),
                    "category": comparator.get("category"),
                    "list1_rank": comparator.get("list1_rank"),
                    "list2_rank": comparator.get("list2_rank"),
                    "list1_percentile": comparator.get("list1_percentile"),
                    "list2_percentile": comparator.get("list2_percentile"),
                    "evidence_concordance": comparator.get("evidence_concordance"),
                    **{
                        field: predictor.get(field)
                        for field in comparator_fields
                        if field
                        in {
                            "reference_cohort_sensitivity_percentile",
                            "q2_model_reliability",
                            "q4_drug_support",
                            "integrated_single_drug_priority",
                            "within_patient_predictor_rank",
                            "predictor_version",
                        }
                    },
                }
            )

    predictor_combo_path = EXPORT_DIR / f"{run.run_id}_predictor_combinations.csv"
    predictor_combos = result.get("predictor_combinations") or []
    predictor_combo_fields = [
        "rank",
        "combination",
        "drug_a",
        "drug_b",
        "component_drug_priority",
        "aligned_pair_support",
        "pair_q4_support",
        "integrated_combination_priority",
        "aligned_cell_lines",
        "cell_line_alignment_confidence",
        "predictor_version",
        "interpretation",
    ]
    with predictor_combo_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=predictor_combo_fields)
        writer.writeheader()
        for combo in predictor_combos:
            writer.writerow({key: combo.get(key) for key in predictor_combo_fields})
    return path


def export_pdf(run: AnalysisRun) -> Path:
    path = EXPORT_DIR / f"{run.run_id}_clinician_report.pdf"
    styles = getSampleStyleSheet()
    banner_style = ParagraphStyle(
        "Banner",
        parent=styles["Normal"],
        textColor=colors.white,
        backColor=colors.HexColor("#7a1f1f"),
        alignment=1,
        spaceAfter=12,
        borderPadding=6,
    )

    doc = SimpleDocTemplate(str(path), pagesize=LETTER)
    elements = [
        Paragraph(BANNER_TEXT, banner_style),
        Paragraph("MOFA Copilot V2 — Overlap Nomination Report", styles["Title"]),
        Paragraph(f"Run ID: {run.run_id}", styles["Normal"]),
        Paragraph(f"Revision: {int(run.revision or 0)}", styles["Normal"]),
        Paragraph(f"Generated: {dt.datetime.now(dt.timezone.utc).isoformat()}", styles["Normal"]),
        Paragraph(f"Patient label (de-identified): {run.patient_label}", styles["Normal"]),
        Paragraph(
            "Patient metadata: "
            + ", ".join(
                f"{key.replace('_', ' ')}={value}"
                for key, value in (run.patient_metadata or {}).items()
                if value is not None and key != "field_provenance"
            ),
            styles["Normal"],
        ),
        Paragraph(f"Administered regimen: {', '.join(run.administered_regimen) or 'none recorded'}", styles["Normal"]),
        Spacer(1, 0.2 * inch),
    ]

    result = run.result_payload or {}
    sig = result.get("signature_params") or {}
    elements.append(
        Paragraph(
            f"Signature sizes: top_up={sig.get('top_up') or run.signature_top_up}, "
            f"top_down={sig.get('top_down') or run.signature_top_down}",
            styles["Normal"],
        )
    )
    elements.append(Spacer(1, 0.15 * inch))

    cluster = result.get("cluster_prediction") or {}
    if cluster:
        elements.append(Paragraph("MOFA cluster probabilities (RNA-only surrogate)", styles["Heading2"]))
        rows = [["Cluster", "Probability"]] + [
            [str(k), f"{v:.1%}"] for k, v in sorted(cluster.get("probabilities", {}).items())
        ]
        table = Table(rows, hAlign="LEFT")
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2b3a55")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ]
            )
        )
        elements.append(table)
        elements.append(
            Paragraph(
                f"Confidence level: {cluster.get('confidence_level')} | "
                f"Gene coverage: {cluster.get('gene_coverage', 0):.0%} "
                f"({cluster.get('genes_found')}/{cluster.get('genes_requested')} genes) | "
                f"Method: {cluster.get('method_used')}",
                styles["Normal"],
            )
        )
        elements.append(Spacer(1, 0.2 * inch))

    summary = result.get("overlap_summary") or {}
    elements.append(Paragraph("Overlap nominations (List 1 ∩ List 2)", styles["Heading2"]))
    elements.append(
        Paragraph(
            f"List 1 size={summary.get('n_list1')}, List 2 size={summary.get('n_list2')}, "
            f"overlap={summary.get('n_overlap')}. Ranking: weaker percentile first.",
            styles["Normal"],
        )
    )
    nominations = result.get("overlap_nominations") or []
    rows = [["Rank", "Drug", "List1", "List2", "Development", "Lane"]]
    for row in nominations[:15]:
        rows.append(
            [
                str(row.get("nomination_rank") or ""),
                str(row.get("drug") or ""),
                f"{row.get('list1_percentile') or 0:.0%}",
                f"{row.get('list2_percentile') or 0:.0%}",
                str(row.get("human_development_status") or row.get("evidence_tier") or "")[:28],
                str(row.get("display_action") or ""),
            ]
        )
    table = Table(rows, hAlign="LEFT", colWidths=[0.5 * inch, 1.4 * inch, 0.7 * inch, 0.7 * inch, 2.2 * inch, 0.7 * inch])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2b3a55")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
            ]
        )
    )
    elements.append(table)
    elements.append(Spacer(1, 0.2 * inch))

    combos = result.get("almanac_combinations") or []
    if combos:
        elements.append(Paragraph("ALMANAC cell-line-aligned combinations (preclinical)", styles["Heading2"]))
        rows = [["Combination", "Aligned lines", "Priority"]]
        for combo in combos[:8]:
            rows.append(
                [
                    str(combo.get("combination") or ""),
                    str(combo.get("aligned_cell_lines") or ""),
                    f"{combo.get('combination_priority') or 0:.3f}",
                ]
            )
        table = Table(rows, hAlign="LEFT")
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2b3a55")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                ]
            )
        )
        elements.append(table)
        elements.append(Spacer(1, 0.2 * inch))

    comparators = result.get("clinical_comparators") or []
    predictor_comparators = [
        row for row in comparators if row.get("predictor_evidence")
    ]
    if predictor_comparators:
        elements.append(
            Paragraph(
                "Parallel standard-treatment predictor context (not nominations)",
                styles["Heading2"],
            )
        )
        rows = [["Drug", "Ref Q2 pct", "Reliability", "Q4", "Priority", "Concordance"]]
        for comparator in predictor_comparators[:15]:
            predictor = comparator["predictor_evidence"]
            rows.append(
                [
                    str(comparator.get("drug") or ""),
                    f"{predictor.get('reference_cohort_sensitivity_percentile') or 0:.0%}",
                    f"{predictor.get('q2_model_reliability') or 0:.0%}",
                    f"{predictor.get('q4_drug_support') or 0:.0%}",
                    f"{predictor.get('integrated_single_drug_priority') or 0:.3f}",
                    str(comparator.get("evidence_concordance") or "").replace("_", " "),
                ]
            )
        table = Table(rows, hAlign="LEFT")
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#7c5a10")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("FONTSIZE", (0, 0), (-1, -1), 7),
                ]
            )
        )
        elements.append(table)
        elements.append(Spacer(1, 0.2 * inch))

    predictor_combos = result.get("predictor_combinations") or []
    if predictor_combos:
        elements.append(
            Paragraph(
                "Predictor-supported ALMANAC comparator lane (preclinical)",
                styles["Heading2"],
            )
        )
        rows = [["Rank", "Combination", "Components", "ALMANAC", "Pair Q4", "Priority"]]
        for combo in predictor_combos[:10]:
            rows.append(
                [
                    str(combo.get("rank") or ""),
                    str(combo.get("combination") or ""),
                    f"{combo.get('component_drug_priority') or 0:.3f}",
                    f"{combo.get('aligned_pair_support') or 0:.3f}",
                    f"{combo.get('pair_q4_support') or 0:.3f}",
                    f"{combo.get('integrated_combination_priority') or 0:.3f}",
                ]
            )
        table = Table(rows, hAlign="LEFT")
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#7c5a10")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("FONTSIZE", (0, 0), (-1, -1), 7),
                ]
            )
        )
        elements.append(table)
        elements.append(Spacer(1, 0.2 * inch))

    pcr = result.get("administered_regimen_pcr")
    if pcr:
        elements.append(
            Paragraph(
                "Historical Q5 regimen validation (separate from nomination evidence)",
                styles["Heading2"],
            )
        )
        gate = pcr.get("applicability_gate", {})
        if pcr.get("pcr_probability") is not None:
            elements.append(
                Paragraph(
                    f"Validated pCR probability estimate: {pcr['pcr_probability']:.1%} "
                    f"(cohort: {gate.get('validated_cohort')}, held-out AUROC "
                    f"{(gate.get('held_out_auroc') or 0):.2f}). This is a population-calibrated "
                    "estimate, not a guarantee of this patient's outcome, and is not merged into "
                    "overlap nomination or ALMANAC combination scores.",
                    styles["Normal"],
                )
            )
        else:
            elements.append(
                Paragraph(
                    f"No validated pCR estimate is available for this regimen. {gate.get('reason', '')}",
                    styles["Normal"],
                )
            )
        elements.append(Spacer(1, 0.2 * inch))

    for note in result.get("limitations") or []:
        elements.append(Paragraph(f"• {note}", styles["Normal"]))

    if run.warnings:
        elements.append(Paragraph("Warnings", styles["Heading2"]))
        for w in run.warnings:
            elements.append(Paragraph(f"[{w.severity}] {w.message}", styles["Normal"]))

    doc.build(elements)
    return path
