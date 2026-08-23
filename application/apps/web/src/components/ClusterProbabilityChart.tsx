"use client";

import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { ClusterPrediction } from "@/lib/types";

const CONFIDENCE_COLOR: Record<string, string> = {
  high: "#1d4ed8",
  moderate: "#2563eb",
  low: "#93c5fd",
  abstain: "#cbd5e1",
};

export function ClusterProbabilityChart({ prediction }: { prediction: ClusterPrediction }) {
  const data = Object.entries(prediction.probabilities)
    .map(([cluster, probability]) => ({ cluster: `Cluster ${cluster}`, probability: probability * 100 }))
    .sort((a, b) => a.cluster.localeCompare(b.cluster));
  const color = CONFIDENCE_COLOR[prediction.confidence_level] ?? "#2563eb";

  return (
    <div>
      <div className="h-56">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="cluster" tick={{ fontSize: 12 }} />
            <YAxis tick={{ fontSize: 12 }} unit="%" domain={[0, 100]} />
            <Tooltip formatter={(value) => `${Number(Array.isArray(value) ? value[0] : value).toFixed(1)}%`} />
            <Bar dataKey="probability" fill={color} radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="mt-3 flex flex-wrap gap-x-6 gap-y-1 text-sm text-slate-600">
        <span>
          Top cluster: <strong>{prediction.top_cluster}</strong> ({(prediction.top_probability * 100).toFixed(0)}%)
        </span>
        <span>
          Confidence: <strong className="capitalize">{prediction.confidence_level}</strong>
        </span>
        <span>
          Gene coverage: <strong>{(prediction.gene_coverage * 100).toFixed(0)}%</strong> (
          {prediction.genes_found}/{prediction.genes_requested})
        </span>
        <span>
          Method: <strong>{prediction.method_used.replace("_", " ")}</strong>
        </span>
      </div>
    </div>
  );
}
