from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class ClusterPredictionOut(BaseModel):
    probabilities: dict[int, float]
    top_cluster: int
    top_probability: float
    confidence_level: Literal["high", "moderate", "low", "abstain"]
    gene_coverage: float
    genes_found: int
    genes_requested: int
    method_used: Literal["signature_similarity", "elastic_net"]
    warnings: list[str]


class ClusterGeneOut(BaseModel):
    gene: str
    coefficient: float
    p_value: float
    fdr: float
    direction: Literal["higher", "lower"]


class ClusterDetailOut(BaseModel):
    cluster_id: int
    patient_probability: float
    n_in_cluster: int
    n_out_cluster: int
    genes_tested: int
    significant_gene_count: int
    coefficient_interpretation: str
    positive_genes: list[ClusterGeneOut]
    negative_genes: list[ClusterGeneOut]
