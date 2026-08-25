"""One-line panel takeaways. Every string is run through assert_safe."""

from __future__ import annotations

from safety import assert_safe


def _fmt_p(value: float | None) -> str | None:
    if value is None:
        return None
    if value < 0.001:
        return "<0.001"
    return f"{value:.3f}"


def _subgroup(label: int) -> str:
    return f"Subgroup {int(label) + 1}"


def _top_pathways(cohort: dict, cluster: int, n: int = 2) -> list[str]:
    rows = [
        r
        for r in (cohort.get("cluster_profiles") or [])
        if int(r.get("cluster") or -1) == cluster and r.get("family") == "pathway" and float(r.get("q") or 1) < 0.05
    ]
    rows.sort(key=lambda r: abs(float(r.get("effect") or 0)), reverse=True)
    names = []
    for row in rows[:n]:
        direction = "elevated" if float(row.get("effect") or 0) > 0 else "reduced"
        names.append(f"{direction} {row.get('feature')}")
    return names


def cohort_takeaways(cohort: dict) -> dict[str, str]:
    k = cohort.get("preregistered", {}).get("k")
    a1 = (cohort.get("gates") or {}).get("a1") or {}
    a2 = (cohort.get("gates") or {}).get("a2") or {}
    n = int(cohort.get("n_samples") or 0)
    source = cohort.get("cohort_source") or "this cohort"
    if a1.get("clustering_available") and k:
        structure = f"The data supports {k} subgroups (n = {n}, {source})."
    else:
        structure = f"No stable discrete structure in this {source} cohort (n = {n})."
    p = _fmt_p(a2.get("p_os"))
    if a2.get("passed") and k and p:
        survival = f"The {k} subgroups differ in overall survival (p = {p})."
    elif k and p:
        survival = f"These subgroups differ molecularly but did not separate survival (p = {p})."
    else:
        survival = "Survival is shown as a descriptive overlay, not a selection criterion."
    out = {"structure": structure, "survival": survival}
    for text in out.values():
        assert_safe(text, "takeaway")
    return out


def patient_takeaways(cohort: dict, patient: dict) -> dict[str, str]:
    tf = float((patient.get("sample_quality") or {}).get("tumour_fraction") or 0)
    verdict = (patient.get("sample_quality") or {}).get("verdict") or "unknown"
    quality = f"{tf:.0%} tumour content — {verdict} for analysis."
    pos = (patient.get("position") or {}).get("cluster") or {}
    label = int(pos.get("label") or 0)
    mass = float(pos.get("posterior_mass") or 0)
    projection = f"This patient falls in {_subgroup(label)} ({mass:.0%} membership)."
    paths = _top_pathways(cohort, label)
    if paths:
        characteristics = f"{_subgroup(label)} is defined by {', '.join(paths)} signalling."
    else:
        characteristics = f"{_subgroup(label)} has no pathway passing q < 0.05 versus the rest of the cohort."
    lines = patient.get("nearest_lines") or []
    drugs = ((patient.get("reversal_candidates") or {}) or {}).get("members") or []
    if patient.get("state") == 3 or (patient.get("abstention") or {}).get("abstained"):
        retrieval = "Drug retrieval is withheld because this encoding abstains."
    elif drugs:
        retrieval = (
            f"{len(lines)} cell lines resemble this tumour; "
            f"{len(drugs)} compounds reverse its signature. Compounds are shown as evidence, not as recommendations."
        )
    elif lines:
        retrieval = (
            f"{len(lines)} cell lines resemble this tumour. "
            "Signature reversal is withheld. Compounds are shown as evidence, not as recommendations."
        )
    else:
        retrieval = "No measured cell-line neighbours were retrieved for this tumour."
    out = {
        "quality": quality,
        "projection": projection,
        "characteristics": characteristics,
        "retrieval": retrieval,
    }
    for text in out.values():
        assert_safe(text, "takeaway")
    return out
