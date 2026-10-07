// Crypto Machine panel as an installable app. Only the shell (page, icons) is cached so the app opens
// even with a weak signal; data (/api/…) always comes live from the server and is never cached.
const CACHE = "mm-shell-v3";
const SHELL = ["/plancia", "/icon-192.png", "/icon-512.png", "/manifest.webmanifest"];
self.addEventListener("install", e => { e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting())); });
self.addEventListener("activate", e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener("fetch", e => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin || url.pathname.startsWith("/api/")) return;
  if (e.request.mode === "navigate") {  // pages: always the fresh version, the cached one only when offline
    e.respondWith(fetch(e.request).then(r => { const copy = r.clone(); if (url.pathname === "/plancia") caches.open(CACHE).then(c => c.put("/plancia", copy)); return r; })
      .catch(() => url.pathname === "/plancia" ? caches.match("/plancia") : offline()));
    return;
  }
  if (SHELL.includes(url.pathname)) e.respondWith(caches.match(e.request).then(hit => hit || fetch(e.request)));
});

// Any other page while the server is off: say so, instead of showing the cached panel under the wrong address.
function offline() {
  return new Response('<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">' +
    '<title>Server spento</title><body style="font:16px system-ui;background:#0d1424;color:#e8ecf4;padding:24px">' +
    '<h1>Il server della plancia è spento</h1><p>Questa pagina ha bisogno del server. Apri la cartella del progetto, ' +
    'scrivi <code>cmd</code> nella barra dell&#39;indirizzo e lancia <code>python dashboard/server.py</code>, poi ricarica.</p>',
    { status: 503, headers: { "Content-Type": "text/html; charset=utf-8" } });
}
