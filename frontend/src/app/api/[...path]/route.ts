// Proxies /api/* to the backend, read fresh from the environment on every
// request. Unlike a next.config.ts rewrite (resolved once at build time),
// this is what actually lets one built image point at a different backend
// per environment.

const BACKEND_URL = process.env.TASKFLOW_BACKEND_URL || "http://localhost:8000";

async function proxy(
  request: Request,
  { params }: { params: Promise<{ path: string[] }> },
): Promise<Response> {
  const { path } = await params;
  const search = new URL(request.url).search;
  const target = `${BACKEND_URL}/api/${path.join("/")}${search}`;

  const init: RequestInit = {
    method: request.method,
    headers: { "Content-Type": "application/json" },
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
