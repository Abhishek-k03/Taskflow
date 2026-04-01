// Proxies /api/* to the backend, read fresh from the environment on every
// request. Unlike a next.config.ts rewrite (resolved once at build time),
// this is what actually lets one built image point at a different backend
// per environment.

const BACKEND_URL = process.env.TASKFLOW_BACKEND_URL || "http://localhost:8000";
// Server-side only. The browser never sees this - it talks to this origin,
// and the key is attached here. That is what let auth be switched on without
// every existing client breaking.
const API_KEY = process.env.TASKFLOW_API_KEY;

async function proxy(
  request: Request,
  { params }: { params: Promise<{ path: string[] }> },
): Promise<Response> {
  const { path } = await params;
  const search = new URL(request.url).search;
  const target = `${BACKEND_URL}/api/${path.join("/")}${search}`;

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (API_KEY) headers["X-API-Key"] = API_KEY;

  const init: RequestInit = {
    method: request.method,
    headers,
    cache: "no-store",
  };
  if (request.method !== "GET" && request.method !== "HEAD") {
    const body = await request.text();
    if (body) init.body = body;
  }

  const backendResponse = await fetch(target, init);
  const responseBody = await backendResponse.text();

  return new Response(responseBody, {
    status: backendResponse.status,
    headers: {
      "Content-Type": backendResponse.headers.get("Content-Type") || "application/json",
    },
  });
}

export { proxy as GET, proxy as POST, proxy as DELETE, proxy as PUT, proxy as PATCH };
