"""Orchestrates deterministic tools into staged analysis runs with revisions."""

from __future__ import annotations

import threading
import time
from contextlib import contextmanager

from sqlalchemy.orm import Session

from pipeline_core.almanac_evidence import combinations_for_overlap
from pipeline_core.clinical_comparators import expression_ranked_comparators
from pipeline_core.cluster_model import ClusterClassifierArtifact
from pipeline_core.config import DEFAULT_TOP_DOWN, DEFAULT_TOP_UP
from pipeline_core.drug_names import normalize_drug_name
from pipeline_core.embedding import project_patient
from pipeline_core.gctx_evidence import load_all_cluster_drug_tables
from pipeline_core.gctx_retrieval import list1_cluster_reversal, list2_patient_residual_reversal
from pipeline_core.display_gating import apply_display_gating
from pipeline_core.nominations import nominate_overlap
from pipeline_core.predictor_evidence import (
    PREDICTOR_VERSION,
    attach_predictor_context,
    predictor_combinations,
    score_predictor_drugs,
)
from pipeline_core.q2_annotations import q2_annotations_for_drugs
from pipeline_core.residual_signatures import clamp_signature_size, signature_to_payload

from app.db import SessionLocal
from app.models_orm import AnalysisRun, AnalysisStage, AuditEvent, RunWarning
from app.schemas.patient import PatientProfileIn
from app.services import tools
from app.services.literature_service import prefetch_literature_batch
from app.services.v2_prototype import is_demo_patient, load_demo_payload, result_fields_from_prototype

STAGES = [
    ("validate", "Validating profile"),
    ("deconvolve", "Estimating tumour composition"),
    ("encode_latent", "Encoding latent position"),
    ("infer_activity", "Inferring pathway and TF activity"),
    ("project_sensitivity", "Projecting drug-pathway sensitivity"),
    ("calibrate_set", "Calibrating the prediction set"),
    ("assemble", "Preparing dashboard"),
]


@contextmanager
def _timed_audit(db: Session, run_id: str, tool_name: str, input_summary: dict):
    start = time.perf_counter()
    output_summary: dict = {}
    try:
        yield output_summary
    finally:
        duration_ms = (time.perf_counter() - start) * 1000
        db.add(
            AuditEvent(
                run_id=run_id,
                tool_name=tool_name,
                input_summary=input_summary,
                output_summary=output_summary,
                duration_ms=duration_ms,
            )
        )


def _set_stage(db: Session, run: AnalysisRun, stage_id: str, label: str, status: str, detail: str | None = None):
    run.current_stage = stage_id
    run.status = "running" if status == "running" else run.status
    db.add(
        AnalysisStage(
            run_id=run.run_id,
            stage_id=stage_id,
            label=label,
            status=status,
            detail=detail,
        )
    )
    db.commit()


