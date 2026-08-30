"use client";

import type { AnalysisProgress } from "@/lib/types";

const FALLBACK_STAGE_ORDER = [
  "validate",
  "deconvolve",
  "encode_latent",
  "infer_activity",
  "project_sensitivity",
  "calibrate_set",
  "assemble",
];

export function AnalyzingModal({
  open,
  progress,
  error,
}: {
  open: boolean;
  progress: AnalysisProgress | null;
  error?: string | null;
}) {
  if (!open) return null;

  const STAGE_ORDER =
    progress?.stages?.length
      ? [...new Set(progress.stages.map((stage) => stage.stage_id))]
      : FALLBACK_STAGE_ORDER;

  const latestByStage = new Map<string, string>();
  for (const stage of progress?.stages ?? []) {
    const previous = latestByStage.get(stage.stage_id);
    if (previous === "completed" || previous === "failed") continue;
    latestByStage.set(stage.stage_id, stage.status);
  }
  const completedStages = STAGE_ORDER.filter((stageId) => latestByStage.get(stageId) === "completed").length;
  const progressPercent = (completedStages / STAGE_ORDER.length) * 100;
  const currentStageLabel = progress?.stages.find(
    (stage) => stage.stage_id === progress.current_stage
  )?.label;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-[rgba(6,10,16,0.55)] p-4 backdrop-blur-sm">
      <div className="panel w-full max-w-lg p-6">
        <p className="eyebrow">Analysis in progress</p>
        <h2 className="mt-2 text-lg font-semibold text-[var(--text-primary)]">Building the evidence workspace</h2>
        <p className="mt-2 text-[13px] text-[var(--text-secondary)]">
          Stages reflect real backend progress. No artificial delays are added.
        </p>
        <div className="well mt-5 overflow-hidden p-4">
          <div className="flex items-center gap-5">
            <div className="relative h-24 w-24 shrink-0" aria-hidden="true">
              <div className="absolute inset-2 animate-spin rounded-full border border-dashed border-[var(--line-strong)] [animation-duration:8s]" />
              <div className="absolute inset-5 animate-spin rounded-full border-2 border-cyan-300 border-l-transparent [animation-direction:reverse] [animation-duration:3s]" />
              <div className="absolute left-1/2 top-1/2 h-8 w-8 -translate-x-1/2 -translate-y-1/2 animate-pulse rounded-full bg-[var(--cluster-1)]" />
              <span className="absolute left-1 top-1/2 h-2 w-2 animate-pulse rounded-full bg-fuchsia-400" />
              <span className="absolute right-2 top-3 h-2.5 w-2.5 animate-bounce rounded-full bg-cyan-400 [animation-duration:2s]" />
              <span className="absolute bottom-2 left-1/2 h-1.5 w-1.5 animate-ping rounded-full bg-[var(--cluster-1)]" />
            </div>
            <div className="min-w-0 flex-1">
              <p className="eyebrow">Molecular signal scan</p>
              <p className="mt-1 text-[13px] font-medium text-[var(--text-primary)]">
                {currentStageLabel ?? "Preparing patient expression profile"}
              </p>
              <p className="mt-1 text-[11px] text-[var(--text-muted)]">{completedStages} of {STAGE_ORDER.length} analysis stages complete</p>
              <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-[var(--line)]">
                <div
                  className="h-full rounded-full bg-[var(--cluster-1)] transition-all duration-700"
                  style={{ width: `${progressPercent}%` }}
                />
              </div>
            </div>
          </div>
        </div>
        <ol className="mt-5 space-y-2">
          {STAGE_ORDER.map((stageId) => {
            const status = latestByStage.get(stageId);
            const label =
              progress?.stages.find((s) => s.stage_id === stageId)?.label ??
              stageId.replace(/_/g, " ");
            const done = status === "completed";
            const failed = status === "failed";
            const active = !done && !failed && (progress?.current_stage === stageId || status === "running");
            return (
              <li
                key={stageId}
                className={`flex items-center gap-3 rounded-xl border px-3 py-2 text-sm ${
                  failed
                    ? "border-[var(--line)] text-[var(--progression)]"
                    : done
                      ? "border-[var(--line)] text-[var(--response)]"
                      : active
                        ? "border-[var(--line-strong)] text-[var(--text-primary)]"
                        : "border-[var(--line)] text-[var(--text-muted)]"
                }`}
              >
                <span className={`font-mono text-[10px] uppercase ${active ? "animate-pulse" : ""}`}>
                  {done ? "done" : active ? "run" : "wait"}
                </span>
                <span className="capitalize">{label}</span>
              </li>
            );
          })}
        </ol>
        {error && <p className="mt-4 rounded-[var(--radius-inner)] border border-[color-mix(in_oklab,var(--progression)_35%,transparent)] p-3 text-sm text-[var(--progression)]">{error}</p>}
      </div>
    </div>
  );
}
