# -*- coding: utf-8 -*-
"""冒烟：确认测试基础设施可用（服务 + 无头浏览器 + CDP 点击）"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from webrunner import App  # noqa: E402


class SmokeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ctx = App().__enter__()
        cls.b = cls.ctx.browser

    @classmethod
    def tearDownClass(cls):
        cls.ctx.__exit__(None, None, None)

    def test_boot_and_render(self):
        b = self.ctx.open()
        t = b.app_text()
        self.assertGreater(len(t), 50, "首屏（地图）应渲染出文字")
        self.assertIn("化工园区", t, "地图页应有园区统计")

    def test_click_tab(self):
        b = self.ctx.open()
        h = b.click_and_wait_hash('.tab[data-r="prices"]', "#/prices")
        self.assertEqual(h, "#/prices")
        b.wait_js("document.querySelectorAll('#app .mover').length>10", 15,
                  "行情页应出现品种行")


if __name__ == "__main__":
    unittest.main(verbosity=2)
