/* 版本号：每次改 app.js / styles.css / index.html 都必须升这个值，
   否则手机上打开的还是缓存里的旧文件（开发计划 P5-1）。*/
const VER = "chem-v5";
const DATA = "chem-data";   // 数据缓存不跟版本走：升版不该把离线数据清空
const SHELL = [
  "./", "./index.html", "./app.js", "./styles.css",
  "./manifest.webmanifest", "./icons/icon-192.png", "./icons/icon-512.png",
  "./icons/icon-maskable-512.png", "./icons/apple-touch-icon.png"
];

self.addEventListener("install", (e) => {
  e.waitUntil(
    caches.open(VER).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((ks) =>
      Promise.all(
        ks.filter((k) => k !== VER && k !== DATA).map((k) => caches.delete(k))
      )
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  if (req.url.indexOf("/api/") >= 0) return;

  // 数据文件：网络优先，失败用缓存（拿到新数据就顺手更新缓存）
  if (req.url.indexOf("/data/") >= 0) {
    e.respondWith(
      fetch(req).then((res) => {
        const cp = res.clone();
        caches.open(DATA).then((c) => c.put(req, cp));
        return res;
      }).catch(() => caches.match(req).then((hit) => hit || Response.error()))
    );
    return;
  }

  // 静态资源：缓存优先，取到新的就写回缓存
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
