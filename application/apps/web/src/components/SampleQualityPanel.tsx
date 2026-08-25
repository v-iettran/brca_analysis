"use client";

import { useState } from "react";
import type { SampleQuality } from "@/lib/types";
import { GlossaryAffordance } from "@/components/GlossaryAffordance";

const COLORS: Record<string, string> = {
  malignant: "bg-indigo-600",
  immune: "bg-cyan-500",
  stroma: "bg-slate-400",
};

export function SampleQualityPanel({ data, takeaway }: { data: SampleQuality; takeaway?: string }) {
  const [open, setOpen] = useState(false);
  const verdictColor =
    data.verdict === "sufficient"
      ? "bg-emerald-50 text-emerald-800"
      : data.verdict === "marginal"
        ? "bg-amber-50 text-amber-900"
        : "bg-rose-50 text-rose-800";

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <header className="flex items-start justify-between gap-3">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-400">Sample quality</p>
          <h2 className="mt-1 text-lg font-semibold text-slate-950">Tumour composition</h2>
          {takeaway && <p className="takeaway mt-1">{takeaway}</p>}
        </div>
        <GlossaryAffordance panel="sample_quality" />
      </header>
      <div className="mt-4 flex flex-wrap items-end gap-4">
        <p className="text-4xl font-semibold tabular-nums text-slate-950">
          {(data.tumour_fraction * 100).toFixed(0)}
          <span className="ml-1 text-base font-medium text-slate-400">% tumour</span>
        </p>
        <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${verdictColor}`}>{data.verdict}</span>
      </div>
      {data.verdict_reason && <p className="mt-2 text-sm text-slate-600">{data.verdict_reason}</p>}
      <div className="mt-4 flex h-3 overflow-hidden rounded-full bg-slate-100">
        {data.composition.map((part) => (
          <div
            key={part.cell_type}
            className={COLORS[part.cell_type] ?? "bg-slate-300"}
            style={{ width: `${Math.max(part.fraction * 100, 0)}%` }}
            title={`${part.cell_type} ${(part.fraction * 100).toFixed(0)}%`}
          />
        ))}
      </div>
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="mt-3 text-xs font-semibold text-indigo-700"
      >
        {open ? "Hide cell-type breakdown" : "Show cell-type breakdown"}
      </button>
      {open && (
        <ul className="mt-3 space-y-1 text-sm text-slate-600">
          {data.composition.map((part) => (
            <li key={part.cell_type} className="flex justify-between gap-4">
              <span className="capitalize">{part.cell_type}</span>
              <span className="font-mono text-xs">
                {(part.fraction * 100).toFixed(1)}%
                {part.ci?.length === 2
                  ? ` (${(part.ci[0] * 100).toFixed(0)}–${(part.ci[1] * 100).toFixed(0)})`
                  : ""}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
