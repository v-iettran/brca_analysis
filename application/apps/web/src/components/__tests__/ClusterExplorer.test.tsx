import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ClusterExplorer } from "@/components/ClusterExplorer";
import type { ClusterPrediction } from "@/lib/types";

vi.mock("@/lib/api", () => ({
  getClusterDetail: vi.fn().mockResolvedValue({
    cluster_id: 1,
    patient_probability: 0.7,
    n_in_cluster: 380,
    n_out_cluster: 1037,
    genes_tested: 12011,
    significant_gene_count: 5601,
    coefficient_interpretation: "PAM50-adjusted one-vs-rest expression difference.",
    positive_genes: [
      { gene: "ERBB2", coefficient: 2.4, p_value: 0.0001, fdr: 0.001, direction: "higher" },
    ],
    negative_genes: [
      { gene: "ESR1", coefficient: -2.1, p_value: 0.0002, fdr: 0.002, direction: "lower" },
    ],
  }),
  getGeneLiterature: vi.fn(),
}));

const prediction: ClusterPrediction = {
  probabilities: { "0": 0.1, "1": 0.7, "2": 0.1, "3": 0.05, "4": 0.05 },
  top_cluster: 1,
  top_probability: 0.7,
  confidence_level: "high",
  gene_coverage: 0.92,
  genes_found: 1380,
  genes_requested: 1500,
  method_used: "elastic_net",
  warnings: [],
};

describe("ClusterExplorer", () => {
  it("renders clickable cluster probabilities and directional gene coefficients", async () => {
    render(<ClusterExplorer runId="run-1" prediction={prediction} />);

    expect(screen.getByRole("button", { name: /cluster 1/i })).toHaveAttribute("aria-pressed", "true");
    expect(await screen.findByText("ERBB2")).toBeInTheDocument();
    expect(screen.getByText("ESR1")).toBeInTheDocument();
    expect(screen.getByText("Higher expression")).toBeInTheDocument();
    expect(screen.getByText("Lower expression")).toBeInTheDocument();
    expect(screen.getByText("+2.40")).toBeInTheDocument();
    expect(screen.getByText("-2.10")).toBeInTheDocument();
  });
});
