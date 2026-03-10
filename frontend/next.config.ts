import type { NextConfig } from "next";

// Server-side only (no NEXT_PUBLIC_ prefix) - read at request time, not
// inlined into the client bundle at build time. This is what lets one built
// image point at a different backend per environment instead of being
// permanently pinned to whatever URL it was built with.
const BACKEND_URL = process.env.TASKFLOW_BACKEND_URL || "http://localhost:8000";

const nextConfig: NextConfig = {
  /* config options here */
  reactCompiler: true,
  output: "standalone",
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${BACKEND_URL}/api/:path*` },
      { source: "/health", destination: `${BACKEND_URL}/health` },
      // A WS handshake is an HTTP GET with an Upgrade header, so the
      // destination scheme stays http(s) - Next's rewrite validator
      // rejects ws:// destinations outright, and doesn't need it anyway.
      { source: "/ws", destination: `${BACKEND_URL}/ws` },
    ];
  },
};

export default nextConfig;
