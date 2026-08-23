"use client";

import { useMemo } from "react";
import type { RnaProjection } from "@/lib/types";

const CLUSTER_COLORS = [
  "#4f46e5",
  "#db2777",
  "#059669",
  "#d97706",
  "#0891b2",
];

export function RnaUmapPanel({ projection }: { projection: RnaProjection }) {
  const bounds = useMemo(() => {
    const xs = [...projection.reference.map((p) => p.x), projection.patient.x];
    const ys = [...projection.reference.map((p) => p.y), projection.patient.y];
    const minX = Math.min(...xs);
    const maxX = Math.max(...xs);
    const minY = Math.min(...ys);
    const maxY = Math.max(...ys);
    return { minX, maxX, minY, maxY };
  }, [projection]);

  const clusterIds = useMemo(() => {
    const ids = new Set(projection.reference.map((p) => Number(p.mofa_cluster)));
    return [...ids].filter((id) => Number.isFinite(id)).sort((a, b) => a - b);
  }, [projection]);

  const width = 640;
  const height = 360;
  const pad = 24;

  function sx(x: number) {
    const span = bounds.maxX - bounds.minX || 1;
    return pad + ((x - bounds.minX) / span) * (width - pad * 2);
  }
  function sy(y: number) {
    const span = bounds.maxY - bounds.minY || 1;
    return height - pad - ((y - bounds.minY) / span) * (height - pad * 2);
  }

  function colorForCluster(clusterId: number) {
    return CLUSTER_COLORS[((clusterId % CLUSTER_COLORS.length) + CLUSTER_COLORS.length) % CLUSTER_COLORS.length];
  }

  return (
    <section className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-indigo-600">RNA projection</p>
          <h3 className="mt-1 text-lg font-semibold text-slate-950">Patient placement among METABRIC RNA</h3>
          <p className="mt-1 max-w-2xl text-xs leading-5 text-slate-500">{projection.label}</p>
        </div>
        <div className="rounded-full bg-slate-100 px-3 py-1 text-[11px] font-semibold text-slate-600">
          Method: {projection.method.toUpperCase()} · shown {projection.n_reference_shown}/{projection.n_reference_total}
        </div>
      </div>
      <svg viewBox={`0 0 ${width} ${height}`} className="mt-4 w-full rounded-xl border border-slate-100 bg-slate-50">
        {projection.reference.map((point) => (
          <circle
            key={point.sample_id}
            cx={sx(point.x)}
            cy={sy(point.y)}
            r={3}
            fill={colorForCluster(point.mofa_cluster)}
            opacity={0.55}
          >
            <title>{`Cluster ${point.mofa_cluster}`}</title>
          </circle>
        ))}
        <circle
          cx={sx(projection.patient.x)}
          cy={sy(projection.patient.y)}
          r={8}
          fill="#0f172a"
          stroke="#f8fafc"
          strokeWidth={2}
        >
          <title>Patient</title>
        </circle>
      </svg>
      <div className="mt-3 flex flex-wrap gap-2 text-[10px] font-semibold text-slate-500">
        {clusterIds.map((clusterId) => (
          <span key={clusterId} className="inline-flex items-center gap-1 rounded-md bg-slate-100 px-2 py-1">
            <span className="h-2 w-2 rounded-full" style={{ background: colorForCluster(clusterId) }} />
            Cluster {clusterId}
          </span>
        ))}
        <span className="inline-flex items-center gap-1 rounded-md bg-slate-900 px-2 py-1 text-white">
          ● Patient
        </span>
      </div>
    </section>
  );
}
