"use client";

import { clusterColor, clusterStroke } from "@/lib/clusterPalette";
import { formatP, subgroupLabel } from "@/lib/v3-format";
import type { V3KmBlock } from "@/lib/v3-types";
import { PanelCard } from "@/components/PanelCard";
import { SubgroupMark } from "@/components/SubgroupMark";
import { ChartAxes, chartPad } from "@/components/ChartAxes";

/**
 * Kaplan-Meier to the standard reporting set: y from 0 to 1, x in months, an
 * at-risk table aligned to the x ticks, confidence bands, and stroke style as a
 * second channel beyond colour.
 *
 * Series identity lives in the legend rather than in end-of-line labels. Four
 * curves that converge at the right edge stack their labels on top of one
 * another; the legend also gives each subgroup a click target, which an SVG
 * text node does not.
 *
 * The p-value renders only at the pre-registered configuration. That is not a
 * display preference: showing p across every k is what would make the
 * pre-registered p meaningless.
 */
export function SurvivalPanel({
  block,
  k,
  exploratory,
  a2Failed,
  a2P,
  framing,
  endpoint,
  onEndpoint,
  selectedClusters,
  onToggleCluster,
  takeaway,
  nCohort,
  sensitivity,
  preregisteredK,
  sweepApplies = true,
}: {
  block: V3KmBlock | undefined;
  k: number;
  exploratory: boolean;
  a2Failed: boolean;
  a2P?: number | null;
  framing: string;
  endpoint: "os" | "pfi";
  onEndpoint: (value: "os" | "pfi") => void;
  selectedClusters: number[];
  onToggleCluster: (cluster: number) => void;
  takeaway?: string;
  nCohort?: number;
  sensitivity?: Array<{ k: number; p_value: number; q_value?: number }>;
  preregisteredK?: number | null;
  sweepApplies?: boolean;
}) {
  const curves = Object.entries(block?.curves ?? {}).sort((a, b) => Number(a[0]) - Number(b[0]));
  const maxT = Math.max(24, ...curves.flatMap(([, c]) => c.time), 0);
  const ticks: number[] = [];
  for (let t = 0; t <= maxT + 0.01; t += 24) ticks.push(t);
  if (ticks[ticks.length - 1] < maxT) ticks.push(Math.ceil(maxT / 24) * 24);

  const W = 760;
  const H = 300;
  const geom = chartPad(W, H, { l: 56, r: 24, t: 14, b: 38 });
  const span = ticks[ticks.length - 1] || 1;
  const x = (t: number) => geom.pad.l + (t / span) * geom.innerW;
  const y = (s: number) => geom.y(s);

  const yLabel = endpoint === "os" ? "Overall survival probability" : "Progression-free probability";
  const anySelected = selectedClusters.length > 0;

  // At an exploratory k the p is shown rather than withheld, at the reader's
  // request — but never on its own. The Benjamini-Hochberg q for the same k is
  // printed beside it, because seven values of k is seven tests and the raw p
  // is not interpretable without that correction.
  // The configuration payload deliberately nulls p_value away from the
  // pre-registered split, so the exploratory value comes from the sweep — which
  // was computed on the GMM/full path only, and is therefore not shown when the
  // reader has also changed method or covariance.
  const sweepRow = sweepApplies ? sensitivity?.find((row) => row.k === k) : undefined;
  const currentQ = sweepRow?.q_value ?? null;
  const exploratoryP = sweepRow?.p_value ?? null;

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
      title="Kaplan-Meier by subgroup"
      takeaway={takeaway}
      display={exploratory ? formatP(exploratoryP) : formatP(block?.p_value ?? a2P)}
      displayCaption={
        exploratory
          ? exploratoryP != null
            ? `exploratory log-rank p · BH-adjusted q ${currentQ != null ? formatP(currentQ) : "—"}`
            : "not computed for this method"
          : "log-rank p"
      }
      footnote={`Source: TCGA-BRCA clinical ${endpoint.toUpperCase()}. Time in months since diagnosis. Framing: ${framing}. Shaded bands are 95% confidence. Stroke style repeats the subgroup identity so colour is never the only channel.`}
      actions={
        <div className="flex items-center gap-2">
          {exploratory && (
            <span data-testid="exploratory-badge-survival" className="exploratory-chip">
              exploratory
            </span>
          )}
          <div className="seg">
            {(["os", "pfi"] as const).map((ep) => (
              <button
                key={ep}
                type="button"
                data-active={endpoint === ep}
                onClick={() => onEndpoint(ep)}
                className="uppercase"
              >
                {ep}
              </button>
            ))}
          </div>
        </div>
      }
    >
      {a2Failed && (
        <p className="mb-3 text-[13px] text-[var(--text-secondary)]" data-testid="descriptive-framing">
          These subgroups differ molecularly but did not separate survival
          {a2P != null ? ` (p = ${formatP(a2P)})` : ""}. Presented as descriptive.
        </p>
      )}

      <p className="mb-2 font-mono text-[12px] tabular-nums text-[var(--text-secondary)]">
        {exploratory
          ? exploratoryP != null
            ? `k = ${k} · log-rank p = ${formatP(exploratoryP)} · BH-adjusted q = ${formatP(currentQ)} · n = ${block?.n ?? nCohort ?? "—"} · events = ${block?.n_events ?? "—"}`
            : `k = ${k} · the sweep covers the GMM/full path only, so no p is available for this method · n = ${block?.n ?? nCohort ?? "—"}`
          : `log-rank p = ${formatP(block?.p_value ?? a2P)} · n = ${block?.n ?? "—"} · events = ${block?.n_events ?? "—"}`}
      </p>

      {exploratory && (
        <p className="mb-2 text-[12px] text-[var(--warning)]">
          k = {k} was not pre-registered. This p is one of seven tested across k, so it carries no
          significance claim on its own
          {currentQ != null
            ? ` — after correcting for all seven, q = ${formatP(currentQ)}${currentQ >= 0.05 ? ", which does not clear 0.05" : ""}.`
            : "."}{" "}
          The pre-registered split is k = {preregisteredK ?? "—"}.
        </p>
      )}

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
          const cluster = Number(cl);
          const color = clusterColor(cluster);
          const on = !anySelected || selectedClusters.includes(cluster);
          const startsAtZero = curve.time[0] === 0;
          const times = startsAtZero ? curve.time : [0, ...curve.time];
          const surv = startsAtZero ? curve.survival : [1, ...curve.survival];
          const lower = startsAtZero ? curve.lower : [1, ...curve.lower];
          const upper = startsAtZero ? curve.upper : [1, ...curve.upper];

          const band = [
            ...times.map((t, i) => `${x(t)},${y(upper[i] ?? surv[i])}`),
            ...[...times]
              .reverse()
              .map((t, i, arr) => `${x(t)},${y(lower[arr.length - 1 - i] ?? surv[arr.length - 1 - i])}`),
          ].join(" ");

          const step: string[] = [];
          times.forEach((t, i) => {
            if (i === 0) step.push(`${x(t)},${y(surv[i])}`);
            else {
              step.push(`${x(t)},${y(surv[i - 1])}`);
              step.push(`${x(t)},${y(surv[i])}`);
            }
          });

          return (
            <g key={cl} style={{ transition: "opacity 200ms var(--ease-out)" }} opacity={on ? 1 : 0.18}>
              {(!anySelected || on) && <polygon fill={color} opacity="0.14" points={band} />}
              <polyline
                fill="none"
                stroke={color}
                strokeWidth={anySelected && on ? 2.6 : 2}
                strokeDasharray={clusterStroke(idx) || undefined}
                points={step.join(" ")}
              />
            </g>
          );
        })}
      </ChartAxes>

      {/* Interactive legend: identity, click target, and the per-subgroup numbers
          that used to be crammed into the plot. */}
      <ul className="mt-3 grid gap-1 border-t border-[var(--line)] pt-3 sm:grid-cols-2">
        {curves.map(([cl, curve], idx) => {
          const cluster = Number(cl);
          const on = selectedClusters.includes(cluster);
          return (
            <li key={cl}>
              <button
                type="button"
                aria-pressed={on}
                onClick={() => onToggleCluster(cluster)}
                className="pressable flex w-full items-center gap-2 px-2 py-1 text-left"
                style={{ opacity: anySelected && !on ? 0.5 : 1 }}
              >
                <SubgroupMark cluster={cluster} />
                <svg width="16" height="6" aria-hidden className="shrink-0">
                  <line
                    x1="0"
                    x2="16"
                    y1="3"
                    y2="3"
                    stroke={clusterColor(cluster)}
                    strokeWidth="2"
                    strokeDasharray={clusterStroke(idx) || undefined}
                  />
                </svg>
                <span className="text-[12px] font-medium text-[var(--text-primary)]">
                  {subgroupLabel(cluster)}
                </span>
                <span className="ml-auto font-mono text-[11px] tabular-nums text-[var(--text-secondary)]">
                  n {curve.n ?? curve.at_risk[0] ?? "—"} · events {curve.n_events ?? "—"} · median{" "}
                  {curve.median != null ? `${curve.median.toFixed(0)} mo` : "not reached"}
                </span>
              </button>
            </li>
          );
        })}
      </ul>

      {/* At-risk table, columns aligned to the x-axis ticks above. */}
      <div className="mt-3 overflow-x-auto">
        <table className="w-full font-mono text-[10.5px] text-[var(--text-secondary)]">
          <caption className="sr-only">Number at risk by subgroup at each time point</caption>
          <thead>
            <tr className="text-[var(--text-muted)]">
              <th scope="col" className="py-1 text-left font-normal">
                Months
              </th>
              {ticks.map((t) => (
                <th key={t} scope="col" className="py-1 text-right font-normal tabular-nums">
                  {t}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {curves.map(([cl, curve]) => {
              const cluster = Number(cl);
              const on = selectedClusters.includes(cluster);
              return (
              <tr
                key={cl}
                className="border-t border-[var(--line)] transition-colors duration-200"
                style={
                  on
                    ? {
                        background: `color-mix(in oklab, ${clusterColor(cluster)} 12%, transparent)`,
                        color: "var(--text-primary)",
                      }
                    : { opacity: anySelected ? 0.5 : 1 }
                }
              >
                <td className="py-0.5">
                  <span className="inline-flex items-center gap-1.5">
                    <SubgroupMark cluster={cluster} size={9} />
                    {subgroupLabel(cluster)}
                  </span>
                </td>
                {ticks.map((t) => (
                  <td key={t} className="text-right tabular-nums">
                    {atRisk(curve, t)}
                  </td>
                ))}
              </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </PanelCard>
  );
}
