"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { AbstentionPanel } from "@/components/AbstentionPanel";
import { CellLineCard } from "@/components/CellLineCard";
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

const SECTION_IDS = ["quality", "structure", "projection", "survival", "characteristics", "retrieval"];

export function V3Workspace({
  cohort,
  patient,
  runId,
}: {
  cohort: V3CohortPayload;
  patient: V3PatientPayload;
  runId: string;
}) {
  const pregK = cohort.preregistered.k ?? 3;
  const [k, setK] = useState(pregK);
  const [method, setMethod] = useState<"gmm" | "kmeans">("gmm");
  const [covariance, setCovariance] = useState<"full" | "diag" | "tied">("full");
  const [projection, setProjection] = useState<"umap" | "pca">(cohort.projection_meta?.default ?? "pca");
  // One selection model for every panel: cross-filtering and multi-subgroup
  // comparison are the same gesture, so they share the same state.
  const [selectedClusters, setSelectedClusters] = useState<number[]>([patient.position.cluster.label]);
  const [endpoint, setEndpoint] = useState<"os" | "pfi">("os");
  const [lineId, setLineId] = useState(patient.nearest_lines?.[0]?.line_id ?? null);
  const firstCmax = patient.nearest_lines?.[0]?.curves?.[0]?.cmax_nm;
  const [concentration, setConcentration] = useState(firstCmax && firstCmax > 0 ? firstCmax : 250);
  const [step, setStep] = useState<string>("quality");

  const cid = configId(method, method === "gmm" ? covariance : null, k);
  const config = cohort.configurations[cid] ?? cohort.configurations[configId("gmm", "full", pregK)];
  const exploratory =
    Boolean(config?.exploratory) || k !== cohort.preregistered.k || method !== "gmm" || covariance !== "full";
  const clusteringAvailable = cohort.clustering_available;
  const abstained = patient.state === 3 || patient.abstention.abstained;
  const a2Failed = !cohort.gates.a2.passed;
  const a4Failed = !cohort.gates.a4.passed;
  const ids = useMemo(
    () => Object.keys(cohort.projections.pca || cohort.projections.umap),
    [cohort.projections.pca, cohort.projections.umap]
  );
  const coords = projection === "umap" ? cohort.projections.umap : cohort.projections.pca;
  const lines = useMemo(() => patient.nearest_lines ?? [], [patient.nearest_lines]);
  const line = lines.find((item) => item.line_id === lineId) ?? lines[0] ?? null;
  const showDrug = !abstained;
  const assignments = config?.assignments ?? {};
  const membership = useMemo(() => config?.membership ?? {}, [config]);
  const takeaways = panelTakeaways(cohort, patient, { exploratory });
  const meta = populatedEntries(patient.patient_metadata);
  const modalities = patient.modalities_used ?? patient.modalities_present;

  const similarityRange = useMemo<[number, number]>(() => {
    if (!lines.length) return [0, 1];
    const values = lines.map((l) => l.similarity);
    return [Math.min(...values) * 0.98, Math.max(...values)];
  }, [lines]);

  const toggleCluster = useCallback((cluster: number) => {
    setSelectedClusters((prev) =>
      prev.includes(cluster) ? prev.filter((c) => c !== cluster) : [...prev, cluster].sort((a, b) => a - b)
    );
  }, []);
  const clearClusters = useCallback(() => setSelectedClusters([]), []);

  // Scroll-spy for the rail. IntersectionObserver rather than a scroll listener,
  // which would re-render the tree on every frame.
  useEffect(() => {
    if (typeof IntersectionObserver === "undefined") return;
    const seen = new Map<string, number>();
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) seen.set(entry.target.id, entry.intersectionRatio);
        let best: string | null = null;
        let bestRatio = 0;
        for (const [id, ratio] of seen) {
          if (ratio > bestRatio) {
            best = id;
            bestRatio = ratio;
          }
        }
        if (best) setStep(best);
      },
      { rootMargin: "-96px 0px -55% 0px", threshold: [0, 0.25, 0.5, 1] }
    );
    for (const id of SECTION_IDS) {
      const el = document.getElementById(id);
      if (el) observer.observe(el);
    }
    return () => observer.disconnect();
  }, [showDrug]);

  return (
    <div className={exploratory ? "shell-exploratory" : undefined}>
      <PatientMetadataBar
        patientId={patient.patient_id}
        modalities={modalities}
        pam50={patient.pam50}
        tumourFraction={patient.sample_quality.tumour_fraction}
        verdict={patient.sample_quality.verdict}
        timestamp={patient.analysis_timestamp}
        state={patient.state}
        encoder={patient.encoder}
        exploratory={exploratory}
      />

      <div className="flex gap-6 pt-4">
        <ProgressRail current={step} />

        <div className="flex min-w-0 flex-1 flex-col gap-4">
          {patient.banner && (
            <p className="rounded-[var(--radius-inner)] border border-[var(--warning-line)] bg-[var(--warning-wash)] px-4 py-2.5 text-[13px] text-[var(--warning)]">
              {patient.banner}
            </p>
          )}

          {/* Metadata first: who this is, before anything is claimed about them. */}
          {meta.filled.length > 0 && (
            <PanelCard
              eyebrow="Patient"
              title={patient.patient_id}
              bare
              footnote={meta.empty.length ? `${meta.empty.length} fields not recorded` : undefined}
            >
              <dl className="grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-4 lg:grid-cols-6">
                {meta.filled.map(([label, value]) => (
                  <div key={label} className="min-w-0">
                    <dt className="eyebrow truncate">{label}</dt>
                    <dd className="mt-1 truncate font-mono text-[13px] text-[var(--text-primary)]">{value}</dd>
                  </div>
                ))}
              </dl>
            </PanelCard>
          )}

          {/* The control board shares the projection's column width, which lifts
              model selection and sample quality up beside it. */}
          <div className="grid min-w-0 items-start gap-4 xl:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
            <div className="flex min-w-0 flex-col gap-4">
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
              <ClusterProjection
                ids={ids}
                coords={coords}
                assignments={assignments}
                membership={membership}
                widths={cohort.posterior_width ?? {}}
                currentId={patient.patient_id}
                clusteringAvailable={clusteringAvailable}
                selectedClusters={selectedClusters}
                onToggleCluster={toggleCluster}
                takeaway={takeaways.projection}
                projection={projection}
                variance={cohort.projection_meta?.pca_variance_ratio}
                annotations={cohort.cluster_annotations}
                umapNote={cohort.projection_meta?.umap_note}
                encoder={cohort.encoder}
                encoderNote={cohort.provenance?.encoder_note as string | undefined}
                preregistered={cohort.preregistered}
              />
            </div>
            <div className="flex min-w-0 flex-col gap-4">
              <ModelSelectionPanel
                rows={cohort.model_selection}
                k={k}
                preregisteredK={cohort.preregistered.k}
                showReference={method === "gmm"}
                takeaway={takeaways.structure}
              />
              <SampleQualityPanel data={patient.sample_quality} takeaway={takeaways.quality} />
            </div>
          </div>

          <SurvivalPanel
            block={config?.km[endpoint]}
            k={k}
            exploratory={exploratory && clusteringAvailable}
            a2Failed={a2Failed && !exploratory}
            a2P={cohort.gates.a2.p_os}
            framing={cohort.gates.a2.framing}
            endpoint={endpoint}
            onEndpoint={setEndpoint}
            selectedClusters={selectedClusters}
            onToggleCluster={toggleCluster}
            takeaway={takeaways.survival}
            nCohort={cohort.n_samples}
            sensitivity={cohort.survival_sensitivity}
            preregisteredK={cohort.preregistered.k}
            sweepApplies={method === "gmm" && covariance === "full"}
          />

          <ClusterHeatmap
            runId={runId}
            cohort={cohort}
            selectedClusters={selectedClusters}
            onToggleCluster={toggleCluster}
            onClearClusters={clearClusters}
            takeaway={takeaways.characteristics}
          />

          {showDrug ? (
            <div className="grid min-w-0 items-start gap-4 xl:grid-cols-[20rem_minmax(0,1fr)]">
              {/* Pinned while the response panel is read: switching line is the
                  whole point of that panel, and it sat above the fold. */}
              <div className="xl:sticky xl:top-[4.25rem] xl:flex xl:max-h-[calc(100vh-5.5rem)] xl:flex-col">
              <PanelCard
                eyebrow="Similar cell lines"
                title="Nearest measured lines"
                takeaway={takeaways.retrieval}
                display={lines.length}
                displayCaption="lines"
                bare
                scrollBody
                className="xl:min-h-0 xl:flex-1"
                footnote="Retrieved by cosine similarity in a PCA shared between this tumour and DepMap breast lines. Compounds are shown as evidence, not as recommendations."
              >
                <div className="flex flex-col gap-2">
                  {lines.map((item) => (
                    <CellLineCard
                      key={item.line_id}
                      line={item}
                      axes={cohort.fingerprint_axes}
                      patientPam50={patient.pam50}
                      similarityRange={similarityRange}
                      joint={cohort.joint_projection}
                      patientId={patient.patient_id}
                      selected={item.line_id === line?.line_id}
                      onSelect={() => setLineId(item.line_id)}
                    />
                  ))}
                </div>
              </PanelCard>
              </div>
              <DoseResponsePanel
                runId={runId}
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

          {showDrug && patient.prognostic_estimate && (
            <PrognosticEstimatePanel data={patient.prognostic_estimate} />
          )}

          <ul className="mt-2 space-y-1.5 border-t border-[var(--line)] pt-4 text-[11px] leading-relaxed text-[var(--text-muted)]">
            {patient.limitations.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
