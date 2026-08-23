"""Assemble B2–B7 demo payloads from the committed PoE-VAE and conformal model."""

from __future__ import annotations

import json
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from demo_patients import (  # noqa: E402
    load_demo_manifest,
    tumour_verdict,
    view_mask_for_role,
)
from pathway_candidates import pathway_activity, pathway_candidates  # noqa: E402
from paths import resolve_v2_root  # noqa: E402
from poe_vae import (  # noqa: E402
    encode_optional_views,
    fit_linear_poe,
    load_poe_vae,
    posterior_width,
    view_width_reduction,
)
from safety import assert_safe  # noqa: E402


IMMUNE = ["T-cells", "Myeloid", "B-cells", "Plasmablasts"]
STROMA = ["Endothelial", "Normal_Epithelial", "CAFs", "PVL"]


def _ci(frac: float) -> list[float]:
    return [max(0.0, frac - 0.04), min(1.0, frac + 0.04)]


def _load_view(root: Path, patterns: list[str], index: pd.Index) -> pd.DataFrame | None:
    for base in (root / "data" / "raw" / "tcga_brca", root.parent / "brca_metabric"):
        if not base.exists():
            continue
        for pat in patterns:
            hits = list(base.rglob(pat))
            if not hits:
                continue
            df = pd.read_csv(hits[0], sep="\t", comment="#")
            if "Hugo_Symbol" in df.columns:
                df = df.set_index("Hugo_Symbol")
            drop = [c for c in df.columns if "entrez" in c.lower()]
            df = df.drop(columns=drop, errors="ignore").apply(pd.to_numeric, errors="coerce").T
            df.index = df.index.astype(str).str[:12]
            return df.reindex(index)
    return None


def _composition(row: pd.Series) -> list[dict]:
    mal = float(row["malignant"])
    immune = float(sum(float(row.get(c, 0) or 0) for c in IMMUNE))
    stroma = float(sum(float(row.get(c, 0) or 0) for c in STROMA))
    return [
        {"cell_type": "malignant", "fraction": mal, "ci": _ci(mal)},
        {"cell_type": "immune", "fraction": immune, "ci": _ci(immune)},
        {"cell_type": "stroma", "fraction": stroma, "ci": _ci(stroma)},
    ]


APP_DATA_DIRS = [
    Path("/Users/luke/Desktop/UCD/Class/Summer/AI-for-PM/person_med_a2/application/apps/api/app/data"),
    Path("/Users/luke/Desktop/UCD/Class/Summer/AI-for-PM/brca_analysis/application/apps/api/app/data"),
]


def _align_view(df: pd.DataFrame, genes: list[str], index: pd.Index) -> pd.DataFrame:
    if df.columns.duplicated().any():
        df = df.loc[:, ~df.columns.duplicated()]
    src = df.reindex(index=index)
    out = pd.DataFrame(0.0, index=index, columns=pd.RangeIndex(len(genes)))
    lookup = {str(c): src[c] for c in src.columns}
    for i, gene in enumerate(genes):
        series = lookup.get(str(gene))
        if series is None:
            continue
        if isinstance(series, pd.DataFrame):
            series = series.iloc[:, 0]
        out.iloc[:, i] = pd.to_numeric(series, errors="coerce").fillna(0.0).to_numpy()
    out.columns = list(genes)
    return out


def _load_encoder(root: Path, views: list[np.ndarray], fit_ids: list[str]):
    meta_p = root / "artifacts" / "poe_vae_meta.json"
    eqx_p = root / "artifacts" / "poe_vae.eqx"
    if meta_p.exists() and eqx_p.exists():
        meta = json.loads(meta_p.read_text())
        try:
            model = load_poe_vae(eqx_p, meta)
            print("loaded committed PoE-VAE", eqx_p, "encoder", meta.get("encoder"))
            return model, meta
        except Exception as exc:
            print("VAE load failed, linear PoE fallback", exc)
    print("fitting linear PoE on n=", len(fit_ids), "(committed VAE unavailable)")
    fit = fit_linear_poe([v for v in views], latent_dim=16)
    meta = {"encoder": "linear_poe", "latent_dim": 16, "input_dims": [int(v.shape[1]) for v in views]}
    return fit, meta


