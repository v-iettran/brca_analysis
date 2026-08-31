/**
 * The route only reports an address; the waiting happens in the browser, over the
 * path measured against the live service (~42s to a 200). These cover the one
 * judgement it makes: whether the address is reachable from a page at all.
 */
import { describe, expect, it, afterEach } from "vitest";
import { GET } from "./route";

const original = process.env.INTERNAL_API_URL;
afterEach(() => {
  if (original === undefined) delete process.env.INTERNAL_API_URL;
  else process.env.INTERNAL_API_URL = original;
});

async function origin() {
  return ((await (await GET()).json()) as { origin: string | null }).origin;
}

describe("/api/warm", () => {
  it("reports nothing to warm in local development", async () => {
    delete process.env.INTERNAL_API_URL;
    expect(await origin()).toBeNull();
  });

  it("returns a public https address the browser can reach", async () => {
    process.env.INTERNAL_API_URL = "https://brca-research-demo-api.onrender.com";
    expect(await origin()).toBe("https://brca-research-demo-api.onrender.com");
  });

  it("strips a trailing slash so the probe URL has no double slash", async () => {
    process.env.INTERNAL_API_URL = "https://api.example.com/";
    expect(await origin()).toBe("https://api.example.com");
  });

  it("withholds a private-service address, which no page could reach", async () => {
    // What INTERNAL_API_URL becomes if the API is moved back to a private service.
    process.env.INTERNAL_API_URL = "http://brca-research-demo-api:8000";
    expect(await origin()).toBeNull();
  });

  it("withholds a bare internal hostname even over https", async () => {
    process.env.INTERNAL_API_URL = "https://brca-api:8000";
    expect(await origin()).toBeNull();
  });
});
