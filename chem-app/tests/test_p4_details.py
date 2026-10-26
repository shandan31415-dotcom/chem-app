# -*- coding: utf-8 -*-
"""P4 细节补齐 · 验收测试

对应 G3（头部企业点不到）、G11（政策无搜索）、G12（动态不灰化）、
G13（58 个品类没有行情入口）、G16（液氯只有 1 家头部）。
"""
import json
import os
import sys
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import qa  # noqa: E402
import webrunner as W  # noqa: E402


def load(name):
    with open(os.path.join(ROOT, "data", name), encoding="utf-8") as f:
        return json.load(f)


class TestDataLevel(unittest.TestCase):
    """数据层断言：不依赖浏览器，跑得快，失败了也最容易定位"""

    def test_price_link_coverage_ge_25(self):
        """G13：至少 25/73 个品类有「相关行情」入口"""
        items = load("categories.json")["items"]
        linked = [it for it in items if it.get("price_links")]
        self.assertGreaterEqual(len(linked), 25,
                                "有行情入口的品类 %d/73，应 ≥25" % len(linked))

    def test_price_link_names_exist(self):
        """链接指向的品种必须真在行情里，不能造出不存在的品种"""
        items = load("categories.json")["items"]
        prices = load("prices.json")
        names = {p["name"] for g in prices["groups"] for p in g["items"]}
        bad = []
        for it in items:
            for n in it.get("price_links") or []:
                if n not in names:
                    bad.append("%s -> %s" % (it["id"], n))
        self.assertEqual([], bad, "品类行情链接指向了不存在的品种")

    def test_no_wrong_price_link(self):
        """几个已知易错的映射关系必须没被自动推导错配"""
        by_id = {it["id"]: it for it in load("categories.json")["items"]}
        # 煤沥青/针状焦 不能被当成「沥青」期货
        self.assertNotIn("沥青", by_id["coke"].get("price_links") or [],
                         "焦化品类错配了沥青期货")
        # PEEK 里的 "PE" 不能被当成聚乙烯
        self.assertNotIn("聚乙烯", by_id["peek"].get("price_links") or [],
                         "PEEK 被 PE 误配成聚乙烯")
        # PPS / EPS 里的 "PS" 不能被当成聚苯乙烯
        self.assertNotIn("聚苯乙烯", by_id["engplastic"].get("price_links") or [],
                         "工程塑料被 PPS 的 PS 误配成聚苯乙烯")

    def test_cl2_has_three_real_leaders(self):
        """G16：液氯头部企业 ≥3 家，且不能是「自产自用」这种说明句"""
        by_id = {it["id"]: it for it in load("categories.json")["items"]}
        ls = by_id["cl2"].get("leaders") or []
        self.assertGreaterEqual(len(ls), 3, "液氯头部企业 %d 家" % len(ls))
        for l in ls:
            self.assertNotIn("自产自用", l["name"], "头部企业不能填说明性文字")

    def test_qa_all_green(self):
        """qa 不允许有真失败；XFAIL 只接受「上游源站故障」这一种原因

        历史上这条断言是「必须全 PASS」。豁免 XFAIL 的原因很具体：中国化工报
        （中化新网 ccin.com.cn）整站维护时，山东本地企业栏目与全球国际频道
        直接归零，a8 会据实标 XFAIL。这不是抓取规则坏了，也不是数据质量问题，
        但硬要求全 PASS 会让测试天天红，真正的回归故障反而被噪音淹没。

        所以标准没有放宽：FAIL 一条都不许有；XFAIL 必须在说明里写明源站
        不可达，否则照旧算失败。
        """
        rows = qa.run_all()
        fails = [(r[0], r[2]) for r in rows if r[1] == "FAIL"]
        self.assertEqual([], fails, "qa 存在真失败：%r" % (fails,))
        for name, st, detail in rows:
            if st != "XFAIL":
                continue
            self.assertIn("源站", detail,
                          "XFAIL 只能用于上游源站故障，%s 的理由不成立：%s" % (name, detail))


