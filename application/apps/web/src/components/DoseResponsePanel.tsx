"use client";

import { useEffect, useMemo, useState } from "react";
import type { V3CellLine, V3DoseCurve, V3PatientPayload } from "@/lib/v3-types";
import { PanelCard } from "@/components/PanelCard";
import { ChartAxes, chartPad } from "@/components/ChartAxes";
import { clusterColor } from "@/lib/clusterPalette";
import { termLabel } from "@/lib/v3-vocabulary";
import { ReversalCandidates } from "@/components/ReversalCandidates";

function viabilityAt(curve: V3DoseCurve, conc: number): number {
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

/**
 * GDSC reports concentrations in micromolar, so the panel does too. The payload
 * stores nanomolar internally; converting at the edge keeps one unit on screen
 * instead of a nanomolar axis under micromolar source data.
 */
function uM(nm: number): string {
  const value = nm / 1000;
  if (value >= 10) return `${value.toFixed(0)} µM`;
  if (value >= 1) return `${value.toFixed(1)} µM`;
  if (value >= 0.01) return `${value.toFixed(2)} µM`;
  return `${value.toPrecision(2)} µM`;
}

/**
 * Measured GDSC response.
 *
 * Series identity is in the legend, not written into the plot: four curves that
 * converge stacked their names and their IC50 markers on top of one another.
 *
 * The curve is drawn solid only across the concentrations GDSC actually tested
 * and dotted beyond them. Most of these fitted IC50s fall outside the tested
 * window — for EFM-192A, three of four do — which makes them extrapolations of
 * a no-effect curve rather than measured potencies. Drawing them identically to
 * a real hit was the panel's most misleading behaviour.
 */
export function DoseResponsePanel({
  runId,
  line,
  reversal,
  a4Failed,
  concentration,
  onConcentration,
  takeaway,
}: {
  runId: string;
  line: V3CellLine | null;
  reversal: V3PatientPayload["reversal_candidates"];
  a4Failed: boolean;
  concentration: number;
  onConcentration: (nm: number) => void;
  takeaway?: string;
}) {
  const curves = useMemo(() => line?.curves ?? [], [line]);
  const [selected, setSelected] = useState<string[]>([]);

  // Clear the comparison when the reader picks a different cell line. Adjusting
  // state during render rather than in an effect avoids a second render pass.
  const [seenLine, setSeenLine] = useState(line?.line_id);
  if (line?.line_id !== seenLine) {
    setSeenLine(line?.line_id);
    setSelected([]);
  }

  const cmax = useMemo(() => {
    const values = curves.map((c) => c.cmax_nm).filter((v): v is number => v != null && v > 0);
    return values[0] ?? null;
  }, [curves]);

  useEffect(() => {
    if (cmax != null && concentration === 250) onConcentration(cmax);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cmax]);


  // 1 nM to 100 uM, labelled in micromolar.
  const decades = [1, 10, 100, 1000, 10000, 100000];
  const W = 620;
  const H = 260;
  const geom = chartPad(W, H, { l: 54, r: 24, t: 18, b: 38 });
  const xOf = (nm: number) => geom.pad.l + (Math.log10(Math.max(nm, 1)) / 5) * geom.innerW;
  const yOf = (v: number) => geom.y(v);
  // Default to the retrieved candidates that were actually measured on this
  // line; everything else GDSC tested is one click away.
  const candidateNames = useMemo(() => {
    const names = new Set(
      (reversal?.members ?? []).map((m) => String(m.canonical || m.drug).toLowerCase())
    );
    return names;
  }, [reversal]);
  const defaults = useMemo(
    () => curves.filter((c) => candidateNames.has(String(c.canonical || c.drug).toLowerCase())).map((c) => c.drug),
    [curves, candidateNames]
  );
  const [seenDefaults, setSeenDefaults] = useState<string>("");
  const key = `${line?.line_id ?? ""}:${defaults.join(",")}`;
  if (key !== seenDefaults) {
    setSeenDefaults(key);
    setSelected(defaults);
  }

  const plotted = curves.filter((c) => selected.includes(c.drug));
  const nExtrapolated = plotted.filter((c) => c.ic50_extrapolated).length;

  function toggle(drug: string) {
    setSelected((prev) => (prev.includes(drug) ? prev.filter((d) => d !== drug) : [...prev, drug]));
  }

  return (
    <PanelCard
      id="retrieval"
      eyebrow="Measured response"
      title="Measured GDSC dose-response"
      takeaway={takeaway}
      display={curves.length || "—"}
      displayCaption={curves.length ? "measured curves" : "no curves for this line"}
      footnote="Not a simulation. Curves are Hill models fitted by GDSC to measured viability readings. Solid where GDSC actually tested; dashed beyond that, where the curve is the fitted model extended past the data rather than anything measured. The shaded ribbon is a fixed ±8% display band, not a confidence interval. Compounds are shown as evidence, not as recommendations."
    >
      {a4Failed && (
        <p className="mb-3 text-[12px] text-[var(--warning)]">
          Cluster-versus-normal reversal is omitted because the normal comparison did not recover known
          biology.
        </p>
      )}

      {reversal && !a4Failed && <ReversalCandidates runId={runId} reversal={reversal} />}

      {line && curves.length > 0 ? (
        <>
          {nExtrapolated > 0 && (
            <p className="mb-2 text-[12px] text-[var(--warning)]">
              {nExtrapolated} of {plotted.length} plotted IC50 values fall outside the range GDSC tested.
              The cells never reached half viability at any tested dose, so that IC50 is where the fitted
              curve would cross 50% if extended — a property of the fit, not an observation.
            </p>
          )}

          <ChartAxes
            width={W}
            height={H}
            pad={geom.pad}
            xLabel="Concentration (µM)"
            yLabel="Cell viability (%)"
            xTicks={decades.map((d) => ({ v: d, x: xOf(d), label: uM(d).replace(" µM", "") }))}
            yTicks={[0, 0.25, 0.5, 0.75, 1].map((v) => ({ v, y: yOf(v), label: String(v * 100) }))}
          >
            {cmax != null && (
              <>
                <rect
                  x={geom.pad.l}
                  y={geom.pad.t}
                  width={Math.max(0, xOf(cmax) - geom.pad.l)}
                  height={geom.innerH}
                  fill="var(--text-secondary)"
                  opacity="0.06"
                />
                <line
                  x1={xOf(cmax)}
                  x2={xOf(cmax)}
                  y1={geom.pad.t}
                  y2={geom.pad.t + geom.innerH}
                  stroke="var(--text-secondary)"
                />
                <text
                  x={xOf(cmax) - 5}
                  y={geom.pad.t + 11}
                  textAnchor="end"
                  fontSize="10"
                  fill="var(--text-secondary)"
                  className="font-mono"
                >
                  Cmax {uM(cmax)}
                </text>
              </>
            )}

            {curves.map((curve, i) => {
              const color = clusterColor(i);
              const on = selected.includes(curve.drug);
              if (!on) return null;
              const ceiling = curve.max_conc_nm ?? Infinity;
              const inside: string[] = [];
              const beyond: string[] = [];
              curve.concentration_nm.forEach((c, idx) => {
                const point = `${xOf(c)},${yOf(curve.viability[idx])}`;
                if (c <= ceiling) inside.push(point);
                else {
                  if (beyond.length === 0 && inside.length) beyond.push(inside[inside.length - 1]);
                  beyond.push(point);
                }
              });
              return (
                <g key={curve.drug} style={{ transition: "opacity 200ms var(--ease-out)" }}>
                  {inside.length > 1 && (
                    <polyline
                      fill="none"
                      stroke={color}
                      strokeWidth="2.4"
                      points={inside.join(" ")}
                    />
                  )}
                  {beyond.length > 1 && (
                    <polyline
                      fill="none"
                      stroke={color}
                      strokeWidth="2.4"
                      strokeDasharray="2 3"
                      points={beyond.join(" ")}
                    />
                  )}
                  {!curve.ic50_extrapolated && (
                    <line
                      x1={xOf(curve.ic50_nm)}
                      x2={xOf(curve.ic50_nm)}
                      y1={yOf(0.5) - 6}
                      y2={yOf(0.5) + 6}
                      stroke={color}
                      strokeWidth="2"
                    />
                  )}
                </g>
              );
            })}

            <line
              x1={xOf(concentration)}
              x2={xOf(concentration)}
              y1={geom.pad.t}
              y2={geom.pad.t + geom.innerH}
              stroke="var(--text-primary)"
              strokeDasharray="3 2"
            />
          </ChartAxes>

          {/* A picker, not just a legend: nothing is plotted unless chosen. */}
          <div className="mt-3 flex flex-wrap items-baseline justify-between gap-2 border-t border-[var(--line)] pt-3">
            <p className="eyebrow">Drugs measured on {line.name}</p>
            <span className="flex gap-1.5">
              <button
                type="button"
                onClick={() => setSelected(curves.map((c) => c.drug))}
                className="pressable border border-[var(--line)] px-2 py-0.5 text-[11px] text-[var(--text-secondary)]"
              >
                Plot all {curves.length}
              </button>
              <button
                type="button"
                onClick={() => setSelected([])}
                className="pressable border border-[var(--line)] px-2 py-0.5 text-[11px] text-[var(--text-secondary)]"
              >
                Clear
              </button>
            </span>
          </div>
          <ul className="mt-1.5 space-y-0.5">
            {curves.map((curve, i) => {
              const on = selected.includes(curve.drug);
              const candidate = candidateNames.has(String(curve.canonical || curve.drug).toLowerCase());
              return (
                <li key={curve.drug}>
                  <button
                    type="button"
                    aria-pressed={on}
                    onClick={() => toggle(curve.drug)}
                    className="pressable flex w-full flex-wrap items-center gap-x-3 gap-y-0.5 px-2 py-1 text-left"
                    style={{ opacity: on ? 1 : 0.55 }}
                  >
                    <span
                      aria-hidden
                      className="flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-[3px] border text-[9px] font-bold text-white"
                      style={{
                        borderColor: on ? clusterColor(i) : "var(--line-strong)",
                        background: on ? clusterColor(i) : "transparent",
                      }}
                    >
                      {on ? "✓" : ""}
                    </span>
                    <span className="font-mono text-[12px] font-medium text-[var(--text-primary)]">
                      {curve.canonical || curve.drug}
                    </span>
                    {curve.evidence_label && (
                      <span
                        className="rounded border px-1 text-[9.5px]"
                        style={
                          curve.evidence_tier === "standard_of_care"
                            ? { borderColor: "var(--cluster-1)", color: "var(--cluster-1)" }
                            : { borderColor: "var(--line-strong)", color: "var(--text-muted)" }
                        }
                        title={curve.evidence_reason}
                      >
                        {curve.evidence_label}
                      </span>
                    )}
                    {candidate && (
                      <span
                        className="text-[9.5px] text-[var(--text-muted)]"
                        title="This compound was among the reversal candidates retrieved for this subgroup."
                      >
                        retrieved
                      </span>
                    )}
                    <span className="font-mono text-[11px] tabular-nums text-[var(--text-secondary)]">
                      IC50 {uM(curve.ic50_nm)}
                    </span>
                    {curve.auc != null && (
                      <span className="font-mono text-[11px] tabular-nums text-[var(--text-muted)]">
                        AUC {curve.auc.toFixed(2)}
                      </span>
                    )}
                    {curve.ic50_extrapolated ? (
                      <span className="rounded border border-[var(--warning-line)] bg-[var(--warning-wash)] px-1 text-[10px] font-medium text-[var(--warning)]">
                        beyond tested range
                      </span>
                    ) : (
                      <span className="text-[10px] text-[var(--text-muted)]">
                        within tested range{curve.max_conc_nm ? ` (≤ ${uM(curve.max_conc_nm)})` : ""}
                      </span>
                    )}
                  </button>
                </li>
              );
            })}
          </ul>

          <div className="mt-3">
            <div className="flex items-baseline justify-between">
              <span className="text-[11px] text-[var(--text-secondary)]">Concentration</span>
              <span className="font-mono text-[11px] tabular-nums text-[var(--text-primary)]">
                {uM(concentration)}
              </span>
            </div>
            <input
              type="range"
              min={1}
              max={100000}
              value={concentration}
              onChange={(e) => onConcentration(Number(e.target.value))}
              className="mt-1.5 w-full"
              /* A stable name: the value belongs in aria-valuetext, which
                 assistive tech reads on change, not in the label itself. */
              aria-label="Concentration"
              aria-valuetext={uM(concentration)}
            />
          </div>

          {/* One line per drug, not one run-on sentence. */}
          <div
            className="mt-1.5 space-y-0.5 rounded-[var(--radius-inner)] border border-[var(--line)] bg-[var(--well)] p-2.5"
            data-testid="dose-readout"
          >
            <p className="font-mono text-[11px] tabular-nums text-[var(--text-muted)]">
              At {uM(concentration)} in {line.name}
              {plotted.length ? "" : " — choose a drug above to plot it"}
            </p>
            {plotted.map((curve, i) => (
              <p key={curve.drug} className="font-mono text-[12px] tabular-nums text-[var(--text-secondary)]">
                <span
                  className="mr-1.5 inline-block h-2 w-2 rounded-[2px] align-middle"
                  style={{ background: clusterColor(curves.indexOf(curve) >= 0 ? curves.indexOf(curve) : i) }}
                />
                <span className="text-[var(--text-primary)]">{curve.canonical || curve.drug}</span>{" "}
                {(viabilityAt(curve, concentration) * 100).toFixed(0)}% viability
                <span className="text-[var(--text-muted)]">
                  {" "}
                  · {termLabel(curve.source)}
                  {curve.z_score != null ? ` · z ${curve.z_score.toFixed(2)}` : ""}
                </span>
              </p>
            ))}
          </div>
        </>
      ) : (
        <div className="flex min-h-[180px] flex-col items-start justify-center gap-1.5 px-1">
          <p className="text-[13px] text-[var(--text-secondary)]">
            No GDSC dose-response was measured for {line?.name ?? "this line"}.
          </p>
          <p className="text-[11px] text-[var(--text-muted)]">
            The line is still a valid molecular neighbour. Select another line to see measured curves, rather
            than reading an absence as a null result.
          </p>
        </div>
      )}
    </PanelCard>
  );
}
