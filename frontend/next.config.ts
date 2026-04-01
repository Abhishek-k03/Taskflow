import type { NextConfig } from "next";

// Server-side only (no NEXT_PUBLIC_ prefix) - never inlined into the client
// bundle. /api/* and /health are proxied by Route Handlers (see
// src/app/api/[...path]/route.ts) that read this at request time, so one
// built image can point at different backends without a rebuild.
//
// /ws can't use a Route Handler - Next has no App Router API for handling a
// WebSocket upgrade, only this rewrite mechanism. That makes /ws's backend
// target fixed at build time: unlike the other two routes, pointing this
// image at a different backend for /ws does require a rebuild.
const BACKEND_URL = process.env.TASKFLOW_BACKEND_URL || "http://localhost:8000";
// Browsers cannot set headers on a WebSocket, so the backend authenticates
// the socket with ?token=. Appended here, server-side, rather than shipped
// to the browser.
const API_KEY = process.env.TASKFLOW_API_KEY;
const WS_DESTINATION = API_KEY
  ? `${BACKEND_URL}/ws?token=${encodeURIComponent(API_KEY)}`
  : `${BACKEND_URL}/ws`;

const nextConfig: NextConfig = {
  /* config options here */
  reactCompiler: true,
  output: "standalone",
  async rewrites() {
    return [
      // A WS handshake is an HTTP GET with an Upgrade header, so the
      // destination scheme stays http(s) - Next's rewrite validator
      // rejects ws:// destinations outright, and doesn't need it anyway.
      { source: "/ws", destination: WS_DESTINATION },
    ];
  },
};

export default nextConfig;
