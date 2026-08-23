"use client";

import type { PrototypePayload } from "@/lib/types";
import { AbstentionPanel } from "@/components/AbstentionPanel";
import { MolecularStatePanel } from "@/components/MolecularStatePanel";
import { PatientPositionPanel } from "@/components/PatientPositionPanel";
import { PredictionSetPanel } from "@/components/PredictionSetPanel";
import { PrognosticEstimatePanel } from "@/components/PrognosticEstimatePanel";
import { SampleQualityPanel } from "@/components/SampleQualityPanel";

export function PrototypeWorkspace({ payload }: { payload: PrototypePayload }) {
  const abstained = payload.abstention.abstained;
  const meth = payload.modality_value_estimate.find((row) => row.modality === "methylation");
  const methNote =
    meth && !meth.present && meth.posterior_width_reduction != null
      ? `Adding methylation would narrow this by ~${Math.round(meth.posterior_width_reduction * 100)}%.`
      : null;

  return (
    <div className="space-y-5">
      {payload.banner && (
        <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-950">
          {payload.banner}
        </div>
      )}
      <SampleQualityPanel data={payload.sample_quality} />
      <PatientPositionPanel data={payload.position} />
      <MolecularStatePanel data={payload.molecular_state} />
      {abstained ? (
        <AbstentionPanel data={payload.abstention} />
      ) : (
        <>
          {payload.prognostic_estimate && <PrognosticEstimatePanel data={payload.prognostic_estimate} />}
          {payload.pathway_candidates && (
            <PredictionSetPanel data={payload.pathway_candidates} methylationNote={methNote} />
          )}
        </>
      )}
    </div>
  );
}
