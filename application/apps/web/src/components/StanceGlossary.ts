/**
 * How a stance label is produced.
 *
 * This is not a summary of what a paper concluded. The server runs two keyword
 * lists over the short excerpt Paperclip returned, and nothing else — the rules
 * are in `pipeline_core/dedup.py:rule_based_stance`. The phrase lists below are
 * copied from it verbatim, so the popup a reader sees is auditable against the
 * code rather than a paraphrase of it.
 *
 * Keeping the honest limitation visible matters more here than looking clever:
 * a trial whose safety section lists adverse events is labelled `conflicting`
 * even when its conclusion is positive.
 */

export type Stance = "supporting" | "conflicting" | "neutral" | "unclear";

export const STANCE_ORDER: Stance[] = ["supporting", "conflicting", "neutral", "unclear"];

export const SUPPORTING_PHRASES = [
  "effective",
  "improved survival / response / outcome",
  "significant benefit / improvement / response",
  "well-tolerated",
  "superior to",
];

export const CONFLICTING_PHRASES = [
  "no (significant) benefit / difference / improvement",
  "failed to show / demonstrate",
  "resistant / resistance",
  "adverse event(s)",
  "did not meet / improve",
  "inferior to",
];

type StanceMeta = {
  label: string;
  /** Shape as well as colour, so the four are distinguishable without hue. */
  glyph: string;
  colorVar: string;
  rule: string;
  phrases: string[] | null;
};

export const STANCE_META: Record<Stance, StanceMeta> = {
  supporting: {
    label: "Supports",
    glyph: "▲",
    colorVar: "var(--stance-support)",
    rule: "The excerpt used supporting language and none of the conflicting language.",
    phrases: SUPPORTING_PHRASES,
  },
  conflicting: {
    label: "Conflicts",
    glyph: "▼",
    colorVar: "var(--stance-conflict)",
    rule: "The excerpt used conflicting language and none of the supporting language.",
    phrases: CONFLICTING_PHRASES,
  },
  neutral: {
    label: "Neutral",
    glyph: "■",
    colorVar: "var(--stance-neutral)",
    rule: "Neither list matched. The excerpt describes the work without claiming for or against.",
    phrases: null,
  },
  unclear: {
    label: "Unclear",
    glyph: "◆",
    colorVar: "var(--stance-unclear)",
    rule:
      "Both lists matched, or there was no excerpt to read. Deliberately not resolved to a side — a guess here would be indistinguishable from a finding.",
    phrases: null,
  },
};

export const STANCE_CAVEAT =
  "These labels come from matching phrases in the retrieved excerpt, not from reading the paper. A study whose safety section lists adverse events is marked Conflicts even if its conclusion is positive. Treat them as a way to sort the list, never as evidence.";
