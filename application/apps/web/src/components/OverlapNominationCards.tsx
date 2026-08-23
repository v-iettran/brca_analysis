"use client";

import { useState } from "react";
import type { AlmanacCombination, ClinicalComparator, OverlapNomination } from "@/lib/types";
import { CitationPopup } from "@/components/CitationPopup";

function tierLabel(tier?: string | null) {
  if (!tier) return "Unranked";
  if (tier.includes("tier_a")) return "Tier A · potential trial match";
  if (tier.includes("tier_b")) return "Tier B · breast context";
  if (tier.includes("tier_c")) return "Tier C · repurposing hypothesis";
  if (tier.includes("tier_d")) return "Tier D · artifact / insufficient";
  return tier;
}

function pct(value?: number | null) {
  if (value == null || !Number.isFinite(value)) return "n/a";
  return `${(value * 100).toFixed(1)}%`;
}

const CONCORDANCE_LABELS = {
  concordant_high: "Concordant high",
  expression_only: "Expression-only",
  predictor_only: "Predictor-only",
  low_or_uncertain: "Low / uncertain",
} as const;

export function OverlapNominationCards({
  nominations,
  combinations,
  selectedDrug,
  onSelectDrug,
  clinicalComparators = [],
  exploratory = [],
  technicalExcluded = [],
  runId,
}: {
  nominations: OverlapNomination[];
  combinations: AlmanacCombination[];
  selectedDrug: string | null;
  onSelectDrug: (drug: string) => void;
  clinicalComparators?: ClinicalComparator[];
  exploratory?: OverlapNomination[];
  technicalExcluded?: OverlapNomination[];
  runId: string;
}) {
  const [literatureDrug, setLiteratureDrug] = useState<string | null>(null);
  const combosByDrug = new Map<string, AlmanacCombination[]>();
  for (const combo of combinations) {
    for (const drug of [combo.drug_a, combo.drug_b]) {
      const list = combosByDrug.get(drug) ?? [];
      list.push(combo);
      combosByDrug.set(drug, list);
    }
  }
  const supported = nominations.filter((row) => row.support_class === "breast_cell_line_supported");
  const suggestive = nominations.filter(
    (row) => !row.support_class || row.support_class === "suggestive"
  );
  const groups = [
    {
      id: "supported",
      title: "Breast-cell-line-supported overlap",
      description:
        "Independently scored in both lists using the compact GCTX artifact, supported in at least two breast cell lines with consistency ≥ 0.5.",
      rows: supported,
    },
    {
      id: "suggestive",
      title: "Suggestive overlap hypotheses",
      description:
        "Dual-list signals with incomplete cell-line breadth or consistency. These are lower-confidence screening hypotheses.",
      rows: suggestive,
    },
  ];

  return (
    <section className="space-y-4 rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm">
      <div>
        <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-indigo-600">Research nominations</p>
        <h3 className="mt-1 text-lg font-semibold text-slate-950">Default-visible overlap evidence</h3>
        <p className="mt-1 text-xs text-slate-500">
          These are research nominations from List 1 ∩ List 2, not treatment recommendations.
          Rank percentiles measure reversal ranking (not clinical probability). Human-development
          badges come from the versioned compound registry after ranking.
        </p>
      </div>
      <div className="space-y-6">
        {groups.map((group) => (
          <div key={group.id}>
            <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
              <div>
                <h4 className="text-sm font-semibold text-slate-900">{group.title}</h4>
                <p className="mt-1 max-w-3xl text-[11px] leading-4 text-slate-500">{group.description}</p>
              </div>
              <span className="rounded-full bg-slate-100 px-2.5 py-1 text-[10px] font-semibold text-slate-600">
                {group.rows.length} compounds
              </span>
            </div>
            <div className="grid gap-3">
        {group.rows.map((row) => {
          const selected = selectedDrug === row.drug;
          const robustness = row.robustness || {};
          const lit = row.literature_summary;
          const q2 = row.q2_annotation || {};
          const combos = combosByDrug.get(row.drug) || combosByDrug.get(row.canonical) || [];
          return (
            <article
              key={row.canonical}
              onClick={() => onSelectDrug(row.drug)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") onSelectDrug(row.drug);
              }}
              role="button"
              tabIndex={0}
              className={`rounded-xl border p-4 text-left transition ${
                selected
                  ? "border-indigo-400 bg-indigo-50/60 ring-2 ring-indigo-100"
                  : "border-slate-200 hover:border-slate-300 hover:bg-slate-50"
              }`}
            >
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-mono text-[11px] text-slate-400">#{row.support_rank ?? row.nomination_rank}</span>
                    <h4 className="text-sm font-semibold capitalize text-slate-900">{row.drug}</h4>
                    {row.is_in_administered_regimen && (
                      <span className="rounded-full bg-blue-50 px-2 py-0.5 text-[10px] font-semibold text-blue-700">
                        In regimen
                      </span>
                    )}
                    {row.human_development_label && (
                      <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-semibold text-emerald-800">
                        {row.human_development_label}
                      </span>
                    )}
                    {robustness.likely_artifact && (
                      <span className="rounded-full bg-amber-50 px-2 py-0.5 text-[10px] font-semibold text-amber-700">
                        Likely artifact
                      </span>
                    )}
                  </div>
                  <p className="mt-1 text-[11px] font-medium text-indigo-700">{tierLabel(row.evidence_tier)}</p>
                </div>
                <div className="text-right text-xs text-slate-500">
                  <div title="Cluster-signature reversal rank percentile">
                    List 1 rank pct {pct(row.list1_percentile)}
                    {row.list1_rank != null ? ` (#${row.list1_rank})` : ""}
                  </div>
                  <div title="Patient-residual reversal rank percentile">
                    List 2 rank pct {pct(row.list2_percentile)}
                    {row.list2_rank != null ? ` (#${row.list2_rank})` : ""}
                  </div>
                </div>
              </div>
              <div className="mt-3 flex flex-wrap gap-2 text-[10px] font-semibold text-slate-500">
                <span
                  className="rounded-md bg-slate-100 px-2 py-1"
                  title="Minimum of List 1 and List 2 rank percentiles; used for ranking so both arms must be strong"
                >
                  Dual-support (min) {pct(row.weaker_percentile)}
                </span>
                <span className="rounded-md bg-slate-100 px-2 py-1">{row.indication_bucket ?? "unclassified"}</span>
                {row.targets.slice(0, 4).map((t) => (
                  <span key={t} className="rounded-md bg-slate-100 px-2 py-1">
                    {t}
                  </span>
                ))}
              </div>
              <div className="mt-3 grid gap-2 text-[11px] text-slate-600 sm:grid-cols-3">
                <div className="rounded-lg bg-slate-50 p-2">
                  <p className="font-semibold text-slate-700">Q2 annotation</p>
                  <p className="mt-1">
                    {(q2.evidence_category as string) || "unavailable"} · genes {(q2.genes_used as number) ?? 0}
                  </p>
                </div>
                <div className="rounded-lg bg-slate-50 p-2">
                  <p className="font-semibold text-slate-700">Literature stance</p>
                  <p className="mt-1">
                    {lit?.unavailable_reason
                      ? "Unavailable"
                      : `${lit?.retrieved_relevant_references ?? 0} retrieved · ${lit?.dominant_stance ?? "n/a"}`}
                  </p>
                  <button
                    type="button"
                    className="mt-2 font-semibold text-indigo-700 hover:underline"
                    onClick={(event) => {
                      event.stopPropagation();
                      setLiteratureDrug(row.drug);
                    }}
                  >
                    View ranked literature and search terms
                  </button>
                </div>
                <div className="rounded-lg bg-slate-50 p-2">
                  <p className="font-semibold text-slate-700">ALMANAC pairs</p>
                  <p className="mt-1">
                    {combos.length
                      ? combos
                          .slice(0, 2)
                          .map((c) => c.combination)
                          .join("; ")
                      : "No aligned pair among overlap drugs"}
                  </p>
                </div>
              </div>
              {(robustness.notes || []).length > 0 && (
                <ul className="mt-2 space-y-1 text-[11px] text-amber-700">
                  {(robustness.notes || []).slice(0, 2).map((note) => (
                    <li key={note}>• {note}</li>
                  ))}
                </ul>
              )}
            </article>
          );
        })}
            {group.rows.length === 0 && (
              <p className="rounded-xl border border-dashed border-slate-200 p-4 text-xs text-slate-500">
                No compounds meet this evidence class for the current signature sizes.
              </p>
            )}
            </div>
          </div>
        ))}
        {nominations.length === 0 && (
          <p className="rounded-xl border border-dashed border-slate-200 p-4 text-sm text-slate-500">
            No default-visible research nominations for the current signature sizes.
          </p>
        )}
        {(exploratory.length > 0 || technicalExcluded.length > 0) && (
          <div className="space-y-3 border-t border-slate-200 pt-5">
            {exploratory.length > 0 && (
              <details>
                <summary className="cursor-pointer text-sm font-semibold text-slate-800">
                  Exploratory clinical candidates ({exploratory.length})
                </summary>
                <p className="mt-2 text-[11px] text-slate-500">
                  Investigational compounds retained with raw List 1/List 2 ranks. Not shown in the default lane.
                </p>
                <ul className="mt-2 space-y-1 text-xs text-slate-600">
                  {exploratory.map((row) => (
                    <li key={row.canonical}>
                      {row.drug} · List 1 #{row.list1_rank ?? "n/a"} ({pct(row.list1_percentile)}) · List 2 #
                      {row.list2_rank ?? "n/a"} ({pct(row.list2_percentile)}) · {row.human_development_label}
                    </li>
                  ))}
                </ul>
              </details>
            )}
            {technicalExcluded.length > 0 && (
              <details>
                <summary className="cursor-pointer text-sm font-semibold text-slate-800">
                  Technical exclusions ({technicalExcluded.length})
                </summary>
                <p className="mt-2 text-[11px] text-slate-500">
                  Tool compounds, anonymous LINCS IDs, withdrawn agents, and unresolved rows. Raw ranks are unchanged.
                </p>
                <ul className="mt-2 space-y-1 text-xs text-slate-600">
                  {technicalExcluded.map((row) => (
                    <li key={row.canonical}>
                      {row.drug} · List 1 #{row.list1_rank ?? "n/a"} ({pct(row.list1_percentile)}) · List 2 #
                      {row.list2_rank ?? "n/a"} ({pct(row.list2_percentile)}) · {row.display_gate_reason}
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </div>
        )}
        <div className="border-t border-slate-200 pt-5">
          <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
            <div>
              <h4 className="text-sm font-semibold text-slate-900">Recognizable clinical comparators in the expression rankings</h4>
              <p className="mt-1 max-w-3xl text-[11px] leading-4 text-slate-500">
                PARP inhibitors, chemotherapy, endocrine agents, and targeted small molecules are shown here even when
                they rank below the nomination cutoff. Available ranks come from the compact patient analysis or the
                expression-derived MOFA cluster reference; unavailable residual ranks stay explicitly marked n/a.
                Compounds are not manually promoted into recommendations. Concordance labels compare top-quartile
                dual-expression support with top-quartile predictor rank; the scores are never averaged.
              </p>
            </div>
            <span className="rounded-full bg-indigo-50 px-2.5 py-1 text-[10px] font-semibold text-indigo-700">
              {clinicalComparators.length} found in expression artifact
            </span>
          </div>
          <div className="grid gap-2 sm:grid-cols-2">
            {clinicalComparators.map((row) => (
              <article
                key={row.canonical}
                role="button"
                tabIndex={0}
                onClick={() => onSelectDrug(row.drug)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") onSelectDrug(row.drug);
                }}
                className={`rounded-xl border p-3 transition ${
                  selectedDrug === row.drug
                    ? "border-indigo-400 bg-indigo-50/70 ring-2 ring-indigo-100"
                    : "border-slate-200 bg-slate-50/60 hover:border-slate-300"
                }`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <p className="text-[10px] font-semibold uppercase tracking-wide text-indigo-600">{row.category}</p>
                    <h5 className="mt-0.5 text-sm font-semibold capitalize text-slate-900">{row.drug}</h5>
                    {row.evidence_concordance && (
                      <span className="mt-1 inline-flex rounded-full bg-indigo-50 px-2 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-indigo-700">
                        {CONCORDANCE_LABELS[row.evidence_concordance]}
                      </span>
                    )}
                  </div>
                  <button
                    type="button"
                    onClick={(event) => {
                      event.stopPropagation();
                      setLiteratureDrug(row.drug);
                    }}
                    className="shrink-0 rounded-md border border-indigo-200 bg-white px-2 py-1 text-[10px] font-semibold text-indigo-700 hover:bg-indigo-50"
                  >
                    Literature
                  </button>
                </div>
                <p className="mt-2 text-[11px] text-slate-600">{row.clinical_context}</p>
                {row.list1_source === "mofa_cluster_reference_gctx" && (
                  <p className="mt-1 text-[10px] font-medium text-amber-700">
                    Cluster-reference expression rank; patient-residual compound was unavailable.
                  </p>
                )}
                <div className="mt-2 flex flex-wrap gap-1.5 text-[10px] text-slate-600">
                  <span className="rounded bg-white px-1.5 py-1">List 1 #{row.list1_rank ?? "n/a"} · {pct(row.list1_percentile)}</span>
                  <span className="rounded bg-white px-1.5 py-1">List 2 #{row.list2_rank ?? "n/a"} · {pct(row.list2_percentile)}</span>
                </div>
                {row.predictor_evidence ? (
                  <details className="mt-3 rounded-lg border border-indigo-100 bg-white px-3 py-2">
                    <summary className="cursor-pointer text-[10px] font-semibold text-indigo-700">
                      Predictor clinical context · rank #{row.predictor_evidence.within_patient_predictor_rank ?? "n/a"}
                    </summary>
                    <div className="mt-2 grid grid-cols-2 gap-2 text-[10px] sm:grid-cols-4">
                      <div>
                        <p className="text-slate-400">METABRIC sensitivity</p>
                        <p className="font-semibold text-slate-800">
                          {pct(row.predictor_evidence.reference_cohort_sensitivity_percentile)}
                        </p>
                      </div>
                      <div>
                        <p className="text-slate-400">Q2 reliability</p>
                        <p className="font-semibold text-slate-800">
                          {pct(row.predictor_evidence.q2_model_reliability)}
                        </p>
                      </div>
                      <div>
                        <p className="text-slate-400">Q4 support</p>
                        <p className="font-semibold text-slate-800">
                          {pct(row.predictor_evidence.q4_drug_support)}
                        </p>
                      </div>
                      <div>
                        <p className="text-slate-400">Integrated priority</p>
                        <p className="font-semibold text-slate-800">
                          {row.predictor_evidence.integrated_single_drug_priority?.toFixed(3) ?? "n/a"}
                        </p>
                      </div>
                    </div>
                    <p className="mt-2 text-[9px] leading-4 text-slate-400">
                      60% reference-cohort Q2 sensitivity + 25% model reliability + 15% Q4 support.
                      Relative evidence priority, not response probability.
                    </p>
                  </details>
                ) : (
                  <p className="mt-2 text-[10px] text-slate-400">Predictor context unavailable for this compound.</p>
                )}
              </article>
            ))}
          </div>
          {clinicalComparators.length === 0 && (
            <p className="rounded-xl border border-dashed border-slate-200 p-4 text-xs text-slate-500">
              None of the tracked clinical comparators are present in the current expression perturbation artifact.
            </p>
          )}
        </div>
      </div>
      {literatureDrug && (
        <CitationPopup runId={runId} drug={literatureDrug} onClose={() => setLiteratureDrug(null)} />
      )}
    </section>
  );
}
