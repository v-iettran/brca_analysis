"""A7 — transfer the v3 gene panel to METABRIC.

Criteria are fixed in `v3/reports/prereg_a7_metabric_transfer.md`, written before
this script was run. Nothing here may be tuned to improve the outcome.

The subgroups cannot be recomputed on METABRIC: they are defined on the malignant
compartment after BayesPrism deconvolution of RSEM counts, and METABRIC is
microarray with no counts. So the reference is built from *bulk* TCGA, making this
a bulk-against-bulk comparison, and the transfer happens in gene space rather than
by re-encoding anything through the VAE.
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

SCORED = [0, 1, 2]          # subgroup 3 (n=13) excluded in advance
DEGENERACY_LIMIT = 0.80
N_PERMUTATIONS = 1000
RNG = np.random.default_rng(20260830)

# METABRIC's CLAUDIN_SUBTYPE uses PAM50 names plus claudin-low and NC. Only the
# shared vocabulary is compared; claudin-low and NC have no PAM50 counterpart and
# are held out of the composition matrix rather than folded into a nearby class.
SHARED_SUBTYPES = ["LumA", "LumB", "Her2", "Basal", "Normal"]


def log(msg: str) -> None:
    print(msg, flush=True)


def read_matrix(path: Path, symbol_col: str = "Hugo_Symbol") -> pd.DataFrame:
    frame = pd.read_csv(path, sep="\t", low_memory=False)
    frame = frame[frame[symbol_col].notna()]
    drop = [c for c in ("Entrez_Gene_Id",) if c in frame.columns]
    frame = frame.drop(columns=drop).set_index(symbol_col)
    frame = frame[~frame.index.duplicated(keep="first")]
    return frame.apply(pd.to_numeric, errors="coerce")


def zscore_rows(frame: pd.DataFrame) -> pd.DataFrame:
    """Per gene, within this cohort only. No cross-cohort statistic is fitted."""
    mu = frame.mean(axis=1)
    sd = frame.std(axis=1).replace(0, np.nan)
    return frame.sub(mu, axis=0).div(sd, axis=0)


def event_indicator(series: pd.Series) -> pd.Series:
    """cBioPortal encodes status as `0:LIVING` / `1:DECEASED`, `0:Not Recurred` /
    `1:Recurred`. Substring matching is unsafe -- "Not Recurred" contains
    "Recurred" -- so the leading numeric code is the only thing read. Rows with no
    status are left as NA and dropped, never silently censored.
    """
    code = series.astype(str).str.split(":").str[0].str.strip()
    return pd.to_numeric(code, errors="coerce")


def composition(labels: pd.Series, subtypes: pd.Series, groups: list[int]) -> pd.DataFrame:
    out = {}
    for g in groups:
        ids = labels[labels == g].index
        counts = Counter(s for s in subtypes.reindex(ids).dropna() if s in SHARED_SUBTYPES)
        total = sum(counts.values())
        out[g] = {s: (counts.get(s, 0) / total if total else np.nan) for s in SHARED_SUBTYPES}
    return pd.DataFrame(out).T[SHARED_SUBTYPES]


def main() -> None:
    payload = json.loads(PAYLOAD.read_text())
    panel = sorted({r["feature"] for r in payload["cluster_profiles"]
                    if (r.get("family") or r.get("kind")) == "gene"})
    tcga_pam50 = pd.Series(payload["pam50"])

    assign = pd.read_parquet(ASSIGN)
    tcga_labels = (assign[assign.config_id == "gmm:full:k=4"]
                   .set_index("patient_id")["cluster"].astype(int))
    log(f"TCGA subgroups: n={len(tcga_labels)} {dict(sorted(Counter(tcga_labels).items()))}")

    log("reading TCGA bulk RSEM…")
    tcga = read_matrix(TCGA_EXPR)
    tcga.columns = [c[:12] for c in tcga.columns]          # TCGA-XX-XXXX barcode
    tcga = tcga.loc[:, ~tcga.columns.duplicated(keep="first")]
    tcga = np.log2(tcga.clip(lower=0) + 1)

    log("reading METABRIC microarray…")
    meta = read_matrix(METABRIC / "data_mrna_illumina_microarray.txt")

    shared = [g for g in panel if g in tcga.index and g in meta.index]
    log(f"panel genes usable on both platforms: {len(shared)}/{len(panel)} "
        f"({100 * len(shared) / len(panel):.1f}%)")

    ids = [i for i in tcga_labels.index if i in tcga.columns]
    log(f"TCGA patients with expression: {len(ids)}/{len(tcga_labels)}")

    tz = zscore_rows(tcga.loc[shared, ids]).dropna(how="all")
    mz = zscore_rows(meta.loc[shared]).dropna(how="all")
    common = [g for g in tz.index if g in mz.index]
    tz, mz = tz.loc[common], mz.loc[common]
    log(f"genes after z-scoring within each cohort: {len(common)}")

    labels_here = tcga_labels.reindex(ids)
    centroids = pd.DataFrame(
        {int(g): tz.loc[:, (labels_here == g).values].mean(axis=1) for g in sorted(labels_here.unique())}
    )

    # Pearson correlation to each centroid, computed as a dot product of the
    # column-standardised matrices.
    def standardise(df: pd.DataFrame) -> np.ndarray:
        arr = df.to_numpy(dtype=float)
        arr = arr - np.nanmean(arr, axis=0, keepdims=True)
        arr = arr / np.nanstd(arr, axis=0, keepdims=True)
        return np.nan_to_num(arr)

    corr = standardise(mz).T @ standardise(centroids) / len(common)
    called = pd.Series(centroids.columns.to_numpy()[np.argmax(corr, axis=1)],
                       index=mz.columns, name="subgroup")
    margin = np.sort(corr, axis=1)[:, -1] - np.sort(corr, axis=1)[:, -2]

    dist = dict(sorted(Counter(called).items()))
    largest = max(dist.values()) / len(called)
    log(f"\nMETABRIC assignment: n={len(called)} {dist}")
    log(f"  largest subgroup share: {largest:.1%}  (degeneracy limit {DEGENERACY_LIMIT:.0%})")
    log(f"  median assignment margin: {np.median(margin):.4f}")

    clinical = pd.read_csv(METABRIC / "data_clinical_patient.txt", sep="\t", comment="#")
    clinical = clinical.set_index("PATIENT_ID")
    subtypes = clinical["CLAUDIN_SUBTYPE"].reindex(called.index)

    tcga_comp = composition(labels_here, tcga_pam50.reindex(ids), SCORED)
    meta_comp = composition(called, subtypes, SCORED)
    log("\nTCGA reference composition:\n" + tcga_comp.round(3).to_string())
    log("\nMETABRIC transferred composition:\n" + meta_comp.round(3).to_string())

    majority_ok = sum(
        1 for g in SCORED
        if not meta_comp.loc[g].isna().all()
        and tcga_comp.loc[g].idxmax() == meta_comp.loc[g].idxmax()
    )
    paired = np.array([[tcga_comp.loc[g].to_numpy(), meta_comp.loc[g].to_numpy()] for g in SCORED])
    a, b = paired[:, 0].ravel(), paired[:, 1].ravel()
    ok = ~(np.isnan(a) | np.isnan(b))
    comp_r = float(np.corrcoef(a[ok], b[ok])[0, 1])

    null_r = []
    for _ in range(N_PERMUTATIONS):
        shuffled = pd.Series(RNG.permutation(called.to_numpy()), index=called.index)
        mc = composition(shuffled, subtypes, SCORED)
        bb = np.array([mc.loc[g].to_numpy() for g in SCORED]).ravel()
        m = ~(np.isnan(a) | np.isnan(bb))
        null_r.append(np.corrcoef(a[m], bb[m])[0, 1] if m.sum() > 2 else np.nan)
    null_r = np.array([v for v in null_r if not np.isnan(v)])
    comp_p = float((np.sum(null_r >= comp_r) + 1) / (len(null_r) + 1))

    log(f"\nPrimary — subtype concordance")
    log(f"  majority agrees for {majority_ok}/3 subgroups (need >= 2)")
    log(f"  composition r = {comp_r:.3f} (need > 0.5), permutation p = {comp_p:.4f} (need < 0.05)")

    surv = clinical.reindex(called.index)
    results = {}
    for label, tcol, ecol in (
        ("os", "OS_MONTHS", "OS_STATUS"),
        ("rfs", "RFS_MONTHS", "RFS_STATUS"),
    ):
        if tcol not in surv.columns:
            continue
        block = pd.DataFrame({
            "t": pd.to_numeric(surv[tcol], errors="coerce"),
            "e": event_indicator(surv[ecol]),
            "g": called,
        }).dropna(subset=["t", "e"])
        block = block[block["t"] >= 0]
        block["e"] = block["e"].astype(int)
        res = multivariate_logrank_test(block["t"], block["g"], block["e"])
        results[label] = {"p": float(res.p_value), "statistic": float(res.test_statistic),
                          "n": int(len(block)), "n_events": int(block["e"].sum())}
        log(f"\nSecondary — {label.upper()}: p = {res.p_value:.3e}, "
            f"statistic = {res.test_statistic:.2f}, n = {len(block)}, events = {int(block['e'].sum())}")

    os_block = pd.DataFrame({
        "t": pd.to_numeric(surv["OS_MONTHS"], errors="coerce"),
        "e": event_indicator(surv["OS_STATUS"]),
        "g": called,
    }).dropna(subset=["t", "e"])
    os_block = os_block[os_block["t"] >= 0]
    os_block["e"] = os_block["e"].astype(int)
    null_stat = []
    for _ in range(N_PERMUTATIONS):
        g = RNG.permutation(os_block["g"].to_numpy())
        null_stat.append(multivariate_logrank_test(os_block["t"], g, os_block["e"]).test_statistic)
    null_stat = np.array(null_stat)
    observed = results["os"]["statistic"]
    pct95 = float(np.percentile(null_stat, 95))
    log(f"\nNegative control: observed {observed:.2f} vs null 95th percentile {pct95:.2f} "
        f"-> {'exceeds' if observed > pct95 else 'DOES NOT exceed'}")

    degenerate = largest > DEGENERACY_LIMIT
    primary = (majority_ok >= 2) and (comp_r > 0.5) and (comp_p < 0.05)
    secondary = results.get("os", {}).get("p", 1.0) < 0.05
    control = observed > pct95
    passed = bool(primary and secondary and control and not degenerate)

    log("\n" + "=" * 62)
    log(f"  degeneracy guard : {'FAIL' if degenerate else 'pass'} ({largest:.1%})")
    log(f"  primary          : {'pass' if primary else 'FAIL'}")
    log(f"  secondary (OS)   : {'pass' if secondary else 'FAIL'}")
    log(f"  negative control : {'pass' if control else 'FAIL'}")
    log(f"  A7 OVERALL       : {'PASS' if passed else 'FAIL'}")
    log("=" * 62)

    gate = {
        "gate": "a7_metabric_panel_transfer",
        "passed": passed,
        "preregistered": "v3/reports/prereg_a7_metabric_transfer.md",
        "cohort": {"source": "METABRIC", "n_assigned": int(len(called)),
                   "n_panel_genes_used": len(common), "n_panel_genes_total": len(panel)},
        "assignment_distribution": {str(k): int(v) for k, v in dist.items()},
        "largest_share": round(largest, 4),
        "median_margin": round(float(np.median(margin)), 4),
        "primary": {"majority_agree": majority_ok, "of": len(SCORED),
                    "composition_r": round(comp_r, 4), "permutation_p": round(comp_p, 4),
                    "passed": primary},
        "secondary": results,
        "negative_control": {"observed_statistic": round(observed, 3),
                             "null_p95": round(pct95, 3), "passed": control},
        "tcga_reference": {"logrank_p": 0.0380, "n": 1082, "n_events": 151},
        "excluded": {"subgroup_3": "n=13 in TCGA; excluded before running"},
    }
    dest = V2 / "reports" / "gates.jsonl"
    with dest.open("a") as fh:
        fh.write(json.dumps(gate) + "\n")
    log(f"\nappended to {dest}")
    (V2 / "reports" / "a7_metabric_transfer.json").write_text(json.dumps(gate, indent=2))


if __name__ == "__main__":
    main()
