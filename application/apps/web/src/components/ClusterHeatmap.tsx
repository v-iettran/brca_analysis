"use client";

import { Fragment, useMemo, useState } from "react";
import { clusterColor, divergingEffect } from "@/lib/clusterPalette";
import { formatQ, subgroupLabel } from "@/lib/v3-format";
import type { V3ClusterAnnotation, V3ComparisonMatrix } from "@/lib/v3-types";
import { PanelCard } from "@/components/PanelCard";

const GROUP_META = [
  { key: "pathway", label: "PATHWAYS" },
  { key: "tf", label: "TRANSCRIPTION FACTORS" },
  { key: "gene", label: "GENES" },
] as const;

export function ClusterHeatmap({
  matrix,
  k,
  selectedCluster,
  onSelectCluster,
  takeaway,
  annotations,
}: {
  matrix: V3ComparisonMatrix;
  k: number;
  selectedCluster: number | null;
  onSelectCluster: (cluster: number) => void;
  takeaway?: string;
  annotations?: Record<string, V3ClusterAnnotation>;
}) {
  const [groups, setGroups] = useState({ pathway: true, tf: true, gene: true });
  const [open, setOpen] = useState({ pathway: true, tf: true, gene: true });
  const [hover, setHover] = useState<{ row: number; col: number } | null>(null);

  const grouped = useMemo(() => {
    const by: Record<string, Array<{ feature: string; family: string; effects: number[]; q: number[]; i: number }>> = {
      pathway: [],
      tf: [],
      gene: [],
    };
    matrix.features.forEach((feature, i) => {
      const family = matrix.families[i];
      const row = { feature, family, effects: matrix.effects[i], q: matrix.q[i], i };
      (by[family] || by.gene).push(row);
    });
    for (const key of Object.keys(by)) {
      by[key].sort((a, b) => Math.max(...b.effects.map(Math.abs)) - Math.max(...a.effects.map(Math.abs)));
    }
    return by;
  }, [matrix]);

  const visible = GROUP_META.filter((g) => groups[g.key]).flatMap((g) => (open[g.key] ? grouped[g.key] : []));
  const maxAbs = Math.max(0.01, ...visible.flatMap((r) => r.effects.map((v) => Math.abs(v))));

  return (
    <PanelCard
      id="characteristics"
      eyebrow="Cluster characteristics"
      title="Compare every subgroup at once"
      takeaway={takeaway}
      footnote="Colour is standardised effect size, centred at 0. Cells with q ≥ 0.05 are shown at 20% opacity. Source: TCGA-BRCA."
    >
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div className="flex gap-2 text-xs">
          {GROUP_META.map((g) => (
            <button
              key={g.key}
              type="button"
              onClick={() => setGroups((prev) => ({ ...prev, [g.key]: !prev[g.key] }))}
              className={`rounded-full px-2 py-0.5 ${groups[g.key] ? "bg-slate-900 text-white" : "border border-slate-300 text-slate-500"}`}
            >
              {g.label.toLowerCase()}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-2 text-[11px] text-[var(--text-muted)]">
          <span>−{maxAbs.toFixed(1)}</span>
          <span
            className="h-2 w-36 rounded-full"
            style={{
              background: "linear-gradient(90deg,#0F766E,#5EEAD4,#F8FAFC,#C4B5FD,#7C3AED)",
            }}
          />
          <span>+{maxAbs.toFixed(1)}</span>
          <span>standardised effect size</span>
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr>
              <th className="text-left font-medium text-slate-500">feature</th>
              {matrix.clusters.map((cl) => {
                const ann = annotations?.[String(cl)];
                return (
                  <th key={cl}>
                    <button type="button" onClick={() => onSelectCluster(cl)} className="inline-flex flex-col items-center gap-0.5 font-mono">
                      <span className="inline-flex items-center gap-1">
                        <span className="inline-block h-2 w-2 rounded-full" style={{ background: clusterColor(cl, k) }} />
                        {subgroupLabel(cl)}
                      </span>
                      <span className="text-[10px] font-normal text-[var(--text-muted)]">
                        n={ann?.n ?? "—"} {ann?.pam50_majority ?? ""}
                      </span>
                    </button>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {GROUP_META.filter((g) => groups[g.key]).map((g) => (
              <Fragment key={g.key}>
                <tr key={`${g.key}-h`}>
                  <td colSpan={1 + matrix.clusters.length} className="pt-3">
                    <button
                      type="button"
                      className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]"
                      onClick={() => setOpen((prev) => ({ ...prev, [g.key]: !prev[g.key] }))}
                    >
                      {open[g.key] ? "▾" : "▸"} {g.label} ({grouped[g.key].length})
                    </button>
                  </td>
                </tr>
                {open[g.key] &&
                  grouped[g.key].map((row) => (
                    <tr key={row.feature} className={hover?.row === row.i ? "bg-slate-50" : ""}>
                      <td className="whitespace-nowrap py-0.5 pr-2 text-slate-600">{row.feature}</td>
                      {row.effects.map((value, j) => {
                        const q = row.q[j] ?? 1;
                        const direction = value > 0 ? "up" : value < 0 ? "down" : "unchanged";
                        return (
                          <td
                            key={j}
                            className="p-0.5"
                            onMouseEnter={() => setHover({ row: row.i, col: j })}
                            onMouseLeave={() => setHover(null)}
                          >
                            <div
                              className="h-5 rounded-sm"
                              style={{
                                background: divergingEffect(value, maxAbs),
                                opacity: q < 0.05 ? 1 : 0.2,
                              }}
                              title={`${row.feature} ${subgroupLabel(matrix.clusters[j])} effect=${value.toFixed(2)} q=${formatQ(q)} ${direction}`}
                            />
                          </td>
                        );
                      })}
                    </tr>
                  ))}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
      {hover && (
        <p className="mt-2 font-mono text-[11px] text-[var(--text-secondary)]">
          {matrix.features[hover.row]} · {subgroupLabel(matrix.clusters[hover.col])} · effect{" "}
          {matrix.effects[hover.row][hover.col].toFixed(2)} · q={formatQ(matrix.q[hover.row][hover.col])}
        </p>
      )}
      {selectedCluster == null && <p className="mt-2 text-[11px] text-slate-400">Click a column for the cluster drawer.</p>}
    </PanelCard>
  );
}
