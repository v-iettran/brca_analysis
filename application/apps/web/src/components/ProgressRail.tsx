"use client";

/**
 * The spine. Each step names what the panel below establishes, so a scroll
 * reads as one argument rather than six unrelated widgets.
 */
const STEPS = [
  { id: "quality", label: "Quality", note: "Is the sample usable" },
  { id: "structure", label: "Structure", note: "How many subgroups" },
  { id: "projection", label: "Position", note: "This tumour in the cohort" },
  { id: "survival", label: "Survival", note: "Do they differ in outcome" },
  { id: "characteristics", label: "Meaning", note: "What defines each" },
  { id: "retrieval", label: "Retrieval", note: "What was measured" },
] as const;

export function ProgressRail({ current }: { current?: string }) {
  const activeIndex = STEPS.findIndex((s) => s.id === current);

  return (
    <nav aria-label="Analysis steps" className="sticky top-24 hidden h-fit w-44 shrink-0 lg:block">
      <ol className="relative">
        <span aria-hidden className="absolute bottom-1 left-[5px] top-1 w-px bg-[var(--line)]" />
        <span
          aria-hidden
          className="absolute left-[5px] top-1 w-px bg-[var(--text-secondary)] transition-[height] duration-500 ease-out"
          style={{ height: activeIndex < 0 ? 0 : `${(activeIndex / (STEPS.length - 1)) * 100}%` }}
        />
        {STEPS.map((stepItem, i) => {
          const active = current === stepItem.id;
          const passed = activeIndex >= 0 && i < activeIndex;
          return (
            <li key={stepItem.id} className="relative pb-5 pl-6 last:pb-0">
              <span
                aria-hidden
                className="absolute left-0 top-[5px] h-[11px] w-[11px] rounded-full border-2 transition-colors duration-300"
                style={{
                  borderColor: active || passed ? "var(--text-primary)" : "var(--line-strong)",
                  background: active ? "var(--text-primary)" : "var(--ground)",
                }}
              />
              <a href={`#${stepItem.id}`} className="block">
                <span
                  className="block text-[12px] font-medium transition-colors duration-200"
                  style={{ color: active ? "var(--text-primary)" : "var(--text-secondary)" }}
                >
                  {stepItem.label}
                </span>
                <span
                  className="mt-0.5 block text-[10.5px] leading-snug transition-opacity duration-200"
                  style={{ color: "var(--text-muted)", opacity: active ? 1 : 0.55 }}
                >
                  {stepItem.note}
                </span>
              </a>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
