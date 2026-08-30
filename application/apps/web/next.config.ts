import path from "path";
import type { NextConfig } from "next";

const internalApi = process.env.INTERNAL_API_URL;
const publicApiBase = process.env.NEXT_PUBLIC_API_BASE_URL;

// Rewrites are resolved here, during `next build`, and written into
// .next/routes-manifest.json. Setting INTERNAL_API_URL only at runtime is too late.
//
// Asking the browser to call /api while no proxy rule exists is the one combination
// that produces a site that loads and then 404s on every request, so refuse to build
// it rather than discover it in production.
if (publicApiBase === "/api" && !internalApi) {
  throw new Error(
    "NEXT_PUBLIC_API_BASE_URL is '/api', which needs the /api/:path* proxy, but " +
      "INTERNAL_API_URL is not set at build time. In Docker it must be declared " +
      "with ARG INTERNAL_API_URL in the builder stage; a runtime-only value cannot " +
      "work, because rewrites are baked into the build.",
  );
}

const nextConfig: NextConfig = {
  devIndicators: false,
  turbopack: {
    root: path.join(__dirname),
  },
  async rewrites() {
    if (!internalApi) return [];
    return [{ source: "/api/:path*", destination: `${internalApi.replace(/\/$/, "")}/:path*` }];
  },
};

export default nextConfig;
