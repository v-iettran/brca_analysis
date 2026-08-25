/** Categorical cluster colours, distinct from --progression / --response. */
export const CLUSTER_RAMP = [
  "#0369A1",
  "#7C3AED",
  "#0F766E",
  "#D97706",
  "#DB2777",
  "#65A30D",
  "#0891B2",
  "#9333EA",
];

export function clusterColor(index: number, _k = 8): string {
  return CLUSTER_RAMP[((index % CLUSTER_RAMP.length) + CLUSTER_RAMP.length) % CLUSTER_RAMP.length];
}

export function clusterStroke(index: number): string {
  return ["", "6 4", "2 3", "8 3 2 3", "1 4"][index % 5];
}

/** Diverging teal ↔ molecular, centred at 0. */
export function divergingEffect(value: number, maxAbs: number): string {
  const t = Math.max(-1, Math.min(1, value / (maxAbs || 1)));
  const stops = [
    [0xf, 0x76, 0x6e],
    [0x5e, 0xea, 0xd4],
    [0xf8, 0xfa, 0xfc],
    [0xc4, 0xb5, 0xfd],
    [0x7c, 0x3a, 0xed],
  ];
  const x = (t + 1) / 2;
  const scaled = x * (stops.length - 1);
  const i = Math.min(stops.length - 2, Math.floor(scaled));
  const f = scaled - i;
  const a = stops[i];
  const b = stops[i + 1];
  const rgb = a.map((c, j) => Math.round(c + (b[j] - c) * f));
  return `rgb(${rgb[0]}, ${rgb[1]}, ${rgb[2]})`;
}

export function interpolate(a: number[], b: number[], t: number): number[] {
  return a.map((v, i) => v + ((b[i] ?? v) - v) * t);
}
