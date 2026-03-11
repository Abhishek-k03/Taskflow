// Proxies /health to the backend, read fresh from the environment on every
// request - see src/app/api/[...path]/route.ts for why this isn't a
// next.config.ts rewrite.

const BACKEND_URL = process.env.TASKFLOW_BACKEND_URL || "http://localhost:8000";

export async function GET(): Promise<Response> {
  const backendResponse = await fetch(`${BACKEND_URL}/health`, {
    cache: "no-store",
  });
  const body = await backendResponse.text();

  return new Response(body, {
    status: backendResponse.status,
    headers: { "Content-Type": "application/json" },
  });
}
