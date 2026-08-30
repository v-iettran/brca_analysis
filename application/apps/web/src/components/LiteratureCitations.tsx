"use client";

import { useEffect, useState } from "react";
import { getDrugLiterature, getGeneLiterature } from "@/lib/api";
import type { CitationOut } from "@/lib/types";

type Result = {
  citations: CitationOut[];
  unavailable_reason?: string;
  cache_hit?: boolean;
  deduplicated_count?: number;
  raw_result_count?: number;
  interpretation_note?: string;
};

const STANCE_LABEL: Record<string, string> = {
  supporting: "supports",
  conflicting: "conflicts",
  neutral: "neutral",
  unclear: "unclear",
};

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

  // Reset during render rather than in an effect when the subject changes, so a
  // stale result never flashes under a new heading.
  const [seen, setSeen] = useState(subject);
  if (seen !== subject) {
    setSeen(subject);
    setState("loading");
    setResult(null);
    setMessage(null);
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

  const citations = result?.citations ?? [];

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

  return (
    <div>
      <p className="text-[10.5px] text-[var(--text-muted)]">
        {citations.length} of {result?.raw_result_count ?? citations.length} retrieved records, deduplicated
        and ranked by credibility and relevance{result?.cache_hit ? " · cached" : ""}.
      </p>
      <ul className="mt-1.5 space-y-1.5">
        {citations.slice(0, 8).map((citation) => {
          const href = citation.doi
            ? `https://doi.org/${citation.doi}`
            : citation.pmid
              ? `https://pubmed.ncbi.nlm.nih.gov/${citation.pmid}/`
              : null;
          return (
            <li key={citation.doi || citation.pmid || citation.title} className="text-[11.5px]">
              <span className="text-[var(--text-primary)]">
                {href ? (
                  <a href={href} target="_blank" rel="noreferrer" className="underline underline-offset-2">
                    {citation.title}
                  </a>
                ) : (
                  citation.title
                )}
              </span>
              <span className="text-[var(--text-muted)]">
                {" "}
                {citation.journal ? `${citation.journal}, ` : ""}
                {citation.year ?? "year not recorded"}
                {citation.stance ? ` · ${STANCE_LABEL[citation.stance] ?? citation.stance}` : ""}
              </span>
            </li>
          );
        })}
      </ul>
      {result?.interpretation_note && (
        <p className="mt-2 text-[10.5px] text-[var(--text-muted)]">{result.interpretation_note}</p>
      )}
    </div>
  );
}
