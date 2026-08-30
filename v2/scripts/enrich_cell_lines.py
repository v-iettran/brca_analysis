#!/usr/bin/env python3
"""Make the nearest-cell-line panel explainable.

Four things the panel could not previously say, all from data already on disk:

1. **What the fingerprint axes are.** `assemble_v3_real` fits a joint PCA and
   then discards `components_`, so the five bars had no meaning attached. This
   refits the same PCA with the same parameters and persists, per component, its
   variance share and its strongest positive and negative loading genes.
2. **Comparable fingerprints.** `_fingerprint` divided by each line's own peak,
   so exactly one bar was pinned to +/-1.0 for every line and no two lines could
   be compared. Normalisation now happens across the retrieved set.
3. **Why this line.** DepMap's `ModelSubtypeFeatures`, `OncotreeSubtype` and
   `PrimaryOrMetastasis` were read and dropped; PAM50 was carried but never
   compared against the patient's own call.
4. **What was actually tested.** GDSC ships MIN_CONC/MAX_CONC/AUC/Z_SCORE/RMSE
   and the pipeline used none of them, so an IC50 extrapolated far beyond the
   tested range looked identical to a measured one.

Does not retune k, refit clusters, or touch any gate.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.decomposition import PCA

V2_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V2_ROOT / "src"))

from cluster_stats import annotate_clusters  # noqa: E402
from nearest_lines import attach_gdsc_curves  # noqa: E402
from v3_payload import copy_payloads_to_app, v3_interim  # noqa: E402
from v3_real import (  # noqa: E402
    depmap_lines,
    label_cell_lines_pam50,
    load_gdsc,
    load_intrinsic,
    load_pk,
)

# Breast comparators worth showing whether or not they were retrieved, plus
# every reversal candidate GDSC actually measured on the line — the panel exists
# to ask what happened to the retrieved compounds, and previously only four
# hard-coded names could ever appear.
SOC_COMPARATORS = ["palbociclib", "tamoxifen", "lapatinib", "fulvestrant"]
MARKERS = ("ESR1", "ERBB2")
PROLIF = ("MKI67", "CCNB1", "AURKA")
N_LOADINGS = 4


def pam50_series(v2_root: Path, ids: list[str]) -> pd.Series | None:
    clin = next((v2_root / "data" / "raw" / "tcga_brca").rglob("*clinical_patient.txt"), None)
    if clin is None:
        return None
    frame = pd.read_csv(clin, sep="\t", comment="#")
    if "PATIENT_ID" not in frame.columns or "SUBTYPE" not in frame.columns:
        return None
    frame = frame.set_index(frame["PATIENT_ID"].astype(str).str[:12])
    from pam50 import normalize_pam50_label

    return frame["SUBTYPE"].map(normalize_pam50_label).reindex(ids)


def main() -> int:
    dest = v3_interim(V2_ROOT)
    repo_root = V2_ROOT.parent

    expr = load_intrinsic(V2_ROOT)
    expr.index = expr.index.astype(str).str[:12]
    expr = expr[~expr.index.duplicated(keep="first")]
    ids = list(expr.index)
    print(f"intrinsic {expr.shape}")

    cell_expr, cell_meta = depmap_lines(repo_root, [str(g) for g in expr.columns])
    if cell_expr is None or cell_expr.empty:
        print("STOP: DepMap breast expression unavailable")
        return 2

    # Reproduce assemble_v3_real's joint space exactly (v3_real.py:420-442).
    shared = [g for g in cell_expr.columns if g in expr.columns and np.isfinite(cell_expr[g].to_numpy(float)).all()]
    cell_clean = cell_expr[shared].astype(float)
    keep = [g for g in shared if cell_clean[g].std() > 1e-8]
    cell_clean = cell_clean[keep]
    tumour_mat = np.nan_to_num(expr[keep].to_numpy(float))
    cell_mat = cell_clean.to_numpy(float)
    cell_mat = (cell_mat - cell_mat.mean(axis=0)) / (cell_mat.std(axis=0) + 1e-9)
    joint = PCA(n_components=min(10, len(keep), len(cell_mat) - 1), whiten=True, random_state=0)
    joint.fit(np.vstack([tumour_mat, cell_mat]))
    tumour_proj = joint.transform(tumour_mat)
    cell_proj = joint.transform(cell_mat)
    print(f"joint PCA {joint.n_components_} components over {len(keep)} genes")

    # 1. Name the axes.
    axes = []
    for i in range(min(5, joint.n_components_)):
        loading = pd.Series(joint.components_[i], index=keep)
        up = loading.sort_values(ascending=False).head(N_LOADINGS)
        down = loading.sort_values().head(N_LOADINGS)
        axes.append(
            {
                "component": i + 1,
                "variance_ratio": float(joint.explained_variance_ratio_[i]),
                "top_positive": [str(g) for g in up.index],
                "top_negative": [str(g) for g in down.index],
            }
        )
        print(f"  PC{i+1} {joint.explained_variance_ratio_[i]:.1%} +{list(up.index)[:3]} -{list(down.index)[:3]}")

    pam = pam50_series(V2_ROOT, ids)
    if pam is not None:
        calls = label_cell_lines_pam50(expr, pam, cell_clean)
        if calls is not None:
            cell_meta["pam50"] = calls.reindex(cell_meta.index)

    # Marker means per cell line, on the same reduction used for tumour clusters.
    line_markers = {}
    for line_id in cell_clean.index:
        row = cell_clean.loc[line_id]
        line_markers[str(line_id)] = {
            m: float(row[m]) for m in MARKERS if m in cell_clean.columns
        } | {
            "prolif": float(np.mean([row[g] for g in PROLIF if g in cell_clean.columns]))
            if any(g in cell_clean.columns for g in PROLIF)
            else 0.0
        }

    cell_index = {str(v): i for i, v in enumerate(cell_clean.index)}
    tumour_index = {pid: i for i, pid in enumerate(ids)}

    gdsc = load_gdsc(V2_ROOT)
    pk = load_pk(V2_ROOT)
    if gdsc is None:
        print("WARN: GDSC2 not loaded; curves left unchanged")

    # Coordinates in the joint space, so a card can *show* where a line sits
    # relative to the cohort rather than only asserting a similarity number.
    # This is the space the cosine is measured in, so the picture and the number
    # are the same claim.
    rng = np.random.default_rng(0)
    sample = rng.choice(len(ids), size=min(400, len(ids)), replace=False)
    joint_payload = {
        "axes": [1, 2],
        "variance_ratio": [float(joint.explained_variance_ratio_[0]), float(joint.explained_variance_ratio_[1])],
        "note": (
            "The shared tumour/cell-line PCA. PC1 separates tumour tissue from cultured cells as much "
            "as it separates biology, so read distance along PC2 with more confidence than along PC1."
        ),
        "tumours": [[round(float(tumour_proj[i][0]), 3), round(float(tumour_proj[i][1]), 3)] for i in sample],
        "patients": {
            pid: [round(float(tumour_proj[i][0]), 3), round(float(tumour_proj[i][1]), 3)]
            for pid, i in tumour_index.items()
        },
        "lines": {
            str(name): [round(float(cell_proj[i][0]), 3), round(float(cell_proj[i][1]), 3)]
            for name, i in cell_index.items()
        },
    }

    cohort_path = dest / "cohort_payload.json"
    cohort = json.loads(cohort_path.read_text())
    cohort["fingerprint_axes"] = axes
    cohort["joint_projection"] = joint_payload
    cohort.setdefault("provenance", {})["cell_line_metadata"] = "depmap_model_csv"
    cohort_path.write_text(json.dumps(cohort, indent=2))

    assign = pd.read_parquet(dest / "cluster_assignments.parquet")
    preg = json.loads((V2_ROOT / "data" / "reference" / "preregistered_k.json").read_text())
    sub = assign[
        (assign["method"] == preg["method"])
        & (assign["covariance_type"] == preg["covariance_type"])
        & (assign["k"] == preg["k"])
    ]
    labels = sub.drop_duplicates("patient_id").set_index("patient_id")["cluster"].reindex(ids).dropna().astype(int)
    cluster_marks = annotate_clusters(expr.loc[labels.index], labels.to_numpy())

    patients = {}
    for path in sorted(dest.glob("payload_*.json")):
        payload = json.loads(path.read_text())
        lines = payload.get("nearest_lines")
        if not lines:
            patients[payload["patient_id"]] = payload
            path.write_text(json.dumps(payload, indent=2))
            continue

        pid = payload["patient_id"]
        ti = tumour_index.get(pid)
        patient_pam = payload.get("pam50")
        cluster = str((payload.get("position") or {}).get("cluster", {}).get("label"))
        ann = cluster_marks.get(cluster) or {}

        # 2. Fingerprints normalised across the retrieved set, so the five bars
        #    are comparable rather than each pinned to its own peak.
        raw = []
        for line in lines:
            ci = cell_index.get(str(line["line_id"]))
            if ti is None or ci is None:
                raw.append(None)
                continue
            raw.append((tumour_proj[ti][:5] * cell_proj[ci][:5]).astype(float))
        peak = max((float(np.max(np.abs(v))) for v in raw if v is not None), default=1.0) or 1.0

        for line, contrib in zip(lines, raw):
            if contrib is not None:
                line["fingerprint"] = np.clip(contrib / peak, -1, 1).tolist()
            line["fingerprint_scale"] = "shared_peak_across_retrieved_lines"

            # 3. Why this line.
            meta_row = cell_meta.loc[str(line["line_id"])] if str(line["line_id"]) in cell_meta.index else None
            if meta_row is not None:
                for src, key in (
                    ("subtype_features", "subtype_features"),
                    ("oncotree_subtype", "oncotree_subtype"),
                    ("primary_or_metastasis", "primary_or_metastasis"),
                ):
                    if src in cell_meta.columns:
                        value = meta_row.get(src)
                        line[key] = None if pd.isna(value) else str(value)
            line["pam50_match"] = (
                None if not patient_pam or not line.get("pam50") else bool(line["pam50"] == patient_pam)
            )
            marks = line_markers.get(str(line["line_id"]))
            if marks and ann:
                line["marker_comparison"] = [
                    {"marker": m, "line": round(marks.get(m, 0.0), 2), "subgroup": round(float(ann.get(f"{m.lower()}_mean", 0.0)), 2)}
                    for m in MARKERS
                ] + [
                    {"marker": "proliferation", "line": round(marks.get("prolif", 0.0), 2), "subgroup": round(float(ann.get("prolif_mean", 0.0)), 2)}
                ]

        # 4. Curves that say what was tested.
        if gdsc is not None:
            candidates = [
                str(m.get("canonical") or m.get("drug"))
                for m in ((payload.get("reversal_candidates") or {}).get("members") or [])
            ]
            drugs = list(dict.fromkeys(SOC_COMPARATORS + candidates))
            refreshed = attach_gdsc_curves(lines, gdsc, drugs, pk=pk)
            payload["nearest_lines"] = refreshed
            n_extrap = sum(1 for l in refreshed for c in (l.get("curves") or []) if c.get("ic50_extrapolated"))
            n_curves = sum(len(l.get("curves") or []) for l in refreshed)
            print(f"  {pid}: {n_curves} curves, {n_extrap} with IC50 beyond the tested range")
        else:
            payload["nearest_lines"] = lines

        path.write_text(json.dumps(payload, indent=2))
        patients[payload["patient_id"]] = payload

    copy_payloads_to_app(cohort, patients, repo_root)
    print("payloads copied to the app")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
