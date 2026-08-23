"use client";

import { useEffect, useMemo, useState } from "react";
import { getDrugTrials } from "@/lib/api";
import type { DrugCandidate, TrialsResult } from "@/lib/types";
import { CitationPopup } from "./CitationPopup";
import { TrialList } from "./TrialList";

function formatPercent(value: number | null | undefined): string {
  return value == null ? "n/a" : `${(value * 100).toFixed(0)}%`;
}

export function DrugEvidenceTable({
  runId,
  candidates,
  onSelectDrug,
}: {
  runId: string;
  candidates: DrugCandidate[];
  onSelectDrug?: (drug: string) => void;
}) {
  const [literatureDrug, setLiteratureDrug] = useState<string | null>(null);
  const [trialsDrug, setTrialsDrug] = useState<string | null>(null);
  const [trialResults, setTrialResults] = useState<Record<string, TrialsResult>>({});
  const [checkingTrials, setCheckingTrials] = useState(true);

  useEffect(() => {
    let cancelled = false;
    Promise.allSettled(candidates.map((candidate) => getDrugTrials(runId, candidate.drug)))
      .then((results) => {
        if (cancelled) return;
        const next: Record<string, TrialsResult> = {};
        results.forEach((result, index) => {
          if (result.status === "fulfilled") next[candidates[index].drug] = result.value;
        });
        setTrialResults(next);
      })
      .finally(() => {
        if (!cancelled) setCheckingTrials(false);
      });
    return () => {
      cancelled = true;
    };
  }, [candidates, runId]);

  const totalTrials = useMemo(
    () => Object.values(trialResults).reduce((sum, result) => sum + result.trials.length, 0),
    [trialResults]
  );

  return (
    <section id="drug" className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold tracking-tight text-slate-950">Drug evidence explorer</h2>
          <p className="mt-1 max-w-2xl text-sm leading-6 text-slate-500">
            Each evidence component is shown separately. Select a drug to give the Copilot context.
          </p>
        </div>
        <div className="flex gap-2 text-xs">
          <span className="rounded-full bg-slate-100 px-3 py-1.5 font-medium text-slate-600">
            {candidates.length} hypotheses
          </span>
          {checkingTrials && (
            <span className="rounded-full bg-sky-50 px-3 py-1.5 font-medium text-sky-700">
              Checking trial registry…
            </span>
          )}
          {!checkingTrials && totalTrials > 0 && (
            <span className="rounded-full bg-emerald-50 px-3 py-1.5 font-semibold text-emerald-700">
              {totalTrials} trial matches
            </span>
          )}
        </div>
      </div>

      <div className="mt-5 space-y-2">
        {candidates.map((candidate, index) => {
          const trialResult = trialResults[candidate.drug];
          const trialCount = trialResult?.trials.length ?? 0;
          const percentile = candidate.gctx_evidence?.blended_percentile;
          return (
            <article
              key={candidate.drug}
              className={`group rounded-xl border p-4 transition hover:border-indigo-200 hover:shadow-sm ${
                candidate.is_in_administered_regimen
                  ? "border-blue-200 bg-blue-50/40"
                  : "border-slate-200 bg-white"
              }`}
              onClick={() => onSelectDrug?.(candidate.drug)}
            >
              <div className="grid items-center gap-4 md:grid-cols-[1.2fr_1fr_1fr_auto]">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-lg bg-slate-100 text-[10px] font-bold text-slate-500">
                      {index + 1}
                    </span>
                    <h3 className="truncate text-sm font-semibold capitalize text-slate-900">
                      {candidate.drug}
                    </h3>
                    {candidate.is_in_administered_regimen && (
                      <span className="rounded-full bg-blue-100 px-2 py-0.5 text-[9px] font-bold uppercase tracking-wide text-blue-700">
                        Administered
                      </span>
                    )}
                  </div>
                  <p className="mt-2 truncate pl-8 text-xs text-slate-500">
                    {candidate.targets.slice(0, 5).join(" · ") || "No annotated targets"}
                  </p>
                </div>

                <div>
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-slate-500">GCTX reversal</span>
                    <span className="font-semibold text-indigo-700">{formatPercent(percentile)}</span>
                  </div>
                  <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-100">
                    <div
                      className="h-full rounded-full bg-indigo-500"
                      style={{ width: `${Math.max((percentile ?? 0) * 100, 1)}%` }}
                    />
                  </div>
                </div>

                <div>
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                    Q2 cell-line evidence
                  </p>
                  <p className="mt-1 text-xs font-medium capitalize text-slate-700">
                    {candidate.q2_evidence?.evidence_category?.replaceAll("_", " ") ?? "Not modeled"}
                  </p>
                </div>

                <div className="flex justify-end gap-2" onClick={(event) => event.stopPropagation()}>
                  <button
                    type="button"
                    className="rounded-lg border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-600 transition hover:border-indigo-200 hover:bg-indigo-50 hover:text-indigo-700"
                    onClick={() => {
                      onSelectDrug?.(candidate.drug);
                      setLiteratureDrug(candidate.drug);
                    }}
                  >
                    Literature
                  </button>
                  {trialCount > 0 && (
                    <button
                      type="button"
                      className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs font-semibold text-emerald-700 transition hover:bg-emerald-100"
                      onClick={() => {
                        onSelectDrug?.(candidate.drug);
                        setTrialsDrug(candidate.drug);
                      }}
                    >
                      Trials · {trialCount}
                    </button>
                  )}
                </div>
              </div>
            </article>
          );
        })}
      </div>

      {literatureDrug && (
        <CitationPopup runId={runId} drug={literatureDrug} onClose={() => setLiteratureDrug(null)} />
      )}
      {trialsDrug && (
        <TrialList
          runId={runId}
          drug={trialsDrug}
          initialResult={trialResults[trialsDrug]}
          onClose={() => setTrialsDrug(null)}
        />
      )}
    </section>
  );
}
