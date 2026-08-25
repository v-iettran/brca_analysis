import type { V3CohortPayload, V3PatientPayload } from "@/lib/v3-types";
import { formatP, subgroupLabel } from "@/lib/v3-format";

export function panelTakeaways(
  cohort: V3CohortPayload,
  patient: V3PatientPayload,
  opts?: { exploratory?: boolean }
): Record<string, string> {
  const stored = { ...(cohort.takeaways || {}), ...(patient.takeaways || {}) };
  const k = cohort.preregistered.k;
  const tf = patient.sample_quality.tumour_fraction;
  const cl = patient.position.cluster.label;
  const mass = patient.position.cluster.posterior_mass;
  const a2 = cohort.gates.a2;
  const nLines = patient.nearest_lines?.length ?? 0;
  const nDrugs = patient.reversal_candidates?.members.length ?? 0;
  const profiles = (cohort.cluster_profiles || []).filter(
    (row) => Number(row.cluster) === cl && row.family === "pathway" && Number(row.q) < 0.05
  ) as Array<{ feature: string; effect: number }>;
  profiles.sort((a, b) => Math.abs(b.effect) - Math.abs(a.effect));
  const pathBits = profiles.slice(0, 2).map((r) => `${r.effect > 0 ? "elevated" : "reduced"} ${r.feature}`);
  const fallback: Record<string, string> = {
    quality: `${Math.round(tf * 100)}% tumour content — ${patient.sample_quality.verdict} for analysis.`,
    structure: k
      ? `The data supports ${k} subgroups.`
      : "No stable discrete structure was found.",
    projection: `This patient falls in ${subgroupLabel(cl)} (${Math.round(mass * 100)}% membership).`,
    survival: opts?.exploratory
      ? "These Kaplan–Meier curves are an exploratory overlay. No p-value is shown."
      : a2.framing === "prognostic" && a2.p_os != null
        ? `The ${k} subgroups differ in overall survival (p = ${formatP(a2.p_os)}).`
        : `These subgroups differ molecularly but did not separate survival${a2.p_os != null ? ` (p = ${formatP(a2.p_os)})` : ""}.`,
    characteristics: pathBits.length
      ? `${subgroupLabel(cl)} is defined by ${pathBits.join(" and ")} signalling.`
      : `${subgroupLabel(cl)} has no pathway passing q < 0.05 versus the rest of the cohort.`,
    retrieval: patient.state === 3 || patient.abstention.abstained
      ? "Drug retrieval is withheld because this encoding abstains."
      : nDrugs
        ? `${nLines} cell lines resemble this tumour; these compounds reverse its signature.`
        : nLines
          ? `${nLines} cell lines resemble this tumour. Signature reversal is withheld.`
          : "No measured cell-line neighbours were retrieved.",
  };
  return { ...fallback, ...stored };
}