def _none_if_nan(value) -> float | None:
    import math

    try:
        f = float(value)
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def _build_v2_payload(
    profile: PatientProfileIn,
    prediction,
    top_up: int,
    top_down: int,
    db: Session,
    run: AnalysisRun,
) -> dict:
    cluster_id = int(prediction.top_cluster)

    _set_stage(db, run, "deconvolve", "Estimating tumour composition", "running")
    with _timed_audit(db, run.run_id, "deconvolve", {"mode": "synthetic_rna_only"}) as out:
        out["applicable"] = False
        out["reason"] = "RNA-only synthetic profile; tumour deconvolution is not applicable"
    _set_stage(db, run, "deconvolve", "Estimating tumour composition", "completed")

    _set_stage(db, run, "encode_latent", "Encoding latent position", "running")
    with _timed_audit(db, run.run_id, "project_patient_rna", {"cluster": cluster_id}) as out:
        projection = project_patient(profile.expression)
        out["method"] = projection.get("method")
    _set_stage(db, run, "encode_latent", "Encoding latent position", "completed")

    _set_stage(db, run, "infer_activity", "Inferring pathway and TF activity", "running")
    with _timed_audit(
        db, run.run_id, "build_signatures", {"top_up": top_up, "top_down": top_down, "cluster": cluster_id}
    ) as out:
        arms, list1 = list1_cluster_reversal(
            cluster_id,
            cluster_probabilities=prediction.probabilities,
            top_up=top_up,
            top_down=top_down,
            top_n=None,
        )
        residual, list2 = list2_patient_residual_reversal(
            profile.expression,
            cluster_id,
            cluster_probabilities=prediction.probabilities,
            top_up=top_up,
            top_down=top_down,
            top_n=None,
        )
        cluster_sig_payload = signature_to_payload(arms)
        residual_sig_payload = signature_to_payload(residual)
        out.update({"n_list1": len(list1), "n_list2": len(list2), "n_residual_genes": residual.genes_used})
    _set_stage(db, run, "infer_activity", "Inferring pathway and TF activity", "completed")

    _set_stage(db, run, "project_sensitivity", "Projecting drug-pathway sensitivity", "completed")
    _set_stage(db, run, "project_sensitivity", "Projecting drug-pathway sensitivity", "running")
    with _timed_audit(db, run.run_id, "nominate_overlap", {}) as out:
        nomination = nominate_overlap(list1, list2, top_n=25)
        out["n_overlap"] = nomination["n_overlap"]
        clinical_comparators = expression_ranked_comparators(
            list1,
            list2,
            cluster_reference=load_all_cluster_drug_tables().get(cluster_id),
        )
        out["n_clinical_comparators"] = len(clinical_comparators)
    _set_stage(db, run, "project_sensitivity", "Projecting drug-pathway sensitivity", "completed")

    _set_stage(db, run, "project_sensitivity", "Projecting drug-pathway sensitivity", "running")
    overlap_drugs = [row["drug"] for row in nomination["overlap"]]
    with _timed_audit(db, run.run_id, "annotate_q2", {"n_drugs": len(overlap_drugs)}) as out:
        q2_ann = q2_annotations_for_drugs(profile.expression, overlap_drugs)
        out["drugs_annotated"] = len(q2_ann)
    predictor_rows: list[dict] = []
    predictor_combo_rows: list[dict] = []
    with _timed_audit(db, run.run_id, "score_predictor_context", {}) as out:
        try:
            predictor_rows = score_predictor_drugs(profile.expression)
            clinical_comparators = attach_predictor_context(
                clinical_comparators, predictor_rows
            )
            predictor_combo_rows = predictor_combinations(predictor_rows)
            out.update(
                {
                    "version": PREDICTOR_VERSION,
                    "single_drugs_scored": len(predictor_rows),
                    "combinations_scored": len(predictor_combo_rows),
                }
            )
        except (FileNotFoundError, KeyError, ValueError) as exc:
            out["unavailable_reason"] = str(exc)
            db.add(
                RunWarning(
                    run_id=run.run_id,
                    severity="caution",
                    message=(
                        "Parallel predictor context was unavailable; primary List 1/List 2 "
                        "nominations are unaffected."
                    ),
                )
            )
    q2_percentiles = {
        k: v.get("sensitivity_percentile")
        for k, v in q2_ann.items()
        if v.get("sensitivity_percentile") is not None
    }
    with _timed_audit(db, run.run_id, "almanac_combinations", {}) as out:
        combos = combinations_for_overlap(
            [row["canonical"] for row in nomination["overlap"]],
            q2_percentiles={k: float(v) for k, v in q2_percentiles.items()},
            top_n=10,
        )
        out["n_combinations"] = len(combos)

    # Keep legacy Q2 table + pCR as separate historical validation evidence.
    with _timed_audit(db, run.run_id, "score_q2_drugs", {}) as out:
        q2_table = tools.score_q2_drugs(profile.expression)
        out["drugs_scored"] = int(q2_table["raw_score"].notna().sum())

    pcr_result = None
    if profile.administered_regimen:
        with _timed_audit(
            db, run.run_id, "calculate_supported_pcr", {"regimen": profile.administered_regimen}
        ) as out:
            pcr_result = tools.calculate_supported_pcr(
                profile.expression, profile.administered_regimen, prediction.probabilities
            )
            out.update(
                {
                    "gate_passed": pcr_result["applicability_gate"]["gate_passed"],
                    "pcr_probability": pcr_result["pcr_probability"],
                }
            )
    _set_stage(db, run, "project_sensitivity", "Projecting drug-pathway sensitivity", "completed")

    nominations_out = []
    for row in nomination["overlap"]:
        canonical = row["canonical"]
        q2 = q2_ann.get(canonical)
        nominations_out.append(
            {
                **row,
                "q2_annotation": q2,
                "is_in_administered_regimen": normalize_drug_name(row["drug"])
                in {normalize_drug_name(d) for d in profile.administered_regimen},
                "literature_summary": None,
            }
        )

    _set_stage(db, run, "calibrate_set", "Calibrating the prediction set", "running")
    visible_genes: list[str] = []
    for panel in (cluster_sig_payload, residual_sig_payload):
        for gene_row in (panel or {}).get("genes", [])[:20]:
            symbol = gene_row.get("gene")
            if symbol and symbol not in visible_genes:
                visible_genes.append(symbol)
    with _timed_audit(
        db, run.run_id, "prefetch_literature", {"n_drugs": len(nominations_out), "n_genes": len(visible_genes)}
    ) as out:
        try:
            lit_batch = prefetch_literature_batch(db, nominations_out, visible_genes)
            out.update(
                {
                    "drugs_enriched": len(lit_batch.get("drugs") or {}),
                    "genes_enriched": len(lit_batch.get("genes") or {}),
                }
            )
        except Exception as exc:  # noqa: BLE001
            lit_batch = {"drugs": {}, "genes": {}}
            out["error"] = str(exc)[:240]
            db.add(
                RunWarning(
                    run_id=run.run_id,
                    severity="caution",
                    message="Literature prefetch was unavailable; overlap ranks are unchanged.",
                )
            )
    gene_counts = lit_batch.get("genes") or {}
    for panel_key, panel in (
        ("cluster_signature", cluster_sig_payload),
        ("residual_signature", residual_sig_payload),
    ):
        for gene_row in (panel or {}).get("genes", []):
            gene_row["literature_count"] = gene_counts.get(str(gene_row.get("gene", "")).upper())
    for row in nominations_out:
        row["literature_summary"] = lit_batch.get("drugs", {}).get(row["drug"])
    gated = apply_display_gating(nominations_out)
    nominations_out = gated["visible"]
    _set_stage(db, run, "calibrate_set", "Calibrating the prediction set", "completed")

    # Backward-compatible top_candidate_drugs alias = overlap nominations shaped like old cards.
    legacy_candidates = []
    for row in nominations_out:
        q2 = row.get("q2_annotation")
        legacy_candidates.append(
            {
                "drug": row["drug"],
                "targets": row.get("targets") or [],
                "gctx_evidence": {
                    "drug": row["drug"],
                    "blended_percentile": row.get("weaker_percentile"),
                    "clusters_with_data": 1,
                    "per_cluster": [
                        {
                            "cluster_id": cluster_id,
                            "cluster_probability": prediction.probabilities.get(cluster_id, 0.0),
                            "drug_rank": row.get("list1_rank") or 0,
                            "reversal_score": row.get("list1_score") or 0.0,
                            "percentile": row.get("list1_percentile") or 0.0,
                            "n_signatures": row.get("n_signatures"),
                            "targets": row.get("targets") or [],
                            "n_drugs_in_cluster": nomination["n_list1"],
                        }
                    ],
                },
                "q2_evidence": (
                    {
                        "drug": row["drug"],
                        "raw_score": q2.get("raw_score") if q2 else None,
                        "z_score": q2.get("z_score") if q2 else None,
                        "genes_used": q2.get("genes_used") if q2 else 0,
                        "evidence_category": q2.get("evidence_category") if q2 else None,
                        "model_support": q2.get("model_support") if q2 else None,
                        "model_spearman": q2.get("model_spearman") if q2 else None,
                        "external_spearman": q2.get("external_spearman") if q2 else None,
                    }
                    if q2
                    else None
                ),
                "literature_summary": row.get("literature_summary"),
                "is_in_administered_regimen": row["is_in_administered_regimen"],
                "evidence_tier": row.get("evidence_tier"),
                "list1_percentile": row.get("list1_percentile"),
                "list2_percentile": row.get("list2_percentile"),
                "indication_bucket": row.get("indication_bucket"),
                "robustness": row.get("robustness"),
            }
        )

    def _records(df):
        if hasattr(df, "to_dict"):
            records = df.head(50).to_dict(orient="records")
            for record in records:
                for key, value in list(record.items()):
                    if value is not None and hasattr(value, "item"):
                        record[key] = value.item()
                    elif isinstance(value, float):
                        record[key] = _none_if_nan(value)
            return records
        return df

    return {
        "schema_version": "v2",
        "signature_params": {"top_up": top_up, "top_down": top_down},
        "cluster_prediction": {
            "probabilities": {str(k): v for k, v in prediction.probabilities.items()},
            "top_cluster": prediction.top_cluster,
            "top_probability": prediction.top_probability,
            "confidence_level": prediction.confidence_level,
            "gene_coverage": prediction.gene_coverage,
            "genes_found": prediction.genes_found,
            "genes_requested": prediction.genes_requested,
            "method_used": prediction.method_used,
            "warnings": prediction.warnings,
        },
        "rna_projection": projection,
        "cluster_signature": cluster_sig_payload,
        "residual_signature": residual_sig_payload,
        "list1_drugs": _records(list1),
        "list2_drugs": _records(list2),
        "overlap_nominations": nominations_out,
        "overlap_exploratory": gated["exploratory"],
        "overlap_technical_excluded": gated["technical_excluded"],
        "display_gate_summary": gated["gate_summary"],
        "compound_registry_version": gated["registry_version"],
        "analysis_summary": {
            "top_cluster": prediction.top_cluster,
            "top_probability": prediction.top_probability,
            "confidence_level": prediction.confidence_level,
            "headline_nominations": [
                {
                    "drug": row.get("drug"),
                    "human_development_label": row.get("human_development_label"),
                    "weaker_percentile": row.get("weaker_percentile"),
                    "display_gate_reason": row.get("display_gate_reason"),
                }
                for row in nominations_out[:3]
            ],
            "dominant_uncertainty": (
                "Cluster signatures are one-vs-rest among METABRIC tumours; there is no normal-breast reference."
            ),
        },
        "clinical_comparators": clinical_comparators,
        "predictor_single_drugs": predictor_rows,
        "predictor_combinations": predictor_combo_rows,
        "predictor_summary": {
            "version": PREDICTOR_VERSION,
            "role": "parallel_clinical_context_not_nomination",
            "reference_cohort": "METABRIC",
            "parity_scope": (
                "R scoring equations and committed Q2/Q4/ALMANAC support tables; "
                "not numerical parity with DLDCCC-reference runs."
            ),
            "concordance_thresholds": {
                "dual_expression_percentile": 0.75,
                "within_patient_predictor_percentile": 0.75,
            },
            "single_drug_formula": {
                "patient_q2_sensitivity": 0.60,
                "q2_model_reliability": 0.25,
                "q4_support": 0.15,
            },
            "combination_formula": {
                "component_drug_priority": 0.55,
                "aligned_pair_support": 0.35,
                "pair_q4_support": 0.10,
            },
            "warning": (
                "Scores are relative evidence priorities, not treatment-response "
                "probabilities or recommendations."
            ),
        },
        "near_consensus": nomination["near_consensus"],
        "overlap_summary": {
            "n_list1": nomination["n_list1"],
            "n_list2": nomination["n_list2"],
            "n_overlap": nomination["n_overlap"],
            "n_supported": nomination.get("n_supported", 0),
            "n_suggestive": nomination.get("n_suggestive", 0),
            "n_excluded_low_confidence": nomination.get("n_excluded_low_confidence", 0),
            "ranking_rule": nomination["ranking_rule"],
        },
        "almanac_combinations": combos,
        "administered_regimen_pcr": pcr_result,
        "top_candidate_drugs": legacy_candidates,
        "limitations": [
            "Cluster signatures are one-vs-rest among METABRIC tumours; there is no normal-breast reference.",
            "Reversing a cluster signature moves away from that cluster state, not necessarily toward a favorable or normal state.",
            "RNA UMAP/PCA is a surrogate projection colored by MOFA labels, not the original multi-omics MOFA space.",
            "Q2 scores annotate sensitivity only and do not prescribe dosage.",
            "Predictor scores are a parallel standard-treatment context and do not alter List 1/List 2 nomination ranks.",
            "ALMANAC combinations are preclinical cell-line-aligned priorities, not clinical recommendations.",
            "Literature counts are retrieved relevant references, not total publications or clinical proof.",
            "Trial matches require investigator confirmation of eligibility.",
            "Human-development labels are regulatory snapshots for presentation only, not patient suitability.",
        ],
    }


