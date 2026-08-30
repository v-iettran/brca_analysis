"use client";

import { useState } from "react";
import { ChatTeardropDots, X } from "@phosphor-icons/react";
import { CopilotPanel } from "@/components/CopilotPanel";
import type { ActiveView } from "@/lib/types";

/**
 * The copilot as a dock rather than a column.
 *
 * As a permanent right-hand column it took a third of the width from the panels
 * that carry the analysis, for a tool that is only wanted intermittently. It now
 * collapses to a single control and opens over the page when asked for.
 */
export function CopilotDock({
  runId,
  selectedDrug,
  selectedCluster,
  activeView,
}: {
  runId: string;
  selectedDrug: string | null;
  selectedCluster: number | null;
  activeView: ActiveView;
}) {
  const [open, setOpen] = useState(false);

  return (
    <>
      <div className="fixed bottom-5 right-5 z-40 print:hidden">
        {!open && (
          <button
            type="button"
            onClick={() => setOpen(true)}
            aria-label="Open the research copilot"
            className="flex items-center gap-2 rounded-full border border-[var(--line-strong)] bg-[var(--surface)] py-2.5 pl-3 pr-4 text-[13px] font-medium text-[var(--text-secondary)] shadow-lg transition-colors hover:text-[var(--text-primary)]"
          >
            <ChatTeardropDots size={18} weight="duotone" aria-hidden />
            Research copilot
          </button>
        )}
      </div>

      {open && (
        <div
          className="fixed bottom-5 right-5 z-40 flex max-h-[min(78vh,720px)] w-[min(26rem,calc(100vw-2.5rem))] flex-col overflow-hidden rounded-[var(--radius-panel)] border border-[var(--line-strong)] bg-[var(--surface)] shadow-2xl print:hidden"
          role="complementary"
          aria-label="Research copilot"
        >
          <div className="flex shrink-0 items-center justify-between gap-2 border-b border-[var(--line)] px-3 py-2">
            <span className="inline-flex items-center gap-2 text-[12px] font-semibold text-[var(--text-primary)]">
              <ChatTeardropDots size={16} weight="duotone" aria-hidden />
              Research copilot
            </span>
            <button
              type="button"
              onClick={() => setOpen(false)}
              aria-label="Close the research copilot"
              className="pressable flex h-6 w-6 items-center justify-center text-[var(--text-muted)]"
            >
              <X size={14} aria-hidden />
            </button>
          </div>
          <div className="flex min-h-0 flex-1 flex-col p-3">
            <CopilotPanel
              runId={runId}
              selectedDrug={selectedDrug}
              selectedCluster={selectedCluster}
              activeView={activeView}
            />
          </div>
        </div>
      )}
    </>
  );
}
