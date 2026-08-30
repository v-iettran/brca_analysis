import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { LiteratureCitations } from "@/components/LiteratureCitations";
import { getDrugLiterature, getGeneLiterature } from "@/lib/api";

vi.mock("@/lib/api", () => ({
  getDrugLiterature: vi.fn(),
  getGeneLiterature: vi.fn(),
}));

const base = {
  title: "",
  year: null as number | null,
  doi: null as string | null,
  pmid: null as string | null,
  pmcid: null as string | null,
  journal: null as string | null,
  publisher: null as string | null,
  source: null as string | null,
  article_type: null as string | null,
  peer_reviewed: null as boolean | null,
  full_text_available: null as boolean | null,
  excerpt: null as string | null,
  stance: "neutral" as const,
  matched_queries: [] as string[],
};

const CITATIONS = [
  { ...base, title: "Zeta trial of lapatinib", year: 2011, journal: "Lancet Oncol", doi: "10.1/z", stance: "supporting" as const, evidence_rank: 2 },
  { ...base, title: "Alpha resistance mechanisms", year: 2019, journal: "Cancers", pmid: "111", stance: "conflicting" as const, evidence_rank: 1 },
  { ...base, title: "Mid review of doxorubicin", source: "PMC", pmcid: "PMC900", stance: "neutral" as const, evidence_rank: 3 },
  { ...base, title: "Beta ambiguous readout", year: 2004, stance: "unclear" as const, pmcid: "PMC901", evidence_rank: 4 },
];

function payload(citations = CITATIONS) {
  return {
    drug: "lapatinib",
    query_families: [],
    citations,
    deduplicated_count: citations.length,
    raw_result_count: 40,
    cache_hit: false,
    searched_at: new Date().toISOString(),
  };
}

async function renderList(citations = CITATIONS) {
  vi.mocked(getDrugLiterature).mockResolvedValue(payload(citations) as never);
  render(<LiteratureCitations runId="r1" subject="lapatinib" kind="drug" />);
  await waitFor(() => expect(titles().length).toBeGreaterThan(0));
}

// Scoped to the source list: the stance tooltip also renders a <ul> of phrases.
const titles = () =>
  within(screen.getByRole("list", { name: "Retrieved sources" }))
    .getAllByRole("listitem")
    .map((li) => li.textContent?.split("↗")[0]?.trim() ?? "");

beforeEach(() => vi.clearAllMocks());

describe("LiteratureCitations", () => {
  it("shows title, venue, year and a stance label for each source", async () => {
    await renderList();
    const row = screen.getByRole("link", { name: /Zeta trial of lapatinib/ }).closest("li")!;
    expect(within(row).getByText("Lancet Oncol")).toBeInTheDocument();
    expect(within(row).getByText("2011")).toBeInTheDocument();
    expect(within(row).getByText("Supports")).toBeInTheDocument();
  });

  it("links DOI, PMID and PMCID records to the right resolver", async () => {
    await renderList();
    expect(screen.getByRole("link", { name: /Zeta trial/ })).toHaveAttribute("href", "https://doi.org/10.1/z");
    expect(screen.getByRole("link", { name: /Alpha resistance/ })).toHaveAttribute(
      "href",
      "https://pubmed.ncbi.nlm.nih.gov/111/",
    );
    expect(screen.getByRole("link", { name: /Mid review/ })).toHaveAttribute(
      "href",
      "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC900/",
    );
  });

  it("labels a repository fallback as such rather than passing it off as a journal", async () => {
    await renderList();
    const row = screen.getByRole("link", { name: /Mid review/ }).closest("li")!;
    expect(within(row).getByText("PMC")).toBeInTheDocument();
    expect(within(row).getByText("repo")).toBeInTheDocument();
  });

  it("counts each stance in the legend", async () => {
    await renderList();
    for (const label of ["Supports", "Conflicts", "Neutral", "Unclear"]) {
      expect(screen.getByRole("button", { name: new RegExp(`^${label}: 1 source`) })).toBeInTheDocument();
    }
  });

  it("filters to a stance and back", async () => {
    const user = userEvent.setup();
    await renderList();
    await user.click(screen.getByRole("button", { name: /^Conflicts: 1 source/ }));
    expect(titles()).toEqual(["Alpha resistance mechanisms"]);
    await user.click(screen.getByRole("button", { name: "clear" }));
    expect(titles()).toHaveLength(4);
  });

  it("sorts by year newest first, keeping undated records last", async () => {
    const user = userEvent.setup();
    await renderList();
    await user.click(screen.getByRole("button", { name: "Newest" }));
    expect(titles()).toEqual([
      "Alpha resistance mechanisms", // 2019
      "Zeta trial of lapatinib", // 2011
      "Beta ambiguous readout", // 2004
      "Mid review of doxorubicin", // no year -> last
    ]);
  });

  it("keeps undated records last when sorting oldest first too", async () => {
    const user = userEvent.setup();
    await renderList();
    await user.click(screen.getByRole("button", { name: "Oldest" }));
    expect(titles()[3]).toBe("Mid review of doxorubicin");
    expect(titles()[0]).toBe("Beta ambiguous readout");
  });

  it("defaults to the server's evidence rank", async () => {
    await renderList();
    expect(titles()[0]).toBe("Alpha resistance mechanisms");
  });

  it("explains on hover how a stance is decided, quoting the real phrases", async () => {
    const user = userEvent.setup();
    await renderList();
    await user.hover(screen.getByRole("button", { name: /^Conflicts: 1 source/ }));
    const tip = await screen.findByRole("tooltip");
    expect(tip).toHaveTextContent(/conflicting language and none of the supporting/i);
    expect(tip).toHaveTextContent("adverse event(s)");
    expect(tip).toHaveTextContent(/not from reading the paper/i);
  });

  it("never encodes stance with colour alone", async () => {
    await renderList();
    // Every row carries the word as well as the swatch.
    for (const label of ["Supports", "Conflicts", "Neutral", "Unclear"]) {
      expect(screen.getAllByText(label).length).toBeGreaterThan(0);
    }
  });

  it("still reports the unavailable reason instead of an empty list", async () => {
    vi.mocked(getGeneLiterature).mockResolvedValue({
      citations: [],
      unavailable_reason: "Paperclip SDK is not installed or PAPERCLIP_API_KEY is not set.",
    } as never);
    render(<LiteratureCitations runId="r1" subject="ERBB2" kind="feature" clusterId={1} />);
    expect(await screen.findByText(/No sources retrieved/)).toBeInTheDocument();
    expect(screen.getByText(/does not depend on this lookup/)).toBeInTheDocument();
  });
});
