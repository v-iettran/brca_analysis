"use client";

import { useEffect, useState } from "react";
import { getDrugLiterature } from "@/lib/api";
import type { CitationOut, LiteratureResult } from "@/lib/types";

const STANCE_STYLE: Record<string, string> = {
  supporting: "bg-emerald-100 text-emerald-800 border-emerald-300",
  conflicting: "bg-rose-100 text-rose-800 border-rose-300",
  neutral: "bg-slate-100 text-slate-700 border-slate-300",
  unclear: "bg-amber-100 text-amber-800 border-amber-300",
};

function CitationCard({ citation }: { citation: CitationOut }) {
  return (
    <li className="rounded-lg border border-slate-200 p-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-wide text-indigo-600">
            Evidence rank #{citation.evidence_rank ?? "—"} · combined {citation.combined_score?.toFixed(1) ?? "n/a"}
          </p>
          <p className="mt-0.5 font-medium text-sm text-slate-900">{citation.title}</p>
        </div>
        <span
          className={`shrink-0 rounded-full border px-2 py-0.5 text-[11px] font-semibold uppercase ${
            STANCE_STYLE[citation.stance] ?? STANCE_STYLE.unclear
          }`}
        >
          {citation.stance}
        </span>
      </div>
      <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-slate-500">
        <span>Credibility {citation.credibility_score?.toFixed(0) ?? "n/a"}/100</span>
        <span>Relevance {citation.relevance_score?.toFixed(0) ?? "n/a"}/100</span>
        {citation.journal && <span>{citation.journal}</span>}
        {citation.year && <span>{citation.year}</span>}
        {citation.article_type && <span>{citation.article_type}</span>}
        <span>{citation.peer_reviewed ? "Peer-reviewed" : "Peer-review status unknown"}</span>
        <span>{citation.full_text_available ? "Full text available" : "Abstract only / unknown"}</span>
      </div>
      {citation.excerpt && <p className="mt-2 text-sm text-slate-600 italic">&ldquo;{citation.excerpt.slice(0, 280)}&rdquo;</p>}
      <div className="mt-2 flex flex-wrap gap-3 text-xs">
        {citation.doi && (
          <a className="text-blue-700 underline" href={`https://doi.org/${citation.doi}`} target="_blank" rel="noreferrer">
            DOI: {citation.doi}
          </a>
        )}
        {citation.pmid && (
          <a
            className="text-blue-700 underline"
            href={`https://pubmed.ncbi.nlm.nih.gov/${citation.pmid}`}
            target="_blank"
            rel="noreferrer"
          >
            PMID: {citation.pmid}
          </a>
        )}
        {citation.matched_queries.length > 0 && (
          <span className="text-slate-400">matched: {citation.matched_queries.join(", ")}</span>
        )}
      </div>
    </li>
  );
}

export function CitationPopup({ runId, drug, onClose }: { runId: string; drug: string; onClose: () => void }) {
  const [result, setResult] = useState<LiteratureResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getDrugLiterature(runId, drug)
      .then(setResult)
      .catch((err) => setError(String(err)));
  }, [runId, drug]);

  const counts = result
    ? result.citations.reduce<Record<string, number>>((acc, c) => {
        acc[c.stance] = (acc[c.stance] ?? 0) + 1;
        return acc;
      }, {})
    : {};

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
      <div
        className="max-h-[85vh] w-full max-w-2xl overflow-y-auto rounded-xl bg-white p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-slate-900">Literature evidence — {drug}</h2>
          <button onClick={onClose} className="rounded-full p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700">
            ✕
          </button>
        </div>

        {error && <p className="mt-4 text-sm text-red-700">{error}</p>}
        {!result && !error && <p className="mt-4 text-sm text-slate-500">Searching Paperclip…</p>}

        {result?.unavailable_reason && (
          <p className="mt-4 rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
            {result.unavailable_reason}
          </p>
        )}

        {result && !result.unavailable_reason && (
          <>
            <div className="mt-4 grid grid-cols-2 gap-2 text-xs text-slate-500 sm:grid-cols-4">
              <span>Supporting: {counts.supporting ?? 0}</span>
              <span>Conflicting: {counts.conflicting ?? 0}</span>
              <span>Neutral: {counts.neutral ?? 0}</span>
              <span>Unclear: {counts.unclear ?? 0}</span>
            </div>

            <details open className="mt-3 rounded-md border border-slate-200 p-3 text-xs text-slate-500">
              <summary className="cursor-pointer font-medium text-slate-700">
                Keywords and exact search queries ({result.query_families.length}) — {result.raw_result_count} raw results,{" "}
                {result.deduplicated_count} unique after dedup {result.cache_hit ? "(cached)" : ""}
              </summary>
              <ul className="mt-2 space-y-1">
                {result.query_families.map((family) => (
                  <li key={family.label}>
                    <span className="font-mono">{family.label}</span>: &ldquo;{family.query_text}&rdquo; →{" "}
                    {family.result_count} results
                  </li>
                ))}
              </ul>
            </details>
            <p className="mt-3 rounded-md bg-indigo-50 p-3 text-xs leading-5 text-indigo-800">
              Papers are sorted by 55% text/query relevance and 45% metadata credibility. Scores make retrieval
              ordering transparent; they are not a formal evidence-grade assessment.
            </p>

            <ul className="mt-4 space-y-3">
              {result.citations.length === 0 && (
                <p className="text-sm text-slate-500">No literature was found for this drug.</p>
              )}
              {result.citations.map((citation, idx) => (
                <CitationCard key={`${citation.doi ?? citation.pmid ?? idx}`} citation={citation} />
              ))}
            </ul>
          </>
        )}
      </div>
    </div>
  );
}
