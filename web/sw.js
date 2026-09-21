/* MehranAiShabestar — service worker (v9.9)
   شبکه اول: هر بار آنلاین هستی نسخهٔ تازه از سرور می‌آید (هیچ‌وقت کهنه نمی‌مانی)
   آفلاین: همان صفحهٔ ذخیره‌شده باز می‌شود تا اپ از صفحهٔ گوشی باز بماند. */
const CACHE = "mega-ai-v99";

self.addEventListener("install", (e) => {
  self.skipWaiting();
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(["/", "/assets/logo_icon_256.png"]).catch(() => {})));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== location.origin) return;
  if (url.pathname.startsWith("/api/") || url.pathname.startsWith("/files/")) return; /* داده‌ها هرگز کش نشوند */
  e.respondWith(
    fetch(req)
      .then((res) => {
        const copy = res.clone();
        caches.open(CACHE).then((c) => c.put(req, copy)).catch(() => {});
        return res;
      })
      .catch(() => caches.match(req).then((hit) => hit || caches.match("/")))
  );
});
