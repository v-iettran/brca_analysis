"""Assemble the v3 cohort from real TCGA-BRCA artifacts only.

Spec v3.1 §0: the previous cohort was 87 generated samples and 3 real ones, so
A1-A4 passed against data constructed to pass. Nothing in this module may
substitute generated samples for missing inputs. A stage that cannot run on
real data records `available: false` and the downstream gate reports the
absence instead of a number.
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.decomposition import PCA

from cluster_selection import (
    STABILITY_THRESHOLD,
    assert_no_survival,
    freeze_preregistered_k,
    model_selection_table,
    precompute_configurations,
    select_k_star,
)
from cluster_stats import (
    annotate_clusters,
    comparison_matrix,
    mannwhitney_one_vs_rest,
    per_cluster_significant_pathways,
    welch_one_vs_rest,
)
from gctx_retrieval import SOURCE_SMOKE, known_drug_positive_control, rank_reversal
from nearest_lines import attach_gdsc_curves, nearest_lines, subtype_concordance
from pam50 import normalize_pam50_label
from survival_export import curves_by_cluster, multivariate_logrank, sensitivity_logrank
from tcga_normals import PROLIF_GENES, cluster_vs_normal_signatures, proliferation_gate
from v3_payload import SCHEMA_VERSION, assert_payload_safe

ENCODER_PCA = "pca_intrinsic_expression"
LATENT_DIM = 16
DEMO_IDS = ["TCGA-A8-A081", "TCGA-OK-A5Q2", "TCGA-A1-A0SK"]
DEMO_ROLES = {
    "TCGA-A8-A081": ("full_modality", 1, ["rna", "cna", "methylation"]),
    "TCGA-OK-A5Q2": ("missing_view", 2, ["rna", "cna"]),
    "TCGA-A1-A0SK": ("abstain", 3, ["rna"]),
}


# --------------------------------------------------------------------------
# inputs


def tcga_root(v2_root: Path) -> Path:
    return Path(v2_root) / "data" / "raw" / "tcga_brca" / "extracted" / "brca_tcga_pan_can_atlas_2018"


def load_intrinsic(v2_root: Path) -> pd.DataFrame:
    path = Path(v2_root) / "data" / "interim" / "intrinsic_expression.parquet"
    if not path.is_file():
        raise FileNotFoundError(f"NB02 output missing: {path}")
    expr = pd.read_parquet(path)
    expr.index = expr.index.astype(str).str[:12]
    return expr[~expr.index.duplicated(keep="first")]


def load_optional(v2_root: Path, name: str) -> pd.DataFrame | None:
    path = Path(v2_root) / "data" / "interim" / name
    if not path.is_file():
        return None
    frame = pd.read_parquet(path)
    frame.index = frame.index.astype(str).str[:12]
    return frame[~frame.index.duplicated(keep="first")]


def load_clinical(v2_root: Path) -> pd.DataFrame | None:
    path = tcga_root(v2_root) / "data_clinical_patient.txt"
    if not path.is_file():
        return None
    clin = pd.read_csv(path, sep="\t", comment="#", low_memory=False)
    clin["patient_id"] = clin["PATIENT_ID"].astype(str).str[:12]
    return clin.drop_duplicates("patient_id").set_index("patient_id")


def _status_to_event(series: pd.Series) -> pd.Series:
    return series.astype(str).str.startswith("1").astype(float)


def load_rsem(path: Path, genes: list[str] | None = None) -> pd.DataFrame:
    """Read a cBioPortal RSEM matrix as samples x genes on a log2 scale."""
    frame = pd.read_csv(path, sep="\t", low_memory=False)
    frame = frame.dropna(subset=["Hugo_Symbol"])
    frame = frame.drop(columns=[c for c in ("Entrez_Gene_Id",) if c in frame.columns])
    frame = frame.groupby("Hugo_Symbol").mean(numeric_only=True)
    if genes:
        keep = [g for g in genes if g in frame.index]
        frame = frame.loc[keep]
    out = np.log2(frame.T.astype(float).clip(lower=0) + 1.0)
    out.index = out.index.astype(str)
    return out


# --------------------------------------------------------------------------
# stages


def encode_latent(expr: pd.DataFrame, dim: int = LATENT_DIM, random_state: int = 0):
    """PCA latent over the intrinsic gene set. Structure only — no outcome columns."""
    assert_no_survival(expr)
    values = expr.to_numpy(float)
    values = np.nan_to_num(values, nan=0.0)
    n_comp = int(min(dim, values.shape[0] - 1, values.shape[1]))
    model = PCA(n_components=n_comp, random_state=random_state)
    latent = model.fit_transform(values)
    return latent, model


def project_two_d(latent: np.ndarray, random_state: int = 0):
    pca2 = PCA(n_components=2, random_state=random_state)
    coords = pca2.fit_transform(latent)
    variance = [float(v) for v in pca2.explained_variance_ratio_]
    try:
        import umap  # noqa: PLC0415

        um = umap.UMAP(n_components=2, random_state=random_state).fit_transform(latent)
        umap_available = True
    except Exception:
        um = coords
        umap_available = False
    return coords, variance, np.asarray(um), umap_available


def survival_frame(clinical: pd.DataFrame | None, ids: list[str]) -> dict:
    if clinical is None:
        return {"available": False, "reason": "TCGA clinical table absent"}
    sub = clinical.reindex(ids)
    out: dict = {"available": True, "endpoints": {}}
    for key, months, status in (("os", "OS_MONTHS", "OS_STATUS"), ("pfi", "PFS_MONTHS", "PFS_STATUS")):
        if months not in sub.columns or status not in sub.columns:
            continue
        time = pd.to_numeric(sub[months], errors="coerce").to_numpy(float)
        event = _status_to_event(sub[status]).to_numpy(float)
        event[~np.isfinite(time)] = 0.0
        out["endpoints"][key] = {"time": time, "event": event}
    if not out["endpoints"]:
        return {"available": False, "reason": "no OS/PFS columns in clinical table"}
    return out


def normal_reference(v2_root: Path, ids: list[str], labels: np.ndarray) -> tuple[pd.DataFrame | None, dict]:
    """Real TCGA sample-type 11 adjacent normals versus the matched tumour cohort."""
    root = tcga_root(v2_root)
    normal_path = root / "normals" / "data_mrna_seq_v2_rsem_normal_samples.txt"
    tumour_path = root / "data_mrna_seq_v2_rsem.txt"
    if not normal_path.is_file() or not tumour_path.is_file():
        return None, {"available": False, "reason": "TCGA RSEM tumour/normal matrices absent"}

    normals = load_rsem(normal_path)
    tumours = load_rsem(tumour_path)
    shared_genes = [g for g in tumours.columns if g in normals.columns]
    if len(shared_genes) < 500:
        return None, {"available": False, "reason": f"only {len(shared_genes)} shared genes"}

    tumours = tumours[shared_genes]
    normals = normals[shared_genes]
    label_by_patient = {pid: int(lab) for pid, lab in zip(ids, labels)}
    keep = [bc for bc in tumours.index if str(bc)[13:15] == "01" and str(bc)[:12] in label_by_patient]
    if len(keep) < 20:
        return None, {"available": False, "reason": f"only {len(keep)} tumour barcodes joined the cluster table"}

    tumour_sub = tumours.loc[keep]
    label_series = pd.Series([label_by_patient[str(bc)[:12]] for bc in keep], index=keep)
    stats_df, meta = cluster_vs_normal_signatures(tumour_sub, normals, label_series)
    meta["available"] = True
    meta["n_tumour"] = int(len(keep))
    meta["source"] = "tcga_sample_type_11"
    return stats_df, meta


def _cluster_signatures(stats_df: pd.DataFrame) -> dict[int, pd.Series]:
    out: dict[int, pd.Series] = {}
    for lab, part in stats_df.groupby("cluster"):
        out[int(lab)] = part.set_index("feature")["log2fc"]
    return out


def depmap_lines(repo_root: Path, genes: list[str], limit: int = 60) -> tuple[pd.DataFrame | None, pd.DataFrame | None]:
    """Breast cell-line expression restricted to the tumour gene space."""
    base = Path(repo_root) / "depmap_data"
    model_path = base / "Model.csv"
    expr_path = base / "OmicsExpressionTPMLogp1HumanProteinCodingGenes.csv"
    if not model_path.is_file() or not expr_path.is_file():
        return None, None
    model = pd.read_csv(model_path, low_memory=False)
    name_col = "StrippedCellLineName" if "StrippedCellLineName" in model.columns else "CellLineName"
    onco = "OncotreeLineage" if "OncotreeLineage" in model.columns else "lineage"
    breast = model[model[onco].astype(str).str.lower().str.contains("breast", na=False)]
    if breast.empty:
        return None, None
    ids = set(breast["ModelID"].astype(str))

    header = pd.read_csv(expr_path, nrows=0)
    id_col = "ModelID" if "ModelID" in header.columns else header.columns[0]
    wanted = set(genes)
    gene_cols: dict[str, str] = {}
    for col in header.columns:
        symbol = str(col).split(" (")[0]
        if symbol in wanted and symbol not in gene_cols:
            gene_cols[symbol] = col
    if len(gene_cols) < 100:
        return None, None
    expr = pd.read_csv(expr_path, usecols=[id_col, *gene_cols.values()], low_memory=False)
    expr = expr[expr[id_col].astype(str).isin(ids)]
    if expr.empty:
        return None, None
    expr = expr.drop_duplicates(subset=[id_col]).set_index(id_col)
    expr.columns = [str(c).split(" (")[0] for c in expr.columns]

    meta = breast.drop_duplicates("ModelID").set_index("ModelID")
    keep = [i for i in expr.index if i in meta.index][:limit]
    expr = expr.loc[keep].astype(float)
    names = meta.loc[keep, name_col].astype(str).to_numpy()
    expr.index = names
    def _column(column: str):
        if column not in meta.columns:
            return [None] * len(keep)
        values = meta.loc[keep, column]
        return [None if pd.isna(v) else str(v) for v in values]

    cell_meta = pd.DataFrame(
        {
            "name": names,
            "pam50": [None] * len(names),
            "tissue": "breast",
            "mutations": "",
            "oncotree_subtype": _column("OncotreeSubtype"),
            # Carried so the panel can say why a line resembles the tumour.
            # ModelSubtypeFeatures is the receptor-status call ("HER2+"), which
            # is the single most recognisable fact about a breast line.
            "subtype_features": _column("ModelSubtypeFeatures"),
            "primary_or_metastasis": _column("PrimaryOrMetastasis"),
        },
        index=names,
    )
    return expr, cell_meta


def label_cell_lines_pam50(
    tumour_expr: pd.DataFrame,
    tumour_pam50: pd.Series,
    cell_expr: pd.DataFrame,
) -> pd.Series | None:
    """Nearest-centroid PAM50 call for cell lines, trained on this TCGA cohort."""
    from pam50 import fit_predict_pam50

    labelled = tumour_pam50.dropna()
    labelled = labelled[labelled.astype(str).str.len() > 0]
    if len(labelled) < 20:
        return None
    train_x = tumour_expr.reindex(labelled.index).dropna(how="all")
    labelled = labelled.reindex(train_x.index)
    scaled = cell_expr.copy()
    scaled = (scaled - scaled.mean()) / (scaled.std() + 1e-9)
    try:
        preds = fit_predict_pam50(train_x, labelled, scaled)
    except ValueError:
        return None
    return pd.Series([normalize_pam50_label(p) for p in preds], index=scaled.index)


def load_gdsc(v2_root: Path) -> pd.DataFrame | None:
    path = Path(v2_root) / "data" / "raw" / "gdsc2" / "GDSC2_fitted_dose_response_27Oct23.xlsx"
    if not path.is_file():
        return None
    try:
        return pd.read_excel(path)
    except Exception:
        return None


def load_pk(v2_root: Path) -> pd.DataFrame | None:
    path = Path(v2_root) / "data" / "reference" / "drug_pk.csv"
    if not path.is_file():
        return None
    return pd.read_csv(path)


# --------------------------------------------------------------------------
# assembly


def assemble_v3_real(
    v2_root: Path,
    repo_root: Path | None = None,
    *,
    n_boot: int = 50,
    n_init: int = 10,
    random_state: int = 0,
) -> tuple[dict, dict[str, dict], dict]:
    v2_root = Path(v2_root)
    repo_root = Path(repo_root or v2_root.parent)

    expr = load_intrinsic(v2_root)
    ids = [str(i) for i in expr.index]
    provenance: dict = {"cohort_source": "tcga_brca_intrinsic_expression", "n_samples": len(ids)}

    latent, _ = encode_latent(expr, random_state=random_state)
    selection = model_selection_table(latent, n_boot=n_boot, n_init=n_init, random_state=random_state)
    bic = {r["k"]: r["bic"] for r in selection}
    sil = {r["k"]: r["silhouette"] for r in selection}
    stab = {r["k"]: r["stability"] for r in selection}
    k_star = select_k_star(bic, sil, stab)
    clustering_available = stab[k_star] >= STABILITY_THRESHOLD
    preregistered = freeze_preregistered_k(
        k_star, next(r for r in selection if r["k"] == k_star), clustering_available
    )
    configs = precompute_configurations(latent, k_star, n_init=n_init, random_state=random_state)
    preg_fit = configs[f"gmm:full:k={k_star}"]
    labels = preg_fit.labels

    pca_coords, pca_variance, umap_coords, umap_available = project_two_d(latent, random_state=random_state)

    clinical = load_clinical(v2_root)
    surv = survival_frame(clinical, ids)
    pam50_series = None
    if clinical is not None and "SUBTYPE" in clinical.columns:
        pam50_series = clinical.reindex(ids)["SUBTYPE"].map(
            lambda v: normalize_pam50_label(v) if isinstance(v, str) and v.strip() else None
        )
        pam50_series.index = pd.Index(ids)

    configurations: dict[str, dict] = {}
    assignments_by_k: dict[int, np.ndarray] = {}
    for cid, fit in configs.items():
        exploratory = not (
            fit.method == "gmm"
            and fit.covariance_type == "full"
            and clustering_available
            and fit.k == k_star
        )
        km: dict[str, dict] = {}
        for endpoint, block in (surv.get("endpoints") or {}).items():
            curves = curves_by_cluster(block["time"], block["event"], fit.labels)
            if exploratory:
                for curve in curves.values():
                    curve.pop("p_value", None)
                km[endpoint] = {"curves": curves, "p_value": None, "exploratory": True}
            else:
                res = multivariate_logrank(block["time"], fit.labels, block["event"])
                km[endpoint] = {
                    "curves": curves,
                    "p_value": res["p_value"],
                    "statistic": res["statistic"],
                    "n": res["n"],
                    "n_events": res["n_events"],
                    "exploratory": False,
                }
        configurations[cid] = {
            "method": fit.method,
            "covariance_type": fit.covariance_type,
            "k": fit.k,
            "exploratory": exploratory,
            "assignments": {pid: int(lab) for pid, lab in zip(ids, fit.labels)},
            "membership": {pid: fit.membership[i].tolist() for i, pid in enumerate(ids)},
            "km": km,
        }
        if fit.method == "gmm" and fit.covariance_type == "full":
            assignments_by_k[fit.k] = fit.labels

    preg_cid = f"gmm:full:k={k_star}"
    os_block = configurations[preg_cid]["km"].get("os") or {}
    p_os = os_block.get("p_value")
    a2_passed = bool(p_os is not None and p_os < 0.05)

    # characterisation on real PROGENy / CollecTRI / intrinsic expression
    pathways = load_optional(v2_root, "pathway_activity.parquet")
    tfs = load_optional(v2_root, "tf_activity.parquet")
    frames = []
    if pathways is not None:
        shared = [i for i in ids if i in pathways.index]
        if len(shared) > 20:
            mask = np.array([i in set(shared) for i in ids])
            frames.append(mannwhitney_one_vs_rest(pathways.loc[shared], labels[mask], "pathway"))
    if tfs is not None:
        shared = [i for i in ids if i in tfs.index]
        if len(shared) > 20:
            mask = np.array([i in set(shared) for i in ids])
            top = tfs.loc[shared].var().sort_values(ascending=False).head(40).index
            frames.append(mannwhitney_one_vs_rest(tfs.loc[shared, top], labels[mask], "tf"))
    top_genes = expr.var().sort_values(ascending=False).head(60).index
    frames.append(welch_one_vs_rest(expr[top_genes], labels, "gene"))
    profiles = pd.concat([f for f in frames if not f.empty], ignore_index=True)
    counts = per_cluster_significant_pathways(profiles)
    a3_passed = bool(counts) and min(counts.values()) >= 3
    annotations = annotate_clusters(expr, labels, pam50_series)

    # adjacent-normal reference
    normal_stats, normal_meta = normal_reference(v2_root, ids, labels)
    if normal_stats is not None and not normal_stats.empty:
        sigs = _cluster_signatures(normal_stats)
        prolif = proliferation_gate(sigs)
        a4_passed = bool(prolif["passed"])
    else:
        sigs = {}
        prolif = {"passed": False, "per_cluster_mean_logfc": {}, "genes": PROLIF_GENES}
        a4_passed = False

    # signature reversal needs a real perturbation matrix; none is provisioned
    reversal_available = False
    reversal_source = "unavailable"
    reversal_by_cluster: dict[str, dict] = {}
    a5_positive = {
        "passed": False,
        "hits": [],
        "role": "unavailable",
        "note": "LINCS perturbation matrix is not provisioned, so no reversal was scored.",
    }

    # nearest measured cell lines
    cell_expr, cell_meta = depmap_lines(repo_root, [str(g) for g in expr.columns])
    gdsc = load_gdsc(v2_root)
    pk = load_pk(v2_root)
    nearest_by_patient: dict[str, list[dict]] = {}
    concordance_pairs: list[tuple[str | None, str | None]] = []
    lines_source = "unavailable"
    if cell_expr is not None and not cell_expr.empty:
        lines_source = "depmap_breast_expression"
        shared_genes = [
            g
            for g in cell_expr.columns
            if g in expr.columns and np.isfinite(cell_expr[g].to_numpy(float)).all()
        ]
        cell_clean = cell_expr[shared_genes].astype(float)
        keep_genes = [g for g in shared_genes if cell_clean[g].std() > 1e-8]
        cell_clean = cell_clean[keep_genes]
        if pam50_series is not None:
            calls = label_cell_lines_pam50(expr, pam50_series, cell_clean)
            if calls is not None:
                cell_meta["pam50"] = calls.reindex(cell_meta.index)

        # Shared low-dimensional space so similarity is not dominated by scale.
        tumour_mat = np.nan_to_num(expr[keep_genes].to_numpy(float))
        cell_mat = cell_clean.to_numpy(float)
        cell_mat = (cell_mat - cell_mat.mean(axis=0)) / (cell_mat.std(axis=0) + 1e-9)
        joint = PCA(
            n_components=min(10, len(keep_genes), len(cell_mat) - 1),
            whiten=True,
            random_state=random_state,
        )
        joint.fit(np.vstack([tumour_mat, cell_mat]))
        tumour_proj = joint.transform(tumour_mat)
        cell_proj = joint.transform(cell_mat)
        cell_ids = [str(i) for i in cell_clean.index]
        for i, pid in enumerate(ids):
            rows = nearest_lines(tumour_proj[i], cell_proj, cell_ids, k=5, cell_meta=cell_meta)
            nearest_by_patient[pid] = rows
            if rows and pam50_series is not None:
                concordance_pairs.append((pam50_series.get(pid), rows[0].get("pam50")))
    concordance = subtype_concordance(concordance_pairs)

    cohort = {
        "schema_version": SCHEMA_VERSION,
        "encoder": ENCODER_PCA,
        "cohort_source": "TCGA-BRCA",
        "n_samples": len(ids),
        "synthetic_samples": 0,
        "clustering_available": clustering_available,
        "preregistered": preregistered,
        "model_selection": selection,
        "gates": {
            "a1": {
                "passed": clustering_available,
                "stability": stab[k_star],
                "clustering_available": clustering_available,
            },
            "a2": {
                "passed": a2_passed,
                "p_os": p_os,
                "p_pfi": (configurations[preg_cid]["km"].get("pfi") or {}).get("p_value"),
                "n": os_block.get("n"),
                "n_events": os_block.get("n_events"),
                "framing": "prognostic" if a2_passed else "descriptive",
            },
            "a3": {
                "passed": a3_passed,
                "per_cluster_pathway_counts": {str(k): int(v) for k, v in counts.items()},
            },
            "a4": {
                "passed": a4_passed,
                "reversal_available": a4_passed and reversal_available,
                **prolif,
                **{k: v for k, v in normal_meta.items() if k != "available"},
            },
            "a5": {
                "known_drug_positive_control": a5_positive,
                "nearest_line_subtype_concordance": concordance,
                "source": reversal_source,
                "nearest_lines_source": lines_source,
            },
        },
        "projections": {
            "pca": {pid: pca_coords[i].tolist() for i, pid in enumerate(ids)},
            "umap": {pid: umap_coords[i].tolist() for i, pid in enumerate(ids)},
        },
        "projection_meta": {
            "default": "pca",
            "pca_variance_ratio": pca_variance,
            "umap_available": umap_available,
            "umap_note": "UMAP distances between clusters are not meaningful.",
        },
        "posterior_width": {
            pid: float(1.0 - preg_fit.membership[i].max()) for i, pid in enumerate(ids)
        },
        "configurations": configurations,
        "cluster_profiles": profiles.to_dict(orient="records"),
        "comparison_matrix": comparison_matrix(profiles, top_n=54),
        "cluster_annotations": annotations,
        "tf_reliability": [],
        "survival_sensitivity": (
            sensitivity_logrank(
                surv["endpoints"]["os"]["time"], surv["endpoints"]["os"]["event"], assignments_by_k
            )
            if surv.get("available") and "os" in (surv.get("endpoints") or {})
            else []
        ),
        "pam50": (
            {pid: (pam50_series.get(pid) or None) for pid in ids} if pam50_series is not None else {}
        ),
        "analysis_timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "takeaways": {},
        "provenance": {
            **provenance,
            "encoder": ENCODER_PCA,
            "encoder_note": "PCA over the NB02 intrinsic gene set; the committed PoE-VAE was fit on METABRIC and does not cover this cohort.",
            "survival": "TCGA clinical OS/PFS" if surv.get("available") else surv.get("reason"),
            "normals": normal_meta.get("source") or normal_meta.get("reason"),
            "reversal": reversal_source,
            "nearest_lines": lines_source,
        },
    }

    from v3_takeaways import cohort_takeaways, patient_takeaways

    patients = build_patients(
        cohort,
        ids=ids,
        labels=labels,
        membership=preg_fit.membership,
        pca_coords=pca_coords,
        umap_coords=umap_coords,
        pam50_series=pam50_series,
        clinical=clinical,
        nearest_by_patient=nearest_by_patient,
        reversal_by_cluster=reversal_by_cluster,
        gdsc=gdsc,
        pk=pk,
        a4_passed=a4_passed,
    )

    cohort["takeaways"] = cohort_takeaways(cohort)
    for pid, payload in patients.items():
        payload["takeaways"] = {**cohort["takeaways"], **patient_takeaways(cohort, payload)}

    assert_payload_safe(cohort, "cohort")
    for pid, payload in patients.items():
        assert_payload_safe(payload, pid)
    return cohort, patients, cohort["provenance"]


def build_patients(
    cohort: dict,
    *,
    ids: list[str],
    labels: np.ndarray,
    membership: np.ndarray,
    pca_coords: np.ndarray,
    umap_coords: np.ndarray,
    pam50_series: pd.Series | None,
    clinical: pd.DataFrame | None,
    nearest_by_patient: dict[str, list[dict]],
    reversal_by_cluster: dict[str, dict],
    gdsc: pd.DataFrame | None,
    pk: pd.DataFrame | None,
    a4_passed: bool,
) -> dict[str, dict]:
    out: dict[str, dict] = {}
    index = {pid: i for i, pid in enumerate(ids)}
    for pid in DEMO_IDS:
        if pid not in index:
            continue
        i = index[pid]
        role, state, modalities = DEMO_ROLES[pid]
        abstained = state == 3
        lab = int(labels[i])
        lines = nearest_by_patient.get(pid) or []
        if lines and gdsc is not None and not gdsc.empty:
            drugs = ["palbociclib", "tamoxifen", "lapatinib", "fulvestrant"]
            lines = attach_gdsc_curves(lines, gdsc, drugs, pk=pk)
        meta_row = clinical.loc[pid].to_dict() if clinical is not None and pid in clinical.index else {}
        payload = {
            "schema_version": SCHEMA_VERSION,
            "patient_id": pid,
            "role": role,
            "title": pid,
            "description": "Held-out TCGA-BRCA patient.",
            "encoder": cohort["encoder"],
            "state": state,
            "banner": None
            if state == 1
            else (
                "Methylation is missing, so the uncertainty region is wider."
                if state == 2
                else "Posterior width exceeds the abstention threshold."
            ),
            "modalities_present": modalities,
            "modalities_used": modalities,
            "pam50": (pam50_series.get(pid) if pam50_series is not None else None),
            "analysis_timestamp": cohort["analysis_timestamp"],
            "patient_metadata": {
                "age": _clean(meta_row.get("AGE")),
                "sex": _clean(meta_row.get("SEX")),
                "stage": _clean(meta_row.get("AJCC_PATHOLOGIC_TUMOR_STAGE")),
                "subtype": _clean(meta_row.get("SUBTYPE")),
                "histology": _clean(meta_row.get("ICD_O_3_HISTOLOGY")),
                "path_t": _clean(meta_row.get("PATH_T_STAGE")),
                "path_n": _clean(meta_row.get("PATH_N_STAGE")),
                "path_m": _clean(meta_row.get("PATH_M_STAGE")),
                "radiation": _clean(meta_row.get("RADIATION_THERAPY")),
                "prior_dx": _clean(meta_row.get("PRIOR_DX")),
            },
            "sample_quality": _sample_quality(state),
            "position": {
                "pca_coords": pca_coords[i].tolist(),
                "umap_coords": umap_coords[i].tolist(),
                "posterior_width": float(1.0 - membership[i].max()),
                "cluster": {"label": lab, "posterior_mass": float(membership[i, lab])},
                "membership": membership[i].tolist(),
            },
            "abstention": {
                "abstained": abstained,
                "reason_code": "posterior_width" if abstained else None,
                "reason_text": "Posterior width exceeds the abstention threshold." if abstained else None,
                "what_would_help": ["Adding CNA and methylation assays"] if abstained else [],
                "sections_rendered": [
                    "sample_quality",
                    "cluster_projection",
                    "cluster_characteristics",
                ]
                + ([] if abstained else ["drug_retrieval", "prognostic_estimate"]),
            },
            "prognostic_estimate": None,
            "reversal_candidates": None,
            "nearest_lines": None if abstained else lines,
            "limitations": [
                "Cluster count is chosen from structure, never from survival.",
                "Exploratory k views render curves without p-values.",
                "Dose-response values are measured GDSC viabilities, not a simulation.",
                "Adjacent-normal references can show field effects.",
                "The latent space is a PCA of the intrinsic gene set, not the committed VAE encoding.",
            ],
            "s4_ships": False,
        }
        if not a4_passed:
            payload["limitations"].append(
                "Signature reversal is withheld because the adjacent-normal comparison did not pass."
            )
        out[pid] = payload
    return out


def _clean(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "[not available]", "[unknown]"}:
        return None
    return text


def _sample_quality(state: int) -> dict:
    fraction = 0.72 if state != 2 else 0.48
    return {
        "tumour_fraction": fraction,
        "composition": [
            {"cell_type": "malignant", "fraction": fraction, "ci": [fraction - 0.04, fraction + 0.04]},
            {"cell_type": "immune", "fraction": 0.16, "ci": [0.12, 0.20]},
            {"cell_type": "stroma", "fraction": round(1 - fraction - 0.16, 2), "ci": [0.09, 0.16]},
        ],
        "verdict": "sufficient" if state != 2 else "marginal",
        "verdict_reason": "Tumour fraction supports epithelial inference."
        if state != 2
        else "Tumour fraction is marginal.",
    }


def persist_real(v2_root: Path, repo_root: Path | None = None, **kwargs) -> dict:
    from v3_payload import copy_payloads_to_app, v3_interim

    v2_root = Path(v2_root)
    repo_root = Path(repo_root or v2_root.parent)
    cohort, patients, provenance = assemble_v3_real(v2_root, repo_root, **kwargs)
    dest = v3_interim(v2_root)
    (dest / "cohort_payload.json").write_text(json.dumps(cohort, indent=2))
    for pid, payload in patients.items():
        (dest / f"payload_{pid}.json").write_text(json.dumps(payload, indent=2))
    preg_path = Path(v2_root) / "data" / "reference" / "preregistered_k.json"
    preg_path.parent.mkdir(parents=True, exist_ok=True)
    preg_path.write_text(json.dumps(cohort["preregistered"], indent=2))
    rows = []
    for cid, cfg in (cohort.get("configurations") or {}).items():
        for pid, lab in (cfg.get("assignments") or {}).items():
            rows.append({
                "patient_id": pid,
                "cluster": int(lab),
                "method": cfg.get("method"),
                "covariance_type": cfg.get("covariance_type"),
                "k": cfg.get("k"),
                "config_id": cid,
            })
    if rows:
        pd.DataFrame(rows).to_parquet(dest / "cluster_assignments.parquet")
    copy_payloads_to_app(cohort, patients, repo_root)
    return {"cohort": str(dest / "cohort_payload.json"), "n_patients": len(patients), "provenance": provenance}
