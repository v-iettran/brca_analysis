"use client";

import { useEffect, useMemo, useState } from "react";
import { getDrugLiterature, getGeneLiterature } from "@/lib/api";
import type { CitationOut } from "@/lib/types";
import { StanceLegend } from "./StanceLegend";
import { STANCE_META, STANCE_ORDER, type Stance } from "./StanceGlossary";

type Result = {
  citations: CitationOut[];
  unavailable_reason?: string;
  cache_hit?: boolean;
  deduplicated_count?: number;
  raw_result_count?: number;
  interpretation_note?: string;
};

type SortKey = "rank" | "year_desc" | "year_asc" | "title" | "stance";

const SORTS: { key: SortKey; label: string }[] = [
  { key: "rank", label: "Rank" },
  { key: "year_desc", label: "Newest" },
  { key: "year_asc", label: "Oldest" },
  { key: "title", label: "A–Z" },
  { key: "stance", label: "Stance" },
];

const PAGE = 8;

/** Best available public link. Every retrieved record has had at least one of these. */
function linkFor(c: CitationOut): string | null {
  if (c.doi) return `https://doi.org/${c.doi}`;
  if (c.pmid) return `https://pubmed.ncbi.nlm.nih.gov/${c.pmid}/`;
  if (c.pmcid) return `https://www.ncbi.nlm.nih.gov/pmc/articles/${c.pmcid}/`;
  return null;
}

/**
 * Where a record was published. `journal` is the real answer when Paperclip
 * supplies one; `source` is the repository it was retrieved from, which is
 * weaker but still tells a reader whether they are looking at a preprint.
 */
function venueFor(c: CitationOut): { text: string; muted: boolean } | null {
  if (c.journal) return { text: c.journal, muted: false };
  if (c.publisher) return { text: c.publisher, muted: false };
  if (c.source) return { text: c.source, muted: true };
  return null;
}

function key(c: CitationOut, i: number): string {
  return c.doi || c.pmid || c.pmcid || `${c.title}-${i}`;
}

/**
 * Sources behind an evidence label, fetched on demand from the literature agent.
 *
 * The tier itself is curated and never comes from here — this is the reading
 * behind it. Publication counts describe attention, not truth, so nothing in
 * this component upgrades a tier or validates a coefficient.
 */
