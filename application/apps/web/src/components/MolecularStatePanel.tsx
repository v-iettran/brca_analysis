"use client";

import type { MolecularState } from "@/lib/types";
import { GlossaryAffordance } from "@/components/GlossaryAffordance";

export function MolecularStatePanel({ data }: { data: MolecularState }) {
  const maxAbs = Math.max(...data.pathways.map((row) => Math.abs(row.activity)), 1e-6);

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <header className="flex items-start justify-between gap-3">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-400">3 · Molecular state</p>
          <h2 className="mt-1 text-lg font-semibold text-slate-950">Pathway and TF activity</h2>
          <p className="mt-1 text-xs text-slate-500">Bars, not a network — there are no validated edges.</p>
        </div>
        <GlossaryAffordance panel="molecular_state" />
      </header>
      <div className="mt-4 space-y-1.5">
        {data.pathways.map((row) => {
          const width = (Math.abs(row.activity) / maxAbs) * 50;
          const positive = row.activity >= 0;
          return (
            <div key={row.name} className="grid grid-cols-[7rem_1fr_3rem] items-center gap-2 text-xs">
              <span className="truncate text-right text-slate-600">{row.name}</span>
              <div className="relative h-3 rounded bg-slate-100">
                <div className="absolute bottom-0 top-0 left-1/2 w-px bg-slate-300" />
                <div
                  className={`absolute top-0 h-3 ${positive ? "left-1/2 bg-indigo-500" : "right-1/2 bg-rose-400"}`}
                  style={{ width: `${width}%` }}
                />
              </div>
              <span className="font-mono text-slate-500">{row.activity.toFixed(2)}</span>
            </div>
          );
        })}
      </div>
      <h3 className="mt-6 text-sm font-semibold text-slate-900">Top transcription factors</h3>
      <ul className="mt-2 divide-y divide-slate-100">
        {data.transcription_factors.map((tf) => (
          <li key={tf.name} className="flex items-center justify-between py-1.5 text-sm">
            <span className={tf.reliability === "low" ? "text-slate-400" : "text-slate-800"}>
              {tf.name}
              {tf.reliability === "low" && (
                <span className="ml-2 text-[10px] uppercase tracking-wide text-slate-400" title={tf.reliability_reason ?? ""}>
                  low reliability
                </span>
              )}
            </span>
            <span className="font-mono text-xs text-slate-500">{tf.activity.toFixed(2)}</span>
          </li>
        ))}
      </ul>
      {data.discrepancies.length > 0 && (
        <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-950">
          {data.discrepancies.map((item) => (
            <p key={`${item.field}-${item.clinical}`}>
              Clinical {item.field} is {item.clinical}; inferred {item.inferred}.
            </p>
          ))}
        </div>
      )}
    </section>
  );
}
