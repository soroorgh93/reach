// Reach service worker: the app shell works offline and opens instantly; everything live
// (/api, Qloo, previews, YouTube) always goes to the network and is never cached here.
const VERSION = "reach-v25";
const SHELL = ["./", "./index.html", "./styles.css", "./app.js", "./film.js", "./synth.js", "./mood.js", "./gestures.js", "./guide.js", "./i18n.js", "./i18n_extra.js", "./i18n_after.js", "./i18n_uni.js", "./universe.js", "./instrument.js", "./after.js", "./judge.html", "./privacy.html", "./readme.html",
  "./vendor/three.module.js", "./vendor/MeshSurfaceSampler.js", "./vendor/tracker.js", "./vendor/d3-array.min.js", "./vendor/d3-geo.min.js",
  "./manifest.webmanifest", "./icons/icon-192.png", "./icons/icon-512.png", "./icons/apple-touch-icon.png", "./icons/favicon.png",
  "./assets/world.json", "./assets/guide/manifest.json", "./assets/earth_atmos_2048.jpg", "./assets/earth_normal_2048.jpg", "./assets/earth_specular_2048.jpg",
  "./assets/earth_lights_2048.png", "./assets/earth_clouds_1024.png", "./assets/touch_poster.jpg", "./assets/oracle_poster.jpg"];
self.addEventListener("install", (e) => { e.waitUntil(caches.open(VERSION).then(c => c.addAll(SHELL)).then(() => self.skipWaiting())); });
self.addEventListener("activate", (e) => { e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== VERSION).map(k => caches.delete(k)))).then(() => self.clients.claim())); });
self.addEventListener("fetch", (e) => {
  const u = new URL(e.request.url);
  if (e.request.method !== "GET" || u.origin !== location.origin || u.pathname.startsWith("/api/")) return;      // live: network only
  const media = /\.(mp3|mp4|webm)$/.test(u.pathname);
  if (media) {                       // soundscapes, guide voice, films: cached the first time they play (range requests pass through)
    if (e.request.headers.get("range")) return;
    e.respondWith(caches.open(VERSION).then(async c => (await c.match(e.request)) || fetch(e.request).then(r => { if (r.ok && r.status === 200) c.put(e.request, r.clone()); return r; })));
    return;
  }
  // the shell: network first so updates arrive at once, the cache when offline
  e.respondWith(fetch(e.request).then(r => { if (r.ok) { const cl = r.clone(); caches.open(VERSION).then(c => c.put(e.request, cl)); } return r; }).catch(() => caches.match(e.request).then(m => m || caches.match("./index.html"))));
});
