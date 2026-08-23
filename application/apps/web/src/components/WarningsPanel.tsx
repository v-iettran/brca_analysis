import type { WarningOut } from "@/lib/types";

const SEVERITY_STYLE: Record<string, string> = {
  info: "border-slate-300 bg-slate-50 text-slate-700",
  caution: "border-amber-300 bg-amber-50 text-amber-900",
  abstain: "border-red-300 bg-red-50 text-red-900",
};

export function WarningsPanel({ warnings }: { warnings: WarningOut[] }) {
  if (warnings.length === 0) return null;
  return (
    <div className="space-y-2">
      {warnings.map((warning, idx) => (
        <div
          key={idx}
          className={`rounded-md border px-3 py-2 text-sm ${SEVERITY_STYLE[warning.severity] ?? SEVERITY_STYLE.info}`}
        >
          <span className="mr-2 rounded bg-white/60 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide">
            {warning.severity}
          </span>
          {warning.message}
        </div>
      ))}
    </div>
  );
}
