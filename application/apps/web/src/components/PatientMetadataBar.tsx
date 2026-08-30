"use client";

import { termLabel } from "@/lib/v3-vocabulary";

const ALL_MODALITIES = ["rna", "cna", "methylation"] as const;

const STATE_COPY: Record<number, string> = {
  1: "full modality",
  2: "missing view",
  3: "abstained",
};

export function PatientMetadataBar({
  patientId,
  modalities,
  pam50,
  tumourFraction,
  verdict,
  timestamp,
  state,
  encoder,
  exploratory,
}: {
  patientId: string;
  modalities: string[];
  pam50?: string | null;
  tumourFraction: number;
  verdict: string;
  timestamp?: string;
  state: number;
  encoder?: string;
  exploratory?: boolean;
}) {
  const verdictColor =
    verdict === "sufficient" ? "var(--response)" : verdict === "marginal" ? "var(--warning)" : "var(--progression)";

  return (
    <header className="sticky top-0 z-30 border-b border-[var(--line)] bg-[color-mix(in_oklab,var(--shell)_88%,transparent)] backdrop-blur-md">
      <div className="mx-auto flex w-full max-w-[1400px] flex-wrap items-center gap-x-5 gap-y-2 px-4 py-3 sm:px-6">
        <div className="flex items-baseline gap-2.5">
          <span className="font-mono text-[15px] font-semibold tracking-tight text-[var(--text-primary)]">
            {patientId}
          </span>
          <span className="text-[11px] text-[var(--text-muted)]">{STATE_COPY[state] ?? `state ${state}`}</span>
          {encoder && (
            <span className="text-[11px] text-[var(--text-muted)]" title="How positions were computed">
              {termLabel(encoder)}
            </span>
          )}
        </div>

        {/* Absent assays render as outlined chips. Absence should be visible. */}
        <div className="flex gap-1">
          {ALL_MODALITIES.map((mod) => {
            const present = modalities.includes(mod);
            return (
              <span
                key={mod}
                title={present ? `${mod} present` : `${mod} not available`}
                className="rounded-md px-1.5 py-0.5 text-[10.5px] font-medium"
                style={
                  present
                    ? { background: "var(--surface-raised)", color: "var(--text-secondary)", border: "1px solid var(--line-strong)" }
                    : { border: "1px dashed var(--line-strong)", color: "var(--text-muted)", opacity: 0.7 }
                }
              >
                {mod}
              </span>
            );
          })}
        </div>

        {pam50 && (
          <span className="font-mono text-[11px] text-[var(--text-secondary)]">
            PAM50 <span className="text-[var(--text-primary)]">{pam50}</span>
          </span>
        )}

        <span className="inline-flex items-center gap-1.5 text-[11px] text-[var(--text-secondary)]">
          <span className="h-1.5 w-1.5 rounded-full" style={{ background: verdictColor }} />
          <span className="font-mono tabular-nums text-[var(--text-primary)]">
            {(tumourFraction * 100).toFixed(0)}%
          </span>
          tumour
        </span>

        {timestamp && (
          <span className="font-mono text-[11px] text-[var(--text-muted)]">{timestamp.slice(0, 10)}</span>
        )}

        <div className="ml-auto flex items-center gap-2.5">
          {exploratory && <span className="exploratory-chip">exploratory configuration</span>}
        </div>
      </div>
    </header>
  );
}