class TestPolicySearch(unittest.TestCase):
    """G11：政策页要能搜"""

    @classmethod
    def setUpClass(cls):
        cls.ctx = W.App().__enter__()
        cls.b = cls.ctx.browser

    @classmethod
    def tearDownClass(cls):
        cls.ctx.__exit__(None, None, None)

    def open_policies(self):
        self.ctx.open()
        self.ctx.goto_hash("#/policies")
        self.b.wait_js("!!document.getElementById('q')", 10, "政策页应有搜索框")

    def test_search_hits_and_can_open(self):
        """搜「环保」有结果，并且能点进详情"""
        self.open_policies()
        self.b.type_into("#q", "环保")
        self.b.wait_js("document.querySelectorAll('#app a[href^=\"#/policy/\"]').length>0",
                       10, "搜「环保」应有政策结果")
        self.assertIn("搜索结果", self.b.app_text(), "要说明这是搜索结果")
        n = self.b.count('#app a[href^="#/policy/"]')
        self.assertGreater(n, 0)
        h = self.b.click_and_wait_hash('#app a[href^="#/policy/"]', "#/policy/")
        self.assertTrue(h.startswith("#/policy/"))

    def test_search_by_org(self):
        """按发文机关也能搜到"""
        self.open_policies()
        self.b.type_into("#q", "生态环境部")
        self.b.wait_js("document.querySelectorAll('#app a[href^=\"#/policy/\"]').length>=2",
                       10, "按机关应能搜到多条")
        txt = self.b.app_text()
        self.assertIn("生态环境部", txt)

    def test_search_no_result_message(self):
        """搜不到要说「没有匹配」，不能给个空白页"""
        self.open_policies()
        self.b.type_into("#q", "这个词一定搜不到zzz")
        self.b.wait_js("document.querySelectorAll('#app a[href^=\"#/policy/\"]').length===0",
                       10, "不该有结果")
        self.assertIn("没有匹配", self.b.app_text())

    def test_clear_search_restores_levels(self):
        """清空搜索后回到「国家级/山东省」两级列表"""
        self.open_policies()
        self.b.type_into("#q", "环保")
        self.b.wait_js("document.querySelectorAll('#app a[href^=\"#/policy/\"]').length>0", 10)
        self.b.type_into("#q", "")
        self.b.wait_js("document.querySelectorAll('#app .chip[data-lv]').length===2",
                       10, "清空后应回到分级视图")

    def test_detail_shows_impact(self):
        """详情页要把「对撮合的影响」写出来，而不是只有原文链接"""
        self.open_policies()
        first = self.b.cdp.eval(
            "document.querySelector('#app a[href^=\"#/policy/\"]').getAttribute('href')")
        self.ctx.goto_hash(first)
        self.b.wait_js("document.getElementById('app').innerText.indexOf('影响')>=0",
                       10, "政策详情应含影响判断")


class TestCatLeader(unittest.TestCase):
    """G3：头部企业点不到的问题"""

    @classmethod
    def setUpClass(cls):
        cls.ctx = W.App().__enter__()
        cls.b = cls.ctx.browser

    @classmethod
    def tearDownClass(cls):
        cls.ctx.__exit__(None, None, None)

    def open_cat(self, cid):
        self.ctx.open()
        self.ctx.goto_hash("#/cat/" + cid)
        self.b.wait_js("!!document.querySelector('#app .dt')", 10)

    def test_no_dead_leaders(self):
        """A11：页面里不允许出现「点了没反应」的链接"""
        self.open_cat("chloralkali")
        dead = self.b.count('#app a[href="javascript:void(0)"]') + \
            self.b.count('#app a[href="#"]')
        self.assertEqual(0, dead, "头部企业仍有死链")

    def test_off_province_leaders_are_marked(self):
        """省外/国外企业要明确标注，且整行不可点（只留「查山东据点」一个入口）"""
        self.open_cat("chloralkali")
        n_off = self.b.count('#app .leader.off')
        self.assertGreater(n_off, 0, "烧碱头部企业里有省外公司，应被标注")
        txt = self.b.cdp.eval(
            "Array.prototype.map.call(document.querySelectorAll('#app .leader.off'),"
            "function(e){return e.innerText}).join('|')")
        self.assertTrue(("省外" in txt) or ("国外" in txt), "标注要写清省外还是国外")
        bad = self.b.cdp.eval("""(function(){
          var rows=document.querySelectorAll('#app .row'), bad=[];
          for(var i=0;i<rows.length;i++){
            var r=rows[i];
            if(!r.querySelector('.leader.off')) continue;
            var as=r.querySelectorAll('a');
            if(as.length!==1 || String(as[0].getAttribute('href')).indexOf('#/parks/')!==0)
              bad.push(r.innerText.slice(0,20));
          }
          return bad;
        })()""")
        self.assertEqual([], bad, "省外企业那一行只能有「查山东据点」一个链接，主体不能整行可点")

    def test_off_province_has_shandong_lookup(self):
        """每个省外企业都给一个「查山东据点」入口，点了真的能查"""
        self.open_cat("chloralkali")
        self.assertGreater(self.b.count('#app .row a.lk[href^="#/parks/"]'), 0,
                           "省外企业应带查山东据点链接")
        h = self.b.click_and_wait_hash('#app .row a.lk[href^="#/parks/"]', "#/parks/")
        self.assertTrue(h.startswith("#/parks/"))
        self.b.wait_js("!!document.getElementById('mq')", 10, "应落到园区搜索页")
        q = self.b.cdp.eval("document.getElementById('mq').value")
        self.assertTrue(q, "搜索框要自动带上企业名")

    def test_in_province_leader_still_clickable(self):
        """山东本地企业仍然可以直接点进详情"""
        self.open_cat("soda")
        self.assertGreater(self.b.count('#app a[href^="#/ent/"]'), 0,
                           "本地头部企业应保持可点")

    def test_cat_without_price_link_says_so(self):
        """没有对应期货品种的品类，要诚实说一句，而不是留个空板块"""
        self.open_cat("aramid")
        txt = self.b.app_text()
        self.assertIn("暂无对应期货品种", txt)

    def test_derived_price_link_is_clickable(self):
        """自动推导出来的行情入口，点了要能进行情详情"""
        self.open_cat("px")
        self.assertGreater(self.b.count('#app a[href^="#/price/"]'), 0,
                           "对二甲苯品类应有行情入口")
        h = self.b.click_and_wait_hash('#app a[href^="#/price/"]', "#/price/")
        self.assertTrue(h.startswith("#/price/"))
        self.b.wait_js("!!document.getElementById('kline')", 10, "行情详情应有 K 线")


