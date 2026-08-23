"use client";

import { useState } from "react";
import glossaryJson from "@/data/glossary.json";

type GlossaryEntry = {
  panel: string;
  plain_language: string;
  method: string;
  known_limitations: string[];
  reference?: string | null;
  validation: {
    metric?: string | null;
    value?: number | null;
    n?: number | null;
    threshold?: number | null;
    status: string;
    revised: boolean;
    revision_note?: string | null;
  };
};

const ENTRIES = (glossaryJson as { entries: GlossaryEntry[] }).entries;

export function GlossaryAffordance({ panel }: { panel: string }) {
  const [open, setOpen] = useState(false);
  const entry = ENTRIES.find((item) => item.panel === panel);
  if (!entry) return null;

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="inline-flex h-6 w-6 items-center justify-center rounded-full text-slate-400 transition hover:bg-slate-100 hover:text-slate-700"
        aria-label={`About the ${panel.replace(/_/g, " ")} method`}
      >
        <span className="text-sm leading-none" aria-hidden>
          ⓘ
        </span>
      </button>
      {open && (
        <div className="fixed inset-0 z-50 flex justify-end bg-slate-950/30" onClick={() => setOpen(false)}>
          <aside
            className="h-full w-full max-w-md overflow-y-auto bg-white p-6 shadow-2xl"
            onClick={(event) => event.stopPropagation()}
          >
            <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-indigo-600">Glossary</p>
            <h3 className="mt-2 text-lg font-semibold text-slate-950">{entry.plain_language}</h3>
            <p className="mt-3 text-sm text-slate-600">{entry.method}</p>
            <dl className="mt-5 space-y-2 text-sm">
              <div className="flex justify-between gap-4">
                <dt className="text-slate-500">Validation</dt>
                <dd className="font-medium text-slate-900">
                  {entry.validation.status === "unvalidated"
                    ? "No validation gate"
                    : `${entry.validation.metric ?? "—"} · ${entry.validation.status}`}
                  {entry.validation.n != null ? ` · n=${entry.validation.n}` : ""}
                </dd>
              </div>
              {entry.validation.value != null && (
                <div className="flex justify-between gap-4">
                  <dt className="text-slate-500">Value / threshold</dt>
                  <dd className="font-mono text-xs text-slate-800">
                    {Number(entry.validation.value).toFixed(3)} / {entry.validation.threshold}
                  </dd>
                </div>
              )}
            </dl>
            {entry.validation.revised && entry.validation.revision_note && (
              <p className="mt-4 rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900">
                Threshold was revised. {entry.validation.revision_note}
              </p>
            )}
            {entry.known_limitations.length > 0 && (
              <ul className="mt-4 list-disc space-y-1 pl-5 text-xs text-slate-600">
                {entry.known_limitations.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            )}
            {entry.reference && <p className="mt-4 text-xs text-slate-400">{entry.reference}</p>}
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="mt-6 rounded-lg border border-slate-200 px-3 py-1.5 text-sm font-semibold text-slate-700"
            >
              Close
            </button>
          </aside>
        </div>
      )}
    </>
  );
}