def _run_prototype_on_run(db: Session, run: AnalysisRun, patient_id: str) -> AnalysisRun:
    demo = load_demo_payload(patient_id)
    slices = {
        "deconvolve": "sample_quality",
        "encode_latent": "position",
        "infer_activity": "molecular_state",
        "project_sensitivity": "modality_value_estimate",
        "calibrate_set": "pathway_candidates",
    }
    for stage_id, label in STAGES:
        _set_stage(db, run, stage_id, label, "running")
        with _timed_audit(db, run.run_id, stage_id, {"patient_id": patient_id, "role": demo.get("role")}) as out:
            key = slices.get(stage_id)
            if key:
                out["has_slice"] = demo.get(key) is not None
            out["state"] = demo.get("state")
            out["abstained"] = bool((demo.get("abstention") or {}).get("abstained"))
        _set_stage(db, run, stage_id, label, "completed")
    fields = result_fields_from_prototype(demo)
    run.status = "completed"
    run.result_payload = fields
    run.patient_metadata = demo.get("patient_metadata") or run.patient_metadata
    run.cluster_probabilities = fields["cluster_prediction"]["probabilities"]
    run.confidence_level = fields["cluster_prediction"]["confidence_level"]
    run.gene_coverage = fields["cluster_prediction"]["gene_coverage"]
    run.current_stage = "assemble"
    if demo.get("banner"):
        db.add(
            RunWarning(
                run_id=run.run_id,
                severity="abstain" if int(demo.get("state") or 1) == 3 else "caution",
                message=demo["banner"],
            )
        )
    db.commit()
    return run


