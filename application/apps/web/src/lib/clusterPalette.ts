/**
 * Cluster identity: colour + shape.
 *
 * The hues are the dataviz reference steps, validated with
 * `scripts/validate_palette.js` against this app's own surfaces (#111827 dark,
 * #ffffff light). All eight slots pass the lightness band, chroma floor,
 * CVD separation, normal-vision floor and contrast checks on the adjacent
 * pairlist in both modes.
 *
 * The previous ramp did not: #9333EA and #7C3AED were two purples at ΔE 0.5
 * under protanopia, #0F766E fell below the chroma floor and read gray, and
 * #0369A1 sat under 3:1 contrast.
 *
 * Colour alone is not enough in the projection. A scatter is read with the
 * all-pairs pairlist, where no four-hue set clears the floors — so every
 * subgroup also carries a marker shape, and the shape travels with it into the
 * legend, the heatmap headers and the at-risk table.
 *
 * Values live as CSS custom properties so light and dark swap in one place;
 * `var(--cluster-N)` is a valid SVG paint.
 */

export const CLUSTER_SLOTS = 8;

export function clusterColor(index: number): string {
  return `var(--cluster-${slot(index)})`;
}

/** Faint fill for hulls and confidence bands, derived from the slot hue. */
export function clusterWash(index: number, percent = 12): string {
  return `color-mix(in oklab, var(--cluster-${slot(index)}) ${percent}%, transparent)`;
}

function slot(index: number): number {
  const i = Math.trunc(index);
  return (((i % CLUSTER_SLOTS) + CLUSTER_SLOTS) % CLUSTER_SLOTS) + 1;
}

/** Stroke dash per subgroup — a third channel for line charts. */
export function clusterStroke(index: number): string {
  return ["", "6 4", "2 3", "8 3 2 3", "1 4", "10 4", "4 2 1 2", "3 3"][index % 8];
}

export const CLUSTER_SHAPES = [
  "circle",
  "square",
  "triangle",
  "diamond",
  "plus",
  "cross",
  "star",
  "hexagon",
] as const;

export type ClusterShape = (typeof CLUSTER_SHAPES)[number];

export function clusterShape(index: number): ClusterShape {
  const i = Math.trunc(index);
  return CLUSTER_SHAPES[(((i % CLUSTER_SHAPES.length) + CLUSTER_SHAPES.length) % CLUSTER_SHAPES.length)];
}

/**
 * SVG path for a subgroup marker, centred on (0,0).
 *
 * `r` is the circumradius, so shapes are visually comparable rather than
 * equal-area — at scatter sizes an equal-area triangle reads much smaller than
 * its circle.
 */
export function clusterShapePath(shape: ClusterShape, r: number): string {
  switch (shape) {
    case "circle":
      return `M ${-r},0 a ${r},${r} 0 1,0 ${r * 2},0 a ${r},${r} 0 1,0 ${-r * 2},0 Z`;
    case "square": {
      const s = r * 0.88;
      return `M ${-s},${-s} H ${s} V ${s} H ${-s} Z`;
    }
    case "triangle": {
      const h = r * 1.15;
      return `M 0,${-h} L ${h * 0.92},${h * 0.62} L ${-h * 0.92},${h * 0.62} Z`;
    }
    case "diamond": {
      const d = r * 1.18;
      return `M 0,${-d} L ${d},0 L 0,${d} L ${-d},0 Z`;
    }
    case "plus": {
      const a = r * 1.15;
      const b = r * 0.38;
      return `M ${-b},${-a} H ${b} V ${-b} H ${a} V ${b} H ${b} V ${a} H ${-b} V ${b} H ${-a} V ${-b} H ${-b} Z`;
    }
    case "cross": {
      const a = r * 0.92;
      const b = r * 0.3;
      return [
        `M ${-a},${-a + b} L ${-a + b},${-a} L 0,${-b * 1.2} L ${a - b},${-a} L ${a},${-a + b}`,
        `L ${b * 1.2},0 L ${a},${a - b} L ${a - b},${a} L 0,${b * 1.2}`,
        `L ${-a + b},${a} L ${-a},${a - b} L ${-b * 1.2},0 Z`,
      ].join(" ");
    }
    case "star": {
      const pts: string[] = [];
      for (let i = 0; i < 10; i++) {
        const rad = i % 2 === 0 ? r * 1.25 : r * 0.52;
        const ang = (Math.PI / 5) * i - Math.PI / 2;
        pts.push(`${(Math.cos(ang) * rad).toFixed(2)},${(Math.sin(ang) * rad).toFixed(2)}`);
      }
      return `M ${pts.join(" L ")} Z`;
    }
    case "hexagon": {
      const pts: string[] = [];
      for (let i = 0; i < 6; i++) {
        const ang = (Math.PI / 3) * i - Math.PI / 2;
        pts.push(`${(Math.cos(ang) * r * 1.08).toFixed(2)},${(Math.sin(ang) * r * 1.08).toFixed(2)}`);
      }
      return `M ${pts.join(" L ")} Z`;
    }
  }
}

/**
 * Diverging colour for a signed effect.
 *
 * Blue and red: warm and cool poles that read as opposite, through a neutral
 * gray midpoint that reads as "nothing". The previous teal-to-purple scale had
 * two cool poles, so the sign of an effect was not legible.
 *
 * `maxAbs` MUST be the maximum within the feature's own family. A pathway score
 * and a gene log2FC are different units; sharing one scale meant pathways, whose
 * effects top out near 1.0, were rendered on a scale reaching 5.95 and appeared
 * blank.
 */
export function divergingEffect(value: number, maxAbs: number): string {
  const t = Math.max(-1, Math.min(1, value / (maxAbs || 1)));
  const pole = t >= 0 ? "var(--diverge-pos)" : "var(--diverge-neg)";
  const strength = Math.round(Math.abs(t) * 100);
  return `color-mix(in oklab, ${pole} ${strength}%, var(--diverge-mid))`;
}

/** CSS gradient for a diverging scale legend. */
export const DIVERGING_GRADIENT =
  "linear-gradient(90deg, var(--diverge-neg), var(--diverge-mid) 50%, var(--diverge-pos))";

export function interpolate(a: number[], b: number[], t: number): number[] {
  return a.map((v, i) => v + ((b[i] ?? v) - v) * t);
}
