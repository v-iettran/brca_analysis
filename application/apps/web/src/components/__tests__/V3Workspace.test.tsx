import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { V3Workspace } from "@/components/V3Workspace";
import type { V3CohortPayload, V3PatientPayload } from "@/lib/v3-types";

function km(cluster: number) {
  return {
    time: [0, 12, 24],
    survival: [1, 0.8, 0.5],
    lower: [1, 0.7, 0.4],
    upper: [1, 0.9, 0.6],
    at_risk: [30, 20, 10],
    cluster,
  };
}

function config(k: number, exploratory: boolean, p: number | null) {
  const assignments: Record<string, number> = { "TCGA-A8-A081": 0, "TCGA-XX-0001": 1 };
  return {
    method: "gmm" as const,
    covariance_type: "full",
    k,
    exploratory,
    assignments,
    membership: { "TCGA-A8-A081": [0.9, 0.1], "TCGA-XX-0001": [0.2, 0.8] },
    km: {
      os: { curves: { "0": km(0), "1": km(1) }, p_value: p, n: 30, n_events: 8, exploratory },
      pfi: { curves: { "0": km(0), "1": km(1) }, p_value: p, n: 30, n_events: 10, exploratory },
    },
  };
}

const cohort: V3CohortPayload = {
  schema_version: "v3_cluster",
  encoder: "jax_poe_vae",
  clustering_available: true,
  preregistered: {
    k: 3,
    timestamp: "2026-01-01T00:00:00Z",
    selection_rule: "stability_within_10_bic",
    method: "gmm",
    covariance_type: "full",
    clustering_available: true,
    stability_threshold: 0.6,
  },
  model_selection: [2, 3, 4].map((k) => ({ k, bic: 100 - k, silhouette: 0.4, stability: 0.7 })),
  gates: {
    a1: { passed: true },
    a2: { passed: false, p_os: 0.14, framing: "descriptive" },
    a4: { passed: true, reversal_available: true },
  },
  projections: {
    umap: { "TCGA-A8-A081": [0.1, 0.2], "TCGA-XX-0001": [1, 1] },
    pca: { "TCGA-A8-A081": [0.1, 0.2], "TCGA-XX-0001": [1, 1] },
  },
  projection_meta: { default: "pca", pca_variance_ratio: [0.34, 0.19], umap_note: "UMAP distances between clusters are not meaningful." },
  posterior_width: { "TCGA-A8-A081": 0.4, "TCGA-XX-0001": 0.5 },
  configurations: {
    "gmm:full:k=3": config(3, false, 0.14),
    "gmm:full:k=4": config(4, true, null),
    "kmeans:na:k=3": { ...config(3, true, null), method: "kmeans", covariance_type: null },
  },
  cluster_profiles: [
    { feature: "Estrogen", family: "pathway", cluster: 0, effect: 0.8, q: 0.01 },
    { feature: "EGFR", family: "pathway", cluster: 1, effect: 0.6, q: 0.02 },
  ],
  comparison_matrix: {
    features: ["Estrogen", "EGFR"],
    families: ["pathway", "pathway"],
    clusters: [0, 1],
    effects: [
      [0.8, -0.2],
      [-0.1, 0.6],
    ],
    q: [
      [0.01, 0.4],
      [0.5, 0.02],
    ],
  },
  cluster_annotations: {
    "0": { cluster: 0, n: 20, esr1_mean: 1, erbb2_mean: 0, prolif_mean: 0, er_high: true },
  },
};

