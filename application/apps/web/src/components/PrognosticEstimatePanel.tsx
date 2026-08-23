"use client";

import type { PrognosticEstimate } from "@/lib/types";
import { GlossaryAffordance } from "@/components/GlossaryAffordance";

function daysLabel(value: number): string {
  if (value >= 365) return `${(value / 365).toFixed(1)} years`;
  return `${Math.round(value)} days`;
}

export function PrognosticEstimatePanel({ data }: { data: PrognosticEstimate }) {
  const coveragePct = Math.round(data.requested_coverage * 100);
  const empiricalPct = data.empirical_coverage == null ? null : (data.empirical_coverage * 100).toFixed(1);
  const hasInterval = Boolean(data.interval_days && data.interval_days.length === 2);

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <header className="flex items-start justify-between gap-3">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-400">
            4 · Prognostic estimate
          </p>
          <h2 className="mt-1 text-lg font-semibold text-slate-950">{data.label}</h2>
          <p className="mt-2 text-sm font-medium text-slate-800">
            Survival interval from the conformal model — not a drug set.
          </p>
        </div>
        <GlossaryAffordance panel="prognostic_estimate" />
      </header>
      {hasInterval ? (
        <p className="mt-4 text-2xl font-semibold tabular-nums text-slate-950">
          {daysLabel(data.interval_days![0])} – {daysLabel(data.interval_days![1])}
        </p>
      ) : (
        <p className="mt-4 text-sm text-slate-600">Interval not available for this sample.</p>
      )}
      {data.point_days != null && (
        <p className="mt-1 text-sm text-slate-600">Point estimate {daysLabel(data.point_days)}.</p>
      )}
      <p className="mt-4 text-xs text-slate-500">
        Requested coverage {coveragePct}%
        {empiricalPct != null ? ` · empirical ${empiricalPct}%` : ""}
        {data.n ? ` · n=${data.n}` : ""} · {data.method}
      </p>
      <p className="mt-2 text-xs text-slate-500">{data.domain_note}</p>
    </section>
  );
}
