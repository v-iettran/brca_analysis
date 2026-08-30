import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AnswerText } from "@/components/AnswerText";

/**
 * Local models emit markdown whatever the prompt says, so the renderer is the
 * thing that has to be reliable. These assert that the markers never reach the
 * screen and that the output stays plain elements rather than injected HTML.
 */
describe("AnswerText", () => {
  it("renders markdown structure without showing its markers", () => {
    const answer = [
      "### Analysis of Drug Response",
      "",
      "The suitability is inferred from the **molecular profile** of the subgroup.",
      "",
      "- **Lapatinib**: within the tested range",
      "- *Taselisib*: under investigation",
      "",
      "1. First point",
      "2. Second point",
    ].join("\n");

    const { container } = render(<AnswerText text={answer} />);
    const text = container.textContent ?? "";

    expect(text).not.toContain("###");
    expect(text).not.toContain("**");
    expect(text).not.toMatch(/(^|\s)- /);

    expect(screen.getByText("Analysis of Drug Response")).toBeInTheDocument();
    expect(screen.getByText("molecular profile").tagName).toBe("STRONG");
    expect(screen.getByText("Taselisib").tagName).toBe("EM");
    expect(container.querySelectorAll("ul li")).toHaveLength(2);
    expect(container.querySelectorAll("ol li")).toHaveLength(2);
  });

  it("leaves ordinary prose untouched", () => {
    render(<AnswerText text="This tumour sits in subgroup 1 of 4." />);
    expect(screen.getByText("This tumour sits in subgroup 1 of 4.")).toBeInTheDocument();
  });

  it("never renders model output as HTML", () => {
    // Model output is untrusted; a markdown library passing raw HTML through
    // would turn a hallucination into an injection.
    const { container } = render(
      <AnswerText text={'<img src=x onerror="alert(1)"> and <b>bold</b>'} />
    );
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("b")).toBeNull();
    expect(container.textContent).toContain("<img src=x");
  });

  it("keeps inline code readable", () => {
    render(<AnswerText text="The gate rejected `0.0021` as untraceable." />);
    expect(screen.getByText("0.0021").tagName).toBe("CODE");
  });
});
