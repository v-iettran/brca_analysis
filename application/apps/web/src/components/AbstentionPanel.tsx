"use client";

import type { AbstentionState } from "@/lib/types";
import { GlossaryAffordance } from "@/components/GlossaryAffordance";
import { termDetail, termLabel } from "@/lib/v3-vocabulary";

/**
 * State 3. Clustering stays on screen because it remains legitimate when
 * therapeutic inference does not, and because the reason has to be visible
 * next to what it suppressed.
 */
export function AbstentionPanel({ data }: { data: AbstentionState }) {
  return (
    <section
      id="retrieval"
      className="rounded-[var(--radius-panel)] border p-5 scroll-mt-28"
      style={{
        borderColor: "color-mix(in oklab, var(--progression) 35%, transparent)",
        background: "color-mix(in oklab, var(--progression) 7%, transparent)",
      }}
    >
      <header className="flex items-start justify-between gap-3">
        <div>
          <p className="eyebrow" style={{ color: "var(--progression)" }}>
            No therapeutic set
          </p>
          <h2 className="mt-1.5 text-[15px] font-semibold text-[var(--text-primary)]">{data.reason_text}</h2>
          {data.reason_code && (
            <p className="mt-1 text-[12px] text-[var(--text-secondary)]">
              {termLabel(data.reason_code)}. {termDetail(data.reason_code)}
            </p>
          )}
        </div>
        <GlossaryAffordance panel="abstention" />
      </header>

      {data.what_would_help.length > 0 && (
        <div className="mt-4">
          <p className="eyebrow">What would help</p>
          <ul className="mt-1.5 space-y-1 text-[13px] text-[var(--text-secondary)]">
            {data.what_would_help.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      )}

      <p className="mt-4 border-t border-[var(--line)] pt-3 text-[11px] text-[var(--text-muted)]">
        Drug retrieval and the prognostic interval are withheld. Clustering remains visible so the reason is
        apparent.
      </p>
    </section>
  );
}
