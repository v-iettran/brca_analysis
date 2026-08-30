"use client";

import { PanelCard } from "@/components/PanelCard";

const GATE = 0.6;

/**
 * A lookup table, not three sparklines. The reader's task is comparing values
 * across k, which is a lookup, and the k markers on three separate charts were
 * unreadable. Spec v3.1 §1.1.
 */
export function ModelSelectionPanel({
  rows,
  k,
  preregisteredK,
  showReference,
  takeaway,
}: {
  rows: Array<{ k: number; bic: number; silhouette: number; stability: number }>;
  k: number;
  preregisteredK?: number | null;
  showReference: boolean;
  takeaway?: string;
}) {
  const minBic = Math.min(...rows.map((r) => r.bic));
  const inWindow = rows.filter((r) => r.bic <= minBic + 10);
  const bestStability = rows.reduce((a, b) => (b.stability > a.stability ? b : a), rows[0]);

  return (
    <PanelCard
      id="structure"
      eyebrow="Model selection"
      title="Structure, not survival"
      takeaway={takeaway}
      display={k}
      displayCaption="subgroups shown"
      bare
      footnote={`Selected: highest stability among k within 10 BIC of the minimum. BIC magnitude is not interpretable on its own — it carries a penalty of roughly p·ln(n), so only differences across k mean anything. None of these three criteria touches outcome data. Source: TCGA-BRCA intrinsic expression.`}
    >
      {!showReference && (
        <p className="mb-2 text-[11px] text-[var(--warning)]">
          KMeans is exploratory. The BIC window and the stability gate describe the GMM path only.
        </p>
      )}

      <table className="w-full text-[12px]">
        <caption className="sr-only">Model selection criteria by number of subgroups</caption>
        <thead>
          <tr className="text-[var(--text-muted)]">
            <th scope="col" className="pb-1.5 text-left font-medium">k</th>
            <th scope="col" className="pb-1.5 text-right font-medium">BIC ↓</th>
            <th scope="col" className="pb-1.5 text-right font-medium">Silh. ↑</th>
            <th scope="col" className="pb-1.5 pl-3 text-left font-medium">Stability ↑</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const viewing = row.k === k;
            const preg = row.k === preregisteredK;
            const withinWindow = row.bic <= minBic + 10;
            const bar = Math.max(0, Math.min(1, row.stability));
            return (
              <tr
                key={row.k}
                className="border-t border-[var(--line)] transition-colors duration-200"
                style={{ background: viewing ? "var(--surface-raised)" : undefined }}
              >
                <td className="py-1.5 font-mono tabular-nums">
                  <span className="inline-flex items-center gap-1">
                    <span
                      className="w-2 text-[var(--text-primary)]"
                      style={{ opacity: viewing ? 1 : 0 }}
                      aria-hidden
                    >
                      ▸
                    </span>
                    <span style={{ color: viewing ? "var(--text-primary)" : "var(--text-secondary)" }}>
                      {row.k}
                    </span>
                    {preg && (
                      <span
                        className="rounded-sm border border-[var(--line-strong)] px-1 text-[9px] font-medium text-[var(--text-muted)]"
                        title="pre-registered"
                      >
                        PR
                      </span>
                    )}
                  </span>
                </td>
                <td
                  className="text-right font-mono tabular-nums"
                  style={{ color: withinWindow ? "var(--text-primary)" : "var(--text-muted)" }}
                  title={withinWindow ? "within 10 BIC of the minimum" : undefined}
                >
                  {row.bic.toFixed(0)}
                </td>
                <td className="text-right font-mono tabular-nums text-[var(--text-secondary)]">
                  {row.silhouette.toFixed(2)}
                </td>
                <td className="py-1.5 pl-3">
                  <span className="flex items-center gap-2">
                    <span className="w-8 shrink-0 font-mono tabular-nums text-[var(--text-secondary)]">
                      {row.stability.toFixed(2)}
                    </span>
                    <span className="relative h-1.5 min-w-0 flex-1 overflow-hidden rounded-full bg-[var(--line)]">
                      <span
                        className="absolute inset-y-0 left-0 rounded-full transition-[width] duration-300 ease-out"
                        style={{
                          width: `${bar * 100}%`,
                          background: row.stability >= GATE ? "var(--text-secondary)" : "var(--text-muted)",
                        }}
                      />
                      {showReference && (
                        <span
                          className="absolute inset-y-0 w-px bg-[var(--text-primary)]"
                          style={{ left: `${GATE * 100}%` }}
                          title="0.60 stability gate"
                        />
                      )}
                    </span>
                  </span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      <div className="mt-2.5 space-y-1 text-[10.5px] text-[var(--text-muted)]">
        <p>
          Emphasised BIC values fall inside the 10-point window above the minimum ({minBic.toFixed(0)}). The
          tick on each bar is the 0.60 stability gate.
        </p>
        {/* Worth stating plainly: with one candidate in the window the stability
            criterion never breaks a tie, so the rule reduces to the BIC minimum. */}
        <p>
          <span className="font-medium text-[var(--text-secondary)]">
            {inWindow.length} candidate{inWindow.length === 1 ? "" : "s"} in the window
          </span>
          {inWindow.length === 1 ? (
            <>
              {" "}
              (k = {inWindow[0].k}), so stability broke no tie here and the rule reduced to the BIC minimum.
              {bestStability.k !== inWindow[0].k && (
                <>
                  {" "}
                  k = {bestStability.k} is more stable ({bestStability.stability.toFixed(2)} vs{" "}
                  {inWindow[0].stability.toFixed(2)}) but sits{" "}
                  {(bestStability.bic - minBic).toFixed(0)} BIC away, far outside the window.
                </>
              )}
            </>
          ) : (
            <> — stability chose between them.</>
          )}
        </p>
      </div>
    </PanelCard>
  );
}
