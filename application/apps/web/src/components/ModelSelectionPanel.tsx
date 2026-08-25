"use client";

import { PanelCard } from "@/components/PanelCard";

export function ModelSelectionPanel({
  rows,
  k,
  showReference,
  takeaway,
}: {
  rows: Array<{ k: number; bic: number; silhouette: number; stability: number }>;
  k: number;
  showReference: boolean;
  takeaway?: string;
}) {
  const minBic = Math.min(...rows.map((r) => r.bic));
  const rule = "Selected: highest stability among k within 10 BIC of the minimum.";
  const w = 320;
  const h = 88;
  const pad = { l: 28, r: 8, t: 8, b: 22 };

  function series(key: "bic" | "silhouette" | "stability", invert = false) {
    const vals = rows.map((r) => r[key]);
    const lo = Math.min(...vals);
    const hi = Math.max(...vals);
    const span = hi - lo || 1;
    return rows.map((r, i) => {
      const t = (r[key] - lo) / span;
      const y = pad.t + (invert ? t : 1 - t) * (h - pad.t - pad.b);
      const x = pad.l + (i / Math.max(rows.length - 1, 1)) * (w - pad.l - pad.r);
      return { x, y, k: r.k };
    });
  }

  const bicPts = series("bic", true);
  const silPts = series("silhouette");
  const stabPts = series("stability");

  return (
    <PanelCard
      id="structure"
      eyebrow="Model selection"
      title="Structure, not survival"
      takeaway={takeaway}
      display={k}
      displayCaption="subgroups"
      footnote={`${rule} Source: TCGA-BRCA intrinsic expression. n = cohort shown in the projection.`}
    >
      {!showReference && (
        <p className="mb-2 text-[11px] text-amber-800">KMeans is exploratory — BIC/ARI reference lines are for the GMM path only.</p>
      )}
      <table className="w-full text-xs">
        <thead>
          <tr className="text-left text-[var(--text-muted)]">
            <th className="pb-1 font-medium">k</th>
            <th className="pb-1 font-medium">BIC ↓</th>
            <th className="pb-1 font-medium">Silhouette ↑</th>
            <th className="pb-1 font-medium">Stability ↑</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const selected = row.k === k;
            const bar = Math.max(0, Math.min(1, row.stability));
            return (
              <tr key={row.k} className={selected ? "bg-teal-50 font-medium" : ""}>
                <td className="py-1 font-mono tabular-nums">
                  {selected ? "▸ " : "  "}
                  {row.k}
                </td>
                <td className="font-mono tabular-nums">{row.bic.toFixed(1)}</td>
                <td className="font-mono tabular-nums">{row.silhouette.toFixed(2)}</td>
                <td>
                  <span className="inline-flex items-center gap-2 font-mono tabular-nums">
                    {row.stability.toFixed(2)}
                    <span className="relative h-2 w-20 overflow-hidden rounded-full bg-slate-200">
                      <span className="absolute inset-y-0 left-0 bg-teal-700" style={{ width: `${bar * 100}%` }} />
                      {showReference && (
                        <span className="absolute inset-y-0 w-px bg-[var(--text-primary)]" style={{ left: "60%" }} title="0.60 gate" />
                      )}
                    </span>
                  </span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="mt-2 text-[11px] text-[var(--text-muted)]">
        Window: BIC within 10 of {minBic.toFixed(1)}. Dashed mark on the bar is the 0.60 stability gate.
      </p>
      <svg viewBox={`0 0 ${w} ${h}`} className="mt-3 w-full" role="img" aria-label="Selection metrics versus k">
        <text x={w / 2} y={h - 2} textAnchor="middle" fontSize="11" className="fill-[var(--text-secondary)]">
          k
        </text>
        <text x={4} y={12} fontSize="9" className="fill-[var(--text-muted)]">
          normalised
        </text>
        {rows.map((row, i) => {
          const x = pad.l + (i / Math.max(rows.length - 1, 1)) * (w - pad.l - pad.r);
          return (
            <text key={row.k} x={x} y={h - 10} textAnchor="middle" fontSize="11" className="fill-[var(--text-muted)] font-mono">
              {row.k}
            </text>
          );
        })}
        {[
          { pts: bicPts, color: "#0369A1", dash: undefined, name: "BIC ↓" },
          { pts: silPts, color: "#7C3AED", dash: "4 3", name: "Silhouette ↑" },
          { pts: stabPts, color: "#0F766E", dash: "1 3", name: "Stability ↑" },
        ].map((s) => (
          <polyline
            key={s.name}
            fill="none"
            stroke={s.color}
            strokeWidth="1.5"
            strokeDasharray={s.dash}
            points={s.pts.map((p) => `${p.x},${p.y}`).join(" ")}
          />
        ))}
      </svg>
      <ul className="mt-1 flex flex-wrap gap-3 text-[10px] text-[var(--text-secondary)]">
        <li className="flex items-center gap-1">
          <span className="inline-block h-px w-4 bg-[#0369A1]" /> BIC ↓
        </li>
        <li className="flex items-center gap-1">
          <span className="inline-block w-4 border-t border-dashed border-[#7C3AED]" /> Silhouette ↑
        </li>
        <li className="flex items-center gap-1">
          <span className="inline-block w-4 border-t border-dotted border-[#0F766E]" /> Stability ↑
        </li>
      </ul>
    </PanelCard>
  );
}
