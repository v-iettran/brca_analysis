import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ClusterProbabilityChart } from "@/components/ClusterProbabilityChart";
import type { ClusterPrediction } from "@/lib/types";

const prediction: ClusterPrediction = {
  probabilities: { "0": 0.05, "1": 0.7, "2": 0.1, "3": 0.1, "4": 0.05 },
  top_cluster: 1,
  top_probability: 0.7,
  confidence_level: "high",
  gene_coverage: 0.92,
  genes_found: 460,
  genes_requested: 500,
  method_used: "elastic_net",
  warnings: [],
};

describe("ClusterProbabilityChart", () => {
  it("summarizes the top cluster, confidence, coverage, and method", () => {
    render(<ClusterProbabilityChart prediction={prediction} />);

    expect(screen.getByText(/top cluster:/i)).toBeInTheDocument();
    expect(screen.getByText("1")).toBeInTheDocument();
    expect(screen.getByText(/confidence:/i)).toBeInTheDocument();
    expect(screen.getByText("high")).toBeInTheDocument();
    expect(screen.getByText(/gene coverage:/i)).toBeInTheDocument();
    expect(screen.getByText("92%")).toBeInTheDocument();
    expect(screen.getByText(/460\/500/)).toBeInTheDocument();
    expect(screen.getByText("elastic net")).toBeInTheDocument();
  });
});
