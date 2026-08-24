"use client";

import { clusterColor } from "@/lib/clusterPalette";
import type { V3KmBlock } from "@/lib/v3-types";

export function SurvivalPanel({
  block,
  k,
  exploratory,
  a2Failed,
  a2P,
  framing,
  endpoint,
  onEndpoint,
  selectedCluster,
}: {
  block: V3KmBlock | undefined;
  k: number;
  exploratory: boolean;
  a2Failed: boolean;
  a2P?: number | null;
  framing: string;
  endpoint: "os" | "pfi";
  onEndpoint: (value: "os" | "pfi") => void;
  selectedCluster: number | null;
}) {
  const curves = Object.entries(block?.curves ?? {});
  const maxT = Math.max(1, ...curves.flatMap(([, c]) => c.time));
  const times = [0, maxT / 2, maxT];

  return (
    <section className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-4">
      <header className="flex items-start justify-between gap-2">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-400">Survival</p>
          <h2 className="mt-1 text-base font-semibold">Kaplan–Meier by subgroup</h2>
        </div>
        <div className="flex items-center gap-2">
          {exploratory && (
            <span data-testid="exploratory-badge-survival" className="rounded-full bg-amber-100 px-2 py-0.5 font-mono text-[11px] font-semibold text-amber-800">
              exploratory
            </span>
          )}
          <div className="flex rounded-lg border border-slate-200 text-[11px]">
            {(["os", "pfi"] as const).map((ep) => (
              <button
                key={ep}
                type="button"
                onClick={() => onEndpoint(ep)}
                className={`px-2 py-1 uppercase ${endpoint === ep ? "bg-slate-900 text-white" : "text-slate-600"}`}
              >
                {ep}
              </button>
            ))}
          </div>
        </div>
      </header>
      {a2Failed && (
        <p className="mt-2 text-sm text-slate-700" data-testid="descriptive-framing">
          These subgroups differ molecularly but did not separate survival
          {a2P != null ? ` (p = ${a2P.toPrecision(2)})` : ""}. Presented as descriptive.
        </p>
      )}
      {!exploratory && block?.p_value != null && !a2Failed && (
        <p className="mt-2 font-mono text-sm tabular-nums text-slate-800">
          log-rank p = {block.p_value.toExponential(2)} · n={block.n} · events={block.n_events}
        </p>
      )}
      {exploratory && (
        <p className="mt-2 text-sm text-amber-800">p-value withheld — this split was not pre-registered.</p>
      )}
      <svg viewBox="0 0 400 220" className="mt-2 w-full" role="img" aria-label="Kaplan-Meier curves">
        {curves.map(([cl, curve], idx) => {
          const color = clusterColor(Number(cl), k);
          const faded = selectedCluster != null && Number(cl) !== selectedCluster;
          const pts = curve.time.map((t, i) => `${20 + (t / maxT) * 340},${20 + (1 - curve.survival[i]) * 160}`).join(" ");
          const last = curve.time.length ? curve.time[curve.time.length - 1] : 0;
          const lastY = curve.survival.length ? curve.survival[curve.survival.length - 1] : 1;
          return (
            <g key={cl} opacity={faded ? 0.25 : 1} className="transition-opacity duration-200">
              <polyline
                fill="none"
                stroke={color}
                strokeWidth="2"
                strokeDasharray={idx % 2 === 1 ? "6 4" : undefined}
                points={pts}
                className="transition-[points] duration-[400ms] ease-out"
              />
              <text x={20 + (last / maxT) * 340} y={16 + (1 - lastY) * 160} fontSize="9" fill={color} className="font-mono">
                {cl}
              </text>
            </g>
          );
        })}
      </svg>
      <table className="mt-2 w-full font-mono text-[10px] text-slate-500">
        <thead>
          <tr>
            <th className="text-left">at risk</th>
            {times.map((t) => (
              <th key={t} className="text-right tabular-nums">
                {t.toFixed(0)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {curves.map(([cl, curve]) => (
            <tr key={cl}>
              <td>c{cl}</td>
              {times.map((t) => {
                let n = curve.at_risk[0] ?? 0;
                curve.time.forEach((ti, i) => {
                  if (ti <= t) n = curve.at_risk[i];
                });
                return (
                  <td key={t} className="text-right tabular-nums">
                    {n}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-2 text-[11px] text-slate-400">Framing: {framing}. Solid vs dashed is a second channel besides colour.</p>
    </section>
  );
}
