import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { V3Workspace } from "@/components/V3Workspace";
import type { V3CohortPayload, V3PatientPayload } from "@/lib/v3-types";
import cohortJson from "./fixtures/cohort.json";
import fullModalityJson from "./fixtures/TCGA-A8-A081.json";
import abstainJson from "./fixtures/TCGA-A1-A0SK.json";

/**
 * Renders the workspace against the real full-n TCGA-BRCA payloads rather than
 * hand-written fixtures. The hand-written suite checks the state machine; this
 * one checks that the reporting contract survives contact with the actual
 * numbers, which is where the earlier synthetic cohort slipped through.
 */
const cohort = cohortJson as unknown as V3CohortPayload;
const fullModality = fullModalityJson as unknown as V3PatientPayload;
const abstain = abstainJson as unknown as V3PatientPayload;

describe("V3Workspace against the real cohort", () => {
  it("reports the pre-registered configuration honestly", () => {
    render(<V3Workspace cohort={cohort} patient={fullModality} runId="test-run" />);

    expect(cohort.preregistered.k).toBe(4);
    expect(cohort.n_samples).toBe(1082);
    expect(cohort.synthetic_samples).toBe(0);

    // p renders at the pre-registered k, with n and events beside it.
    expect(screen.getByText(/log-rank p = 0\.038 · n = 1082 · events = 151/)).toBeInTheDocument();
    expect(screen.queryByTestId("exploratory-badge")).not.toBeInTheDocument();

    // Axis labels with units, on the charts the earlier review found bare.
    expect(screen.getByText("Overall survival probability")).toBeInTheDocument();
    expect(screen.getByText("Months since diagnosis")).toBeInTheDocument();
    expect(screen.getByText("Cell viability (%)")).toBeInTheDocument();
    // GDSC reports micromolar, so the panel does too.
    expect(screen.getByText("Concentration (µM)")).toBeInTheDocument();
    expect(screen.getByText(/PC1 \(\d+% var\)/)).toBeInTheDocument();
  });

  it("shows an exploratory p only alongside its multiple-testing correction", () => {
    render(<V3Workspace cohort={cohort} patient={fullModality} runId="test-run" />);
    fireEvent.change(screen.getByLabelText("Number of subgroups"), { target: { value: "5" } });

    expect(screen.getAllByText("exploratory").length).toBeGreaterThanOrEqual(2);
    // k=5's raw p (0.016) is smaller than the pre-registered k=4's. It is shown
    // on request, but the BH-adjusted q must always be printed with it, and the
    // panel must say the split was not pre-registered.
    expect(screen.getByText(/log-rank p = 0\.016/)).toBeInTheDocument();
    expect(screen.getByText(/BH-adjusted q = 0\.070/)).toBeInTheDocument();
    expect(screen.getByText(/was not pre-registered/)).toBeInTheDocument();
    expect(screen.getByText(/does not clear 0\.05/)).toBeInTheDocument();
  });

  it("derives modality claims from the payload rather than hardcoding", () => {
    const { unmount } = render(<V3Workspace cohort={cohort} patient={fullModality} runId="test-run" />);
    expect(fullModality.modalities_used).toEqual(["rna", "cna", "methylation"]);
    for (const mod of ["rna", "cna", "methylation"]) {
      expect(screen.getAllByTitle(`${mod} present`).length).toBe(1);
    }
    unmount();

    render(<V3Workspace cohort={cohort} patient={abstain} runId="test-run" />);
    expect(screen.getAllByTitle("rna present").length).toBe(1);
    expect(screen.getAllByTitle("cna not available").length).toBe(1);
    expect(screen.getAllByTitle("methylation not available").length).toBe(1);
  });

  it("groups the heatmap by family and scales each family to its own maximum", () => {
    render(<V3Workspace cohort={cohort} patient={fullModality} runId="test-run" />);
    const heatmap = screen.getByText("Compare every subgroup at once").closest("section")!;
    for (const family of [/Pathways/, /Transcription factors/, /Genes/]) {
      expect(within(heatmap).getAllByText(family).length).toBeGreaterThanOrEqual(2);
    }

    // The bug this replaced: one global maximum meant pathways, whose effects
    // top out near 1, were painted on a scale reaching ~6 and rendered blank.
    const profiles = cohort.cluster_profiles as Array<{ family: string; effect: number }>;
    const peak = (family: string) =>
      Math.max(...profiles.filter((r) => r.family === family).map((r) => Math.abs(r.effect)));
    expect(peak("gene")).toBeGreaterThan(peak("pathway") * 3);

    // Each family therefore prints its own scale bound, not one shared bound.
    const bounds = within(heatmap)
      .getAllByText(/^[+−]\d+\.\d{2}$/)
      .map((el) => el.textContent);
    expect(new Set(bounds).size).toBeGreaterThan(2);
  });

  it("never changes a data cell when a subgroup is selected", () => {
    render(<V3Workspace cohort={cohort} patient={fullModality} runId="test-run" />);
    const cell = screen.getAllByTitle(/^Trail · Subgroup 1 /)[0];
    const before = { background: cell.style.background, opacity: cell.style.opacity };

    // Selecting a different subgroup must not repaint or dim the data: opacity
    // encodes q >= 0.05 here and nothing else may borrow that channel.
    fireEvent.click(screen.getAllByRole("button", { name: /Subgroup 2/ })[0]);
    const after = screen.getAllByTitle(/^Trail · Subgroup 1 /)[0];
    expect(after.style.background).toBe(before.background);
    expect(after.style.opacity).toBe(before.opacity);
  });

  it("expands a feature inline rather than in a separate drawer", () => {
    render(<V3Workspace cohort={cohort} patient={fullModality} runId="test-run" />);
    expect(screen.queryByText("Subgroup detail")).not.toBeInTheDocument();
    const row = screen.getByRole("button", { name: /^Estrogen —/ });
    expect(row).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(row);
    expect(row).toHaveAttribute("aria-expanded", "true");
  });

  it("carries survival identity in a legend, not in colliding end-of-line labels", () => {
    render(<V3Workspace cohort={cohort} patient={fullModality} runId="test-run" />);
    const survival = screen.getByText("Kaplan-Meier by subgroup").closest("section")!;
    const legend = within(survival).getAllByRole("button", { name: /Subgroup \d.*events/ });
    expect(legend.length).toBe(4);
    fireEvent.click(legend[1]);
    expect(legend[1]).toHaveAttribute("aria-pressed", "true");
  });

  it("separates measured curves from ones extrapolated past the tested range", () => {
    render(<V3Workspace cohort={cohort} patient={fullModality} runId="test-run" />);
    const curves = fullModality.nearest_lines?.[0].curves ?? [];
    expect(curves.some((c) => c.ic50_extrapolated)).toBe(true);
    expect(curves.some((c) => !c.ic50_extrapolated)).toBe(true);
    expect(screen.getAllByText(/beyond tested range/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/a property of the fit, not an observation/)).toBeInTheDocument();
  });

  it("explains the cell-line similarity number and its axes", () => {
    render(<V3Workspace cohort={cohort} patient={fullModality} runId="test-run" />);
    expect(screen.getAllByText("cosine similarity in joint PCA space").length).toBeGreaterThanOrEqual(1);
    // Fingerprints are normalised across the retrieved set, so they are no longer
    // each pinned to their own peak.
    const prints = (fullModality.nearest_lines ?? []).map((l) => Math.max(...l.fingerprint.map(Math.abs)));
    expect(prints.filter((p) => p === 1).length).toBe(1);
  });

  it("labels retrieval as measurement and never as a recommendation", () => {
    render(<V3Workspace cohort={cohort} patient={fullModality} runId="test-run" />);
    expect(screen.getByText(/Not a simulation/)).toBeInTheDocument();
    expect(screen.getAllByText(/evidence, not as recommendations/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/order carries no meaning/i)).toBeInTheDocument();
    // Real compound names, not the compound_0 placeholders of the synthetic era.
    expect(screen.queryByText(/^compound_\d+$/)).not.toBeInTheDocument();
  });

  it("suppresses therapy for the abstaining patient but keeps clustering", () => {
    render(<V3Workspace cohort={cohort} patient={abstain} runId="test-run" />);
    expect(abstain.state).toBe(3);
    expect(screen.getByText("Compare every subgroup at once")).toBeInTheDocument();
    expect(screen.getByText("Where this tumour sits")).toBeInTheDocument();
    expect(screen.getByText(/Drug retrieval and the prognostic interval are withheld/)).toBeInTheDocument();
    expect(screen.queryByText(/Not a simulation/)).not.toBeInTheDocument();
  });

  it("groups reversal candidates by development status, never guessing one", () => {
    render(<V3Workspace cohort={cohort} patient={fullModality} runId="test-run" />);
    const retrieval = screen.getByText("Measured GDSC dose-response").closest("section")!;
    for (const label of [
      "Breast standard of care",
      "Under investigation",
      "Not usable in humans",
      // Unmatched compounds stay explicitly unclassified rather than tiered.
      "Not classified",
    ]) {
      expect(within(retrieval).getByRole("button", { name: `Show only ${label}` })).toBeInTheDocument();
    }

    // Each row carries what a reader screens on, not just a name.
    expect(within(retrieval).getByRole("button", { name: "palbociclib" })).toBeInTheDocument();
    expect(within(retrieval).getAllByText("CDK inhibitor").length).toBeGreaterThanOrEqual(1);
    expect(within(retrieval).getByLabelText("Filter reversal candidates")).toBeInTheDocument();

    const members = fullModality.reversal_candidates?.members ?? [];
    const soc = members.filter((m) => m.evidence_tier === "standard_of_care").map((m) => m.canonical);
    expect(soc).toEqual(expect.arrayContaining(["palbociclib", "fulvestrant", "tamoxifen"]));
    expect(members.every((m) => m.evidence_tier)).toBe(true);
  });

  it("tiers features from the curated reference and can filter by tier", () => {
    render(<V3Workspace cohort={cohort} patient={fullModality} runId="test-run" />);
    expect(cohort.evidence_reference?.curated_date).toBeTruthy();
    const established = screen.getByRole("button", { name: "Filter to Established role" });
    fireEvent.click(established);
    expect(established).toHaveAttribute("aria-pressed", "true");
  });

  it("opens the full feature list in a dialog instead of growing the panel", () => {
    render(<V3Workspace cohort={cohort} patient={fullModality} runId="test-run" />);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /View all \d+ genes/ }));
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getAllByText(/ranked by strongest effect/).length).toBeGreaterThanOrEqual(1);
  });

  it("explains the cell line and its similarity number on request", () => {
    render(<V3Workspace cohort={cohort} patient={fullModality} runId="test-run" />);
    fireEvent.click(screen.getAllByRole("button", { name: /how does it resemble this tumour/i })[0]);
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText(/cosine similarity/i)).toBeInTheDocument();
    expect(within(dialog).getByText(/does not mean/i)).toBeInTheDocument();
    expect(within(dialog).getByText(/bulk mRNA only/i)).toBeInTheDocument();
  });

  it("offers literature sources behind an evidence label, and says when there are none", async () => {
    render(<V3Workspace cohort={cohort} patient={fullModality} runId="test-run" />);
    fireEvent.click(screen.getByRole("button", { name: /^Estrogen —/ }));
    // The sources block is present and resolves to an explicit state rather than
    // silently rendering nothing.
    expect(screen.getByText("Sources")).toBeInTheDocument();
    // With no API reachable in jsdom the lookup must resolve to a stated reason,
    // never to a silent empty block that reads as "no evidence exists".
    expect(await screen.findByText(/Literature lookup is unavailable|No sources retrieved|No matching publications/i)).toBeInTheDocument();
  });

  it("keeps the exploratory p and its correction together, with no separate table", () => {
    render(<V3Workspace cohort={cohort} patient={fullModality} runId="test-run" />);
    fireEvent.change(screen.getByLabelText("Number of subgroups"), { target: { value: "5" } });

    // k=5 has a smaller raw p than the pre-registered k=4; it is shown, but the
    // BH-adjusted q is printed with it so it cannot be read on its own.
    const sweep = cohort.survival_sensitivity ?? [];
    expect(sweep.find((r) => r.k === 5)!.p_value).toBeLessThan(sweep.find((r) => r.k === 4)!.p_value);
    expect(screen.getByText(/log-rank p = 0\.016/)).toBeInTheDocument();
    expect(screen.getByText(/BH-adjusted q = 0\.070/)).toBeInTheDocument();
    expect(screen.queryByText(/This is the whole surface, not a result/)).not.toBeInTheDocument();
  });

  it("explains the projection space, and does not claim the VAE built it", () => {
    render(<V3Workspace cohort={cohort} patient={fullModality} runId="test-run" />);
    fireEvent.click(screen.getByRole("button", { name: /How is this space built/ }));
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText(/The encoder is a PCA, not the VAE/)).toBeInTheDocument();
    expect(within(dialog).getByText(/does not cover this cohort/)).toBeInTheDocument();
    expect(cohort.encoder).toBe("pca_intrinsic_expression");
  });

  it("renders dialogs outside the transformed panel so they are not clipped", () => {
    render(<V3Workspace cohort={cohort} patient={fullModality} runId="test-run" />);
    fireEvent.click(screen.getAllByRole("button", { name: /how does it resemble this tumour/i })[0]);
    const dialog = screen.getByRole("dialog");
    // A PanelCard carries a Motion transform, which would make a nested
    // position:fixed dialog resolve against the card instead of the viewport.
    expect(dialog.closest("section")).toBeNull();
    expect(dialog.parentElement?.parentElement).toBe(document.body);
  });

  it("plots the line against the cohort and the patient, inside its explanation", () => {
    render(<V3Workspace cohort={cohort} patient={fullModality} runId="test-run" />);
    expect(cohort.joint_projection?.patients?.[fullModality.patient_id]).toBeTruthy();
    // The card stays compact; the plot lives where there is room to read it.
    expect(screen.queryByLabelText(/relative to the tumour cohort and this patient/)).not.toBeInTheDocument();

    fireEvent.click(screen.getAllByRole("button", { name: /how does it resemble this tumour/i })[0]);
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByLabelText(/relative to the tumour cohort and this patient/)).toBeInTheDocument();
  });

  it("plots only the drugs the reader picks, defaulting to the retrieved ones", () => {
    render(<V3Workspace cohort={cohort} patient={fullModality} runId="test-run" />);
    const curves = fullModality.nearest_lines?.[0].curves ?? [];
    const candidates = new Set(
      (fullModality.reversal_candidates?.members ?? []).map((m) => String(m.canonical || m.drug).toLowerCase())
    );
    // Every drug GDSC measured on the line is offered, including ones that were
    // never retrieved, and the retrieved ones start plotted.
    expect(curves.length).toBeGreaterThan(4);
    expect(curves.some((c) => candidates.has(String(c.canonical || c.drug).toLowerCase()))).toBe(true);
    expect(screen.getByRole("button", { name: new RegExp(`Plot all ${curves.length}`) })).toBeInTheDocument();
    // The tag states the drug's own status. "retrieved" is a separate fact:
    // lapatinib is a breast standard of care that was not retrieved.
    const efm = fullModality.nearest_lines?.[0].curves ?? [];
    expect(efm.find((c) => c.canonical === "lapatinib")?.retrieved).toBe(false);
    expect(efm.find((c) => c.canonical === "lapatinib")?.evidence_tier).toBe("standard_of_care");
    expect(efm.find((c) => c.canonical === "taselisib")?.retrieved).toBe(true);
    expect(efm.find((c) => c.canonical === "taselisib")?.evidence_tier).toBe("investigational");
    expect(screen.getAllByText("Breast standard of care").length).toBeGreaterThanOrEqual(1);
  });

  it("does not let a 13-member subgroup set the colour scale for the rest", () => {
    render(<V3Workspace cohort={cohort} patient={fullModality} runId="test-run" />);
    const profiles = cohort.cluster_profiles as Array<{ family: string; cluster: number; effect: number }>;
    const genes = profiles.filter((r) => r.family === "gene");
    const small = Object.values(cohort.cluster_annotations ?? {}).find((a) => a.n < 30)!;
    expect(small.n).toBe(13);

    // The extreme tail is entirely that one subgroup's, which is why the scale
    // must come from the subgroups large enough for a mean to be stable.
    const sorted = genes.map((r) => Math.abs(r.effect)).sort((a, b) => a - b);
    const p95 = sorted[Math.floor(sorted.length * 0.95)];
    const beyond = genes.filter((r) => Math.abs(r.effect) > p95);
    expect(beyond.length).toBeGreaterThan(0);
    expect(beyond.every((r) => r.cluster === small.cluster)).toBe(true);

    expect(screen.getByText(/set from subgroups of at least 30 tumours/)).toBeInTheDocument();
  });

  it("offers every feature, not a variance-ranked slice", () => {
    render(<V3Workspace cohort={cohort} patient={fullModality} runId="test-run" />);
    const profiles = cohort.cluster_profiles as Array<{ family: string; feature: string }>;
    const genes = new Set(profiles.filter((r) => r.family === "gene").map((r) => r.feature));
    const tfs = new Set(profiles.filter((r) => r.family === "tf").map((r) => r.feature));
    expect(genes.size).toBeGreaterThan(2000);
    expect(tfs.size).toBeGreaterThan(400);

    fireEvent.click(screen.getByRole("button", { name: /View all \d+ genes/ }));
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByLabelText("Search features")).toBeInTheDocument();

    // Ranking within one subgroup and one direction, not just by magnitude.
    fireEvent.click(within(dialog).getByRole("button", { name: "Rank by Subgroup 2" }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Most reduced" }));
    expect(within(dialog).getByText(/most reduced in Subgroup 2/)).toBeInTheDocument();
  });

  it("shows no raw snake_case identifiers anywhere on screen", () => {
    const { container } = render(<V3Workspace cohort={cohort} patient={fullModality} runId="test-run" />);
    const text = container.textContent ?? "";
    // Schema keys are provenance records, not prose.
    for (const leak of ["gdsc_measured_hill", "lincs_breast_trt_cp", "connectivity_reversal_top_n", "pca_intrinsic_expression"]) {
      expect(text).not.toContain(leak);
    }
  });

  it("carries no retired v1 vocabulary into user-facing copy", () => {
    const { container } = render(<V3Workspace cohort={cohort} patient={fullModality} runId="test-run" />);
    const text = container.textContent ?? "";
    expect(text).not.toMatch(/MOFA/i);
    expect(text).not.toMatch(/surrogate/i);
    expect(text).not.toMatch(/RNA-only/i);
  });
});
