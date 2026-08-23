"use client";

import type { PathwayCandidates } from "@/lib/types";
import { GlossaryAffordance } from "@/components/GlossaryAffordance";

export function PredictionSetPanel({
  data,
  methylationNote,
}: {
  data: PathwayCandidates;
  methylationNote?: string | null;
}) {
  const total = (data.n_scored ?? data.set_members.length + data.excluded_count) || data.set_members.length;

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <header className="flex items-start justify-between gap-3">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-400">
            5 · Pathway-matched candidates
          </p>
          <h2 className="mt-1 text-lg font-semibold text-slate-950">
            {data.set_members.length} of {total} agents
          </h2>
          <p className="mt-2 text-sm font-medium text-slate-800">
            Agents whose target pathway shows elevated activity in this sample.
          </p>
          <p className="mt-1 text-sm text-slate-600">Order carries no meaning — list is alphabetical.</p>
        </div>
        <GlossaryAffordance panel="pathway_candidates" />
      </header>
      {methylationNote && <p className="mt-3 text-sm text-slate-600">{methylationNote}</p>}
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
        Mechanistic filter ({data.threshold_rule}). No outcome validation. {data.excluded_count} agents
        below the activity threshold.
      </p>
    </section>
  );
}
