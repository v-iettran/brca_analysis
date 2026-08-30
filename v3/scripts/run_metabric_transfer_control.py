"""A7 negative control — would any 2140 genes have done as well?

Added AFTER A7 passed, and recorded as post-hoc. It can only weaken the claim,
never rescue it: if random gene sets separate METABRIC survival as well as the
panel does, then the A7 result reflects the fact that breast expression carries
prognostic structure, not that this particular panel transfers.

Same transfer procedure throughout. The only thing that changes is which genes
build the centroids.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
from lifelines.statistics import multivariate_logrank_test

ROOT = Path(__file__).resolve().parents[2]
V2 = ROOT / "v3"
METABRIC = V2 / "data/raw/metabric/extracted/brca_metabric"
TCGA_EXPR = V2 / "data/raw/tcga_brca/extracted/brca_tcga_pan_can_atlas_2018/data_mrna_seq_v2_rsem.txt"
PAYLOAD = ROOT / "application/apps/api/app/data/v3/cohort_payload.json"
ASSIGN = V2 / "data/interim/v3/cluster_assignments.parquet"

N_DRAWS = 200
RNG = np.random.default_rng(7)


def read_matrix(path: Path) -> pd.DataFrame:
    f = pd.read_csv(path, sep="\t", low_memory=False)
    f = f[f["Hugo_Symbol"].notna()].drop(columns=[c for c in ("Entrez_Gene_Id",) if c in f.columns])
    f = f.set_index("Hugo_Symbol")
    f = f[~f.index.duplicated(keep="first")]
    return f.apply(pd.to_numeric, errors="coerce")


def zscore_rows(f: pd.DataFrame) -> pd.DataFrame:
    return f.sub(f.mean(axis=1), axis=0).div(f.std(axis=1).replace(0, np.nan), axis=0)


def standardise(df: pd.DataFrame) -> np.ndarray:
    a = df.to_numpy(dtype=float)
    a = a - np.nanmean(a, axis=0, keepdims=True)
    a = a / np.nanstd(a, axis=0, keepdims=True)
    return np.nan_to_num(a)


def main() -> None:
    payload = json.loads(PAYLOAD.read_text())
    panel = sorted({r["feature"] for r in payload["cluster_profiles"]
                    if (r.get("family") or r.get("kind")) == "gene"})
    assign = pd.read_parquet(ASSIGN)
    labels = assign[assign.config_id == "gmm:full:k=4"].set_index("patient_id")["cluster"].astype(int)

    tcga = read_matrix(TCGA_EXPR)
    tcga.columns = [c[:12] for c in tcga.columns]
    tcga = tcga.loc[:, ~tcga.columns.duplicated(keep="first")]
    tcga = np.log2(tcga.clip(lower=0) + 1)
    meta = read_matrix(METABRIC / "data_mrna_illumina_microarray.txt")

    ids = [i for i in labels.index if i in tcga.columns]
    lab = labels.reindex(ids)
    universe = [g for g in tcga.index if g in meta.index]
    panel_shared = [g for g in panel if g in set(universe)]
    pool = sorted(set(universe) - set(panel))
    print(f"universe {len(universe)} genes | panel {len(panel_shared)} | draw pool {len(pool)}")

    clinical = pd.read_csv(METABRIC / "data_clinical_patient.txt", sep="\t", comment="#").set_index("PATIENT_ID")

    def transfer_statistic(genes: list[str]) -> float | None:
        tz = zscore_rows(tcga.loc[genes, ids]).dropna(how="all")
        mz = zscore_rows(meta.loc[genes]).dropna(how="all")
        common = [g for g in tz.index if g in mz.index]
        if len(common) < 100:
            return None
        tz, mz = tz.loc[common], mz.loc[common]
        cent = pd.DataFrame({int(g): tz.loc[:, (lab == g).values].mean(axis=1) for g in sorted(lab.unique())})
        corr = standardise(mz).T @ standardise(cent) / len(common)
        called = pd.Series(cent.columns.to_numpy()[np.argmax(corr, axis=1)], index=mz.columns)
        s = clinical.reindex(called.index)
        code = s["OS_STATUS"].astype(str).str.split(":").str[0].str.strip()
        block = pd.DataFrame({"t": pd.to_numeric(s["OS_MONTHS"], errors="coerce"),
                              "e": pd.to_numeric(code, errors="coerce"),
                              "g": called}).dropna(subset=["t", "e"])
        block = block[block["t"] >= 0]
        if block["g"].nunique() < 2:
            return None
        return float(multivariate_logrank_test(block["t"], block["g"], block["e"].astype(int)).test_statistic)

    observed = transfer_statistic(panel_shared)
    print(f"\npanel statistic: {observed:.2f}")

    draws = []
    for i in range(N_DRAWS):
        genes = list(RNG.choice(pool, size=len(panel_shared), replace=False))
        st = transfer_statistic(genes)
        if st is not None:
            draws.append(st)
        if (i + 1) % 25 == 0:
            arr = np.array(draws)
            print(f"  {i+1}/{N_DRAWS} draws — random median {np.median(arr):.2f}, "
                  f"max {arr.max():.2f}, >= panel: {(arr >= observed).sum()}")

    arr = np.array(draws)
    beat = int((arr >= observed).sum())
    p = (beat + 1) / (len(arr) + 1)
    print("\n" + "=" * 62)
    print(f"  panel                 : {observed:.2f}")
    print(f"  random gene sets      : median {np.median(arr):.2f}, "
          f"p95 {np.percentile(arr, 95):.2f}, max {arr.max():.2f}  (n={len(arr)})")
    print(f"  random >= panel       : {beat}/{len(arr)}  (empirical p = {p:.4f})")
    print(f"  VERDICT               : {'panel is not special' if p > 0.05 else 'panel beats random gene sets'}")
    print("=" * 62)

    out = {
        "gate": "a7_control_random_gene_sets",
        "post_hoc": True,
        "note": "Added after A7 passed. Can only weaken the A7 claim, never rescue it.",
        "panel_statistic": round(observed, 3),
        "n_draws": len(arr),
        "random_median": round(float(np.median(arr)), 3),
        "random_p95": round(float(np.percentile(arr, 95)), 3),
        "random_max": round(float(arr.max()), 3),
        "n_random_ge_panel": beat,
        "empirical_p": round(p, 4),
        "passed": bool(p <= 0.05),
    }
    with (V2 / "reports" / "gates.jsonl").open("a") as fh:
        fh.write(json.dumps(out) + "\n")
    (V2 / "reports" / "a7_control_random_gene_sets.json").write_text(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
