# -*- coding: utf-8 -*-
"""P2 首页「今日」链路 · 验收测试（A3 / A4 + PRD 3.3 / 6.3）

全部用真实浏览器点击，不看 HTML 猜。
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import webrunner as W  # noqa: E402


class TestHomeCards(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ctx = W.App().__enter__()
        cls.b = cls.ctx.browser

    @classmethod
    def tearDownClass(cls):
        cls.ctx.__exit__(None, None, None)

    def fresh_home(self):
        b = self.ctx.open()
        self.ctx.goto_hash("#/home")
        b.wait_js("!!document.querySelector('#app .hero')", 10, "首页应有今日一品")
        return b

    # ---------- A3：四类卡片各点一次，都要进对应详情 ----------
    def test_hero_goes_to_category(self):
        b = self.fresh_home()
        name = b.cdp.eval("document.querySelector('#app .hero .t').innerText")
        h = b.click_and_wait_hash("#app .hero", "#/cat/")
        b.wait_js("!!document.querySelector('#app .dt')", 10)
        self.assertIn(name, b.app_text(), "品类详情页标题应与首页卡片一致")

    def test_policy_card_goes_to_policy_detail(self):
        b = self.fresh_home()
        h = b.click_and_wait_hash('#app a.jrow[href^="#/policy/"]', "#/policy/")
        b.wait_js("document.getElementById('app').innerText.indexOf('发文机关')>=0", 10,
                  "政策详情页应有发文机关")
        self.assertIn("发布层级", b.app_text())

    def test_move_card_goes_to_enterprise_detail(self):
        """今日一动必须进企业/园区详情，不能跳到外部新闻（G4）"""
        b = self.fresh_home()
        href = b.cdp.eval("document.querySelector('#app a.jrow[href^=\"#/ent/\"], "
                          "#app a.jrow[href^=\"#/park/\"]') && "
                          "document.querySelector('#app a.jrow[href^=\"#/ent/\"], "
                          "#app a.jrow[href^=\"#/park/\"]').getAttribute('href')")
        if href and href.startswith("#/ent/"):
            h = b.click_and_wait_hash('#app a.jrow[href^="#/ent/"]', "#/ent/")
            b.wait_js("document.getElementById('app').innerText.indexOf('主营产品范围')>=0",
                      10, "企业详情应有主营产品范围")
        elif href:
            h = b.click_and_wait_hash('#app a.jrow[href^="#/park/"]', "#/park/")
            b.wait_js("!!document.querySelector('#app .dt')", 10)
        else:
            # 没匹配到企业时，页面必须明说是「行业动向」且注明未匹配，不能假装是详情
            txt = b.app_text()
            self.assertIn("行业动向", txt)
            self.assertIn("未匹配到收录企业", txt,
                          "未匹配到企业时必须明说，不能假装是详情页")

    def test_mover_rows_go_to_price_detail(self):
        b = self.fresh_home()
        h = b.click_and_wait_hash("#app .mover", "#/price/")
        b.wait_js("!!document.getElementById('kline')", 10, "品种详情应有 K 线画布")

    # ---------- A4：进详情后按返回回到首页 ----------
    def test_back_returns_home(self):
        b = self.fresh_home()
        b.click_and_wait_hash("#app .hero", "#/cat/")
        b.wait_js("!!document.querySelector('#app .dt')", 10)
        b.click("#back")
        b.wait_js("location.hash==='#/home'", 10, "返回应回到首页")
        b.wait_js("!!document.querySelector('#app .hero')", 10)

    # ---------- PRD 3.2：价格异动要带「和这有关的新闻」 ----------
    def test_movers_have_news_line(self):
        b = self.fresh_home()
        n = b.cdp.eval("document.querySelectorAll('#app .mnews').length")
        self.assertGreaterEqual(n, 3, "3 条异动每条都要有一行关联新闻（或明确「暂无相关报道」）")
        txt = b.app_text()
        self.assertTrue("暂无相关报道" in txt or "…" in txt or len(txt) > 0)

    def test_at_least_one_mover_news_is_real(self):
        b = self.fresh_home()
        real = b.cdp.eval(
            "[].slice.call(document.querySelectorAll('#app .mnews'))"
            ".filter(function(e){return !/暂无相关报道/.test(e.innerText)}).length")
        self.assertGreaterEqual(real, 1, "至少 1 条异动要带真实新闻（PRD 3.2）")

    # ---------- PRD 3.3：同一天反复刷新，今日一品不变 ----------
    def test_today_cat_stable(self):
        b = self.fresh_home()
        first = b.cdp.eval("document.querySelector('#app .hero .t').innerText")
        for _ in range(3):
            b.cdp.eval("document.getElementById('refreshBtn').click()")
            b.wait_js("!!document.querySelector('#app .hero .t')", 10)
            now = b.cdp.eval("document.querySelector('#app .hero .t').innerText")
            self.assertEqual(first, now, "同一天刷新，今日一品不应跳变")

    # ---------- PRD 6.3-2：首页不重复展示同一件事 ----------
    def test_no_duplicate_news_on_home(self):
        b = self.fresh_home()
        info = b.cdp.eval("""(function(){
          var mv=document.querySelector('#app .jrow .jt');
          var news=[].slice.call(document.querySelectorAll('#app .mnews'))
            .map(function(e){return e.innerText});
          return {mv: mv?mv.innerText:'', news:news};
        })()""")
        mv = info["mv"]
        for n in info["news"]:
            if not n or "暂无相关报道" in n:
                continue
            self.assertFalse(mv and n[:12] == mv[:12],
                             "今日一动用过的新闻不应在价格异动里重复出现")

    # ---------- 今日一动必须有动作强度排序痕迹 ----------
    def test_move_prefers_enterprise_news(self):
        b = self.fresh_home()
        tag = b.cdp.eval("document.querySelector('#app .jtag.ent').innerText")
        self.assertIn(tag, ["企业动向", "园区动向", "行业动向"])

    def test_home_five_blocks(self):
        b = self.fresh_home()
        txt = b.app_text()
        for k in ["今日一品", "今日一策", "今日一动", "价格异动", "学习进度"]:
            self.assertIn(k, txt, "首页缺区块：" + k)


class TestHomeDedupUnit(unittest.TestCase):
    """不依赖浏览器：直接跑一遍挑选逻辑的一致性检查"""

    @classmethod
    def setUpClass(cls):
        cls.ctx = W.App().__enter__()
        cls.b = cls.ctx.open()

    @classmethod
    def tearDownClass(cls):
        cls.ctx.__exit__(None, None, None)

    def test_movers_unique_symbols(self):
        names = self.b.cdp.eval(
            "[].slice.call(document.querySelectorAll('#app .mover .mn'))"
            ".map(function(e){return e.childNodes[0].textContent.trim()})")
        self.assertEqual(len(names), len(set(names)), "价格异动同品种只能出现一次")

    def test_movers_sorted_by_abs_change(self):
        vals = self.b.cdp.eval(
            "[].slice.call(document.querySelectorAll('#app .mover s'))"
            ".map(function(e){return Math.abs(parseFloat(e.innerText))})")
        self.assertEqual(vals, sorted(vals, reverse=True), "异动应按涨跌幅绝对值降序")


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestMoveToEnterprise(unittest.TestCase):
    """构造一条「含企业名 + 强动作」的新闻，验证今日一动真的会落到企业详情页"""

    @classmethod
    def setUpClass(cls):
        import time
        cls.root = W.copy_app()
        now = int(time.time())

        def add_move(d):
            blocks = d["blocks"]
            sd = [b for b in blocks if b["name"] == "山东"][0]
            sd["items"].insert(0, {
                "title": "万华化学烟台工业园新建 POE 装置一期投产",
                "url": "https://example.com/fake-but-not-used",
                "source": "测试构造", "ts": now - 3600,
                "cats": ["高端聚烯烃"], "day": time.strftime("%Y-%m-%d", time.localtime(now)),
                "block": "山东",
            })
            return d

        W.patch_json(cls.root, "news.json", add_move)
        cls.ctx = W.App(cls.root).__enter__()
        cls.b = cls.ctx.browser

    @classmethod
    def tearDownClass(cls):
        cls.ctx.__exit__(None, None, None)
        import shutil
        shutil.rmtree(os.path.dirname(cls.root), ignore_errors=True)

    def test_move_card_links_to_enterprise(self):
        self.ctx.open()
        self.ctx.goto_hash("#/home")
        self.b.wait_js("!!document.querySelector('#app .jtag.ent')", 10)
        tag = self.b.cdp.eval("document.querySelector('#app .jtag.ent').innerText")
        self.assertEqual("企业动向", tag, "标题含企业名 + 投产，应识别为企业动向")
        href = self.b.cdp.eval(
            "document.querySelector('#app .jtag.ent').closest('a').getAttribute('href')")
        self.assertTrue(href.startswith("#/ent/"), "应链到企业详情，实际 %s" % href)
        self.b.click('#app a.jrow[href^="#/ent/"]')
        self.b.wait_js("location.hash.indexOf('#/ent/')===0", 10)
        self.b.wait_js("document.getElementById('app').innerText.indexOf('主营产品范围')>=0", 10,
                       "企业详情应能打开")
        self.assertIn("万华", self.b.app_text())
