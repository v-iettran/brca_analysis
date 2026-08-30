import { clusterColor, clusterShape, clusterShapePath } from "@/lib/clusterPalette";

/**
 * One subgroup's identity swatch: shape plus colour.
 *
 * Used in every legend, column header and table row so a subgroup looks the
 * same wherever it appears. Shape is what carries identity when hue cannot —
 * in the projection scatter, and for any reader with a colour vision
 * deficiency.
 */
export function SubgroupMark({
  cluster,
  size = 11,
  filled = true,
}: {
  cluster: number;
  size?: number;
  filled?: boolean;
}) {
  const r = size / 2;
  const color = clusterColor(cluster);
  return (
    <svg
      width={size}
      height={size}
      viewBox={`${-r - 1} ${-r - 1} ${size + 2} ${size + 2}`}
      className="shrink-0"
      aria-hidden
      focusable="false"
    >
      <path
        d={clusterShapePath(clusterShape(cluster), r * 0.86)}
        fill={filled ? color : "none"}
        stroke={color}
        strokeWidth={filled ? 0 : 1.6}
      />
    </svg>
  );
}