def run_analysis(
    db: Session,
    profile: PatientProfileIn,
    top_up: int | None = None,
    top_down: int | None = None,
    session_id: str | None = None,
) -> AnalysisRun:
    top_up = clamp_signature_size(top_up, DEFAULT_TOP_UP)
    top_down = clamp_signature_size(top_down, DEFAULT_TOP_DOWN)

    run = AnalysisRun(
        patient_label=profile.patient_label,
        patient_metadata=profile.metadata.model_dump(),
        administered_regimen=profile.administered_regimen,
        status="pending",
        session_id=session_id,
        expression_snapshot=profile.expression,
        signature_top_up=top_up,
        signature_top_down=top_down,
        revision=0,
    )
    db.add(run)
    db.commit()

    try:
        if is_demo_patient(profile.patient_label):
            return _run_prototype_on_run(db, run, profile.patient_label)

        _set_stage(db, run, "validate", "Validating profile", "running")
        with _timed_audit(db, run.run_id, "validate_patient", {"gene_count": len(profile.expression)}) as out:
            validation = tools.validate_patient(profile)
            out.update(
                {
                    "ok": validation.ok,
                    "gene_count": validation.gene_count,
                    "unrecognized_regimen_drugs": validation.unrecognized_regimen_drugs,
                }
            )
        for message in validation.warnings:
            db.add(RunWarning(run_id=run.run_id, severity="caution", message=message))
        _set_stage(db, run, "validate", "Validating profile", "completed")

        _set_stage(db, run, "encode_latent", "Encoding latent position", "running")
        with _timed_audit(db, run.run_id, "score_clusters", {"gene_count": len(profile.expression)}) as out:
            prediction = tools.score_clusters(profile.expression)
            out.update(
                {
                    "top_cluster": prediction.top_cluster,
                    "top_probability": prediction.top_probability,
                    "confidence_level": prediction.confidence_level,
                    "gene_coverage": prediction.gene_coverage,
                }
            )
        for message in prediction.warnings:
            severity = "abstain" if prediction.confidence_level == "abstain" else "caution"
            db.add(RunWarning(run_id=run.run_id, severity=severity, message=message))

        payload = _build_v2_payload(profile, prediction, top_up, top_down, db, run)

        artifact_version = None
        try:
            artifact_version = ClusterClassifierArtifact.load().version
        except FileNotFoundError:
            pass

        _set_stage(db, run, "assemble", "Preparing dashboard", "running")
        run.status = "completed"
        run.classifier_method = prediction.method_used
        run.classifier_version = artifact_version
        run.cluster_probabilities = {str(k): v for k, v in prediction.probabilities.items()}
        run.confidence_level = prediction.confidence_level
        run.gene_coverage = prediction.gene_coverage
        run.result_payload = payload
        run.current_stage = "assemble"
        db.commit()
        _set_stage(db, run, "assemble", "Preparing dashboard", "completed")
    except Exception as exc:  # noqa: BLE001
        run.status = "failed"
        run.error_message = str(exc)
        db.add(
            AnalysisStage(
                run_id=run.run_id,
                stage_id=run.current_stage or "failed",
                label="Failed",
                status="failed",
                detail=str(exc),
            )
        )
        db.commit()
        raise

    return run


