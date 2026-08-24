"use client";

import { clusterColor } from "@/lib/clusterPalette";
import type { V3ClusterAnnotation, V3CohortPayload } from "@/lib/v3-types";

export function ClusterDrawer({
  cluster,
  k,
  annotation,
  cohort,
  onClose,
}: {
  cluster: number;
  k: number;
  annotation?: V3ClusterAnnotation;
  cohort: V3CohortPayload;
  onClose: () => void;
}) {
  const profiles = cohort.cluster_profiles.filter((row) => Number(row.cluster) === cluster) as Array<{
    feature: string;
    family: string;
    effect: number;
    q: number;
    log2fc?: number;
  }>;
  const pathways = profiles.filter((r) => r.family === "pathway").sort((a, b) => a.q - b.q).slice(0, 8);
  const tfs = profiles.filter((r) => r.family === "tf").sort((a, b) => a.q - b.q).slice(0, 8);
  const genes = profiles.filter((r) => r.family === "gene").sort((a, b) => a.q - b.q).slice(0, 8);
  const rel = Object.fromEntries((cohort.tf_reliability ?? []).map((r) => [r.tf, r]));

  return (
    <aside className="w-full max-w-md rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-4 shadow-sm">
      <header className="flex items-start justify-between gap-2">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-400">Cluster drawer</p>
          <h3 className="mt-1 flex items-center gap-2 text-lg font-semibold">
            <span className="inline-block h-3 w-3 rounded-full" style={{ background: clusterColor(cluster, k) }} />
            Subgroup {cluster}
            <span className="font-mono text-sm text-slate-400">n={annotation?.n ?? "—"}</span>
          </h3>
        </div>
        <button type="button" onClick={onClose} className="text-sm text-slate-500">
          Close
        </button>
      </header>
      {annotation?.pam50_majority && <p className="mt-2 text-sm text-slate-600">PAM50 majority {annotation.pam50_majority}</p>}
      <h4 className="mt-4 text-xs font-semibold uppercase tracking-wide text-slate-400">Pathways</h4>
      <ul className="mt-1 space-y-1">
        {pathways.map((row) => (
          <li key={row.feature} className="flex items-center gap-2 text-sm">
            <span className="w-24 truncate">{row.feature}</span>
            <span className="h-2 flex-1 rounded-full bg-slate-100">
              <span
                className="block h-2 rounded-full bg-teal-700"
                style={{ width: `${Math.min(100, Math.abs(row.effect) * 50)}%` }}
              />
            </span>
            <span className="font-mono text-[11px]">q={row.q.toFixed(3)}</span>
          </li>
        ))}
      </ul>
      <h4 className="mt-4 text-xs font-semibold uppercase tracking-wide text-slate-400">Transcription factors</h4>
      <ul className="mt-1 space-y-1 text-sm">
        {tfs.map((row) => {
          const flag = rel[row.feature];
          const silenced = flag?.reliability === "low";
          return (
            <li key={row.feature} className={silenced ? "text-slate-400" : ""}>
              {row.feature}
              {silenced ? " · methylation-silenced regulon" : ""}
            </li>
          );
        })}
      </ul>
      <h4 className="mt-4 text-xs font-semibold uppercase tracking-wide text-slate-400">Genes</h4>
      <ul className="mt-1 space-y-1 font-mono text-[11px]">
        {genes.map((row) => (
          <li key={row.feature}>
            {row.feature} log2FC {(row.log2fc ?? row.effect).toFixed(2)} · q={row.q.toFixed(3)}
          </li>
        ))}
      </ul>
      <p className="mt-4 text-xs text-slate-500">
        Versus adjacent-normal epithelium
        {annotation?.basal_enriched ? " · strongest proliferation in this basal-enriched subgroup." : "."} Field-effect and small n apply.
      </p>
    </aside>
  );
}
