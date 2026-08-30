"""A8 — does the panel separate the two luminal subgroups in METABRIC?

Criteria fixed in `v3/reports/prereg_a8_within_luminal.md`. The criterion is
comparative: the panel must beat expression-matched random gene sets. A high
AUROC on its own is not a pass — that was the flaw A7 exposed.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from lifelines.statistics import multivariate_logrank_test
from sklearn.metrics import roc_auc_score

ROOT = Path(__file__).resolve().parents[2]
V2 = ROOT / "v3"
MB = V2 / "data/raw/metabric/extracted/brca_metabric"
TC = V2 / "data/raw/tcga_brca/extracted/brca_tcga_pan_can_atlas_2018/data_mrna_seq_v2_rsem.txt"
PAYLOAD = ROOT / "application/apps/api/app/data/v3/cohort_payload.json"

N_DRAWS = 200
N_DECILES = 10
RNG = np.random.default_rng(20260830)


def read_matrix(p: Path) -> pd.DataFrame:
    f = pd.read_csv(p, sep="\t", low_memory=False)
    f = f[f["Hugo_Symbol"].notna()]
    f = f.drop(columns=[c for c in ("Entrez_Gene_Id",) if c in f.columns]).set_index("Hugo_Symbol")
    return f[~f.index.duplicated(keep="first")].apply(pd.to_numeric, errors="coerce")


def zrows(f: pd.DataFrame) -> pd.DataFrame:
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
    asg = pd.read_parquet(V2 / "data/interim/v3/cluster_assignments.parquet")
    labels = asg[asg.config_id == "gmm:full:k=4"].set_index("patient_id")["cluster"].astype(int)

    print("reading matrices…")
    tcga = read_matrix(TC)
    tcga.columns = [c[:12] for c in tcga.columns]
    tcga = tcga.loc[:, ~tcga.columns.duplicated(keep="first")]
    tcga = np.log2(tcga.clip(lower=0) + 1)
    meta = read_matrix(MB / "data_mrna_illumina_microarray.txt")

    ids = [i for i in labels.index if i in tcga.columns]
    lab = labels.reindex(ids)
    universe = [g for g in tcga.index if g in meta.index]
    uset = set(universe)
    panel_shared = [g for g in panel if g in uset]
    pool = [g for g in universe if g not in set(panel)]

    clin = pd.read_csv(MB / "data_clinical_patient.txt", sep="\t", comment="#").set_index("PATIENT_ID")
    subtype = clin["CLAUDIN_SUBTYPE"]

    # Expression-matched null: bin the shared universe by mean TCGA expression and
    # reproduce the panel's decile profile in every random draw.
    mean_expr = tcga.loc[universe, ids].mean(axis=1)
    deciles = pd.qcut(mean_expr, N_DECILES, labels=False, duplicates="drop")
    panel_profile = deciles.reindex(panel_shared).value_counts().sort_index()
    pool_by_decile = {d: np.array([g for g in pool if deciles.get(g) == d]) for d in panel_profile.index}
    print(f"panel {len(panel_shared)} genes | pool {len(pool)} | matched on {len(panel_profile)} deciles")

    def draw_matched() -> list[str]:
        out: list[str] = []
        for d, n in panel_profile.items():
            avail = pool_by_decile[d]
            out.extend(RNG.choice(avail, size=min(int(n), len(avail)), replace=False))
        return out

    def axis_scores(genes: list[str]):
        tz = zrows(tcga.loc[genes, ids]).dropna(how="all")
        mz = zrows(meta.loc[genes]).dropna(how="all")
        common = [g for g in tz.index if g in mz.index]
        if len(common) < 100:
            return None
        tz, mz = tz.loc[common], mz.loc[common]
        c0 = tz.loc[:, (lab == 0).values].mean(axis=1)
        c1 = tz.loc[:, (lab == 1).values].mean(axis=1)
        cent = pd.DataFrame({0: c0, 1: c1})
        corr = standardise(mz).T @ standardise(cent) / len(common)
        return pd.Series(corr[:, 0] - corr[:, 1], index=mz.columns)

    def evaluate(genes: list[str]):
        s = axis_scores(genes)
        if s is None:
            return None
        st = subtype.reindex(s.index)
        lum = st.isin(["LumA", "LumB"])
        y = (st[lum] == "LumB").astype(int)
        if y.nunique() < 2:
            return None
        auroc = float(roc_auc_score(y, s[lum]))

        surv = clin.reindex(s.index)
        code = surv["OS_STATUS"].astype(str).str.split(":").str[0].str.strip()
        block = pd.DataFrame({
            "t": pd.to_numeric(surv["OS_MONTHS"], errors="coerce"),
            "e": pd.to_numeric(code, errors="coerce"),
            "g": (s > 0).astype(int),
        })[lum.to_numpy()].dropna(subset=["t", "e"])
        block = block[block["t"] >= 0]
        stat = float(multivariate_logrank_test(block["t"], block["g"], block["e"].astype(int)).test_statistic) \
            if block["g"].nunique() > 1 else np.nan
        p = float(multivariate_logrank_test(block["t"], block["g"], block["e"].astype(int)).p_value) \
            if block["g"].nunique() > 1 else np.nan
        return auroc, stat, p, int(lum.sum()), int(y.sum()), int(len(block))

    panel_auroc, panel_stat, panel_p, n_lum, n_lumb, n_surv = evaluate(panel_shared)
    print(f"\npanel: AUROC(LumB vs LumA) = {panel_auroc:.4f} on {n_lum} luminal samples "
          f"({n_lumb} LumB)")
    print(f"panel: within-luminal OS logrank statistic = {panel_stat:.2f} (p = {panel_p:.3e}, n={n_surv})")

    aurocs, stats = [], []
    for i in range(N_DRAWS):
        out = evaluate(draw_matched())
        if out:
            aurocs.append(out[0])
            stats.append(out[1])
        if (i + 1) % 50 == 0:
            a = np.array(aurocs)
            print(f"  {i+1}/{N_DRAWS} — random AUROC median {np.median(a):.4f}, "
                  f">= panel: {(a >= panel_auroc).sum()}")

    a, s_arr = np.array(aurocs), np.array(stats)
    beat_a = int((a >= panel_auroc).sum())
    p_a = (beat_a + 1) / (len(a) + 1)
    beat_s = int((s_arr >= panel_stat).sum())
    p_s = (beat_s + 1) / (len(s_arr) + 1)

    print("\n" + "=" * 64)
    print(f"  PRIMARY  panel AUROC        : {panel_auroc:.4f}")
    print(f"           matched random     : median {np.median(a):.4f}, p95 {np.percentile(a,95):.4f}, max {a.max():.4f}")
    print(f"           random >= panel    : {beat_a}/{len(a)}   empirical p = {p_a:.4f}")
    print(f"           verdict            : {'PASS' if p_a <= 0.05 else 'FAIL'}")
    print(f"  SECOND'Y panel OS statistic : {panel_stat:.2f}")
    print(f"           matched random     : median {np.median(s_arr):.2f}, p95 {np.percentile(s_arr,95):.2f}")
    print(f"           random >= panel    : {beat_s}/{len(s_arr)}   empirical p = {p_s:.4f}")
    print(f"           verdict            : {'PASS' if p_s <= 0.05 else 'FAIL'}")
    print("=" * 64)

    gate = {
        "gate": "a8_within_luminal_transfer",
        "preregistered": "v3/reports/prereg_a8_within_luminal.md",
        "passed": bool(p_a <= 0.05),
        "null": "expression-decile-matched random gene sets, drawn outside the panel",
        "n_draws": len(a),
        "n_genes": len(panel_shared),
        "primary": {"metric": "AUROC LumB vs LumA on the subgroup-0-minus-1 axis",
                    "panel": round(panel_auroc, 4),
                    "random_median": round(float(np.median(a)), 4),
                    "random_p95": round(float(np.percentile(a, 95)), 4),
                    "random_max": round(float(a.max()), 4),
                    "n_random_ge_panel": beat_a, "empirical_p": round(p_a, 4),
                    "n_luminal": n_lum, "n_lumb": n_lumb},
        "secondary": {"metric": "within-luminal OS logrank, split by axis sign",
                      "panel_statistic": round(panel_stat, 3), "panel_p": panel_p,
                      "random_median": round(float(np.median(s_arr)), 3),
                      "n_random_ge_panel": beat_s, "empirical_p": round(p_s, 4),
                      "passed": bool(p_s <= 0.05)},
    }
    with (V2 / "reports" / "gates.jsonl").open("a") as fh:
        fh.write(json.dumps(gate) + "\n")
    (V2 / "reports" / "a8_within_luminal.json").write_text(json.dumps(gate, indent=2))
    print(f"\nappended to {V2/'reports'/'gates.jsonl'}")


if __name__ == "__main__":
    main()
