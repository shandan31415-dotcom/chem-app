# -*- coding: utf-8 -*-
"""问题3 · 地图产业集群 / 产业布局高亮切换 验收测试

需求：地图模块增加「高端热力 / 产业集群 / 产业布局」三种视图切换，
产业集群按 PPT 第 19 页五大产业集群着色，产业布局按 PPT 第 20 页「1+3+2」格局着色。
数据源：data/industry.json（数据驱动，独立于 parks.json）。
"""
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import webrunner as W  # noqa: E402


def load_industry():
    p = os.path.join(ROOT, "data", "industry.json")
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def load_parks():
    p = os.path.join(ROOT, "data", "parks.json")
    with open(p, encoding="utf-8") as f:
        return json.load(f)


# ------------------------------------------------------------------ 数据层
class TestIndustryData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = load_industry()
        cls.codes = {c["code"] for c in load_parks()["cities"]}

    def test_has_two_views(self):
        views = self.d.get("views", {})
        self.assertIn("cluster", views, "应有 cluster 产业集群视图")
        self.assertIn("layout", views, "应有 layout 产业布局视图")

    def test_cluster_has_five_clusters(self):
        """产业集群视图应覆盖五大产业集群（石化/煤化/盐化/橡胶/精细）"""
        v = self.d["views"]["cluster"]
        keys = {l["key"] for l in v["legend"]}
        for k in ["石化", "煤化", "盐化", "橡胶", "精细"]:
            self.assertIn(k, keys, "产业集群缺 %s" % k)

    def test_layout_has_1_3_2(self):
        """产业布局视图应含「1+3+2」六类（主体/半岛/鲁中/鲁南/转型/临港）"""
        v = self.d["views"]["layout"]
        keys = {l["key"] for l in v["legend"]}
        for k in ["主体", "半岛", "鲁中", "鲁南", "转型", "临港"]:
            self.assertIn(k, keys, "产业布局缺 %s" % k)

    def test_all_16_cities_covered(self):
        """两个视图都应覆盖全部 16 地市，且 code 合法"""
        for vk in ["cluster", "layout"]:
            cities = self.d["views"][vk].get("cities", {})
            self.assertEqual(16, len(cities), "%s 视图应覆盖 16 地市，实际 %d" % (vk, len(cities)))
            for code in cities:
                self.assertIn(code, self.codes, "%s 视图出现非法 code %s" % (vk, code))

    def test_tags_within_legend(self):
        """每个地市的归属标签必须在该视图 legend 内"""
        for vk in ["cluster", "layout"]:
            v = self.d["views"][vk]
            keys = {l["key"] for l in v["legend"]}
            for code, tags in v["cities"].items():
                self.assertTrue(tags, "%s 视图 %s 无标签" % (vk, code))
                for t in tags:
                    self.assertIn(t, keys, "%s 视图 %s 标签 %s 不在 legend" % (vk, code, t))

    def test_legend_has_color_and_name(self):
        """legend 每项必须有颜色和名称，key 唯一"""
        for vk in ["cluster", "layout"]:
            legend = self.d["views"][vk]["legend"]
            keys = [l["key"] for l in legend]
            self.assertEqual(len(keys), len(set(keys)), "%s 视图 legend key 重复" % vk)
            for l in legend:
                self.assertTrue(l.get("color"), "%s 视图 legend 缺 color" % vk)
                self.assertTrue(l.get("name"), "%s 视图 legend 缺 name" % vk)

    def test_has_updated_at(self):
        self.assertTrue(self.d.get("updated_at_text"), "industry.json 应含 updated_at_text")