def start_analysis_async(
    profile: PatientProfileIn,
    top_up: int | None = None,
    top_down: int | None = None,
    session_id: str | None = None,
) -> str:
    """Create a pending run and execute analysis on a background thread."""
    db = SessionLocal()
    try:
        top_up = clamp_signature_size(top_up, DEFAULT_TOP_UP)
        top_down = clamp_signature_size(top_down, DEFAULT_TOP_DOWN)
        run = AnalysisRun(
            patient_label=profile.patient_label,
            patient_metadata=profile.metadata.model_dump(),
            administered_regimen=profile.administered_regimen,
            status="pending",
            session_id=session_id,
            expression_snapshot=profile.expression,
            signature_top_up=top_up,
            signature_top_down=top_down,
            revision=0,
            current_stage="queued",
        )
        db.add(run)
        db.commit()
        run_id = run.run_id
    finally:
        db.close()

    def _worker():
        worker_db = SessionLocal()
        try:
            run_obj = worker_db.get(AnalysisRun, run_id)
            # Re-hydrate profile and execute on this session.
            profile_local = PatientProfileIn(
                patient_label=run_obj.patient_label,
                expression=run_obj.expression_snapshot or {},
                metadata=run_obj.patient_metadata or {},
                administered_regimen=run_obj.administered_regimen or [],
            )
            # Delete placeholder and reuse same run_id by updating in place.
            run_obj.status = "running"
            worker_db.commit()
            _execute_on_existing_run(worker_db, run_obj, profile_local, run_obj.signature_top_up, run_obj.signature_top_down)
        except Exception as exc:  # noqa: BLE001
            run_obj = worker_db.get(AnalysisRun, run_id)
            if run_obj is not None:
                run_obj.status = "failed"
                run_obj.error_message = str(exc)
                worker_db.commit()
        finally:
            worker_db.close()

    threading.Thread(target=_worker, daemon=True).start()
    return run_id


