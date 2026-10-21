# -*- coding: utf-8 -*-
"""P1 前端 · 「本次更新失败」提示与单文件损坏隔离（A19 的一半）

用真实浏览器跑，数据文件在临时副本里改坏，不动项目里的真数据。
"""
import os
import shutil
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import webrunner as W  # noqa: E402


class TestDataErrorBanner(unittest.TestCase):
    """后端 save_or_keep 写入 error 后，前端必须在对应模块顶部说清楚"""

    @classmethod
    def setUpClass(cls):
        cls.root = W.copy_app()
        W.patch_json(cls.root, "news.json",
                     lambda d: dict(d, error={"msg": "连接超时，5 次重试均失败", "at": "2026-10-21 03:00"}))
        cls.ctx = W.App(cls.root).__enter__()
        cls.b = cls.ctx.browser

    @classmethod
    def tearDownClass(cls):
        cls.ctx.__exit__(None, None, None)
        shutil.rmtree(os.path.dirname(cls.root), ignore_errors=True)

    def test_banner_on_news_module(self):
        self.ctx.open()
        self.ctx.goto_hash("#/news")
        self.b.wait_js("document.getElementById('netbar') && !document.getElementById('netbar').hidden",
                       10, "资讯页应显示更新失败提示")
        txt = self.b.cdp.eval("document.getElementById('netbar').innerText")
        self.assertIn("资讯本次更新失败", txt)
        self.assertIn("连接超时", txt, "提示要带上失败原因")
        self.assertIn("显示", txt, "提示要说明当前显示的是哪一次的数据")

    def test_banner_not_leaking_to_other_modules(self):
        self.ctx.open()
        self.ctx.goto_hash("#/prices")
        self.b.wait_js("document.getElementById('netbar')", 10)
        hidden = self.b.cdp.eval("document.getElementById('netbar').hidden")
        self.assertTrue(hidden, "资讯的更新失败不该在行情页显示")

    def test_news_still_readable_when_update_failed(self):
        """失败时保留上次内容：列表里要还能看到新闻"""
        self.ctx.open()
        self.ctx.goto_hash("#/news")
        self.b.wait_js("document.querySelectorAll('#app .row').length>0", 10,
                       "更新失败时仍要显示上次的资讯")
        self.assertGreater(self.b.cdp.eval("document.querySelectorAll('#app .row').length"), 0)


class TestBrokenFileIsolation(unittest.TestCase):
    """把一个数据文件写坏，只影响该模块，其他模块照常（A19）"""

    @classmethod
    def setUpClass(cls):
        cls.root = W.copy_app()
        p = os.path.join(cls.root, "data", "categories.json")
        with open(p, "w", encoding="utf-8") as f:
            f.write('{"items": [ 这里故意写坏 JSON')
        cls.ctx = W.App(cls.root).__enter__()
        cls.b = cls.ctx.browser

    @classmethod
    def tearDownClass(cls):
        cls.ctx.__exit__(None, None, None)
        shutil.rmtree(os.path.dirname(cls.root), ignore_errors=True)

    def test_broken_module_shows_message_not_blank(self):
        self.ctx.open()
        self.ctx.goto_hash("#/cats")
        self.b.wait_text("未加载", 10)
        self.assertGreater(len(self.b.app_text()), 5, "坏掉的模块要给提示，不能白屏")

    def test_other_modules_still_work(self):
        self.ctx.open()
        for h, mark in [("#/prices", ".mover"), ("#/policies", ".chip"),
                        ("#/parks", ".sdmap")]:
            self.ctx.goto_hash(h)
            self.b.wait_js("!!document.querySelector('#app %s')" % mark, 12,
                           "%s 应照常渲染" % h)

    def test_no_js_crash(self):
        self.ctx.open()
        self.ctx.goto_hash("#/cats")
        self.ctx.goto_hash("#/prices")
        errs = self.b.cdp.eval("window.__errs") or []
        self.assertEqual([], errs, "坏文件不应引发未捕获异常")


if __name__ == "__main__":
    unittest.main(verbosity=2)
