"use client";

import { clusterColor, clusterStroke } from "@/lib/clusterPalette";
import { formatP, subgroupLabel } from "@/lib/v3-format";
import type { V3KmBlock } from "@/lib/v3-types";
import { PanelCard } from "@/components/PanelCard";
import { ChartAxes, chartPad } from "@/components/ChartAxes";

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
  takeaway,
  nCohort,
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
  takeaway?: string;
  nCohort?: number;
}) {
  const curves = Object.entries(block?.curves ?? {}).sort((a, b) => Number(a[0]) - Number(b[0]));
  const maxT = Math.max(24, ...curves.flatMap(([, c]) => c.time), 0);
  const tickStep = 24;
  const ticks: number[] = [];
  for (let t = 0; t <= maxT + 0.01; t += tickStep) ticks.push(t);
  if (ticks[ticks.length - 1] < maxT) ticks.push(Math.ceil(maxT / tickStep) * tickStep);
  const W = 420;
  const H = 240;
  const geom = chartPad(W, H, { l: 52, r: 88, t: 12, b: 36 });
  const x = (t: number) => geom.pad.l + (t / (ticks[ticks.length - 1] || 1)) * geom.innerW;
  const y = (s: number) => geom.y(s);
  const yLabel = endpoint === "os" ? "Overall survival probability" : "Progression-free probability";
  const pShown = !exploratory && !a2Failed && block?.p_value != null;
  const header = exploratory
    ? `exploratory · n = ${block?.n ?? nCohort ?? "—"}`
    : `log-rank p = ${formatP(block?.p_value ?? a2P)} · n = ${block?.n ?? "—"} · events = ${block?.n_events ?? "—"}`;

  function atRisk(curve: (typeof curves)[number][1], t: number) {
    let n = curve.at_risk[0] ?? 0;
    curve.time.forEach((ti, i) => {
      if (ti <= t) n = curve.at_risk[i];
    });
    return n;
  }

  return (
    <PanelCard
      id="survival"
      eyebrow="Survival"
      title="Kaplan–Meier by subgroup"
      takeaway={takeaway}
      display={exploratory ? "—" : pShown ? formatP(block?.p_value) : framing === "descriptive" || a2Failed ? formatP(a2P) : "—"}
      displayCaption={exploratory ? "p withheld" : "log-rank p"}
      footnote={`Source: TCGA-BRCA clinical ${endpoint.toUpperCase()}. Time unit: months since diagnosis. Framing: ${framing}.`}
      actions={
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
      }
    >
      {a2Failed && (
        <p className="mb-2 text-sm text-slate-700" data-testid="descriptive-framing">
          These subgroups differ molecularly but did not separate survival
          {a2P != null ? ` (p = ${formatP(a2P)})` : ""}. Presented as descriptive.
        </p>
      )}
      <p className="mb-2 font-mono text-sm tabular-nums text-slate-800">{header}</p>
      {exploratory && <p className="mb-2 text-sm text-amber-800">p-value withheld — this split was not pre-registered.</p>}
      <ChartAxes
        width={W}
        height={H}
        pad={geom.pad}
        xLabel="Months since diagnosis"
        yLabel={yLabel}
        xTicks={ticks.map((t) => ({ v: t, x: x(t), label: String(t) }))}
        yTicks={[0, 0.25, 0.5, 0.75, 1].map((s) => ({ v: s, y: y(s), label: s.toFixed(2) }))}
      >
        {curves.map(([cl, curve], idx) => {
          const color = clusterColor(Number(cl), k);
          const faded = selectedCluster != null && Number(cl) !== selectedCluster;
          const dash = clusterStroke(idx);
          const times = curve.time[0] === 0 ? curve.time : [0, ...curve.time];
          const surv = curve.time[0] === 0 ? curve.survival : [1, ...curve.survival];
          const lower = curve.time[0] === 0 ? curve.lower : [1, ...curve.lower];
          const upper = curve.time[0] === 0 ? curve.upper : [1, ...curve.upper];
          const band = [
            ...times.map((t, i) => `${x(t)},${y(upper[i] ?? surv[i])}`),
            ...[...times].reverse().map((t, i, arr) => `${x(t)},${y(lower[arr.length - 1 - i] ?? surv[arr.length - 1 - i])}`),
          ].join(" ");
          const step: string[] = [];
          times.forEach((t, i) => {
            const s = surv[i];
            if (i === 0) step.push(`${x(t)},${y(s)}`);
            else {
              step.push(`${x(t)},${y(surv[i - 1])}`);
              step.push(`${x(t)},${y(s)}`);
            }
          });
          const lastT = times[times.length - 1] ?? 0;
          const lastS = surv[surv.length - 1] ?? 1;
          return (
            <g key={cl} opacity={faded ? 0.25 : 1} className="transition-opacity duration-200">
              <polygon fill={color} opacity="0.12" points={band} />
              <polyline fill="none" stroke={color} strokeWidth="2" strokeDasharray={dash || undefined} points={step.join(" ")} />
              <text x={x(lastT) + 4} y={y(lastS)} fontSize="11" fill={color} className="font-mono">
                {subgroupLabel(Number(cl))} (n={curve.n ?? curve.at_risk[0] ?? "—"})
              </text>
            </g>
          );
        })}
      </ChartAxes>
      <table className="mt-2 w-full font-mono text-[10px] text-slate-600">
        <thead>
          <tr>
            <th className="text-left">At risk</th>
            {ticks.map((t) => (
              <th key={t} className="text-right tabular-nums">
                {t}
              </th>
            ))}
          </tr>
          <tr>
            <th className="text-left font-normal text-[var(--text-muted)]">Months</th>
            {ticks.map((t) => (
              <th key={`h-${t}`} className="text-right font-normal text-[var(--text-muted)]">
                {t}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {curves.map(([cl, curve]) => (
            <tr key={cl}>
              <td>{subgroupLabel(Number(cl))}</td>
              {ticks.map((t) => (
                <td key={t} className="text-right tabular-nums">
                  {atRisk(curve, t)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <table className="mt-3 text-xs text-[var(--text-secondary)]">
        <thead>
          <tr>
            <th className="text-left font-medium">Subgroup</th>
            <th className="text-right font-medium">Median OS (months)</th>
          </tr>
        </thead>
        <tbody>
          {curves.map(([cl, curve]) => (
            <tr key={cl}>
              <td>{subgroupLabel(Number(cl))}</td>
              <td className="text-right font-mono tabular-nums">{curve.median != null ? curve.median.toFixed(1) : "not reached"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </PanelCard>
  );
}
