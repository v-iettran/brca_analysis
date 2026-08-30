import type { ReactNode } from "react";

/** Shared SVG axis primitives. Every chart labels both axes with units. */

export function ChartAxes({
  width,
  height,
  pad = { l: 48, r: 16, t: 12, b: 36 },
  xLabel,
  yLabel,
  xTicks,
  yTicks,
  children,
}: {
  width: number;
  height: number;
  pad?: { l: number; r: number; t: number; b: number };
  xLabel: string;
  yLabel: string;
  xTicks: Array<{ v: number; x: number; label: string }>;
  yTicks: Array<{ v: number; y: number; label: string }>;
  children: ReactNode;
}) {
  const innerW = width - pad.l - pad.r;
  const innerH = height - pad.t - pad.b;
  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="w-full" role="img">
      <text
        x={pad.l + innerW / 2}
        y={height - 4}
        textAnchor="middle"
        fill="var(--text-secondary)"
        fontSize="11"
      >
        {xLabel}
      </text>
      <text
        x={12}
        y={pad.t + innerH / 2}
        textAnchor="middle"
        transform={`rotate(-90 12 ${pad.t + innerH / 2})`}
        fill="var(--text-secondary)"
        fontSize="11"
      >
        {yLabel}
      </text>
      {yTicks.map((t) => (
        <g key={`y-${t.v}`}>
          <line x1={pad.l} x2={pad.l + innerW} y1={t.y} y2={t.y} stroke="var(--line)" strokeWidth="1" />
          <text
            x={pad.l - 6}
            y={t.y + 3}
            textAnchor="end"
            fill="var(--text-muted)"
            className="font-mono"
            fontSize="10.5"
          >
            {t.label}
          </text>
        </g>
      ))}
      {xTicks.map((t) => (
        <g key={`x-${t.v}`}>
          <line x1={t.x} x2={t.x} y1={pad.t + innerH} y2={pad.t + innerH + 4} stroke="var(--line-strong)" />
          <text
            x={t.x}
            y={pad.t + innerH + 16}
            textAnchor="middle"
            fill="var(--text-muted)"
            className="font-mono"
            fontSize="10.5"
          >
            {t.label}
          </text>
        </g>
      ))}
      <line x1={pad.l} x2={pad.l} y1={pad.t} y2={pad.t + innerH} stroke="var(--line-strong)" />
      <line x1={pad.l} x2={pad.l + innerW} y1={pad.t + innerH} y2={pad.t + innerH} stroke="var(--line-strong)" />
      {children}
    </svg>
  );
}

export function chartPad(width: number, height: number, pad = { l: 48, r: 16, t: 12, b: 36 }) {
  return {
    pad,
    innerW: width - pad.l - pad.r,
    innerH: height - pad.t - pad.b,
    x: (t: number) => pad.l + t * (width - pad.l - pad.r),
    y: (t: number) => pad.t + (1 - t) * (height - pad.t - pad.b),
  };
}
