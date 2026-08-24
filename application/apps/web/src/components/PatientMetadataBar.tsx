"use client";

import { GlossaryAffordance } from "@/components/GlossaryAffordance";

export function PatientMetadataBar({
  patientId,
  modalities,
  pam50,
  tumourFraction,
  verdict,
  timestamp,
  state,
  encoder,
}: {
  patientId: string;
  modalities: string[];
  pam50?: string | null;
  tumourFraction: number;
  verdict: string;
  timestamp?: string;
  state: number;
  encoder?: string;
}) {
  const all = ["rna", "cna", "methylation"];
  const stateClass =
    state === 1 ? "bg-teal-50 text-teal-800" : state === 2 ? "bg-amber-50 text-amber-900 border border-amber-300" : "bg-rose-50 text-rose-800";
  const verdictDot = verdict === "sufficient" ? "bg-teal-600" : verdict === "marginal" ? "bg-amber-500" : "bg-rose-600";

  return (
    <header className="sticky top-0 z-20 flex flex-wrap items-center gap-3 border-b border-[var(--border)] bg-[var(--surface)] px-4 py-3">
      <p className="font-mono text-sm font-medium text-[var(--text-primary)]">{patientId}</p>
      <div className="flex gap-1">
        {all.map((mod) => {
          const present = modalities.includes(mod);
          return (
            <span
              key={mod}
              className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${present ? "bg-teal-50 text-teal-800" : "border border-slate-300 bg-transparent text-slate-400"}`}
            >
              {mod}
            </span>
          );
        })}
      </div>
      {pam50 && <span className="rounded-full bg-violet-50 px-2 py-0.5 text-[11px] font-medium text-violet-800">{pam50}</span>}
      <span className="inline-flex items-center gap-1.5 text-sm text-slate-600">
        <span className={`h-2 w-2 rounded-full ${verdictDot}`} />
        <span className="font-mono tabular-nums">{(tumourFraction * 100).toFixed(0)}%</span> tumour
      </span>
      {timestamp && <span className="font-mono text-[11px] text-slate-400">{timestamp.slice(0, 10)}</span>}
      <GlossaryAffordance panel="sample_quality" encoder={encoder} />
      <span className={`ml-auto rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${stateClass}`}>state {state}</span>
    </header>
  );
}
