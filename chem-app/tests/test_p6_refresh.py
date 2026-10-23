# -*- coding: utf-8 -*-
"""问题6：手动刷新按钮 —— 专项测试。

前端层：头栏有刷新按钮、点击触发重新加载数据、刷新中按钮进入旋转/禁用态、
        刷新完成后恢复并显示更新结果。
"""
import os
import unittest


class TestRefreshButton(unittest.TestCase):
    """前端层：手动刷新按钮（CDP 真点击）"""

    @classmethod
    def setUpClass(cls):
        import sys
        HERE = os.path.dirname(os.path.abspath(__file__))
        ROOT = os.path.dirname(HERE)
        sys.path.insert(0, os.path.join(ROOT, "tests"))
        import webrunner as W
        cls.ctx = W.App().__enter__()
        cls.b = cls.ctx.browser

    @classmethod
    def tearDownClass(cls):
        cls.ctx.__exit__(None, None, None)

    def test_refresh_button_exists(self):
        """头栏有刷新按钮"""
        b = self.ctx.open()
        b.wait_js("!!document.querySelector('#refreshBtn')", 10, "刷新按钮不存在")
        self.assertEqual(b.count("#refreshBtn"), 1, "应有且仅有一个刷新按钮")

    def test_refresh_button_has_icon(self):
        """刷新按钮有刷新图标"""
        b = self.ctx.open()
        b.wait_js("!!document.querySelector('#refreshBtn')", 10)
        txt = b.cdp.eval("document.querySelector('#refreshBtn').textContent")
        self.assertIn("\u27f3", txt, "刷新按钮应有 ⟳ 图标")

    def test_click_refresh_reloads(self):
        """点击刷新后按钮进入旋转态（spin class）"""
        b = self.ctx.open()
        b.wait_js("!!document.querySelector('#refreshBtn')", 10)
        # 点击后立即检查是否进入 spin/disabled 态（刷新很快，用同步判断抓窗口）
        r = b.cdp.eval(
            "(function(){var e=document.querySelector('#refreshBtn');"
            "e.click();return e.classList.contains('spin')||e.disabled;})()")
        self.assertTrue(r, "点击后按钮应立即进入旋转/禁用态")

    def test_refresh_completes(self):
        """刷新完成后按钮恢复可用，且数据仍在"""
        b = self.ctx.open()
        b.wait_js("!!document.querySelector('#refreshBtn')", 10)
        b.cdp.eval("document.querySelector('#refreshBtn').click()")
        # 等待刷新完成（按钮恢复非 spin 态）
        b.wait_js(
            "!!document.querySelector('#refreshBtn') && "
            "!document.querySelector('#refreshBtn').classList.contains('spin')",
            15, "刷新未在预期时间内完成")
        # 数据应正常（地图页能渲染出地图）
        b.wait_js("!!document.querySelector('#app .sdmap') || !!document.querySelector('#app .empty')",
                  10, "刷新后页面未渲染")
        self.assertFalse(b.cdp.eval("document.querySelector('#refreshBtn').disabled"),
                         "刷新完成后按钮应恢复可用")

    def test_refresh_meta_updated(self):
        """刷新完成后 meta 显示更新状态（不再停留在「正在更新…」）"""
        b = self.ctx.open()
        b.wait_js("!!document.querySelector('#refreshBtn')", 10)
        b.cdp.eval("document.querySelector('#refreshBtn').click()")
        b.wait_js(
            "!!document.querySelector('#refreshBtn') && "
            "!document.querySelector('#refreshBtn').classList.contains('spin')",
            15, "刷新未完成")
        import time
        time.sleep(0.8)
        meta = b.cdp.eval("document.querySelector('#meta').textContent")
        self.assertNotIn("正在更新", meta, "刷新完成后 meta 不应停留在「正在更新…」")

    def test_no_js_error(self):
        """刷新操作无 JS 报错"""
        b = self.ctx.open()
        b.wait_js("!!document.querySelector('#refreshBtn')", 10)
        b.cdp.eval("document.querySelector('#refreshBtn').click()")
        b.wait_js(
            "!!document.querySelector('#refreshBtn') && "
            "!document.querySelector('#refreshBtn').classList.contains('spin')",
            15, "刷新未完成")
        errs = b.cdp.eval("window.__errs")
        self.assertFalse(errs, "刷新不应产生 JS 报错: %s" % errs)


if __name__ == "__main__":
    unittest.main(verbosity=2)
