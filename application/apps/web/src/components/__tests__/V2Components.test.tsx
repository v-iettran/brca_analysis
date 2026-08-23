import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AnalyzingModal } from "@/components/AnalyzingModal";
import { OverlapNominationCards } from "@/components/OverlapNominationCards";
import { PredictorCombinationPanel } from "@/components/PredictorCombinationPanel";
import { RationaleCard } from "@/components/RationaleCard";
import { SignaturePanels } from "@/components/SignaturePanels";
import { parseExpressionFile } from "@/lib/api";

describe("parseExpressionFile", () => {
  it("parses gene,expression CSV", () => {
    const rows = ["gene,expression", ...Array.from({ length: 12 }, (_, i) => `GENE${i},${i + 1}`)].join("\n");
    const expr = parseExpressionFile(rows);
    expect(Object.keys(expr).length).toBe(12);
    expect(expr.GENE0).toBe(1);
  });
});

describe("AnalyzingModal", () => {
  it("renders staged progress labels", () => {
    render(
      <AnalyzingModal
        open
        progress={{
          run_id: "abc",
          status: "running",
          current_stage: "build_signatures",
          stages: [
            { stage_id: "validate", label: "Validating profile", status: "completed" },
            { stage_id: "build_signatures", label: "Building cluster and residual signatures", status: "running" },
          ],
        }}
      />
    );
    expect(screen.getByText(/Building the evidence workspace/i)).toBeInTheDocument();
    expect(screen.getAllByText(/Building cluster and residual signatures/i)).toHaveLength(2);
  });
});