def start_demo_analysis(patient_id: str, session_id: str | None = None) -> str:
    """Queue a held-out TCGA demo run. No RNA is submitted."""
    db = SessionLocal()
    try:
        run = AnalysisRun(
            patient_label=patient_id,
            patient_metadata={},
            administered_regimen=[],
            status="pending",
            session_id=session_id,
            expression_snapshot=None,
            revision=0,
            current_stage="queued",
        )
        db.add(run)
        db.commit()
        run_id = run.run_id
    finally:
        db.close()

    def _worker():
        worker_db = SessionLocal()
        try:
            run_obj = worker_db.get(AnalysisRun, run_id)
            run_obj.status = "running"
            worker_db.commit()
            _run_prototype_on_run(worker_db, run_obj, patient_id)
        except Exception as exc:  # noqa: BLE001
            run_obj = worker_db.get(AnalysisRun, run_id)
            if run_obj is not None:
                run_obj.status = "failed"
                run_obj.error_message = str(exc)
                worker_db.commit()
        finally:
            worker_db.close()

    threading.Thread(target=_worker, daemon=True).start()
    return run_id


def _execute_on_existing_run(
    db: Session, run: AnalysisRun, profile: PatientProfileIn, top_up: int, top_down: int
) -> AnalysisRun:
    try:
        if is_demo_patient(profile.patient_label):
            return _run_prototype_on_run(db, run, profile.patient_label)

        _set_stage(db, run, "validate", "Validating profile", "running")
        with _timed_audit(db, run.run_id, "validate_patient", {"gene_count": len(profile.expression)}) as out:
            validation = tools.validate_patient(profile)
            out.update({"ok": validation.ok, "gene_count": validation.gene_count})
        for message in validation.warnings:
            db.add(RunWarning(run_id=run.run_id, severity="caution", message=message))
        _set_stage(db, run, "validate", "Validating profile", "completed")

        _set_stage(db, run, "encode_latent", "Encoding latent position", "running")
        with _timed_audit(db, run.run_id, "score_clusters", {"gene_count": len(profile.expression)}) as out:
            prediction = tools.score_clusters(profile.expression)
            out.update(
                {
                    "top_cluster": prediction.top_cluster,
                    "top_probability": prediction.top_probability,
                    "confidence_level": prediction.confidence_level,
                }
            )
        for message in prediction.warnings:
            severity = "abstain" if prediction.confidence_level == "abstain" else "caution"
            db.add(RunWarning(run_id=run.run_id, severity=severity, message=message))

        payload = _build_v2_payload(profile, prediction, top_up, top_down, db, run)
        artifact_version = None
        try:
            artifact_version = ClusterClassifierArtifact.load().version
        except FileNotFoundError:
            pass
        _set_stage(db, run, "assemble", "Preparing dashboard", "running")
        run.status = "completed"
        run.classifier_method = prediction.method_used
        run.classifier_version = artifact_version
        run.cluster_probabilities = {str(k): v for k, v in prediction.probabilities.items()}
        run.confidence_level = prediction.confidence_level
        run.gene_coverage = prediction.gene_coverage
        run.result_payload = payload
        db.commit()
        _set_stage(db, run, "assemble", "Preparing dashboard", "completed")
    except Exception as exc:  # noqa: BLE001
        run.status = "failed"
        run.error_message = str(exc)
        db.commit()
        raise
    return run


