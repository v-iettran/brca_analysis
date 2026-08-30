"use client";

import type { PrognosticEstimate } from "@/lib/types";
import { GlossaryAffordance } from "@/components/GlossaryAffordance";
import { PanelCard } from "@/components/PanelCard";

function daysLabel(value: number): string {
  if (value >= 365) return `${(value / 365).toFixed(1)} yr`;
  return `${Math.round(value)} d`;
}

export function PrognosticEstimatePanel({ data }: { data: PrognosticEstimate }) {
  const coveragePct = Math.round(data.requested_coverage * 100);
  const empiricalPct = data.empirical_coverage == null ? null : (data.empirical_coverage * 100).toFixed(1);
  const hasInterval = Boolean(data.interval_days && data.interval_days.length === 2);

  return (
    <PanelCard
      eyebrow="Prognostic estimate"
      title={data.label}
      takeaway="A survival interval from the conformal model. This is not a drug set."
      display={hasInterval ? `${daysLabel(data.interval_days![0])} – ${daysLabel(data.interval_days![1])}` : "—"}
      displayCaption={hasInterval ? `${coveragePct}% requested coverage` : "interval unavailable"}
      bare
      actions={<GlossaryAffordance panel="prognostic_estimate" />}
      footnote={data.domain_note}
    >
      <dl className="grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-4">
        <div>
          <dt className="eyebrow">Requested</dt>
          <dd className="mt-0.5 font-mono text-[13px] tabular-nums">{coveragePct}%</dd>
        </div>
        <div>
          <dt className="eyebrow">Empirical</dt>
          <dd className="mt-0.5 font-mono text-[13px] tabular-nums">{empiricalPct != null ? `${empiricalPct}%` : "—"}</dd>
        </div>
        <div>
          <dt className="eyebrow">n</dt>
          <dd className="mt-0.5 font-mono text-[13px] tabular-nums">{data.n ?? "—"}</dd>
        </div>
        <div>
          <dt className="eyebrow">Method</dt>
          <dd className="mt-0.5 font-mono text-[13px]">{data.method}</dd>
        </div>
      </dl>
      {data.point_days != null && (
        <p className="mt-3 text-[11.5px] text-[var(--text-secondary)]">
          Point estimate {daysLabel(data.point_days)}.
        </p>
      )}
    </PanelCard>
  );
}
