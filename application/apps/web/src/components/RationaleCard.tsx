"use client";

import type { GroundedRationale, RationaleClaim } from "@/lib/types";

function ClaimList({ title, claims }: { title: string; claims: RationaleClaim[] }) {
  if (!claims.length) return null;
  return (
    <div>
      <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-400">{title}</p>
      <ul className="mt-2 space-y-2">
        {claims.map((claim) => (
          <li key={claim.text} className="rounded-lg bg-slate-50 px-3 py-2 text-sm text-slate-700">
            <p>{claim.text}</p>
            <div className="mt-1.5 flex flex-wrap gap-1.5">
              {claim.evidence_keys.map((key) => (
                <span key={key} className="rounded-full bg-white px-2 py-0.5 font-mono text-[10px] text-slate-500">
                  {key}
                </span>
              ))}
              {claim.citation_ids.map((id) => (
                <span
                  key={id}
                  className="rounded-full border border-indigo-200 bg-indigo-50 px-2 py-0.5 text-[10px] font-semibold text-indigo-700"
                >
                  {id}
                </span>
              ))}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function RationaleCard({ rationale }: { rationale: GroundedRationale | null }) {
  if (!rationale) return null;
  const sourceLabel = rationale.fallback_used
    ? "Deterministic evidence summary"
    : `${rationale.provider || "LLM"} · ${rationale.model || "model"}`;
  return (
    <section className="space-y-4 rounded-2xl border border-indigo-100 bg-white p-5 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-indigo-600">Evidence rationale</p>
          <h3 className="mt-1 text-lg font-semibold text-slate-950">What the validated evidence supports</h3>
        </div>
        <span className="rounded-full bg-slate-100 px-2.5 py-1 text-[10px] font-semibold text-slate-600">
          {sourceLabel}
        </span>
      </div>
      <p className="text-sm leading-6 text-slate-700">{rationale.summary}</p>
      <ClaimList title="Supporting claims" claims={rationale.supporting_claims} />
      <ClaimList title="Counter-evidence / limitations" claims={rationale.counter_claims} />
      <ClaimList title="Uncertainty" claims={rationale.uncertainty} />
    </section>
  );
}
