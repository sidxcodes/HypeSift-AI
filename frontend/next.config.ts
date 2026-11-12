import type { NextConfig } from "next";

const API = process.env.HYPESIFT_API_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  // Same-origin proxy: the session cookie and media links work without CORS.
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API}/api/:path*` }];
  },
  experimental: { proxyTimeout: 300_000 },
  output: process.env.NEXT_OUTPUT === "standalone" ? "standalone" : undefined,
  distDir: process.env.NEXT_DIST_DIR || ".next",
};

export default nextConfig;
