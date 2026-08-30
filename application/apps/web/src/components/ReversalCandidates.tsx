"use client";

import { useMemo, useState } from "react";
import type { EvidenceTier, V3PatientPayload } from "@/lib/v3-types";
import { Modal } from "@/components/Modal";
import { LiteratureCitations } from "@/components/LiteratureCitations";
import { termDetail, termLabel } from "@/lib/v3-vocabulary";

type Member = NonNullable<V3PatientPayload["reversal_candidates"]>["members"][number];

const TIERS: Array<{ key: EvidenceTier; label: string; note: string }> = [
  { key: "standard_of_care", label: "Breast standard of care", note: "Already used to treat breast cancer." },
  { key: "investigational", label: "Under investigation", note: "In trials, or approved for another disease." },
  { key: "not_human", label: "Not usable in humans", note: "Preclinical tools and withdrawn drugs." },
  { key: "unresolved", label: "Not classified", note: "No development status found. Never assumed." },
];

/**
 * Fifty compounds, screenable.
 *
 * As a wall of name-only chips there was nothing to screen on: every decision
 * needed a lookup elsewhere. Each row now carries the target and mechanism a
 * reader actually filters by, and the name opens what is known about the drug.
 */
export function ReversalCandidates({
  runId,
  reversal,
}: {
  runId: string;
  reversal: NonNullable<V3PatientPayload["reversal_candidates"]>;
}) {
  const [query, setQuery] = useState("");
  const [tier, setTier] = useState<EvidenceTier | null>(null);
  const [openDrug, setOpenDrug] = useState<Member | null>(null);

  const counts = useMemo(() => {
    const out: Record<string, number> = {};
    for (const m of reversal.members) {
      const key = m.evidence_tier ?? "unresolved";
      out[key] = (out[key] ?? 0) + 1;
    }
    return out;
  }, [reversal.members]);

  const rows = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return reversal.members
      .filter((m) => (tier ? (m.evidence_tier ?? "unresolved") === tier : true))
      .filter((m) =>
        needle
          ? [m.canonical, m.drug, m.target, m.moa].some((v) => String(v ?? "").toLowerCase().includes(needle))
          : true
      )
      .sort((a, b) => {
        const order = TIERS.findIndex((t) => t.key === (a.evidence_tier ?? "unresolved"));
        const otherOrder = TIERS.findIndex((t) => t.key === (b.evidence_tier ?? "unresolved"));
        if (order !== otherOrder) return order - otherOrder;
        return (a.canonical || a.drug).localeCompare(b.canonical || b.drug);
      });
  }, [reversal.members, query, tier]);

  return (
    <div className="rounded-[var(--radius-inner)] border border-[var(--line)] p-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="eyebrow">
          Reversal candidates <span className="font-mono">({reversal.members.length})</span>
        </p>
        <p className="font-mono text-[10.5px] text-[var(--text-muted)]">
          <span title={termDetail(reversal.source)}>{termLabel(reversal.source)}</span> ·{" "}
          {reversal.validated ? "validated" : "not validated"}
        </p>
      </div>

      <div className="mt-2.5 flex flex-wrap items-center gap-2">
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Filter by name, target or mechanism"
          aria-label="Filter reversal candidates"
          className="min-w-[14rem] flex-1 rounded-[var(--radius-inner)] border border-[var(--line)] bg-[var(--surface)] px-2.5 py-1.5 text-[12px] text-[var(--text-primary)] placeholder:text-[var(--text-muted)]"
        />
        <div className="seg">
          {TIERS.map((t) => (
            <button
              key={t.key}
              type="button"
              data-active={tier === t.key}
              aria-pressed={tier === t.key}
              aria-label={`Show only ${t.label}`}
              title={t.note}
              onClick={() => setTier((prev) => (prev === t.key ? null : t.key))}
            >
              {t.label} <span className="font-mono tabular-nums opacity-60">{counts[t.key] ?? 0}</span>
            </button>
          ))}
        </div>
      </div>

      <div className="mt-2.5 max-h-80 overflow-y-auto">
        <table className="w-full text-[11.5px]">
          <caption className="sr-only">Reversal candidates with development status, target and mechanism</caption>
          <thead className="sticky top-0 bg-[var(--surface)]">
            <tr className="text-[var(--text-muted)]">
              <th scope="col" className="py-1 text-left font-medium">compound</th>
              <th scope="col" className="py-1 text-left font-medium">target</th>
              <th scope="col" className="py-1 text-left font-medium">mechanism</th>
              <th scope="col" className="py-1 text-left font-medium">status</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.drug} className="border-t border-[var(--line)] align-top">
                <td className="py-1 pr-2">
                  <button
                    type="button"
                    onClick={() => setOpenDrug(row)}
                    className="pressable px-1 py-0.5 text-left font-mono text-[var(--text-primary)] underline decoration-[var(--line-strong)] underline-offset-2"
                  >
                    {row.canonical || row.drug}
                  </button>
                </td>
                <td className="py-1 pr-2 font-mono text-[var(--text-secondary)]">
                  {row.target ? row.target.split(";").slice(0, 2).join(", ") : "—"}
                </td>
                <td className="py-1 pr-2 text-[var(--text-secondary)]">{row.moa || "—"}</td>
                <td className="py-1 text-[var(--text-muted)]">
                  {row.evidence_label ?? TIERS.find((t) => t.key === row.evidence_tier)?.label ?? "—"}
                </td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={4} className="py-3 text-center text-[var(--text-muted)]">
                  No compound matches that filter.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <p className="mt-2 text-[10.5px] text-[var(--text-muted)]">
        Grouped by development status, alphabetical within each group. These are unvalidated connectivity
        hits, so their order carries no meaning. Compounds are shown as evidence, not as recommendations.
      </p>

      <Modal
        open={openDrug != null}
        onClose={() => setOpenDrug(null)}
        title={openDrug ? openDrug.canonical || openDrug.drug : ""}
        subtitle={openDrug?.evidence_label}
      >
        {openDrug && (
          <div className="space-y-4 text-[13px] leading-relaxed text-[var(--text-secondary)]">
            <dl className="grid grid-cols-2 gap-x-4 gap-y-2.5">
              {[
                ["Development status", openDrug.evidence_label ?? "—"],
                ["Highest phase reached", openDrug.max_phase ?? "not recorded"],
                ["Target", openDrug.target ?? "not recorded"],
                ["Mechanism", openDrug.moa ?? "not recorded"],
                ["Approved for", openDrug.approved_indication ?? "not approved, or not recorded"],
                [
                  "Signatures scored",
                  openDrug.n_signatures != null ? `${openDrug.n_signatures} LINCS signatures` : "—",
                ],
              ].map(([label, value]) => (
                <div key={label}>
                  <dt className="eyebrow">{label}</dt>
                  <dd className="mt-0.5 text-[12.5px] text-[var(--text-primary)]">{value}</dd>
                </div>
              ))}
            </dl>

            {openDrug.evidence_reason && (
              <p className="rounded-[var(--radius-inner)] border border-[var(--line)] bg-[var(--well)] p-2.5 text-[12px]">
                {openDrug.evidence_reason}
              </p>
            )}

            <section>
              <h3 className="text-[12px] font-semibold text-[var(--text-primary)]">
                Why it appears here
              </h3>
              <p className="mt-1">
                Its LINCS expression signature is anti-correlated with how this subgroup differs from
                normal breast tissue, with a median reversal score of{" "}
                <span className="font-mono">{openDrug.reversal_score?.toFixed(3) ?? "—"}</span> across{" "}
                {openDrug.n_signatures ?? "several"} signatures. That is a hypothesis about direction of
                effect on gene expression. It is not evidence that the compound shrinks a tumour, and this
                retrieval has no positive control passing at present.
              </p>
            </section>

            <section>
              <h3 className="text-[12px] font-semibold text-[var(--text-primary)]">Sources</h3>
              <div className="mt-1.5">
                <LiteratureCitations runId={runId} subject={openDrug.canonical || openDrug.drug} kind="drug" />
              </div>
            </section>
          </div>
        )}
      </Modal>
    </div>
  );
}
