"use client";

import type { AbstentionState } from "@/lib/types";
import { GlossaryAffordance } from "@/components/GlossaryAffordance";

export function AbstentionPanel({ data }: { data: AbstentionState }) {
  return (
    <section className="rounded-2xl border border-rose-200 bg-rose-50 p-5 shadow-sm">
      <header className="flex items-start justify-between gap-3">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-rose-700">No therapeutic set</p>
          <h2 className="mt-1 text-lg font-semibold text-rose-950">{data.reason_text}</h2>
        </div>
        <GlossaryAffordance panel="abstention" />
      </header>
      {data.what_would_help.length > 0 && (
        <ul className="mt-4 list-disc space-y-1 pl-5 text-sm text-rose-900">
          {data.what_would_help.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      )}
      <p className="mt-4 text-xs text-rose-800">
        Drug retrieval and the prognostic interval are withheld — clustering remains visible so the reason is
        apparent.
      </p>
    </section>
  );
}
