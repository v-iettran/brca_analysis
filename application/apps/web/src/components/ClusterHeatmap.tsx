"use client";

import { Fragment, useMemo, useState } from "react";
import { DIVERGING_GRADIENT, clusterColor, divergingEffect } from "@/lib/clusterPalette";
import { formatQ, subgroupLabel } from "@/lib/v3-format";
import type { FeatureTier, V3CohortPayload } from "@/lib/v3-types";
import { PanelCard } from "@/components/PanelCard";
import { SubgroupMark } from "@/components/SubgroupMark";
import { Modal } from "@/components/Modal";
import { LiteratureCitations } from "@/components/LiteratureCitations";

const FAMILIES = [
  { key: "pathway", label: "Pathways", unit: "PROGENy activity, one-vs-rest" },
  { key: "tf", label: "Transcription factors", unit: "CollecTRI activity, one-vs-rest" },
  { key: "gene", label: "Genes", unit: "log2 fold change, one-vs-rest" },
] as const;

type FamilyKey = (typeof FAMILIES)[number]["key"];

const PREVIEW_ROWS: Record<FamilyKey, number> = { pathway: 14, tf: 10, gene: 12 };

// A 2,247-row table is slower to paint than it is useful; the search box is the
// way to reach anything past the strongest few hundred.
const MODAL_ROWS = 300;

// Below this, a subgroup mean is too easily moved by one sample to share a
// colour scale with the others.
const MIN_STABLE_N = 30;

// The tier is a curated literature claim, shown as glyph plus word so it never
// depends on colour and never reads as a statement about this cohort.
const TIERS: Array<{ key: FeatureTier; label: string; mark: string }> = [
  { key: "established", label: "Established role", mark: "\u25cf" },
  { key: "investigational", label: "Emerging evidence", mark: "\u25d0" },
  { key: "not_established", label: "No curated role", mark: "\u25cb" },
];

type Cell = { effect: number; q: number; log2fc?: number };
type Row = {
  feature: string;
  family: FamilyKey;
  cells: Record<number, Cell>;
  peak: number;
  tier: FeatureTier;
  source?: string | null;
};

/**
 * A matrix, because comparing across subgroups is the actual task and a matrix
 * is the only layout where every subgroup is visible at once.
 *
 * Two rules this panel exists to respect:
 *
 * 1. Each family is scaled against its own maximum. A PROGENy activity score
 *    tops out near |1.0| while a gene log2FC reaches |6|; on one shared scale
 *    every pathway row rendered as blank white. They are different units, so a
 *    single legend would be a lie even if it were legible.
 * 2. Selecting a subgroup never changes a cell's colour or opacity. Opacity
 *    means one thing here — q >= 0.05 — and dimming unselected columns on top of
 *    it corrupted both the effect size and the significance channel. Selection
 *    is shown on the column header instead.
 */
