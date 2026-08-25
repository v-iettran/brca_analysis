"use client";

import { useEffect, useMemo, useState } from "react";
import { getClusterDetail } from "@/lib/api";
import type { ClusterDetail, ClusterGene, ClusterPrediction } from "@/lib/types";
import { GeneLiteratureDrawer } from "@/components/GeneLiteratureDrawer";

const CLUSTER_COLORS = ["#4f46e5", "#0f766e", "#c2410c", "#7e22ce", "#be123c"];

function GeneRow({
  gene,
  maxMagnitude,
  onOpen,
}: {
  gene: ClusterGene;
  maxMagnitude: number;
  onOpen: () => void;
}) {
  const width = Math.max(8, (Math.abs(gene.coefficient) / maxMagnitude) * 100);
  const positive = gene.direction === "higher";
  return (
    <button
      type="button"
      onClick={onOpen}
      className="group w-full rounded-lg px-2 py-2 text-left transition hover:bg-slate-50 focus:outline-none focus:ring-2 focus:ring-indigo-300"
      title={`Open literature for ${gene.gene}`}
    >
      <div className="flex items-center justify-between gap-3">
        <span className="font-mono text-xs font-semibold text-slate-800">{gene.gene}</span>
        <span className={`text-xs font-semibold ${positive ? "text-teal-700" : "text-violet-700"}`}>
          {gene.coefficient > 0 ? "+" : ""}
          {gene.coefficient.toFixed(2)}
        </span>
      </div>
      <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-slate-100">
        <div
          className={`h-full rounded-full ${positive ? "bg-teal-500" : "bg-violet-500"}`}
          style={{ width: `${width}%` }}
        />
      </div>
      <div className="mt-1 flex items-center justify-between text-[10px] text-slate-400">
        <span>FDR {gene.fdr < 0.001 ? gene.fdr.toExponential(1) : gene.fdr.toFixed(3)}</span>
        <span className="opacity-0 transition group-hover:opacity-100">Literature →</span>
      </div>
    </button>
  );
}

