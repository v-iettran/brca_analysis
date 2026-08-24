"use client";

import { useMemo, useState } from "react";
import { clusterColor } from "@/lib/clusterPalette";
import type { V3ComparisonMatrix } from "@/lib/v3-types";

export function ClusterHeatmap({
  matrix,
  k,
  selectedCluster,
  onSelectCluster,
}: {
  matrix: V3ComparisonMatrix;
  k: number;
  selectedCluster: number | null;
  onSelectCluster: (cluster: number) => void;
}) {
  const [groups, setGroups] = useState({ pathway: true, tf: true, gene: true });
  const rows = useMemo(
    () =>
      matrix.features
        .map((feature, i) => ({ feature, family: matrix.families[i], effects: matrix.effects[i], q: matrix.q[i] }))
        .filter((row) => groups[row.family as keyof typeof groups] !== false),
    [matrix, groups]
  );
  const maxAbs = Math.max(0.01, ...rows.flatMap((r) => r.effects.map((v) => Math.abs(v))));

  function cellColor(value: number): string {
    const t = (value / maxAbs + 1) / 2;
    const h = 174 + (258 - 174) * t;
    return `hsl(${h} 70% 42%)`;
  }

  return (
    <section className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-4">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-400">Cluster characteristics</p>
          <h2 className="mt-1 text-base font-semibold">Compare every subgroup at once</h2>
        </div>
        <div className="flex gap-2 text-xs">
          {(["pathway", "tf", "gene"] as const).map((g) => (
            <button
              key={g}
              type="button"
              onClick={() => setGroups((prev) => ({ ...prev, [g]: !prev[g] }))}
              className={`rounded-full px-2 py-0.5 ${groups[g] ? "bg-slate-900 text-white" : "border border-slate-300 text-slate-500"}`}
            >
              {g}
            </button>
          ))}
        </div>
      </header>
      <div className="mt-3 overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr>
              <th className="text-left font-medium text-slate-500">feature</th>
              {matrix.clusters.map((cl) => (
                <th key={cl}>
                  <button type="button" onClick={() => onSelectCluster(cl)} className="inline-flex items-center gap-1 font-mono">
                    <span className="inline-block h-2 w-2 rounded-full" style={{ background: clusterColor(cl, k) }} />
                    c{cl}
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.feature}>
                <td className="whitespace-nowrap py-0.5 pr-2 text-slate-600">{row.feature}</td>
                {row.effects.map((value, j) => (
                  <td key={j} className="p-0.5">
                    <div
                      className="h-5 rounded-sm"
                      style={{
                        background: cellColor(value),
                        opacity: (row.q[j] ?? 1) < 0.05 ? 1 : 0.2,
                      }}
                      title={`${row.feature} c${matrix.clusters[j]} effect=${value.toFixed(2)} q=${(row.q[j] ?? 1).toFixed(3)}`}
                    />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {selectedCluster == null && <p className="mt-2 text-[11px] text-slate-400">Click a column for the cluster drawer.</p>}
    </section>
  );
}
