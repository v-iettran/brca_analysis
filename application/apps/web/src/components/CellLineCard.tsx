"use client";

import { useState } from "react";
import type { V3CellLine, V3CohortPayload, V3FingerprintAxis } from "@/lib/v3-types";
import { Modal } from "@/components/Modal";
import { termDetail, termLabel } from "@/lib/v3-vocabulary";

/**
 * A retrieved cell line, and why it was retrieved.
 *
 * The card is a container rather than a button so the glossary control can sit
 * inside it legally; selection is its own button covering the body.
 */
export function CellLineCard({
  line,
  axes,
  patientPam50,
  similarityRange,
  joint,
  patientId,
  selected,
  onSelect,
}: {
  line: V3CellLine;
  axes?: V3FingerprintAxis[];
  patientPam50?: string | null;
  similarityRange: [number, number];
  joint?: V3CohortPayload["joint_projection"];
  patientId: string;
  selected: boolean;
  onSelect: () => void;
}) {
  const [explaining, setExplaining] = useState(false);
  const [lo, hi] = similarityRange;
  const width = hi > lo ? ((line.similarity - lo) / (hi - lo)) * 100 : 100;
  const curveCount = line.curves?.length ?? 0;

  return (
    <div
      onClick={onSelect}
      className="group cursor-pointer rounded-[var(--radius-inner)] border p-2.5 transition-all duration-150 hover:-translate-y-px hover:shadow-md"
      style={{
        borderColor: selected ? "var(--cluster-1)" : "var(--line)",
        background: selected ? "var(--surface-raised)" : "transparent",
      }}
    >
      <div className="flex items-baseline justify-between gap-2">
        <button
          type="button"
          onClick={onSelect}
          aria-pressed={selected}
          className="min-w-0 flex-1 px-1 py-0.5 text-left"
        >
          <span className="font-mono text-[13px] font-semibold text-[var(--text-primary)]">{line.name}</span>
        </button>
        <span className="font-mono text-[11px] tabular-nums text-[var(--text-secondary)]">
          {line.similarity.toFixed(2)}
        </span>
        <button
          type="button"
          onClick={(event) => {
            event.stopPropagation();
            setExplaining(true);
          }}
          aria-label={`What is ${line.name}, and how does it resemble this tumour?`}
          className="pressable h-5 w-5 shrink-0 text-[11px] text-[var(--text-muted)]"
        >
          ?
        </button>
      </div>
      <p className="mt-0.5 px-1 text-[10px] text-[var(--text-muted)]">
        cosine similarity in joint PCA space
      </p>

      <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-[var(--line)]">
        <div
          className="h-full rounded-full transition-[width] duration-300 ease-out"
          style={{
            width: `${Math.max(6, width)}%`,
            background: selected ? "var(--cluster-1)" : "var(--text-muted)",
          }}
        />
      </div>

      <ul className="mt-2 flex flex-wrap gap-1">
        {line.subtype_features && (
          <li className="rounded border border-[var(--line-strong)] px-1.5 py-0.5 text-[10px] text-[var(--text-secondary)]">
            {line.subtype_features}
          </li>
        )}
        {line.pam50 && (
          <li
            className="rounded border px-1.5 py-0.5 text-[10px]"
            style={
              line.pam50_match
                ? { borderColor: "var(--cluster-1)", color: "var(--cluster-1)" }
                : { borderColor: "var(--line-strong)", color: "var(--text-muted)" }
            }
          >
            PAM50 {line.pam50}
            {line.pam50_match ? " ✓" : ""}
          </li>
        )}
        {line.primary_or_metastasis && (
          <li className="rounded border border-[var(--line-strong)] px-1.5 py-0.5 text-[10px] text-[var(--text-muted)]">
            {line.primary_or_metastasis}
          </li>
        )}
      </ul>

      {line.marker_comparison && line.marker_comparison.length > 0 && (
        <dl className="mt-2 grid grid-cols-3 gap-1 border-t border-[var(--line)] pt-2">
          {line.marker_comparison.map((m) => (
            <div key={m.marker} title={`${m.marker}: this line ${m.line}, subgroup mean ${m.subgroup}`}>
              <dt className="truncate text-[9px] uppercase tracking-wide text-[var(--text-muted)]">
                {m.marker}
              </dt>
              <dd className="font-mono text-[10.5px] tabular-nums text-[var(--text-secondary)]">
                {m.line > 0 ? "+" : ""}
                {m.line.toFixed(1)}
                <span className="text-[var(--text-muted)]"> / {m.subgroup.toFixed(1)}</span>
              </dd>
            </div>
          ))}
        </dl>
      )}

      <div className="mt-2 border-t border-[var(--line)] pt-2">
        <p className="text-[9px] uppercase tracking-wide text-[var(--text-muted)]">Axes driving the match</p>
        <div className="mt-1 flex h-5 items-center gap-1">
          {line.fingerprint.map((v, i) => {
            const axis = axes?.[i];
            const magnitude = Math.min(1, Math.abs(v));
            return (
              <span
                key={i}
                className="relative flex h-full flex-1 items-center"
                title={
                  axis
                    ? `PC${axis.component} (${(axis.variance_ratio * 100).toFixed(1)}% of variance) — high in ${axis.top_positive.slice(0, 3).join(", ")}, low in ${axis.top_negative.slice(0, 3).join(", ")}. Contribution ${v.toFixed(2)}.`
                    : `Axis ${i + 1}: ${v.toFixed(2)}`
                }
              >
                <span className="absolute inset-x-0 top-1/2 h-px bg-[var(--line-strong)]" />
                <span
                  className="absolute inset-x-0 rounded-[1px]"
                  style={{
                    height: `${Math.max(6, magnitude * 46)}%`,
                    top: v >= 0 ? undefined : "50%",
                    bottom: v >= 0 ? "50%" : undefined,
                    background: v >= 0 ? "var(--diverge-pos)" : "var(--diverge-neg)",
                    opacity: selected ? 1 : 0.65,
                  }}
                />
              </span>
            );
          })}
        </div>
      </div>

      <p className="mt-1.5 text-right font-mono text-[10px] text-[var(--text-muted)]">
        {curveCount ? `${curveCount} measured curve${curveCount === 1 ? "" : "s"}` : "no GDSC curves"}
      </p>

      <Modal
        open={explaining}
        onClose={() => setExplaining(false)}
        title={`${line.name}: what it is, and why it was retrieved`}
        subtitle="A cell line is a population of tumour cells grown in a lab. It is a model of a tumour, not a patient."
      >
        <div className="space-y-4 text-[13px] leading-relaxed text-[var(--text-secondary)]">
          <section>
            <h3 className="text-[12px] font-semibold text-[var(--text-primary)]">
              Where the {line.similarity.toFixed(2)} comes from
            </h3>
            <p className="mt-1">
              Both this tumour and {line.name} are described by the same {" "}
              <span className="font-mono">2,141</span> genes. Those measurements are reduced to ten
              components by a PCA fitted across the tumour cohort and the cell lines together, and the
              number is the <strong>cosine similarity</strong> between the two positions in that space:
              1.00 means the two point in exactly the same direction, 0 means unrelated, and it can go
              negative.
            </p>
            <p className="mt-2">
              It is a direction, not a percentage. {line.similarity.toFixed(2)} does not mean
              &ldquo;{Math.round(line.similarity * 100)}% the same&rdquo;. The bar on the card is scaled
              across the five retrieved lines so they can be ranked against each other, not against zero.
            </p>
          </section>

          {joint && (
            <section>
              <h3 className="text-[12px] font-semibold text-[var(--text-primary)]">
                Where it sits relative to this tumour
              </h3>
              <p className="mt-1">
                The same space the cosine is measured in. Grey is the tumour cohort; the dashed line joins
                this patient to {line.name}.
              </p>
              <div className="mt-2 rounded-[var(--radius-inner)] border border-[var(--line)] bg-[var(--well)] p-3">
                <JointMiniPlot joint={joint} patientId={patientId} lineId={line.line_id} selected large />
              </div>
              {joint.note && <p className="mt-1.5 text-[11px] text-[var(--text-muted)]">{joint.note}</p>}
            </section>
          )}

          <section>
            <h3 className="text-[12px] font-semibold text-[var(--text-primary)]">
              What the five bars mean
            </h3>
            <p className="mt-1">
              Each bar is one PCA component&apos;s contribution to that similarity. Upward means the
              tumour and the line sit on the same side of that axis; downward means opposite sides.
              {line.fingerprint_scale ? ` Bars are ${termLabel(line.fingerprint_scale).toLowerCase()}, so cards can be compared.` : ""}
            </p>
            {axes && axes.length > 0 && (
              <ul className="mt-2 space-y-1.5">
                {axes.map((axis, i) => (
                  <li key={axis.component} className="font-mono text-[11px]">
                    <span className="text-[var(--text-primary)]">PC{axis.component}</span>{" "}
                    <span className="text-[var(--text-muted)]">
                      ({(axis.variance_ratio * 100).toFixed(1)}% of variance)
                    </span>{" "}
                    high in {axis.top_positive.slice(0, 3).join(", ")}, low in{" "}
                    {axis.top_negative.slice(0, 3).join(", ")}
                    <span className="text-[var(--text-secondary)]">
                      {" "}
                      · this line {line.fingerprint[i] >= 0 ? "+" : ""}
                      {line.fingerprint[i]?.toFixed(2)}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section>
            <h3 className="text-[12px] font-semibold text-[var(--text-primary)]">
              How it resembles this tumour
            </h3>
            <ul className="mt-1 space-y-1">
              {line.subtype_features && (
                <li>
                  DepMap records it as <strong>{line.subtype_features}</strong>
                  {line.oncotree_subtype ? `, ${line.oncotree_subtype.toLowerCase()}` : ""}
                  {line.primary_or_metastasis ? `, from a ${line.primary_or_metastasis.toLowerCase()} site` : ""}.
                </li>
              )}
              <li>
                Its PAM50 call is <strong>{line.pam50 ?? "not called"}</strong>
                {patientPam50 ? (
                  line.pam50_match ? (
                    <> — the same subtype as this patient ({patientPam50}).</>
                  ) : (
                    <> — a different subtype from this patient ({patientPam50}).</>
                  )
                ) : (
                  "."
                )}
              </li>
              {line.marker_comparison?.map((m) => (
                <li key={m.marker} className="font-mono text-[11px]">
                  {m.marker}: this line {m.line > 0 ? "+" : ""}
                  {m.line.toFixed(2)} versus a subgroup mean of {m.subgroup > 0 ? "+" : ""}
                  {m.subgroup.toFixed(2)}
                </li>
              ))}
            </ul>
          </section>

          <section className="border-t border-[var(--line)] pt-3 text-[11.5px] text-[var(--text-muted)]">
            <p>
              The similarity uses bulk mRNA only. Mutations, copy number and methylation do not enter it,
              and the shared PCA is dominated by its first component, which separates tumour tissue from
              cultured cells as much as it separates biology. Treat a high similarity as &ldquo;a
              reasonable model to look at&rdquo;, not as a claim that this line behaves like this tumour.
            </p>
            {line.curves?.[0]?.source && (
              <p className="mt-2">
                Response data: {termLabel(line.curves[0].source)}. {termDetail(line.curves[0].source)}
              </p>
            )}
          </section>
        </div>
      </Modal>
    </div>
  );
}

/**
 * Where this line sits relative to the cohort and to this patient, in the same
 * PCA the cosine similarity is measured in — so the picture and the number are
 * one claim rather than two.
 */
function JointMiniPlot({
  joint,
  patientId,
  lineId,
  selected,
  large = false,
}: {
  joint: NonNullable<V3CohortPayload["joint_projection"]>;
  patientId: string;
  lineId: string;
  selected: boolean;
  large?: boolean;
}) {
  const patient = joint.patients?.[patientId];
  const line = joint.lines?.[lineId];
  const cloud = joint.tumours ?? [];
  if (!patient || !line || cloud.length === 0) return null;

  const W = large ? 420 : 240;
  const H = large ? 220 : 96;
  const pad = large ? 18 : 10;
  const points = [...cloud, patient, line];
  const xs = points.map((p) => p[0]);
  const ys = points.map((p) => p[1]);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const sx = (v: number) => pad + ((v - minX) / (maxX - minX || 1)) * (W - pad * 2);
  const sy = (v: number) => H - pad - ((v - minY) / (maxY - minY || 1)) * (H - pad * 2);

  return (
    <>
      <svg viewBox={`0 0 ${W} ${H}`} className="mt-1 w-full" role="img"
        aria-label={`Position of ${lineId} relative to the tumour cohort and this patient`}>
        {cloud.map((p, i) => (
          <circle key={i} cx={sx(p[0])} cy={sy(p[1])} r={large ? 2.2 : 1.4} fill="var(--text-muted)" opacity="0.35" />
        ))}
        <line
          x1={sx(patient[0])}
          y1={sy(patient[1])}
          x2={sx(line[0])}
          y2={sy(line[1])}
          stroke="var(--cluster-1)"
          strokeWidth="1"
          strokeDasharray="2 2"
          opacity={selected ? 0.9 : 0.5}
        />
        <circle cx={sx(patient[0])} cy={sy(patient[1])} r={large ? 6 : 4} fill="var(--cluster-1)"
          stroke="var(--surface)" strokeWidth="1.5" />
        <rect
          x={sx(line[0]) - 3.5}
          y={sy(line[1]) - 3.5}
          width="7"
          height="7"
          fill="var(--cluster-2)"
          stroke="var(--surface)"
          strokeWidth="1.5"
        />
      </svg>
      <p className="mt-0.5 flex flex-wrap gap-x-2.5 text-[9px] text-[var(--text-muted)]">
        <span>
          <span className="mr-1 inline-block h-1.5 w-1.5 rounded-full align-middle" style={{ background: "var(--cluster-1)" }} />
          this tumour
        </span>
        <span>
          <span className="mr-1 inline-block h-1.5 w-1.5 align-middle" style={{ background: "var(--cluster-2)" }} />
          {lineId}
        </span>
        <span>grey: cohort</span>
      </p>
    </>
  );
}
