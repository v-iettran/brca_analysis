"use client";

import type { ReactNode } from "react";
import { motion, useReducedMotion } from "motion/react";

/**
 * Panel anatomy for the console.
 *
 * The chart sits in a recessed well so a plot reads as an instrument readout
 * rather than an illustration on a card. The readout numeral gives each panel
 * one focal value, which is what makes the page scannable at a glance.
 */
export function PanelCard({
  id,
  eyebrow,
  title,
  takeaway,
  display,
  displayCaption,
  footnote,
  actions,
  bare,
  className,
  scrollBody,
  children,
}: {
  id?: string;
  eyebrow: string;
  title: string;
  takeaway?: string;
  display?: ReactNode;
  displayCaption?: string;
  footnote?: string;
  actions?: ReactNode;
  /** Render children directly instead of inside the recessed well. */
  bare?: boolean;
  className?: string;
  /** Scroll the body only, keeping the header and footnote in place. */
  scrollBody?: boolean;
  children: ReactNode;
}) {
  const reduce = useReducedMotion();

  return (
    <motion.section
      id={id}
      className={`panel flex min-w-0 flex-col scroll-mt-28 p-5 ${className ?? ""}`}
      initial={reduce ? false : { opacity: 0, y: 12 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, amount: 0.15 }}
      transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
    >
      <header className="flex shrink-0 items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="eyebrow">{eyebrow}</p>
          <h2 className="mt-1.5 text-[15px] font-semibold text-[var(--text-primary)]">{title}</h2>
        </div>
        <div className="flex shrink-0 items-center gap-2">{actions}</div>
      </header>

      {display != null && (
        <p className="readout mt-4 flex items-baseline gap-2 text-[var(--text-primary)]">
          {display}
          {displayCaption && (
            <span className="font-sans text-[11px] font-medium tracking-wide text-[var(--text-muted)]">
              {displayCaption}
            </span>
          )}
        </p>
      )}

      {takeaway && <p className="takeaway mt-3">{takeaway}</p>}

      <div
        className={`${bare ? "mt-4 min-w-0 flex-1" : "well mt-4 min-w-0 flex-1 p-3"}${
          scrollBody ? " min-h-0 overflow-y-auto" : ""
        }`}
      >
        {children}
      </div>

      {footnote && (
        <p className="mt-3 shrink-0 text-[11px] leading-relaxed text-[var(--text-muted)]">{footnote}</p>
      )}
    </motion.section>
  );
}
