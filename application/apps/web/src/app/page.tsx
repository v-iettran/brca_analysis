"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  getAnalysisProgress,
  getPublicHealth,
  listDemoPatients,
  parseExpressionFile,
  submitAnalysisAsync,
  submitDemoAnalysis,
} from "@/lib/api";
import type { AnalysisProgress, DemoPatientSummary, PatientMetadata, PublicHealth, SyntheticPatientSummary } from "@/lib/types";
import { AnalyzingModal } from "@/components/AnalyzingModal";

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
  const [mode, setMode] = useState<"demo" | "upload">("demo");
  const [demoPatients, setDemoPatients] = useState<DemoPatientSummary[] | null>(null);
  // Free instances sleep after ~15 minutes idle. The first visitor after that
  // waits about a minute, and silence for a minute reads as a broken page.
  const [waking, setWaking] = useState(false);
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
    listDemoPatients({ onRetry: () => setWaking(true) })
      .then((data) => {
        setWaking(false);
        setDemoPatients(data);
        setSelected((current) => current ?? data[0]?.patient_id ?? null);
      })
      .catch((err) => {
        setWaking(false);
        setError(String(err));
      });
  }, []);

  // Adjust during render rather than in an effect: uploads can be disabled by
  // the server after the page has already chosen a mode.
  if (!allowUploads && mode === "upload") setMode("demo");

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
    <main className="mx-auto max-w-6xl px-6 py-10 sm:py-14">
      <AnalyzingModal open={submitting} progress={progress} error={error} />

      {/* No decorative gradient. The panel that sat here was an indigo-to-fuchsia
          wash carrying no information; in a clinical tool every visual element
          should encode something. */}
      <section className="panel p-7 sm:p-9">
        <p className="eyebrow">Breast cancer research panel demo</p>
        <h1 className="mt-3 text-3xl font-semibold tracking-[-0.025em] text-[var(--text-primary)] sm:text-4xl">
          Patient analysis from molecular profile.
        </h1>
        <p className="mt-4 text-[15px] leading-7 text-[var(--text-secondary)]">
          This panel takes bulk RNA from a breast tumour and works out which molecular subgroup it
          belongs to, what defines that subgroup, and which laboratory evidence exists for it — showing
          its working at every step, including where the evidence runs out.
        </p>

        <ol className="mt-6 grid gap-x-8 gap-y-4 sm:grid-cols-2">
          {[
            [
              "Separate the tumour from its surroundings",
              "Bulk RNA is deconvolved against a single-cell breast reference, so the signal is the malignant cells rather than the immune and stromal cells mixed in with them.",
            ],
            [
              "Fix the number of subgroups in advance",
              "k is chosen from BIC, silhouette and bootstrap stability, and frozen before survival is looked at, so only that pre-registered split may report a log-rank p-value.",
            ],
            [
              "Say what defines each subgroup",
              "Every pathway, transcription factor and gene is tested one-vs-rest and against adjacent normal tissue, with literature standing shown beside each result.",
            ],
            [
              "Show what was measured, not inferred",
              "Similar cell lines come from DepMap with their real GDSC dose-response curves, and compounds are retrieved by signature reversal against LINCS.",
            ],
          ].map(([title, body], index) => (
            <li key={title} className="flex gap-3">
              <span className="mt-0.5 font-mono text-[12px] tabular-nums text-[var(--text-muted)]">
                {index + 1}
              </span>
              <span>
                <span className="block text-[13.5px] font-semibold text-[var(--text-primary)]">{title}</span>
                <span className="mt-0.5 block text-[13px] leading-6 text-[var(--text-secondary)]">{body}</span>
              </span>
            </li>
          ))}
        </ol>

        <p className="mt-6 text-[15px] leading-7 text-[var(--text-primary)]">
          Go ahead and try out held-out profiles from TCGA-BRCA.
        </p>

        <dl className="mt-7 grid gap-x-8 gap-y-4 border-t border-[var(--line)] pt-6 sm:grid-cols-3">
          {[
            ["1082", "TCGA-BRCA tumours", "the full cohort, no generated samples"],
            ["4", "pre-registered subgroups", "selected from structure alone"],
            ["151", "overall-survival events", "what the log-rank test rests on"],
          ].map(([value, label, note]) => (
            <div key={label}>
              <dt className="readout text-[var(--text-primary)]">{value}</dt>
              <dd className="mt-1.5 text-[13px] font-medium text-[var(--text-secondary)]">{label}</dd>
              <dd className="mt-0.5 text-[11px] text-[var(--text-muted)]">{note}</dd>
            </div>
          ))}
        </dl>

        <p className="mt-6 text-[12px] text-[var(--text-muted)]">
          Compounds are shown as evidence, not as recommendations. This is a research prototype, not a
          clinical decision-support device.
        </p>
      </section>

      {error && !submitting && (
        <div className="mt-6 rounded-[var(--radius-inner)] border border-[color-mix(in_oklab,var(--progression)_35%,transparent)] bg-[color-mix(in_oklab,var(--progression)_8%,transparent)] p-4 text-sm text-[var(--progression)]">{error}</div>
      )}

      <div className="mt-8 flex flex-wrap gap-2">
        {(
          [
            ["demo", "Held-out TCGA"],
            ...(allowUploads ? ([["upload", "Upload RNA + metadata"]] as const) : []),
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            onClick={() => {
              setMode(id);
              if (id === "demo") setSelected(demoPatients?.[0]?.patient_id ?? null);
            }}
            className="pressable border border-[var(--line)] bg-[var(--surface)] px-3.5 py-1.5 text-[13px] font-medium text-[var(--text-secondary)]"
            aria-pressed={mode === id}
          >
            {label}
          </button>
        ))}
      </div>

      {mode === "demo" && (
        <section className="mt-8">
          <h2 className="text-xl font-semibold tracking-tight text-[var(--text-primary)]">Choose a held-out patient</h2>
          <p className="mt-2 text-[13px] text-[var(--text-secondary)]">
            These three profiles were held out of every fit behind this panel.
          </p>
          {!demoPatients && !error && (
            <p className="mt-6 text-sm text-[var(--text-muted)]">
              {waking ? (
                <>
                  Starting the analysis server…{" "}
                  <span className="text-[var(--text-muted)] opacity-80">
                    It sleeps when idle and takes about a minute to wake. This page will continue on
                    its own.
                  </span>
                </>
              ) : (
                "Loading demo patients…"
              )}
            </p>
          )}
          {demoPatients && (
            <div className="mt-6 grid gap-4 sm:grid-cols-3">
              {demoPatients.map((patient) => (
                <button
                  key={patient.patient_id}
                  onClick={() => setSelected(patient.patient_id)}
                  className={`relative overflow-hidden rounded-2xl border p-5 text-left transition ${
                    selected === patient.patient_id
                      ? "border-[var(--cluster-1)] bg-[var(--surface-raised)]"
                      : "border-[var(--line)] bg-[var(--surface)] hover:border-[var(--line-strong)]"
                  }`}
                >
                  <span className="rounded border border-[var(--line-strong)] px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-[var(--text-secondary)]">
                    {patient.role.replace(/_/g, " ")}
                  </span>
                  <div className="mt-4 font-mono text-xs text-[var(--text-muted)]">{patient.patient_id}</div>
                  <p className="mt-2 text-sm font-semibold text-[var(--text-primary)]">{patient.title}</p>
                  <p className="mt-2 min-h-16 text-sm leading-6 text-[var(--text-secondary)]">{patient.description}</p>
                </button>
              ))}
            </div>
          )}
        </section>
      )}

      {mode === "upload" && allowUploads && (
        <section className="panel mt-6 space-y-4 p-6">
          <h2 className="text-lg font-semibold text-[var(--text-primary)]">Upload normalized RNA</h2>
          <p className="text-sm text-[var(--text-secondary)]">
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
            <p className="text-xs font-medium text-[var(--response)]">Parsed {Object.keys(expression).length} genes.</p>
          )}
          <label className="block text-xs font-medium text-[var(--text-secondary)]">
            Patient label
            <input
              value={uploadLabel}
              onChange={(e) => setUploadLabel(e.target.value)}
              className="mt-1 w-full rounded-[var(--radius-inner)] border border-[var(--line)] bg-[var(--surface)] px-3 py-2 text-sm text-[var(--text-primary)]"
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
              <label key={key} className="text-xs font-medium text-[var(--text-secondary)]">
                {label}
                <input
                  value={String(metadata[key] ?? "")}
                  onChange={(e) => setMetadata({ ...metadata, [key]: e.target.value || null })}
                  className="mt-1 w-full rounded-[var(--radius-inner)] border border-[var(--line)] bg-[var(--surface)] px-3 py-2 text-sm text-[var(--text-primary)]"
                />
              </label>
            ))}
            <label className="text-xs font-medium text-[var(--text-secondary)]">
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
                className="mt-1 w-full rounded-[var(--radius-inner)] border border-[var(--line)] bg-[var(--surface)] px-3 py-2 text-sm text-[var(--text-primary)]"
              />
            </label>
            <label className="text-xs font-medium text-[var(--text-secondary)]">
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
                className="mt-1 w-full rounded-[var(--radius-inner)] border border-[var(--line)] bg-[var(--surface)] px-3 py-2 text-sm text-[var(--text-primary)]"
              />
            </label>
            <label className="text-xs font-medium text-[var(--text-secondary)]">
              Administered regimen (comma-separated)
              <input
                value={regimenText}
                onChange={(e) => setRegimenText(e.target.value)}
                className="mt-1 w-full rounded-[var(--radius-inner)] border border-[var(--line)] bg-[var(--surface)] px-3 py-2 text-sm text-[var(--text-primary)]"
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
          className="rounded-[var(--radius-inner)] bg-[var(--cluster-1)] px-6 py-3 text-sm font-semibold text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {submitting ? "Analyzing…" : "Run research analysis →"}
        </button>
        <p className="text-xs leading-5 text-[var(--text-muted)]">
          {publicDemo
            ? "Hosted demo: held-out TCGA profiles only. No RNA is submitted or retained."
            : "Local mode can keep RNA on this machine. External services receive drug, target, or gene terms only."}
        </p>
      </div>
    </main>
  );
}