export function LiteratureCitations({
  runId,
  subject,
  kind,
  clusterId = 0,
}: {
  runId: string;
  subject: string;
  kind: "feature" | "drug";
  clusterId?: number;
}) {
  const [state, setState] = useState<"loading" | "done" | "error">("loading");
  const [result, setResult] = useState<Result | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [active, setActive] = useState<Set<Stance>>(new Set());
  const [sort, setSort] = useState<SortKey>("rank");
  const [expanded, setExpanded] = useState(false);

  // Reset during render rather than in an effect when the subject changes, so a
  // stale result never flashes under a new heading.
  const [seen, setSeen] = useState(subject);
  if (seen !== subject) {
    setSeen(subject);
    setState("loading");
    setResult(null);
    setMessage(null);
    setActive(new Set());
    setSort("rank");
    setExpanded(false);
  }

  useEffect(() => {
    let live = true;
    const request =
      kind === "drug"
        ? getDrugLiterature(runId, subject)
        : getGeneLiterature(runId, clusterId, subject);
    request
      .then((data) => {
        if (!live) return;
        setResult(data as unknown as Result);
        setState("done");
      })
      .catch((error: unknown) => {
        if (!live) return;
        setMessage(error instanceof Error ? error.message : "Literature lookup failed.");
        setState("error");
      });
    return () => {
      live = false;
    };
  }, [runId, subject, kind, clusterId]);

  const citations = useMemo(() => result?.citations ?? [], [result]);

  const counts = useMemo(() => {
    const out = { supporting: 0, conflicting: 0, neutral: 0, unclear: 0 } as Record<Stance, number>;
    for (const c of citations) if (c.stance in out) out[c.stance] += 1;
    return out;
  }, [citations]);

  const visible = useMemo(() => {
    const filtered = active.size ? citations.filter((c) => active.has(c.stance)) : citations.slice();
    const rank = (c: CitationOut) => c.evidence_rank ?? Number.MAX_SAFE_INTEGER;
    // Records with no year sort last in both directions rather than clustering
    // at one end, which would read as "these are the oldest".
    const byYear = (a: CitationOut, b: CitationOut, dir: number) => {
      if (a.year == null && b.year == null) return rank(a) - rank(b);
      if (a.year == null) return 1;
      if (b.year == null) return -1;
      return (b.year - a.year) * dir;
    };
    const order = (s: Stance) => STANCE_ORDER.indexOf(s);
    filtered.sort((a, b) => {
      switch (sort) {
        case "year_desc":
          return byYear(a, b, 1);
        case "year_asc":
          return byYear(a, b, -1);
        case "title":
          return a.title.localeCompare(b.title);
        case "stance":
          return order(a.stance) - order(b.stance) || rank(a) - rank(b);
        default:
          return rank(a) - rank(b);
      }
    });
    return filtered;
  }, [citations, active, sort]);

  if (state === "loading") {
    return <p className="text-[11.5px] text-[var(--text-muted)]">Searching the literature…</p>;
  }

  if (state === "error") {
    return (
      <p className="text-[11.5px] text-[var(--text-muted)]">
        Literature lookup is unavailable for this entity. {message}
      </p>
    );
  }

  if (result?.unavailable_reason) {
    return (
      <div className="rounded-[var(--radius-inner)] border border-[var(--warning-line)] bg-[var(--warning-wash)] p-2.5">
        <p className="text-[11.5px] text-[var(--text-secondary)]">
          No sources retrieved. {result.unavailable_reason}
        </p>
        <p className="mt-1 text-[10.5px] text-[var(--text-muted)]">
          The evidence label above is from the committed reference file and does not depend on this
          lookup.
        </p>
      </div>
    );
  }

  if (!citations.length) {
    return (
      <p className="text-[11.5px] text-[var(--text-muted)]">
        No matching publications were returned for {subject}.
      </p>
    );
  }

  const shown = expanded ? visible : visible.slice(0, PAGE);
  const toggle = (stance: Stance) =>
    setActive((prev) => {
      const next = new Set(prev);
      if (next.has(stance)) next.delete(stance);
      else next.add(stance);
      return next;
    });

  return (
    <div>
      <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
        <StanceLegend counts={counts} active={active} onToggle={toggle} />
        <div className="flex items-center gap-1">
          <span className="text-[10px] uppercase tracking-[0.08em] text-[var(--text-muted)]">Sort</span>
          {SORTS.map((option) => (
            <button
              key={option.key}
              type="button"
              aria-pressed={sort === option.key}
              onClick={() => setSort(option.key)}
              className={`rounded-full px-1.5 py-[3px] text-[10.5px] transition-colors ${
                sort === option.key
                  ? "bg-[var(--surface-raised)] text-[var(--text-primary)]"
                  : "text-[var(--text-muted)] hover:text-[var(--text-secondary)]"
              }`}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>

      <p className="mt-1.5 text-[10.5px] text-[var(--text-muted)]">
        {active.size ? `${visible.length} of ` : ""}
        {citations.length} of {result?.raw_result_count ?? citations.length} retrieved records,
        deduplicated and ranked by credibility and relevance
        {result?.cache_hit ? " · cached" : ""}.
      </p>

      <ul
        aria-label="Retrieved sources"
        className="mt-1.5 divide-y divide-[var(--line)] border-t border-[var(--line)]"
      >
        {shown.map((citation, i) => {
          const href = linkFor(citation);
          const venue = venueFor(citation);
          const meta = STANCE_META[citation.stance] ?? STANCE_META.unclear;
          return (
            <li
              key={key(citation, i)}
              className="grid grid-cols-[1fr_auto] items-baseline gap-x-3 gap-y-0.5 py-1.5 sm:grid-cols-[1fr_9rem_2.6rem_5.6rem]"
            >
              <span className="text-[11.5px] leading-snug text-[var(--text-primary)]">
                {href ? (
                  <a
                    href={href}
                    target="_blank"
                    rel="noreferrer"
                    className="underline decoration-[var(--line-strong)] underline-offset-2 transition-colors hover:decoration-[var(--text-primary)]"
                  >
                    {citation.title}
                    <span aria-hidden className="ml-0.5 text-[9px] text-[var(--text-muted)]">
                      ↗
                    </span>
                  </a>
                ) : (
                  citation.title
                )}
              </span>

              <span
                className="col-start-1 text-[10.5px] text-[var(--text-muted)] sm:col-start-2 sm:truncate"
                title={venue?.text}
              >
                {venue ? (
                  <>
                    {venue.text}
                    {venue.muted && (
                      <span className="ml-1 text-[9px] uppercase tracking-[0.06em] opacity-70">
                        repo
                      </span>
                    )}
                  </>
                ) : (
                  <span className="opacity-50">—</span>
                )}
              </span>

              <span className="hidden font-mono text-[10.5px] text-[var(--text-muted)] sm:inline">
                {citation.year ?? <span className="opacity-50">—</span>}
              </span>

              <span
                className="inline-flex items-center gap-1 justify-self-start text-[10.5px] sm:justify-self-end"
                title={meta.rule}
              >
                <span aria-hidden style={{ color: meta.colorVar }}>
                  {meta.glyph}
                </span>
                <span style={{ color: meta.colorVar }}>{meta.label}</span>
              </span>
            </li>
          );
        })}
      </ul>

      {visible.length > PAGE && (
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="mt-1.5 text-[10.5px] text-[var(--text-secondary)] underline underline-offset-2 transition-colors hover:text-[var(--text-primary)]"
        >
          {expanded ? "Show fewer" : `Show all ${visible.length}`}
        </button>
      )}

      {!visible.length && (
        <p className="py-2 text-[11px] text-[var(--text-muted)]">
          No sources with that stance. Clear the filter to see all {citations.length}.
        </p>
      )}

      {result?.interpretation_note && (
        <p className="mt-2 text-[10.5px] text-[var(--text-muted)]">{result.interpretation_note}</p>
      )}
    </div>
  );
}
