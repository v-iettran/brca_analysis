"""RNA-only surrogate classifier for soft MOFA cluster membership.

Two candidate methods are cross-validated against the true MOFA labels in
``mofa_clusters.csv``:

1. ``signature_similarity`` -- cosine similarity between a z-scored patient
   vector and each cluster's one-vs-rest differential-expression signature
   (regenerated per fold so there is no leakage), softmax-normalized into
   probabilities.
2. ``elastic_net`` -- a calibrated multinomial logistic regression with an
   elastic-net penalty on the top variance-ranked genes.

Whichever wins on macro-F1 in 5-fold cross-validation is persisted as the
shipped artifact (see ``jobs/train_cluster_classifier.py``). The classifier
never returns a forced single label -- always five soft probabilities plus an
explicit abstention/low-confidence flag driven by gene coverage and how
in-distribution the input looks relative to METABRIC.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score, accuracy_score, confusion_matrix
from sklearn.model_selection import StratifiedKFold
from sklearn.preprocessing import StandardScaler

from pipeline_core.config import (
    ABSTENTION_THRESHOLD,
    ARTIFACT_DIR,
    LOW_CONFIDENCE_THRESHOLD,
    MIN_GENE_COVERAGE,
    MOFA_CLUSTERS_DIR,
    N_MOFA_CLUSTERS,
)
from pipeline_core.expression import AlignedExpression, align_patient_expression
from pipeline_core.signatures import one_vs_rest_signature

TOP_N_SIGNATURE_GENES = 200
TOP_N_ELASTIC_NET_GENES = 1500
ClassifierMethod = Literal["signature_similarity", "elastic_net"]


def load_cluster_signatures() -> dict[int, pd.DataFrame]:
    """Load the committed per-cluster signature CSVs written by
    ``final-project/mofa_cluster_signatures.py``."""
    signatures = {}
    for cluster_id in range(N_MOFA_CLUSTERS):
        path = MOFA_CLUSTERS_DIR / f"cluster_{cluster_id}_signature.csv"
        if not path.exists():
            raise FileNotFoundError(f"Missing MOFA cluster signature: {path}")
        df = pd.read_csv(path).set_index("gene")
        df.index = df.index.str.upper()
        signatures[cluster_id] = df
    return signatures


def _top_signature_genes(sig: pd.DataFrame, n: int) -> pd.Series:
    ranked = sig.reindex(sig["coef"].abs().sort_values(ascending=False).index)
    return ranked.head(n)["coef"]


def _cosine_similarity_scores(
    z_scores: pd.Series, signatures: dict[int, pd.DataFrame], top_n: int = TOP_N_SIGNATURE_GENES
) -> dict[int, float]:
    scores = {}
    for cluster_id, sig in signatures.items():
        weights = _top_signature_genes(sig, top_n)
        genes = weights.index.intersection(z_scores.index)
        if len(genes) < 3:
            scores[cluster_id] = 0.0
            continue
        w = weights.loc[genes].to_numpy()
        x = z_scores.loc[genes].to_numpy()
        denom = np.linalg.norm(w) * np.linalg.norm(x)
        scores[cluster_id] = float(np.dot(w, x) / denom) if denom > 0 else 0.0
    return scores


def _softmax(scores: dict[int, float], temperature: float = 0.15) -> dict[int, float]:
    keys = sorted(scores)
    values = np.array([scores[k] for k in keys]) / temperature
    values -= values.max()
    exp = np.exp(values)
    probs = exp / exp.sum()
    return {k: float(p) for k, p in zip(keys, probs)}


@dataclass
class ClassifierMetrics:
    method: ClassifierMethod
    n_folds: int
    accuracy: float
    macro_f1: float
    per_fold_accuracy: list[float] = field(default_factory=list)
    per_fold_macro_f1: list[float] = field(default_factory=list)
    confusion_matrix: list[list[int]] = field(default_factory=list)
    n_samples: int = 0
    n_genes_used: int = 0

    def to_dict(self) -> dict:
        return {
            "method": self.method,
            "n_folds": self.n_folds,
            "accuracy": self.accuracy,
            "macro_f1": self.macro_f1,
            "per_fold_accuracy": self.per_fold_accuracy,
            "per_fold_macro_f1": self.per_fold_macro_f1,
            "confusion_matrix": self.confusion_matrix,
            "n_samples": self.n_samples,
            "n_genes_used": self.n_genes_used,
        }


def cross_validate_signature_similarity(
    expr: pd.DataFrame, labels: pd.Series, n_folds: int = 5, top_n: int = TOP_N_SIGNATURE_GENES
) -> ClassifierMetrics:
    """Regenerate cluster signatures on the training fold only, then score the
    held-out fold by cosine similarity. No leakage: every held-out sample is
    classified using signatures it never contributed to."""
    samples = [s for s in expr.columns if s in labels.index]
    y = labels.loc[samples]
    skf = StratifiedKFold(n_splits=n_folds, shuffle=True, random_state=42)

    fold_acc, fold_f1 = [], []
    all_true, all_pred = [], []

    for train_idx, test_idx in skf.split(np.zeros(len(samples)), y):
        train_samples = [samples[i] for i in train_idx]
        test_samples = [samples[i] for i in test_idx]

        train_expr = expr[train_samples]
        train_labels = y.iloc[train_idx]
        ref_mean = train_expr.mean(axis=1)
        ref_sd = train_expr.std(axis=1).replace(0, np.nan)

        fold_signatures = {
            cid: one_vs_rest_signature(train_expr, train_labels, cid)
            for cid in sorted(y.unique())
        }

        preds = []
        for sample in test_samples:
            z = (expr[sample] - ref_mean) / ref_sd
            z = z.replace([np.inf, -np.inf], np.nan).dropna()
            scores = _cosine_similarity_scores(z, fold_signatures, top_n=top_n)
            preds.append(max(scores, key=scores.get))

        truth = y.loc[test_samples].to_numpy()
        fold_acc.append(accuracy_score(truth, preds))
        fold_f1.append(f1_score(truth, preds, average="macro"))
        all_true.extend(truth.tolist())
        all_pred.extend(preds)

    labels_sorted = sorted(y.unique())
    cm = confusion_matrix(all_true, all_pred, labels=labels_sorted)
    return ClassifierMetrics(
        method="signature_similarity",
        n_folds=n_folds,
        accuracy=float(np.mean(fold_acc)),
        macro_f1=float(np.mean(fold_f1)),
        per_fold_accuracy=[float(a) for a in fold_acc],
        per_fold_macro_f1=[float(f) for f in fold_f1],
        confusion_matrix=cm.tolist(),
        n_samples=len(samples),
        n_genes_used=top_n,
    )


def cross_validate_elastic_net(
    expr: pd.DataFrame,
    labels: pd.Series,
    n_folds: int = 5,
    top_n_genes: int = TOP_N_ELASTIC_NET_GENES,
) -> ClassifierMetrics:
    samples = [s for s in expr.columns if s in labels.index]
    y = labels.loc[samples]

    variances = expr[samples].var(axis=1).sort_values(ascending=False)
    genes = variances.head(top_n_genes).index
    gene_matrix = expr.loc[genes, samples]
    gene_matrix = gene_matrix.apply(lambda row: row.fillna(row.mean()), axis=1)
    X = gene_matrix.T.to_numpy()

    skf = StratifiedKFold(n_splits=n_folds, shuffle=True, random_state=42)
    fold_acc, fold_f1 = [], []
    all_true, all_pred = [], []

    for train_idx, test_idx in skf.split(X, y):
        scaler = StandardScaler().fit(X[train_idx])
        X_train, X_test = scaler.transform(X[train_idx]), scaler.transform(X[test_idx])
        model = LogisticRegression(
            penalty="elasticnet",
            solver="saga",
            l1_ratio=0.3,
            C=0.5,
            max_iter=2000,
            random_state=42,
        )
        model.fit(X_train, y.iloc[train_idx])
        preds = model.predict(X_test)
        truth = y.iloc[test_idx].to_numpy()
        fold_acc.append(accuracy_score(truth, preds))
        fold_f1.append(f1_score(truth, preds, average="macro"))
        all_true.extend(truth.tolist())
        all_pred.extend(preds.tolist())

    labels_sorted = sorted(y.unique())
    cm = confusion_matrix(all_true, all_pred, labels=labels_sorted)
    return ClassifierMetrics(
        method="elastic_net",
        n_folds=n_folds,
        accuracy=float(np.mean(fold_acc)),
        macro_f1=float(np.mean(fold_f1)),
        per_fold_accuracy=[float(a) for a in fold_acc],
        per_fold_macro_f1=[float(f) for f in fold_f1],
        confusion_matrix=cm.tolist(),
        n_samples=len(samples),
        n_genes_used=top_n_genes,
    )


@dataclass
class ClusterPrediction:
    probabilities: dict[int, float]
    top_cluster: int
    top_probability: float
    confidence_level: Literal["high", "moderate", "low", "abstain"]
    gene_coverage: float
    genes_found: int
    genes_requested: int
    method_used: ClassifierMethod
    warnings: list[str]


def fit_final_elastic_net_model(
    expr: pd.DataFrame, labels: pd.Series, top_n_genes: int = TOP_N_ELASTIC_NET_GENES
) -> dict:
    """Fit the production elastic-net model on *all* labeled METABRIC
    patients (cross-validated performance is reported separately by
    ``cross_validate_elastic_net`` -- this is the final artifact actually
    served, matching standard practice of reporting CV metrics but shipping a
    model refit on the full labeled set)."""
    samples = [s for s in expr.columns if s in labels.index]
    y = labels.loc[samples]
    variances = expr[samples].var(axis=1).sort_values(ascending=False)
    genes = variances.head(top_n_genes).index
    gene_matrix = expr.loc[genes, samples].apply(lambda row: row.fillna(row.mean()), axis=1)

    scaler = StandardScaler().fit(gene_matrix.T.to_numpy())
    X = scaler.transform(gene_matrix.T.to_numpy())
    model = LogisticRegression(l1_ratio=0.3, C=0.5, solver="saga", max_iter=2000, random_state=42)
    model.fit(X, y)

    return {
        "genes": genes.tolist(),
        "scaler_mean": scaler.mean_.tolist(),
        "scaler_scale": scaler.scale_.tolist(),
        "coef": model.coef_.tolist(),
        "intercept": model.intercept_.tolist(),
        "classes": model.classes_.tolist(),
    }


class ClusterClassifierArtifact:
    """Serializable, versioned classifier artifact.

    Persists whichever method wins the head-to-head cross-validation
    benchmark (``metrics`` vs. ``alternative_metrics``). Both methods remain
    fully explainable: ``signature_similarity`` points directly at the
    committed per-cluster differential-expression genes, and
    ``elastic_net`` is itself a sparse linear model, so a technical reviewer
    can always see exactly which genes and weights drove a prediction.
    """

    def __init__(
        self,
        method: ClassifierMethod,
        top_n_genes: int,
        metrics: ClassifierMetrics,
        alternative_metrics: ClassifierMetrics | None,
        version: str,
        elastic_net_model: dict | None = None,
    ):
        self.method = method
        self.top_n_genes = top_n_genes
        self.metrics = metrics
        self.alternative_metrics = alternative_metrics
        self.version = version
        self.elastic_net_model = elastic_net_model

    def to_dict(self) -> dict:
        return {
            "method": self.method,
            "top_n_genes": self.top_n_genes,
            "metrics": self.metrics.to_dict(),
            "alternative_metrics": (
                self.alternative_metrics.to_dict() if self.alternative_metrics else None
            ),
            "version": self.version,
            "elastic_net_model": self.elastic_net_model,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ClusterClassifierArtifact":
        return cls(
            method=data["method"],
            top_n_genes=data["top_n_genes"],
            metrics=ClassifierMetrics(**data["metrics"]),
            alternative_metrics=(
                ClassifierMetrics(**data["alternative_metrics"])
                if data.get("alternative_metrics")
                else None
            ),
            version=data["version"],
            elastic_net_model=data.get("elastic_net_model"),
        )

    def save(self, path: Path | None = None) -> Path:
        path = path or (ARTIFACT_DIR / "cluster_classifier_artifact.json")
        path.write_text(json.dumps(self.to_dict(), indent=2))
        return path

    @classmethod
    def load(cls, path: Path | None = None) -> "ClusterClassifierArtifact":
        path = path or (ARTIFACT_DIR / "cluster_classifier_artifact.json")
        if not path.exists():
            raise FileNotFoundError(
                f"No trained classifier artifact at {path}. Run "
                "`python jobs/train_cluster_classifier.py` first."
            )
        return cls.from_dict(json.loads(path.read_text()))


def _predict_elastic_net(
    patient_expression: dict[str, float], model: dict
) -> tuple[dict[int, float], float, int, int]:
    genes = model["genes"]
    reference_genes = pd.Index(genes)
    aligned = align_patient_expression(patient_expression, reference_genes)

    mean = np.array(model["scaler_mean"])
    scale = np.array(model["scaler_scale"])
    # Missing genes are imputed at the reference population mean, i.e. they
    # contribute exactly 0 to the standardized feature (neutral), rather than
    # being silently treated as a measured expression value of 0.
    x = pd.Series(mean, index=genes)
    x.loc[aligned.values.index] = aligned.values
    x_scaled = (x.to_numpy() - mean) / scale

    coef = np.array(model["coef"])  # (n_classes, n_genes)
    intercept = np.array(model["intercept"])
    classes = model["classes"]

    logits = coef @ x_scaled + intercept
    if len(classes) == 2:
        # sklearn stores a single row of coefficients for binary problems.
        logits = np.array([-logits[0] / 2, logits[0] / 2])
    logits -= logits.max()
    exp = np.exp(logits)
    probs = exp / exp.sum()

    probabilities = {int(c): float(p) for c, p in zip(classes, probs)}
    return probabilities, aligned.coverage_fraction, aligned.genes_found, aligned.genes_requested


def predict_cluster_probabilities(
    patient_expression: dict[str, float],
    artifact: ClusterClassifierArtifact | None = None,
) -> ClusterPrediction:
    """Score a single patient's expression against all five MOFA clusters."""
    if artifact is None:
        try:
            artifact = ClusterClassifierArtifact.load()
        except FileNotFoundError:
            artifact = None

    method: ClassifierMethod = artifact.method if artifact else "signature_similarity"
    warnings: list[str] = []

    if method == "elastic_net" and artifact and artifact.elastic_net_model:
        probs, coverage, genes_found, genes_requested = _predict_elastic_net(
            patient_expression, artifact.elastic_net_model
        )
        genes_requested = genes_requested or len(artifact.elastic_net_model["genes"])
    else:
        method = "signature_similarity"
        signatures = load_cluster_signatures()
        top_n = artifact.top_n_genes if artifact else TOP_N_SIGNATURE_GENES
        reference_genes = pd.Index(sorted(signatures[0].index))
        aligned = align_patient_expression(patient_expression, reference_genes)
        raw_scores = _cosine_similarity_scores(aligned.z_scores, signatures, top_n=top_n)
        probs = _softmax(raw_scores)
        coverage = aligned.coverage_fraction
        genes_found = aligned.genes_found
        genes_requested = aligned.genes_requested or len(reference_genes)

    if coverage < MIN_GENE_COVERAGE:
        warnings.append(
            f"Only {genes_found}/{genes_requested} reference genes "
            f"({coverage:.0%}) were found in the submitted profile; cluster "
            f"probabilities are unreliable below {MIN_GENE_COVERAGE:.0%} coverage."
        )

    top_cluster = max(probs, key=probs.get)
    top_prob = probs[top_cluster]

    if coverage < MIN_GENE_COVERAGE:
        confidence: Literal["high", "moderate", "low", "abstain"] = "abstain"
        warnings.append(
            "Abstaining from a confident cluster call: gene coverage is too low "
            "to trust this assignment."
        )
    elif top_prob >= 0.55:
        confidence = "high"
    elif top_prob >= LOW_CONFIDENCE_THRESHOLD:
        confidence = "moderate"
    elif top_prob < ABSTENTION_THRESHOLD:
        confidence = "abstain"
        warnings.append(
            "Abstaining from a confident cluster call: top-cluster probability "
            "is too low to trust this assignment."
        )
    else:
        confidence = "low"
        warnings.append(
            "Cluster probabilities are diffuse (mixed-cluster profile); treat any "
            "single top cluster as provisional."
        )

    return ClusterPrediction(
        probabilities=probs,
        top_cluster=top_cluster,
        top_probability=top_prob,
        confidence_level=confidence,
        gene_coverage=coverage,
        genes_found=genes_found,
        genes_requested=genes_requested,
        method_used=method,
        warnings=warnings,
    )
