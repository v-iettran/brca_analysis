"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { getAnalysis, getPublicHealth, getRationale, recalculateAnalysis } from "@/lib/api";
import type { ActiveView, AnalysisResult, GroundedRationale } from "@/lib/types";
import { CopilotPanel } from "@/components/CopilotPanel";
import { ExportButtons } from "@/components/ExportButtons";
import { OverlapNominationCards } from "@/components/OverlapNominationCards";
import { PredictorCombinationPanel } from "@/components/PredictorCombinationPanel";
import { PatientProfileCard } from "@/components/PatientProfileCard";
import { RationaleCard } from "@/components/RationaleCard";
import { RnaUmapPanel } from "@/components/RnaUmapPanel";
import { SignaturePanels } from "@/components/SignaturePanels";
import { TrialExplorer } from "@/components/TrialExplorer";
import { WarningsPanel } from "@/components/WarningsPanel";
import { PrototypeWorkspace } from "@/components/PrototypeWorkspace";
import { V3Workspace } from "@/components/V3Workspace";
import { cleanClinicalStatus } from "@/lib/format";

export default function ClinicianAnalysisPage() {
  const params = useParams<{ runId: string }>();
  const runId = params.runId;
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedDrug, setSelectedDrug] = useState<string | null>(null);
  const [activeView, setActiveView] = useState<ActiveView>("patient_analysis");
  const [recalculating, setRecalculating] = useState(false);
  const [rationale, setRationale] = useState<GroundedRationale | null>(null);
  const [publicDemo, setPublicDemo] = useState(process.env.NEXT_PUBLIC_PUBLIC_DEMO_MODE === "true");

  useEffect(() => {
    getPublicHealth()
      .then((health) => setPublicDemo(health.public_demo_mode))
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    getAnalysis(runId)
      .then((data) => {
        setResult(data);
        setSelectedDrug(data.overlap_nominations?.[0]?.drug ?? data.top_candidate_drugs?.[0]?.drug ?? null);
      })
      .catch((err) => setError(String(err)));
  }, [runId]);

  useEffect(() => {
    if (!result) return;
    getRationale(runId, selectedDrug)
      .then(setRationale)
      .catch(() => setRationale(null));
  }, [runId, result, selectedDrug]);

  async function handleRecalculate(topUp: number, topDown: number) {
    setRecalculating(true);
    setError(null);
    try {
      const next = await recalculateAnalysis(runId, topUp, topDown);
      setResult(next);
      setSelectedDrug(next.overlap_nominations?.[0]?.drug ?? selectedDrug);
    } catch (err) {
      setError(String(err));
    } finally {
      setRecalculating(false);
    }
  }

  if (error && !result) {
    return (
      <main className="mx-auto max-w-4xl px-6 py-12">
        <p className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-rose-700">{error}</p>
        <Link href="/" className="mt-4 inline-block text-indigo-700 underline">
          Back to patient selection
        </Link>
      </main>
    );
  }

  if (!result) {
    return (
      <main className="mx-auto max-w-4xl px-6 py-16">
        <div className="h-2 w-32 animate-pulse rounded-full bg-indigo-200" />
        <p className="mt-4 text-sm text-slate-500">Loading the patient evidence workspace…</p>
      </main>
    );
  }

  const cluster = result.cluster_prediction;
  const selectedCluster = cluster?.top_cluster ?? null;
  const metadataSummary = [
    `ER ${cleanClinicalStatus(result.patient_metadata.er_status)}`,
    `PR ${cleanClinicalStatus(result.patient_metadata.pr_status)}`,
    `HER2 ${result.patient_metadata.her2_status ?? "n/a"}`,
    `Stage ${result.patient_metadata.tumor_stage ?? "n/a"}`,
    `ECOG ${result.patient_metadata.ecog_status ?? "n/a"}`,
  ].join(" · ");
  const summary = result.analysis_summary;
  const headlines = summary?.headline_nominations || result.overlap_nominations?.slice(0, 3) || [];

  return (
    <main className="mx-auto max-w-[1720px] px-4 py-6 sm:px-6 lg:px-8">
      <header className="mb-5 flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <Link
            href="/"
            className="flex h-10 w-10 items-center justify-center rounded-xl border border-slate-200 bg-white text-lg text-slate-500 shadow-sm transition hover:bg-slate-50"
            aria-label="Back to patient selection"
          >
            ←
          </Link>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-xl font-semibold tracking-tight text-slate-950">
              {result.prototype ? "Patient evidence workspace" : "Overlap evidence workspace"}
            </h1>
              <span className="rounded-full bg-emerald-50 px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-emerald-700">
                Rev {result.revision ?? 0}
              </span>
            </div>
            <p className="mt-0.5 text-xs text-slate-400">
              Immutable run <span className="font-mono">{result.run_id.slice(0, 8)}</span> ·{" "}
              {new Date(result.created_at).toLocaleString()}
            </p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex rounded-xl border border-slate-200 bg-white p-1 shadow-sm">
            {(
              [
                ["patient_analysis", "Patient Analysis"],
                ["clinical_trials", "Clinical Trials"],
              ] as const
            ).map(([id, label]) => (
              <button
                key={id}
                onClick={() => setActiveView(id)}
                className={`rounded-lg px-3 py-1.5 text-xs font-semibold ${
                  activeView === id ? "bg-indigo-600 text-white" : "text-slate-600"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
          <ExportButtons runId={result.run_id} />
          <Link
            href={`/analysis/${runId}/technical`}
            className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-600 shadow-sm transition hover:bg-slate-50"
          >
            Technical audit →
          </Link>
        </div>
      </header>

      {error && (
        <div className="mb-4 rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">{error}</div>
      )}

      <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1.75fr)_minmax(340px,0.75fr)]">
        <div className="min-w-0 space-y-5">
          <section className="rounded-2xl border border-indigo-100 bg-indigo-50/40 p-5 shadow-sm">
            <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-indigo-600">
              What this analysis found
            </p>
            <h2 className="mt-1 text-lg font-semibold text-slate-950">
              {result.prototype
                ? `${result.patient_label} · ${result.prototype.modalities_present.join(" + ") || "no modalities"}`
                : `Cluster ${cluster?.top_cluster ?? "—"} · ${cluster?.confidence_level ?? "unknown"} confidence`}
            </h2>
            <p className="mt-1 text-sm text-slate-600">
              {result.prototype
                ? result.prototype.description || "Held-out TCGA prototype patient. Sets, not rankings."
                : `${cluster ? `${(cluster.top_probability * 100).toFixed(0)}% RNA-only assignment` : "Cluster unavailable"}.
              Up to three default-visible research nominations are shown; this is not a treatment ranking.`}
            </p>
            {!result.prototype && (
            <ol className="mt-3 space-y-1 text-sm text-slate-700">
              {headlines.map((row, index) => (
                <li key={`${row.drug}-${index}`}>
                  {index + 1}. {row.drug}{" "}
                  <span className="text-xs text-slate-500">
                    {row.human_development_label || "research nomination"}
                    {row.weaker_percentile != null ? ` · dual-support ${(row.weaker_percentile * 100).toFixed(0)}%` : ""}
                  </span>
                </li>
              ))}
              {headlines.length === 0 && <li>No default-visible human-use compounds for this scenario.</li>}
            </ol>
            )}
            <p className="mt-3 text-xs text-amber-800">
              Dominant uncertainty: {summary?.dominant_uncertainty || result.limitations?.[0] || "Research signals only."}
            </p>
          </section>

          <RationaleCard rationale={rationale} />

          <div id="patient">
            <PatientProfileCard
              patientLabel={result.patient_label}
              metadata={result.patient_metadata}
              regimen={result.administered_regimen}
            />
          </div>

          <WarningsPanel warnings={result.warnings} />

          {activeView === "patient_analysis" ? (
            <>
              {result.v3_cohort && result.v3_patient ? (
                <V3Workspace cohort={result.v3_cohort} patient={result.v3_patient} />
              ) : result.prototype ? (
                <PrototypeWorkspace payload={result.prototype} />
              ) : (
                <>
              <div id="drug">
                <OverlapNominationCards
                  nominations={result.overlap_nominations || []}
                  exploratory={result.overlap_exploratory || []}
                  technicalExcluded={result.overlap_technical_excluded || []}
                  combinations={result.almanac_combinations || []}
                  clinicalComparators={result.clinical_comparators || []}
                  runId={result.run_id}
                  selectedDrug={selectedDrug}
                  onSelectDrug={setSelectedDrug}
                />
              </div>
              <details className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                <summary className="cursor-pointer text-sm font-semibold text-slate-900">
                  Advanced / methods: signatures, projection, and Predictor equations
                </summary>
                <div className="mt-4 space-y-4">
                  {result.rna_projection && <RnaUmapPanel projection={result.rna_projection} />}
                  <div id="mofa">
                    <SignaturePanels
                      clusterSignature={result.cluster_signature}
                      residualSignature={result.residual_signature}
                      topUp={result.signature_params?.top_up ?? 150}
                      topDown={result.signature_params?.top_down ?? 150}
                      onRecalculate={handleRecalculate}
                      recalculating={recalculating}
                      allowRecalculate={!publicDemo}
                      runId={result.run_id}
                      clusterId={result.cluster_prediction?.top_cluster ?? 1}
                    />
                  </div>
                  <PredictorCombinationPanel combinations={result.predictor_combinations || []} />
                </div>
              </details>
                </>
              )}
              {(result.limitations || []).length > 0 && (
                <section className="rounded-2xl border border-amber-200 bg-amber-50/60 p-4 text-xs text-amber-900">
                  <h3 className="font-semibold">Scientific limitations</h3>
                  <ul className="mt-2 list-disc space-y-1 pl-4">
                    {(result.limitations || []).map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </section>
              )}
            </>
          ) : (
            <div id="trial">
              <TrialExplorer
                runId={result.run_id}
                patientLabel={result.patient_label}
                metadataSummary={metadataSummary}
              />
            </div>
          )}
        </div>

        <CopilotPanel
          runId={result.run_id}
          selectedDrug={selectedDrug}
          selectedCluster={selectedCluster}
          activeView={activeView}
        />
      </div>
    </main>
  );
}
