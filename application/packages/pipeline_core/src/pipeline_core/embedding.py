"""RNA-only UMAP/PCA projection colored by MOFA cluster labels.

This is a surrogate visualization of patient RNA in a METABRIC reference
embedding. It is NOT a projection into the original multi-omics MOFA factor
space (which also uses CNA and methylation).
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler

from pipeline_core.cluster_model import ClusterClassifierArtifact
from pipeline_core.config import (
    UMAP_META_PATH,
    UMAP_REFERENCE_PATH,
    UMAP_TRANSFORM_PATH,
)
from pipeline_core.expression import align_patient_expression, load_metabric_expression, load_mofa_cluster_labels, reference_gene_stats


def _feature_genes() -> list[str]:
    try:
        artifact = ClusterClassifierArtifact.load()
        model = getattr(artifact, "elastic_net_model", None) or {}
        genes = list(model.get("genes") or [])
        if genes:
            return [str(g).upper() for g in genes]
    except FileNotFoundError:
        pass
    # Fallback: high-variance METABRIC genes.
    expr = load_metabric_expression()
    return expr.var(axis=1).sort_values(ascending=False).head(1500).index.astype(str).str.upper().tolist()


def build_rna_projection(n_components: int = 2, random_state: int = 20260726, force: bool = False) -> dict:
    """Fit a deterministic 2D projection (UMAP if available, else PCA) on METABRIC RNA."""
    if UMAP_REFERENCE_PATH.exists() and UMAP_TRANSFORM_PATH.exists() and not force:
        return json.loads(UMAP_META_PATH.read_text()) if UMAP_META_PATH.exists() else {"method": "cached"}

    expr = load_metabric_expression()
    labels = load_mofa_cluster_labels()
    genes = [g for g in _feature_genes() if g in expr.index]
    samples = [s for s in expr.columns if s in labels.index]
    mat = expr.loc[genes, samples].T.fillna(expr.loc[genes].median(axis=1))

    scaler = StandardScaler()
    x = scaler.fit_transform(mat.to_numpy())

    method = "pca"
    coords = None
    reducer = None
    try:
        import umap  # type: ignore

        reducer = umap.UMAP(
            n_components=n_components,
            n_neighbors=15,
            min_dist=0.1,
            metric="euclidean",
            random_state=random_state,
        )
        coords = reducer.fit_transform(x)
        method = "umap"
    except Exception:
        reducer = PCA(n_components=n_components, random_state=random_state)
        coords = reducer.fit_transform(x)
        method = "pca"

    reference = pd.DataFrame(
        {
            "sample_id": samples,
            "x": coords[:, 0],
            "y": coords[:, 1],
            "mofa_cluster": [int(labels.loc[s]) for s in samples],
        }
    )
    UMAP_REFERENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
    reference.to_parquet(UMAP_REFERENCE_PATH, index=False)
    joblib.dump({"scaler": scaler, "reducer": reducer, "genes": genes, "method": method}, UMAP_TRANSFORM_PATH)
    meta = {
        "method": method,
        "n_samples": len(samples),
        "n_genes": len(genes),
        "n_components": n_components,
        "label": (
            "RNA-only projection of METABRIC expression, colored by multi-omics MOFA cluster labels. "
            "Not the original MOFA factor space."
        ),
    }
    UMAP_META_PATH.write_text(json.dumps(meta, indent=2))
    return meta


@lru_cache(maxsize=1)
def load_projection_bundle() -> dict:
    if not UMAP_REFERENCE_PATH.exists() or not UMAP_TRANSFORM_PATH.exists():
        build_rna_projection()
    reference = pd.read_parquet(UMAP_REFERENCE_PATH)
    transform = joblib.load(UMAP_TRANSFORM_PATH)
    meta = json.loads(UMAP_META_PATH.read_text()) if UMAP_META_PATH.exists() else {}
    return {"reference": reference, "transform": transform, "meta": meta}


def project_patient(patient_expression: dict[str, float]) -> dict:
    bundle = load_projection_bundle()
    transform = bundle["transform"]
    genes = transform["genes"]
    aligned = align_patient_expression(patient_expression, reference_genes=pd.Index(genes))
    # Use raw aligned values then scale with the saved scaler (trained on raw expression).
    stats = reference_gene_stats()
    # Reconstruct approximate raw values from z if needed; prefer raw aligned values.
    values = aligned.values.reindex(genes)
    medians = stats["mean"].reindex(genes)
    values = values.fillna(medians).fillna(0.0)
    x = transform["scaler"].transform(values.to_numpy().reshape(1, -1))
    coords = transform["reducer"].transform(x)[0]
    reference = bundle["reference"]
    # Downsample reference for payload size while keeping cluster balance.
    pieces = []
    for cluster_id, group in reference.groupby("mofa_cluster"):
        pieces.append(group.sample(n=min(len(group), 80), random_state=0))
    sampled = pd.concat(pieces, ignore_index=True) if pieces else reference.head(0)
    return {
        "method": transform.get("method") or bundle["meta"].get("method", "pca"),
        "label": bundle["meta"].get(
            "label",
            "RNA-only projection colored by MOFA cluster (surrogate visualization).",
        ),
        "patient": {"x": float(coords[0]), "y": float(coords[1])},
        "reference": sampled[["sample_id", "x", "y", "mofa_cluster"]].to_dict(orient="records"),
        "n_reference_total": int(len(reference)),
        "n_reference_shown": int(len(sampled)),
        "genes_used": int(aligned.genes_found),
        "gene_coverage": float(aligned.coverage_fraction),
    }
