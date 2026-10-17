// Service worker: cache-first for static files, network-first for /api, offline page fallback.
const CACHE = "rozi-v1";
const SHELL = ["/", "/offline.html", "/static/css/tokens.css", "/static/css/base.css", "/static/css/components.css", "/static/js/app.js", "/static/icons/icon.svg", "/manifest.webmanifest"];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))).then(() => self.clients.claim()));
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  const url = new URL(req.url);
  if (req.method !== "GET" || url.origin !== location.origin) return;
  if (url.pathname.startsWith("/api/")) {
    // Network-first; only non-personal content is cached.
    event.respondWith(
      fetch(req).then((res) => {
        if (res.ok && url.pathname.startsWith("/api/content/")) {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(req, copy));
        }
        return res;
      }).catch(() => caches.match(req).then((hit) => hit || new Response(JSON.stringify({ error: { code: "offline", message: "You are offline." } }), { status: 503, headers: { "content-type": "application/json" } })))
    );
    return;
  }
  event.respondWith(
    caches.match(req).then((hit) => hit || fetch(req).catch(() => (req.mode === "navigate" ? caches.match("/offline.html") : Response.error())))
  );
});