const basePatient: V3PatientPayload = {
  schema_version: "v3_cluster",
  patient_id: "TCGA-A8-A081",
  role: "full_modality",
  encoder: "jax_poe_vae",
  state: 1,
  modalities_present: ["rna", "cna", "methylation"],
  pam50: "LumB",
  patient_metadata: {},
  sample_quality: {
    tumour_fraction: 0.72,
    composition: [{ cell_type: "malignant", fraction: 0.72, ci: [0.68, 0.76] }],
    verdict: "sufficient",
  },
  position: { umap_coords: [0.1, 0.2], posterior_width: 0.4, cluster: { label: 0, posterior_mass: 0.9 }, membership: [0.9, 0.1] },
  abstention: { abstained: false, what_would_help: [], sections_rendered: [] },
  prognostic_estimate: {
    requested_coverage: 0.92,
    n: 10,
    method: "MAPIE",
    label: "SCAN-B overall survival interval",
    domain_note: "Domain transfer note.",
    validated: true,
    interval_days: [400, 2000],
  },
  reversal_candidates: {
    members: [{ drug: "tamoxifen" }, { drug: "palbociclib" }],
    validated: false,
    threshold_rule: "connectivity_reversal_top_n",
    order_carries_no_meaning: true,
    source: "synthetic_smoke",
  },
  nearest_lines: [
    {
      line_id: "MCF7",
      name: "MCF7",
      similarity: 0.9,
      rank: 1,
      pam50: "LumA",
      fingerprint: [0.4, 0.3, 0.1, 0.1, 0.1],
      curves: [
        {
          drug: "palbociclib",
          line_id: "MCF7",
          concentration_nm: [1, 250, 1000],
          viability: [0.95, 0.5, 0.2],
          lower: [0.9, 0.4, 0.1],
          upper: [1, 0.6, 0.3],
          ic50_nm: 250,
          cmax_nm: 250,
          source: "gdsc_measured_hill",
          measured: true,
          simulation: false,
        },
      ],
    },
  ],
  limitations: ["Cluster count is chosen from structure, never from survival."],
  s4_ships: false,
};

describe("V3Workspace", () => {
  it("couples exploratory badges and hides p-values off the pre-registered k", () => {
    render(<V3Workspace cohort={cohort} patient={basePatient} />);
    expect(screen.getAllByText(/did not separate survival/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/Months since diagnosis/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Overall survival probability")).toBeInTheDocument();
    expect(screen.getByLabelText("PCA")).toBeChecked();
    expect(screen.queryByTestId("exploratory-badge")).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Number of subgroups"), { target: { value: "4" } });
    expect(screen.getAllByText("exploratory").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText(/p-value withheld/i)).toBeInTheDocument();
  });

  it("state 3 keeps B2/B3 and suppresses drug retrieval plus prognosis", () => {
    const abstain: V3PatientPayload = {
      ...basePatient,
      patient_id: "TCGA-A1-A0SK",
      state: 3,
      modalities_present: ["rna"],
      abstention: {
        abstained: true,
        reason_text: "Posterior width exceeds the abstention threshold.",
        what_would_help: ["Adding CNA"],
        sections_rendered: ["sample_quality"],
      },
      prognostic_estimate: null,
      reversal_candidates: null,
      nearest_lines: null,
    };
    render(<V3Workspace cohort={cohort} patient={abstain} />);
    expect(screen.getByText(/Control board/i)).toBeInTheDocument();
    expect(screen.getByText(/Compare every subgroup/i)).toBeInTheDocument();
    expect(screen.getByText(/Drug retrieval and the prognostic interval are withheld/i)).toBeInTheDocument();
    expect(screen.queryByText(/Not a simulation/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/SCAN-B overall survival interval/i)).not.toBeInTheDocument();
  });

  it("omits reversal members when the normal-reference gate failed", () => {
    const failed = { ...cohort, gates: { ...cohort.gates, a4: { passed: false, reversal_available: false } } };
    render(<V3Workspace cohort={failed} patient={basePatient} />);
    expect(screen.getByText(/reversal is omitted/i)).toBeInTheDocument();
    expect(screen.queryByText("tamoxifen")).not.toBeInTheDocument();
    expect(screen.getByText("MCF7")).toBeInTheDocument();
  });

  it("labels dose-response as measurement and tracks the slider", () => {
    render(<V3Workspace cohort={cohort} patient={basePatient} />);
    expect(screen.getByText(/Not a simulation/i)).toBeInTheDocument();
    expect(screen.getByTestId("dose-readout").textContent).toMatch(/MCF7/);
    fireEvent.change(screen.getByLabelText("Concentration (nM)"), { target: { value: "1000" } });
    expect(screen.getByTestId("dose-readout").textContent).toMatch(/1000 nM/);
  });
});
