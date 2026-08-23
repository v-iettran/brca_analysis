"use client";

import { useEffect, useState } from "react";
import { getRunTrials } from "@/lib/api";
import type { CriterionStatus, EligibilityCriterion, RunTrialsResult, TrialMatch } from "@/lib/types";

const STATUS_STYLE: Record<CriterionStatus, string> = {
  met: "bg-emerald-50 text-emerald-700 border-emerald-200",
  not_met: "bg-rose-50 text-rose-700 border-rose-200",
  unknown: "bg-slate-50 text-slate-600 border-slate-200",
};

function criterionLabel(criterion: EligibilityCriterion): string {
  return (
    criterion.criterion?.trim() ||
    criterion.text?.trim() ||
    criterion.category?.trim() ||
    "Eligibility criterion"
  );
}

function criterionQuote(criterion: EligibilityCriterion): string | null {
  const excerpt = criterion.source_excerpt?.trim();
  if (excerpt) return excerpt;
  const text = criterion.text?.trim();
  if (text && text !== criterion.criterion?.trim()) return text;
  return null;
}

export function TrialExplorer({
  runId,
  patientLabel,
  metadataSummary,
}: {
  runId: string;
  patientLabel: string;
  metadataSummary: string;
}) {
  const [data, setData] = useState<RunTrialsResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);

  useEffect(() => {
    getRunTrials(runId)
      .then(setData)
      .catch((err) => setError(String(err)));
  }, [runId]);

  return (
    <section className="space-y-4 rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm">
      <div>
        <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-indigo-600">Clinical Trials</p>
        <h3 className="mt-1 text-lg font-semibold text-slate-950">Trial Explorer</h3>
        <p className="mt-1 text-xs text-slate-500">
          Aggregated across overlap nominations for <span className="font-mono">{patientLabel}</span>. A trial is a
          potential match only when no known exclusion is found; unknown criteria remain visible. Investigator
          confirmation is required.
        </p>
        <p className="mt-2 rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-600">{metadataSummary}</p>
      </div>

      {error && <p className="rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">{error}</p>}
      {!data && !error && <p className="text-sm text-slate-500">Loading run-level trials…</p>}

      {data && data.trials.length === 0 && (
        <p className="rounded-xl border border-dashed border-slate-200 p-4 text-sm text-slate-500">
          No candidate-associated studies matched, or external trial search is unavailable.
          {(data.unavailable || []).length > 0 && (
            <span className="mt-2 block text-xs text-amber-700">
              {(data.unavailable || []).map((u) => `${u.drug}: ${u.reason}`).join(" · ")}
            </span>
          )}
        </p>
      )}

      <div className="space-y-3">
        {(data?.trials || []).map((trial) => (
          <TrialCard
            key={trial.nct_id}
            trial={trial}
            expanded={expanded === trial.nct_id}
            onToggle={() => setExpanded(expanded === trial.nct_id ? null : trial.nct_id)}
          />
        ))}
      </div>
    </section>
  );
}

function TrialCard({
  trial,
  expanded,
  onToggle,
}: {
  trial: TrialMatch;
  expanded: boolean;
  onToggle: () => void;
}) {
  return (
    <div className="rounded-xl border border-slate-200 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <a href={trial.url} target="_blank" rel="noreferrer" className="text-sm font-semibold text-indigo-700 hover:underline">
            {trial.nct_id}
          </a>
          <h4 className="mt-1 text-sm font-medium text-slate-900">{trial.title}</h4>
          <p className="mt-1 text-[11px] text-slate-500">
            {trial.status} · {trial.phase || "phase n/a"} · drugs {(trial.matched_drugs || []).join(", ") || "n/a"}
          </p>
        </div>
        <span
          className={`rounded-full px-2.5 py-1 text-[10px] font-semibold ${
            trial.eligibility_assessment === "potentially_eligible"
              ? "bg-emerald-50 text-emerald-700"
              : trial.eligibility_assessment === "potentially_ineligible"
                ? "bg-rose-50 text-rose-700"
                : "bg-amber-50 text-amber-700"
          }`}
        >
          {trial.eligibility_assessment.replace(/_/g, " ")}
        </span>
      </div>
      <button onClick={onToggle} className="mt-3 text-xs font-semibold text-indigo-600">
        {expanded ? "Hide criteria" : "Show criterion-by-criterion assessment"}
      </button>
      {expanded && (
        <ul className="mt-3 space-y-2">
          {(trial.eligibility_criteria || []).length === 0 && (
            <li className="rounded-lg border border-slate-100 bg-slate-50 p-2 text-xs text-slate-500">
              No structured criteria were parsed for this study.
            </li>
          )}
          {(trial.eligibility_criteria || []).map((criterion, index) => {
            const label = criterionLabel(criterion);
            const quote = criterionQuote(criterion);
            const rationale = criterion.evidence?.trim() || criterion.rationale?.trim() || null;
            return (
              <li
                key={`${trial.nct_id}-${index}`}
                className={`rounded-lg border p-2 text-xs ${STATUS_STYLE[criterion.status]}`}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-semibold uppercase tracking-wide">
                    {criterion.status.replace("_", " ")}
                  </span>
                  {criterion.category && <span className="opacity-70">{criterion.category}</span>}
                </div>
                <p className="mt-1 font-medium text-slate-800">{label}</p>
                {quote && (
                  <p className="mt-1 whitespace-pre-wrap text-slate-700">&ldquo;{quote}&rdquo;</p>
                )}
                {rationale && <p className="mt-1 opacity-80">{rationale}</p>}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