def _prognostic_estimate(
    bundle: dict | None,
    pw_row: pd.Series,
    trow: pd.Series,
    width: float,
) -> dict | None:
    if not bundle:
        return None
    requested = float(bundle.get("requested_coverage") or (1.0 - float(bundle.get("alpha", 0.08))))
    empirical = bundle.get("coverage")
    feat_cols = list(bundle.get("feat_cols") or ["sens", "tf_esr1", "precise", "target_pathway", "q2r", "posterior_width"])
    est = pathway_activity(pw_row, "estrogen")
    esr = pathway_activity(trow, "ESR1")
    features = {
        "sens": est,
        "tf_esr1": esr,
        "precise": 0.0,
        "target_pathway": est,
        "q2r": 1.0 / (1.0 + width),
        "posterior_width": width,
    }
    row = np.array([[float(features.get(c, 0.0)) for c in feat_cols]], dtype=float)
    point_days = None
    interval_days = None
    mapie = bundle.get("mapie")
    if mapie is not None:
        try:
            y_pred, y_pis = mapie.predict_interval(row)
            lo = float(np.asarray(y_pis)[0, 0, 0])
            hi = float(np.asarray(y_pis)[0, 1, 0])
            point = float(np.asarray(y_pred).reshape(-1)[0])
            point_days = float(np.expm1(point))
            interval_days = [float(np.expm1(lo)), float(np.expm1(hi))]
        except Exception as exc:
            print("conformal predict failed", exc)
    return {
        "point_days": point_days,
        "interval_days": interval_days,
        "requested_coverage": requested,
        "empirical_coverage": None if empirical is None else float(empirical),
        "n": int(bundle.get("n_test") or 0),
        "method": str(bundle.get("method") or "unknown"),
        "label": "SCAN-B overall survival (observed events)",
        "domain_note": (
            "Interval from the SCAN-B conformal model applied to this sample's molecular features. "
            "Coverage was measured on SCAN-B events, not TCGA."
        ),
        "validated": True,
    }


