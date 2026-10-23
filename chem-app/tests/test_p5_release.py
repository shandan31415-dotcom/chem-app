# -*- coding: utf-8 -*-
"""P5 发布就绪 · 验收测试（P5-1 SW / P5-2 自动采集 / P5-3 Pages / A20 安装前提）

这一批测的不是功能，是「发出去能不能用」：
Service Worker 版本、离线缓存清单、PWA manifest、两个 Actions 工作流、
以及说明书里该写的部署步骤是否真写了。
"""
import json
import os
import re
import sys
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
REPO = os.path.dirname(ROOT)
sys.path.insert(0, HERE)
import webrunner as W  # noqa: E402

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def load(name):
    import json as _j
    return _j.loads(read(os.path.join(ROOT, "data", name)))


def sw_src():
    return read(os.path.join(ROOT, "sw.js"))


def const(name):
    m = re.search(r'const\s+%s\s*=\s*"([^"]*)"' % name, sw_src())
    return m.group(1) if m else None


def shell_list():
    m = re.search(r"const\s+SHELL\s*=\s*\[(.*?)\];", sw_src(), re.S)
    return re.findall(r'"([^"]+)"', m.group(1)) if m else []


class TestServiceWorker(unittest.TestCase):
    def test_version_bumped(self):
        """前端改过多次（P1–P6），版本号必须已脱离初始 v5，否则手机看不到更新"""
        ver = const("VER")
        self.assertTrue(ver, "sw.js 应有 VER 版本号")
        # 初始是 chem-v5，此后每个问题都升过版；只要不是 v5 就说明一直在升
        self.assertNotEqual("chem-v5", ver, "版本号必须已从初始 chem-v5 递增")
        m = re.match(r"^chem-v(\d+)$", ver)
        self.assertTrue(m, "版本号格式应为 chem-vN")
        self.assertGreaterEqual(int(m.group(1)), 5, "版本号不应回退到 5 以下")

    def test_data_cache_not_versioned(self):
        """数据缓存不能跟版本号绑在一起，升版会把离线数据清空"""
        data = const("DATA")
        self.assertTrue(data, "sw.js 应有独立的 DATA 缓存名")
        self.assertNotEqual(const("VER"), data)
        self.assertNotIn("VER + \"-d\"", sw_src(), "数据缓存不应再拼版本号")

    def test_shell_files_exist(self):
        """SHELL 里列的每个文件都必须真实存在，否则 install 直接失败"""
        miss = []
        for p in shell_list():
            rel = p.lstrip("./")
            full = os.path.join(ROOT, rel if rel else "index.html")
            if rel == "" or rel == ".":
                full = os.path.join(ROOT, "index.html")
            if not os.path.exists(full):
                miss.append(p)
        self.assertEqual([], miss, "SHELL 清单里有不存在的文件")

    def test_shell_covers_core_assets(self):
        lst = " ".join(shell_list())
        for f in ["index.html", "app.js", "styles.css", "manifest.webmanifest",
                  "icons/icon-192.png", "icons/icon-512.png",
                  "icons/icon-maskable-512.png"]:
            self.assertIn(f, lst, "SHELL 缺少 %s" % f)

    def test_strategy_unchanged(self):
        """数据网络优先、静态缓存优先：这两条是离线的命根子"""
        s = sw_src()
        self.assertIn('/data/', s)
        self.assertIn("caches.match(req)", s)
        self.assertIn(".catch(", s, "取不到网络时必须回落缓存")


