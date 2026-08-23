import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { DrugEvidenceTable } from "@/components/DrugEvidenceTable";
import { getDrugTrials } from "@/lib/api";
import type { DrugCandidate } from "@/lib/types";

vi.mock("@/lib/api", () => ({
  getDrugLiterature: vi.fn().mockResolvedValue({
    drug: "olaparib",
    query_families: [],
    citations: [],
    deduplicated_count: 0,
    raw_result_count: 0,
    cache_hit: false,
    searched_at: new Date().toISOString(),
  }),
  getDrugTrials: vi.fn().mockResolvedValue({
    drug: "olaparib",
    trials: [],
    cache_hit: false,
    searched_at: new Date().toISOString(),
  }),
}));

const candidates: DrugCandidate[] = [
  {
    drug: "olaparib",
    targets: ["PARP1", "PARP2"],
    gctx_evidence: { drug: "olaparib", blended_percentile: 0.88, clusters_with_data: 3, per_cluster: [] },
    q2_evidence: null,
    literature_summary: null,
    is_in_administered_regimen: false,
  },
];

describe("DrugEvidenceTable", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getDrugTrials).mockResolvedValue({
      drug: "olaparib",
      trials: [],
      cache_hit: false,
      searched_at: new Date().toISOString(),
    });
  });

  it("renders drug rows without an overall score or banned recommendation language", async () => {
    render(<DrugEvidenceTable runId="run-1" candidates={candidates} />);

    expect(screen.getByText("olaparib")).toBeInTheDocument();
    expect(screen.getByText(/PARP1 · PARP2/)).toBeInTheDocument();
    expect(screen.queryByText(/best drug/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/overall score/i)).not.toBeInTheDocument();
    await waitFor(() => expect(screen.queryByText(/checking trial registry/i)).not.toBeInTheDocument());
    expect(screen.queryByRole("button", { name: /trials/i })).not.toBeInTheDocument();
  });

  it("opens the literature popup for a drug on demand", async () => {
    const user = userEvent.setup();
    render(<DrugEvidenceTable runId="run-1" candidates={candidates} />);

    await user.click(screen.getByRole("button", { name: /literature/i }));

    await waitFor(() => expect(screen.getByText(/literature evidence — olaparib/i)).toBeInTheDocument());
  });

  it("only highlights the trials action when matches are available", async () => {
    vi.mocked(getDrugTrials).mockResolvedValue({
      drug: "olaparib",
      trials: [
        {
          nct_id: "NCT00000001",
          title: "Example breast cancer study",
          status: "RECRUITING",
          phase: "PHASE2",
          conditions: ["Breast Cancer"],
          interventions: ["olaparib"],
          sites: [],
          eligibility_assessment: "insufficient_information",
          eligibility_notes: [],
          url: "https://clinicaltrials.gov/study/NCT00000001",
        },
      ],
      cache_hit: false,
      searched_at: new Date().toISOString(),
    });

    render(<DrugEvidenceTable runId="run-1" candidates={candidates} />);

    expect(await screen.findByRole("button", { name: "Trials · 1" })).toBeInTheDocument();
  });
});
