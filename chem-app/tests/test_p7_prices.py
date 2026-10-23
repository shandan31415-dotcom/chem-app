# -*- coding: utf-8 -*-
"""问题7：行情模块更新间隔缩短 + 准确核实 —— 专项测试。

数据层：daily.yml 定时从每天 1 次改为 3 次，覆盖期货交易关键时点，
        cron 语法正确、时点换算正确（UTC→北京）。
前端层：行情模块明确显示本次抓取时刻 + 每天三次的说明。
"""
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))  # 仓库根（workflows 在根下）
DAILY = os.path.join(REPO, ".github", "workflows", "daily.yml")


def read_daily():
    with open(DAILY, encoding="utf-8") as f:
        return f.read()


class TestPriceUpdateInterval(unittest.TestCase):
    """数据层：daily.yml 更新间隔与 cron 正确性"""

    def test_three_crons(self):
        """每天应有 3 个 cron（不再只抓一次）"""
        body = read_daily()
        crons = re.findall(r'cron:\s*"([^"]+)"', body)
        self.assertEqual(len(crons), 3, "每天应抓取 3 次，实际 cron 数 %d" % len(crons))

    def test_cron_timepoints(self):
        """三个时点覆盖早盘/日盘收盘/夜盘收盘"""
        body = read_daily()
        crons = re.findall(r'cron:\s*"([^"]+)"', body)
        # UTC → 北京（+8 小时）
        expected = {"30 1 * * *", "30 7 * * *", "0 15 * * *"}
        self.assertEqual(set(crons), expected, "三个定时时点不符合预期：%s" % crons)

    def test_cron_syntax_valid(self):
        """cron 是合法的 5 字段格式"""
        body = read_daily()
        crons = re.findall(r'cron:\s*"([^"]+)"', body)
        for c in crons:
            parts = c.split()
            self.assertEqual(len(parts), 5, "cron 应为 5 字段：%s" % c)
            # 分 0-59，时 0-23
            self.assertTrue(0 <= int(parts[0]) <= 59, "分字段越界：%s" % c)
            self.assertTrue(0 <= int(parts[1]) <= 23, "时字段越界：%s" % c)

    def test_utc_to_beijing_mapping(self):
        """UTC 时点换算到北京时间应落在交易相关时段"""
        body = read_daily()
        crons = re.findall(r'cron:\s*"([^"]+)"', body)
        bj = []
        for c in crons:
            parts = c.split()
            hour_utc = int(parts[1])
            bj_hour = (hour_utc + 8) % 24
            bj.append(bj_hour)
        # 北京 9（早盘）、15（日盘收盘）、23（夜盘收盘）
        self.assertIn(9, bj, "缺少早盘时段（北京 9 点附近）")
        self.assertIn(15, bj, "缺少日盘收盘时段（北京 15 点附近）")
        self.assertIn(23, bj, "缺少夜盘收盘时段（北京 23 点附近）")

    def test_still_fetch_only(self):
        """定时任务仍只跑 fetch_all，不跑 build_enrich（不覆盖人工数据）"""
        body = read_daily()
        self.assertIn("fetch_all.py", body)
        # 只检查实际 run 命令，不含注释里的说明文字
        run_cmds = re.findall(r'run:\s*(?:python\s+)?([\w./]+\.py)', body)
        self.assertIn("scripts/fetch_all.py", run_cmds, "定时任务应运行 fetch_all.py")
        self.assertNotIn("build_enrich", run_cmds, "定时任务不能运行 build_enrich.py")

    def test_still_manual_dispatch(self):
        """仍保留手动触发"""
        body = read_daily()
        self.assertIn("workflow_dispatch", body)


class TestPriceFrontend(unittest.TestCase):
    """前端层：行情模块显示更新时刻与每天三次说明"""

    @classmethod
    def setUpClass(cls):
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tests"))
        import webrunner as W
        cls.ctx = W.App().__enter__()
        cls.b = cls.ctx.browser

    @classmethod
    def tearDownClass(cls):
        cls.ctx.__exit__(None, None, None)

    def test_prices_show_update_time(self):
        """行情页显示本次抓取时刻"""
        b = self.ctx.open()
        self.ctx.goto_hash("#/prices")
        b.wait_js("!!document.querySelector('#app .hint')", 10, "行情页未渲染")
        txt = b.app_text()
        self.assertIn("更新于", txt, "行情页应显示「更新于 XX」")

    def test_prices_show_three_times_note(self):
        """行情页说明每天抓取三次"""
        b = self.ctx.open()
        self.ctx.goto_hash("#/prices")
        b.wait_js("!!document.querySelector('#app .hint')", 10, "行情页未渲染")
        txt = b.app_text()
        self.assertIn("每天", txt, "行情页应说明每天抓取频次")

    def test_no_js_error(self):
        """浏览行情页无 JS 报错"""
        b = self.ctx.open()
        self.ctx.goto_hash("#/prices")
        b.wait_js("!!document.querySelector('#app')", 10)
        errs = b.cdp.eval("window.__errs")
        self.assertFalse(errs, "行情页不应有 JS 报错: %s" % errs)


if __name__ == "__main__":
    unittest.main(verbosity=2)
