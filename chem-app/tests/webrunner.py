# -*- coding: utf-8 -*-
"""测试基础设施：本地静态服务 + 无头 Edge + CDP 驱动。

不依赖 selenium / playwright，只用 websocket-client 直连 Chrome DevTools Protocol，
这样「点击」是真的点击（触发真实事件、真的跳 hash），不是靠读 HTML 猜。
"""

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import websocket

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")

EDGE_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]


def find_browser():
    for p in EDGE_CANDIDATES:
        if os.path.exists(p):
            return p
    raise RuntimeError("找不到 Edge / Chrome，无法跑前端测试")


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=kw.pop("_root", ROOT), **kw)

    def log_message(self, *a):  # 静音
        pass

    def handle_error(self, *a):  # 浏览器退出时的连接重置不算错误
        pass


def make_handler(root):
    class H(Handler):
        def __init__(self, *a, **kw):
            kw["_root"] = root
            super().__init__(*a, **kw)
    return H


class Server:
    def __init__(self, root=None):
        self.root = root or ROOT
        self.port = free_port()
        self.httpd = ThreadingHTTPServer(("127.0.0.1", self.port), make_handler(self.root))
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        # 等端口可用
        for _ in range(50):
            try:
                with socket.create_connection(("127.0.0.1", self.port), 0.2):
                    break
            except OSError:
                time.sleep(0.05)
        return self

    def __exit__(self, *a):
        self.httpd.shutdown()
        self.httpd.server_close()

    @property
    def base(self):
        return "http://127.0.0.1:%d" % self.port


class CDP:
    """极简 CDP 客户端"""

    def __init__(self, ws_url):
        self.ws = websocket.create_connection(ws_url, timeout=30)
        self.i = 0
        self.pending = {}
        # 原生对话框（confirm/alert/prompt）：不接住会把渲染进程挂死，
        # 导致 Runtime.evaluate 一直等不到返回 → 测试表现为 websocket 超时。
        self.dialogs = []          # [{"type":..,"message":..}]
        self.dialog_policy = True  # True=自动点确定 / False=自动取消 / None=不处理
        self._mute = set()

    def _event(self, msg):
        """处理 CDP 事件（无 id 的消息）"""
        if msg.get("method") != "Page.javascriptDialogOpening":
            return
        p = msg.get("params", {})
        self.dialogs.append({"type": p.get("type"), "message": p.get("message", "")})
        if self.dialog_policy is None:
            return
        self.i += 1
        rid = self.i
        self._mute.add(rid)   # 这条命令的响应自己吞掉，别污染主调用
        self.ws.send(json.dumps({
            "id": rid, "method": "Page.handleJavaScriptDialog",
            "params": {"accept": bool(self.dialog_policy)}}))

    def send(self, method, **params):
        self.i += 1
        mid = self.i
        self.ws.send(json.dumps({"id": mid, "method": method, "params": params}))
        while True:
            msg = json.loads(self.ws.recv())
            if "id" in msg:
                if msg["id"] == mid:
                    if "error" in msg:
                        raise RuntimeError("%s -> %s" % (method, msg["error"]))
                    return msg.get("result", {})
                continue          # 内部命令的响应，忽略
            self._event(msg)

    def eval(self, expr, timeout=20):
        r = self.send("Runtime.evaluate", expression=expr, returnByValue=True,
                      awaitPromise=True, userGesture=True)
        res = r.get("result", {})
        if r.get("exceptionDetails"):
            raise RuntimeError("JS 异常: %s | %s" % (
                expr[:120], r["exceptionDetails"].get("text")))
        return res.get("value")

    def close(self):
        try:
            self.ws.close()
        except Exception:  # noqa: BLE001
            pass


