"use client";

import { useMemo, useState } from "react";
import { useReducedMotion } from "motion/react";
import { clusterColor, clusterShape, clusterShapePath } from "@/lib/clusterPalette";
import { subgroupLabel } from "@/lib/v3-format";
import type { V3ClusterAnnotation } from "@/lib/v3-types";
import { PanelCard } from "@/components/PanelCard";
import { SubgroupMark } from "@/components/SubgroupMark";
import { Modal } from "@/components/Modal";

type Point = { id: string; x: number; y: number; cluster: number };

function hull(points: Array<[number, number]>): Array<[number, number]> {
  const pts = [...points].sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  if (pts.length < 3) return pts;
  const cross = (o: number[], a: number[], b: number[]) =>
    (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
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

/**
 * The cohort in two dimensions.
 *
 * Every subgroup carries a marker shape as well as a hue. A scatter is read by
 * comparing any two series, and no four-hue set clears the colourblind
 * all-pairs floors — measured, not assumed — so hue alone cannot be trusted to
 * carry identity here.
 */
export function ClusterProjection({
  ids,
  coords,
  assignments,
  membership,
  widths,
  currentId,
  clusteringAvailable,
  selectedClusters,
  onToggleCluster,
  takeaway,
  projection,
  variance,
  annotations,
  umapNote,
  encoder,
  encoderNote,
  preregistered,
}: {
  ids: string[];
  coords: Record<string, number[]>;
  assignments: Record<string, number>;
  membership: Record<string, number[]>;
  widths: Record<string, number>;
  currentId: string;
  clusteringAvailable: boolean;
  selectedClusters: number[];
  onToggleCluster: (cluster: number) => void;
  takeaway?: string;
  projection: "pca" | "umap";
  variance?: number[];
  annotations?: Record<string, V3ClusterAnnotation>;
  umapNote?: string;
  encoder?: string;
  encoderNote?: string;
  preregistered?: { k: number | null; method: string; covariance_type: string | null; stability?: number | null };
}) {
  const [explaining, setExplaining] = useState(false);
  const reduce = useReducedMotion();
  const [hovered, setHovered] = useState<Point | null>(null);

  const W = 620;
  const H = 400;
  const pad = { l: 54, r: 20, t: 18, b: 42 };

  const { points, sx, sy, grouped } = useMemo(() => {
    const pts: Point[] = [];
    for (const id of ids) {
      const c = coords[id];
      if (!c) continue;
      pts.push({ id, x: c[0], y: c[1], cluster: assignments[id] ?? 0 });
    }
    const xs = pts.map((p) => p.x);
    const ys = pts.map((p) => p.y);
    const minX = Math.min(...xs);
    const maxX = Math.max(...xs);
    const minY = Math.min(...ys);
    const maxY = Math.max(...ys);
    const dx = (maxX - minX) * 0.05 || 0.1;
    const dy = (maxY - minY) * 0.05 || 0.1;
    const spanX = maxX - minX + 2 * dx || 1;
    const spanY = maxY - minY + 2 * dy || 1;
    const fx = (x: number) => pad.l + ((x - (minX - dx)) / spanX) * (W - pad.l - pad.r);
    const fy = (y: number) => pad.t + (1 - (y - (minY - dy)) / spanY) * (H - pad.t - pad.b);
    const map = new Map<number, Point[]>();
    for (const p of pts) {
      const list = map.get(p.cluster) ?? [];
      list.push(p);
      map.set(p.cluster, list);
    }
    return { points: pts, sx: fx, sy: fy, grouped: map };
  }, [ids, coords, assignments, pad.l, pad.r, pad.t, pad.b]);

  const xName =
    projection === "pca"
      ? `PC1${variance?.[0] != null ? ` (${Math.round(variance[0] * 100)}% var)` : ""}`
      : "UMAP-1";
  const yName =
    projection === "pca"
      ? `PC2${variance?.[1] != null ? ` (${Math.round(variance[1] * 100)}% var)` : ""}`
      : "UMAP-2";

  const current = points.find((p) => p.id === currentId);
  const tween = reduce ? "none" : "transform 400ms var(--ease-out), fill 400ms var(--ease-out)";
  const clusters = Array.from(grouped.entries()).sort((a, b) => a[0] - b[0]);
  const anySelected = selectedClusters.length > 0;
  const currentWidth = current ? (widths[current.id] ?? 0) : 0;
  const currentMembership = current ? (membership[current.id]?.[current.cluster] ?? 0) : 0;

  return (
    <PanelCard
      id="projection"
      eyebrow="Cluster projection"
      title="Where this tumour sits"
      takeaway={takeaway}
      actions={
        <button
          type="button"
          onClick={() => setExplaining(true)}
          aria-label="How is this space built, and how is a patient placed in it?"
          className="pressable h-6 w-6 text-[12px] text-[var(--text-muted)]"
        >
          ?
        </button>
      }
      footnote={`n = ${points.length} · source TCGA-BRCA. ${
        projection === "umap"
          ? umapNote || "UMAP distances between clusters are not meaningful."
          : "PCA is linear and carries variance explained. Overlapping clouds are the expected result, not a defect."
      } Each subgroup has its own marker shape, so identity does not depend on colour.`}
    >
      <div className="relative">
        <svg
          viewBox={`0 0 ${W} ${H}`}
          className="w-full touch-none"
          role="img"
          aria-label={`${projection.toUpperCase()} projection of ${points.length} tumours`}
          onMouseLeave={() => setHovered(null)}
        >
          <rect
            x={pad.l}
            y={pad.t}
            width={W - pad.l - pad.r}
            height={H - pad.t - pad.b}
            fill="none"
            stroke="var(--line)"
          />
          <text
            x={12}
            y={(H - pad.b + pad.t) / 2}
            textAnchor="middle"
            transform={`rotate(-90 12 ${(H - pad.b + pad.t) / 2})`}
            fontSize="11"
            fill="var(--text-secondary)"
          >
            {yName}
          </text>
          <text
            x={(W - pad.r + pad.l) / 2}
            y={H - 8}
            textAnchor="middle"
            fontSize="11"
            fill="var(--text-secondary)"
          >
            {xName}
          </text>

          {clusteringAvailable &&
            clusters.map(([cl, pts]) => {
              const h = hull(pts.map((p) => [sx(p.x), sy(p.y)]));
              if (h.length < 3) return null;
              const on = !anySelected || selectedClusters.includes(cl);
              return (
                <polygon
                  key={`h-${cl}`}
                  points={h.map((p) => p.join(",")).join(" ")}
                  fill={clusterColor(cl)}
                  opacity={on ? 0.09 : 0.03}
                  stroke={clusterColor(cl)}
                  strokeOpacity={on ? 0.3 : 0.08}
                  style={{ transition: tween, cursor: "pointer" }}
                  onClick={() => onToggleCluster(cl)}
                />
              );
            })}

          {points.map((p) => {
            if (p.id === currentId) return null;
            const on = !anySelected || selectedClusters.includes(p.cluster);
            const hot = hovered?.id === p.id;
            return (
              <path
                key={p.id}
                d={clusterShapePath(clusterShape(p.cluster), hot ? 4.4 : 2.7)}
                fill={clusteringAvailable ? clusterColor(p.cluster) : "var(--text-muted)"}
                opacity={on ? 0.72 : 0.12}
                style={{ transform: `translate(${sx(p.x)}px, ${sy(p.y)}px)`, transition: tween }}
                onMouseEnter={() => setHovered(p)}
              />
            );
          })}

          {clusteringAvailable &&
            clusters.map(([cl, pts]) => {
              const cx = pts.reduce((s, p) => s + sx(p.x), 0) / pts.length;
              const cy = pts.reduce((s, p) => s + sy(p.y), 0) / pts.length;
              return (
                <g key={`c-${cl}`} style={{ transition: tween }}>
                  <circle cx={cx} cy={cy} r="7" fill="var(--surface)" opacity="0.85" />
                  <path
                    d={clusterShapePath(clusterShape(cl), 5)}
                    transform={`translate(${cx},${cy})`}
                    fill="none"
                    stroke={clusterColor(cl)}
                    strokeWidth="2"
                  />
                </g>
              );
            })}

          {/* The patient under review. The posterior ring keeps a floor radius:
              62% of this cohort has a membership probability above 0.999, so a
              ring scaled purely on posterior width would vanish for most
              patients and read as "no uncertainty shown" rather than "almost
              none". */}
          {current && (() => {
            const cx = sx(current.x);
            const cy = sy(current.y);
            // Keep the label inside the plot: near the right edge it flips to
            // the left of the marker rather than running past the frame.
            const flip = cx > W - pad.r - 90;
            const ringR = 18 + currentWidth * 44;
            return (
              <g style={{ transform: `translate(${cx}px, ${cy}px)`, transition: tween }}>
                <circle r={ringR} fill="var(--surface)" opacity="0.55" />
                <circle
                  r={ringR}
                  fill="none"
                  stroke={clusterColor(current.cluster)}
                  strokeWidth="2"
                  strokeDasharray="5 4"
                />
                <path
                  d={clusterShapePath(clusterShape(current.cluster), 6.5)}
                  fill={clusterColor(current.cluster)}
                  stroke="var(--surface)"
                  strokeWidth="2"
                />
                <text
                  x={flip ? -(ringR + 6) : ringR + 6}
                  y={-ringR - 5}
                  textAnchor={flip ? "end" : "start"}
                  fontSize="11"
                  fill="var(--text-primary)"
                  className="font-mono"
                >
                  {currentId}
                </text>
              </g>
            );
          })()}
        </svg>

        {hovered && (
          <div
            className="pointer-events-none absolute z-10 rounded-md border border-[var(--line-strong)] bg-[var(--surface)] px-2 py-1.5 font-mono text-[11px] shadow-lg"
            style={{
              left: `${(sx(hovered.x) / W) * 100}%`,
              top: `${(sy(hovered.y) / H) * 100}%`,
              transform: "translate(-50%, -130%)",
            }}
          >
            <span className="text-[var(--text-primary)]">{hovered.id}</span>
            <span className="mx-1.5 text-[var(--text-muted)]">/</span>
            <span style={{ color: clusterColor(hovered.cluster) }}>{subgroupLabel(hovered.cluster)}</span>
            <span className="mx-1.5 text-[var(--text-muted)]">/</span>
            <span className="text-[var(--text-secondary)]">
              P = {(membership[hovered.id]?.[hovered.cluster] ?? 0).toFixed(3)}
            </span>
          </div>
        )}
      </div>

      {current && (
        <p className="mt-2 font-mono text-[11px] tabular-nums text-[var(--text-secondary)]">
          {currentId} · membership {(currentMembership * 100).toFixed(1)}% ·{" "}
          {currentWidth < 0.005
            ? "posterior width below 0.005, so the ring shows the display floor rather than a measured spread"
            : `posterior width ${currentWidth.toFixed(3)}`}
        </p>
      )}

      <ul className="mt-2 flex flex-wrap gap-x-3 gap-y-1 border-t border-[var(--line)] pt-3 text-[11px]">
        {clusters.map(([cl, pts]) => {
          const ann = annotations?.[String(cl)];
          const on = selectedClusters.includes(cl);
          return (
            <li key={cl}>
              <button
                type="button"
                aria-pressed={on}
                onClick={() => onToggleCluster(cl)}
                className="pressable inline-flex items-center gap-1.5 px-1.5 py-1"
                style={{ opacity: anySelected && !on ? 0.45 : 1 }}
              >
                <SubgroupMark cluster={cl} />
                <span className={on ? "font-semibold text-[var(--text-primary)]" : "text-[var(--text-secondary)]"}>
                  {subgroupLabel(cl)}
                </span>
                <span className="font-mono tabular-nums text-[var(--text-muted)]">n={ann?.n ?? pts.length}</span>
                {ann?.pam50_majority && <span className="text-[var(--text-muted)]">{ann.pam50_majority}</span>}
              </button>
            </li>
          );
        })}
      </ul>
      <Modal
        open={explaining}
        onClose={() => setExplaining(false)}
        title="How this space is built, and how a patient is placed in it"
        subtitle="Every step below runs before any survival data is touched."
      >
        <div className="space-y-4 text-[13px] leading-relaxed text-[var(--text-secondary)]">
          <section>
            <h3 className="text-[12px] font-semibold text-[var(--text-primary)]">1. What is measured</h3>
            <p className="mt-1">
              Bulk RNA from each tumour is deconvolved with BayesPrism against a single-cell breast
              reference, which separates the malignant epithelial signal from the immune and stromal cells
              mixed into the same sample. What remains is the tumour-intrinsic expression of{" "}
              <span className="font-mono">2,247</span> genes across{" "}
              <span className="font-mono">1,082</span> TCGA-BRCA tumours.
            </p>
          </section>

          <section>
            <h3 className="text-[12px] font-semibold text-[var(--text-primary)]">
              2. The encoder is a PCA, not the VAE
            </h3>
            <p className="mt-1">
              Worth being direct about, because the project does contain a product-of-experts VAE and this
              is not it. {encoderNote
                ? encoderNote
                : "The committed PoE-VAE was fitted on METABRIC and does not cover this cohort."}{" "}
              Using it here would mean encoding these tumours with a model that never saw them, so the
              positions on this plot come from a principal component analysis of the intrinsic expression
              instead — {" "}
              <span className="font-mono">{encoder ?? "pca_intrinsic_expression"}</span> in the payload.
            </p>
            <p className="mt-2">
              PCA finds the directions along which tumours differ most and keeps the first 16. It is fitted
              once on the whole cohort and is entirely unsupervised: it is given expression and nothing
              else — no subtype, no treatment, and no outcome.
            </p>
          </section>

          <section>
            <h3 className="text-[12px] font-semibold text-[var(--text-primary)]">
              3. How a patient gets a position
            </h3>
            <p className="mt-1">
              This patient&apos;s expression is passed through that same fitted PCA, giving 16 coordinates.
              The two shown here are the first two components, carrying{" "}
              <span className="font-mono">{variance?.[0] != null ? `${Math.round(variance[0] * 100)}%` : "—"}</span>{" "}
              and{" "}
              <span className="font-mono">{variance?.[1] != null ? `${Math.round(variance[1] * 100)}%` : "—"}</span>{" "}
              of the total variance. The remaining 14 components are used for clustering but are not drawn,
              so two points that look adjacent here can still differ along an axis you cannot see.
            </p>
          </section>

          <section>
            <h3 className="text-[12px] font-semibold text-[var(--text-primary)]">
              4. How a patient gets a subgroup
            </h3>
            <p className="mt-1">
              A Gaussian mixture ({preregistered?.method?.toUpperCase() ?? "GMM"},{" "}
              {preregistered?.covariance_type ?? "full"} covariance) is fitted to the 16-dimensional
              coordinates for every k from 2 to 8. Each fit gives every tumour a{" "}
              <em>probability</em> of belonging to each subgroup, not a hard label; the label shown is
              simply the highest of those probabilities.
            </p>
            <p className="mt-2">
              k = {preregistered?.k ?? "—"} was fixed in advance from BIC, silhouette and bootstrap
              stability{preregistered?.stability != null ? ` (stability ${preregistered.stability.toFixed(2)})` : ""} —
              none of which sees survival. That is what allows the survival panel to report a p-value at
              this k and nowhere else.
            </p>
          </section>

          <section>
            <h3 className="text-[12px] font-semibold text-[var(--text-primary)]">
              5. Reading the plot honestly
            </h3>
            <ul className="mt-1 space-y-1">
              <li>
                The dashed ring around this patient is the uncertainty in that membership probability.
                Most of this cohort has a probability above 0.999, so the ring has a floor size and is
                usually showing &ldquo;almost none&rdquo; rather than a measured spread.
              </li>
              <li>
                Overlapping clouds are the expected result. Breast tumours form a continuum; crisp islands
                would suggest the projection was manufacturing separation, which is why PCA is the default
                here and UMAP is offered only with a warning.
              </li>
              <li>
                Each subgroup has its own marker shape, so identity never depends on colour alone.
              </li>
            </ul>
          </section>
        </div>
      </Modal>
    </PanelCard>
  );
}
