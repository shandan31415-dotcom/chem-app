#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
带自动刷新的轻量服务端（纯标准库）。

作用：
  1. 提供静态文件（index.html 等）；
  2. 提供 /api/data 接口 —— 任何人打开 App 时返回最新数据；
  3. 数据超过 TTL 秒就在后台悄悄刷新，用户永远不用等。

这样即使没有定时任务，打开 App 也是最新的；定时任务只是兜底。
"""

import os
import sys
import json
import time
import threading
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data.json")
TTL = 600          # 数据有效期（秒），10 分钟
_lock = threading.Lock()
_refreshing = False


def refresh(force=False):
    """重新抓取数据写回 data.json"""
    global _refreshing
    with _lock:
        if _refreshing:
            return
        if not force and os.path.exists(DATA) and (time.time() - os.path.getmtime(DATA) < TTL):
            return
        _refreshing = True
    try:
        sys.path.insert(0, BASE)
        import importlib
        import fetch
        importlib.reload(fetch)
        fetch.main()
    except Exception as e:  # noqa: BLE001
        print("刷新失败:", e, flush=True)
    finally:
        _refreshing = False


def is_stale():
    if not os.path.exists(DATA):
        return True
    return (time.time() - os.path.getmtime(DATA)) > TTL


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=BASE, **kw)

    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        if self.path.split("?")[0] in ("/api/data", "/api/data.json"):
            return self.serve_data()
        return super().do_GET()

    def serve_data(self):
        # 没有缓存 → 阻塞抓一次；有缓存但过期 → 先返回旧的，后台再刷新
        if not os.path.exists(DATA):
            refresh(force=True)
        elif is_stale():
            threading.Thread(target=refresh, kwargs={"force": True}, daemon=True).start()

        try:
            with open(DATA, "rb") as f:
                body = f.read()
            json.loads(body.decode("utf-8"))      # 校验一下别把坏文件发出去
        except Exception:  # noqa: BLE001
            body = json.dumps({"generated_at": 0, "generated_at_text": "",
                               "categories": []}, ensure_ascii=False).encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    port = int(os.environ.get("PORT", "8891"))
    # 启动时如果没有数据，先同步抓一次
    if not os.path.exists(DATA):
        print("首次启动，先抓一次数据…", flush=True)
        refresh(force=True)
    else:
        threading.Thread(target=refresh, daemon=True).start()

    srv = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print("服务已启动: http://0.0.0.0:%d" % port, flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
