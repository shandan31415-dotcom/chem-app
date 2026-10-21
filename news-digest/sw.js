/* 离线缓存：界面秒开，断网也能看上次的内容 */
const VER = "v1";
const SHELL = [
  "./",
  "./index.html",
  "./manifest.webmanifest",
  "./icons/icon-192.png",
  "./icons/icon-512.png",
  "./icons/apple-touch-icon.png"
];

self.addEventListener("install", (e) => {
  e.waitUntil(
    caches.open(VER + "-shell").then((c) => c.addAll(SHELL)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => !k.startsWith(VER)).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;

  // 接口请求：只走网络，绝不进缓存
  if (req.url.indexOf("/api/") >= 0) return;

  // 数据文件：先走网络，失败再用缓存
  if (req.url.indexOf("data.json") >= 0) {
    e.respondWith(
      fetch(req, { cache: "no-store" })
        .then((res) => {
          const copy = res.clone();
          caches.open(VER + "-data").then((c) => c.put(req, copy));
          return res;
        })
        .catch(() => caches.match(req))
    );
    return;
  }

  // 静态资源：缓存优先
  e.respondWith(
    caches.match(req).then((hit) => hit || fetch(req).then((res) => {
      if (res && res.status === 200 && req.url.startsWith(self.location.origin)) {
        const copy = res.clone();
        caches.open(VER + "-shell").then((c) => c.put(req, copy));
      }
      return res;
    }).catch(() => caches.match("./index.html")))
  );
});
