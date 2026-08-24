"use client";

export function CellLineCard({
  name,
  pam50,
  similarity,
  mutations,
  fingerprint,
  selected,
  onSelect,
}: {
  name: string;
  pam50?: string | null;
  similarity: number;
  mutations?: string[];
  fingerprint: number[];
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className={`w-full rounded-xl border p-3 text-left transition ${selected ? "border-teal-700 bg-teal-50" : "border-[var(--border)] bg-[var(--surface)]"}`}
    >
      <div className="flex items-start justify-between gap-2">
        <p className="font-mono text-sm font-medium">{name}</p>
        {pam50 && <span className="rounded-full bg-violet-50 px-2 py-0.5 text-[10px] text-violet-800">{pam50}</span>}
      </div>
      <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-100">
        <div className="h-full bg-teal-700" style={{ width: `${Math.max(4, similarity * 100)}%` }} />
      </div>
      <div className="mt-2 flex h-3 gap-0.5" aria-hidden>
        {fingerprint.map((v, i) => (
          <span key={i} className="flex-1 rounded-sm bg-violet-400" style={{ opacity: 0.25 + v * 0.75 }} />
        ))}
      </div>
      {mutations && mutations.length > 0 && <p className="mt-2 text-[11px] text-slate-500">{mutations.join(", ")}</p>}
    </button>
  );
}
