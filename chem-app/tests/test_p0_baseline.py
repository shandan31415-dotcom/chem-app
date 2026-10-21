# -*- coding: utf-8 -*-
"""P0 基线固化 · 验收测试

覆盖：数据断言脚本无真失败、6 个标签可切换且非空、顶栏有更新时间、
无静默 JS 报错、PRD 正文口径已同步。
"""
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import qa  # noqa: E402
from webrunner import App  # noqa: E402

TABS = [
    ("home", "总览"), ("news", "资讯"), ("parks", "地图"),
    ("cats", "品类"), ("prices", "行情"), ("policies", "政策"),
]


class TestDataBaseline(unittest.TestCase):
    """数据层断言"""

    def test_no_hard_failure(self):
        rows = qa.run_all()
        fails = [r for r in rows if r[1] == "FAIL"]
        self.assertEqual([], [(r[0], r[2]) for r in fails], "qa 断言存在真失败")

    def test_reported_assertions_complete(self):
        rows = qa.run_all()
        self.assertGreaterEqual(len(rows), 9, "断言项数不应减少")

    def test_xfail_have_reasons(self):
        for k, v in qa.XFAIL.items():
            self.assertTrue(v.strip(), "XFAIL %s 必须写清原因与归属批次" % k)


class TestPrdSynced(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(ROOT, "..", "PRD.md"), encoding="utf-8") as f:
            self.full = f.read()
        # 变更记录章节里的旧数字是历史留痕，不算过时口径；只校验规范正文
        self.txt = self.full.split("## 12. v1.2 变更记录")[0]

    def test_no_stale_numbers(self):
        hit = [bad for bad in ["27 个园区", "59 家企业", "品类 12 个", "共 12 个"] if bad in self.txt]
        self.assertEqual([], hit, "规范正文仍有旧口径")

    def test_has_v14_chapter(self):
        self.assertIn("## 14. v1.4", self.full)

    def test_park_zip_numbers_are_actual(self):
        import json
        with open(os.path.join(ROOT, "data", "parks.json"), encoding="utf-8") as f:
            d = json.load(f)
        zibo = [c for c in d["cities"] if c["name"] == "淄博"][0]
        ents = sum(len(p.get("enterprises", [])) for p in zibo["parks"]) + len(zibo.get("enterprises") or [])
        self.assertIn("%d 家企业" % ents, self.txt, "A8 口径应与实测一致")


class TestAppShell(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ctx = App().__enter__()
        cls.b = cls.ctx.browser

    @classmethod
    def tearDownClass(cls):
        cls.ctx.__exit__(None, None, None)

    def test_boot_shows_update_time(self):
        b = self.ctx.open()
        meta = b.cdp.eval("document.getElementById('meta').innerText") or ""
        self.assertRegex(meta, r"\d{4}-\d{2}-\d{2}", "顶栏必须显示数据更新时间，实际：%r" % meta)

    def test_six_tabs_switch_and_not_blank(self):
        b = self.ctx.open()
        for r, label in TABS:
            b.click_and_wait_hash('.tab[data-r="%s"]' % r, "#/" + r)
            b.wait_js("document.querySelector('.tab.on').dataset.r===%s" % ('"%s"' % r), 10,
                      "当前页标签应高亮：" + label)
            txt = b.app_text()
            self.assertGreater(len(txt), 20, "「%s」页内容为空" % label)
            self.assertNotIn("未加载", txt, "「%s」页报数据未加载" % label)

    def test_no_silent_js_error(self):
        b = self.ctx.open()
        for r, _ in TABS:
            b.click_and_wait_hash('.tab[data-r="%s"]' % r, "#/" + r)
        errs = b.cdp.eval("window.__errs") or []
        self.assertEqual([], errs, "页面存在未捕获 JS 报错")

    def test_bottom_nav_sticky(self):
        b = self.ctx.open()
        pos = b.cdp.eval("getComputedStyle(document.getElementById('nav')).position")
        self.assertEqual("fixed", pos, "底部导航必须常驻")

    def test_nav_single_row(self):
        b = self.ctx.open()
        rows = b.cdp.eval(
            "Array.from(document.querySelectorAll('.tab')).map(function(t){"
            "return Math.round(t.getBoundingClientRect().top)}).filter(function(v,i,a){"
            "return a.indexOf(v)===i}).length")
        self.assertEqual(1, rows, "6 个标签必须在同一行（不折行）")


if __name__ == "__main__":
    unittest.main(verbosity=2)
