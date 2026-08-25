"use client";

const STEPS = [
  { id: "quality", label: "Quality" },
  { id: "structure", label: "Structure" },
  { id: "projection", label: "Position" },
  { id: "survival", label: "Survival" },
  { id: "characteristics", label: "Meaning" },
  { id: "retrieval", label: "Retrieval" },
] as const;

export function ProgressRail({ current }: { current?: string }) {
  return (
    <nav aria-label="Analysis steps" className="sticky top-20 hidden w-36 shrink-0 lg:block">
      <ol className="space-y-1 border-l border-[var(--border)] pl-3">
        {STEPS.map((step, i) => {
          const active = current === step.id;
          return (
            <li key={step.id}>
              <a
                href={`#${step.id}`}
                className={`block py-1 text-xs ${active ? "font-semibold text-[var(--clinical-900)]" : "text-[var(--text-muted)] hover:text-[var(--text-secondary)]"}`}
              >
                <span className="font-mono tabular-nums">{i + 1}</span> {step.label}
              </a>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
