import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PredictionSetPanel } from "@/components/PredictionSetPanel";
import { SampleQualityPanel } from "@/components/SampleQualityPanel";
import { AbstentionPanel } from "@/components/AbstentionPanel";

describe("PredictionSetPanel", () => {
  it("states that the set is not a ranking", () => {
    render(
      <PredictionSetPanel
        data={{
          coverage_level: 0.9,
          set_members: [
            { drug: "Fulvestrant", evidence_tier: "B" },
            { drug: "Palbociclib", evidence_tier: "A" },
          ],
          excluded_count: 33,
          n_scored: 35,
        }}
      />
    );
    expect(screen.getByText(/Set, not a ranking — order carries no meaning/i)).toBeInTheDocument();
    expect(screen.getByText(/2 of 35 agents/i)).toBeInTheDocument();
  });
});

describe("SampleQualityPanel", () => {
  it("shows tumour fraction and verdict", () => {
    render(
      <SampleQualityPanel
        data={{
          tumour_fraction: 0.62,
          composition: [
            { cell_type: "malignant", fraction: 0.62, ci: [0.58, 0.66] },
            { cell_type: "immune", fraction: 0.21, ci: [0.18, 0.24] },
            { cell_type: "stroma", fraction: 0.17, ci: [0.14, 0.2] },
          ],
          verdict: "sufficient",
        }}
      />
    );
    expect(screen.getByText("62")).toBeInTheDocument();
    expect(screen.getByText("sufficient")).toBeInTheDocument();
  });
});

describe("AbstentionPanel", () => {
  it("explains why sections 4 and 5 are absent", () => {
    render(
      <AbstentionPanel
        data={{
          abstained: true,
          reason_code: "posterior_width",
          reason_text: "Posterior width exceeds the abstention threshold.",
          what_would_help: ["Adding CNA and methylation assays"],
          sections_rendered: ["sample_quality", "position", "molecular_state"],
        }}
      />
    );
    expect(screen.getByText(/Sections 4 and 5 are absent/i)).toBeInTheDocument();
  });
});
