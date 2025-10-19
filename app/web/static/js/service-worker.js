const CACHE_NAME = "tacticaldesk-shell-v2";
const PRECACHE_URLS = [
  "/static/css/app.css",
  "/static/js/app.js",
  "/static/img/logo.svg",
  "/static/img/favicon.svg",
  "/static/manifest.webmanifest"
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(CACHE_NAME)
      .then((cache) => cache.addAll(PRECACHE_URLS))
      .catch(() => Promise.resolve())
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys.filter((key) => key !== CACHE_NAME).map((staleKey) => caches.delete(staleKey))
      )
    )
  );
  self.clients.claim();
});

function isSameOrigin(request) {
  return new URL(request.url).origin === self.location.origin;
}

function isApiRequest(request) {
  return new URL(request.url).pathname.startsWith("/api/");
}

const OFFLINE_FALLBACK =
  "<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"utf-8\"/><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"/><title>Offline · Tactical Desk</title><style>body{font-family:system-ui,-apple-system,BlinkMacSystemFont,\"Segoe UI\",sans-serif;margin:0;display:flex;align-items:center;justify-content:center;min-height:100vh;background:#0f172a;color:#e2e8f0;padding:32px;text-align:center;}main{max-width:420px;}h1{font-size:1.5rem;margin-bottom:12px;}p{margin:0;font-size:1rem;line-height:1.5;}</style></head><body><main><h1>You&apos;re offline</h1><p>Reconnect to resume using Tactical Desk. Recent pages and assets stay available when possible.</p></main></body></html>";

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET" || !isSameOrigin(request) || isApiRequest(request)) {
    return;
  }

  if (request.mode === "navigate" || request.destination === "document") {
    event.respondWith(
      fetch(request)
        .then((response) => {
          const copy = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(request, copy));
          return response;
        })
        .catch(async () => {
          const cache = await caches.open(CACHE_NAME);
          const cachedResponse = await cache.match(request);
          if (cachedResponse) {
            return cachedResponse;
          }
          return new Response(OFFLINE_FALLBACK, {
            headers: { "Content-Type": "text/html; charset=utf-8" },
          });
        })
    );
    return;
  }

  event.respondWith(
    caches.open(CACHE_NAME).then(async (cache) => {
      const cached = await cache.match(request);
      const networkFetch = fetch(request)
        .then((response) => {
          if (response && response.ok) {
            cache.put(request, response.clone());
          }
          return response;
        })
        .catch(() => {
          if (cached) {
            return cached;
          }
          return Promise.reject(new Error("Network unavailable and no cached response."));
        });
      return cached || networkFetch;
    })
  );
});
