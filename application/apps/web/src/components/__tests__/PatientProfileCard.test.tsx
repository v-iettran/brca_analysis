import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PatientProfileCard } from "@/components/PatientProfileCard";

describe("PatientProfileCard", () => {
  it("shows the de-identified patient metadata and administered regimen", () => {
    render(
      <PatientProfileCard
        patientLabel="SYN-HIG-123"
        metadata={{
          age_at_diagnosis: 58.7,
          er_status: "Positive",
          her2_status: "Negative",
          histological_subtype: "Ductal/NST",
          lymph_nodes_positive: 2,
          menopausal_state: "Post",
          organ_function: {
            creatinine_mg_dl: 1.07,
            bilirubin_mg_dl: 0.8,
            alt_u_l: 38.2,
          },
          location: {
            city: "Cork",
            country: "Ireland",
            latitude: 51.8985,
            longitude: -8.4756,
          },
        }}
        regimen={["doxorubicin", "paclitaxel"]}
      />
    );

    expect(screen.getByText("SYN-HIG-123")).toBeInTheDocument();
    expect(screen.getByText("59 years")).toBeInTheDocument();
    expect(screen.getByText("Positive")).toBeInTheDocument();
    expect(screen.getByText("Negative")).toBeInTheDocument();
    expect(screen.getByText("doxorubicin + paclitaxel")).toBeInTheDocument();
    expect(screen.getByText(/Creatinine 1\.07 mg\/dL/i)).toBeInTheDocument();
    expect(screen.getByText("Cork, Ireland")).toBeInTheDocument();
    expect(screen.queryByText(/latitude/i)).not.toBeInTheDocument();
  });

  it("corrects the METABRIC ER_IHC Positve typo", () => {
    render(
      <PatientProfileCard
        patientLabel="SYN-HIG-123"
        metadata={{ er_status: "Positve" }}
        regimen={[]}
      />
    );
    expect(screen.getByText("Positive")).toBeInTheDocument();
    expect(screen.queryByText("Positve")).not.toBeInTheDocument();
  });
});
