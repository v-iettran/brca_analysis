"use client";

import { useState } from "react";
import { STANCE_META, STANCE_ORDER, STANCE_CAVEAT, type Stance } from "./StanceGlossary";

/**
 * The stance key, which doubles as the filter.
 *
 * Colour never carries the label alone: each chip is glyph + word + count. The
 * validated stance palette separates at ΔE 7.4 under deuteranopia, inside the
 * 6–8 band that is only legal with exactly this kind of secondary encoding.
 *
 * Hovering (or focusing) a chip explains how that label is decided, quoting the
 * phrase list the server actually matches on.
 */
export function StanceLegend({
  counts,
  active,
  onToggle,
}: {
  counts: Record<Stance, number>;
  active: Set<Stance>;
  onToggle: (stance: Stance) => void;
}) {
  const [hovered, setHovered] = useState<Stance | null>(null);
  const filtering = active.size > 0;

  return (
    <div className="relative">
      <div className="flex flex-wrap items-center gap-1">
        <span className="mr-0.5 text-[10px] uppercase tracking-[0.08em] text-[var(--text-muted)]">
          Stance
        </span>
        {STANCE_ORDER.map((stance) => {
          const meta = STANCE_META[stance];
          const count = counts[stance] ?? 0;
          const on = active.has(stance);
          const dimmed = filtering && !on;
          return (
            <button
              key={stance}
              type="button"
              disabled={count === 0}
              aria-pressed={on}
              aria-label={`${meta.label}: ${count} source${count === 1 ? "" : "s"}. ${meta.rule}`}
              onClick={() => onToggle(stance)}
              onMouseEnter={() => setHovered(stance)}
              onMouseLeave={() => setHovered((s) => (s === stance ? null : s))}
              onFocus={() => setHovered(stance)}
              onBlur={() => setHovered((s) => (s === stance ? null : s))}
              className="inline-flex items-center gap-1 rounded-full border px-1.5 py-[3px] text-[10.5px] transition-colors disabled:cursor-not-allowed disabled:opacity-40"
              style={{
                borderColor: on
                  ? meta.colorVar
                  : "color-mix(in oklab, var(--line-strong) 70%, transparent)",
                background: on ? `color-mix(in oklab, ${meta.colorVar} 12%, transparent)` : "transparent",
                opacity: dimmed ? 0.45 : 1,
              }}
            >
              <span aria-hidden style={{ color: meta.colorVar }}>
                {meta.glyph}
              </span>
              <span className="text-[var(--text-secondary)]">{meta.label}</span>
              <span className="font-mono text-[9.5px] text-[var(--text-muted)]">{count}</span>
            </button>
          );
        })}
        {filtering && (
          <button
            type="button"
            onClick={() => STANCE_ORDER.filter((s) => active.has(s)).forEach(onToggle)}
            className="ml-0.5 rounded-full px-1.5 py-[3px] text-[10px] text-[var(--text-muted)] underline underline-offset-2 transition-colors hover:text-[var(--text-primary)]"
          >
            clear
          </button>
        )}
      </div>

      {hovered && (
        <div
          role="tooltip"
          className="absolute left-0 top-full z-30 mt-1.5 w-[19rem] rounded-[var(--radius-inner)] border border-[var(--line-strong)] bg-[var(--surface)] p-2.5 shadow-[var(--shadow-panel)]"
        >
          <p className="flex items-center gap-1.5 text-[11.5px] font-semibold text-[var(--text-primary)]">
            <span aria-hidden style={{ color: STANCE_META[hovered].colorVar }}>
              {STANCE_META[hovered].glyph}
            </span>
            {STANCE_META[hovered].label}
          </p>
          <p className="mt-1 text-[11px] leading-snug text-[var(--text-secondary)]">
            {STANCE_META[hovered].rule}
          </p>
          {STANCE_META[hovered].phrases && (
            <>
              <p className="mt-1.5 text-[9.5px] uppercase tracking-[0.08em] text-[var(--text-muted)]">
                Phrases matched
              </p>
              <ul className="mt-0.5 space-y-[1px]">
                {STANCE_META[hovered].phrases!.map((phrase) => (
                  <li key={phrase} className="font-mono text-[10px] text-[var(--text-secondary)]">
                    {phrase}
                  </li>
                ))}
              </ul>
            </>
          )}
          <p className="mt-2 border-t border-[var(--line)] pt-1.5 text-[10px] leading-snug text-[var(--text-muted)]">
            {STANCE_CAVEAT}
          </p>
        </div>
      )}
    </div>
  );
}
