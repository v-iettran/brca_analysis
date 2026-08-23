"use client";

import { useState } from "react";
import type { SignaturePanel } from "@/lib/types";
import { GeneLiteratureDrawer } from "@/components/GeneLiteratureDrawer";

export function SignaturePanels({
  clusterSignature,
  residualSignature,
  topUp,
  topDown,
  onRecalculate,
  recalculating,
  runId,
  clusterId,
  allowRecalculate = true,
}: {
  clusterSignature?: SignaturePanel | null;
  residualSignature?: SignaturePanel | null;
  topUp: number;
  topDown: number;
  onRecalculate: (topUp: number, topDown: number) => Promise<void> | void;
  recalculating?: boolean;
  runId: string;
  clusterId: number;
  allowRecalculate?: boolean;
}) {
  const [up, setUp] = useState(topUp);
  const [down, setDown] = useState(topDown);
  const [selectedGene, setSelectedGene] = useState<string | null>(null);

  return (
    <section className="space-y-4 rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-indigo-600">Signatures</p>
          <h3 className="mt-1 text-lg font-semibold text-slate-950">Cluster and patient residual arms</h3>
          <p className="mt-1 text-xs text-slate-500">
            Defaults are 150 up / 150 down. Changing sizes creates an auditable revision without re-upload.
          </p>
        </div>
        {allowRecalculate && (
        <div className="flex flex-wrap items-end gap-3">
          <label className="text-xs font-semibold text-slate-600">
            Top up
            <input
              type="number"
              min={10}
              max={500}
              value={up}
              onChange={(e) => setUp(Number(e.target.value))}
              className="mt-1 block w-24 rounded-lg border border-slate-200 px-2 py-1.5 text-sm"
            />
          </label>
          <label className="text-xs font-semibold text-slate-600">
            Top down
            <input
              type="number"
              min={10}
              max={500}
              value={down}
              onChange={(e) => setDown(Number(e.target.value))}
              className="mt-1 block w-24 rounded-lg border border-slate-200 px-2 py-1.5 text-sm"
            />
          </label>
          <button
            onClick={() => onRecalculate(up, down)}
            disabled={recalculating}
            className="rounded-lg bg-indigo-600 px-3 py-2 text-xs font-semibold text-white shadow-sm disabled:opacity-50"
          >
            {recalculating ? "Recalculating…" : "Apply and Recalculate"}
          </button>
        </div>
        )}
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <SignatureTable title="List 1 · Cluster signature" panel={clusterSignature} onOpenGene={setSelectedGene} />
        <SignatureTable title="List 2 · Residual signature" panel={residualSignature} onOpenGene={setSelectedGene} />
      </div>
      {selectedGene && (
        <GeneLiteratureDrawer
          runId={runId}
          clusterId={clusterId}
          gene={selectedGene}
          onClose={() => setSelectedGene(null)}
        />
      )}
    </section>
  );
}

function SignatureTable({
  title,
  panel,
  onOpenGene,
}: {
  title: string;
  panel?: SignaturePanel | null;
  onOpenGene: (gene: string) => void;
}) {
  if (!panel) {
    return (
      <div className="rounded-xl border border-dashed border-slate-200 p-4 text-sm text-slate-400">{title}: unavailable</div>
    );
  }
  const ranked = [...panel.genes].sort((a, b) => Math.abs(b.effect) - Math.abs(a.effect)).slice(0, 25);
  return (
    <div className="overflow-hidden rounded-xl border border-slate-200">
      <div className="border-b border-slate-100 bg-slate-50 px-3 py-2">
        <h4 className="text-sm font-semibold text-slate-800">{title}</h4>
        <p className="text-[11px] text-slate-500">
          {panel.n_up} up / {panel.n_down} down
          {panel.coverage_fraction != null ? ` · coverage ${(panel.coverage_fraction * 100).toFixed(0)}%` : ""}
        </p>
      </div>
      <div className="max-h-72 overflow-auto">
        <table className="min-w-full text-left text-xs">
          <thead className="sticky top-0 bg-white text-slate-400">
            <tr>
              <th className="px-3 py-2 font-semibold">Gene</th>
              <th className="px-3 py-2 font-semibold">Effect</th>
              <th className="px-3 py-2 font-semibold">Dir</th>
              <th className="px-3 py-2 font-semibold">FDR</th>
              <th className="px-3 py-2 font-semibold">Lit</th>
            </tr>
          </thead>
          <tbody>
            {ranked.map((gene) => (
              <tr key={`${panel.kind}-${gene.gene}`} className="border-t border-slate-50">
                <td className="px-3 py-1.5">
                  <button
                    type="button"
                    onClick={() => onOpenGene(gene.gene)}
                    className="font-mono font-semibold text-indigo-700 hover:underline"
                    title={`Open ranked literature for ${gene.gene}`}
                  >
                    {gene.gene}
                  </button>
                </td>
                <td className="px-3 py-1.5">{gene.effect.toFixed(3)}</td>
                <td className="px-3 py-1.5 uppercase">{gene.direction}</td>
                <td className="px-3 py-1.5">{gene.fdr != null ? gene.fdr.toExponential(1) : "—"}</td>
                <td className="px-3 py-1.5">{gene.literature_count ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
