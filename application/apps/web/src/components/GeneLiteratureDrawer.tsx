"use client";

import { useEffect, useState } from "react";
import { getGeneLiterature } from "@/lib/api";
import type { GeneLiteratureResult } from "@/lib/types";

export function GeneLiteratureDrawer({
  runId,
  clusterId,
  gene,
  onClose,
}: {
  runId: string;
  clusterId: number;
  gene: string;
  onClose: () => void;
}) {
  const [result, setResult] = useState<GeneLiteratureResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getGeneLiterature(runId, clusterId, gene).then(setResult).catch((err) => setError(String(err)));
  }, [runId, clusterId, gene]);

  return (
    <div className="fixed inset-0 z-50 bg-slate-950/35 backdrop-blur-sm" onClick={onClose}>
      <aside
        className="ml-auto flex h-full w-full max-w-xl flex-col border-l border-slate-200 bg-white shadow-2xl"
        onClick={(event) => event.stopPropagation()}
        aria-label={`Literature for ${gene}`}
      >
        <header className="flex items-start justify-between border-b border-slate-100 px-6 py-5">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-indigo-600">
              Cluster {clusterId} gene context
            </p>
            <h2 className="mt-1 text-2xl font-semibold tracking-tight text-slate-950">{gene}</h2>
            <p className="mt-1 text-sm text-slate-500">Breast-cancer literature retrieved through Paperclip</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-full border border-slate-200 px-3 py-1.5 text-sm text-slate-500 transition hover:bg-slate-50"
            aria-label="Close gene literature"
          >
            Close
          </button>
        </header>

        <div className="flex-1 overflow-y-auto px-6 py-5">
          {!result && !error && (
            <div className="rounded-xl border border-indigo-100 bg-indigo-50 p-4 text-sm text-indigo-700">
              Searching gene-focused reviews and breast-cancer literature…
            </div>
          )}
          {error && <p className="rounded-xl bg-rose-50 p-4 text-sm text-rose-700">{error}</p>}
          {result?.unavailable_reason && (
            <p className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
              {result.unavailable_reason}
            </p>
          )}

          {result && (
            <>
              <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
                <div className="flex items-center justify-between gap-3">
                  <span className="text-sm font-medium text-slate-700">Published context</span>
                  <span className="rounded-full bg-white px-2.5 py-1 text-xs font-semibold text-slate-600 shadow-sm">
                    {result.deduplicated_count} unique papers
                  </span>
                </div>
                <p className="mt-2 text-xs leading-5 text-slate-500">{result.interpretation_note}</p>
              </div>

              <details open className="mt-4 rounded-xl border border-slate-200 px-4 py-3 text-xs text-slate-500">
                <summary className="cursor-pointer font-semibold text-slate-700">
                  Keywords and exact search queries · {result.raw_result_count} raw results
                </summary>
                <ul className="mt-3 space-y-2">
                  {result.query_families.map((family) => (
                    <li key={family.label}>
                      <span className="font-medium text-slate-700">{family.label.replaceAll("_", " ")}</span>
                      <span className="ml-2">({family.result_count})</span>
                      <div className="mt-0.5 font-mono text-[11px] text-slate-400">{family.query_text}</div>
                    </li>
                  ))}
                </ul>
              </details>
              <p className="mt-3 rounded-xl bg-indigo-50 p-3 text-xs leading-5 text-indigo-800">
                Ranked by 55% text/query relevance and 45% publication-metadata credibility. This ordering is
                transparent retrieval support, not validation of the expression coefficient.
              </p>

              <ul className="mt-5 space-y-3">
                {result.citations.map((citation, index) => (
                  <li key={citation.doi ?? citation.pmid ?? `${citation.title}-${index}`} className="rounded-xl border border-slate-200 p-4">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="text-[10px] font-semibold uppercase tracking-wide text-indigo-600">
                          Evidence rank #{citation.evidence_rank ?? "—"} · combined {citation.combined_score?.toFixed(1) ?? "n/a"}
                        </p>
                        <h3 className="mt-0.5 text-sm font-semibold leading-5 text-slate-900">{citation.title}</h3>
                      </div>
                      <span className="shrink-0 rounded-full bg-slate-100 px-2 py-1 text-[10px] font-semibold uppercase text-slate-600">
                        {citation.stance}
                      </span>
                    </div>
                    <p className="mt-1 text-xs text-slate-500">
                      {[citation.journal, citation.year, citation.article_type].filter(Boolean).join(" · ")}
                    </p>
                    <p className="mt-1 text-xs text-slate-500">
                      Credibility {citation.credibility_score?.toFixed(0) ?? "n/a"}/100 · Relevance{" "}
                      {citation.relevance_score?.toFixed(0) ?? "n/a"}/100
                    </p>
                    {citation.excerpt && (
                      <p className="mt-3 line-clamp-4 text-sm leading-6 text-slate-600">
                        {citation.excerpt}
                      </p>
                    )}
                    <div className="mt-3 flex gap-3 text-xs font-medium">
                      {citation.doi && (
                        <a href={`https://doi.org/${citation.doi}`} target="_blank" rel="noreferrer" className="text-indigo-600 hover:underline">
                          DOI
                        </a>
                      )}
                      {citation.pmid && (
                        <a href={`https://pubmed.ncbi.nlm.nih.gov/${citation.pmid}`} target="_blank" rel="noreferrer" className="text-indigo-600 hover:underline">
                          PubMed
                        </a>
                      )}
                    </div>
                  </li>
                ))}
                {result.citations.length === 0 && !result.unavailable_reason && (
                  <li className="rounded-xl border border-dashed border-slate-300 p-6 text-center text-sm text-slate-500">
                    No matching papers were returned for this gene.
                  </li>
                )}
              </ul>
            </>
          )}
        </div>
      </aside>
    </div>
  );
}
