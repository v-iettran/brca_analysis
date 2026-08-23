import type {
  ActiveView,
  AnalysisProgress,
  AnalysisResult,
  AnalysisSubmitAck,
  AuditEvent,
  ClusterDetail,
  CopilotChatMessage,
  CopilotChatResponse,
  GeneLiteratureResult,
  GroundedRationale,
  LiteratureResult,
  PatientMetadata,
  PublicHealth,
  RunTrialsResult,
  DemoPatientSummary,
  SyntheticPatientFull,
  SyntheticPatientSummary,
  TrialsResult,
} from "./types";

export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (init?.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    credentials: "include",
    headers,
    cache: "no-store",
  });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`API ${response.status} ${path}: ${body}`);
  }
  return response.json() as Promise<T>;
}

export function getPublicHealth(): Promise<PublicHealth> {
  return apiFetch("/health");
}

export function submitSyntheticAnalysis(syntheticId: string): Promise<AnalysisSubmitAck> {
  return apiFetch(`/analysis/synthetic/${encodeURIComponent(syntheticId)}`, { method: "POST" });
}

export function getRationale(runId: string, selectedDrug?: string | null): Promise<GroundedRationale> {
  const query = selectedDrug ? `?selected_drug=${encodeURIComponent(selectedDrug)}` : "";
  return apiFetch(`/analysis/${encodeURIComponent(runId)}/rationale${query}`);
}

export function listSyntheticPatients(): Promise<SyntheticPatientSummary[]> {
  return apiFetch("/patients/synthetic");
}

export function listDemoPatients(): Promise<DemoPatientSummary[]> {
  return apiFetch("/patients/demo");
}

export function submitDemoAnalysis(patientId: string): Promise<AnalysisSubmitAck> {
  return apiFetch(`/analysis/demo/${encodeURIComponent(patientId)}`, { method: "POST" });
}

export function getSyntheticPatient(id: string): Promise<SyntheticPatientFull> {
  return apiFetch(`/patients/synthetic/${encodeURIComponent(id)}`);
}

export function submitAnalysis(patient: {
  patient_label: string;
  expression: Record<string, number>;
  metadata: PatientMetadata;
  administered_regimen: string[];
  top_up?: number;
  top_down?: number;
}): Promise<AnalysisResult> {
  return apiFetch("/analysis", {
    method: "POST",
    body: JSON.stringify(patient),
  });
}

export function submitAnalysisAsync(patient: {
  patient_label: string;
  expression: Record<string, number>;
  metadata: PatientMetadata;
  administered_regimen: string[];
  top_up?: number;
  top_down?: number;
}): Promise<AnalysisSubmitAck> {
  return apiFetch("/analysis/async", {
    method: "POST",
    body: JSON.stringify(patient),
  });
}

export function getAnalysisProgress(runId: string): Promise<AnalysisProgress> {
  return apiFetch(`/analysis/${encodeURIComponent(runId)}/progress`);
}

export function getAnalysis(runId: string): Promise<AnalysisResult> {
  return apiFetch(`/analysis/${encodeURIComponent(runId)}`);
}

export function recalculateAnalysis(
  runId: string,
  topUp: number,
  topDown: number
): Promise<AnalysisResult> {
  return apiFetch(`/analysis/${encodeURIComponent(runId)}/recalculate`, {
    method: "POST",
    body: JSON.stringify({ top_up: topUp, top_down: topDown }),
  });
}

export function getAnalysisAudit(runId: string): Promise<AuditEvent[]> {
  return apiFetch(`/analysis/${encodeURIComponent(runId)}/audit`);
}

export function getClusterDetail(runId: string, clusterId: number): Promise<ClusterDetail> {
  return apiFetch(`/analysis/${encodeURIComponent(runId)}/clusters/${clusterId}`);
}

export function getGeneLiterature(
  runId: string,
  clusterId: number,
  gene: string
): Promise<GeneLiteratureResult> {
  return apiFetch(
    `/analysis/${encodeURIComponent(runId)}/clusters/${clusterId}/genes/${encodeURIComponent(gene)}/literature`
  );
}

export function getDrugLiterature(runId: string, drug: string): Promise<LiteratureResult> {
  return apiFetch(`/analysis/${encodeURIComponent(runId)}/drugs/${encodeURIComponent(drug)}/literature`);
}

export function getDrugTrials(runId: string, drug: string): Promise<TrialsResult> {
  return apiFetch(`/analysis/${encodeURIComponent(runId)}/drugs/${encodeURIComponent(drug)}/trials`);
}

export function getRunTrials(runId: string): Promise<RunTrialsResult> {
  return apiFetch(`/analysis/${encodeURIComponent(runId)}/trials`);
}

export function getChatHistory(runId: string): Promise<{
  messages: Array<{ role: string; content: string; active_view?: string | null }>;
}> {
  return apiFetch(`/analysis/${encodeURIComponent(runId)}/chat`);
}

export function askCopilot(
  runId: string,
  message: string,
  history: CopilotChatMessage[],
  selectedDrug?: string | null,
  selectedCluster?: number | null,
  activeView?: ActiveView | null
): Promise<CopilotChatResponse> {
  return apiFetch(`/analysis/${encodeURIComponent(runId)}/chat`, {
    method: "POST",
    body: JSON.stringify({
      message,
      history,
      selected_drug: selectedDrug ?? null,
      selected_cluster: selectedCluster ?? null,
      active_view: activeView ?? null,
    }),
  });
}

export function exportUrl(runId: string, format: "json" | "csv" | "pdf"): string {
  return `${API_BASE_URL}/analysis/${encodeURIComponent(runId)}/export/${format}`;
}

/** Browser-side CSV/TSV parser for gene,expression uploads. */
export function parseExpressionFile(text: string): Record<string, number> {
  const lines = text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
  if (lines.length === 0) throw new Error("Expression file is empty.");
  const delim = lines[0].includes("\t") ? "\t" : ",";
  const expression: Record<string, number> = {};
  let start = 0;
  const header = lines[0].toLowerCase();
  if (header.includes("gene") && (header.includes("expression") || header.includes("value"))) {
    start = 1;
  }
  for (let i = start; i < lines.length; i += 1) {
    const parts = lines[i].split(delim).map((p) => p.trim().replace(/^"|"$/g, ""));
    if (parts.length < 2) continue;
    const gene = parts[0];
    const value = Number(parts[1]);
    if (!gene || !Number.isFinite(value)) continue;
    expression[gene] = value;
  }
  if (Object.keys(expression).length < 10) {
    throw new Error("Parsed fewer than 10 genes. Expected CSV/TSV with gene,expression columns.");
  }
  return expression;
}