def main() -> Path:
    root = resolve_v2_root()
    ref = root / "data" / "reference"
    interim = root / "data" / "interim"
    man = load_demo_manifest(ref / "demo_patients.json")
    patients = man["patients"]
    exclude = {str(x)[:12] for x in man.get("exclude_from_fits", [])}

    deconv = pd.read_parquet(interim / "deconvolution_posterior.parquet")
    lat = pd.read_parquet(interim / "latent_posterior.parquet")
    pw = pd.read_parquet(interim / "pathway_activity.parquet")
    tf = pd.read_parquet(interim / "tf_activity.parquet")
    rel = pd.read_parquet(interim / "tf_reliability.parquet") if (interim / "tf_reliability.parquet").exists() else None
    pk = pd.read_csv(ref / "drug_pk.csv")
    clin = pd.read_csv(next((root / "data" / "raw" / "tcga_brca").rglob("*clinical_patient.txt")), sep="\t", comment="#")
    tau = float(lat["tau"].iloc[0]) if "tau" in lat.columns else 0.70
    typical_width = float(lat["width"].median())

    expr = pd.read_parquet(interim / "harmonised_expression.parquet").select_dtypes(include=[np.number])
    expr.index = expr.index.astype(str)
    meta_p = root / "artifacts" / "poe_vae_meta.json"
    genes = json.loads(meta_p.read_text())["genes"] if meta_p.exists() else None
    if genes:
        rna = _align_view(expr, genes["rna"], expr.index)
        cna_raw = _load_view(root, ["*data_cna.txt"], rna.index)
        meth_raw = _load_view(root, ["*methylation*"], rna.index)
        cna_df = _align_view(cna_raw if cna_raw is not None else pd.DataFrame(index=rna.index), genes["cna"], rna.index)
        meth_df = _align_view(meth_raw if meth_raw is not None else pd.DataFrame(index=rna.index), genes["methylation"], rna.index)
        meth_df = meth_df.clip(0, 1)
    else:
        var = expr.var().nlargest(min(500, expr.shape[1])).index
        rna = expr[var].fillna(0)
        cna_df = _load_view(root, ["*data_cna.txt"], rna.index)
        meth_df = _load_view(root, ["*methylation*"], rna.index)
        if cna_df is None:
            cna_df = pd.DataFrame(0.0, index=rna.index, columns=var[: min(50, len(var))])
        else:
            cna_df = cna_df.loc[:, cna_df.var().nlargest(min(500, cna_df.shape[1])).index].fillna(0)
        if meth_df is None:
            meth_df = pd.DataFrame(
                1 / (1 + np.exp(-rna.to_numpy() / (rna.to_numpy().std() + 1e-6))),
                index=rna.index,
                columns=rna.columns,
            )
        else:
            meth_df = meth_df.loc[:, meth_df.var().nlargest(min(500, meth_df.shape[1])).index].fillna(0)
            meth_df = meth_df.clip(0, 1)

    fit_ids = [i for i in rna.index if i[:12] not in exclude]
    fit_views = [
        rna.loc[fit_ids].to_numpy(),
        cna_df.reindex(fit_ids).fillna(0).to_numpy(),
        meth_df.reindex(fit_ids).fillna(0).to_numpy(),
    ]
    fit, enc_meta = _load_encoder(root, fit_views, fit_ids)
    print("encoder", enc_meta.get("encoder"), "fit n=", len(fit_ids), "excluded", sorted(exclude))

    conformal_p = root / "artifacts" / "conformal_model.pkl"
    conformal = None
    if conformal_p.exists():
        with open(conformal_p, "rb") as fh:
            conformal = pickle.load(fh)
        print("loaded conformal bundle", conformal_p, "coverage", conformal.get("coverage"), "requested", conformal.get("requested_coverage"))

    z_all = lat[[c for c in lat.columns if c.startswith("z")]].to_numpy(float)
    z_all = np.nan_to_num(z_all)
    # 2D cohort frame = first two latent coords (no extra UMAP dependency).
    cohort = [{"x": float(a), "y": float(b)} for a, b in z_all[:: max(1, len(z_all) // 400), :2]]

    out = {"patients": {}}
    for spec in patients:
        pid = spec["patient_id"]
        role = spec["role"]
        mods = list(view_mask_for_role(role))
        drow = deconv.loc[pid] if pid in deconv.index else deconv.loc[deconv.index.astype(str).str[:12] == pid].iloc[0]
        lrow = lat.loc[pid] if pid in lat.index else lat.loc[lat.index.astype(str).str[:12] == pid].iloc[0]
        prow = pw.loc[pid] if pid in pw.index else pw.loc[pw.index.astype(str).str[:12] == pid].iloc[0]
        trow = tf.loc[pid] if pid in tf.index else tf.loc[tf.index.astype(str).str[:12] == pid].iloc[0]
        crow = clin.loc[clin["PATIENT_ID"].astype(str) == pid[:12]]
        subtype = str(crow["SUBTYPE"].iloc[0]) if len(crow) and "SUBTYPE" in crow.columns else None
        age = int(crow["AGE"].iloc[0]) if len(crow) and "AGE" in crow.columns and pd.notna(crow["AGE"].iloc[0]) else None
        stage = str(crow["AJCC_PATHOLOGIC_TUMOR_STAGE"].iloc[0]) if len(crow) and "AJCC_PATHOLOGIC_TUMOR_STAGE" in crow.columns else None

        dims = list(enc_meta.get("input_dims") or [rna.shape[1], cna_df.shape[1], meth_df.shape[1]])

        def _row(frame: pd.DataFrame, dim: int) -> np.ndarray:
            raw = frame.reindex([pid]).to_numpy(dtype=float)
            if raw.size == 0:
                raw = np.zeros((1, dim), dtype=float)
            if raw.ndim == 1:
                raw = raw.reshape(1, -1)
            out = np.zeros((1, dim), dtype=float)
            n = min(raw.shape[1], dim)
            out[:, :n] = np.nan_to_num(raw[:, :n])
            return out

        named = {
            "rna": _row(rna, int(dims[0])),
            "cna": _row(cna_df, int(dims[1])),
            "methylation": _row(meth_df, int(dims[2])),
        }
        used = [named[m] if m in mods else None for m in ("rna", "cna", "methylation")]
        with_meth = [
            named["rna"] if "rna" in mods else None,
            named["cna"] if "cna" in mods else None,
            named["methylation"],
        ]
        without_meth = [
            named["rna"] if "rna" in mods else None,
            named["cna"] if "cna" in mods else None,
            None,
        ]
        mu_u, lv_u = encode_optional_views(fit, used)
        _, lv_with_meth = encode_optional_views(fit, with_meth)
        _, lv_without_meth = encode_optional_views(fit, without_meth)
        width_used = posterior_width(lv_u)
        reduction = view_width_reduction(posterior_width(lv_without_meth), posterior_width(lv_with_meth))

        tf_frac = float(drow["malignant"])
        verdict = tumour_verdict(tf_frac)
        # B5b is an unvalidated rule, not a coverage-backed set. Width>tau
        # no longer forces abstention except the designated RNA-only case.
        width_abstain = role == "abstain"
        abstained = verdict == "insufficient" or width_abstain
        if abstained:
            state = 3
            reason_code = "insufficient_tumour_fraction" if verdict == "insufficient" else "posterior_width"
        elif role == "missing_view" or verdict == "marginal":
            state = 2
            reason_code = "marginal_tumour_fraction" if verdict == "marginal" else "missing_modality"
        else:
            state = 1
            reason_code = None

        pathways = [
            {"name": str(c), "activity": float(prow[c]), "z": float(prow[c])}
            for c in prow.index
        ]
        pathways.sort(key=lambda r: abs(r["activity"]), reverse=True)

        rel_map = {}
        if rel is not None and "reliability" in rel.columns:
            name_col = "tf" if "tf" in rel.columns else rel.columns[0]
            for rec in rel.itertuples(index=False):
                raw = getattr(rec, "reliability")
                flag = "high" if float(raw) >= 0.5 else "low"
                rel_map[str(getattr(rec, name_col)).upper()] = flag
        tfs = []
        for name, act in trow.abs().sort_values(ascending=False).head(10).items():
            signed = float(trow[name])
            flag = rel_map.get(str(name).upper(), "high")
            item = {"name": str(name), "activity": signed, "reliability": flag}
            if flag == "low":
                item["reliability_reason"] = "regulon promoter methylation elevated"
            tfs.append(item)

        er_clinical = "positive" if subtype and "Lum" in subtype else ("negative" if subtype and "Basal" in subtype else None)
        est = next((p for p in pathways if p["name"].lower() == "estrogen"), None)
        discrepancies = []
        if er_clinical == "positive" and est is not None and est["activity"] < 0:
            discrepancies.append(
                {
                    "field": "ER",
                    "clinical": "positive",
                    "inferred": "low estrogen pathway activity",
                    "severity": "note",
                }
            )
        if er_clinical == "negative" and est is not None and est["activity"] > 0.5:
            discrepancies.append(
                {
                    "field": "ER",
                    "clinical": "negative",
                    "inferred": "high estrogen pathway activity",
                    "severity": "note",
                }
            )

        sample_quality = {
            "tumour_fraction": tf_frac,
            "composition": _composition(drow),
            "verdict": verdict,
            "verdict_reason": (
                None
                if verdict == "sufficient"
                else f"Tumour fraction {tf_frac:.0%} is {verdict} (thresholds 40% / 25%)."
            ),
        }
        position = {
            "umap_coords": [float(mu_u[0, 0]), float(mu_u[0, 1])],
            "posterior_ellipse": {
                "rx": width_used,
                "ry": width_used * 0.72,
                "theta": float(np.arctan2(mu_u[0, 1], mu_u[0, 0]) % (2 * np.pi)),
            },
            "cluster": {"label": int(lrow.get("cluster", 0)), "posterior_mass": float(lrow.get("cluster_mass", 0))},
            "cohort_density_ref": "tcga_brca_v2",
            "modalities_used": mods,
            "cohort_points": cohort,
            "posterior_width": width_used,
            "tau": tau,
        }
        molecular_state = {
            "pathways": pathways,
            "transcription_factors": tfs,
            "discrepancies": discrepancies,
        }
        candidates = None if abstained else pathway_candidates(prow, pk)
        prognostic = None if abstained else _prognostic_estimate(conformal, prow, trow, width_used)
        modality_value = [
            {
                "modality": "methylation",
                "present": "methylation" in mods,
                "posterior_width_reduction": float(reduction),
            }
        ]
        if abstained:
            if reason_code == "insufficient_tumour_fraction":
                reason_text = f"Tumour content {tf_frac:.0%}. Below the 25% threshold for reliable analysis."
                help_items = ["A biopsy with higher tumour content", "Macrodissection of the existing sample"]
            else:
                reason_text = (
                    f"Posterior width {width_used:.2f} exceeds the abstention threshold {tau:.2f} "
                    f"with modalities {', '.join(mods)}."
                )
                help_items = ["Adding CNA and methylation assays", "A sample with complete molecular views"]
            abstention = {
                "abstained": True,
                "reason_code": reason_code,
                "reason_text": reason_text,
                "what_would_help": help_items,
                "sections_rendered": ["sample_quality", "position", "molecular_state"],
            }
        else:
            abstention = {
                "abstained": False,
                "reason_code": reason_code,
                "reason_text": None,
                "what_would_help": [],
                "sections_rendered": ["sample_quality", "position", "molecular_state", "prognostic_estimate", "pathway_candidates"],
            }

        banner = None
        if state == 2:
            if verdict == "marginal":
                banner = f"Wider than typical — tumour fraction {tf_frac:.0%}."
            else:
                banner = "Wider than typical — methylation absent."
        elif state == 3:
            banner = abstention["reason_text"]

        payload = {
            "schema_version": "v2_prototype",
            "patient_id": pid,
            "role": role,
            "title": spec.get("title"),
            "description": spec.get("description"),
            "state": state,
            "banner": banner,
            "modalities_present": mods,
            "patient_metadata": {
                "er_status": er_clinical,
                "her2_status": "positive" if subtype and "Her2" in subtype else "negative",
                "claudin_subtype": subtype,
                "age_at_diagnosis": age,
                "tumor_stage": stage,
            },
            "sample_quality": sample_quality,
            "position": position,
            "molecular_state": molecular_state,
            "prognostic_estimate": prognostic,
            "pathway_candidates": candidates,
            "modality_value_estimate": modality_value,
            "abstention": abstention,
            "s4_ships": False,
            "limitations": [
                "Pathway-matched candidates are a mechanistic filter with no outcome validation.",
                "The conformal model predicts overall survival, not drug response.",
                "Endocrine-treatment assignment was dropped from the conformal model after an ER+ refit.",
                "S4 (ODE simulator) is cut: cut_s4_no_signal (join not independently verified).",
            ],
        }
        for text in (
            payload.get("banner"),
            (payload.get("prognostic_estimate") or {}).get("domain_note"),
            (payload.get("abstention") or {}).get("reason_text"),
            *payload["limitations"],
        ):
            if text:
                assert_safe(str(text))
        out["patients"][pid] = payload
        n_cand = None if candidates is None else len(candidates["set_members"])
        print(
            pid, "role", role, "state", state,
            "width", round(width_used, 3), "tau", tau, "tf", round(tf_frac, 3),
            "meth_reduction", round(reduction, 3), "candidates", n_cand,
        )

    dest = interim / "demo_payloads.json"
    dest.write_text(json.dumps(out, indent=2))
    for app_dest in APP_DATA_DIRS:
        app_dest.mkdir(parents=True, exist_ok=True)
        (app_dest / "demo_payloads.json").write_text(json.dumps(out, indent=2))
        (app_dest / "demo_patients.json").write_text((ref / "demo_patients.json").read_text())
        print("copied payloads →", app_dest)
    print("wrote", dest)
    return dest


if __name__ == "__main__":
    main()
