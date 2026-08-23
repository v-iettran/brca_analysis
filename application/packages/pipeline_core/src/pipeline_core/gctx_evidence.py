"""GCTX/L1000 drug-reversal evidence, keyed by MOFA cluster.

The 33 GB ``level5_beta_trt_cp_*.gctx`` file itself is never read at request
time -- ``jobs/refresh_gctx_cluster_drugs.py`` is an offline, host-only job
that reads it and materializes the small ``cluster_{i}_drug_targets.csv``
tables this module loads. Percentiles are computed from the ``drug_rank``
column already present in those tables (1 = strongest transcriptional
reversal of that cluster's signature).
"""

from __future__ import annotations

from functools import lru_cache

import pandas as pd

from pipeline_core.config import MOFA_CLUSTERS_DIR, N_MOFA_CLUSTERS


@lru_cache(maxsize=1)
def load_all_cluster_drug_tables() -> dict[int, pd.DataFrame]:
    tables = {}
    for cluster_id in range(N_MOFA_CLUSTERS):
        path = MOFA_CLUSTERS_DIR / f"cluster_{cluster_id}_drug_targets.csv"
        if not path.exists():
            raise FileNotFoundError(f"Missing GCTX drug-target table: {path}")
        df = pd.read_csv(path)
        df["drug_lower"] = df["drug"].str.lower().str.strip()
        n = len(df)
        # Percentile 1.0 = strongest reversal (rank 1), 0.0 = weakest.
        df["percentile"] = 1.0 - (df["drug_rank"] - 1) / max(n - 1, 1)
        tables[cluster_id] = df.set_index("drug_lower")
    return tables


def drug_evidence_for_cluster(cluster_id: int, drug_name: str) -> dict | None:
    tables = load_all_cluster_drug_tables()
    table = tables.get(cluster_id)
    if table is None:
        return None
    key = drug_name.lower().strip()
    if key not in table.index:
        return None
    row = table.loc[key]
    if isinstance(row, pd.DataFrame):  # duplicate drug rows -- take the best rank
        row = row.sort_values("drug_rank").iloc[0]
    return {
        "drug_rank": int(row["drug_rank"]),
        "reversal_score": float(row["reversal_score"]),
        "percentile": float(row["percentile"]),
        "median_score": float(row["median_score"]) if pd.notna(row["median_score"]) else None,
        "n_signatures": int(row["n_signatures"]) if pd.notna(row["n_signatures"]) else None,
        "targets": (row["targets"].split(";") if pd.notna(row.get("targets")) else []),
        "n_drugs_in_cluster": len(table),
    }


def blended_drug_evidence(cluster_probabilities: dict[int, float], drug_name: str) -> dict:
    """Blend a drug's per-cluster GCTX reversal percentile using the patient's
    soft cluster-probability vector as weights."""
    per_cluster = {}
    weighted_sum = 0.0
    weight_total = 0.0
    for cluster_id, probability in cluster_probabilities.items():
        evidence = drug_evidence_for_cluster(int(cluster_id), drug_name)
        if evidence is None:
            continue
        per_cluster[int(cluster_id)] = {"cluster_probability": probability, **evidence}
        weighted_sum += probability * evidence["percentile"]
        weight_total += probability

    blended_percentile = weighted_sum / weight_total if weight_total > 0 else None
    return {
        "drug": drug_name,
        "blended_percentile": blended_percentile,
        "per_cluster": per_cluster,
        "clusters_with_data": len(per_cluster),
    }


def top_candidate_drugs(cluster_probabilities: dict[int, float], top_n: int = 15) -> pd.DataFrame:
    """Rank all drugs seen in any cluster table by their probability-blended
    GCTX reversal percentile. This is discovery evidence only -- it never
    implies a validated pCR probability (see ``pcr_model.py``)."""
    tables = load_all_cluster_drug_tables()
    all_drug_names: set[str] = set()
    for table in tables.values():
        all_drug_names.update(table["drug"].tolist())

    rows = []
    for drug in all_drug_names:
        evidence = blended_drug_evidence(cluster_probabilities, drug)
        if evidence["blended_percentile"] is None:
            continue
        rows.append(
            {
                "drug": drug,
                "blended_percentile": evidence["blended_percentile"],
                "clusters_with_data": evidence["clusters_with_data"],
                "targets": sorted(
                    {
                        t
                        for c in evidence["per_cluster"].values()
                        for t in c.get("targets", [])
                    }
                ),
            }
        )
    result = pd.DataFrame(rows).sort_values("blended_percentile", ascending=False)
    return result.head(top_n).reset_index(drop=True)
