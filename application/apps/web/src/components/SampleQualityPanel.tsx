"use client";

import type { SampleQuality } from "@/lib/types";
import { GlossaryAffordance } from "@/components/GlossaryAffordance";
import { PanelCard } from "@/components/PanelCard";

// Validated categorical slots; --molecular and --teal-secondary no longer exist.
const COMPOSITION_TINT: Record<string, string> = {
  malignant: "var(--cluster-1)",
  immune: "var(--cluster-3)",
  stroma: "var(--text-muted)",
};

export function SampleQualityPanel({ data, takeaway }: { data: SampleQuality; takeaway?: string }) {
  const verdictColor =
    data.verdict === "sufficient"
      ? "var(--response)"
      : data.verdict === "marginal"
        ? "var(--warning)"
        : "var(--progression)";

  return (
    <PanelCard
      id="quality"
      eyebrow="Sample quality"
      title="Tumour composition"
      takeaway={takeaway}
      display={`${(data.tumour_fraction * 100).toFixed(0)}%`}
      displayCaption="tumour content"
      bare
      actions={<GlossaryAffordance panel="sample_quality" />}
      footnote={data.verdict_reason ?? undefined}
    >
      <div className="flex items-center gap-2">
        <span className="h-1.5 w-1.5 rounded-full" style={{ background: verdictColor }} />
        <span className="text-[11px] font-medium" style={{ color: verdictColor }}>
          {data.verdict}
        </span>
      </div>

      <div className="mt-2.5 flex h-2.5 overflow-hidden rounded-full bg-[var(--line)]">
        {data.composition.map((part) => (
          <div
            key={part.cell_type}
            style={{
              width: `${Math.max(part.fraction * 100, 0)}%`,
              background: COMPOSITION_TINT[part.cell_type] ?? "var(--line-strong)",
            }}
            title={`${part.cell_type} ${(part.fraction * 100).toFixed(0)}%`}
          />
        ))}
      </div>

      <ul className="mt-3 space-y-1 border-t border-[var(--line)] pt-2.5 text-[11.5px]">
        {data.composition.map((part) => (
          <li key={part.cell_type} className="flex items-baseline justify-between gap-4">
            <span className="inline-flex items-center gap-1.5 capitalize text-[var(--text-secondary)]">
              <span
                className="h-2.5 w-2.5 rounded-[2px]"
                style={{ background: COMPOSITION_TINT[part.cell_type] ?? "var(--line-strong)" }}
              />
              {part.cell_type}
            </span>
            <span className="font-mono tabular-nums text-[var(--text-primary)]">
              {(part.fraction * 100).toFixed(1)}%
              {part.ci?.length === 2 && (
                <span className="text-[var(--text-muted)]">
                  {" "}
                  ({(part.ci[0] * 100).toFixed(0)}-{(part.ci[1] * 100).toFixed(0)})
                </span>
              )}
            </span>
          </li>
        ))}
      </ul>
      <p className="mt-2 text-[10.5px] text-[var(--text-muted)]">
        Deconvolved cell-type shares with 95% intervals. Tumour content is the malignant share; the rest is
        the microenvironment the signal has to be read through.
      </p>
    </PanelCard>
  );
}
