// Minimal offline shell: cache the app shell, always go to network for data.
const CACHE = "studio-v1";
self.addEventListener("install", (e) => { self.skipWaiting(); e.waitUntil(caches.open(CACHE).then((c) => c.addAll(["/manifest.webmanifest", "/icons/icon-192.png"]))); });
self.addEventListener("activate", (e) => { e.waitUntil(caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== CACHE).map((k) => caches.delete(k))))); self.clients.claim(); });
self.addEventListener("fetch", (e) => {
  const u = new URL(e.request.url);
  if (e.request.method !== "GET" || u.origin !== location.origin) return;
  if (u.pathname.startsWith("/_next/static/") || u.pathname.startsWith("/icons/")) {
    e.respondWith(caches.match(e.request).then((r) => r || fetch(e.request).then((res) => { const cp = res.clone(); caches.open(CACHE).then((c) => c.put(e.request, cp)); return res; })));
    return;
  }
  if (e.request.mode === "navigate") {
    e.respondWith(fetch(e.request).catch(() => new Response("<meta name=viewport content='width=device-width'><body style='background:#0f1117;color:#eee;font-family:sans-serif;padding:24px'><h2>Çevrimdışı</h2><p>Bağlantı yok. Başlattığınız üretimler sunucuda devam ediyor; bağlantı gelince durumu görebilirsiniz.</p></body>", { headers: { "Content-Type": "text/html; charset=utf-8" } })));
  }
});
