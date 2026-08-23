"use client";

import { useEffect, useState } from "react";
import { getDrugTrials } from "@/lib/api";
import type { TrialMatch, TrialsResult } from "@/lib/types";

const ELIGIBILITY_STYLE: Record<string, string> = {
  potentially_eligible: "bg-emerald-100 text-emerald-800 border-emerald-300",
  potentially_ineligible: "bg-rose-100 text-rose-800 border-rose-300",
  insufficient_information: "bg-slate-100 text-slate-700 border-slate-300",
};

const ELIGIBILITY_LABEL: Record<string, string> = {
  potentially_eligible: "Potentially eligible",
  potentially_ineligible: "Potentially ineligible",
  insufficient_information: "Insufficient information",
};

function TrialCard({ trial }: { trial: TrialMatch }) {
  return (
    <li className="rounded-lg border border-slate-200 p-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <a href={trial.url} target="_blank" rel="noreferrer" className="font-medium text-sm text-blue-800 underline">
            {trial.nct_id}
          </a>
          <p className="text-sm text-slate-800">{trial.title}</p>
        </div>
        <span
          className={`shrink-0 rounded-full border px-2 py-0.5 text-[11px] font-semibold ${
            ELIGIBILITY_STYLE[trial.eligibility_assessment]
          }`}
        >
          {ELIGIBILITY_LABEL[trial.eligibility_assessment]}
        </span>
      </div>
      <div className="mt-1 text-xs text-slate-500">
        {trial.status} {trial.phase ? `· ${trial.phase}` : ""} · {trial.interventions.join(", ")}
      </div>
      <div className="mt-2 flex flex-wrap gap-2 text-xs text-slate-600">
        {trial.sites.slice(0, 4).map((site, idx) => (
          <span key={idx} className="rounded bg-slate-100 px-2 py-0.5">
            {site.facility ?? site.city}, {site.country}
            {site.distance_from_ireland_km != null ? ` (${Math.round(site.distance_from_ireland_km)} km from Ireland)` : ""}
          </span>
        ))}
      </div>
      {trial.eligibility_notes.length > 0 && (
        <ul className="mt-2 list-disc pl-4 text-xs text-slate-500">
          {trial.eligibility_notes.map((note, idx) => (
            <li key={idx}>{note}</li>
          ))}
        </ul>
      )}
    </li>
  );
}

export function TrialList({
  runId,
  drug,
  initialResult,
  onClose,
}: {
  runId: string;
  drug: string;
  initialResult?: TrialsResult | null;
  onClose: () => void;
}) {
  const [result, setResult] = useState<TrialsResult | null>(initialResult ?? null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (initialResult) return;
    getDrugTrials(runId, drug)
      .then(setResult)
      .catch((err) => setError(String(err)));
  }, [initialResult, runId, drug]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
      <div
        className="max-h-[85vh] w-full max-w-2xl overflow-y-auto rounded-xl bg-white p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-slate-900">Trial matches — {drug}</h2>
          <button onClick={onClose} className="rounded-full p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700">
            ✕
          </button>
        </div>
        <p className="mt-1 text-xs text-slate-500">
          Ireland first, then rest of Europe, then United States. Eligibility is a conservative,
          automated text match only — a clinician must confirm.
        </p>

        {error && <p className="mt-4 text-sm text-red-700">{error}</p>}
        {!result && !error && <p className="mt-4 text-sm text-slate-500">Searching ClinicalTrials.gov…</p>}
        {result?.unavailable_reason && (
          <p className="mt-4 rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
            {result.unavailable_reason}
          </p>
        )}
        {result && !result.unavailable_reason && (
          <ul className="mt-4 space-y-3">
            {result.trials.length === 0 && <p className="text-sm text-slate-500">No matching trials found in Europe/US.</p>}
            {result.trials.map((trial) => (
              <TrialCard key={trial.nct_id} trial={trial} />
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
