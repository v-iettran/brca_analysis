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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/50 p-4 backdrop-blur-sm">
      <div className="w-full max-w-lg rounded-2xl border border-slate-200 bg-white p-6 shadow-2xl">
        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-indigo-600">Analysis in progress</p>
        <h2 className="mt-2 text-xl font-semibold text-slate-950">Building the evidence workspace</h2>
        <p className="mt-2 text-sm text-slate-500">
          Stages reflect real backend progress. No artificial delays are added.
        </p>
        <div className="mt-5 overflow-hidden rounded-2xl border border-indigo-100 bg-gradient-to-br from-indigo-50 via-white to-cyan-50 p-4">
          <div className="flex items-center gap-5">
            <div className="relative h-24 w-24 shrink-0" aria-hidden="true">
              <div className="absolute inset-2 animate-spin rounded-full border border-dashed border-indigo-300 [animation-duration:8s]" />
              <div className="absolute inset-5 animate-spin rounded-full border-2 border-cyan-300 border-l-transparent [animation-direction:reverse] [animation-duration:3s]" />
              <div className="absolute left-1/2 top-1/2 h-8 w-8 -translate-x-1/2 -translate-y-1/2 animate-pulse rounded-full bg-gradient-to-br from-indigo-500 to-cyan-400 shadow-lg shadow-indigo-200" />
              <span className="absolute left-1 top-1/2 h-2 w-2 animate-pulse rounded-full bg-fuchsia-400" />
              <span className="absolute right-2 top-3 h-2.5 w-2.5 animate-bounce rounded-full bg-cyan-400 [animation-duration:2s]" />
              <span className="absolute bottom-2 left-1/2 h-1.5 w-1.5 animate-ping rounded-full bg-indigo-500" />
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-xs font-semibold uppercase tracking-wider text-indigo-600">Molecular signal scan</p>
              <p className="mt-1 text-sm font-medium text-slate-800">
                {currentStageLabel ?? "Preparing patient expression profile"}
              </p>
              <p className="mt-1 text-xs text-slate-500">{completedStages} of {STAGE_ORDER.length} analysis stages complete</p>
              <div className="mt-3 h-2 overflow-hidden rounded-full bg-white shadow-inner">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-indigo-500 via-violet-500 to-cyan-400 transition-all duration-700"
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
                    ? "border-rose-200 bg-rose-50 text-rose-800"
                    : done
                      ? "border-emerald-200 bg-emerald-50 text-emerald-800"
                      : active
                        ? "border-indigo-200 bg-indigo-50 text-indigo-800"
                        : "border-slate-100 bg-slate-50 text-slate-500"
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
        {error && <p className="mt-4 rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">{error}</p>}
      </div>
    </div>
  );
}