class TestManifest(unittest.TestCase):
    def setUp(self):
        self.m = json.loads(read(os.path.join(ROOT, "manifest.webmanifest")))

    def test_installable_fields(self):
        self.assertEqual("standalone", self.m["display"], "装到桌面要全屏无地址栏")
        self.assertTrue(self.m["start_url"])
        self.assertTrue(self.m["name"] and self.m["short_name"])
        self.assertTrue(self.m.get("theme_color"))

    def test_icons_192_512_maskable(self):
        """A20 的硬前提：192/512 + maskable 三个图标缺一个就装不上或图标被裁"""
        sizes = set()
        maskable = False
        for ic in self.m["icons"]:
            sizes.add(ic["sizes"])
            if ic.get("purpose") == "maskable":
                maskable = True
            self.assertTrue(os.path.exists(os.path.join(ROOT, ic["src"])),
                            "图标文件不存在：%s" % ic["src"])
        self.assertIn("192x192", sizes)
        self.assertIn("512x512", sizes)
        self.assertTrue(maskable, "缺 maskable 图标，安卓桌面会被裁成方块")


class TestServiceWorkerLive(unittest.TestCase):
    """真的在浏览器里注册一次，确认缓存建好了"""

    @classmethod
    def setUpClass(cls):
        cls.ctx = W.App().__enter__()
        cls.b = cls.ctx.browser

    @classmethod
    def tearDownClass(cls):
        cls.ctx.__exit__(None, None, None)

    def test_sw_takes_control_and_precaches(self):
        b = self.ctx.open()
        b.wait_js("!!navigator.serviceWorker.controller", 20, "Service Worker 应接管页面")
        ver = const("VER")
        keys = b.cdp.eval(
            "caches.keys().then(function(ks){return ks;})") or []
        self.assertIn(ver, keys, "缓存里应有当前版本 %s，实际 %r" % (ver, keys))
        hit = b.cdp.eval(
            "caches.match(new URL('./index.html',location.href).href)"
            ".then(function(r){return !!r;})")
        self.assertTrue(hit, "install 时应预缓存 index.html")


class TestWorkflows(unittest.TestCase):
    def setUp(self):
        if yaml is None:
            self.skipTest("没装 pyyaml，跳过工作流结构校验")
        self.daily_p = os.path.join(REPO, ".github", "workflows", "daily.yml")
        self.pages_p = os.path.join(REPO, ".github", "workflows", "pages.yml")

    def load(self, p):
        self.assertTrue(os.path.exists(p), "工作流文件不存在：%s" % p)
        return yaml.safe_load(read(p))

    def trigger(self, d):
        return d.get("on") or d.get(True) or {}

    def runs(self, d):
        out = []
        for job in d["jobs"].values():
            for st in job.get("steps", []):
                out.append(str(st.get("run", "")))
        return "\n".join(out)

    def test_daily_fetches_only(self):
        """每天只跑采集，绝不能跑 build_enrich（会覆盖人工整理的企业与品类）"""
        d = self.load(self.daily_p)
        body = self.runs(d)
        self.assertIn("scripts/fetch_all.py", body)
        self.assertNotIn("build_enrich", body, "Actions 里不能跑 build_enrich.py")
        self.assertNotIn("build_map", body)

    def test_daily_schedule_and_manual(self):
        d = self.load(self.daily_p)
        trig = self.trigger(d)
        self.assertIn("workflow_dispatch", trig, "要能手动触发一次验证")
        cron = [c["cron"] for c in trig["schedule"]]
        # 问题7：缩短更新间隔，每天 3 次覆盖期货交易关键时点
        # UTC 01:30=北京09:30（早盘） / UTC 07:30=北京15:30（日盘收盘） / UTC 15:00=北京23:00（夜盘收盘）
        for c in ["30 1 * * *", "30 7 * * *", "0 15 * * *"]:
            self.assertIn(c, cron, "缺少定时 %s（每天应抓取 3 次）" % c)

    def test_daily_commits_data(self):
        d = self.load(self.daily_p)
        self.assertEqual("write", d["permissions"]["contents"], "提交 data 需要写权限")
        body = self.runs(d)
        self.assertIn("git add data", body)
        self.assertIn("git commit", body)
        self.assertIn("git push", body)

    def test_pages_publishes_chem_app(self):
        """chem-app 是子目录，必须把子目录作为站点根发布"""
        d = self.load(self.pages_p)
        steps = [st for job in d["jobs"].values() for st in job.get("steps", [])]
        uses = " ".join(str(s.get("uses", "")) for s in steps)
        self.assertIn("actions/upload-pages-artifact", uses)
        self.assertIn("actions/deploy-pages", uses)
        up = [s for s in steps if "upload-pages-artifact" in str(s.get("uses", ""))][0]
        self.assertEqual("chem-app", up["with"]["path"])
        self.assertEqual("write", d["permissions"]["pages"])
        self.assertEqual("write", d["permissions"]["id-token"])


