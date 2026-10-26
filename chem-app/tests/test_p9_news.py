# -*- coding: utf-8 -*-
"""问题9 · 资讯不是最新的 —— 专项测试

现象：手机端打开资讯模块，内容停留在几天前，且条数很少（全球 0 条）。
根因不止一个，全部都是真实存在的：

  1. 主源中国化工报（中化新网 ccin.com.cn）整站「系统维护升级中」，
     中国化工报、国际化工、山东三家企业的栏目全部归零；
  2. 垂类源被「化工 + 高端」双关键词卡死：化工信息周刊 27 条只过 1 条、
     隆众 61 条几乎全丢，因为标题写的是品种名（苯酚、丁二烯、粗苯），
     不含「化工」二字；
  3. 省名「山东省」被当成化工主体信号，政务稿（无线电演练、省委会议）
     会冒充化工资讯。

本测试守的规矩：
  - 垂类源只排非化工品种，不再要求标题出现「化工」
  - 政务源走严格词表，不许把政务活动当行业资讯
  - 每板块不少于 3 条；不足时必须是源站故障且写明原因，不能静默通过
  - 最新一条必须是近期稿，不能拿旧稿顶版面
"""
import json
import os
import re
import sys
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SCRIPTS = os.path.join(ROOT, "scripts")
sys.path.insert(0, SCRIPTS)

import fetch_all as F  # noqa: E402

NEWS = os.path.join(ROOT, "data", "news.json")


def load_news():
    with open(NEWS, encoding="utf-8") as f:
        return json.load(f)


def mk(title, **kw):
    """构造一条原始稿件，用来走 enrich 的过滤链"""
    d = {"title": title, "url": "http://example.com/x", "summary": "",
         "ts": int(time.time()), "source": "测试源"}
    d.update(kw)
    return d


class TestVerticalSourceRelaxed(unittest.TestCase):
    """垂类源：品种名标题必须能进，非化工品种必须挡"""

    def test_bulk_chem_words_defined(self):
        """大宗基础品种词表要覆盖行情稿天天写的那些品种"""
        for w in ["苯酚", "丁二烯", "粗苯", "醋酸乙酯", "烧碱"]:
            self.assertIn(w, F.BULK_CHEM, "大宗品种词表缺 %s" % w)

    def test_wide_keywords_cover_categories(self):
        """宽词库要能吃进品类库的品类名，不能只靠手写清单"""
        kw = F.chem_keywords_wide()
        self.assertGreater(len(kw), 200, "宽词库过小，品类库没被吃进来：%d" % len(kw))
        self.assertIn("聚氨酯", kw)

    def test_product_title_passes(self):
        """「苯酚市场早间提示」不含「化工」二字，但必须判为化工稿"""
        out = F.enrich([mk("苯酚市场早间提示（20261026）", _vertical=True)])
        self.assertEqual(len(out), 1, "垂类源的品种行情稿被误杀，资讯量就是这样掉没的")

    def test_off_topic_rejected(self):
        """垂类源首页混着鸡蛋、钢铁，必须挡掉"""
        for t in ["江西九江德安地区褐壳鸡蛋市场价格上涨（20261026）",
                  "前三季度粗钢产量降2.9%"]:
            out = F.enrich([mk(t, _vertical=True)])
            self.assertEqual(out, [], "非化工品种混进了资讯：%s" % t)

    def test_off_topic_words_defined(self):
        for w in ["鸡蛋", "钢铁", "生猪"]:
            self.assertIn(w, F.OFF_TOPIC)


class TestGovSourceStrict(unittest.TestCase):
    """政务源：只认明确的行业词，政务活动不许冒充行业资讯"""

    def test_gov_sources_registered(self):
        self.assertIn("山东省工信厅", F.GOV_SOURCES)

    def test_strict_keywords_defined(self):
        for w in ["化工", "石化", "化学", "新材料"]:
            self.assertIn(w, F.KW_CHEM_STRICT)

    def test_gov_rejects_non_chem(self):
        """无线电演练、纺织产业活动不是化工资讯"""
        for t in ["2026年山东省无线电监测技术和行政执法演练在潍坊临朐举办",
                  "山东省2026年现代轻工纺织产业链科技创新和产业创新融合成果对接活动成功举办"]:
            out = F.enrich([mk(t, _gov=True)])
            self.assertEqual(out, [], "政务稿冒充化工资讯：%s" % t)

    def test_gov_accepts_chem(self):
        """真正沾化工的政务稿要留下"""
        out = F.enrich([mk("山东一企业顺利通过禁止化学武器组织现场视察", _gov=True)])
        self.assertEqual(len(out), 1, "化工相关的政务动态被误杀")

    def test_province_name_not_chem_signal(self):
        """省名不能当化工主体信号——这是政务稿大量混入的根因"""
        self.assertNotIn("山东省", F.SD_BRAND_SIGNALS,
                         "省名进了化工主体信号，所有省政务稿都会被判成化工稿")


