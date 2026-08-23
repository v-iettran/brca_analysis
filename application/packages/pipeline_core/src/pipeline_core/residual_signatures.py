"""Patient residual signatures: z_patient - cluster_centroid.

List 2 reverses this residual on the same gene scale used for List 1
(cluster one-vs-rest signatures). This does not imply a cancer-to-normal
transition; it personalizes the cluster-state reversal query.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np
import pandas as pd

from pipeline_core.config import (
    CLUSTER_CENTROIDS_PATH,
    DEFAULT_TOP_DOWN,
    DEFAULT_TOP_UP,
    MAX_SIGNATURE_GENES,
    MIN_SIGNATURE_GENES,
    MOFA_CLUSTERS_DIR,
    N_MOFA_CLUSTERS,
)
from pipeline_core.expression import align_patient_expression, load_metabric_expression, load_mofa_cluster_labels, reference_gene_stats


@dataclass
class SignatureArm:
    genes: list[str]
    values: dict[str, float]


@dataclass
class ResidualSignature:
    cluster_id: int
    residual: pd.Series
    up: SignatureArm
    down: SignatureArm
    top_up: int
    top_down: int
    coverage_fraction: float
    genes_used: int
    warnings: list[str]


@dataclass
class ClusterSignatureArms:
    cluster_id: int
    up: SignatureArm
    down: SignatureArm
    top_up: int
    top_down: int
    table: pd.DataFrame


def clamp_signature_size(n: int | None, default: int) -> int:
    if n is None:
        return default
    return int(max(MIN_SIGNATURE_GENES, min(MAX_SIGNATURE_GENES, n)))


@lru_cache(maxsize=1)
def load_cluster_centroids() -> pd.DataFrame:
    """Rows = genes, columns = cluster ids as strings. Values are reference z-means."""
    if CLUSTER_CENTROIDS_PATH.exists():
        df = pd.read_parquet(CLUSTER_CENTROIDS_PATH)
        df.index = df.index.astype(str).str.upper()
        return df

    # Build on the fly if the offline job has not been run yet.
    return build_cluster_centroids(force=True)


def build_cluster_centroids(force: bool = False) -> pd.DataFrame:
    if CLUSTER_CENTROIDS_PATH.exists() and not force:
        return load_cluster_centroids()

    expr = load_metabric_expression()
    labels = load_mofa_cluster_labels()
    stats = reference_gene_stats()
    common_samples = [s for s in expr.columns if s in labels.index]
    expr = expr[common_samples]
    labels = labels.loc[common_samples]

    means = stats["mean"].reindex(expr.index)
    sds = stats["sd"].reindex(expr.index).replace(0, np.nan)
    z = expr.sub(means, axis=0).div(sds, axis=0)

    cols = {}
    for cluster_id in range(N_MOFA_CLUSTERS):
        members = labels[labels == cluster_id].index
        if len(members) == 0:
            continue
        cols[str(cluster_id)] = z[members].mean(axis=1)

    centroids = pd.DataFrame(cols)
    centroids.index = centroids.index.astype(str).str.upper()
    CLUSTER_CENTROIDS_PATH.parent.mkdir(parents=True, exist_ok=True)
    centroids.to_parquet(CLUSTER_CENTROIDS_PATH)
    return centroids


def load_cluster_signature_table(cluster_id: int) -> pd.DataFrame:
    path = MOFA_CLUSTERS_DIR / f"cluster_{cluster_id}_signature.csv"
    if not path.exists():
        raise FileNotFoundError(f"Missing cluster signature: {path}")
    sig = pd.read_csv(path)
    sig["gene"] = sig["gene"].astype(str).str.upper()
    return sig.sort_values("coef", ascending=False)


def cluster_signature_arms(
    cluster_id: int, top_up: int | None = None, top_down: int | None = None
) -> ClusterSignatureArms:
    top_up = clamp_signature_size(top_up, DEFAULT_TOP_UP)
    top_down = clamp_signature_size(top_down, DEFAULT_TOP_DOWN)
    table = load_cluster_signature_table(cluster_id)
    up_rows = table[table["coef"] > 0].sort_values("coef", ascending=False).head(top_up)
    down_rows = table[table["coef"] < 0].sort_values("coef", ascending=True).head(top_down)
    return ClusterSignatureArms(
        cluster_id=cluster_id,
        up=SignatureArm(
            genes=up_rows["gene"].tolist(),
            values={g: float(v) for g, v in zip(up_rows["gene"], up_rows["coef"])},
        ),
        down=SignatureArm(
            genes=down_rows["gene"].tolist(),
            values={g: float(v) for g, v in zip(down_rows["gene"], down_rows["coef"])},
        ),
        top_up=top_up,
        top_down=top_down,
        table=table,
    )


def patient_residual_signature(
    patient_expression: dict[str, float],
    cluster_id: int,
    top_up: int | None = None,
    top_down: int | None = None,
) -> ResidualSignature:
    """Compute z_patient - mu_cluster and select residual up/down arms."""
    top_up = clamp_signature_size(top_up, DEFAULT_TOP_UP)
    top_down = clamp_signature_size(top_down, DEFAULT_TOP_DOWN)
    warnings: list[str] = []

    centroids = load_cluster_centroids()
    cluster_key = str(int(cluster_id))
    if cluster_key not in centroids.columns:
        raise KeyError(f"No centroid for MOFA cluster {cluster_id}")

    aligned = align_patient_expression(patient_expression, reference_genes=centroids.index)
    centroid = centroids[cluster_key]
    common = aligned.z_scores.index.intersection(centroid.index)
    residual = aligned.z_scores.loc[common] - centroid.loc[common]
    residual = residual.replace([np.inf, -np.inf], np.nan).dropna()

    if residual.empty:
        warnings.append("Residual signature is empty after alignment to the cluster centroid.")
        empty = SignatureArm(genes=[], values={})
        return ResidualSignature(
            cluster_id=int(cluster_id),
            residual=residual,
            up=empty,
            down=empty,
            top_up=top_up,
            top_down=top_down,
            coverage_fraction=aligned.coverage_fraction,
            genes_used=0,
            warnings=warnings,
        )

    up_rows = residual.sort_values(ascending=False).head(top_up)
    up_rows = up_rows[up_rows > 0]
    down_rows = residual.sort_values(ascending=True).head(top_down)
    down_rows = down_rows[down_rows < 0]

    if len(up_rows) < MIN_SIGNATURE_GENES or len(down_rows) < MIN_SIGNATURE_GENES:
        warnings.append(
            f"Residual arms are thin (up={len(up_rows)}, down={len(down_rows)}); "
            "List 2 evidence will be low-confidence."
        )

    return ResidualSignature(
        cluster_id=int(cluster_id),
        residual=residual,
        up=SignatureArm(genes=up_rows.index.tolist(), values={g: float(v) for g, v in up_rows.items()}),
        down=SignatureArm(
            genes=down_rows.index.tolist(), values={g: float(v) for g, v in down_rows.items()}
        ),
        top_up=top_up,
        top_down=top_down,
        coverage_fraction=aligned.coverage_fraction,
        genes_used=int(len(residual)),
        warnings=warnings,
    )


def signature_to_payload(sig: ClusterSignatureArms | ResidualSignature) -> dict:
    if isinstance(sig, ClusterSignatureArms):
        table = sig.table.set_index("gene")
        genes = []
        for gene, coef in list(sig.up.values.items()) + list(sig.down.values.items()):
            row = table.loc[gene] if gene in table.index else None
            genes.append(
                {
                    "gene": gene,
                    "effect": coef,
                    "direction": "up" if coef > 0 else "down",
                    "pval": float(row["pval"]) if row is not None and "pval" in row else None,
                    "fdr": float(row["fdr"]) if row is not None and "fdr" in row else None,
                    "literature_count": None,
                }
            )
        genes.sort(key=lambda g: abs(g["effect"]), reverse=True)
        return {
            "kind": "cluster",
            "cluster_id": sig.cluster_id,
            "top_up": sig.top_up,
            "top_down": sig.top_down,
            "n_up": len(sig.up.genes),
            "n_down": len(sig.down.genes),
            "genes": genes,
        }

    genes = []
    for gene, effect in list(sig.up.values.items()) + list(sig.down.values.items()):
        genes.append(
            {
                "gene": gene,
                "effect": effect,
                "direction": "up" if effect > 0 else "down",
                "pval": None,
                "fdr": None,
                "literature_count": None,
            }
        )
    genes.sort(key=lambda g: abs(g["effect"]), reverse=True)
    return {
        "kind": "residual",
        "cluster_id": sig.cluster_id,
        "top_up": sig.top_up,
        "top_down": sig.top_down,
        "n_up": len(sig.up.genes),
        "n_down": len(sig.down.genes),
        "coverage_fraction": sig.coverage_fraction,
        "genes_used": sig.genes_used,
        "warnings": sig.warnings,
        "genes": genes,
    }
