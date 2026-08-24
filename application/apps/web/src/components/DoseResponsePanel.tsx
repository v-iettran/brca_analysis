"use client";

import type { V3CellLine, V3PatientPayload } from "@/lib/v3-types";

function viabilityAt(curve: NonNullable<V3CellLine["curves"]>[number], conc: number): number {
  const xs = curve.concentration_nm;
  const ys = curve.viability;
  if (!xs.length) return NaN;
  if (conc <= xs[0]) return ys[0];
  if (conc >= xs[xs.length - 1]) return ys[ys.length - 1];
  for (let i = 1; i < xs.length; i++) {
    if (conc <= xs[i]) {
      const t = (Math.log(conc) - Math.log(xs[i - 1])) / (Math.log(xs[i]) - Math.log(xs[i - 1]) || 1);
      return ys[i - 1] + t * (ys[i] - ys[i - 1]);
    }
  }
  return ys[ys.length - 1];
}

export function DoseResponsePanel({
  line,
  reversal,
  a4Failed,
  concentration,
  onConcentration,
}: {
  line: V3CellLine | null;
  reversal: V3PatientPayload["reversal_candidates"];
  a4Failed: boolean;
  concentration: number;
  onConcentration: (nm: number) => void;
}) {
  const curves = line?.curves ?? [];
  const maxLog = 5;
  const xOf = (nm: number) => ((Math.log10(Math.max(nm, 1)) ) / maxLog) * 340 + 30;

  return (
    <section className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-4">
      <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-400">Measured response</p>
      <h2 className="mt-1 text-base font-semibold">Measured GDSC dose-response. Not a simulation.</h2>
      {a4Failed && <p className="mt-2 text-sm text-amber-800">Cluster-versus-normal reversal is omitted because the normal comparison did not recover known biology.</p>}
      {reversal && !a4Failed && (
        <div className="mt-3">
          <p className="text-xs font-semibold text-slate-500">Reversal candidates — order carries no meaning</p>
          <p className="font-mono text-[11px] text-slate-600">
            {reversal.threshold_rule} · validated={String(reversal.validated)} · {reversal.source}
          </p>
          <ul className="mt-1 flex flex-wrap gap-1">
            {[...reversal.members].sort((a, b) => a.drug.localeCompare(b.drug)).map((row) => (
              <li key={row.drug} className="rounded-full border border-slate-200 px-2 py-0.5 font-mono text-[11px]">
                {row.drug}
              </li>
            ))}
          </ul>
        </div>
      )}
      {line && curves.length > 0 && (
        <>
          <svg viewBox="0 0 400 220" className="mt-3 w-full" role="img" aria-label="Dose response curves">
            {curves.map((curve, i) => {
              const pts = curve.concentration_nm.map((c, idx) => `${xOf(c)},${20 + (1 - curve.viability[idx]) * 160}`).join(" ");
              return (
                <g key={curve.drug}>
                  {curve.cmax_nm != null && (
                    <rect x={30} y={20} width={xOf(curve.cmax_nm) - 30} height={160} fill="#14b8a6" opacity="0.06" />
                  )}
                  <polyline fill="none" stroke={i % 2 ? "#7c3aed" : "#0f766e"} strokeWidth="1.6" points={pts} />
                </g>
              );
            })}
            <line x1={xOf(concentration)} x2={xOf(concentration)} y1="20" y2="180" stroke="#0f172a" strokeDasharray="3 2" />
          </svg>
          <label className="mt-2 block text-xs text-slate-500">
            Concentration
            <input
              type="range"
              min={1}
              max={100000}
              value={concentration}
              onChange={(e) => onConcentration(Number(e.target.value))}
              className="w-full accent-teal-700"
            />
          </label>
          <p className="mt-1 font-mono text-sm tabular-nums" data-testid="dose-readout">
            At {concentration} nM — {curves.map((c) => `${c.drug} ${(viabilityAt(c, concentration) * 100).toFixed(0)}% viability`).join(", ")}, measured in {line.name}.
          </p>
        </>
      )}
    </section>
  );
}
