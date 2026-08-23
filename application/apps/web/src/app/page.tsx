"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  getAnalysisProgress,
  getPublicHealth,
  getSyntheticPatient,
  listDemoPatients,
  listSyntheticPatients,
  parseExpressionFile,
  submitAnalysisAsync,
  submitDemoAnalysis,
  submitSyntheticAnalysis,
} from "@/lib/api";
import type { AnalysisProgress, DemoPatientSummary, PatientMetadata, PublicHealth, SyntheticPatientSummary } from "@/lib/types";
import { AnalyzingModal } from "@/components/AnalyzingModal";
import { cleanClinicalStatus } from "@/lib/format";

const SCENARIO_LABEL: Record<string, string> = {
  high_confidence: "High confidence",
  mixed_cluster: "Mixed cluster",
  low_quality: "Low-coverage / abstention",
};

const EMPTY_META: PatientMetadata = {
  age_at_diagnosis: null,
  er_status: null,
  her2_status: null,
  pr_status: null,
  histological_subtype: null,
  lymph_nodes_positive: null,
  menopausal_state: null,
  tumor_stage: null,
  tumor_grade: null,
  tumor_size_mm: null,
  ecog_status: null,
  prior_therapy: null,
};

const ENV_PUBLIC_DEMO = process.env.NEXT_PUBLIC_PUBLIC_DEMO_MODE === "true";

