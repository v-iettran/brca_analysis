/**
 * Rendered against records captured from the live Paperclip integration.
 *
 * Every one of them has a null year, journal and publisher, because the adapter
 * was falling back to parsing formatted text. That is fixed, but the panel must
 * stay readable when a record genuinely carries no metadata — Paperclip returns
 * plenty of those — so this fixture is kept exactly as the API returned it.
 */
import { it, expect, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import { LiteratureCitations } from "@/components/LiteratureCitations";
import { getDrugLiterature } from "@/lib/api";
import real from "./fixtures/real_literature.json";

vi.mock("@/lib/api", () => ({ getDrugLiterature: vi.fn(), getGeneLiterature: vi.fn() }));

const list = () => within(screen.getByRole("list", { name: "Retrieved sources" }));

it("stays readable when records carry no year, journal or publisher", async () => {
  vi.mocked(getDrugLiterature).mockResolvedValue(real as never);
  render(<LiteratureCitations runId="r" subject="doxorubicin" kind="drug" />);
  await waitFor(() => expect(list().getAllByRole("listitem").length).toBeGreaterThan(0));

  // Titles and links survive even when everything else is missing.
  const rows = list().getAllByRole("listitem");
  expect(rows.length).toBe(8);
  for (const row of rows) {
    expect(within(row).getByRole("link")).toHaveAttribute("href", expect.stringContaining("http"));
  }

  // Counts come from the data, not a hardcoded list.
  expect(screen.getByRole("button", { name: /^Neutral: 4 source/ })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /^Conflicts: 4 source/ })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /^Supports: 4 source/ })).toBeInTheDocument();
  // Nothing had this stance, so its chip is present but not selectable.
  expect(screen.getByRole("button", { name: /^Unclear: 0 source/ })).toBeDisabled();

  expect(screen.getByText("Show all 12")).toBeInTheDocument();
});
