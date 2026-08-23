"use client";

import type { PredictorCombination } from "@/lib/types";

function score(value?: number | null) {
  return value == null || !Number.isFinite(value) ? "n/a" : value.toFixed(3);
}

export function PredictorCombinationPanel({
  combinations,
}: {
  combinations: PredictorCombination[];
}) {
  return (
    <section className="rounded-2xl border border-amber-200 bg-amber-50/40 p-5 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-amber-700">
            Parallel clinical-comparator lane
          </p>
          <h3 className="mt-1 text-lg font-semibold text-slate-950">
            Predictor-supported ALMANAC combinations
          </h3>
          <p className="mt-1 max-w-3xl text-xs leading-5 text-slate-600">
            These pairs are scored independently of the List 1 ∩ List 2 cutoff. Priority combines
            component-drug context (55%), aligned ALMANAC support (35%), and pair Q4 support (10%).
            They are preclinical comparators—not additional patient-specific nominations.
          </p>
        </div>
        <span className="rounded-full border border-amber-200 bg-white px-2.5 py-1 text-[10px] font-semibold text-amber-800">
          {combinations.length} eligible pairs
        </span>
      </div>

      <div className="mt-4 grid gap-3 lg:grid-cols-2">
        {combinations.map((row) => (
          <article key={row.combination} className="rounded-xl border border-amber-100 bg-white p-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="font-mono text-[10px] text-slate-400">Predictor rank #{row.rank}</p>
                <h4 className="mt-0.5 text-sm font-semibold capitalize text-slate-900">
                  {row.combination}
                </h4>
              </div>
              <span className="rounded-md bg-amber-100 px-2 py-1 text-xs font-bold text-amber-900">
                {score(row.integrated_combination_priority)}
              </span>
            </div>
            <div className="mt-3 grid grid-cols-3 gap-2 text-center text-[10px]">
              <div className="rounded-lg bg-slate-50 p-2">
                <p className="text-slate-400">Components · 55%</p>
                <p className="mt-1 font-semibold text-slate-800">{score(row.component_drug_priority)}</p>
              </div>
              <div className="rounded-lg bg-slate-50 p-2">
                <p className="text-slate-400">ALMANAC · 35%</p>
                <p className="mt-1 font-semibold text-slate-800">{score(row.aligned_pair_support)}</p>
              </div>
              <div className="rounded-lg bg-slate-50 p-2">
                <p className="text-slate-400">Pair Q4 · 10%</p>
                <p className="mt-1 font-semibold text-slate-800">{score(row.pair_q4_support)}</p>
              </div>
            </div>
            <p className="mt-3 text-[11px] text-slate-500">
              {row.aligned_cell_lines} aligned breast cell lines
              {row.cell_line_alignment_confidence
                ? ` · ${row.cell_line_alignment_confidence.replaceAll("_", " ")}`
                : ""}
            </p>
          </article>
        ))}
      </div>

      {combinations.length === 0 && (
        <p className="mt-4 rounded-xl border border-dashed border-amber-200 bg-white p-4 text-xs text-slate-500">
          Predictor combination context is unavailable for this profile.
        </p>
      )}
    </section>
  );
}
