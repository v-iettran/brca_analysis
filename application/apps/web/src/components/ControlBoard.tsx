"use client";

export function ControlBoard({
  k,
  preregisteredK,
  method,
  covariance,
  projection,
  clusteringAvailable,
  exploratory,
  onChange,
  onReset,
}: {
  k: number;
  preregisteredK: number | null;
  method: "gmm" | "kmeans";
  covariance: "full" | "diag" | "tied";
  projection: "umap" | "pca";
  clusteringAvailable: boolean;
  exploratory: boolean;
  onChange: (next: { k?: number; method?: "gmm" | "kmeans"; covariance?: "full" | "diag" | "tied"; projection?: "umap" | "pca" }) => void;
  onReset: () => void;
}) {
  return (
    <section className="flex h-full flex-col rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-4">
      <header className="flex items-center justify-between gap-2">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-400">Control board</p>
          <h2 className="mt-1 text-base font-semibold">Clustering configuration</h2>
        </div>
        {exploratory && (
          <span data-testid="exploratory-badge" className="rounded-full bg-amber-100 px-2 py-0.5 font-mono text-[11px] font-semibold text-amber-800">
            exploratory
          </span>
        )}
      </header>
      {!clusteringAvailable && (
        <p className="mt-3 text-sm text-slate-600">No stable discrete structure. The latent is shown without cluster colours.</p>
      )}
      <label className="mt-4 text-xs font-medium text-slate-500">
        k
        <input
          type="range"
          min={2}
          max={8}
          value={k}
          disabled={!clusteringAvailable}
          onChange={(e) => onChange({ k: Number(e.target.value) })}
          className="mt-1 w-full accent-teal-700"
          aria-label="Number of subgroups"
        />
        <span className="mt-1 flex justify-between font-mono text-[11px] text-slate-400">
          {Array.from({ length: 7 }, (_, i) => i + 2).map((value) => (
            <span key={value} className={value === preregisteredK ? "text-teal-700" : ""}>
              {value}
              {value === preregisteredK ? " ▍" : ""}
            </span>
          ))}
        </span>
      </label>
      <fieldset className="mt-3 text-xs">
        <legend className="font-medium text-slate-500">Method (soft k-means = GMM)</legend>
        <div className="mt-1 flex gap-3">
          {(["gmm", "kmeans"] as const).map((m) => (
            <label key={m} className="flex items-center gap-1">
              <input type="radio" name="method" checked={method === m} onChange={() => onChange({ method: m })} disabled={!clusteringAvailable} />
              {m === "gmm" ? "GMM" : "KMeans"}
            </label>
          ))}
        </div>
      </fieldset>
      <fieldset className="mt-3 text-xs" disabled={method !== "gmm" || !clusteringAvailable}>
        <legend className="font-medium text-slate-500">Covariance</legend>
        <div className="mt-1 flex gap-3">
          {(["full", "diag", "tied"] as const).map((c) => (
            <label key={c} className="flex items-center gap-1">
              <input type="radio" name="cov" checked={covariance === c} onChange={() => onChange({ covariance: c })} />
              {c}
            </label>
          ))}
        </div>
      </fieldset>
      <fieldset className="mt-3 text-xs">
        <legend className="font-medium text-slate-500">Projection</legend>
        <div className="mt-1 flex gap-3">
          {(["umap", "pca"] as const).map((p) => (
            <label key={p} className="flex items-center gap-1">
              <input type="radio" name="proj" checked={projection === p} onChange={() => onChange({ projection: p })} />
              {p.toUpperCase()}
            </label>
          ))}
        </div>
      </fieldset>
      <button type="button" onClick={onReset} className="mt-auto rounded-lg border border-teal-700 px-3 py-1.5 text-xs font-semibold text-teal-800">
        Reset to pre-registered
      </button>
    </section>
  );
}
