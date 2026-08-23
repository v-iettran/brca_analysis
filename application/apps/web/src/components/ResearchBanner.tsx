export function ResearchBanner() {
  return (
    <div className="w-full border-b border-amber-200 bg-amber-50 px-4 py-2 text-center text-xs font-medium text-amber-900">
      <span className="mr-2 rounded-full bg-amber-200/70 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider">
        Research prototype
      </span>
      Not a clinical decision-support device. Hosted demos use synthetic patients only; RNA is not
      uploaded or stored. Results are exploratory evidence summaries and require independent clinical
      review.
    </div>
  );
}
