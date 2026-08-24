export function clusterColor(index: number, k: number): string {
  const start = { h: 174, s: 78, l: 26 }; // teal #0F766E
  const end = { h: 258, s: 70, l: 50 }; // molecular #7C3AED
  const t = k <= 1 ? 0 : index / Math.max(k - 1, 1);
  const h = start.h + (end.h - start.h) * t;
  const s = start.s + (end.s - start.s) * t;
  const l = start.l + (end.l - start.l) * t;
  return `hsl(${h} ${s}% ${l}%)`;
}

export function interpolate(a: number[], b: number[], t: number): number[] {
  return a.map((v, i) => v + ((b[i] ?? v) - v) * t);
}
