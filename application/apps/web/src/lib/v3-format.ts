export function formatQ(q: number | null | undefined): string {
  if (q == null || Number.isNaN(q)) return "—";
  if (q < 0.001) return "<0.001";
  if (q < 0.01) return q.toFixed(3);
  return q.toFixed(3);
}

export function formatP(p: number | null | undefined): string {
  if (p == null || Number.isNaN(p)) return "—";
  if (p < 0.001) return "<0.001";
  return p.toFixed(3);
}

export function subgroupLabel(cluster: number): string {
  return `Subgroup ${cluster + 1}`;
}

export function populatedEntries(record: Record<string, unknown> | null | undefined): {
  filled: Array<[string, string]>;
  empty: string[];
} {
  const filled: Array<[string, string]> = [];
  const empty: string[] = [];
  for (const [key, value] of Object.entries(record || {})) {
    const text = value == null ? "" : String(value).trim();
    if (!text || ["nan", "none", "n/a", "not recorded", "[not available]", "[unknown]"].includes(text.toLowerCase())) {
      empty.push(key);
    } else {
      filled.push([key.replace(/_/g, " "), text]);
    }
  }
  return { filled, empty };
}
