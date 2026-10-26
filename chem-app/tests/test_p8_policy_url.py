# -*- coding: utf-8 -*-
"""问题8 · 政策「打开原文」地址不存在 —— 专项测试

现象：政策页点「打开原文」提示「地址出错或不存在」。
根因：resolve_policy_url() 用 lstrip("./") 按字符集剥相对路径，
     把列表页 href 里的 "../../" 层级上跳整个吃掉，拼出
     /zcwj/xxgk2018/... 这种少跳一级的地址。

本测试守三件事：
  1. 相对路径必须走 urljoin 标准解析，上跳层级不能丢
  2. 落盘的 policies.json 里不能出现错误拼接的地址
  3. 政策 URL 必须经过回源核验（verified_at），死链不写入
"""
import json
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SCRIPTS = os.path.join(ROOT, "scripts")
sys.path.insert(0, SCRIPTS)

import fetch_all as F  # noqa: E402

POLICIES = os.path.join(ROOT, "data", "policies.json")

# 生态环境部「政策文件」栏目：列表页在 /zcwj/，正文在 /xxgk2018/
# 正确地址要往上跳两级，错误地址会把 xxgk2018 挂在 /zcwj/ 下面
MEE_SRC = {"level": "国家级", "org": "生态环境部",
           "url": "https://www.mee.gov.cn/zcwj/",
           "pattern": ""}
SD_SRC = {"level": "山东省", "org": "山东省工业和信息化厅",
          "url": "http://gxt.shandong.gov.cn/col/col103862/index.html",
          "pattern": ""}
NDRC_SRC = {"level": "国家级", "org": "国家发展改革委",
            "url": "https://www.ndrc.gov.cn/xxgk/zcfb/tz/",
            "pattern": ""}


def load_policies():
    with open(POLICIES, encoding="utf-8") as f:
        return json.load(f)


class TestResolveUrl(unittest.TestCase):
    """相对路径还原：上跳层级不能丢"""

    def test_parent_levels_kept(self):
        """../../xxgk2018/... 要跳出 /zcwj/ 到站点根"""
        got = F.resolve_policy_url(
            "../../xxgk2018/xxgk/xxgk01/202608/t20260806_1163640.html", MEE_SRC)
        self.assertEqual(
            got, "https://www.mee.gov.cn/xxgk2018/xxgk/xxgk01/202608/t20260806_1163640.html")

    def test_dot_slash_subdir(self):
        """./zyygwj/... 是在当前栏目下找子目录"""
        got = F.resolve_policy_url("./zyygwj/202610/t20261022_1184320.shtml", MEE_SRC)
        self.assertEqual(
            got, "https://www.mee.gov.cn/zcwj/zyygwj/202610/t20261022_1184320.shtml")

    def test_absolute_path_from_root(self):
        """/art/... 这种站根绝对路径，不该被栏目路径污染"""
        got = F.resolve_policy_url("/art/2026/4/3/art_103862_10356311.html", SD_SRC)
        self.assertEqual(
            got, "http://gxt.shandong.gov.cn/art/2026/4/3/art_103862_10356311.html")

    def test_already_absolute_untouched(self):
        """已经是完整地址的，原样保留"""
        u = "https://www.ndrc.gov.cn/xxgk/zcfb/tz/202610/t20261020_1401234.html"
        self.assertEqual(F.resolve_policy_url(u, NDRC_SRC), u)

    def test_no_wrong_nesting(self):
        """回归断言：绝不能出现把 xxgk2018 挂在 /zcwj/ 底下的旧 bug"""
        got = F.resolve_policy_url(
            "../../xxgk2018/xxgk/xxgk01/202608/t20260806_1163640.html", MEE_SRC)
        self.assertNotIn("/zcwj/xxgk2018", got, "上跳层级被吃掉了，这是历史 bug 复发")


class TestDeadLinkGuard(unittest.TestCase):
    """死链自检：政府站死链常返 200，必须看页面内容"""

    def test_markers_defined(self):
        """至少覆盖「页面不存在」「404」「系统维护」三类"""
        self.assertTrue(any("不存在" in k for k in F.POLICY_DEAD_MARKERS))
        self.assertTrue(any("404" in k for k in F.POLICY_DEAD_MARKERS))
        self.assertTrue(any("维护" in k for k in F.POLICY_DEAD_MARKERS))

    def test_guard_exists(self):
        self.assertTrue(callable(getattr(F, "policy_url_alive", None)))

    def test_reject_empty_body(self):
        """拿不到内容必须判死，不能当成正常页放过去"""
        ok, _ = F.policy_url_alive("http://127.0.0.1:1/nope.html", timeout=2)
        self.assertFalse(ok)


class TestPoliciesData(unittest.TestCase):
    """落盘数据：地址合法 + 已核验"""

    def setUp(self):
        self.data = load_policies()
        self.items = self.data.get("items") or []

    def test_has_items(self):
        self.assertGreater(len(self.items), 0, "政策条数为 0")

    def test_all_absolute_https_urls(self):
        """每条都是能直接打开的绝对地址"""
        for x in self.items:
            self.assertRegex(x["url"], r"^https?://",
                             "不是绝对地址：%s" % x["url"])
            self.assertGreater(len(x["url"]), 25)

    def test_no_wrong_mee_nesting(self):
        """落盘数据里不能有历史错误拼接"""
        bad = [x["url"] for x in self.items if "/zcwj/xxgk2018" in x["url"]]
        self.assertEqual(bad, [], "发现错误拼接地址：%s" % bad)

    def test_all_verified(self):
        """每条都过了回源核验，有 verified_at 时间戳"""
        missing = [x["title"][:20] for x in self.items if not x.get("verified_at")]
        self.assertEqual(missing, [],
                         "以下政策未做原文核验，可能点开是死链：%s" % missing)

    def test_no_dead_title(self):
        """标题本身不该是错误页文案"""
        for x in self.items:
            for k in ["不存在", "404", "系统维护"]:
                self.assertNotIn(k, x["title"], "政策标题异常：%s" % x["title"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
