import type { ReactNode } from "react";

export function PanelCard({
  id,
  eyebrow,
  title,
  takeaway,
  display,
  displayCaption,
  footnote,
  actions,
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
  children: ReactNode;
}) {
  return (
    <section id={id} className="panel-card scroll-mt-24">
      <header className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="eyebrow">{eyebrow}</p>
          <h2 className="mt-1 text-base font-semibold text-[var(--text-primary)]">{title}</h2>
          {takeaway && <p className="takeaway mt-1">{takeaway}</p>}
        </div>
        <div className="flex shrink-0 items-center gap-2">{actions}</div>
      </header>
      {display != null && (
        <p className="display-numeral mt-4 text-[var(--text-primary)]">
          {display}
          {displayCaption && (
            <span className="ml-2 align-middle text-sm font-medium text-[var(--text-muted)]">{displayCaption}</span>
          )}
        </p>
      )}
      <div className="chart-well mt-4">{children}</div>
      {footnote && <p className="mt-3 text-xs text-[var(--text-muted)]">{footnote}</p>}
    </section>
  );
}
