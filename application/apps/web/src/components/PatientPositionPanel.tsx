"use client";

import type { PatientPosition } from "@/lib/types";
import { GlossaryAffordance } from "@/components/GlossaryAffordance";

export function PatientPositionPanel({ data }: { data: PatientPosition }) {
  const [x, y] = data.umap_coords;
  const xs = data.cohort_points.map((p) => p.x);
  const ys = data.cohort_points.map((p) => p.y);
  const minX = Math.min(x, ...xs) - 0.4;
  const maxX = Math.max(x, ...xs) + 0.4;
  const minY = Math.min(y, ...ys) - 0.4;
  const maxY = Math.max(y, ...ys) + 0.4;
  const w = 420;
  const h = 280;
  const sx = (v: number) => ((v - minX) / (maxX - minX || 1)) * w;
  const sy = (v: number) => h - ((v - minY) / (maxY - minY || 1)) * h;
  const rx = Math.max(data.posterior_ellipse.rx * (w / (maxX - minX || 1)), 10);
  const ry = Math.max(data.posterior_ellipse.ry * (h / (maxY - minY || 1)), 8);
  const deg = (data.posterior_ellipse.theta * 180) / Math.PI;
  const mass = Math.round(data.cluster.posterior_mass * 100);

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <header className="flex items-start justify-between gap-3">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-400">2 · Patient position</p>
          <h2 className="mt-1 text-lg font-semibold text-slate-950">
            Cluster {data.cluster.label} — {mass}%
          </h2>
          <p className="mt-1 text-xs text-slate-500">
            Modalities used: {data.modalities_used.join(", ") || "none"}. Ellipse is the PoE posterior, not a
            point estimate.
          </p>
        </div>
        <GlossaryAffordance panel="position" />
      </header>
      <svg viewBox={`0 0 ${w} ${h}`} className="mt-4 w-full rounded-xl bg-slate-50" role="img" aria-label="Latent posterior">
        {data.cohort_points.map((point, index) => (
          <circle key={index} cx={sx(point.x)} cy={sy(point.y)} r={1.6} className="fill-slate-300" />
        ))}
        <ellipse
          cx={sx(x)}
          cy={sy(y)}
          rx={rx}
          ry={ry}
          transform={`rotate(${deg} ${sx(x)} ${sy(y)})`}
          className="fill-indigo-500/20 stroke-indigo-600"
          strokeWidth={2}
        />
        <circle cx={sx(x)} cy={sy(y)} r={4} className="fill-indigo-700" />
      </svg>
    </section>
  );
}
