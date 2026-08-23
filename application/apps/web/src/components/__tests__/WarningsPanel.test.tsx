import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { WarningsPanel } from "@/components/WarningsPanel";

describe("WarningsPanel", () => {
  it("renders nothing when there are no warnings", () => {
    const { container } = render(<WarningsPanel warnings={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders each warning with its severity badge and message", () => {
    render(
      <WarningsPanel
        warnings={[
          { severity: "caution", message: "Gene coverage is below the recommended threshold." },
          { severity: "abstain", message: "Insufficient data to assign a cluster." },
        ]}
      />
    );

    expect(screen.getByText(/gene coverage is below/i)).toBeInTheDocument();
    expect(screen.getByText(/insufficient data to assign/i)).toBeInTheDocument();
    expect(screen.getByText("caution")).toBeInTheDocument();
    expect(screen.getByText("abstain")).toBeInTheDocument();
  });
});
