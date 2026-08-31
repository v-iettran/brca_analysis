import { NextResponse } from "next/server";

/**
 * Tell the browser where to knock to wake the API.
 *
 * Measured behaviour on Render's free tier, with the API genuinely asleep:
 *
 *   - a request to the API's own hostname is held open ~42s and returns 200;
 *   - the same request through the `/api/:path*` rewrite returns 502 immediately.
 *     It does still trigger the wake -- an earlier reading suggested otherwise, but
 *     that was an artefact of polling for only 23s against a ~42s cold start -- it
 *     simply does not wait for it.
 *
 * So the wake needs a client willing to wait, and the browser is the one client
 * that certainly can. This route only reports the address; the waiting happens in
 * the browser, over the path that was actually measured. Nothing here holds a long
 * request open, because whether Render's own edge would permit that was never
 * verified and a fix should not rest on an untested assumption.
 *
 * `INTERNAL_API_URL` is read at request time, not frozen into the build the way a
 * rewrite is. The route lives at `/api/warm`, which the rewrite cannot intercept:
 * rewrites run in the `afterFiles` phase, so real routes match first.
 */

export const dynamic = "force-dynamic";

export async function GET() {
  const upstream = process.env.INTERNAL_API_URL?.replace(/\/$/, "");

  // No proxy configured: local development talks to the API directly.
  if (!upstream) {
    return NextResponse.json({ origin: null, reason: "no INTERNAL_API_URL" });
  }

  // Only an address the browser can actually reach is worth returning. A private
  // service (http://name:8000) is unreachable from a page, and saying otherwise
  // would send the browser off to fail slowly.
  const reachable = /^https:\/\//.test(upstream) && !/^https?:\/\/[^.]+(:\d+)?$/.test(upstream);
  return NextResponse.json({ origin: reachable ? upstream : null });
}