class TestEntNewsAge(unittest.TestCase):
    """G12：企业动态超过 3 个月要灰掉（不删，只降权）"""

    @classmethod
    def setUpClass(cls):
        cls.root = W.copy_app()
        news = os.path.join(cls.root, "data", "news.json")
        with open(news, encoding="utf-8") as f:
            d = json.load(f)
        now = int(time.time())
        mk = lambda t, ts: {
            "title": "万华化学 " + t, "url": "https://example.com/" + t,
            "summary": "", "ts": ts, "source": "灰化测试源",
            "cats": [], "day": "", "block": "山东",
        }
        blk = d["blocks"][0]
        blk["items"].insert(0, mk("灰化测试旧稿", now - 100 * 86400))
        blk["items"].insert(0, mk("灰化测试新稿", now - 2 * 86400))
        with open(news, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False)
        cls.ctx = W.App(cls.root).__enter__()
        cls.b = cls.ctx.browser

    @classmethod
    def tearDownClass(cls):
        cls.ctx.__exit__(None, None, None)
        import shutil
        shutil.rmtree(os.path.dirname(cls.root), ignore_errors=True)

    def _open_wenhua(self):
        # 万华化学在 parks.json 里的位置
        d = load("parks.json")
        for c in d["cities"]:
            for p in c["parks"]:
                for i, e in enumerate(p["enterprises"]):
                    if e["name"] == "万华化学":
                        self.ctx.open()
                        self.ctx.goto_hash("#/ent/%s/%d" % (p["id"], i))
                        self.b.wait_js("document.getElementById('app').innerText"
                                       ".indexOf('企业动态')>=0", 10)
                        return
        self.fail("parks.json 里找不到万华化学")

    def test_old_news_greyed_new_not(self):
        self._open_wenhua()
        old_n = self.b.cdp.eval(
            "Array.prototype.filter.call(document.querySelectorAll('#app .row'),"
            "function(r){return r.innerText.indexOf('灰化测试旧稿')>=0 && "
            "r.querySelector('.old')}).length")
        new_n = self.b.cdp.eval(
            "Array.prototype.filter.call(document.querySelectorAll('#app .row'),"
            "function(r){return r.innerText.indexOf('灰化测试新稿')>=0 && "
            "r.querySelector('.old')}).length")
        self.assertEqual(1, old_n, "100 天前那条的日期应该是灰的")
        self.assertEqual(0, new_n, "两天前那条不该灰")

    def test_old_news_not_removed(self):
        """灰化只是降权，不能把老动态删掉"""
        self._open_wenhua()
        self.assertIn("灰化测试旧稿", self.b.app_text())

    def test_new_news_sorted_first(self):
        """排序仍是最新在前"""
        self._open_wenhua()
        first = self.b.cdp.eval(
            "(function(){var rs=document.querySelectorAll('#app .row');"
            "for(var i=0;i<rs.length;i++){var t=rs[i].innerText;"
            "if(t.indexOf('灰化测试')>=0)return t;}return '';})()")
        self.assertIn("新稿", first, "更新的动态应排在前面")


if __name__ == "__main__":
    unittest.main(verbosity=2)
