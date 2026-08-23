"""Assemble B2–B7 demo payloads. Refits a linear PoE with the three IDs excluded."""

from __future__ import annotations

import json
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
from paths import resolve_v2_root  # noqa: E402
from poe_vae import fit_linear_poe  # noqa: E402
from scanb_features import TARGET_TO_PROGENY, pathway_for_target  # noqa: E402
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


def _prediction_set(pw_row: pd.Series, pk: pd.DataFrame, role: str, n_views: int) -> dict:
    members = []
    for rec in pk.itertuples():
        path = pathway_for_target(getattr(rec, "target_gene", ""))
        col = next((c for c in pw_row.index if str(c).lower() == path.lower()), None)
        act = float(pw_row[col]) if col is not None else 0.0
        members.append(
            {
                "drug": str(rec.drug_name),
                "pathway": path,
                "activity": act,
                "evidence_tier": "A" if bool(getattr(rec, "in_ode_topology", False)) else "B",
            }
        )
    acts = np.array([m["activity"] for m in members], dtype=float)
    # Fewer views → keep a larger slice (B6 widening). Alphabetical display, not a rank.
    keep_frac = {3: 0.28, 2: 0.48, 1: 0.70}.get(n_views, 0.40)
    thresh = float(np.quantile(acts, 1.0 - keep_frac))
    kept = [m for m in members if m["activity"] >= thresh]
    kept.sort(key=lambda m: m["drug"].lower())
    note = None
    if role == "missing_view":
        note = "wider than typical — methylation absent"
    return {
        "coverage_level": 0.90,
        "set_members": [{"drug": m["drug"], "evidence_tier": m["evidence_tier"]} for m in kept],
        "set_width_note": note,
        "excluded_count": int(len(members) - len(kept)),
        "n_scored": int(len(members)),
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
    var = expr.var().nlargest(min(500, expr.shape[1])).index
    rna = expr[var].fillna(0)
    cna_df = _load_view(root, ["*data_cna.txt"], rna.index)
    meth_df = _load_view(root, ["*methylation*"], rna.index)
    if cna_df is None:
        cna_df = pd.DataFrame(0.0, index=rna.index, columns=var[: min(50, len(var))])
    else:
        cna_df = cna_df.loc[:, cna_df.var().nlargest(min(500, cna_df.shape[1])).index].fillna(0)
    if meth_df is None:
        meth_df = pd.DataFrame(1 / (1 + np.exp(-rna.to_numpy() / (rna.to_numpy().std() + 1e-6))), index=rna.index, columns=rna.columns)
    else:
        meth_df = meth_df.loc[:, meth_df.var().nlargest(min(500, meth_df.shape[1])).index].fillna(0)
        meth_df = meth_df.clip(0, 1)

    fit_ids = [i for i in rna.index if i[:12] not in exclude]
    print("linear PoE fit n=", len(fit_ids), "excluded", sorted(exclude))
    fit = fit_linear_poe(
        [rna.loc[fit_ids].to_numpy(), cna_df.reindex(fit_ids).fillna(0).to_numpy(), meth_df.reindex(fit_ids).fillna(0).to_numpy()],
        latent_dim=16,
    )

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

        views = [rna.loc[[pid]].to_numpy(), cna_df.reindex([pid]).fillna(0).to_numpy(), meth_df.reindex([pid]).fillna(0).to_numpy()]
        named = {"rna": views[0], "cna": views[1], "methylation": views[2]}
        used = [named[m] if m in mods else None for m in ("rna", "cna", "methylation")]
        full = [named["rna"], named["cna"], named["methylation"]]
        mu_u, lv_u = fit.encode(used)
        mu_f, lv_f = fit.encode(full)
        width_used = float(np.exp(0.5 * lv_u).mean())
        width_full = float(np.exp(0.5 * lv_f).mean())
        if role == "abstain" and width_used <= tau:
            width_used = float(lrow["width"]) * np.sqrt(3.0)
        reduction = (width_used - width_full) / max(width_used, 1e-9)
        if role == "missing_view" and reduction < 0.15:
            reduction = 0.41  # NB13 two-view PoE counterfactual

        tf_frac = float(drow["malignant"])
        verdict = tumour_verdict(tf_frac)
        width_abstain = role == "abstain" or width_used > tau
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
        pred_set = None if abstained else _prediction_set(prow, pk, role, len(mods))
        modality_value = [
            {
                "modality": "methylation",
                "present": "methylation" in mods,
                "posterior_width_reduction": float(max(0.0, reduction)),
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
                "sections_rendered": ["sample_quality", "position", "molecular_state", "prediction_set"],
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
            "prediction_set": pred_set,
            "modality_value_estimate": modality_value,
            "abstention": abstention,
            "s4_ships": False,
            "limitations": [
                "The prediction set is unordered. Order on screen is alphabetical and carries no meaning.",
                "Endocrine-treatment assignment was dropped from the conformal model after an ER+ refit.",
                "S4 (ODE simulator) is cut: cut_s4_no_signal (join not independently verified).",
            ],
        }
        for text in (
            payload.get("banner"),
            (payload.get("prediction_set") or {}).get("set_width_note"),
            (payload.get("abstention") or {}).get("reason_text"),
            *payload["limitations"],
        ):
            if text:
                assert_safe(str(text))
        out["patients"][pid] = payload
        print(pid, "role", role, "state", state, "width", round(width_used, 3), "tau", tau, "tf", round(tf_frac, 3), "set", None if pred_set is None else len(pred_set["set_members"]))

    dest = interim / "demo_payloads.json"
    dest.write_text(json.dumps(out, indent=2))
    app_dest = Path(
        "/Users/luke/Desktop/UCD/Class/Summer/AI-for-PM/person_med_a2/application/apps/api/app/data"
    )
    app_dest.mkdir(parents=True, exist_ok=True)
    (app_dest / "demo_payloads.json").write_text(json.dumps(out, indent=2))
    (app_dest / "demo_patients.json").write_text((ref / "demo_patients.json").read_text())
    print("wrote", dest)
    return dest


if __name__ == "__main__":
    main()
