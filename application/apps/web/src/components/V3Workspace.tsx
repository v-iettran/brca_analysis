"use client";

import { useMemo, useState } from "react";
import { AbstentionPanel } from "@/components/AbstentionPanel";
import { CellLineCard } from "@/components/CellLineCard";
import { ClusterDrawer } from "@/components/ClusterDrawer";
import { ClusterHeatmap } from "@/components/ClusterHeatmap";
import { ClusterProjection } from "@/components/ClusterProjection";
import { ControlBoard } from "@/components/ControlBoard";
import { DoseResponsePanel } from "@/components/DoseResponsePanel";
import { ModelSelectionPanel } from "@/components/ModelSelectionPanel";
import { PatientMetadataBar } from "@/components/PatientMetadataBar";
import { PrognosticEstimatePanel } from "@/components/PrognosticEstimatePanel";
import { SampleQualityPanel } from "@/components/SampleQualityPanel";
import { SurvivalPanel } from "@/components/SurvivalPanel";
import { configId, type V3CohortPayload, type V3PatientPayload } from "@/lib/v3-types";

export function V3Workspace({ cohort, patient }: { cohort: V3CohortPayload; patient: V3PatientPayload }) {
  const pregK = cohort.preregistered.k ?? 3;
  const [k, setK] = useState(pregK);
  const [method, setMethod] = useState<"gmm" | "kmeans">("gmm");
  const [covariance, setCovariance] = useState<"full" | "diag" | "tied">("full");
  const [projection, setProjection] = useState<"umap" | "pca">("umap");
  const [selectedCluster, setSelectedCluster] = useState<number | null>(patient.position.cluster.label);
  const [endpoint, setEndpoint] = useState<"os" | "pfi">("os");
  const [lineId, setLineId] = useState(patient.nearest_lines?.[0]?.line_id ?? null);
  const [concentration, setConcentration] = useState(250);

  const cid = configId(method, method === "gmm" ? covariance : null, k);
  const config = cohort.configurations[cid] ?? cohort.configurations[configId("gmm", "full", pregK)];
  const exploratory = Boolean(config?.exploratory) || k !== cohort.preregistered.k || method !== "gmm" || covariance !== "full";
  const clusteringAvailable = cohort.clustering_available;
  const abstained = patient.state === 3 || patient.abstention.abstained;
  const a2Failed = !cohort.gates.a2.passed;
  const a4Failed = !cohort.gates.a4.passed;
  const ids = Object.keys(cohort.projections.umap);
  const coords = projection === "pca" ? cohort.projections.pca : cohort.projections.umap;
  const line = (patient.nearest_lines ?? []).find((item) => item.line_id === lineId) ?? patient.nearest_lines?.[0] ?? null;
  const showDrug = !abstained;

  const assignments = config?.assignments ?? {};
  const membership = useMemo(() => config?.membership ?? {}, [config]);

  return (
    <div className="space-y-4">
      {patient.banner && (
        <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-950">{patient.banner}</div>
      )}
      <PatientMetadataBar
        patientId={patient.patient_id}
        modalities={patient.modalities_present}
        pam50={patient.pam50}
        tumourFraction={patient.sample_quality.tumour_fraction}
        verdict={patient.sample_quality.verdict}
        timestamp={patient.analysis_timestamp}
        state={patient.state}
        encoder={patient.encoder}
      />
      <SampleQualityPanel data={patient.sample_quality} />
      <div className="grid gap-3 lg:grid-cols-2">
        <ControlBoard
          k={k}
          preregisteredK={cohort.preregistered.k}
          method={method}
          covariance={covariance}
          projection={projection}
          clusteringAvailable={clusteringAvailable}
          exploratory={exploratory && clusteringAvailable}
          onChange={(next) => {
            if (next.k != null) setK(next.k);
            if (next.method) setMethod(next.method);
            if (next.covariance) setCovariance(next.covariance);
            if (next.projection) setProjection(next.projection);
          }}
          onReset={() => {
            setK(pregK);
            setMethod("gmm");
            setCovariance("full");
            setProjection("umap");
          }}
        />
        <ModelSelectionPanel rows={cohort.model_selection} k={k} showReference={method === "gmm"} />
        <ClusterProjection
          ids={ids}
          coords={coords}
          assignments={assignments}
          membership={membership}
          widths={cohort.posterior_width ?? {}}
          currentId={patient.patient_id}
          k={k}
          clusteringAvailable={clusteringAvailable}
          selectedCluster={selectedCluster}
          onSelectCluster={(cl) => setSelectedCluster((prev) => (prev === cl ? null : cl))}
        />
        <SurvivalPanel
          block={config?.km[endpoint]}
          k={k}
          exploratory={exploratory && clusteringAvailable}
          a2Failed={a2Failed && !exploratory}
          a2P={cohort.gates.a2.p_os}
          framing={cohort.gates.a2.framing}
          endpoint={endpoint}
          onEndpoint={setEndpoint}
          selectedCluster={selectedCluster}
        />
      </div>
      <div className="grid gap-3 lg:grid-cols-[1fr_20rem]">
        <ClusterHeatmap
          matrix={cohort.comparison_matrix}
          k={k}
          selectedCluster={selectedCluster}
          onSelectCluster={setSelectedCluster}
        />
        {selectedCluster != null && (
          <ClusterDrawer
            cluster={selectedCluster}
            k={k}
            annotation={cohort.cluster_annotations[String(selectedCluster)]}
            cohort={cohort}
            onClose={() => setSelectedCluster(null)}
          />
        )}
      </div>
      {showDrug ? (
        <div className="grid gap-3 lg:grid-cols-2">
          <section className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-4">
            <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-400">Similar cell lines</p>
            <p className="mt-1 text-sm text-slate-700">5 cell lines closely resemble this tumour&apos;s molecular profile.</p>
            <div className="mt-3 space-y-2">
              {(patient.nearest_lines ?? []).map((item) => (
                <CellLineCard
                  key={item.line_id}
                  name={item.name}
                  pam50={item.pam50}
                  similarity={item.similarity}
                  mutations={item.mutations}
                  fingerprint={item.fingerprint}
                  selected={item.line_id === line?.line_id}
                  onSelect={() => setLineId(item.line_id)}
                />
              ))}
            </div>
          </section>
          <DoseResponsePanel
            line={line}
            reversal={a4Failed ? null : patient.reversal_candidates}
            a4Failed={a4Failed}
            concentration={concentration}
            onConcentration={setConcentration}
          />
        </div>
      ) : (
        <AbstentionPanel data={patient.abstention} />
      )}
      {showDrug && patient.prognostic_estimate && <PrognosticEstimatePanel data={patient.prognostic_estimate} />}
    </div>
  );
}
