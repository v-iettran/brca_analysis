import type { PatientMetadata } from "@/lib/types";
import { cleanClinicalStatus } from "@/lib/format";

function cleanStatus(value?: string | null): string {
  const cleaned = cleanClinicalStatus(value);
  return cleaned === "n/a" ? "Not recorded" : cleaned;
}

function provenanceLabel(metadata: PatientMetadata, field: string): string | null {
  const provenance = metadata.field_provenance as Record<string, string> | null | undefined;
  if (!provenance || !provenance[field]) return null;
  return provenance[field];
}

function formatNumber(value: unknown, digits = 1): string | null {
  const n = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(n)) return null;
  return n.toFixed(digits);
}

function formatOrganFunction(organ: Record<string, unknown>): string {
  if (!Object.keys(organ).length) return "Not recorded";
  const parts: string[] = [];
  const creatinine = formatNumber(organ.creatinine_mg_dl ?? organ.creatinine, 2);
  const bilirubin = formatNumber(organ.bilirubin_mg_dl ?? organ.bilirubin, 2);
  const alt = formatNumber(organ.alt_u_l ?? organ.alt, 1);
  if (creatinine) parts.push(`Creatinine ${creatinine} mg/dL`);
  if (bilirubin) parts.push(`Bilirubin ${bilirubin} mg/dL`);
  if (alt) parts.push(`ALT ${alt} U/L`);
  // Any remaining lab keys with humanized labels.
  for (const [key, value] of Object.entries(organ)) {
    if (["creatinine_mg_dl", "creatinine", "bilirubin_mg_dl", "bilirubin", "alt_u_l", "alt"].includes(key)) {
      continue;
    }
    const formatted = formatNumber(value, 1) ?? String(value);
    const label = key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
    parts.push(`${label} ${formatted}`);
  }
  return parts.length ? parts.join(" · ") : "Not recorded";
}

function formatLocation(location: Record<string, unknown>): string {
  if (!Object.keys(location).length) return "Not recorded";
  const city = location.city != null ? String(location.city) : "";
  const country = location.country != null ? String(location.country) : "";
  if (city && country) return `${city}, ${country}`;
  if (city || country) return city || country;
  return "Not recorded";
}

function ProfileItem({
  label,
  value,
  provenance,
}: {
  label: string;
  value: string;
  provenance?: string | null;
}) {
  return (
    <div className="min-w-0">
      <dt className="text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-400">{label}</dt>
      <dd className="mt-1 break-words text-sm font-medium leading-5 text-slate-800" title={value}>
        {value}
      </dd>
      {provenance && (
        <p className="mt-0.5 text-[10px] font-medium text-slate-400">
          {provenance === "demo_generated" || provenance === "generated" ? "Demo-generated" : "METABRIC-derived"}
        </p>
      )}
    </div>
  );
}

export function PatientProfileCard({
  patientLabel,
  metadata,
  regimen,
}: {
  patientLabel: string;
  metadata: PatientMetadata;
  regimen: string[];
}) {
  const organ = (metadata.organ_function || {}) as Record<string, unknown>;
  const location = (metadata.location || {}) as Record<string, unknown>;

  return (
    <section className="overflow-hidden rounded-2xl border border-slate-200/80 bg-white shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 bg-gradient-to-r from-slate-50 to-white px-5 py-4">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-indigo-600 text-sm font-bold text-white shadow-sm">
            PT
          </div>
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-indigo-600">
              De-identified patient
            </p>
            <h2 className="font-mono text-sm font-semibold text-slate-900">{patientLabel}</h2>
          </div>
        </div>
        <div className="rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-xs font-medium text-emerald-700">
          Data remains local
        </div>
      </div>

      <dl className="grid grid-cols-2 gap-x-5 gap-y-4 px-5 py-5 sm:grid-cols-4 xl:grid-cols-7">
        <ProfileItem
          label="Age"
          value={
            metadata.age_at_diagnosis != null
              ? `${Math.round(metadata.age_at_diagnosis)} years`
              : "Not recorded"
          }
          provenance={provenanceLabel(metadata, "age_at_diagnosis")}
        />
        <ProfileItem label="ER" value={cleanStatus(metadata.er_status)} provenance={provenanceLabel(metadata, "er_status")} />
        <ProfileItem label="PR" value={cleanStatus(metadata.pr_status)} provenance={provenanceLabel(metadata, "pr_status")} />
        <ProfileItem label="HER2" value={cleanStatus(metadata.her2_status)} provenance={provenanceLabel(metadata, "her2_status")} />
        <ProfileItem
          label="Stage"
          value={cleanStatus(metadata.tumor_stage)}
          provenance={provenanceLabel(metadata, "tumor_stage")}
        />
        <ProfileItem
          label="Grade"
          value={metadata.tumor_grade != null ? String(metadata.tumor_grade) : "Not recorded"}
          provenance={provenanceLabel(metadata, "tumor_grade")}
        />
        <ProfileItem
          label="Tumour size"
          value={metadata.tumor_size_mm != null ? `${metadata.tumor_size_mm} mm` : "Not recorded"}
          provenance={provenanceLabel(metadata, "tumor_size_mm")}
        />
        <ProfileItem
          label="ECOG"
          value={metadata.ecog_status != null ? String(metadata.ecog_status) : "Not recorded"}
          provenance={provenanceLabel(metadata, "ecog_status")}
        />
        <ProfileItem
          label="Nodes+"
          value={
            metadata.lymph_nodes_positive != null
              ? String(Math.round(metadata.lymph_nodes_positive))
              : "Not recorded"
          }
        />
        <ProfileItem label="Prior therapy" value={cleanStatus(metadata.prior_therapy)} provenance={provenanceLabel(metadata, "prior_therapy")} />
        <ProfileItem
          label="Organ function"
          value={formatOrganFunction(organ)}
          provenance={provenanceLabel(metadata, "organ_function")}
        />
        <ProfileItem
          label="Location"
          value={formatLocation(location)}
          provenance={provenanceLabel(metadata, "location")}
        />
        <ProfileItem
          label="Administered regimen"
          value={regimen.length > 0 ? regimen.join(" + ") : "Not recorded"}
        />
      </dl>
    </section>
  );
}