class TestFreshness(unittest.TestCase):
    """发出去的内容不能是两年前的稿子"""

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        import fetch_all as F
        cls.F = F

    def test_stale_news_dropped(self):
        now = 1792512000
        items = [
            {"title": "今天的", "ts": now - 3600},
            {"title": "40 天前", "ts": now - 40 * 86400},
            {"title": "两年前", "ts": now - 700 * 86400},
            {"title": "没日期"},
        ]
        keep, dropped = self.F.drop_stale(items, now=now)
        self.assertEqual(1, dropped)
        titles = [i["title"] for i in keep]
        self.assertIn("今天的", titles)
        self.assertIn("40 天前", titles, "45 天内应保留")
        self.assertIn("没日期", titles, "没有日期的稿子不能一刀切删")

    def test_current_news_is_fresh(self):
        """现在线上的资讯里不该有超过 45 天的稿子"""
        d = load("news.json")
        now = time.time()
        stale = [(i["title"][:28], int((now - i["ts"]) / 86400))
                 for b in d["blocks"] for i in b["items"]
                 if i.get("ts") and now - i["ts"] > 45 * 86400]
        self.assertEqual([], stale, "资讯里有旧稿：%r" % (stale[:3],))

    def test_no_paid_report_spam(self):
        """卖报告/订阅稿不是行业新闻"""
        d = load("news.json")
        bad = []
        for b in d["blocks"]:
            for i in b["items"]:
                for w in ["月报", "推荐报告", "年度报告", "数据包", "订阅", "征订"]:
                    if w in i["title"]:
                        bad.append(i["title"][:30])
                        break
        self.assertEqual([], bad, "资讯里混进了卖报告的稿子")


class TestEntMatch(unittest.TestCase):
    """企业简称匹配的切词边界（回归：『祥海科技』曾命中『海科』）"""

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        import fetch_all as F
        cls.ent_in = staticmethod(F.ent_in)

    def test_two_char_key_not_inside_another_name(self):
        self.assertFalse(self.ent_in("祥海科技开展反应器除锈作业", "海科"),
                         "「祥海科技」不该命中「海科」")

    def test_two_char_key_at_start(self):
        self.assertTrue(self.ent_in("海科化工上半年净利增长", "海科"))

    def test_two_char_key_before_company_suffix(self):
        self.assertTrue(self.ent_in("记者专访海科集团董事长", "海科"))

    def test_long_key_still_plain_substring(self):
        self.assertTrue(self.ent_in("金正大上半年净利同比增长211%", "金正大"))
        self.assertFalse(self.ent_in("无关稿件", "金正大"))


class TestDocs(unittest.TestCase):
    def setUp(self):
        self.t = read(os.path.join(ROOT, "使用说明.md"))

    def test_install_and_deploy_steps(self):
        for k in ["GitHub Pages", "添加到主屏幕", "安装应用", "HTTPS"]:
            self.assertIn(k, self.t, "说明书缺「%s」相关步骤" % k)

    def test_version_bump_rule_documented(self):
        """SW 不升版＝白改，这条必须写进说明书"""
        self.assertIn("VER", self.t)
        self.assertIn("升版本", self.t)

    def test_p3_p4_features_documented(self):
        for k in ["我的数据", "快照", "离线缓存不是备份"]:
            self.assertIn(k, self.t, "说明书缺「%s」" % k)


if __name__ == "__main__":
    unittest.main(verbosity=2)
