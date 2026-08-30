/**
 * Cold-start behaviour.
 *
 * Both Render free instances sleep after ~15 minutes idle; the API then takes
 * about a minute to wake, and the proxy in front of it answers 502 meanwhile.
 * That reached the user as a raw HTML dump, so these cover both halves: the
 * retry, and what is said when it genuinely fails.
 */
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { listDemoPatients, submitDemoAnalysis } from "@/lib/api";

const HTML_502 = '<!DOCTYPE html>\n<html lang="en"><head><title>502</title></head><body>502</body></html>';

const gateway = (status: number) =>
  new Response(HTML_502, { status, headers: { "content-type": "text/html" } });
const ok = (body: unknown) =>
  new Response(JSON.stringify(body), { status: 200, headers: { "content-type": "application/json" } });

beforeEach(() => {
  vi.useFakeTimers();
  vi.stubGlobal("fetch", vi.fn());
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

/** Let the backoff elapse without actually waiting ~50 seconds. */
async function drain<T>(promise: Promise<T>) {
  const settled = promise.then(
    (v) => ({ ok: true, v } as const),
    (e) => ({ ok: false, e } as const),
  );
  for (let i = 0; i < 20; i += 1) await vi.advanceTimersByTimeAsync(30_000);
  return settled;
}

describe("cold start", () => {
  it("retries a sleeping upstream and succeeds when it wakes", async () => {
    const mock = vi.mocked(fetch);
    mock.mockResolvedValueOnce(gateway(502));
    mock.mockResolvedValueOnce(gateway(502));
    mock.mockResolvedValueOnce(gateway(503));
    mock.mockResolvedValueOnce(ok([{ patient_id: "TCGA-A8-A081" }]));

    const result = await drain(listDemoPatients());
    expect(result.ok).toBe(true);
    expect(mock).toHaveBeenCalledTimes(4);
  });

  it("reports each retry so the page can explain the wait", async () => {
    const mock = vi.mocked(fetch);
    mock.mockResolvedValueOnce(gateway(502));
    mock.mockResolvedValueOnce(ok([]));
    const onRetry = vi.fn();
    await drain(listDemoPatients({ onRetry }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("retries a dropped connection too", async () => {
    const mock = vi.mocked(fetch);
    mock.mockRejectedValueOnce(new TypeError("Failed to fetch"));
    mock.mockResolvedValueOnce(ok([]));
    const result = await drain(listDemoPatients());
    expect(result.ok).toBe(true);
    expect(mock).toHaveBeenCalledTimes(2);
  });

  it("never dumps an HTML page into the error message", async () => {
    vi.mocked(fetch).mockResolvedValue(gateway(502));
    const result = await drain(listDemoPatients());
    expect(result.ok).toBe(false);
    const message = String((result as { e: unknown }).e);
    expect(message).not.toContain("<!DOCTYPE");
    expect(message).not.toContain("<html");
    expect(message).toContain("did not respond in time");
  });

  it("gives up rather than retrying forever", async () => {
    vi.mocked(fetch).mockResolvedValue(gateway(502));
    const result = await drain(listDemoPatients());
    expect(result.ok).toBe(false);
    expect(vi.mocked(fetch)).toHaveBeenCalledTimes(7); // initial + 6 backoff steps
  });

  it("does not retry a 404 — that is an answer, not a cold start", async () => {
    vi.mocked(fetch).mockResolvedValue(new Response("no such thing", { status: 404 }));
    const result = await drain(listDemoPatients());
    expect(result.ok).toBe(false);
    expect(vi.mocked(fetch)).toHaveBeenCalledTimes(1);
  });

  it("never retries a POST, so a cold start cannot start two analyses", async () => {
    vi.mocked(fetch).mockResolvedValue(gateway(502));
    const result = await drain(submitDemoAnalysis("TCGA-A8-A081"));
    expect(result.ok).toBe(false);
    expect(vi.mocked(fetch)).toHaveBeenCalledTimes(1);
  });
});
