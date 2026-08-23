"""Cross-validate the two candidate RNA surrogate cluster classifiers and
persist whichever wins as the shipped inference artifact.

Usage (from person_med_a2/, with the venv activated and pipeline_core
installed editable):

    python jobs/train_cluster_classifier.py

Writes ``outputs/copilot_artifacts/cluster_classifier_artifact.json`` and a
human-readable ``outputs/copilot_artifacts/cluster_classifier_report.md``.
"""

from __future__ import annotations

import time

from pipeline_core.cluster_model import (
    ClusterClassifierArtifact,
    TOP_N_ELASTIC_NET_GENES,
    TOP_N_SIGNATURE_GENES,
    cross_validate_elastic_net,
    cross_validate_signature_similarity,
    fit_final_elastic_net_model,
)
from pipeline_core.config import ARTIFACT_DIR
from pipeline_core.expression import load_metabric_expression, load_mofa_cluster_labels


def main() -> None:
    print("Loading METABRIC expression + MOFA cluster labels...")
    expr = load_metabric_expression()
    labels = load_mofa_cluster_labels()

    print(f"n_samples={len(labels)}, n_genes={expr.shape[0]}")

    print("Cross-validating signature-similarity classifier (5-fold)...")
    t0 = time.time()
    sig_metrics = cross_validate_signature_similarity(expr, labels, n_folds=5, top_n=TOP_N_SIGNATURE_GENES)
    print(f"  accuracy={sig_metrics.accuracy:.3f} macro_f1={sig_metrics.macro_f1:.3f} ({time.time()-t0:.1f}s)")

    print("Cross-validating elastic-net classifier (5-fold)...")
    t0 = time.time()
    enet_metrics = cross_validate_elastic_net(expr, labels, n_folds=5, top_n_genes=TOP_N_ELASTIC_NET_GENES)
    print(f"  accuracy={enet_metrics.accuracy:.3f} macro_f1={enet_metrics.macro_f1:.3f} ({time.time()-t0:.1f}s)")

    if enet_metrics.macro_f1 >= sig_metrics.macro_f1:
        winner, alternative = "elastic_net", sig_metrics
        print("Winner: elastic_net")
        print("Fitting final elastic-net model on all labeled patients...")
        enet_model = fit_final_elastic_net_model(expr, labels, top_n_genes=TOP_N_ELASTIC_NET_GENES)
        artifact = ClusterClassifierArtifact(
            method="elastic_net",
            top_n_genes=TOP_N_ELASTIC_NET_GENES,
            metrics=enet_metrics,
            alternative_metrics=alternative,
            version="1.0.0",
            elastic_net_model=enet_model,
        )
    else:
        winner, alternative = "signature_similarity", enet_metrics
        print("Winner: signature_similarity")
        artifact = ClusterClassifierArtifact(
            method="signature_similarity",
            top_n_genes=TOP_N_SIGNATURE_GENES,
            metrics=sig_metrics,
            alternative_metrics=alternative,
            version="1.0.0",
            elastic_net_model=None,
        )

    path = artifact.save()
    print(f"Saved artifact -> {path}")

    report_path = ARTIFACT_DIR / "cluster_classifier_report.md"
    report_path.write_text(
        "# RNA surrogate cluster classifier benchmark\n\n"
        f"- Winner (shipped): **{winner}**\n\n"
        "## signature_similarity (5-fold CV)\n"
        f"- accuracy: {sig_metrics.accuracy:.3f}\n"
        f"- macro F1: {sig_metrics.macro_f1:.3f}\n"
        f"- per-fold accuracy: {sig_metrics.per_fold_accuracy}\n"
        f"- confusion matrix: {sig_metrics.confusion_matrix}\n\n"
        "## elastic_net (5-fold CV)\n"
        f"- accuracy: {enet_metrics.accuracy:.3f}\n"
        f"- macro F1: {enet_metrics.macro_f1:.3f}\n"
        f"- per-fold accuracy: {enet_metrics.per_fold_accuracy}\n"
        f"- confusion matrix: {enet_metrics.confusion_matrix}\n\n"
        "Both classifiers only ever see RNA -- true MOFA cluster labels come "
        "from all three omics layers, so this benchmark also reports how much "
        "cluster signal survives when only expression is available at "
        "inference time, which is the deployment-realistic scenario.\n"
    )
    print(f"Saved report -> {report_path}")


if __name__ == "__main__":
    main()