# ------------------------------------------------------------------ 前端层
class TestIndustryFrontend(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ctx = W.App().__enter__()
        cls.b = cls.ctx.browser

    @classmethod
    def tearDownClass(cls):
        cls.ctx.__exit__(None, None, None)

    def test_three_view_buttons(self):
        """地图页应有 3 个视图切换按钮：高端热力 / 产业集群 / 产业布局"""
        b = self.ctx.open()
        b.wait_js("!!document.querySelector('#app .sdmap')", 10, "地图未渲染")
        n = b.count("#app .mvt")
        self.assertEqual(3, n, "应 3 个视图切换按钮，实际 %d" % n)
        txt = b.app_text()
        for k in ["高端热力", "产业集群", "产业布局"]:
            self.assertIn(k, txt, "缺视图按钮 %s" % k)

    def test_default_is_heat(self):
        """默认视图是高端热力（地图 path 带热力色 class，无 vw- 前缀）"""
        b = self.ctx.open()
        b.wait_js("!!document.querySelector('#app .sdmap')", 10, "地图未渲染")
        heat = b.count("#app .sdmap path.mct.t0, #app .sdmap path.mct.t1, "
                       "#app .sdmap path.mct.t2, #app .sdmap path.mct.t3")
        self.assertGreater(heat, 0, "默认应有热力色 path")

    def test_click_cluster_switches_view(self):
        """点击「产业集群」后，地图 path 出现 vw-cluster class 和内联 fill"""
        b = self.ctx.open()
        b.wait_js("!!document.querySelector('#app .sdmap')", 10, "地图未渲染")
        b.click("#app .mvt[data-mv='cluster']")
        b.wait_js("!!document.querySelector('#app .sdmap path.vw-cluster')", 10,
                  "点击产业集群后地图未切换")
        n = b.count("#app .sdmap path.vw-cluster")
        self.assertGreater(n, 0, "产业集群视图应有 path.vw-cluster")
        # 有内联 fill 颜色
        filled = b.cdp.eval(
            "Array.from(document.querySelectorAll('#app .sdmap path.vw-cluster'))"
            ".filter(p=>p.style.fill).length")
        self.assertGreater(filled, 0, "产业集群视图 path 应有内联 fill 颜色")
        # 图例应显示产业集群名称
        txt = b.app_text()
        self.assertIn("石油化工", txt, "图例应含「石油化工」")

    def test_click_layout_switches_view(self):
        """点击「产业布局」后，地图 path 出现 vw-layout class"""
        b = self.ctx.open()
        b.wait_js("!!document.querySelector('#app .sdmap')", 10, "地图未渲染")
        b.click("#app .mvt[data-mv='layout']")
        b.wait_js("!!document.querySelector('#app .sdmap path.vw-layout')", 10,
                  "点击产业布局后地图未切换")
        n = b.count("#app .sdmap path.vw-layout")
        self.assertGreater(n, 0, "产业布局视图应有 path.vw-layout")
        txt = b.app_text()
        self.assertIn("鲁北高端石化", txt, "图例应含「鲁北高端石化」")

    def test_switch_back_to_heat(self):
        """切换回「高端热力」后恢复热力色"""
        b = self.ctx.open()
        b.wait_js("!!document.querySelector('#app .sdmap')", 10, "地图未渲染")
        b.click("#app .mvt[data-mv='cluster']")
        b.wait_js("!!document.querySelector('#app .sdmap path.vw-cluster')", 10, "切集群失败")
        b.click("#app .mvt[data-mv='heat']")
        # 轮询直到热力色 path 出现
        import time as _t
        end = _t.time() + 10
        n = 0
        while _t.time() < end:
            n = b.count("#app .sdmap path.mct.t0, #app .sdmap path.mct.t1, "
                        "#app .sdmap path.mct.t2, #app .sdmap path.mct.t3")
            if n > 0:
                break
            _t.sleep(0.1)
        self.assertGreater(n, 0, "切回高端热力应恢复热力色")

    def test_city_click_still_works_after_switch(self):
        """切换视图后，点击地图地市仍能跳转（交互不被破坏）"""
        b = self.ctx.open()
        b.wait_js("!!document.querySelector('#app .sdmap')", 10, "地图未渲染")
        b.click("#app .mvt[data-mv='cluster']")
        b.wait_js("!!document.querySelector('#app .sdmap path.vw-cluster')", 10, "切集群失败")
        # 点击任一地市 path
        b.cdp.eval(
            "(function(){var p=document.querySelector('#app .sdmap path[data-code]');"
            "if(p){var e=new MouseEvent('click',{bubbles:true});p.dispatchEvent(e);}return !!p;})()")
        end = __import__("time").time() + 10
        while __import__("time").time() < end:
            if (b.hash() or "").startswith("#/city/"):
                break
            __import__("time").sleep(0.08)
        self.assertTrue((b.hash() or "").startswith("#/city/"),
                        "切换视图后点击地市应跳转，当前 hash=%s" % b.hash())

    def test_no_js_error(self):
        b = self.ctx.open()
        b.wait_js("!!document.querySelector('#app .sdmap')", 10, "地图未渲染")
        # 三个视图都点一遍，确认无报错
        b.click("#app .mvt[data-mv='cluster']")
        b.wait_js("!!document.querySelector('#app .sdmap path.vw-cluster')", 10, "切集群失败")
        b.click("#app .mvt[data-mv='layout']")
        b.wait_js("!!document.querySelector('#app .sdmap path.vw-layout')", 10, "切布局失败")
        errs = b.cdp.eval("window.__errs") or []
        self.assertEqual([], errs, "切换视图存在未捕获 JS 报错")


if __name__ == "__main__":
    unittest.main(verbosity=2)
