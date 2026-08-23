#!/usr/bin/env python3
"""Build cluster RNA centroids and RNA-only UMAP/PCA projection artifacts."""

from __future__ import annotations

from pipeline_core.embedding import build_rna_projection
from pipeline_core.residual_signatures import build_cluster_centroids


def main() -> None:
    print("Building MOFA-cluster RNA centroids on reference-z scale ...")
    centroids = build_cluster_centroids(force=True)
    print(f"  centroids shape={centroids.shape}")
    print("Building RNA-only projection (UMAP if available, else PCA) ...")
    meta = build_rna_projection(force=True)
    print(f"  projection method={meta.get('method')} samples={meta.get('n_samples')} genes={meta.get('n_genes')}")
    print("Done.")


if __name__ == "__main__":
    main()
