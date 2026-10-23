# -*- coding: utf-8 -*-
"""问题1 · 导航重构验收测试

需求：删除「总览」模块，把「地图」设为第一个模块，打开 App 即看到地图；
所有模块底部新增免责声明。
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import webrunner as W  # noqa: E402

# 删除总览后剩下的 5 个模块，顺序：地图第一
TABS = [("parks", "地图"), ("cats", "品类"), ("news", "资讯"),
        ("prices", "行情"), ("policies", "政策")]


class TestNavRestructure(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ctx = W.App().__enter__()
        cls.b = cls.ctx.browser

    @classmethod
    def tearDownClass(cls):
        cls.ctx.__exit__(None, None, None)

    def test_five_tabs_no_overview(self):
        """导航只有 5 个模块，不再有「总览」"""
        b = self.ctx.open()
        labels = b.cdp.eval(
            "Array.from(document.querySelectorAll('.tab')).map(function(t){return t.innerText.trim()})")
        self.assertEqual(5, len(labels), "应有 5 个标签，实际 %s" % labels)
        self.assertFalse(any("总览" in l for l in labels), "不应再出现「总览」标签")

    def test_map_is_first_tab(self):
        """地图是第一个标签"""
        b = self.ctx.open()
        first = b.cdp.eval("document.querySelector('.tab').dataset.r")
        self.assertEqual("parks", first, "第一个标签应为地图")

    def test_open_app_shows_map(self):
        """打开 App（无 hash）即显示地图页"""
        b = self.ctx.open()
        seg = b.cdp.eval(
            "(location.hash.replace(/^#\\/?/,'').split('/')[0]) || 'parks'")
        # 地图页有搜索框和地图 svg
        b.wait_js("!!document.querySelector('#app .sdmap')", 10, "应显示山东地图")
        self.assertIn("parks", seg)

    def test_hash_home_falls_back_to_map(self):
        """旧的 #/home 应回落到地图，不再有总览首页"""
        b = self.ctx.open()
        self.ctx.goto_hash("#/home")
        b.wait_js("!!document.querySelector('#app .sdmap')", 10, "#/home 应回落到地图")
        self.assertFalse(b.cdp.eval("!!document.querySelector('#app .hero')"),
                         "不应再渲染总览首页的今日一品卡片")

    def test_every_module_has_disclaimer(self):
        """5 个模块页底部都要有免责声明"""
        b = self.ctx.open()
        for r, label in TABS:
            self.ctx.goto_hash("#/" + r)
            b.wait_js("!!document.querySelector('#app')", 10)
            n = b.cdp.eval("document.querySelectorAll('#app .disclaimer').length")
            self.assertGreaterEqual(n, 1, "「%s」页缺免责声明" % label)
            txt = b.cdp.eval(
                "(function(){var e=document.querySelector('#app .disclaimer');"
                "return e?e.innerText:''})()")
            self.assertIn("仅供参考", txt, "「%s」页免责声明文案应含「仅供参考」" % label)

    def test_all_tabs_switch_and_not_blank(self):
        """5 个标签都能切换且非空"""
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
