const VER = "chem-v4";
const SHELL = [
  "./", "./index.html", "./app.js", "./styles.css",
  "./manifest.webmanifest", "./icons/icon-192.png", "./icons/icon-512.png",
  "./icons/apple-touch-icon.png"
];

self.addEventListener("install", (e) => {
  e.waitUntil(
    caches.open(VER).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((ks) =>
      Promise.all(ks.filter((k) => k !== VER).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  if (req.url.indexOf("/api/") >= 0) return;

  // 数据文件：网络优先，失败用缓存
  if (req.url.indexOf("/data/") >= 0) {
    e.respondWith(
      fetch(req).then((res) => {
        const cp = res.clone();
        caches.open(VER + "-d").then((c) => c.put(req, cp));
        return res;
      }).catch(() => caches.match(req))
    );
    return;
  }

  // 静态资源：缓存优先
  e.respondWith(
    caches.match(req).then((hit) => hit || fetch(req).then((res) => {
      if (res && res.status === 200 && req.url.startsWith(self.location.origin)) {
        const cp = res.clone();
        caches.open(VER).then((c) => c.put(req, cp));
      }
      return res;
    }).catch(() => caches.match("./index.html")))
  );
});