class Browser:
    """一次测试会话用一个浏览器实例（全新 profile，避免 SW 缓存串味）"""

    def __init__(self):
        self.profile = tempfile.mkdtemp(prefix="chemt-")
        self.debug_port = free_port()
        self.proc = subprocess.Popen([
            find_browser(), "--headless=new", "--disable-gpu", "--no-first-run",
            "--no-default-browser-check", "--disable-extensions",
            "--disable-background-networking",
            "--remote-debugging-port=%d" % self.debug_port,
            "--remote-allow-origins=*",
            "--user-data-dir=%s" % self.profile,
            "--window-size=390,844",
            "about:blank",
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.cdp = None
        self._connect()

    def _connect(self):
        url = None
        for _ in range(160):
            try:
                raw = urllib.request.urlopen(
                    "http://127.0.0.1:%d/json/list" % self.debug_port, timeout=1).read()
                targets = json.loads(raw)
                for t in targets:
                    if t.get("type") == "page" and t.get("webSocketDebuggerUrl"):
                        url = t["webSocketDebuggerUrl"]
                        break
                if url:
                    break
            except Exception:  # noqa: BLE001
                pass
            time.sleep(0.1)
        if not url:
            raise RuntimeError("浏览器调试端口没起来")
        self.cdp = CDP(url)
        self.cdp.send("Page.enable")
        self.cdp.send("Runtime.enable")
        self.cdp.send("Network.enable")
        # 收集页面 JS 报错，测试里可以断言「没有静默报错」
        self.cdp.send("Page.addScriptToEvaluateOnNewDocument", source=(
            "window.__errs=[];"
            "window.addEventListener('error',function(e){"
            "window.__errs.push(String(e.message||e.type));});"
            "window.addEventListener('unhandledrejection',function(e){"
            "window.__errs.push('rejection:'+String(e.reason));});"))

    # ---------------- 导航与等待 ----------------
    def goto(self, url, wait_expr=None, timeout=25):
        self.cdp.send("Page.navigate", url=url)
        self.wait_ready(timeout)
        if wait_expr:
            self.wait_js(wait_expr, timeout)

    def wait_ready(self, timeout=25):
        end = time.time() + timeout
        while time.time() < end:
            try:
                if self.cdp.eval("document.readyState", timeout=5) == "complete":
                    return True
            except Exception:  # noqa: BLE001
                pass
            time.sleep(0.1)
        raise RuntimeError("页面 readyState 未完成")

    def wait_js(self, expr, timeout=20, msg=""):
        """轮询直到表达式为真；返回最后一次的值"""
        end = time.time() + timeout
        last = None
        while time.time() < end:
            try:
                last = self.cdp.eval(expr, timeout=8)
            except Exception:  # noqa: BLE001
                last = None
            if last is True or (last is not None and last is not False and last != 0
                                and last != "" and last != []):
                return last
            time.sleep(0.1)
        raise AssertionError("等待超时：%s %s（最后值 %r）" % (msg, expr[:110], last))

    def wait_text(self, text, timeout=20):
        return self.wait_js(
            "document.getElementById('app') && document.getElementById('app').innerText.indexOf(%s)>=0"
            % json.dumps(text), timeout, "页面应出现文字「%s」" % text)

    # ---------------- 便捷操作 ----------------
    def hash(self):
        return self.cdp.eval("location.hash")

    def app_text(self):
        return self.cdp.eval("document.getElementById('app').innerText") or ""

    def app_html(self):
        return self.cdp.eval("document.getElementById('app').innerHTML") or ""

    def click(self, selector, index=0):
        """真实点击（element.click() 会触发默认行为，含 hash 跳转）"""
        expr = ("(function(){var els=document.querySelectorAll(%s);"
                "if(!els[%d])return 'MISS';els[%d].click();return 'OK';})()"
                % (json.dumps(selector), index, index))
        r = self.cdp.eval(expr)
        if r == "MISS":
            raise AssertionError("点击目标不存在: %s[%d]" % (selector, index))
        return r

    def type_into(self, selector, text):
        """往输入框里打字：改 value + 派发 input 事件，等同于用户真的输入"""
        expr = ("(function(){var e=document.querySelector(%s);if(!e)return 'MISS';"
                "e.value=%s;e.dispatchEvent(new Event('input',{bubbles:true}));return 'OK';})()"
                % (json.dumps(selector), json.dumps(text)))
        r = self.cdp.eval(expr)
        if r == "MISS":
            raise AssertionError("输入框不存在: %s" % selector)
        return r

    def count(self, selector):
        return self.cdp.eval("document.querySelectorAll(%s).length" % json.dumps(selector)) or 0

    def click_and_wait_hash(self, selector, prefix, index=0, timeout=15):
        self.click(selector, index)
        end = time.time() + timeout
        while time.time() < end:
            h = self.hash()
            if h and h.startswith(prefix):
                return h
            time.sleep(0.08)
        raise AssertionError("点击 %s 后 hash 未跳到 %s（当前 %s）" % (selector, prefix, self.hash()))

    def set_local(self, key, val):
        self.cdp.eval("localStorage.setItem(%s, %s)" % (json.dumps(key), json.dumps(val)))

    def get_local(self, key):
        return self.cdp.eval("localStorage.getItem(%s)" % json.dumps(key))

    def clear_local(self):
        self.cdp.eval("localStorage.clear()")

    def offline(self, on=True):
        self.cdp.send("Network.emulateNetworkConditions", offline=on,
                      latency=0, downloadThroughput=0, uploadThroughput=0)

    # ---------------- 原生对话框 ----------------
    def accept_dialogs(self, accept=True):
        """设成 True 等于用户点「确定」，False 等于点「取消」"""
        self.cdp.dialog_policy = accept

    def clear_dialogs(self):
        del self.cdp.dialogs[:]

    def last_dialog(self):
        return self.cdp.dialogs[-1]["message"] if self.cdp.dialogs else ""

    def close(self):
        if self.cdp:
            self.cdp.close()
        try:
            self.proc.terminate()
            self.proc.wait(timeout=10)
        except Exception:  # noqa: BLE001
            try:
                self.proc.kill()
            except Exception:  # noqa: BLE001
                pass
        shutil.rmtree(self.profile, ignore_errors=True)


class App:
    """Server + Browser 的组合上下文。root 可指向一个「数据被改坏」的副本，用于隔离性测试。"""

    def __init__(self, root=None):
        self.root = root or ROOT
        self.server = None
        self.browser = None

    def __enter__(self):
        self.server = Server(self.root).__enter__()
        self.browser = Browser()
        return self

    def __exit__(self, *a):
        if self.browser:
            self.browser.close()
        if self.server:
            self.server.__exit__(*a)

    def open(self, hash_path="", wait_text=None):
        url = self.server.base + "/index.html"
        self.browser.goto(url, "!!document.getElementById('app')")
        # 等首屏数据渲染完（骨架屏消失）
        self.browser.wait_js(
            "!!(document.querySelector('#app .hero')||document.querySelector('#app .card-hd')"
            "||document.querySelector('#app .chips')||document.querySelector('#app .sbar')"
            "||document.querySelector('#app .empty')||document.querySelector('#app .dt'))",
            25, "首屏应渲染出内容")
        if hash_path:
            self.goto_hash(hash_path)
        if wait_text:
            self.browser.wait_text(wait_text)
        return self.browser

    def goto_hash(self, path):
        h = path if path.startswith("#") else "#" + ("/" + path if path else "")
        self.browser.cdp.eval("location.hash=%s" % json.dumps(h))
        self.browser.wait_js("location.hash===%s" % json.dumps(h), 10, "hash 应为 " + h)
        self.browser.wait_js("document.readyState==='complete'", 10)


def copy_app():
    """把 App 拷到临时目录（不含测试与备份），用于「改坏数据文件」这类破坏性测试"""
    d = tempfile.mkdtemp(prefix="chemax-")
    dst = os.path.join(d, "app")
    shutil.copytree(ROOT, dst, ignore=shutil.ignore_patterns(
        "tests", "backups", "node_modules", "__pycache__", "*.pyc"))
    return dst


def patch_json(root, name, fn):
    """读改写 data/<name>.json；fn(dict)->dict"""
    p = os.path.join(root, "data", name)
    with open(p, encoding="utf-8") as f:
        d = json.load(f)
    d = fn(d)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False)