export function ClusterHeatmap({
  runId,
  cohort,
  selectedClusters,
  onToggleCluster,
  onClearClusters,
  takeaway,
}: {
  runId: string;
  cohort: V3CohortPayload;
  selectedClusters: number[];
  onToggleCluster: (cluster: number) => void;
  onClearClusters: () => void;
  takeaway?: string;
}) {
  const [shown, setShown] = useState<Record<FamilyKey, boolean>>({ pathway: true, tf: true, gene: true });
  const [tierFilter, setTierFilter] = useState<FeatureTier | null>(null);
  const [openFeature, setOpenFeature] = useState<string | null>(null);
  const [fullList, setFullList] = useState<FamilyKey | null>(null);
  const [search, setSearch] = useState("");
  const [sortCluster, setSortCluster] = useState<number | null>(null);
  const [direction, setDirection] = useState<"up" | "down" | null>(null);

  const { byFamily, clusters, familyMax } = useMemo(() => {
    const profiles = (cohort.cluster_profiles ?? []) as Array<Record<string, unknown>>;
    const seen = new Set<number>();
    const rows = new Map<string, Row>();
    for (const p of profiles) {
      const family = String(p.family) as FamilyKey;
      if (!PREVIEW_ROWS[family]) continue;
      const cluster = Number(p.cluster);
      seen.add(cluster);
      const key = `${family}::${String(p.feature)}`;
      let row = rows.get(key);
      if (!row) {
        row = {
          feature: String(p.feature),
          family,
          cells: {},
          peak: 0,
          tier: (p.evidence_tier as FeatureTier) ?? "not_established",
          source: (p.evidence_source as string) ?? null,
        };
        rows.set(key, row);
      }
      const effect = Number(p.effect) || 0;
      row.cells[cluster] = {
        effect,
        q: Number(p.q ?? 1),
        log2fc: p.log2fc == null ? undefined : Number(p.log2fc),
      };
      row.peak = Math.max(row.peak, Math.abs(effect));
    }

    const grouped: Record<FamilyKey, Row[]> = { pathway: [], tf: [], gene: [] };
    for (const row of rows.values()) grouped[row.family].push(row);
    // Rank within the family, never globally.
    for (const key of Object.keys(grouped) as FamilyKey[]) {
      grouped[key].sort((a, b) => b.peak - a.peak);
    }
    // Set each family's colour range from subgroups large enough for a mean to
    // be stable. Measured on this cohort: every one of the 449 gene cells beyond
    // the 95th percentile belongs to subgroup 4, which has 13 members — so even
    // a percentile scale was still being set by it, and the other three columns
    // stayed pale. Cells beyond the range are clamped and drawn dashed, which
    // marks the small subgroup as off-scale rather than letting it flatten
    // everything else.
    const stable = new Set(
      Object.values(cohort.cluster_annotations ?? {})
        .filter((a) => (a?.n ?? 0) >= MIN_STABLE_N)
        .map((a) => a.cluster)
    );
    const max: Record<FamilyKey, number> = { pathway: 0.01, tf: 0.01, gene: 0.01 };
    for (const key of Object.keys(grouped) as FamilyKey[]) {
      const pick = (only: boolean) =>
        grouped[key]
          .flatMap((r) =>
            Object.entries(r.cells)
              .filter(([cl]) => !only || stable.has(Number(cl)))
              .map(([, c]) => Math.abs(c.effect))
          )
          .sort((a, b) => a - b);
      let values = pick(true);
      if (values.length < 20) values = pick(false);
      max[key] = Math.max(0.01, values[Math.floor(values.length * 0.98)] ?? 0);
    }

    return { byFamily: grouped, clusters: [...seen].sort((a, b) => a - b), familyMax: max };
  }, [cohort.cluster_profiles, cohort.cluster_annotations]);

  const [seenList, setSeenList] = useState<FamilyKey | null>(null);
  if (seenList !== fullList) {
    setSeenList(fullList);
    setSearch("");
    setSortCluster(null);
    setDirection(null);
  }

  const annotations = cohort.cluster_annotations;
  const reliability = useMemo(
    () => Object.fromEntries((cohort.tf_reliability ?? []).map((r) => [r.tf, r])),
    [cohort.tf_reliability]
  );

  const visibleFamilies = FAMILIES.filter((f) => shown[f.key]);
  const filtered = (family: FamilyKey) =>
    tierFilter ? byFamily[family].filter((r) => r.tier === tierFilter) : byFamily[family];
  const searched = (family: FamilyKey) => {
    const needle = search.trim().toLowerCase();
    let rows = filtered(family);
    if (needle) rows = rows.filter((r) => r.feature.toLowerCase().includes(needle));
    if (sortCluster == null) return rows;

    // Ranked within one subgroup, in one direction: "what is most up in
    // subgroup 2" is a different question from "what varies most overall", and
    // only the first is answerable from a magnitude ranking.
    const effectOf = (r: Row) => r.cells[sortCluster]?.effect ?? 0;
    const picked = direction
      ? rows.filter((r) => (direction === "up" ? effectOf(r) > 0 : effectOf(r) < 0))
      : rows;
    return [...picked].sort((a, b) =>
      direction === "down" ? effectOf(a) - effectOf(b) : effectOf(b) - effectOf(a)
    );
  };
  const tierCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const family of Object.keys(byFamily) as FamilyKey[]) {
      for (const row of byFamily[family]) counts[row.tier] = (counts[row.tier] ?? 0) + 1;
    }
    return counts;
  }, [byFamily]);
  const totalFeatures = Object.values(byFamily).reduce((n, rows) => n + rows.length, 0);

  return (
    <PanelCard
      id="characteristics"
      eyebrow="Cluster characteristics"
      title="Compare every subgroup at once"
      takeaway={takeaway}
      display={totalFeatures}
      displayCaption="features analysed"
      bare
      footnote={`Each family has its own colour range, set from subgroups of at least 30 tumours — a pathway score and a gene log2 fold change are different units, and a subgroup too small for a stable mean would otherwise set the range for every column. Dashed cells exceed that range and are drawn at full saturation. Cells at q ≥ 0.05 are shown at 20% opacity. One-vs-rest per subgroup, Benjamini-Hochberg adjusted. Source: TCGA-BRCA. ${cohort.evidence_reference?.caveat ?? ""}`}
    >
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <div className="seg">
          {FAMILIES.map((f) => (
            <button
              key={f.key}
              type="button"
              data-active={shown[f.key]}
              aria-pressed={shown[f.key]}
              onClick={() => setShown((prev) => ({ ...prev, [f.key]: !prev[f.key] }))}
            >
              {f.label} <span className="font-mono tabular-nums opacity-60">{byFamily[f.key].length}</span>
            </button>
          ))}
        </div>
        <div className="seg">
          {TIERS.map((t) => (
            <button
              key={t.key}
              type="button"
              data-active={tierFilter === t.key}
              aria-pressed={tierFilter === t.key}
              aria-label={`Filter to ${t.label}`}
              onClick={() => setTierFilter((prev) => (prev === t.key ? null : t.key))}
              title={cohort.evidence_reference?.tiers?.[t.key]}
            >
              <span aria-hidden className="mr-1">
                {t.mark}
              </span>
              {t.label} <span className="font-mono tabular-nums opacity-60">{tierCounts[t.key] ?? 0}</span>
            </button>
          ))}
        </div>

        {selectedClusters.length > 0 && (
          <button
            type="button"
            onClick={onClearClusters}
            className="pressable border border-[var(--line-strong)] px-2 py-1 text-[11px] text-[var(--text-secondary)]"
          >
            Clear subgroup filter
          </button>
        )}
      </div>

      {selectedClusters.map((cl) =>
        annotations?.[String(cl)] ? (
          <SubgroupSummary
            key={cl}
            cluster={cl}
            annotation={annotations[String(cl)]}
            rows={byFamily.pathway}
            max={familyMax.pathway}
          />
        ) : null
      )}

      <div className="overflow-x-auto">
        <table className="w-full border-separate border-spacing-0 text-[11.5px]">
          <caption className="sr-only">Signed effect size per feature per subgroup</caption>
          <thead>
            <tr>
              <th
                scope="col"
                className="sticky left-0 z-10 bg-[var(--surface)] pb-2 text-left font-medium text-[var(--text-muted)]"
              >
                feature
              </th>
              {clusters.map((cl) => {
                const ann = annotations?.[String(cl)];
                const active = selectedClusters.includes(cl);
                return (
                  <th key={cl} scope="col" className="px-0.5 pb-2 align-bottom">
                    {/* Selection lives on the header, never on the data cells. */}
                    <button
                      type="button"
                      aria-pressed={active}
                      onClick={() => onToggleCluster(cl)}
                      className="pressable flex w-full flex-col items-center gap-0.5 px-1.5 py-1"
                      style={
                        active
                          ? {
                              background: `color-mix(in oklab, ${clusterColor(cl)} 14%, transparent)`,
                              boxShadow: `inset 0 0 0 1px ${clusterColor(cl)}`,
                            }
                          : undefined
                      }
                    >
                      <span className="inline-flex items-center gap-1.5">
                        <SubgroupMark cluster={cl} />
                        <span
                          className="font-mono text-[11px]"
                          style={{ color: active ? "var(--text-primary)" : "var(--text-secondary)" }}
                        >
                          {subgroupLabel(cl)}
                        </span>
                      </span>
                      <span className="font-mono text-[9.5px] tabular-nums text-[var(--text-muted)]">
                        n={ann?.n ?? "—"} {ann?.pam50_majority ?? ""}
                      </span>
                    </button>
                  </th>
                );
              })}
            </tr>
          </thead>

          <tbody>
            {visibleFamilies.map((family) => {
              const all = filtered(family.key);
              const rows = all.slice(0, PREVIEW_ROWS[family.key]);
              const max = familyMax[family.key];
              return (
                <Fragment key={family.key}>
                  <tr>
                    <td colSpan={1 + clusters.length} className="pb-1.5 pt-4">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <span className="eyebrow">
                          {family.label} <span className="font-mono">({all.length})</span>
                        </span>
                        {/* Each family carries its own scale legend, because each
                            has its own units and its own maximum. */}
                        <span className="flex items-center gap-1.5 text-[10px] text-[var(--text-muted)]">
                          <span className="font-mono tabular-nums">−{max.toFixed(2)}</span>
                          <span
                            className="h-2 w-20 rounded-full border border-[var(--line)]"
                            style={{ background: DIVERGING_GRADIENT }}
                          />
                          <span className="font-mono tabular-nums">+{max.toFixed(2)}</span>
                          <span className="hidden sm:inline">{family.unit}</span>
                        </span>
                      </div>
                    </td>
                  </tr>

                  {rows.map((row) => (
                    <HeatmapRow
                      key={`${family.key}::${row.feature}`}
                      runId={runId}
                      row={row}
                      clusters={clusters}
                      max={max}
                      unit={family.unit}
                      open={openFeature === `${family.key}::${row.feature}`}
                      onToggle={() =>
                        setOpenFeature((prev) =>
                          prev === `${family.key}::${row.feature}` ? null : `${family.key}::${row.feature}`
                        )
                      }
                      reliability={family.key === "tf" ? reliability[row.feature] : undefined}
                    />
                  ))}

                  {all.length > PREVIEW_ROWS[family.key] && (
                    <tr>
                      <td colSpan={1 + clusters.length} className="pt-1.5">
                        {/* The full list opens in a dialog. A 60-row table inside
                            the panel pushes every other panel off the screen. */}
                        <button
                          type="button"
                          onClick={() => setFullList(family.key)}
                          className="pressable border border-[var(--line-strong)] px-2.5 py-1 text-[11px] font-medium text-[var(--text-secondary)]"
                        >
                          View all {all.length} {family.label.toLowerCase()} →
                        </button>
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>

      <Modal
        open={fullList != null}
        onClose={() => setFullList(null)}
        size="lg"
        title={fullList ? FAMILIES.find((f) => f.key === fullList)!.label : ""}
        subtitle={
          fullList
            ? `All ${filtered(fullList).length}, ranked by strongest effect across subgroups. ${FAMILIES.find((f) => f.key === fullList)!.unit}. Click a row for per-subgroup detail.`
            : undefined
        }
      >
        {fullList && (
          <>
            <div className="sticky top-0 z-20 mb-2 flex flex-wrap items-center gap-2 bg-[var(--surface)] pb-2">
              <input
                type="search"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder={`Search ${filtered(fullList).length} ${FAMILIES.find((f) => f.key === fullList)!.label.toLowerCase()} by name`}
                aria-label="Search features"
                className="min-w-[16rem] flex-1 rounded-[var(--radius-inner)] border border-[var(--line)] bg-[var(--surface)] px-2.5 py-1.5 text-[12px] text-[var(--text-primary)] placeholder:text-[var(--text-muted)]"
              />
              <div className="seg">
                {TIERS.map((t) => (
                  <button
                    key={t.key}
                    type="button"
                    data-active={tierFilter === t.key}
                    aria-pressed={tierFilter === t.key}
                    aria-label={`Filter list to ${t.label}`}
                    onClick={() => setTierFilter((prev) => (prev === t.key ? null : t.key))}
                  >
                    <span aria-hidden className="mr-1">
                      {t.mark}
                    </span>
                    {t.label}
                  </button>
                ))}
              </div>

              <div className="flex w-full flex-wrap items-center gap-2">
                <span className="text-[11px] text-[var(--text-muted)]">Rank within</span>
                <div className="seg">
                  {clusters.map((cl) => (
                    <button
                      key={cl}
                      type="button"
                      data-active={sortCluster === cl}
                      aria-pressed={sortCluster === cl}
                      aria-label={`Rank by ${subgroupLabel(cl)}`}
                      onClick={() => setSortCluster((prev) => (prev === cl ? null : cl))}
                    >
                      {subgroupLabel(cl)}
                    </button>
                  ))}
                </div>
                <div className="seg">
                  {([
                    ["up", "Most raised"],
                    ["down", "Most reduced"],
                  ] as const).map(([key, label]) => (
                    <button
                      key={key}
                      type="button"
                      disabled={sortCluster == null}
                      data-active={direction === key}
                      aria-pressed={direction === key}
                      aria-label={label}
                      onClick={() => setDirection((prev) => (prev === key ? null : key))}
                      className="disabled:opacity-40"
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </div>
            </div>
            {(() => {
              const all = searched(fullList);
              const shown = all.slice(0, MODAL_ROWS);
              return (
                <>
                  {all.length > MODAL_ROWS && (
                    <p className="mb-2 text-[11px] text-[var(--text-muted)]">
                      Showing {MODAL_ROWS} of {all.length}
                      {sortCluster != null
                        ? `, ranked by ${direction === "down" ? "most reduced" : "most raised"} in ${subgroupLabel(sortCluster)}`
                        : ", ranked by strongest effect in any subgroup"}
                      . Search by name to reach the rest.
                    </p>
                  )}
                  {all.length === 0 && (
                    <p className="py-6 text-center text-[12px] text-[var(--text-muted)]">
                      Nothing matches that search.
                    </p>
                  )}
          <table className="w-full border-separate border-spacing-0 text-[11.5px]">
            <thead>
              <tr>
                <th scope="col" className="pb-2 text-left font-medium text-[var(--text-muted)]">
                  feature
                </th>
                {clusters.map((cl) => (
                  <th key={cl} scope="col" className="px-0.5 pb-2">
                    <span className="inline-flex items-center gap-1.5">
                      <SubgroupMark cluster={cl} />
                      <span className="font-mono text-[11px] text-[var(--text-secondary)]">
                        {subgroupLabel(cl)}
                      </span>
                    </span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {shown.map((row) => (
                <HeatmapRow
                  key={row.feature}
                  runId={runId}
                  row={row}
                  clusters={clusters}
                  max={familyMax[fullList]}
                  unit={FAMILIES.find((f) => f.key === fullList)!.unit}
                  open={openFeature === `modal::${row.feature}`}
                  onToggle={() =>
                    setOpenFeature((prev) => (prev === `modal::${row.feature}` ? null : `modal::${row.feature}`))
                  }
                  reliability={fullList === "tf" ? reliability[row.feature] : undefined}
                />
              ))}
            </tbody>
          </table>
                </>
              );
            })()}
          </>
        )}
      </Modal>
    </PanelCard>
  );
}

function TierChip({ tier, source }: { tier: FeatureTier; source?: string | null }) {
  const meta = TIERS.find((t) => t.key === tier) ?? TIERS[2];
  return (
    <span
      className="shrink-0 text-[10px] text-[var(--text-muted)]"
      title={source ? `${meta.label} — ${source}` : meta.label}
      aria-hidden
    >
      {meta.mark}
    </span>
  );
}

function HeatmapRow({
  runId,
  row,
  clusters,
  max,
  unit,
  open,
  onToggle,
  reliability,
}: {
  runId: string;
  row: Row;
  clusters: number[];
  max: number;
  unit: string;
  open: boolean;
  onToggle: () => void;
  reliability?: { reliability: string; reliability_reason?: string };
}) {
  return (
    <>
      <tr>
        <td className="sticky left-0 z-10 bg-[var(--surface)] py-[3px] pr-3">
          <button
            type="button"
            aria-expanded={open}
            aria-label={`${row.feature} — ${(TIERS.find((t) => t.key === row.tier) ?? TIERS[2]).label}`}
            onClick={onToggle}
            className="pressable flex w-full items-center gap-1.5 px-1 py-0.5 text-left font-mono"
            style={{ color: open ? "var(--text-primary)" : "var(--text-secondary)" }}
          >
            <span className="text-[8px] text-[var(--text-muted)]">{open ? "▾" : "▸"}</span>
            <TierChip tier={row.tier} source={row.source} />
            <span className="truncate">{row.feature}</span>
          </button>
        </td>
        {clusters.map((cl) => {
          const cell = row.cells[cl];
          const significant = cell != null && cell.q < 0.05;
          const clamped = cell != null && Math.abs(cell.effect) > max;
          return (
            <td key={cl} className="p-[2px]">
              <div
                className="h-[18px] rounded-[3px] border"
                style={{
                  background: cell ? divergingEffect(cell.effect, max) : "transparent",
                  opacity: significant ? 1 : 0.2,
                  borderColor: clamped ? "var(--text-primary)" : "var(--line)",
                  borderStyle: clamped ? "dashed" : "solid",
                }}
                title={
                  cell
                    ? `${row.feature} · ${subgroupLabel(cl)} · effect ${cell.effect > 0 ? "+" : ""}${cell.effect.toFixed(2)} · q ${formatQ(cell.q)}${clamped ? " · beyond the colour range, shown at full saturation" : ""}`
                    : undefined
                }
              />
            </td>
          );
        })}
      </tr>
      {open && (
        <tr>
          <td colSpan={1 + clusters.length} className="pb-2">
            <FeatureDetail runId={runId} row={row} clusters={clusters} max={max} unit={unit} reliability={reliability} />
          </td>
        </tr>
      )}
    </>
  );
}

/** Absorbs the old right-hand drawer: subgroup detail, inline, above the matrix. */
function SubgroupSummary({
  cluster,
  annotation,
  rows,
  max,
}: {
  cluster: number;
  annotation: NonNullable<V3CohortPayload["cluster_annotations"]>[string];
  rows: Row[];
  max: number;
}) {
  const top = rows
    .map((r) => ({ feature: r.feature, ...(r.cells[cluster] ?? { effect: 0, q: 1 }) }))
    .filter((r) => r.q < 0.05)
    .sort((a, b) => Math.abs(b.effect) - Math.abs(a.effect))
    .slice(0, 5);

  return (
    <div
      className="mb-3 rounded-[var(--radius-inner)] border p-3"
      style={{
        borderColor: clusterColor(cluster),
        background: `color-mix(in oklab, ${clusterColor(cluster)} 7%, transparent)`,
      }}
    >
      <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
        <span className="inline-flex items-center gap-1.5 text-[13px] font-semibold">
          <SubgroupMark cluster={cluster} size={12} />
          {subgroupLabel(cluster)}
        </span>
        <span className="font-mono text-[11px] tabular-nums text-[var(--text-secondary)]">
          n={annotation.n}
        </span>
        {annotation.pam50_majority && (
          <span className="text-[11px] text-[var(--text-secondary)]">
            PAM50 majority {annotation.pam50_majority}
          </span>
        )}
        <span className="font-mono text-[11px] tabular-nums text-[var(--text-muted)]">
          ESR1 {annotation.esr1_mean.toFixed(2)} · ERBB2 {annotation.erbb2_mean.toFixed(2)} · proliferation{" "}
          {annotation.prolif_mean.toFixed(2)}
        </span>
      </div>

      {top.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[11px]">
          <span className="text-[var(--text-muted)]">Defining pathways</span>
          {top.map((t) => (
            <span key={t.feature} className="font-mono text-[var(--text-secondary)]">
              {t.effect > 0 ? "↑" : "↓"} {t.feature}
              <span className="ml-1 text-[var(--text-muted)]">q {formatQ(t.q)}</span>
            </span>
          ))}
        </div>
      )}
      <p className="mt-2 text-[10.5px] text-[var(--text-muted)]">
        Effects are one-vs-rest within this cohort, on a scale reaching {max.toFixed(2)}. The
        cluster-versus-normal comparison uses adjacent normal tissue, which is scarce and can carry field
        effects from neighbouring tumour.
      </p>
    </div>
  );
}

function FeatureDetail({
  runId,
  row,
  clusters,
  max,
  unit,
  reliability,
}: {
  runId: string;
  row: Row;
  clusters: number[];
  max: number;
  unit: string;
  reliability?: { reliability: string; reliability_reason?: string };
}) {
  return (
    <div className="rounded-[var(--radius-inner)] border border-[var(--line)] bg-[var(--well)] p-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <span className="font-mono text-[12px] font-semibold text-[var(--text-primary)]">{row.feature}</span>
        <span className="text-[10.5px] text-[var(--text-muted)]">{unit}</span>
      </div>

      {/* Literature standing, kept visibly separate from this cohort's numbers. */}
      <p className="mt-1 text-[11px] text-[var(--text-secondary)]">
        <span aria-hidden className="mr-1">
          {(TIERS.find((t) => t.key === row.tier) ?? TIERS[2]).mark}
        </span>
        <span className="font-medium">{(TIERS.find((t) => t.key === row.tier) ?? TIERS[2]).label}</span>
        {row.source ? <span className="text-[var(--text-muted)]"> — {row.source}</span> : null}
      </p>

      <ul className="mt-2 space-y-1">
        {clusters.map((cl) => {
          const cell = row.cells[cl];
          if (!cell) return null;
          const overflows = Math.abs(cell.effect) > max;
          const width = Math.min(50, (Math.abs(cell.effect) / max) * 50);
          return (
            <li key={cl} className="flex items-center gap-2 text-[11px]">
              <span className="inline-flex w-24 shrink-0 items-center gap-1.5">
                <SubgroupMark cluster={cl} size={9} />
                <span className="text-[var(--text-secondary)]">{subgroupLabel(cl)}</span>
              </span>
              <span className="relative h-2 min-w-0 flex-1 rounded-full bg-[var(--line)]">
                <span
                  className="absolute inset-y-0 rounded-full"
                  style={{
                    width: `${width}%`,
                    left: cell.effect >= 0 ? "50%" : undefined,
                    right: cell.effect >= 0 ? undefined : "50%",
                    background: cell.effect >= 0 ? "var(--diverge-pos)" : "var(--diverge-neg)",
                    opacity: cell.q < 0.05 ? 1 : 0.35,
                  }}
                />
                {overflows && (
                  <span
                    className="absolute top-1/2 -translate-y-1/2 font-mono text-[9px] text-[var(--text-muted)]"
                    style={{ [cell.effect >= 0 ? "right" : "left"]: "2px" } as React.CSSProperties}
                    title={`Beyond the colour range for this family (${max.toFixed(2)})`}
                  >
                    {cell.effect >= 0 ? "▸" : "◂"}
                  </span>
                )}
                <span className="absolute inset-y-0 left-1/2 w-px bg-[var(--line-strong)]" />
              </span>
              <span className="w-14 shrink-0 text-right font-mono tabular-nums text-[var(--text-secondary)]">
                {cell.effect > 0 ? "+" : ""}
                {cell.effect.toFixed(2)}
              </span>
              <span className="w-16 shrink-0 text-right font-mono tabular-nums text-[var(--text-muted)]">
                q {formatQ(cell.q)}
              </span>
            </li>
          );
        })}
      </ul>

      {reliability && (
        <p className="mt-2 border-t border-[var(--line)] pt-2 text-[10.5px] text-[var(--text-muted)]">
          Regulon reliability: <span className="font-medium">{reliability.reliability}</span>
          {reliability.reliability_reason ? ` — ${reliability.reliability_reason}` : ""}
        </p>
      )}

      <div className="mt-2 border-t border-[var(--line)] pt-2">
        <p className="eyebrow mb-1.5">Sources</p>
        <LiteratureCitations runId={runId} subject={row.feature} kind="feature" clusterId={clusters[0] ?? 0} />
      </div>
    </div>
  );
}
