"use client";

import { useEffect, useMemo } from "react";
import type { V3CellLine, V3PatientPayload } from "@/lib/v3-types";
import { PanelCard } from "@/components/PanelCard";
import { ChartAxes, chartPad } from "@/components/ChartAxes";
import { clusterColor } from "@/lib/clusterPalette";

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
  takeaway,
}: {
  line: V3CellLine | null;
  reversal: V3PatientPayload["reversal_candidates"];
  a4Failed: boolean;
  concentration: number;
  onConcentration: (nm: number) => void;
  takeaway?: string;
}) {
  const curves = line?.curves ?? [];
  const cmax = useMemo(() => {
    const values = curves.map((c) => c.cmax_nm).filter((v): v is number => v != null && v > 0);
    return values[0] ?? null;
  }, [curves]);

  useEffect(() => {
    if (cmax != null && concentration === 250) onConcentration(cmax);
    // default once to Cmax when the panel first sees a real Cmax
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cmax]);

  const decades = [1, 10, 100, 1000, 10000, 100000];
  const W = 420;
  const H = 240;
  const geom = chartPad(W, H, { l: 52, r: 96, t: 16, b: 36 });
  const minLog = 0;
  const maxLog = 5;
  const xOf = (nm: number) => geom.pad.l + ((Math.log10(Math.max(nm, 1)) - minLog) / (maxLog - minLog)) * geom.innerW;
  const yOf = (v: number) => geom.y(v);

  return (
    <PanelCard
      id="retrieval"
      eyebrow="Measured response"
      title="Measured GDSC dose-response"
      takeaway={takeaway}
      display={curves.length || undefined}
      displayCaption={curves.length ? "curves" : undefined}
      footnote="Not a simulation. Source: GDSC2 fitted Hill curves. Compounds are shown as evidence, not as recommendations."
    >
      {a4Failed && (
        <p className="mb-2 text-sm text-amber-800">
          Cluster-versus-normal reversal is omitted because the normal comparison did not recover known biology.
        </p>
      )}
      {reversal && !a4Failed && (
        <div className="mb-3">
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
          <ChartAxes
            width={W}
            height={H}
            pad={geom.pad}
            xLabel="Concentration (nM)"
            yLabel="Cell viability (%)"
            xTicks={decades.map((d) => ({ v: d, x: xOf(d), label: String(d) }))}
            yTicks={[0, 0.25, 0.5, 0.75, 1].map((v) => ({ v, y: yOf(v), label: String(v * 100) }))}
          >
            {cmax != null && (
              <>
                <rect x={geom.pad.l} y={geom.pad.t} width={Math.max(0, xOf(cmax) - geom.pad.l)} height={geom.innerH} fill="#14B8A6" opacity="0.08" />
                <text x={xOf(cmax) - 4} y={geom.pad.t + 12} textAnchor="end" fontSize="10" className="fill-teal-800 font-mono">
                  Plasma Cmax {cmax} nM
                </text>
              </>
            )}
            {curves.map((curve, i) => {
              const pts = curve.concentration_nm.map((c, idx) => `${xOf(c)},${yOf(curve.viability[idx])}`).join(" ");
              const lastX = xOf(curve.concentration_nm[curve.concentration_nm.length - 1] ?? 1);
              const lastY = yOf(curve.viability[curve.viability.length - 1] ?? 0.5);
              const ic50x = xOf(curve.ic50_nm);
              const ic50y = yOf(0.5);
              return (
                <g key={curve.drug}>
                  <polyline fill="none" stroke={clusterColor(i, 8)} strokeWidth="1.8" strokeDasharray={i ? "6 3" : undefined} points={pts} />
                  <line x1={ic50x} x2={ic50x} y1={ic50y - 4} y2={ic50y + 4} stroke={clusterColor(i, 8)} />
                  <text x={ic50x + 4} y={ic50y - 6} fontSize="10" className="fill-[var(--text-secondary)] font-mono">
                    IC50 {curve.ic50_nm.toFixed(0)} nM
                  </text>
                  <text x={lastX + 4} y={lastY} fontSize="11" fill={clusterColor(i, 8)} className="font-mono">
                    {curve.canonical || curve.drug}
                  </text>
                </g>
              );
            })}
            <line x1={xOf(concentration)} x2={xOf(concentration)} y1={geom.pad.t} y2={geom.pad.t + geom.innerH} stroke="#0f172a" strokeDasharray="3 2" />
          </ChartAxes>
          <label className="mt-2 block text-xs text-slate-500">
            Concentration (nM)
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
            At {concentration} nM — {curves.map((c) => `${c.canonical || c.drug} ${(viabilityAt(c, concentration) * 100).toFixed(0)}% viability (${c.source}, ${line.name})`).join("; ")}.
          </p>
        </>
      )}
    </PanelCard>
  );
}
