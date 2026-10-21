#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""本地/云端运行：静态文件 + 数据自动刷新接口"""

import os
import sys
import json
import time
import threading
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

BASE = os.path.dirname(os.path.abspath(__file__))
TTL = 600
_lock = threading.Lock()
_busy = False


def stale():
    p = os.path.join(BASE, "data", "meta.json")
    if not os.path.exists(p):
        return True
    return (time.time() - os.path.getmtime(p)) > TTL


def refresh():
    global _busy
    with _lock:
        if _busy:
            return
        _busy = True
    try:
        sys.path.insert(0, os.path.join(BASE, "scripts"))
        import importlib
        import fetch_all
        importlib.reload(fetch_all)
        fetch_all.main()
    except Exception as e:  # noqa: BLE001
        print("刷新失败:", e, flush=True)
    finally:
        _busy = False


class H(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=BASE, **kw)

    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path.startswith("/api/refresh"):
            threading.Thread(target=refresh, daemon=True).start()
            body = b'{"ok":true}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/" and stale():
            threading.Thread(target=refresh, daemon=True).start()
        return super().do_GET()


def main():
    port = int(os.environ.get("PORT", "8893"))
    if stale():
        print("首次启动，先采集数据…", flush=True)
        refresh()
    srv = ThreadingHTTPServer(("0.0.0.0", port), H)
    print("http://0.0.0.0:%d" % port, flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
