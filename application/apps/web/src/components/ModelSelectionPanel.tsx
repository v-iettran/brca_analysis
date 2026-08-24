"use client";

export function ModelSelectionPanel({
  rows,
  k,
  showReference,
}: {
  rows: Array<{ k: number; bic: number; silhouette: number; stability: number }>;
  k: number;
  showReference: boolean;
}) {
  const metrics: Array<{ key: "bic" | "silhouette" | "stability"; label: string; invert?: boolean; gate?: number }> = [
    { key: "bic", label: "BIC", invert: true },
    { key: "silhouette", label: "Silhouette" },
    { key: "stability", label: "Bootstrap ARI", gate: 0.6 },
  ];
  return (
    <section className="flex h-full flex-col rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-4">
      <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-400">Model selection</p>
      <h2 className="mt-1 text-base font-semibold">Structure, not survival</h2>
      <div className="mt-3 grid grid-cols-3 gap-2">
        {metrics.map((metric) => {
          const values = rows.map((r) => r[metric.key]);
          const min = Math.min(...values);
          const max = Math.max(...values);
          const span = max - min || 1;
          const w = 120;
          const h = 56;
          const pts = rows
            .map((r, i) => {
              const x = (i / Math.max(rows.length - 1, 1)) * w;
              const y = h - ((r[metric.key] - min) / span) * (h - 8) - 4;
              return `${x},${y}`;
            })
            .join(" ");
          const kIndex = rows.findIndex((r) => r.k === k);
          const kx = (kIndex / Math.max(rows.length - 1, 1)) * w;
          return (
            <svg key={metric.key} viewBox={`0 0 ${w} ${h + 16}`} className="w-full" role="img" aria-label={metric.label}>
              <text x="0" y="10" className="fill-slate-500" fontSize="9">
                {metric.label}
              </text>
              {metric.gate != null && showReference && (
                <line
                  x1="0"
                  x2={w}
                  y1={h - ((metric.gate - min) / span) * (h - 8) - 4 + 12}
                  y2={h - ((metric.gate - min) / span) * (h - 8) - 4 + 12}
                  stroke="#0f766e"
                  strokeDasharray="3 2"
                  opacity="0.6"
                />
              )}
              <polyline fill="none" stroke="#0f766e" strokeWidth="1.5" points={pts.split(" ").map((p) => {
                const [x, y] = p.split(",");
                return `${x},${Number(y) + 12}`;
              }).join(" ")} />
              <line x1={kx} x2={kx} y1="12" y2={h + 8} stroke="#7c3aed" strokeWidth="1" />
            </svg>
          );
        })}
      </div>
      {!showReference && <p className="mt-2 text-[11px] text-amber-700">KMeans is exploratory — BIC/ARI reference lines are for the GMM path only.</p>}
      <p className="mt-auto pt-2 text-[11px] text-slate-500">k selected from structure. Survival is tested separately.</p>
    </section>
  );
}
