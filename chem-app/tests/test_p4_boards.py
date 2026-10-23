# -*- coding: utf-8 -*-
"""问题4 · 品类模块七大门类树状图 验收测试

需求：品类模块加「七大板块」树状图（炼化/化肥/无机化工/有机化工/橡胶加工/精细化工/合成材料），
点进去有板块介绍和标杆企业。数据源：data/boards.json，73 个品类各归一个主板块。
"""
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import webrunner as W  # noqa: E402


def load_boards():
    p = os.path.join(ROOT, "data", "boards.json")
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def load_cats():
    p = os.path.join(ROOT, "data", "categories.json")
    with open(p, encoding="utf-8") as f:
        return json.load(f)


# ------------------------------------------------------------------ 数据层
class TestBoardsData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = load_boards()
        cls.cat_ids = {it["id"] for it in load_cats()["items"]}

    def test_seven_boards(self):
        """应恰好 7 大板块"""
        boards = self.d["boards"]
        self.assertEqual(7, len(boards), "应 7 大板块，实际 %d" % len(boards))

    def test_board_names_authoritative(self):
        """板块名与 PPT 第 17 页「七大板块」一致"""
        names = {b["name"] for b in self.d["boards"]}
        self.assertEqual(
            {"炼化", "化肥", "无机化工", "有机化工", "橡胶加工", "精细化工", "合成材料"},
            names, "板块名应与 PPT 七大板块一致，实际 %s" % names)

    def test_all_cats_assigned_once(self):
        """73 个品类应全部归入，且只归一次"""
        assigned = []
        for b in self.d["boards"]:
            assigned.extend(b["cat_ids"])
        self.assertEqual(len(self.cat_ids), len(assigned),
                         "应 %d 个品类被归入，实际 %d" % (len(self.cat_ids), len(assigned)))
        self.assertEqual(len(set(assigned)), len(assigned), "品类存在重复归类")
        self.assertEqual(self.cat_ids, set(assigned), "有品类未被归入或被引用了不存在的品类")

    def test_every_board_has_intro_and_leaders(self):
        """每个板块都应有介绍和至少 3 家标杆企业"""
        for b in self.d["boards"]:
            self.assertTrue(b.get("intro"), "%s 缺介绍" % b["name"])
            self.assertGreaterEqual(len(b.get("leaders") or []), 3,
                                    "%s 标杆企业应 ≥3" % b["name"])

    def test_every_board_has_cats(self):
        """每个板块都应有品类"""
        for b in self.d["boards"]:
            self.assertGreaterEqual(len(b["cat_ids"]), 1, "%s 无品类" % b["name"])

    def test_has_updated_at(self):
        self.assertTrue(self.d.get("updated_at_text"), "boards.json 应含 updated_at_text")


# ------------------------------------------------------------------ 前端层
class TestBoardsFrontend(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ctx = W.App().__enter__()
        cls.b = cls.ctx.browser

    @classmethod
    def tearDownClass(cls):
        cls.ctx.__exit__(None, None, None)

    def test_cats_page_shows_board_tree(self):
        """品类页应显示七大板块树状图入口"""
        b = self.ctx.open()
        self.ctx.goto_hash("#/cats")
        b.wait_js("!!document.querySelector('#app .boards')", 10, "品类页应有七大板块树状图")
        n = b.count("#app .board-node")
        self.assertEqual(7, n, "应 7 个板块节点，实际 %d" % n)
        txt = b.app_text()
        for name in ["炼化", "化肥", "无机化工", "有机化工", "橡胶加工", "精细化工", "合成材料"]:
            self.assertIn(name, txt, "缺板块 %s" % name)

    def test_board_detail_shows_intro_and_leaders(self):
        """点进板块，应有介绍、标杆企业和品类列表"""
        b = self.ctx.open()
        self.ctx.goto_hash("#/board/refining")  # 炼化
        b.wait_js("!!document.querySelector('#app .card-hd')", 10, "板块详情未渲染")
        txt = b.app_text()
        self.assertIn("炼化", txt, "板块名应显示")
        self.assertIn("板块介绍", txt, "应有板块介绍区块")
        self.assertIn("标杆企业", txt, "应有标杆企业区块")
        self.assertIn("本板块品类", txt, "应有品类列表区块")

    def test_board_lists_its_cats(self):
        """板块详情页应列出该板块下的品类，且可点进品类"""
        d = load_boards()
        refining = next(b for b in d["boards"] if b["key"] == "refining")
        b = self.ctx.open()
        self.ctx.goto_hash("#/board/refining")
        b.wait_js("!!document.querySelector('#app .sec-title')", 10, "板块详情未渲染")
        # 该板块第一个品类应出现在列表里（点进后是 #/cat/ 链接）
        links = b.cdp.eval(
            "Array.from(document.querySelectorAll('#app a[href^=\"#/cat/\"]')).map(a=>a.getAttribute('href'))")
        self.assertGreater(len(links), 0, "板块详情应包含品类链接")
        # 品类链接应指向该板块的品类
        expected_ids = set(refining["cat_ids"])
        got_ids = {h.split("/")[-1] for h in links}
        self.assertTrue(got_ids.issubset(expected_ids),
                        "板块品类链接应属于该板块，实际 %s" % got_ids)

    def test_board_back_to_cats(self):
        """板块页返回应回到品类页"""
        b = self.ctx.open()
        self.ctx.goto_hash("#/cats")
        b.wait_js("!!document.querySelector('#app .boards')", 10, "品类页未渲染")
        b.click("#app .board-node", 0)
        b.wait_js("!!document.querySelector('#app .card-hd')", 10, "板块详情未渲染")
        # 点返回按钮
        b.click("#back", 0)
        b.wait_js("!!document.querySelector('#app .boards')", 10, "返回后品类页未渲染")
        n = b.count("#app .board-node")
        self.assertEqual(7, n, "返回品类页应有 7 板块节点")

    def test_no_js_error(self):
        b = self.ctx.open()
        self.ctx.goto_hash("#/cats")
        b.wait_js("!!document.querySelector('#app .boards')", 10, "品类页未渲染")
        b.click("#app .board-node", 0)
        b.wait_js("!!document.querySelector('#app .card-hd')", 10, "板块详情未渲染")
        errs = b.cdp.eval("window.__errs") or []
        self.assertEqual([], errs, "七大板块树状图存在未捕获 JS 报错")


if __name__ == "__main__":
    unittest.main(verbosity=2)
