export function ResearchBanner() {
  return (
    <div className="w-full border-b border-[var(--line)] bg-[var(--shell)] px-4 py-1.5 text-center text-[11px] text-[var(--text-muted)]">
      <span className="mr-2 rounded-md border border-[color-mix(in_oklab,var(--warning)_45%,transparent)] px-1.5 py-0.5 text-[9.5px] font-semibold uppercase tracking-[0.1em] text-[var(--warning)]">
        Research prototype
      </span>
      Not a clinical decision-support device. Results are exploratory evidence summaries and require independent
      clinical review.
    </div>
  );
}
