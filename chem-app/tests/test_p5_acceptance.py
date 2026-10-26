# -*- coding: utf-8 -*-
"""P5-5 · A1–A26 全量回归

一张表对应 PRD 第 5 章的验收条目。除了 A20 的「真机安装」必须你拿手机点
（这里只能验它的技术前提），其余全部自动跑。

A1–A15 / A17 / A21–A26：一个浏览器会话串起来跑（省启动时间）
A16 断网 / A19 坏文件：需要独立环境，单独两个类
"""
import json
import os
import shutil
import sys
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import webrunner as W  # noqa: E402


def load(name):
    with open(os.path.join(ROOT, "data", name), encoding="utf-8") as f:
        return json.load(f)


class A01_15(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ctx = W.App().__enter__()
        cls.b = cls.ctx.browser

    @classmethod
    def tearDownClass(cls):
        cls.ctx.__exit__(None, None, None)

    def go(self, h):
        self.ctx.goto_hash(h)
        return self.b

    # ---------------- A1 首屏（地图页）3 秒 ----------------
    def test_A1_home_within_3s(self):
        self.ctx.open()          # 先把浏览器和服务叫醒，重开一次才是冷页面计时
        t0 = time.time()
        self.ctx.open()
        dt = (time.time() - t0) * 1000
        self.assertLess(dt, 3000, "首屏 %.0fms，超过 3 秒" % dt)
        head = self.b.cdp.eval("document.querySelector('header').innerText") or ""
        self.assertIn("更新", head, "顶栏要写出数据是哪天的：%r" % head)

    # ---------------- A2 五个标签 ----------------
    def test_A2_five_tabs(self):
        self.ctx.open()
        n = self.b.count("#tabbar .tab, .tabbar .tab, nav .tab")
        self.assertEqual(5, n, "底部标签数应为 5，实际 %d" % n)
        seen = []
        for i in range(n):
            self.b.click(".tab", i)
            time.sleep(0.25)
            h = self.b.hash()
            self.assertTrue(h.startswith("#/"), "第 %d 个标签没跳转" % (i + 1))
            txt = self.b.app_text()
            self.assertGreater(len(txt), 20, "第 %d 个标签（%s）是空页" % (i + 1, h))
            seen.append(h)
        self.assertEqual(n, len(set(seen)), "有标签跳到了同一个页面：%r" % (seen,))

    # ---------------- A3 地图页可点进详情 ----------------
    def test_A3_map_links(self):
        self.ctx.open()
        self.go("#/parks")
        # 地图要有 SVG 和 KPI 统计
        self.assertGreater(self.b.count("#app .sdmap"), 0, "地图页应有山东地图")
        self.assertGreater(self.b.count("#app .kpis .kp"), 0, "地图页应有园区/企业统计")
        # 点地图页的地市列表应进地市详情
        self.b.click('#app a[href^="#/city/"]', 0)
        self.assertTrue(self.b.hash().startswith("#/city/"), "点地市应进地市详情")
        self.b.wait_js("!!document.querySelector('#app .dt')", 10)

    # ---------------- A4 返回回地图 ----------------
    def test_A4_back_to_map(self):
        self.ctx.open()
        self.go("#/parks")
        self.b.click('#app a[href^="#/city/"]', 0)
        self.assertTrue(self.b.hash().startswith("#/city/"))
        self.b.cdp.eval("history.length")   # 确保有历史
        self.b.click("#back")
        time.sleep(0.3)
        self.assertIn(self.b.hash(), ["#/parks", ""], "从详情返回应回到地图，实际 %s" % self.b.hash())

    # ---------------- A5 三板块都有内容 ----------------
    def test_A5_three_blocks(self):
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        import fetch_all as F
        self.ctx.open()
        self.go("#/news")
        self.b.wait_js("document.querySelectorAll('#app .row').length>0", 10, "资讯页应有内容")
        self.assertEqual(3, self.b.count('#app .chip[data-block]'), "资讯应分三个板块")
        d = load("news.json")
        self.assertEqual(3, len(d["blocks"]))
        for blk in d["blocks"]:
            if len(blk["items"]) >= 3:
                continue
            # 门槛不降：源站正常时必须 ≥3 条。只有源站确实不可达
            # （中国化工报整站维护，山东/全球板块的口径源全归零）才豁免，
            # 且必须能在 source_status 里查到故障记录，不能凭空空过去。
            st = d.get("source_status") or {}
            down = [k for k, v in st.items() if (v or {}).get("status") != "ok"]
            self.assertTrue(
                down,
                "%s 板块只有 %d 条，且没有任何源站故障记录" % (blk["name"], len(blk["items"])))
        # 山东板块内的稿件必须真的和山东相关（判定口径与 enrich() 一致：
        # 市名/省属信号词，或标题里出现名录里的山东企业名）
        sd = [b for b in d["blocks"] if b["name"] == "山东"][0]
        keys = F.SD_KEYS or F.sd_enterprise_keys()
        def is_sd(t):
            return F.is_shandong(t) or any(k in t for k in keys)
        wrong = [it["title"][:30] for it in sd["items"] if not is_sd(it["title"])]
        self.assertEqual([], wrong, "山东板块混入了无关稿件")
        # 点每个板块都能出内容
        for i in range(3):
            self.b.click("#app .chip[data-block]", i)
            time.sleep(0.25)
            self.assertGreater(self.b.count("#app .row"), 0, "第 %d 个板块是空的" % (i + 1))

    # ---------------- A6 资讯搜索 ----------------
    def test_A6_news_search(self):
        """搜一个品类/材料关键词能出结果。关键词从当天真实标题里取，不写死"""
        titles = [i["title"] for b in load("news.json")["blocks"] for i in b["items"]]
        kw = None
        for cand in ["甲醇", "乙烯", "树脂", "新材料", "聚氨酯", "轮胎", "化工"]:
            if any(cand in t for t in titles):
                kw = cand
                break
        self.assertTrue(kw, "当天资讯里一个品类词都没有，先看采集")
        self.ctx.open()
        self.go("#/news")
        self.b.type_into("#q", kw)
        self.b.wait_js("document.querySelectorAll('#app .row').length>0", 10,
                       "搜「%s」应有结果" % kw)
        self.assertIn("搜索结果", self.b.app_text())
        href = self.b.cdp.eval("document.querySelector('#app a.row').getAttribute('href')")
        self.assertTrue(str(href).startswith("http"), "搜索结果要能点开原文")

    def test_A6b_news_search_cross_blocks(self):
        """搜索跨三个板块：当前停在哪个板块都能搜到别处的稿子"""
        titles = [i["title"] for b in load("news.json")["blocks"] for i in b["items"]]
        kw = "化工" if any("化工" in t for t in titles) else titles[0][:4]
        self.ctx.open()
        self.go("#/news")
        self.b.type_into("#q", kw)
        self.b.wait_js("document.querySelectorAll('#app .row').length>0", 10)
        blocks = self.b.cdp.eval(
            "Array.prototype.map.call(document.querySelectorAll('#app .row .tag.cat'),"
            "function(e){return e.innerText}).join(',')")
        self.assertTrue(blocks, "搜索结果要标出这条属于哪个板块")

    # ---------------- A7 跨板块去重 ----------------
    def test_A7_no_duplicate_across_blocks(self):
        d = load("news.json")
        self.assertIn("dedup_dropped", d, "缺少去重留痕字段")
        titles = {}
        for blk in d["blocks"]:
            for it in blk["items"]:
                t = it["title"].strip()
                self.assertNotIn(t, titles, "同一标题在两处出现：%s（%s / %s）"
                                 % (t[:30], titles.get(t), blk["name"]))
                titles[t] = blk["name"]
                if it.get("dup_of"):
                    self.fail("还留在页面上的条目不应带 dup_of：%s" % t[:30])

    # ---------------- A8 淄博页数字 ----------------
    def test_A8_zibo_numbers(self):
        d = load("parks.json")
        zb = [c for c in d["cities"] if c["name"] == "淄博"][0]
        ents = sum(len(p.get("enterprises") or []) for p in zb["parks"]) + \
            len(zb.get("enterprises") or [])
        high = sum(1 for p in zb["parks"] for e in (p.get("enterprises") or []) if e.get("high")) + \
            sum(1 for e in (zb.get("enterprises") or []) if e.get("high"))
        self.ctx.open()
        self.go("#/city/" + zb["code"])
        txt = self.b.app_text()
        self.assertIn("化工园区", txt)
        # 问题2 已把园区从 32 家扩充到官方 84 家，淄博现为 6 家（官方名单），
        # 这里不再写死数量，只验证有园区且页面数字与实际数据一致。
        self.assertGreater(len(zb["parks"]), 0, "淄博应有化工园区")
        self.assertIn("淄博", txt)
        # 页面上的企业总数与实际数据一致（数字不能对不上）
        self.assertIn(str(ents), txt, "淄博企业数 %d 未出现在页面上" % ents)
        self.assertIn(str(high), txt, "淄博高端企业数 %d 未出现在页面上" % high)
        # 点园区能进园内企业，点企业能进企业详情
        self.assertGreater(self.b.count('#app a[href^="#/park/"]'), 0)
        self.b.click('#app a[href^="#/park/"]', 0)
        self.assertTrue(self.b.hash().startswith("#/park/"))
        self.assertGreater(self.b.count('#app a[href^="#/ent/"]'), 0, "园区页应有企业可点")

    # ---------------- A9 企业详情 ----------------
    def _ent_with_news(self):
        """挑一家今天真匹配到资讯的企业：动态是自动匹配的，挑不到就得去补数据，不能造假"""
        titles = [i["title"] for b in load("news.json")["blocks"] for i in b["items"]]
        for c in load("parks.json")["cities"]:
            for p in c["parks"]:
                for i, e in enumerate(p["enterprises"]):
                    keys = e.get("match") or [e["name"]]
                    if any(any(k in t for t in titles) for k in keys):
                        return p["id"], i, e["name"]
        return None

    def test_A9_ent_detail(self):
        tgt = self._ent_with_news()
        self.assertTrue(tgt, "今天没有任何企业匹配到资讯，A9 无从验证，先看采集")
        pid, idx, name = tgt
        self.ctx.open()
        self.go("#/ent/%s/%d" % (pid, idx))
        self.b.wait_js("document.getElementById('app').innerText.indexOf('企业动态')>=0", 10)
        txt = self.b.app_text()
        self.assertIn(name, txt)
        self.assertIn("主营产品范围", txt)
        self.assertIn("所属品类", txt)
        self.assertGreater(self.b.count('#app a[target="_blank"]'), 0,
                           "%s 应有可点开的动态" % name)
        href = self.b.cdp.eval("document.querySelector('#app a[target=\"_blank\"]')"
                              ".getAttribute('href')")
        self.assertTrue(str(href).startswith("http"))

    def test_A9_coverage_is_reported_honestly(self):
        """企业动态靠资讯标题匹配，覆盖率做不到 100%，页面必须明说「暂无收录」而不是空白"""
        titles = [i["title"] for b in load("news.json")["blocks"] for i in b["items"]]
        ents = [(p["id"], i, e) for c in load("parks.json")["cities"]
                for p in c["parks"] for i, e in enumerate(p["enterprises"])]
        with_news = [x for x in ents
                     if any(any(k in t for t in titles) for k in (x[2].get("match") or [x[2]["name"]]))]
        self.assertGreater(len(with_news), 0, "一条都没匹配上，匹配规则坏了")
        # 挑一个没匹配到的，页面要给「暂无收录」
        pid, idx, e = [x for x in ents if x not in with_news][0]
        self.ctx.open()
        self.go("#/ent/%s/%d" % (pid, idx))
        self.assertIn("暂无收录", self.b.app_text(),
                      "没匹配到动态时要明说，不能留空白")

    # ---------------- A10 品类数与六问 ----------------
    def test_A10_cats_count_and_fields(self):
        self.ctx.open()
        self.go("#/cats")
        d = load("categories.json")
        self.assertEqual(73, len(d["items"]), "PRD 口径是 73 个品类")
        self.assertIn("73", self.b.app_text())
        for cid in ["pp", "soda", "tire"]:
            self.go("#/cat/" + cid)
            n = self.b.count("#app .field")
            self.assertGreaterEqual(n, 6, "%s 只有 %d 个字段" % (cid, n))
            self.assertIn("山东的位置", self.b.app_text())

    # ---------------- A11 头部企业可点 ----------------
    def test_A11_leaders_clickable_or_marked(self):
        self.ctx.open()
        for cid in ["soda", "pp", "chloralkali"]:
            self.go("#/cat/" + cid)
            dead = self.b.count('#app a[href="javascript:void(0)"]')
            self.assertEqual(0, dead, "%s 头部企业有死链" % cid)
            clickable = self.b.count('#app a[href^="#/ent/"]')
            marked = self.b.count('#app .leader.off')
            self.assertGreater(clickable + marked, 0, "%s 头部企业既不可点也没标注" % cid)

    # ---------------- A12 红涨绿跌 ----------------
    def test_A12_red_up_green_down(self):
        self.ctx.open()
        self.go("#/prices")
        got = self.b.cdp.eval("""(function(){
          var u=document.querySelector('#app .up'), d=document.querySelector('#app .down');
          function rgb(e){ if(!e) return null; var c=getComputedStyle(e).color.match(/\\d+/g);
            return c ? [ +c[0], +c[1], +c[2] ] : null; }
          return {up:rgb(u), down:rgb(d)};
        })()""")
        if got["up"]:
            r, g, b = got["up"]
            self.assertTrue(r > g and r > b, "上涨应为红色，实际 rgb(%d,%d,%d)" % (r, g, b))
        if got["down"]:
            r, g, b = got["down"]
            self.assertTrue(g > r, "下跌应为绿色，实际 rgb(%d,%d,%d)" % (r, g, b))
        self.assertTrue(got["up"] or got["down"], "行情页应有涨跌着色")

    # ---------------- A13 K 线切换 ----------------
    def test_A13_kline_periods(self):
        self.ctx.open()
        self.go("#/price/" + "甲醇")
        self.b.wait_js("!!document.getElementById('kline')", 10)
        before = self.b.cdp.eval("document.getElementById('klabel').innerText")
        self.b.click('#periods button[data-d="90"]')
        time.sleep(0.3)
        after = self.b.cdp.eval("document.getElementById('klabel').innerText")
        self.assertNotEqual(before, after, "切 90 天后标签应变化")
        self.assertIn("90", after)
        w = self.b.cdp.eval("document.getElementById('kline').width")
        self.assertGreater(w, 0, "K 线画布不该是空的")
        self.b.click('#periods button[data-d="250"]')
        time.sleep(0.3)
        self.assertIn("250", self.b.cdp.eval("document.getElementById('klabel').innerText"))
        # 250 天不能是空图：canvas 上应该真的画了东西
        painted = self.b.cdp.eval("""(function(){
          var c=document.getElementById('kline');
          var ctx=c.getContext('2d');
          var d=ctx.getImageData(0,0,c.width,c.height).data;
          for(var i=3;i<d.length;i+=4){ if(d[i]!==0) return true; }
          return false;
        })()""")
        self.assertTrue(painted, "K 线画布是空白的")

    # ---------------- A14 关联新闻 ----------------
    def test_A14_price_news(self):
        p = load("prices.json")
        name = None
        for g in p["groups"]:
            for it in g["items"]:
                if it.get("news"):
                    name = it["name"]
                    break
            if name:
                break
        self.assertTrue(name, "至少应有一个品种带关联新闻")
        self.ctx.open()
        self.go("#/price/" + name)
        self.assertIn("相关新闻", self.b.app_text())
        self.assertGreater(self.b.count('#app a[target="_blank"]'), 0, "关联新闻要能点开")

    # ---------------- A15 政策两栏 ----------------
    def test_A15_policies_two_levels(self):
        self.ctx.open()
        self.go("#/policies")
        self.assertEqual(2, self.b.count('#app .chip[data-lv]'), "政策分两级")
        d = load("policies.json")["items"]
        for lv in ["国家级", "山东省"]:
            self.assertGreaterEqual(sum(1 for x in d if x["level"] == lv), 3, "%s 太少" % lv)
        for x in d:
            self.assertTrue(x.get("org") and x.get("ts"), "政策缺机关或日期：%s" % x["title"][:20])
            self.assertTrue(str(x.get("url", "")).startswith("http"), "政策缺原文链接")
        self.b.click('#app a[href^="#/policy/"]', 0)
        self.assertGreater(self.b.count('#app a[href^="http"]'), 0, "详情要能打开原文")

    # ---------------- A17 导出 ----------------
    def test_A17_export(self):
        self.ctx.open()
        self.go("#/me")
        self.b.wait_js("!!document.getElementById('exp')", 10)
        self.b.click("#exp")
        self.b.wait_js("!!window.__lastExport", 10)
        o = json.loads(self.b.cdp.eval("window.__lastExport"))
        for k in ["learned", "read", "fav"]:
            self.assertIn(k, o)

    # ---------------- A21 搜「万华」 ----------------
    def test_A21_search_wenhua(self):
        self.ctx.open()
        self.go("#/parks")
        self.b.type_into("#mq", "万华")
        self.b.wait_js("document.querySelectorAll('#mres a.row').length>0", 10, "应有结果")
        first = self.b.cdp.eval("document.querySelector('#mres a.row').innerText")
        self.assertIn("万华", first, "首条应是万华相关，实际 %r" % first[:30])
        self.b.click("#mres a.row", 0)
        self.assertTrue(self.b.hash().startswith("#/ent/"), "点结果应进企业页")

    # ---------------- A22 搜「东营」 ----------------
    def test_A22_search_dongying(self):
        self.ctx.open()
        self.go("#/parks")
        self.b.type_into("#mq", "东营")
        self.b.wait_js("document.querySelectorAll('#mres a.row').length>0", 10)
        first = self.b.cdp.eval(
            "document.querySelector('#mres a.row').getAttribute('href')")
        self.assertTrue(first.startswith("#/city/"), "首条应是地市，实际 %s" % first)
        self.assertIn("东营", self.b.cdp.eval("document.querySelector('#mres a.row').innerText"))

    # ---------------- A23 搜「轮胎」 ----------------
    def test_A23_search_tire(self):
        self.ctx.open()
        self.go("#/parks")
        self.b.type_into("#mq", "轮胎")
        self.b.wait_js("document.querySelectorAll('#mres a.row').length>0", 10)
        first = self.b.cdp.eval(
            "document.querySelector('#mres a.row').innerText")
        self.assertIn("轮胎", first, "首条应是名称含「轮胎」的企业，实际 %r" % first[:30])
        self.assertTrue(self.b.cdp.eval(
            "document.querySelector('#mres a.row').getAttribute('href')").startswith("#/ent/"))

    # ---------------- A24 地市页五块 ----------------
    def test_A24_city_five_blocks(self):
        self.ctx.open()
        self.go("#/city/370500")
        txt = self.b.app_text()
        for k in ["产业概况", "产业集群", "本地重点品种", "化工园区"]:
            self.assertIn(k, txt, "地市页缺「%s」" % k)
        self.assertIn("万吨", txt, "体量定位没显示")
        self.assertGreater(self.b.count('#app .angle'), 0, "缺撮合判断要点")

    # ---------------- A25 品种标签跳转 ----------------
    def test_A25_chem_tag_jump(self):
        self.ctx.open()
        self.go("#/city/370300")
        self.assertGreater(self.b.count('#app .pill.tap'), 0, "地市页应有品种标签")
        kw = self.b.cdp.eval("document.querySelector('#app .pill.tap').dataset.f")
        self.b.click("#app .pill.tap", 0)
        time.sleep(0.4)
        self.assertTrue(self.b.hash().startswith("#/parks"), "应跳到地图页")
        self.assertEqual(kw, self.b.cdp.eval("document.getElementById('mq').value"),
                         "搜索框应自动带上品种名")
        self.b.wait_js("document.querySelectorAll('#mres a.row').length>0", 10,
                       "应搜出该品种相关企业")

    # ---------------- A26 品类页搜索 ----------------
    def test_A26_cats_search(self):
        self.ctx.open()
        self.go("#/cats")
        self.b.type_into("#cq", "纯碱")
        self.b.wait_js("document.querySelectorAll('#app a[href^=\"#/cat/\"]').length>0", 10,
                       "品类页应能搜到纯碱")
        self.b.click('#app a[href^="#/cat/"]', 0)
        self.assertTrue(self.b.hash().startswith("#/cat/"))
        self.assertIn("山东的位置", self.b.app_text())
        self.assertGreaterEqual(self.b.count("#app .field"), 6)


class A16_Offline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ctx = W.App().__enter__()
        cls.b = cls.ctx.browser

    @classmethod
    def tearDownClass(cls):
        cls.ctx.__exit__(None, None, None)

    def test_A16_offline_shows_last_data(self):
        b = self.ctx.open()
        b.wait_js("!!navigator.serviceWorker.controller", 20, "SW 要先接管")
        b.offline(True)
        try:
            b.cdp.eval("location.reload()")
            time.sleep(1.0)
            b.wait_ready(20)
            b.wait_js("!!document.querySelector('#app .sdmap')", 25, "断网仍要能看到上次内容（地图）")
            b.wait_js("document.getElementById('netbar')&&!document.getElementById('netbar').hidden",
                      15, "必须明确显示离线")
            txt = b.cdp.eval("document.getElementById('netbar').innerText")
            self.assertIn("离线", txt)
            self.assertIn("显示", txt)
        finally:
            b.offline(False)
            b.cdp.eval("location.reload()")
            time.sleep(0.5)
            b.wait_ready(20)


class A19_BrokenFile(unittest.TestCase):
    """把某个数据文件改坏：只影响该模块，其余照常，坏的那个要给提示"""

    @classmethod
    def setUpClass(cls):
        cls.root = W.copy_app()
        for n in ["prices.json", "prices_history.json"]:
            with open(os.path.join(cls.root, "data", n), "w", encoding="utf-8") as f:
                f.write("{ 这不是 json")
        cls.ctx = W.App(cls.root).__enter__()
        cls.b = cls.ctx.browser

    @classmethod
    def tearDownClass(cls):
        cls.ctx.__exit__(None, None, None)
        shutil.rmtree(os.path.dirname(cls.root), ignore_errors=True)

    def test_A19_other_modules_still_work(self):
        self.ctx.open()
        self.ctx.goto_hash("#/parks")
        self.b.wait_js("!!document.querySelector('#app .sdmap')", 15,
                       "行情坏了地图仍应正常")
        self.ctx.goto_hash("#/cats")
        self.b.wait_js("document.querySelectorAll('#app a[href^=\"#/cat/\"]').length>0", 10,
                       "品类模块不受行情影响")

    def test_A19_broken_module_shows_message(self):
        self.ctx.open()
        self.ctx.goto_hash("#/prices")
        self.b.wait_js("document.getElementById('app').innerText.indexOf('未加载')>=0",
                       10, "行情坏了要明说，不能白屏")


if __name__ == "__main__":
    unittest.main(verbosity=2)
