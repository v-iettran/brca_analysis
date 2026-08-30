#!/usr/bin/env python3
"""Recompute the payload objects derived from cluster_profiles.

`run_real_pathways.py` replaced `cluster_profiles` with real PROGENy/CollecTRI
scores but left three things behind that are computed from it:

  * `comparison_matrix` — still ranked globally, so the heatmap carried 2 of 14
    pathways;
  * patient `takeaways` — the characteristics line contradicted the profiles it
    is generated from;
  * `tf_reliability` — an empty list, so the drawer had no methylation flag.

None of this retunes k or re-evaluates a gate. It re-derives what was stale.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import certifi

os.environ.setdefault("SSL_CERT_FILE", certifi.where())
os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())

V2_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V2_ROOT / "src"))

import pandas as pd  # noqa: E402

from cluster_stats import comparison_matrix  # noqa: E402
from methylation_tf_reliability import methylation_silencing_reliability  # noqa: E402
from v3_payload import copy_payloads_to_app, v3_interim  # noqa: E402
from v3_takeaways import cohort_takeaways, patient_takeaways  # noqa: E402

TCGA = V2_ROOT / "data" / "raw" / "tcga_brca" / "extracted" / "brca_tcga_pan_can_atlas_2018"


def gene_methylation() -> pd.DataFrame | None:
    """Probe-level hm450 collapsed to a samples x genes beta matrix."""
    path = TCGA / "data_methylation_hm450.txt"
    if not path.is_file():
        return None
    raw = pd.read_csv(path, sep="\t", low_memory=False)
    if "NAME" not in raw.columns:
        return None
    values = raw.drop(columns=[c for c in ("ENTITY_STABLE_ID", "DESCRIPTION", "TRANSCRIPT_ID") if c in raw.columns])
    values = values.groupby("NAME").mean(numeric_only=True)
    out = values.T
    out.index = out.index.astype(str).str[:12]
    return out


def tf_regulons(tfs: list[str]) -> dict[str, list[str]]:
    try:
        import decoupler as dc

        net = dc.op.collectri(organism="human")
    except Exception as exc:  # noqa: BLE001
        print(f"  CollecTRI unavailable ({exc}); regulons limited to the TF itself")
        return {tf: [tf] for tf in tfs}
    src = "source" if "source" in net.columns else net.columns[0]
    tgt = "target" if "target" in net.columns else net.columns[1]
    grouped = net.groupby(src)[tgt].apply(lambda s: sorted(set(s.astype(str))))
    return {tf: list(grouped.get(tf, [tf])) for tf in tfs}


def main() -> int:
    dest = v3_interim(V2_ROOT)
    cohort_p = dest / "cohort_payload.json"
    cohort = json.loads(cohort_p.read_text())
    profiles = pd.DataFrame(cohort["cluster_profiles"])
    print(f"profiles: {len(profiles)} rows · families {profiles['family'].value_counts().to_dict()}")

    # 1. comparison matrix, selected per family
    matrix = comparison_matrix(profiles)
    fams = pd.Series(matrix["families"]).value_counts().to_dict()
    cohort["comparison_matrix"] = matrix
    print(f"comparison_matrix: {len(matrix['features'])} rows · {fams}")

    # 2. methylation reliability for the TFs actually on screen
    tfs = [f for f, fam in zip(matrix["features"], matrix["families"]) if fam == "tf"]
    meth = gene_methylation()
    if meth is None:
        print("  no methylation matrix on disk")
    else:
        print(f"  methylation {meth.shape[0]} samples x {meth.shape[1]} genes")
    rel = methylation_silencing_reliability(tf_regulons(tfs), meth)
    cohort["tf_reliability"] = rel.to_dict(orient="records")
    print(f"tf_reliability: {len(rel)} TFs · {rel['reliability'].value_counts().to_dict()}")

    # 3. takeaways regenerated from the current profiles
    cohort["takeaways"] = cohort_takeaways(cohort)
    cohort_p.write_text(json.dumps(cohort, indent=2))

    patients = {}
    for path in sorted(dest.glob("payload_*.json")):
        payload = json.loads(path.read_text())
        before = (payload.get("takeaways") or {}).get("characteristics")
        payload["takeaways"] = {**cohort["takeaways"], **patient_takeaways(cohort, payload)}
        after = payload["takeaways"]["characteristics"]
        if before != after:
            print(f"  {payload['patient_id']}\n    was: {before}\n    now: {after}")
        path.write_text(json.dumps(payload, indent=2))
        patients[payload["patient_id"]] = payload
    copy_payloads_to_app(cohort, patients, V2_ROOT.parent)
    print("payloads copied to the app")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
