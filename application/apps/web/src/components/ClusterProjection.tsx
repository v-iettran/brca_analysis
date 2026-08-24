"use client";

import { clusterColor } from "@/lib/clusterPalette";

function hull(points: Array<[number, number]>): Array<[number, number]> {
  const pts = [...points].sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  if (pts.length < 3) return pts;
  const cross = (o: number[], a: number[], b: number[]) => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
  const lower: Array<[number, number]> = [];
  for (const p of pts) {
    while (lower.length >= 2 && cross(lower[lower.length - 2], lower[lower.length - 1], p) <= 0) lower.pop();
    lower.push(p);
  }
  const upper: Array<[number, number]> = [];
  for (const p of [...pts].reverse()) {
    while (upper.length >= 2 && cross(upper[upper.length - 2], upper[upper.length - 1], p) <= 0) upper.pop();
    upper.push(p);
  }
  lower.pop();
  upper.pop();
  return [...lower, ...upper];
}

export function ClusterProjection({
  ids,
  coords,
  assignments,
  membership,
  widths,
  currentId,
  k,
  clusteringAvailable,
  selectedCluster,
  onSelectCluster,
}: {
  ids: string[];
  coords: Record<string, number[]>;
  assignments: Record<string, number>;
  membership: Record<string, number[]>;
  widths: Record<string, number>;
  currentId: string;
  k: number;
  clusteringAvailable: boolean;
  selectedCluster: number | null;
  onSelectCluster: (cluster: number | null) => void;
}) {
  const points = ids
    .map((id) => {
      const c = coords[id];
      if (!c) return null;
      return { id, x: c[0], y: c[1], cluster: assignments[id] ?? 0 };
    })
    .filter((p): p is { id: string; x: number; y: number; cluster: number } => p != null);
  const xs = points.map((p) => p.x);
  const ys = points.map((p) => p.y);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const sx = (x: number) => ((x - minX) / (maxX - minX || 1)) * 360 + 20;
  const sy = (y: number) => 280 - ((y - minY) / (maxY - minY || 1)) * 240;
  const grouped = new Map<number, Array<[number, number]>>();
  for (const p of points) {
    const list = grouped.get(p.cluster) ?? [];
    list.push([sx(p.x), sy(p.y)]);
    grouped.set(p.cluster, list);
  }

  return (
    <section className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-4">
      <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-400">Cluster projection</p>
      <h2 className="mt-1 text-base font-semibold">Cohort map</h2>
      <svg viewBox="0 0 400 300" className="mt-2 w-full" role="img" aria-label="Latent projection scatter">
        {clusteringAvailable &&
          Array.from(grouped.entries()).map(([cl, pts]) => {
            const h = hull(pts);
            if (h.length < 3) return null;
            return (
              <polygon
                key={`h-${cl}`}
                points={h.map((p) => p.join(",")).join(" ")}
                fill={clusterColor(cl, k)}
                opacity={0.15}
                onClick={() => onSelectCluster(cl)}
              />
            );
          })}
        {points.map((p) => {
          const faded = selectedCluster != null && p.cluster !== selectedCluster;
          const current = p.id === currentId;
          const width = widths[p.id] ?? 0.4;
          return (
            <g key={p.id} className="transition-opacity duration-200" opacity={faded ? 0.25 : 1}>
              {current && (
                <ellipse
                  cx={sx(p.x)}
                  cy={sy(p.y)}
                  rx={12 + width * 18}
                  ry={8 + width * 12}
                  fill="none"
                  stroke={clusterColor(p.cluster, k)}
                  strokeWidth="1.2"
                />
              )}
              <circle
                cx={sx(p.x)}
                cy={sy(p.y)}
                r={current ? 6 : 3.5}
                fill={clusteringAvailable ? clusterColor(p.cluster, k) : "#64748b"}
                className="transition-[cx,cy,fill] duration-[400ms] ease-out"
              >
                <title>{`${p.id} · cluster ${p.cluster} · P=${(membership[p.id]?.[p.cluster] ?? 0).toFixed(2)}`}</title>
              </circle>
            </g>
          );
        })}
      </svg>
    </section>
  );
}