describe("OverlapNominationCards", () => {
  it("shows dual-list support and artifact flags", () => {
    const onSelectDrug = vi.fn();
    render(
      <OverlapNominationCards
        nominations={[
          {
            drug: "vorinostat",
            canonical: "vorinostat",
            nomination_rank: 1,
            list1_percentile: 0.9,
            list2_percentile: 0.8,
            weaker_percentile: 0.8,
            evidence_tier: "tier_c_novel_repurposing_hypothesis",
            indication_bucket: "repurposing_hypothesis",
            targets: ["HDAC"],
            robustness: { likely_artifact: true, notes: ["Low consistency"] },
            literature_summary: { retrieved_relevant_references: 2, dominant_stance: "unclear" },
            q2_annotation: { evidence_category: "exploratory", genes_used: 12 },
          },
        ]}
        combinations={[]}
        runId="run-1"
        clinicalComparators={[
          {
            drug: "olaparib",
            canonical: "olaparib",
            category: "PARP inhibitor",
            clinical_context: "Requires qualifying BRCA/HRR context.",
            list1_rank: 187,
            list2_rank: 436,
            list1_percentile: 0.72,
            list2_percentile: 0.31,
            dual_support_percentile: 0.31,
            present_in_both_lists: true,
            list1_source: "patient_cluster_compact_gctx",
            list2_source: "patient_residual_compact_gctx",
            targets: ["PARP1"],
            interpretation: "Comparator only.",
          },
        ]}
        selectedDrug={null}
        onSelectDrug={onSelectDrug}
      />
    );
    expect(screen.getByText("vorinostat")).toBeInTheDocument();
    expect(screen.getByText(/Likely artifact/i)).toBeInTheDocument();
    expect(screen.getByText(/List 1 rank pct 90\.0%/i)).toBeInTheDocument();
    expect(screen.getByText(/Dual-support \(min\) 80\.0%/i)).toBeInTheDocument();
    expect(screen.getByText("olaparib")).toBeInTheDocument();
    expect(screen.getByText(/List 2 #436/i)).toBeInTheDocument();
    fireEvent.click(screen.getByText("olaparib"));
    expect(onSelectDrug).toHaveBeenCalledWith("olaparib");
  });

  it("shows development badges and collapsed technical exclusions", () => {
    render(
      <OverlapNominationCards
        nominations={[
          {
            drug: "paclitaxel",
            canonical: "paclitaxel",
            nomination_rank: 1,
            list1_percentile: 0.9,
            list2_percentile: 0.8,
            weaker_percentile: 0.8,
            targets: ["TUBB"],
            human_development_label: "Approved drug (breast-cancer context)",
            display_action: "default_visible",
            support_class: "breast_cell_line_supported",
          },
        ]}
        exploratory={[
          {
            drug: "veliparib",
            canonical: "veliparib",
            list1_rank: 20,
            list2_rank: 22,
            list1_percentile: 0.7,
            list2_percentile: 0.6,
            targets: ["PARP"],
            human_development_label: "Investigational / not approved",
            display_action: "exploratory_only",
          },
        ]}
        technicalExcluded={[
          {
            drug: "BRD-K000",
            canonical: "brd-k000",
            list1_rank: 1,
            list2_rank: 2,
            list1_percentile: 0.99,
            list2_percentile: 0.98,
            targets: [],
            display_gate_reason: "anonymous_lincs_identifier",
            display_action: "technical_excluded",
          },
        ]}
        combinations={[]}
        runId="run-1"
        selectedDrug={null}
        onSelectDrug={vi.fn()}
      />
    );
    expect(screen.getByText("Research nominations")).toBeInTheDocument();
    expect(screen.getByText(/Approved drug \(breast-cancer context\)/i)).toBeInTheDocument();
    expect(screen.getByText(/Exploratory clinical candidates/i)).toBeInTheDocument();
    expect(screen.getByText(/Technical exclusions/i)).toBeInTheDocument();
  });
});

describe("SignaturePanels", () => {
  it("exposes Apply and Recalculate", () => {
    const onRecalculate = vi.fn();
    render(
      <SignaturePanels
        clusterSignature={{
          kind: "cluster",
          cluster_id: 1,
          top_up: 150,
          top_down: 150,
          n_up: 1,
          n_down: 1,
          genes: [{ gene: "ESR1", effect: 1.2, direction: "up", fdr: 0.01, literature_count: 3 }],
        }}
        residualSignature={null}
        topUp={150}
        topDown={150}
        onRecalculate={onRecalculate}
        runId="run-1"
        clusterId={1}
      />
    );
    expect(screen.getByText(/Apply and Recalculate/i)).toBeInTheDocument();
    expect(screen.getByText("ESR1")).toBeInTheDocument();
  });
});

describe("RationaleCard", () => {
  it("renders claim-level evidence keys and citation chips", () => {
    render(
      <RationaleCard
        rationale={{
          summary: "This is a research demonstration, not a treatment recommendation.",
          supporting_claims: [
            {
              text: "Cluster 2 has the largest RNA-only probability.",
              kind: "support",
              evidence_keys: ["cluster_prediction.top_cluster"],
              citation_ids: ["12345"],
              section: "mofa",
            },
          ],
          counter_claims: [],
          uncertainty: [
            {
              text: "No normal-breast reference is available.",
              kind: "uncertainty",
              evidence_keys: ["limitations"],
              citation_ids: [],
              section: "mofa",
            },
          ],
          citations: [],
          used_llm: false,
          fallback_used: true,
          provider: "none",
          model: "deterministic",
        }}
      />
    );
    expect(screen.getByText(/Evidence rationale/i)).toBeInTheDocument();
    expect(screen.getByText("cluster_prediction.top_cluster")).toBeInTheDocument();
    expect(screen.getByText("12345")).toBeInTheDocument();
    expect(screen.getByText(/Deterministic evidence summary/i)).toBeInTheDocument();
  });
});

describe("PredictorCombinationPanel", () => {
  it("keeps predictor combinations in a separate preclinical lane", () => {
    render(
      <PredictorCombinationPanel
        combinations={[
          {
            rank: 1,
            drug_a: "cisplatin",
            drug_b: "doxorubicin",
            combination: "cisplatin + doxorubicin",
            component_drug_priority: 0.62,
            drug_a_priority: 0.7,
            drug_b_priority: 0.55,
            aligned_pair_support: 0.986,
            pair_q4_support: 0.18,
            integrated_combination_priority: 0.704,
            aligned_cell_lines: 5,
            cell_line_alignment_confidence: "high_4_or_more_aligned_lines",
            predictor_version: "predictor_r_port_v1",
            interpretation: "Preclinical context only.",
          },
        ]}
      />
    );
    expect(screen.getByText("cisplatin + doxorubicin")).toBeInTheDocument();
    expect(screen.getByText(/not additional patient-specific nominations/i)).toBeInTheDocument();
  });
});
