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

/**
 * Gateway statuses that mean "the server is not answering yet", as opposed to
 * "the server answered and said no". On Render's free tier both services sleep
 * after about 15 minutes idle, and the API takes roughly a minute to wake — long
 * enough that the proxy in front of it gives up and returns one of these.
 */
const WAKING_STATUS = new Set([502, 503, 504]);

/**
 * Backoff for a sleeping upstream, ~2 minutes in total.
 *
 * Sized against a measured ~42s cold start with room to spare. The previous ladder
 * totalled ~50s, which sat right on that boundary and so failed intermittently --
 * the symptom that started this. Proxy requests do trigger the wake, they just
 * return 502 without waiting for it, so persisting here does eventually succeed.
 */
export const RETRY_DELAYS_MS = [1000, 2000, 4000, 8000, 15000, 20000, 25000, 25000, 25000];

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

/**
 * A gateway error arrives as a full HTML page. Putting that in a thrown Error
 * means the user is shown a wall of markup, which is what used to happen.
 */
function describeFailure(status: number, body: string): string {
  const looksLikeHtml = /^\s*<(!doctype|html)/i.test(body);
  if (looksLikeHtml) {
    return WAKING_STATUS.has(status)
      ? "the server did not respond in time"
      : `the server returned a ${status} page`;
  }
  return body.slice(0, 300);
}

export type ApiFetchOptions = {
  /** Called before each retry, so a caller can say what is happening. */
  onRetry?: (attempt: number, total: number) => void;
};

async function apiFetch<T>(path: string, init?: RequestInit, options?: ApiFetchOptions): Promise<T> {
  const headers = new Headers(init?.headers);
  if (init?.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const method = (init?.method ?? "GET").toUpperCase();
  // Only idempotent reads are retried. A gateway error does not prove the
  // request never arrived, so re-sending a POST could start a second analysis.
  const retryable = method === "GET";

  for (let attempt = 0; ; attempt += 1) {
    const canRetry = retryable && attempt < RETRY_DELAYS_MS.length;
    let response: Response;
    try {
      response = await fetch(`${API_BASE_URL}${path}`, {
        ...init,
        credentials: "include",
        headers,
        cache: "no-store",
      });
    } catch (networkError) {
      // A dropped connection while the upstream wakes looks like this.
      if (canRetry) {
        options?.onRetry?.(attempt + 1, RETRY_DELAYS_MS.length);
        await sleep(RETRY_DELAYS_MS[attempt]);
        continue;
      }
      throw networkError;
    }

    if (!response.ok) {
      if (canRetry && WAKING_STATUS.has(response.status)) {
        options?.onRetry?.(attempt + 1, RETRY_DELAYS_MS.length);
        await sleep(RETRY_DELAYS_MS[attempt]);
        continue;
      }
      const body = await response.text();
      throw new Error(`API ${response.status} ${path}: ${describeFailure(response.status, body)}`);
    }
    return response.json() as Promise<T>;
  }
}

/**
 * Wake the API before asking it for data.
 *
 * On Render's free tier both services stop after ~15 minutes idle. A request to
 * the API's own hostname is held open while it starts -- measured twice at 41s and
 * 42s -- and returns 200. The same request through the `/api` proxy returns 502
 * immediately instead of waiting, which is what the user sees.
 *
 * So the browser does the waiting, against the address the server hands back. The
 * API's CORS allowlist already permits this page's origin, verified against the
 * live service, and `credentials: "omit"` keeps it a simple request with no
 * preflight.
 *
 * Returns true when the API answered, or when there was nothing to wake.
 */
export async function wakeApi(): Promise<boolean> {
  if (API_BASE_URL !== "/api") return true;   // direct connection; nothing to warm

  let origin: string | null = null;
  try {
    const response = await fetch("/api/warm", { cache: "no-store" });
    if (response.ok) origin = ((await response.json()) as { origin: string | null }).origin;
  } catch {
    // Fall through to the retry ladder in apiFetch.
  }
  if (!origin) return false;

  // Two attempts: a cold start measured ~42s, and the first request occasionally
  // lands as the container is still binding its port.
  for (let attempt = 0; attempt < 2; attempt += 1) {
    try {
      const probe = await fetch(`${origin}/health`, {
        cache: "no-store",
        credentials: "omit",
        signal: AbortSignal.timeout(90_000),
      });
      if (probe.ok) return true;
    } catch {
      // Timed out or refused while starting; try once more.
    }
  }
  return false;
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

export function listDemoPatients(options?: ApiFetchOptions): Promise<DemoPatientSummary[]> {
  return apiFetch("/patients/demo", undefined, options);
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
