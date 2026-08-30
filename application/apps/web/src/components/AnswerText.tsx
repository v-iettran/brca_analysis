"use client";

import { Fragment, type ReactNode } from "react";

/**
 * Render a model answer as typed elements.
 *
 * Local models emit markdown whatever the prompt says, so the answer arrives
 * carrying `###`, `**` and `-` markers. Those were being printed literally.
 *
 * This parses the small subset they actually use and returns React elements —
 * never `dangerouslySetInnerHTML`. Model output is untrusted input, and a
 * markdown library that passes raw HTML through would turn a hallucination into
 * an injection. Anything unrecognised degrades to plain text.
 */

type Block =
  | { kind: "heading"; text: string }
  | { kind: "paragraph"; text: string }
  | { kind: "list"; items: string[]; ordered: boolean };

const HEADING = /^\s{0,3}#{1,6}\s+(.*)$/;
const BULLET = /^\s*[-*•]\s+(.*)$/;
const NUMBERED = /^\s*\d+[.)]\s+(.*)$/;

function parse(text: string): Block[] {
  const blocks: Block[] = [];
  let paragraph: string[] = [];
  let list: string[] = [];
  let ordered = false;

  const flushParagraph = () => {
    if (paragraph.length) {
      blocks.push({ kind: "paragraph", text: paragraph.join(" ").trim() });
      paragraph = [];
    }
  };
  const flushList = () => {
    if (list.length) {
      blocks.push({ kind: "list", items: list, ordered });
      list = [];
    }
  };

  for (const raw of (text || "").split("\n")) {
    const line = raw.replace(/\s+$/, "");
    if (!line.trim()) {
      flushParagraph();
      flushList();
      continue;
    }
    const heading = line.match(HEADING);
    if (heading) {
      flushParagraph();
      flushList();
      blocks.push({ kind: "heading", text: heading[1].replace(/[*_`]/g, "").trim() });
      continue;
    }
    const bullet = line.match(BULLET);
    const numbered = line.match(NUMBERED);
    if (bullet || numbered) {
      flushParagraph();
      const isOrdered = Boolean(numbered);
      if (list.length && isOrdered !== ordered) flushList();
      ordered = isOrdered;
      list.push((bullet ?? numbered)![1]);
      continue;
    }
    flushList();
    paragraph.push(line.trim());
  }
  flushParagraph();
  flushList();
  return blocks;
}

/** Inline emphasis and code, as elements rather than markers. */
function inline(text: string, keyPrefix: string): ReactNode[] {
  const out: ReactNode[] = [];
  const pattern = /(\*\*[^*]+\*\*|__[^_]+__|`[^`]+`|\*[^*\n]+\*)/g;
  let last = 0;
  let match: RegExpExecArray | null;
  let index = 0;

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > last) out.push(text.slice(last, match.index));
    const token = match[0];
    const key = `${keyPrefix}-${index++}`;
    if (token.startsWith("**") || token.startsWith("__")) {
      out.push(
        <strong key={key} className="font-semibold text-[var(--text-primary)]">
          {token.slice(2, -2)}
        </strong>
      );
    } else if (token.startsWith("`")) {
      out.push(
        <code key={key} className="font-mono text-[11.5px] text-[var(--text-primary)]">
          {token.slice(1, -1)}
        </code>
      );
    } else {
      out.push(
        <em key={key} className="italic">
          {token.slice(1, -1)}
        </em>
      );
    }
    last = match.index + token.length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

export function AnswerText({ text }: { text: string }) {
  const blocks = parse(text);
  return (
    <div className="space-y-2 text-[12.5px] leading-relaxed text-[var(--text-primary)]">
      {blocks.map((block, i) => {
        if (block.kind === "heading") {
          return (
            <p key={i} className="eyebrow pt-1">
              {block.text}
            </p>
          );
        }
        if (block.kind === "list") {
          const List = block.ordered ? "ol" : "ul";
          return (
            <List key={i} className="space-y-1 pl-4">
              {block.items.map((item, j) => (
                <li key={j} className={block.ordered ? "list-decimal" : "list-disc"}>
                  <Fragment>{inline(item, `${i}-${j}`)}</Fragment>
                </li>
              ))}
            </List>
          );
        }
        return (
          <p key={i}>
            <Fragment>{inline(block.text, String(i))}</Fragment>
          </p>
        );
      })}
    </div>
  );
}
