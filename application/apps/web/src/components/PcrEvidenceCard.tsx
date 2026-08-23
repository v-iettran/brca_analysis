import type { SupportedPcrResult } from "@/lib/types";

export function PcrEvidenceCard({ pcr, regimen }: { pcr: SupportedPcrResult; regimen: string[] }) {
  const gate = pcr.applicability_gate;
  const available = pcr.pcr_probability != null;

  return (
    <section id="q5" className="overflow-hidden rounded-2xl border border-slate-200/80 bg-white shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-100 bg-gradient-to-r from-blue-50 via-white to-white px-5 py-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="rounded-full bg-blue-600 px-2.5 py-1 text-[10px] font-bold uppercase tracking-[0.14em] text-white">
              Q5
            </span>
            <span className="text-xs font-medium text-blue-700">External patient validation</span>
          </div>
          <h2 className="mt-2 text-lg font-semibold tracking-tight text-slate-950">
            Validated pCR evidence for the administered regimen
          </h2>
          <p className="mt-1 text-sm capitalize text-slate-500">{regimen.join(" + ")}</p>
        </div>
        <span
          className={`rounded-full border px-3 py-1.5 text-xs font-semibold ${
            available
              ? "border-emerald-200 bg-emerald-50 text-emerald-700"
              : "border-amber-200 bg-amber-50 text-amber-700"
          }`}
        >
          {available ? "Applicability gate passed" : "Estimate withheld"}
        </span>
      </div>

      <div className="grid gap-4 p-5 lg:grid-cols-[0.8fr_1.2fr]">
        <div
          className={`flex min-h-40 flex-col justify-center rounded-2xl p-5 ${
            available ? "bg-blue-600 text-white" : "border border-amber-200 bg-amber-50 text-amber-900"
          }`}
        >
          {available ? (
            <>
              <span className="text-xs font-semibold uppercase tracking-[0.12em] text-blue-100">
                Population-calibrated pCR estimate
              </span>
              <div className="mt-2 text-5xl font-semibold tracking-tight">
                {(pcr.pcr_probability! * 100).toFixed(0)}%
              </div>
              <p className="mt-3 text-xs leading-5 text-blue-100">
                Cohort-level estimate for this regimen and RNA profile. It does not guarantee an
                individual outcome.
              </p>
            </>
          ) : (
            <>
              <span className="text-xs font-semibold uppercase tracking-[0.12em]">No pCR number shown</span>
              <p className="mt-3 text-sm leading-6">
                {gate.reason ?? "The regimen did not meet the validated Q5 applicability requirements."}
              </p>
            </>
          )}
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          <div className="rounded-xl border border-slate-200 p-4">
            <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-400">
              Validation cohort
            </p>
            <p className="mt-2 text-sm font-semibold text-slate-800">
              {gate.validated_cohort ?? "No matching cohort"}
            </p>
            <p className="mt-1 text-xs text-slate-500">{gate.validated_split?.replaceAll("_", " ")}</p>
          </div>
          <div className="rounded-xl border border-slate-200 p-4">
            <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-400">
              Held-out AUROC
            </p>
            <p className="mt-2 text-2xl font-semibold text-slate-900">
              {gate.held_out_auroc?.toFixed(2) ?? "—"}
            </p>
            <p className="mt-1 text-xs text-slate-500">
              Display threshold {gate.gate_threshold?.toFixed(2) ?? "—"}
            </p>
          </div>
          <div className="rounded-xl border border-violet-100 bg-violet-50/60 p-4 sm:col-span-2">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-violet-600">
                  Separate discovery signal
                </p>
                <p className="mt-1 text-sm font-semibold text-slate-800">MOFA regimen reversal</p>
              </div>
              <span className="text-xl font-semibold text-violet-700">
                {pcr.mofa_regimen_reversal_percentile != null
                  ? `${(pcr.mofa_regimen_reversal_percentile * 100).toFixed(0)}th`
                  : "—"}
              </span>
            </div>
            <p className="mt-2 text-xs leading-5 text-slate-500">
              GCTX transcriptional-reversal percentile. It is intentionally not fused into the Q5
              pCR estimate because the combined Q2+MOFA model is not externally validated.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