def recalculate_signatures(db: Session, run: AnalysisRun, top_up: int, top_down: int) -> AnalysisRun:
    if not run.expression_snapshot:
        raise ValueError("Run has no stored expression snapshot for recalculation.")
    top_up = clamp_signature_size(top_up, DEFAULT_TOP_UP)
    top_down = clamp_signature_size(top_down, DEFAULT_TOP_DOWN)
    profile = PatientProfileIn(
        patient_label=run.patient_label,
        expression=run.expression_snapshot,
        metadata=run.patient_metadata or {},
        administered_regimen=run.administered_regimen or [],
    )
    run.revision = int(run.revision or 0) + 1
    run.signature_top_up = top_up
    run.signature_top_down = top_down
    run.status = "running"
    db.commit()

    prediction = tools.score_clusters(profile.expression)
    payload = _build_v2_payload(profile, prediction, top_up, top_down, db, run)
    run.status = "completed"
    run.cluster_probabilities = {str(k): v for k, v in prediction.probabilities.items()}
    run.confidence_level = prediction.confidence_level
    run.gene_coverage = prediction.gene_coverage
    run.result_payload = payload
    db.commit()
    return run


def materialize_public_synthetic_run(
    db: Session, synthetic_id: str, session_id: str | None = None
) -> AnalysisRun:
    from app.services.demo_bundle import apply_bundle_to_run, bundle_stage_rows

    run = AnalysisRun(
        patient_label=synthetic_id,
        session_id=session_id,
        status="running",
        expression_snapshot=None,
        revision=0,
        current_stage="assemble",
    )
    db.add(run)
    db.commit()
    apply_bundle_to_run(run, synthetic_id)
    for stage in bundle_stage_rows(run.run_id):
        db.add(stage)
    db.commit()
    return run