export default function HomePage() {
  const router = useRouter();
  const [health, setHealth] = useState<PublicHealth | null>(null);
  const [mode, setMode] = useState<"demo" | "synthetic" | "upload">("demo");
  const [patients, setPatients] = useState<SyntheticPatientSummary[] | null>(null);
  const [demoPatients, setDemoPatients] = useState<DemoPatientSummary[] | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [expression, setExpression] = useState<Record<string, number> | null>(null);
  const [uploadLabel, setUploadLabel] = useState("UPLOAD-LOCAL-001");
  const [metadata, setMetadata] = useState<PatientMetadata>(EMPTY_META);
  const [regimenText, setRegimenText] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [progress, setProgress] = useState<AnalysisProgress | null>(null);
  const [error, setError] = useState<string | null>(null);

  const publicDemo = health?.public_demo_mode ?? ENV_PUBLIC_DEMO;
  const allowUploads = health ? health.allow_custom_uploads : !ENV_PUBLIC_DEMO;

  useEffect(() => {
    getPublicHealth()
      .then(setHealth)
      .catch(() => setHealth(null));
    listDemoPatients()
      .then((data) => {
        setDemoPatients(data);
        setSelected((current) => current ?? data[0]?.patient_id ?? null);
      })
      .catch((err) => setError(String(err)));
    listSyntheticPatients()
      .then((data) => {
        setPatients(data);
      })
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    if (!allowUploads && mode === "upload") setMode("demo");
  }, [allowUploads, mode]);

  async function pollUntilDone(runId: string) {
    for (;;) {
      const next = await getAnalysisProgress(runId);
      setProgress(next);
      if (next.status === "completed") {
        router.push(`/analysis/${runId}`);
        return;
      }
      if (next.status === "failed") {
        throw new Error(next.error_message || "Analysis failed");
      }
      await new Promise((resolve) => setTimeout(resolve, 700));
    }
  }

  async function handleAnalyze() {
    setSubmitting(true);
    setError(null);
    setProgress(null);
    try {
      if (mode === "demo") {
        if (!selected) return;
        const ack = await submitDemoAnalysis(selected);
        await pollUntilDone(ack.run_id);
        return;
      }
      if (mode === "synthetic") {
        if (!selected) return;
        const ack = publicDemo
          ? await submitSyntheticAnalysis(selected)
          : await submitAnalysisAsync(await getSyntheticPatient(selected).then((patient) => ({
              patient_label: patient.synthetic_id,
              expression: patient.expression,
              metadata: patient.metadata,
              administered_regimen: patient.administered_regimen,
            })));
        await pollUntilDone(ack.run_id);
        return;
      }
      if (!expression) throw new Error("Upload a gene,expression CSV/TSV first.");
      const ack = await submitAnalysisAsync({
        patient_label: uploadLabel || "UPLOAD-LOCAL",
        expression,
        metadata,
        administered_regimen: regimenText
          .split(/[,+]/)
          .map((d) => d.trim().toLowerCase())
          .filter(Boolean),
      });
      await pollUntilDone(ack.run_id);
    } catch (err) {
      setError(String(err));
      setSubmitting(false);
    }
  }

  async function onFileChange(file: File | null) {
    if (!file) return;
    try {
      const text = await file.text();
      setExpression(parseExpressionFile(text));
      setError(null);
    } catch (err) {
      setExpression(null);
      setError(String(err));
    }
  }

  return (
    <main className="mx-auto max-w-6xl px-6 py-10 sm:py-16">
      <AnalyzingModal open={submitting} progress={progress} error={error} />

      <section className="overflow-hidden rounded-3xl border border-slate-200/80 bg-white shadow-xl shadow-slate-200/40">
        <div className="grid lg:grid-cols-[1.15fr_0.85fr]">
          <div className="px-7 py-10 sm:px-10 sm:py-14">
            <div className="inline-flex items-center gap-2 rounded-full border border-indigo-100 bg-indigo-50 px-3 py-1.5 text-xs font-semibold text-indigo-700">
              <span className="h-2 w-2 rounded-full bg-indigo-500" />
              Public oncology research demo
            </div>
            <h1 className="mt-5 max-w-2xl text-4xl font-semibold tracking-[-0.03em] text-slate-950 sm:text-5xl">
              Sets, not rankings — three held-out TCGA patients.
            </h1>
            <p className="mt-5 max-w-xl text-base leading-7 text-slate-500">
              Sample quality, latent position, molecular state, then a prediction set. One patient
              abstains on purpose. This is not a treatment recommendation.
            </p>
          </div>
          <div className="relative flex min-h-72 items-center justify-center overflow-hidden bg-gradient-to-br from-indigo-600 via-violet-600 to-fuchsia-600 p-10">
            <div className="relative w-full max-w-sm space-y-3 text-white">
              <div className="rounded-2xl border border-white/20 bg-white/10 p-4 backdrop-blur">
                <p className="text-[10px] font-semibold uppercase tracking-wider text-indigo-100">Workflow</p>
                <ol className="mt-3 space-y-2 text-sm">
                  <li>1. Choose a held-out TCGA patient</li>
                  <li>2. Read composition, position, and pathway state</li>
                  <li>3. A set — or an abstention — never a ranked best drug</li>
                </ol>
              </div>
            </div>
          </div>
        </div>
      </section>

      {error && !submitting && (
        <div className="mt-6 rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">{error}</div>
      )}

      <div className="mt-8 flex flex-wrap gap-2">
        {(
          [
            ["demo", "Held-out TCGA"],
            ["synthetic", "v1 synthetic"],
            ...(allowUploads ? ([["upload", "Upload RNA + metadata"]] as const) : []),
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            onClick={() => {
              setMode(id);
              if (id === "demo") setSelected(demoPatients?.[0]?.patient_id ?? null);
              if (id === "synthetic") setSelected(patients?.[0]?.synthetic_id ?? null);
            }}
            className={`rounded-full px-4 py-2 text-sm font-semibold ${
              mode === id ? "bg-indigo-600 text-white" : "bg-white text-slate-600 border border-slate-200"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {mode === "demo" && (
        <section className="mt-8">
          <h2 className="text-2xl font-semibold tracking-tight text-slate-950">Choose a held-out patient</h2>
          <p className="mt-2 text-sm text-slate-500">
            These three IDs were excluded from the VAE, PRECISE, and conformal fits.
          </p>
          {!demoPatients && !error && <p className="mt-8 text-sm text-slate-500">Loading demo patients…</p>}
          {demoPatients && (
            <div className="mt-6 grid gap-4 sm:grid-cols-3">
              {demoPatients.map((patient) => (
                <button
                  key={patient.patient_id}
                  onClick={() => setSelected(patient.patient_id)}
                  className={`relative overflow-hidden rounded-2xl border p-5 text-left transition ${
                    selected === patient.patient_id
                      ? "border-indigo-400 bg-indigo-50/70 shadow-md ring-2 ring-indigo-100"
                      : "border-slate-200 bg-white shadow-sm hover:-translate-y-0.5 hover:border-slate-300 hover:shadow-md"
                  }`}
                >
                  <span className="rounded-full bg-white px-2.5 py-1 text-[10px] font-bold uppercase tracking-wide text-indigo-700 shadow-sm">
                    {patient.role.replace(/_/g, " ")}
                  </span>
                  <div className="mt-4 font-mono text-xs text-slate-400">{patient.patient_id}</div>
                  <p className="mt-2 text-sm font-semibold text-slate-900">{patient.title}</p>
                  <p className="mt-2 min-h-16 text-sm leading-6 text-slate-600">{patient.description}</p>
                </button>
              ))}
            </div>
          )}
        </section>
      )}

      {mode === "synthetic" && (
        <section className="mt-8">
          <h2 className="text-2xl font-semibold tracking-tight text-slate-950">Choose a synthetic scenario</h2>
          {!patients && !error && <p className="mt-8 text-sm text-slate-500">Loading demonstration patients…</p>}
          {patients && (
            <div className="mt-6 grid gap-4 sm:grid-cols-3">
              {patients.map((patient) => (
                <button
                  key={patient.synthetic_id}
                  onClick={() => setSelected(patient.synthetic_id)}
                  className={`relative overflow-hidden rounded-2xl border p-5 text-left transition ${
                    selected === patient.synthetic_id
                      ? "border-indigo-400 bg-indigo-50/70 shadow-md ring-2 ring-indigo-100"
                      : "border-slate-200 bg-white shadow-sm hover:-translate-y-0.5 hover:border-slate-300 hover:shadow-md"
                  }`}
                >
                  <span className="rounded-full bg-white px-2.5 py-1 text-[10px] font-bold uppercase tracking-wide text-indigo-700 shadow-sm">
                    {SCENARIO_LABEL[patient.scenario] ?? patient.scenario}
                  </span>
                  <div className="mt-4 font-mono text-xs text-slate-400">{patient.synthetic_id}</div>
                  <p className="mt-2 min-h-16 text-sm leading-6 text-slate-600">{patient.description}</p>
                  <div className="mt-4 flex flex-wrap gap-2 text-[10px] font-semibold text-slate-500">
                    <span className="rounded-md bg-slate-100 px-2 py-1">ER {cleanClinicalStatus(patient.metadata.er_status)}</span>
                    <span className="rounded-md bg-slate-100 px-2 py-1">
                      Stage {String(patient.metadata.tumor_stage ?? "n/a")}
                    </span>
                  </div>
                </button>
              ))}
            </div>
          )}
        </section>
      )}

      {mode === "upload" && allowUploads && (
        <section className="mt-8 space-y-4 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h2 className="text-xl font-semibold text-slate-950">Upload normalized RNA</h2>
          <p className="text-sm text-slate-500">
            Local scientific mode only. CSV/TSV with <code>gene,expression</code>. Backend validation remains
            authoritative.
          </p>
          <input
            type="file"
            accept=".csv,.tsv,.txt"
            onChange={(e) => void onFileChange(e.target.files?.[0] ?? null)}
            className="block w-full text-sm"
          />
          {expression && (
            <p className="text-xs font-medium text-emerald-700">Parsed {Object.keys(expression).length} genes.</p>
          )}
          <label className="block text-xs font-semibold text-slate-600">
            Patient label
            <input
              value={uploadLabel}
              onChange={(e) => setUploadLabel(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
            />
          </label>
          <div className="grid gap-3 sm:grid-cols-3">
            {(
              [
                ["er_status", "ER status"],
                ["pr_status", "PR status"],
                ["her2_status", "HER2 status"],
                ["tumor_stage", "Stage"],
                ["prior_therapy", "Prior therapy"],
                ["menopausal_state", "Menopause"],
              ] as const
            ).map(([key, label]) => (
              <label key={key} className="text-xs font-semibold text-slate-600">
                {label}
                <input
                  value={String(metadata[key] ?? "")}
                  onChange={(e) => setMetadata({ ...metadata, [key]: e.target.value || null })}
                  className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
                />
              </label>
            ))}
            <label className="text-xs font-semibold text-slate-600">
              Age
              <input
                type="number"
                value={metadata.age_at_diagnosis ?? ""}
                onChange={(e) =>
                  setMetadata({
                    ...metadata,
                    age_at_diagnosis: e.target.value ? Number(e.target.value) : null,
                  })
                }
                className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
              />
            </label>
            <label className="text-xs font-semibold text-slate-600">
              ECOG
              <input
                type="number"
                value={metadata.ecog_status ?? ""}
                onChange={(e) =>
                  setMetadata({
                    ...metadata,
                    ecog_status: e.target.value ? Number(e.target.value) : null,
                  })
                }
                className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
              />
            </label>
            <label className="text-xs font-semibold text-slate-600">
              Administered regimen (comma-separated)
              <input
                value={regimenText}
                onChange={(e) => setRegimenText(e.target.value)}
                className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
                placeholder="paclitaxel, doxorubicin"
              />
            </label>
          </div>
        </section>
      )}

      <div className="mt-7 flex flex-wrap items-center gap-4">
        <button
          onClick={() => void handleAnalyze()}
          disabled={submitting || (mode === "upload" ? !expression : !selected)}
          className="rounded-xl bg-indigo-600 px-6 py-3 text-sm font-semibold text-white shadow-lg shadow-indigo-200 transition hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {submitting ? "Analyzing…" : "Run research analysis →"}
        </button>
        <p className="text-xs leading-5 text-slate-400">
          {publicDemo
            ? "Hosted demo: synthetic IDs only. No RNA is submitted or retained."
            : "Local mode can keep RNA on this machine. External services receive drug, target, or gene terms only."}
        </p>
      </div>
    </main>
  );
}
