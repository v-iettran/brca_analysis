"use client";

import type { PredictionSet } from "@/lib/types";
import { GlossaryAffordance } from "@/components/GlossaryAffordance";

export function PredictionSetPanel({
  data,
  methylationNote,
}: {
  data: PredictionSet;
  methylationNote?: string | null;
}) {
  const total = (data.n_scored ?? data.set_members.length + data.excluded_count) || data.set_members.length;

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <header className="flex items-start justify-between gap-3">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-400">4 · Prediction set</p>
          <h2 className="mt-1 text-lg font-semibold text-slate-950">
            {data.set_members.length} of {total} agents
          </h2>
          <p className="mt-2 text-sm font-medium text-slate-800">
            Set, not a ranking — order carries no meaning.
          </p>
        </div>
        <GlossaryAffordance panel="prediction_set" />
      </header>
      {data.set_width_note && <p className="mt-3 text-sm text-amber-800">{data.set_width_note}</p>}
      {methylationNote && <p className="mt-1 text-sm text-slate-600">{methylationNote}</p>}
      <ul className="mt-4 flex flex-wrap gap-2">
        {data.set_members.map((member) => (
          <li
            key={member.drug}
            className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-sm text-slate-800"
          >
            {member.drug}
            <span className="ml-2 text-[10px] font-semibold uppercase tracking-wide text-slate-400">
              {member.evidence_tier}
            </span>
          </li>
        ))}
      </ul>
      <p className="mt-4 text-xs text-slate-500">
        Coverage level {(data.coverage_level * 100).toFixed(0)}%. {data.excluded_count} agents outside the set.
      </p>
    </section>
  );
}
