// Saur Mitra offline support: app shell cache-first, API network-first with the last good response.
const SHELL = "sinchai-shell-v1";
const DATA = "sinchai-data-v1";
self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(SHELL).then((c) => c.addAll(["/mitra", "/icon.svg", "/manifest.webmanifest"])).then(() => self.skipWaiting()));
});
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));
self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.pathname === "/api/events") return;
  if (url.pathname.startsWith("/api/")) {
    e.respondWith(
      fetch(e.request)
        .then((r) => {
          const copy = r.clone();
          caches.open(DATA).then((c) => c.put(e.request, copy));
          return r;
        })
        .catch(() => caches.match(e.request).then((r) => r || new Response("[]", { status: 503, headers: { "Content-Type": "application/json" } }))),
    );
    return;
  }
  if (url.pathname.startsWith("/_next/") || url.pathname === "/mitra") {
    e.respondWith(
      caches.match(e.request).then((hit) => {
        const net = fetch(e.request).then((r) => {
          const copy = r.clone();
          caches.open(SHELL).then((c) => c.put(e.request, copy));
          return r;
        });
        return hit || net;
      }),
    );
  }
});
