"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { getAnalysis, getAnalysisAudit } from "@/lib/api";
import type { AnalysisResult, AuditEvent } from "@/lib/types";
import { TechnicalAuditPanel } from "@/components/TechnicalAuditPanel";

export default function TechnicalAnalysisPage() {
  const params = useParams<{ runId: string }>();
  const runId = params.runId;
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [events, setEvents] = useState<AuditEvent[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([getAnalysis(runId), getAnalysisAudit(runId)])
      .then(([res, aud]) => {
        setResult(res);
        setEvents(aud);
      })
      .catch((err) => setError(String(err)));
  }, [runId]);

  if (error) {
    return (
      <main className="max-w-5xl mx-auto px-6 py-12">
        <p className="text-red-700">{error}</p>
      </main>
    );
  }

  if (!result || !events) {
    return (
      <main className="max-w-5xl mx-auto px-6 py-12">
        <p className="text-slate-500">Loading technical audit…</p>
      </main>
    );
  }

  const cluster = result.cluster_prediction;

  return (
    <main className="max-w-5xl mx-auto px-6 py-10 space-y-8">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Technical view</h1>
          <p className="mt-1 text-sm text-slate-500">
            Run <span className="font-mono">{result.run_id}</span> · status {result.status}
          </p>
        </div>
        <Link
          href={`/analysis/${runId}`}
          className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
        >
          ← Back to clinician view
        </Link>
      </div>

      <section className="rounded-xl border border-slate-200 bg-white p-5">
        <h2 className="text-base font-semibold text-slate-900">Model / artifact versions</h2>
        <dl className="mt-3 grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
          <div>
            <dt className="text-xs text-slate-400">Classifier method</dt>
            <dd className="font-mono">{cluster?.method_used}</dd>
          </div>
          <div>
            <dt className="text-xs text-slate-400">Gene coverage</dt>
            <dd>
              {cluster
                ? `${(cluster.gene_coverage * 100).toFixed(1)}% of classifier genes (${cluster.genes_found}/${cluster.genes_requested})`
                : "n/a"}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-slate-400">Confidence level</dt>
            <dd className="capitalize">{cluster?.confidence_level}</dd>
          </div>
          <div>
            <dt className="text-xs text-slate-400">Regimen</dt>
            <dd>{result.administered_regimen.join(", ") || "none"}</dd>
          </div>
        </dl>
      </section>

      {result.administered_regimen_pcr && (
        <section className="rounded-xl border border-slate-200 bg-white p-5">
          <h2 className="text-base font-semibold text-slate-900">pCR applicability gate</h2>
          <pre className="mt-3 overflow-x-auto rounded-md bg-slate-900 p-4 text-xs text-slate-100">
            {JSON.stringify(result.administered_regimen_pcr, null, 2)}
          </pre>
        </section>
      )}

      <section>
        <h2 className="text-base font-semibold text-slate-900 mb-3">
          Reproducibility log — every deterministic tool call in this run
        </h2>
        <TechnicalAuditPanel events={events} />
      </section>

      <section className="rounded-xl border border-slate-200 bg-white p-5">
        <h2 className="text-base font-semibold text-slate-900">Raw cluster probabilities</h2>
        <pre className="mt-3 overflow-x-auto rounded-md bg-slate-900 p-4 text-xs text-slate-100">
          {JSON.stringify(cluster, null, 2)}
        </pre>
      </section>
    </main>
  );
}
