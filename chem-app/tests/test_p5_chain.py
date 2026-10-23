# -*- coding: utf-8 -*-
"""问题5：品类按产业链上中下游呈现 —— 专项测试。

数据层：chain.json 三段完整、73 品类全覆盖无重复无遗漏。
前端层：品类页有产业链入口 + 筛选按钮、点筛选后列表正确过滤、
        品类详情页有产业链标签、产业链段详情页（#/chain/:key）正常。
"""
import json
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")


def load(name):
    with open(os.path.join(DATA, name), encoding="utf-8") as f:
        return json.load(f)


class TestChainData(unittest.TestCase):
    """数据层：chain.json 完整性与归类正确性"""

    @classmethod
    def setUpClass(cls):
        cls.chain = load("chain.json")
        cls.cats = load("categories.json")

    def test_three_stages(self):
        stages = self.chain["stages"]
        self.assertEqual(len(stages), 3, "产业链应有上中下游三段")
        keys = [s["key"] for s in stages]
        self.assertEqual(set(keys), {"up", "mid", "down"})

    def test_stage_fields(self):
        for s in self.chain["stages"]:
            self.assertTrue(s.get("name"), "每段要有 name")
            self.assertTrue(s.get("short"), "每段要有 short")
            self.assertTrue(s.get("desc"), "每段要有 desc")

    def test_full_coverage_no_gap(self):
        all_ids = {it["id"] for it in self.cats["items"]}
        assigned = set()
        for s in self.chain["stages"]:
            assigned.update(s["cats"])
        self.assertEqual(all_ids - assigned, set(), "不能有遗漏品类")
        self.assertEqual(assigned - all_ids, set(), "不能引用不存在的品类")

    def test_no_duplicate(self):
        seen = []
        for s in self.chain["stages"]:
            seen.extend(s["cats"])
        self.assertEqual(len(seen), len(set(seen)), "品类不能重复归类")

    def test_stage_counts_reasonable(self):
        counts = {s["key"]: len(s["cats"]) for s in self.chain["stages"]}
        total = sum(counts.values())
        self.assertEqual(total, len(self.cats["items"]))
        # 每段都不应为空
        for k, v in counts.items():
            self.assertGreater(v, 0, "环节 %s 不能为空" % k)

    def test_updated_at(self):
        self.assertIn("updated_at", self.chain)


class TestChainFrontend(unittest.TestCase):
    """前端层：产业链入口、筛选、详情标签、段详情页（CDP 真点击）"""

    @classmethod
    def setUpClass(cls):
        import sys
        sys.path.insert(0, os.path.join(ROOT, "tests"))
        import webrunner as W
        cls.ctx = W.App().__enter__()
        cls.b = cls.ctx.browser

    @classmethod
    def tearDownClass(cls):
        cls.ctx.__exit__(None, None, None)

    def test_cats_has_chain_entry(self):
        """品类页有产业链上中下游入口"""
        b = self.ctx.open()
        self.ctx.goto_hash("#/cats")
        b.wait_js("!!document.querySelector('#app .chainbar')", 10, "产业链入口未渲染")
        n = b.count("#app .chain-node")
        self.assertEqual(n, 3, "应有上中下游 3 个入口")

    def test_chain_filter_chips(self):
        """品类页有产业链筛选按钮"""
        b = self.ctx.open()
        self.ctx.goto_hash("#/cats")
        b.wait_js("!!document.querySelector('#app .chips')", 10, "筛选按钮未渲染")
        chips = b.count("#app .chips .chip")
        self.assertGreaterEqual(chips, 4, "应有 全部+上中下游 共 4 个按钮")

    def test_filter_upstream(self):
        """点「上游」后列表只显示上游品类"""
        b = self.ctx.open()
        self.ctx.goto_hash("#/cats")
        b.wait_js("!!document.querySelector('#app .chips')", 10, "筛选按钮未渲染")
        b.click("#app .chips .chip[data-ch='up']")
        b.wait_js("!!document.querySelector('#app .tag.chg-up')", 10, "上游标签未出现")
        # 列表里应全部是上游标签，无中游/下游
        self.assertEqual(b.count("#app .tag.chg-mid"), 0, "不应出现中游标签")
        self.assertEqual(b.count("#app .tag.chg-down"), 0, "不应出现下游标签")
        self.assertGreater(b.count("#app .tag.chg-up"), 0, "应有上游标签")

    def test_chain_stage_page(self):
        """产业链段详情页正常（#/chain/mid）"""
        b = self.ctx.open()
        self.ctx.goto_hash("#/chain/mid")
        b.wait_js("!!document.querySelector('#app .dt')", 10, "段详情页未渲染")
        txt = b.app_text()
        self.assertIn("中游", txt, "应显示中游标题")

    def test_cat_detail_has_chain_tag(self):
        """品类详情页有产业链位置标签"""
        b = self.ctx.open()
        # 找一个上游品类：纯苯 benzene
        self.ctx.goto_hash("#/cat/benzene")
        b.wait_js("!!document.querySelector('#app .dt')", 10, "品类详情未渲染")
        b.wait_js("!!document.querySelector('#app .tag.chg')", 10, "产业链标签未渲染")
        self.assertGreater(b.count("#app .tag.chg"), 0, "品类详情应有产业链标签")

    def test_no_js_error(self):
        """浏览产业链相关页面无 JS 报错"""
        b = self.ctx.open()
        for h in ["#/cats", "#/chain/up", "#/chain/mid", "#/chain/down", "#/cat/methanol"]:
            self.ctx.goto_hash(h)
            b.wait_js("!!document.querySelector('#app')", 10)
        errs = b.cdp.eval("window.__errs")
        self.assertFalse(errs, "不应有 JS 报错: %s" % errs)


if __name__ == "__main__":
    unittest.main(verbosity=2)
