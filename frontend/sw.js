/* OliveChain mobile app service worker: offline fallback with fresh online data. */
const CACHE = "oc-shell-v4";
const SHELL = ["/m", "/i18n.js", "/icon.svg", "/manifest.webmanifest"];

self.addEventListener("install", event => {
  event.waitUntil(
    caches.open(CACHE).then(cache => cache.addAll(SHELL)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(key => key !== CACHE).map(key => caches.delete(key))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", event => {
  const url = new URL(event.request.url);
  if (event.request.method !== "GET" || url.origin !== location.origin) return;

  const liveData = ["/passport/", "/stats", "/subjects", "/head", "/audit"]
    .some(prefix => url.pathname.startsWith(prefix));
  const shell = SHELL.includes(url.pathname);
  if (!liveData && !shell) return;

  // Network-first prevents an old cached verifier from hiding application fixes.
  event.respondWith(
    fetch(event.request, { cache: "no-store" })
      .then(response => {
        if (response.ok) {
          caches.open(CACHE).then(cache => cache.put(event.request, response.clone()));
        }
        return response;
      })
      .catch(async () => {
        const cached = await caches.match(event.request);
        if (cached) return cached;
        return new Response(JSON.stringify({ error: "offline and no cached response" }), {
          status: 503,
          headers: { "Content-Type": "application/json" }
        });
      })
  );
});
