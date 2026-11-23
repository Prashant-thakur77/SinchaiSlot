// Pages are static files; only /api and /health reach this Worker, which forwards them to the Python API.
// Bodies are streamed, so the server-sent events feed works through it.
export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname.startsWith("/api/") || url.pathname === "/health") {
      const req = new Request(new URL(url.pathname + url.search, env.API_ORIGIN), request);
      req.headers.set("X-Client-IP", request.headers.get("CF-Connecting-IP") ?? "unknown");
      return fetch(req);
    }
    return env.ASSETS.fetch(request);
  },
};
