import path from "path";
import type { NextConfig } from "next";

const internalApi = process.env.INTERNAL_API_URL;

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
