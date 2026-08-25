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
import { PanelCard } from "@/components/PanelCard";
import { PatientMetadataBar } from "@/components/PatientMetadataBar";
import { PrognosticEstimatePanel } from "@/components/PrognosticEstimatePanel";
import { ProgressRail } from "@/components/ProgressRail";
import { SampleQualityPanel } from "@/components/SampleQualityPanel";
import { SurvivalPanel } from "@/components/SurvivalPanel";
import { populatedEntries } from "@/lib/v3-format";
import { panelTakeaways } from "@/lib/v3-takeaways";
import { configId, type V3CohortPayload, type V3PatientPayload } from "@/lib/v3-types";

export function V3Workspace({ cohort, patient }: { cohort: V3CohortPayload; patient: V3PatientPayload }) {
  const pregK = cohort.preregistered.k ?? 3;
  const [k, setK] = useState(pregK);
  const [method, setMethod] = useState<"gmm" | "kmeans">("gmm");
  const [covariance, setCovariance] = useState<"full" | "diag" | "tied">("full");
  const [projection, setProjection] = useState<"umap" | "pca">(cohort.projection_meta?.default ?? "pca");
  const [selectedCluster, setSelectedCluster] = useState<number | null>(patient.position.cluster.label);
  const [endpoint, setEndpoint] = useState<"os" | "pfi">("os");
  const [lineId, setLineId] = useState(patient.nearest_lines?.[0]?.line_id ?? null);
  const firstCmax = patient.nearest_lines?.[0]?.curves?.[0]?.cmax_nm;
  const [concentration, setConcentration] = useState(firstCmax && firstCmax > 0 ? firstCmax : 250);

  const cid = configId(method, method === "gmm" ? covariance : null, k);
  const config = cohort.configurations[cid] ?? cohort.configurations[configId("gmm", "full", pregK)];
  const exploratory = Boolean(config?.exploratory) || k !== cohort.preregistered.k || method !== "gmm" || covariance !== "full";
  const clusteringAvailable = cohort.clustering_available;
  const abstained = patient.state === 3 || patient.abstention.abstained;
  const a2Failed = !cohort.gates.a2.passed;
  const a4Failed = !cohort.gates.a4.passed;
  const ids = Object.keys(cohort.projections.pca || cohort.projections.umap);
  const coords = projection === "umap" ? cohort.projections.umap : cohort.projections.pca;
  const line = (patient.nearest_lines ?? []).find((item) => item.line_id === lineId) ?? patient.nearest_lines?.[0] ?? null;
  const showDrug = !abstained;
  const assignments = config?.assignments ?? {};
  const membership = useMemo(() => config?.membership ?? {}, [config]);
  const takeaways = panelTakeaways(cohort, patient, { exploratory });
  const meta = populatedEntries(patient.patient_metadata);
  const modalities = patient.modalities_used ?? patient.modalities_present;

  return (
    <div className="flex gap-6">
      <ProgressRail />
      <div className="min-w-0 flex-1 space-y-4">
        {patient.banner && (
          <div className="rounded-[20px] border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-950">{patient.banner}</div>
        )}
        <PatientMetadataBar
          patientId={patient.patient_id}
          modalities={modalities}
          pam50={patient.pam50}
          tumourFraction={patient.sample_quality.tumour_fraction}
          verdict={patient.sample_quality.verdict}
          timestamp={patient.analysis_timestamp}
          state={patient.state}
          encoder={patient.encoder}
        />
        <div id="quality">
          <SampleQualityPanel data={patient.sample_quality} takeaway={takeaways.quality} />
        </div>
        {meta.filled.length > 0 && (
          <PanelCard
            eyebrow="Patient metadata"
            title={patient.patient_id}
            footnote={meta.empty.length ? `${meta.empty.length} fields not recorded` : undefined}
          >
            <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              {meta.filled.map(([label, value]) => (
                <div key={label}>
                  <dt className="eyebrow">{label}</dt>
                  <dd className="mt-1 text-sm font-medium">{value}</dd>
                </div>
              ))}
            </dl>
          </PanelCard>
        )}
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
              setProjection(cohort.projection_meta?.default ?? "pca");
            }}
          />
          <ModelSelectionPanel rows={cohort.model_selection} k={k} showReference={method === "gmm"} takeaway={takeaways.structure} />
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
            takeaway={takeaways.projection}
            projection={projection}
            variance={cohort.projection_meta?.pca_variance_ratio}
            annotations={cohort.cluster_annotations}
            umapNote={cohort.projection_meta?.umap_note}
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
            takeaway={takeaways.survival}
            nCohort={cohort.n_samples}
          />
        </div>
        <div className="grid gap-3 lg:grid-cols-[1fr_20rem]">
          <ClusterHeatmap
            matrix={cohort.comparison_matrix}
            k={k}
            selectedCluster={selectedCluster}
            onSelectCluster={setSelectedCluster}
            takeaway={takeaways.characteristics}
            annotations={cohort.cluster_annotations}
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
            <PanelCard
              eyebrow="Similar cell lines"
              title="Nearest measured lines"
              takeaway={takeaways.retrieval}
              display={patient.nearest_lines?.length}
              displayCaption="cell lines"
              footnote="Source: DepMap breast expression in a shared PCA with this tumour. Compounds are shown as evidence, not as recommendations."
            >
              <div className="space-y-2">
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
            </PanelCard>
            <DoseResponsePanel
              line={line}
              reversal={a4Failed ? null : patient.reversal_candidates}
              a4Failed={a4Failed}
              concentration={concentration}
              onConcentration={setConcentration}
              takeaway={takeaways.retrieval}
            />
          </div>
        ) : (
          <AbstentionPanel data={patient.abstention} />
        )}
        {showDrug && patient.prognostic_estimate && <PrognosticEstimatePanel data={patient.prognostic_estimate} />}
      </div>
    </div>
  );
}
