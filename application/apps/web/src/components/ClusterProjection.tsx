"use client";

import { clusterColor } from "@/lib/clusterPalette";
import { subgroupLabel } from "@/lib/v3-format";
import type { V3ClusterAnnotation } from "@/lib/v3-types";
import { PanelCard } from "@/components/PanelCard";

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
  takeaway,
  projection,
  variance,
  annotations,
  umapNote,
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
  takeaway?: string;
  projection: "pca" | "umap";
  variance?: number[];
  annotations?: Record<string, V3ClusterAnnotation>;
  umapNote?: string;
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
  const padFrac = 0.05;
  const dx = (maxX - minX) * padFrac || 0.1;
  const dy = (maxY - minY) * padFrac || 0.1;
  const W = 400;
  const H = 300;
  const pad = { l: 48, r: 72, t: 16, b: 36 };
  const sx = (x: number) => pad.l + ((x - (minX - dx)) / (maxX - minX + 2 * dx || 1)) * (W - pad.l - pad.r);
  const sy = (y: number) => pad.t + (1 - (y - (minY - dy)) / (maxY - minY + 2 * dy || 1)) * (H - pad.t - pad.b);
  const grouped = new Map<number, typeof points>();
  for (const p of points) {
    const list = grouped.get(p.cluster) ?? [];
    list.push(p);
    grouped.set(p.cluster, list);
  }
  const xName = projection === "pca" && variance?.[0] != null ? `PC1 (${Math.round(variance[0] * 100)}% var)` : projection === "pca" ? "PC1" : "UMAP-1";
  const yName = projection === "pca" && variance?.[1] != null ? `PC2 (${Math.round(variance[1] * 100)}% var)` : projection === "pca" ? "PC2" : "UMAP-2";
  const current = points.find((p) => p.id === currentId);

  return (
    <PanelCard
      id="projection"
      eyebrow="Cluster projection"
      title="Where this tumour sits"
      takeaway={takeaway}
      footnote={`n = ${points.length} · source TCGA-BRCA. ${projection === "umap" ? umapNote || "UMAP distances between clusters are not meaningful." : "PCA is linear; overlapping clouds are expected."}`}
    >
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label={`${projection.toUpperCase()} projection`}>
        <text x={12} y={H / 2} textAnchor="middle" transform={`rotate(-90 12 ${H / 2})`} fontSize="11" className="fill-[var(--text-secondary)]">
          {yName}
        </text>
        <text x={(W - pad.r + pad.l) / 2} y={H - 4} textAnchor="middle" fontSize="11" className="fill-[var(--text-secondary)]">
          {xName}
        </text>
        {clusteringAvailable &&
          Array.from(grouped.entries()).map(([cl, pts]) => {
            const h = hull(pts.map((p) => [sx(p.x), sy(p.y)]));
            if (h.length < 3) return null;
            return (
              <polygon
                key={`h-${cl}`}
                points={h.map((p) => p.join(",")).join(" ")}
                fill={clusterColor(cl, k)}
                opacity={0.08}
                onClick={() => onSelectCluster(cl)}
              />
            );
          })}
        {Array.from(grouped.entries()).map(([cl, pts]) => {
          const cx = pts.reduce((s, p) => s + sx(p.x), 0) / pts.length;
          const cy = pts.reduce((s, p) => s + sy(p.y), 0) / pts.length;
          return (
            <g key={`c-${cl}`} opacity={0.8}>
              <line x1={cx - 4} x2={cx + 4} y1={cy} y2={cy} stroke={clusterColor(cl, k)} strokeWidth="1.5" />
              <line x1={cx} x2={cx} y1={cy - 4} y2={cy + 4} stroke={clusterColor(cl, k)} strokeWidth="1.5" />
            </g>
          );
        })}
        {points.map((p) => {
          const faded = selectedCluster != null && p.cluster !== selectedCluster;
          const isCurrent = p.id === currentId;
          const width = widths[p.id] ?? 0.4;
          return (
            <g key={p.id} className="transition-opacity duration-200" opacity={faded ? 0.25 : 1}>
              {isCurrent && (
                <ellipse
                  cx={sx(p.x)}
                  cy={sy(p.y)}
                  rx={14 + width * 16}
                  ry={10 + width * 10}
                  fill={clusterColor(p.cluster, k)}
                  opacity="0.3"
                />
              )}
              <circle
                cx={sx(p.x)}
                cy={sy(p.y)}
                r={isCurrent ? 7 : 3.5}
                fill={clusteringAvailable ? clusterColor(p.cluster, k) : "#64748b"}
                stroke={isCurrent ? "#0F172A" : "none"}
                strokeWidth={isCurrent ? 1.6 : 0}
                className="transition-[cx,cy,fill] duration-[400ms] ease-out"
              >
                <title>{`${p.id} · ${subgroupLabel(p.cluster)} · P=${(membership[p.id]?.[p.cluster] ?? 0).toFixed(2)}`}</title>
              </circle>
            </g>
          );
        })}
        {current && (
          <text x={sx(current.x) + 10} y={sy(current.y) - 10} fontSize="11" className="fill-[var(--text-primary)] font-mono">
            {currentId}
          </text>
        )}
      </svg>
      <ul className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-[var(--text-secondary)]">
        {Array.from(grouped.entries())
          .sort((a, b) => a[0] - b[0])
          .map(([cl, pts]) => {
            const ann = annotations?.[String(cl)];
            return (
              <li key={cl} className="inline-flex items-center gap-1.5">
                <span className="h-2.5 w-2.5 rounded-full" style={{ background: clusterColor(cl, k) }} />
                {subgroupLabel(cl)}
                <span className="font-mono tabular-nums text-[var(--text-muted)]">n={ann?.n ?? pts.length}</span>
                {ann?.pam50_majority && <span>PAM50 majority: {ann.pam50_majority}</span>}
              </li>
            );
          })}
      </ul>
    </PanelCard>
  );
}
