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

export function GlossaryAffordance({ panel, encoder }: { panel: string; encoder?: string }) {
  const [open, setOpen] = useState(false);
  const found = ENTRIES.find((item) => item.panel === panel);
  if (!found) return null;
  const suppressNll = panel === "position" && encoder === "linear_poe";
  const entry = suppressNll
    ? {
        ...found,
        method: "Linear product-of-experts fallback — the committed VAE NLL gate does not apply.",
        validation: { ...found.validation, status: "not_applicable", metric: null, value: null },
      }
    : found;

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="inline-flex h-6 w-6 items-center justify-center rounded-full text-[var(--text-muted)] transition-colors hover:bg-[var(--surface-raised)] hover:text-[var(--text-primary)]"
        aria-label={`About the ${panel.replace(/_/g, " ")} method`}
      >
        <span className="text-sm leading-none" aria-hidden>
          ⓘ
        </span>
      </button>
      {open && (
        <div className="fixed inset-0 z-50 flex justify-end bg-[rgba(2,4,10,0.55)] backdrop-blur-sm" onClick={() => setOpen(false)}>
          <aside
            className="h-full w-full max-w-md overflow-y-auto border-l border-[var(--line)] bg-[var(--surface)] p-6 shadow-2xl"
            onClick={(event) => event.stopPropagation()}
          >
            <p className="eyebrow">Glossary</p>
            <h3 className="mt-2 text-[17px] font-semibold text-[var(--text-primary)]">{entry.plain_language}</h3>
            <p className="mt-3 text-[13px] text-[var(--text-secondary)]">{entry.method}</p>
            <dl className="mt-5 space-y-2 text-[13px]">
              <div className="flex justify-between gap-4">
                <dt className="text-[var(--text-muted)]">Validation</dt>
                <dd className="font-medium text-[var(--text-primary)]">
                  {entry.validation.status === "unvalidated"
                    ? "No validation gate"
                    : `${entry.validation.metric ?? "—"} · ${entry.validation.status}`}
                  {entry.validation.n != null ? ` · n=${entry.validation.n}` : ""}
                </dd>
              </div>
              {entry.validation.value != null && (
                <div className="flex justify-between gap-4">
                  <dt className="text-[var(--text-muted)]">Value / threshold</dt>
                  <dd className="font-mono text-xs text-[var(--text-primary)]">
                    {Number(entry.validation.value).toFixed(3)} / {entry.validation.threshold}
                  </dd>
                </div>
              )}
            </dl>
            {entry.validation.revised && entry.validation.revision_note && (
              <p className="mt-4 rounded-lg border border-[color-mix(in_oklab,var(--warning)_40%,transparent)] bg-[color-mix(in_oklab,var(--warning)_10%,transparent)] p-3 text-xs text-[var(--warning)]">
                Threshold was revised. {entry.validation.revision_note}
              </p>
            )}
            {entry.known_limitations.length > 0 && (
              <ul className="mt-4 list-disc space-y-1 pl-5 text-xs text-[var(--text-secondary)]">
                {entry.known_limitations.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            )}
            {entry.reference && <p className="mt-4 text-xs text-[var(--text-muted)]">{entry.reference}</p>}
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="mt-6 rounded-lg border border-[var(--line-strong)] px-3 py-1.5 text-[13px] font-medium text-[var(--text-secondary)] transition-colors hover:text-[var(--text-primary)]"
            >
              Close
            </button>
          </aside>
        </div>
      )}
    </>
  );
}
