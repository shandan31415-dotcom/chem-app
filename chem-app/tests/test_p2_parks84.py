# -*- coding: utf-8 -*-
"""问题2 · 地图全量展示 84 家化工园区 验收测试

需求：地图模块全量展示 84 个化工园区（原 85 家中「高密仁和化工产业园」已取消资格，按 84 家计），
及园区里的全部企业（现有企业保留，新增园区暂无企业时明确标注「名录整理中」，不做编造）。
"""
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import webrunner as W  # noqa: E402


def load_parks():
    p = os.path.join(ROOT, "data", "parks.json")
    with open(p, encoding="utf-8") as f:
        return json.load(f)


# ------------------------------------------------------------------ 数据层
class TestParks84Data(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = load_parks()

    def test_parks_total_is_84(self):
        tot = sum(len(c["parks"]) for c in self.d["cities"])
        self.assertEqual(84, tot, "应恰好 84 家园区，实际 %d" % tot)

    def test_all_16_cities_covered(self):
        cities = self.d["cities"]
        self.assertEqual(16, len(cities), "应 16 地市")
        for c in cities:
            self.assertGreaterEqual(len(c["parks"]), 1, "%s 应有至少 1 家园区" % c["name"])

    def test_no_duplicate_park_names(self):
        names = [p["name"] for c in self.d["cities"] for p in c["parks"]]
        dups = sorted({n for n in names if names.count(n) > 1})
        self.assertEqual([], dups, "园区重名：" + "、".join(dups))

    def test_gaomi_renhe_excluded(self):
        """高密仁和化工产业园已取消资格，不得出现"""
        names = [p["name"] for c in self.d["cities"] for p in c["parks"]]
        self.assertNotIn("高密仁和化工产业园", names, "高密仁和已被取消资格，不应收录")

    def test_level_values_valid(self):
        """等级只能是三档"""
        levels = {p["level"] for c in self.d["cities"] for p in c["parks"]}
        self.assertTrue(levels <= {"高端为主", "高端+基础", "基础为主"},
                        "出现非法等级：%s" % levels)

    def test_special_parks_marked(self):
        """专业化工园区应有 special 标记"""
        special = [p["name"] for c in self.d["cities"] for p in c["parks"] if p.get("special")]
        self.assertEqual(10, len(special), "专业园区应为 10 家，实际 %d：%s" % (len(special), special))

    def test_enterprises_preserved(self):
        """企业总数不应缩水（保留原有重点企业）"""
        tot = sum(len(p["enterprises"]) for c in self.d["cities"] for p in c["parks"]) + \
            sum(len(c.get("enterprises", [])) for c in self.d["cities"])
        self.assertGreaterEqual(tot, 150, "企业总数应 ≥150，实际 %d" % tot)

    def test_every_park_has_fields(self):
        """每个园区必备字段齐全"""
        for c in self.d["cities"]:
            for p in c["parks"]:
                for f in ["id", "name", "district", "type", "level", "intro"]:
                    self.assertTrue(p.get(f), "%s 缺字段 %s" % (p.get("name"), f))


# ------------------------------------------------------------------ 前端层
class TestParks84Frontend(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ctx = W.App().__enter__()
        cls.b = cls.ctx.browser

    @classmethod
    def tearDownClass(cls):
        cls.ctx.__exit__(None, None, None)

    def test_map_shows_84_parks(self):
        """地图页统计应显示 84 个园区"""
        b = self.ctx.open()
        b.wait_js("!!document.querySelector('#app .sdmap')", 10, "应显示地图")
        txt = b.app_text()
        self.assertIn("84", txt, "地图页统计应含 84 园区")

    def test_city_detail_lists_all_parks(self):
        """进入一个地市，园区列表数量与数据一致"""
        d = load_parks()
        # 选园区最多的地市（潍坊 8 家）
        wf = next(c for c in d["cities"] if c["name"] == "潍坊")
        b = self.ctx.open()
        self.ctx.goto_hash("#/city/370700")
        b.wait_js("!!document.querySelector('#app .sec-title')", 10, "地市详情未渲染")
        txt = b.app_text()
        self.assertIn(str(len(wf["parks"])), txt, "潍坊园区数应显示 %d" % len(wf["parks"]))
        for p in wf["parks"]:
            self.assertIn(p["name"], txt, "潍坊园区列表缺 %s" % p["name"])

    def test_empty_park_shows_placeholder(self):
        """无企业的新园区，详情页应显示「名录整理中」而非空卡片"""
        d = load_parks()
        # 找一个无企业的园区
        empty = None
        for c in d["cities"]:
            for p in c["parks"]:
                if not p.get("enterprises"):
                    empty = (c, p)
                    break
            if empty:
                break
        self.assertIsNotNone(empty, "应有无企业的新园区")
        c, p = empty
        b = self.ctx.open()
        self.ctx.goto_hash("#/park/" + p["id"])
        b.wait_js("!!document.querySelector('#app .card')", 10, "园区详情未渲染")
        txt = b.app_text()
        self.assertIn(p["name"], txt, "园区详情应显示名称")
        self.assertIn("名录整理中", txt, "无企业园区应显示「名录整理中」占位")

    def test_special_park_tagged(self):
        """专业园区在地市列表应有「专业园区」标注"""
        b = self.ctx.open()
        self.ctx.goto_hash("#/city/370800")  # 济宁有 2 家专业园区
        b.wait_js("!!document.querySelector('#app .sec-title')", 10, "地市详情未渲染")
        txt = b.app_text()
        self.assertIn("专业园区", txt, "济宁地市列表应有「专业园区」标注")

    def test_no_js_error(self):
        b = self.ctx.open()
        self.ctx.goto_hash("#/parks")
        b.wait_js("!!document.querySelector('#app .sdmap')", 10, "地图未渲染")
        errs = b.cdp.eval("window.__errs") or []
        self.assertEqual([], errs, "地图页存在未捕获 JS 报错")


if __name__ == "__main__":
    unittest.main(verbosity=2)