class TestSourceHealth(unittest.TestCase):
    """源健康度落盘，qa 才能区分「数据差」和「源站挂」"""

    def setUp(self):
        self.data = load_news()

    def test_source_status_present(self):
        st = self.data.get("source_status")
        self.assertIsInstance(st, dict, "news.json 缺 source_status，qa 无法识别源站故障")
        self.assertGreater(len(st), 0)

    def test_status_values_valid(self):
        for k, v in (self.data.get("source_status") or {}).items():
            self.assertIn(v.get("status"), ("ok", "maintenance", "error"),
                          "源 %s 的状态值非法：%r" % (k, v))
            self.assertIsInstance(v.get("count"), int)

    def test_maintenance_detectable(self):
        """维护页也是 200，必须靠内容判断，不能只看状态码"""
        maint = ("<html><head><title>系统维护升级中 - 中化新网</title></head>"
                 "<body>系统维护升级中</body></html>")
        self.assertTrue(any(k in maint[:5000] for k in ["系统维护", "升级中", "暂停服务"]))


class TestNewsData(unittest.TestCase):
    """落盘数据：结构、鲜度、内容纯度"""

    def setUp(self):
        self.data = load_news()
        self.blocks = {b["name"]: b.get("items") or [] for b in self.data.get("blocks", [])}
        self.all = [it for v in self.blocks.values() for it in v]

    def test_three_blocks(self):
        for k in ["全球", "全国", "山东"]:
            self.assertIn(k, self.blocks, "缺板块 %s" % k)

    def test_blocks_not_empty(self):
        """每个板块都要有内容；不足 3 条必须是源站故障（source_status 有非 ok）"""
        st = self.data.get("source_status") or {}
        down = [k for k, v in st.items() if (v or {}).get("status") != "ok"]
        for k, v in self.blocks.items():
            if len(v) < 3:
                self.assertTrue(down, "板块 %s 只有 %d 条且无源站故障记录" % (k, len(v)))

    def test_total_enough(self):
        """资讯总量要够看，不能只剩个位数"""
        self.assertGreaterEqual(len(self.all), 20, "资讯总量 %d 条，太少" % len(self.all))

    def test_latest_is_fresh(self):
        """最新一条必须是近 3 天的稿，不能拿旧稿顶版面"""
        ts = [it.get("ts") for it in self.all if it.get("ts")]
        self.assertTrue(ts, "所有资讯都没有时间戳")
        newest = max(ts)
        days = (time.time() - newest) / 86400
        self.assertLess(days, 3.0, "最新资讯是 %.1f 天前的，不够新" % days)

    def test_no_stale_over_limit(self):
        """超过 45 天的稿不该留下"""
        old = [it.get("title") for it in self.all
               if it.get("ts") and (time.time() - it["ts"]) / 86400 > F.NEWS_MAX_AGE_DAYS]
        self.assertEqual(old, [], "存在超期旧稿：%s" % old[:3])

    def test_no_offtopic_content(self):
        """落盘数据里不能出现农产品、钢铁、房地产这类非化工内容"""
        bad = []
        for it in self.all:
            t = it.get("title") or ""
            if any(w in t for w in ["鸡蛋", "粗钢", "螺纹钢", "商品住宅", "房地产市场", "生猪"]):
                bad.append(t)
        self.assertEqual(bad, [], "资讯里有非化工内容：%s" % bad[:5])

    def test_has_source_and_url(self):
        for it in self.all:
            self.assertTrue(it.get("source"), "条目缺来源：%s" % it.get("title"))
            self.assertRegex(it.get("url") or "", r"^https?://", "条目缺有效链接")


class TestParsers(unittest.TestCase):
    """新增源解析：不联网，用固定片段验格式"""

    def test_parse_sci99(self):
        html = '<a href="/info/3_1000001_45848408.html">苯酚市场早间提示（20261026）</a>'
        out = F.parse_sci99(html)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["url"], "https://www.sci99.com/info/3_1000001_45848408.html")
        self.assertEqual(out[0]["source"], "卓创资讯")
        self.assertTrue(out[0]["ts"], "标题里的日期没解析出来")
        self.assertEqual(time.strftime("%Y-%m-%d", time.localtime(out[0]["ts"])), "2026-10-26")

    def test_parse_sd_gxt(self):
        html = ('<a href="/art/2026/4/3/art_103862_10356311.html">'
                '关于印发《山东省化工产业数智化改造标杆奖补政策实施细则》的通知</a>')
        out = F.parse_sd_gxt(html)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["url"],
                         "http://gxt.shandong.gov.cn/art/2026/4/3/art_103862_10356311.html")
        self.assertEqual(out[0]["source"], "山东省工信厅")

    def test_parse_sd_gxt_skips_short(self):
        """标题太短的导航链接不是稿子"""
        out = F.parse_sd_gxt('<a href="/art/2026/4/3/art_1_2.html">更多</a>')
        self.assertEqual(out, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