export function ClusterExplorer({
  runId,
  prediction,
  onClusterSelect,
}: {
  runId: string;
  prediction: ClusterPrediction;
  onClusterSelect?: (clusterId: number) => void;
}) {
  const [selectedCluster, setSelectedCluster] = useState(prediction.top_cluster);
  const [details, setDetails] = useState<Record<number, ClusterDetail>>({});
  const [error, setError] = useState<string | null>(null);
  const [selectedGene, setSelectedGene] = useState<string | null>(null);

  useEffect(() => {
    if (details[selectedCluster]) return;
    getClusterDetail(runId, selectedCluster)
      .then((detail) => setDetails((current) => ({ ...current, [selectedCluster]: detail })))
      .catch((err) => setError(String(err)));
  }, [details, runId, selectedCluster]);

  const detail = details[selectedCluster];
  const maxMagnitude = useMemo(() => {
    if (!detail) return 1;
    return Math.max(
      1,
      ...detail.positive_genes.map((gene) => Math.abs(gene.coefficient)),
      ...detail.negative_genes.map((gene) => Math.abs(gene.coefficient))
    );
  }, [detail]);

  function selectCluster(clusterId: number) {
    setError(null);
    setSelectedCluster(clusterId);
    onClusterSelect?.(clusterId);
  }

  return (
    <section id="mofa" className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <span className="rounded-full bg-indigo-50 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.12em] text-indigo-700">
              RNA assignment
            </span>
            <span className="text-xs text-slate-400">{prediction.method_used.replace("_", " ")}</span>
          </div>
          <h2 className="mt-3 text-xl font-semibold tracking-tight text-slate-950">Cluster profile</h2>
          <p className="mt-1 max-w-2xl text-sm leading-6 text-slate-500">
            Select a cluster to see its probability and the genes expressed higher or lower than the
            other METABRIC clusters after PAM50 adjustment.
          </p>
        </div>
        <div className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-right">
          <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">RNA coverage</div>
          <div className="text-sm font-semibold text-slate-800">
            {(prediction.gene_coverage * 100).toFixed(0)}%
            <span className="ml-1 font-normal text-slate-400">
              {prediction.genes_found}/{prediction.genes_requested}
            </span>
          </div>
        </div>
      </div>

      <div className="mt-5 grid gap-2 sm:grid-cols-5">
        {Object.entries(prediction.probabilities)
          .toSorted(([left], [right]) => Number(left) - Number(right))
          .map(([cluster, probability]) => {
            const clusterId = Number(cluster);
            const selected = clusterId === selectedCluster;
            return (
              <button
                type="button"
                key={cluster}
                onClick={() => selectCluster(clusterId)}
                className={`rounded-xl border p-3 text-left transition focus:outline-none focus:ring-2 focus:ring-indigo-300 ${
                  selected
                    ? "border-indigo-300 bg-indigo-50 shadow-sm"
                    : "border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50"
                }`}
                aria-pressed={selected}
              >
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold text-slate-600">Cluster {cluster}</span>
                  {clusterId === prediction.top_cluster && (
                    <span className="rounded-full bg-white px-1.5 py-0.5 text-[9px] font-bold uppercase text-indigo-600">
                      Highest
                    </span>
                  )}
                </div>
                <div className="mt-2 text-xl font-semibold text-slate-950">{(probability * 100).toFixed(1)}%</div>
                <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-200">
                  <div
                    className="h-full rounded-full transition-all"
                    style={{
                      width: `${Math.max(probability * 100, 1)}%`,
                      backgroundColor: CLUSTER_COLORS[clusterId % CLUSTER_COLORS.length],
                    }}
                  />
                </div>
              </button>
            );
          })}
      </div>

      <div className="mt-5 rounded-xl border border-slate-200 bg-slate-50/70 p-4">
        {!detail && !error && <p className="text-sm text-slate-500">Loading cluster signature…</p>}
        {error && <p className="text-sm text-rose-700">{error}</p>}
        {detail && (
          <>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <h3 className="font-semibold text-slate-900">Cluster {selectedCluster} expression signature</h3>
                <p className="mt-0.5 text-xs text-slate-500">
                  {detail.n_in_cluster} cluster patients · {detail.significant_gene_count.toLocaleString()} genes
                  with FDR &lt; 0.10
                </p>
              </div>
              <span className="rounded-full border border-slate-200 bg-white px-2.5 py-1 text-xs text-slate-500">
                Click any gene for literature
              </span>
            </div>

            <div className="mt-4 grid gap-4 lg:grid-cols-2">
              <div className="rounded-xl border border-teal-100 bg-white p-3">
                <div className="flex items-center gap-2 px-2">
                  <span className="h-2.5 w-2.5 rounded-full bg-teal-500" />
                  <h4 className="text-sm font-semibold text-slate-800">Higher expression</h4>
                  <span className="text-xs text-slate-400">positive coefficient</span>
                </div>
                <div className="mt-2 grid grid-cols-2 gap-x-2">
                  {detail.positive_genes.slice(0, 10).map((gene) => (
                    <GeneRow
                      key={gene.gene}
                      gene={gene}
                      maxMagnitude={maxMagnitude}
                      onOpen={() => setSelectedGene(gene.gene)}
                    />
                  ))}
                </div>
              </div>
              <div className="rounded-xl border border-violet-100 bg-white p-3">
                <div className="flex items-center gap-2 px-2">
                  <span className="h-2.5 w-2.5 rounded-full bg-violet-500" />
                  <h4 className="text-sm font-semibold text-slate-800">Lower expression</h4>
                  <span className="text-xs text-slate-400">negative coefficient</span>
                </div>
                <div className="mt-2 grid grid-cols-2 gap-x-2">
                  {detail.negative_genes.slice(0, 10).map((gene) => (
                    <GeneRow
                      key={gene.gene}
                      gene={gene}
                      maxMagnitude={maxMagnitude}
                      onOpen={() => setSelectedGene(gene.gene)}
                    />
                  ))}
                </div>
              </div>
            </div>

            <details className="mt-4 rounded-lg border border-slate-200 bg-white px-4 py-3">
              <summary className="cursor-pointer text-xs font-semibold text-slate-600">
                How to interpret these coefficients
              </summary>
              <p className="mt-2 text-xs leading-5 text-slate-500">{detail.coefficient_interpretation}</p>
              <p className="mt-1 text-xs leading-5 text-slate-500">
                These cluster-signature coefficients are distinct from the elastic-net weights used
                to estimate this patient&apos;s cluster probabilities.
              </p>
            </details>
          </>
        )}
      </div>

      {selectedGene && (
        <GeneLiteratureDrawer
          runId={runId}
          clusterId={selectedCluster}
          gene={selectedGene}
          onClose={() => setSelectedGene(null)}
        />
      )}
    </section>
  );
}
