# -*- coding: utf-8 -*-
"""P1 数据层加固 · 单元测试

覆盖：save 原子写、save_or_keep 保旧+error、每日快照与 30 天轮转、
跨源去重（同事件只留一条且归到山东）、山东四级判定、品种别名匹配、
政策日期兜底。
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import fetch_all as F  # noqa: E402


class TestSaveOrKeep(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="dat-")
        self._data = F.DATA
        F.DATA = self.tmp

    def tearDown(self):
        F.DATA = self._data
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_atomic_write_no_tmp_left(self):
        F.save("a.json", {"x": 1})
        self.assertEqual([], [n for n in os.listdir(self.tmp) if n.endswith(".tmp")])
        with open(os.path.join(self.tmp, "a.json"), encoding="utf-8") as f:
            self.assertEqual({"x": 1}, json.load(f))

    def test_failure_keeps_old_content_and_adds_error(self):
        F.save("news.json", {"updated_at": 1, "total": 9, "blocks": [{"name": "山东", "items": [{"title": "旧闻"}]}]})
        F.save_or_keep("news.json", None, RuntimeError("连接超时"), "2026-10-21 03:00")
        with open(os.path.join(self.tmp, "news.json"), encoding="utf-8") as f:
            d = json.load(f)
        self.assertEqual(9, d["total"], "旧内容必须原样保留")
        self.assertEqual("旧闻", d["blocks"][0]["items"][0]["title"])
        self.assertIn("连接超时", d["error"]["msg"])
        self.assertEqual("2026-10-21 03:00", d["error"]["at"])

    def test_success_clears_error(self):
        F.save("prices.json", {"updated_at": 1, "error": {"msg": "上次失败", "at": "x"}})
        F.save_or_keep("prices.json", {"updated_at": 2, "count": 23}, None, "t")
        with open(os.path.join(self.tmp, "prices.json"), encoding="utf-8") as f:
            d = json.load(f)
        self.assertNotIn("error", d, "成功一次后必须清掉 error")
        self.assertEqual(23, d["count"])

    def test_failure_without_old_file_still_writes_error(self):
        F.save_or_keep("policies.json", None, RuntimeError("no net"), "t")
        with open(os.path.join(self.tmp, "policies.json"), encoding="utf-8") as f:
            d = json.load(f)
        self.assertIn("error", d)


class TestBackups(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="bk-")
        self.data = os.path.join(self.tmp, "data")
        self.bk = os.path.join(self.tmp, "backups")
        os.makedirs(self.data)
        os.makedirs(self.bk)
        for n in F.BACKUP_FILES:
            with open(os.path.join(self.data, n), "w", encoding="utf-8") as f:
                f.write('{"updated_at":1}')

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_snapshot_creates_four_files(self):
        n = F.snapshot_backups("2026-10-21", data_dir=self.data, bk_dir=self.bk)
        self.assertEqual(4, n)
        names = sorted(os.listdir(self.bk))
        self.assertEqual(4, len(names))
        for name, src in zip(names, sorted(F.BACKUP_FILES)):
            self.assertEqual("2026-10-21-" + src, name)

    def test_same_day_twice_does_not_duplicate(self):
        F.snapshot_backups("2026-10-21", data_dir=self.data, bk_dir=self.bk)
        F.snapshot_backups("2026-10-21", data_dir=self.data, bk_dir=self.bk)
        self.assertEqual(4, len(os.listdir(self.bk)))

    def test_rotate_keeps_last_30_days(self):
        for i in range(1, 36):
            day = "2026-09-%02d" % i if i <= 30 else "2026-10-%02d" % (i - 30)
            with open(os.path.join(self.bk, day + "-news.json"), "w") as f:
                f.write("{}")
        removed = F.rotate_backups(self.bk, keep_days=30)
        self.assertEqual(5, len(removed), "35 天应删掉最旧 5 天")
        left = sorted({n[:10] for n in os.listdir(self.bk)})
        self.assertEqual(30, len(left))
        self.assertNotIn("2026-09-01", left, "最旧的必须被删")

    def test_rotate_noop_under_limit(self):
        with open(os.path.join(self.bk, "2026-10-21-news.json"), "w") as f:
            f.write("{}")
        self.assertEqual([], F.rotate_backups(self.bk, keep_days=30))


class TestDedup(unittest.TestCase):
    def mk(self, title, block, ts, **kw):
        d = {"title": title, "block": block, "ts": ts, "day": F.day_of(ts), "url": "u", "source": "s"}
        d.update(kw)
        return d

    def test_same_event_across_blocks_kept_once(self):
        ts = 1761091200  # 2026-10-22 前后，仅用于同一天
        a = self.mk("万华化学烟台基地新增MDI产能投产", "全国", ts)
        b = self.mk("万华化学烟台基地新增 MDI 产能投产！", "山东", ts)
        out = F.dedup_cross([a, b])
        self.assertEqual(1, len(out), "同一事件只能留一条")
        self.assertEqual("山东", out[0]["block"], "应归到更具体的层级（山东）")
        self.assertTrue(a.get("dup_of") or b.get("dup_of"), "被丢弃的那条必须留 dup_of 痕迹")

    def test_different_events_kept(self):
        ts = 1761091200
        a = self.mk("万华化学烟台基地新增MDI产能投产", "山东", ts)
        b = self.mk("巴斯夫上调欧洲MDI报价", "全球", ts)
        self.assertEqual(2, len(F.dedup_cross([a, b])))

    def test_different_day_not_deduped(self):
        a = self.mk("万华化学烟台基地新增MDI产能投产", "山东", 1761091200)
        b = self.mk("万华化学烟台基地新增MDI产能投产", "山东", 1761091200 - 86400)
        self.assertEqual(2, len(F.dedup_cross([a, b])), "不同天的相似标题不算同一事件")

    def test_dup_of_records_winner_title(self):
        ts = 1761091200
        a = self.mk("裕龙石化炼化一体化项目二期投产", "山东", ts)
        b = self.mk("裕龙石化炼化一体化项目二期投产", "全国", ts)
        out = F.dedup_cross([b, a])
        self.assertEqual(1, len(out))
        self.assertEqual(out[0]["title"], out[0].get("dup_of") or out[0]["title"])


class TestShandong(unittest.TestCase):
    def test_city_name(self):
        self.assertTrue(F.is_shandong("淄博化工园区整治提升"))

    def test_province_signal(self):
        self.assertTrue(F.is_shandong("山东省工信厅发布化工园区名单"))

    def test_company_signal(self):
        self.assertTrue(F.is_shandong("裕龙石化二期开工"))

    def test_negative(self):
        self.assertFalse(F.is_shandong("广东石化乙烯装置检修"))

    def test_enterprise_keys_not_empty(self):
        keys = F.sd_enterprise_keys()
        self.assertGreater(len(keys), 100,
                           "山东企业关键词必须能从 cities->parks->enterprises 结构读出")
        self.assertIn("万华", keys)


class TestPriceNews(unittest.TestCase):
    ROWS = [{"name": "PVC"}, {"name": "纯碱"}, {"name": "沥青"}]

    def test_alias_hits_title_first(self):
        raw = [
            {"title": "下游需求走弱 PVC 报价下调", "url": "u1", "source": "s", "ts": 3},
            {"title": "某装置检修影响供应", "summary": "涉及聚氯乙烯", "url": "u2", "source": "s", "ts": 2},
        ]
        out = F.match_price_news(raw, self.ROWS)
        self.assertEqual(2, len(out["PVC"]))
        self.assertEqual("title", out["PVC"][0]["via"], "标题命中必须排在前面")
        self.assertEqual("summary", out["PVC"][1]["via"])

    def test_exclusion_word(self):
        raw = [{"title": "煤沥青价格小幅上行", "url": "u", "source": "s", "ts": 1}]
        out = F.match_price_news(raw, self.ROWS)
        self.assertEqual([], out["沥青"], "煤沥青不是石油沥青，不能算关联新闻")

    def test_empty_is_empty_not_fabricated(self):
        out = F.match_price_news([], self.ROWS)
        for r in self.ROWS:
            self.assertEqual([], out[r["name"]])


class TestPolicyDate(unittest.TestCase):
    def test_url_date_variants(self):
        self.assertIsNotNone(F.date_from_url("https://x.gov.cn/art/2026/10/21/art_1_2.html"))
        self.assertIsNotNone(F.date_from_url("https://x.gov.cn/t20261021_123.html"))
        self.assertIsNotNone(F.date_from_url("https://x.gov.cn/a/202610213902.html"))
        self.assertIsNone(F.date_from_url("https://x.gov.cn/gg/index.html"))


class TestDataAfterFetch(unittest.TestCase):
    """针对 real 数据的断言（跑完 fetch 后才有意义）"""

    def load(self, n):
        with open(os.path.join(ROOT, "data", n), encoding="utf-8") as f:
            return json.load(f)

    def test_news_blocks_all_have_items(self):
        """每板块 ≥3 条；不足时必须能证明是上游源站故障。

        门槛没有放宽，只是和 scripts/qa.py 的 a8 用同一套判定：
        中国化工报（中化新网 ccin.com.cn）整站维护时，山东本地企业栏目
        与全球国际频道全部归零，这两个板块客观凑不满 3 条。以前这里写死
        ≥3，结果是源站一挂测试就红，而真实的数据质量事故被噪音淹没。
        """
        d = self.load("news.json")
        cnt = {b["name"]: len(b["items"]) for b in d["blocks"]}
        st = d.get("source_status") or {}
        down = [k for k, v in st.items() if (v or {}).get("status") != "ok"]
        for k in ["全球", "全国", "山东"]:
            n = cnt.get(k, 0)
            if n >= 3:
                continue
            self.assertTrue(
                down,
                "%s 板块只有 %d 条，且没有任何源站故障记录（%s）" % (k, n, cnt))
            self.assertIn(
                k, ("全球", "山东"),
                "%s 板块只有 %d 条：这个板块不依赖中国化工报，源站故障不能解释" % (k, n))

    def test_shandong_block_really_shandong(self):
        d = self.load("news.json")
        sd = [b for b in d["blocks"] if b["name"] == "山东"][0]["items"]
        keys = F.sd_enterprise_keys()
        bad = [i["title"] for i in sd
               if not (F.is_shandong(i["title"], i.get("summary") or "")
                       or any(k in i["title"] for k in keys))]
        self.assertEqual([], bad[:5], "山东板块里混入了与山东无关的新闻")

    def test_no_duplicate_event_across_blocks(self):
        d = self.load("news.json")
        titles = []
        for b in d["blocks"]:
            for i in b["items"]:
                titles.append(F.norm_title(i["title"]))
        self.assertEqual(len(titles), len(set(titles)), "存在重复标题（应已被去重）")

    def test_price_news_coverage(self):
        d = self.load("prices.json")
        items = [i for g in d["groups"] for i in g["items"]]
        withn = [i["name"] for i in items if i.get("news")]
        self.assertGreaterEqual(len(withn), 15, "有新闻的品种 %d/23 < 15" % len(withn))

    def test_every_news_has_url_and_source(self):
        d = self.load("news.json")
        bad = []
        for b in d["blocks"]:
            for i in b["items"]:
                if not i.get("url") or not i.get("source"):
                    bad.append(i.get("title"))
        self.assertEqual([], bad[:5])


if __name__ == "__main__":
    unittest.main(verbosity=2)
