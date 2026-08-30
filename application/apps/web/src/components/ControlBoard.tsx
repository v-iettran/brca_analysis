"use client";

import { motion, useReducedMotion } from "motion/react";

type Method = "gmm" | "kmeans";
type Covariance = "full" | "diag" | "tied";
type Projection = "umap" | "pca";

const K_RANGE = [2, 3, 4, 5, 6, 7, 8];

/**
 * The dock. Every other panel is downstream of this state, so it stays on
 * screen rather than scrolling away as a panel among panels.
 */
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
  method: Method;
  covariance: Covariance;
  projection: Projection;
  clusteringAvailable: boolean;
  exploratory: boolean;
  onChange: (next: { k?: number; method?: Method; covariance?: Covariance; projection?: Projection }) => void;
  onReset: () => void;
}) {
  const reduce = useReducedMotion();
  const pct = ((k - 2) / 6) * 100;

  return (
    <section className="panel p-4" aria-label="Control board">
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
        <div className="flex items-baseline gap-2.5">
          <p className="eyebrow">Control board</p>
          <span className="text-[11px] text-[var(--text-muted)]">clustering configuration</span>
        </div>
        <div className="flex items-center gap-2">
          {exploratory && (
            <span data-testid="exploratory-badge" className="exploratory-chip">
              exploratory
            </span>
          )}
          <button
            type="button"
            onClick={onReset}
            disabled={!exploratory}
            className="rounded-md border border-[var(--line-strong)] px-2.5 py-1 text-[11px] font-medium text-[var(--text-secondary)] transition-colors duration-150 hover:text-[var(--text-primary)] disabled:opacity-35"
          >
            Reset to pre-registered
          </button>
        </div>
      </div>

      {!clusteringAvailable && (
        <p className="mt-3 text-[13px] text-[var(--text-secondary)]">
          No stable discrete structure. The latent is shown without cluster colours.
        </p>
      )}

      {/* k — the primary affordance, given the space to say so. */}
      <div className="mt-4">
        <div className="flex items-baseline justify-between">
          <label htmlFor="k-slider" className="text-[11px] font-medium text-[var(--text-secondary)]">
            Subgroups
          </label>
          <span className="font-mono text-[11px] text-[var(--text-muted)]">
            pre-registered k = {preregisteredK ?? "n/a"}
          </span>
        </div>

        <div className="mt-2 flex items-center gap-3">
          <motion.span
            key={k}
            initial={reduce ? false : { opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.2 }}
            className="w-10 shrink-0 font-mono text-2xl font-semibold leading-none tabular-nums"
          >
            {k}
          </motion.span>

          <div className="relative min-w-0 flex-1">
            <input
              id="k-slider"
              type="range"
              min={2}
              max={8}
              step={1}
              value={k}
              disabled={!clusteringAvailable}
              onChange={(e) => onChange({ k: Number(e.target.value) })}
              className="w-full"
              aria-label="Number of subgroups"
              aria-valuetext={`${k} subgroups`}
            />
            {/* Filled portion of the track, drawn under the native thumb. */}
            <span
              aria-hidden
              className="pointer-events-none absolute left-0 top-1/2 h-[3px] -translate-y-1/2 rounded-full bg-[var(--text-secondary)] transition-[width] duration-200 ease-out"
              style={{ width: `${pct}%` }}
            />
            <div aria-hidden className="mt-1.5 flex justify-between">
              {K_RANGE.map((value) => {
                const isPreg = value === preregisteredK;
                const isCurrent = value === k;
                return (
                  <span key={value} className="flex w-3 flex-col items-center gap-0.5">
                    <span
                      className="h-1.5 w-px transition-colors duration-200"
                      style={{
                        background: isPreg
                          ? "var(--text-primary)"
                          : isCurrent
                            ? "var(--text-secondary)"
                            : "var(--line-strong)",
                      }}
                    />
                    <span
                      className="font-mono text-[10px] tabular-nums transition-colors duration-200"
                      style={{
                        color: isCurrent
                          ? "var(--text-primary)"
                          : isPreg
                            ? "var(--text-secondary)"
                            : "var(--text-muted)",
                      }}
                    >
                      {value}
                    </span>
                  </span>
                );
              })}
            </div>
          </div>
        </div>
      </div>

      <div className="mt-4 grid gap-3 sm:grid-cols-3">
        <Segment
          legend="Method"
          name="method"
          value={method}
          disabled={!clusteringAvailable}
          options={[
            { value: "gmm", label: "GMM" },
            { value: "kmeans", label: "KMeans" },
          ]}
          onSelect={(value) => onChange({ method: value as Method })}
        />
        <Segment
          legend="Covariance"
          name="cov"
          value={covariance}
          disabled={method !== "gmm" || !clusteringAvailable}
          options={[
            { value: "full", label: "full" },
            { value: "diag", label: "diag" },
            { value: "tied", label: "tied" },
          ]}
          onSelect={(value) => onChange({ covariance: value as Covariance })}
        />
        <Segment
          legend="Projection"
          name="proj"
          value={projection}
          options={[
            { value: "pca", label: "PCA" },
            { value: "umap", label: "UMAP" },
          ]}
          onSelect={(value) => onChange({ projection: value as Projection })}
        />
      </div>

      <p className="mt-3 text-[11px] text-[var(--text-muted)]">
        GMM is soft k-means: it keeps the membership probabilities that a hard assignment throws away.
        {projection === "umap" && " UMAP distances between clusters are not meaningful."}
      </p>
    </section>
  );
}

function Segment({
  legend,
  name,
  value,
  options,
  onSelect,
  disabled,
}: {
  legend: string;
  name: string;
  value: string;
  options: Array<{ value: string; label: string }>;
  onSelect: (value: string) => void;
  disabled?: boolean;
}) {
  return (
    <fieldset disabled={disabled} className="min-w-0 disabled:opacity-40">
      <legend className="text-[11px] font-medium text-[var(--text-secondary)]">{legend}</legend>
      <div className="seg mt-1.5 w-full">
        {options.map((option) => (
          <label key={option.value} data-active={value === option.value} className="flex-1 text-center">
            <input
              type="radio"
              name={name}
              className="sr-only"
              checked={value === option.value}
              onChange={() => onSelect(option.value)}
            />
            {option.label}
          </label>
        ))}
      </div>
    </fieldset>
  );
}
