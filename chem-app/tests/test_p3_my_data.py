# -*- coding: utf-8 -*-
"""P3 我的数据 + 离线 · 验收测试（A16 / A17 / A18 + 每周快照）

导入用 DataTransfer 在页面里造一个真 File 喂给 input，走的是和生产代码完全一样的
change 事件路径，不是绕过 UI 直接改内存。
"""
import json
import os
import sys
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import webrunner as W  # noqa: E402


class TestExportImport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ctx = W.App().__enter__()
        cls.b = cls.ctx.browser

    @classmethod
    def tearDownClass(cls):
        cls.ctx.__exit__(None, None, None)

    def goto_me(self):
        self.ctx.open()
        self.ctx.goto_hash("#/me")
        self.b.wait_js("!!document.getElementById('exp')", 10, "我的数据页应有导出按钮")

    def test_export_payload_shape(self):
        """A17：导出的是可读 json，含 learned / read / fav"""
        self.goto_me()
        # 先制造一些记录
        self.b.cdp.eval("""(function(){
          localStorage.setItem('chemapp.v1', JSON.stringify({
            learned:['polyurethane','soda'], read:['pol:pol1'], fav:['cat:soda'], seen:{}, lastOpen:0
          }));
        })()""")
        self.ctx.open()
        self.ctx.goto_hash("#/me")
        self.b.wait_js("!!document.getElementById('exp')", 10)
        self.b.click("#exp")
        self.b.wait_js("!!window.__lastExport", 10, "导出应产出 json 文本")
        txt = self.b.cdp.eval("window.__lastExport")
        o = json.loads(txt)
        self.assertEqual(1, o["v"], "导出文件必须带版本号")
        self.assertEqual("chem-app", o["app"])
        for k in ["learned", "read", "fav"]:
            self.assertIn(k, o, "导出文件缺字段 " + k)
        self.assertEqual(["polyurethane", "soda"], o["learned"])
        self.assertIn("exported_at", o)

    def _import(self, payload_obj):
        js = """
        (function(){
          var inp=document.getElementById('impFile');
          var dt=new DataTransfer();
          dt.items.add(new File([%s],'backup.json',{type:'application/json'}));
          inp.files=dt.files;
          inp.dispatchEvent(new Event('change'));
          return true;
        })()
        """ % json.dumps(json.dumps(payload_obj, ensure_ascii=False))
        self.b.cdp.eval(js)

    def test_import_merges_and_reports_counts(self):
        """A18：清空后导入恢复，并提示恢复条数（合并而非覆盖）"""
        self.goto_me()
        self.b.cdp.eval("""localStorage.setItem('chemapp.v1', JSON.stringify(
          {learned:['polyurethane'], read:[], fav:[], seen:{}, lastOpen:0}))""")
        self.ctx.open()
        self.ctx.goto_hash("#/me")
        self.b.wait_js("!!document.getElementById('impFile')", 10)

        payload = {"v": 1, "app": "chem-app", "exported_at": "2026-10-21T00:00:00Z",
                   "learned": ["polyurethane", "soda", "methanol"],
                   "read": ["pol:pol1", "pol:pol2"], "fav": ["cat:soda"]}
        self._import(payload)
        self.b.wait_js("document.getElementById('impinfo').innerText.indexOf('恢复完成')>=0",
                       10, "导入后要给恢复明细")
        info = self.b.cdp.eval("document.getElementById('impinfo').innerText")
        self.assertIn("新增品类 2", info, "合并时只算新增：实际 %s" % info)
        self.assertIn("已存在 1", info)
        self.assertIn("新增已读 2", info)
        self.assertIn("新增收藏 1", info)
        st = json.loads(self.b.get_local("chemapp.v1"))
        self.assertEqual(3, len(st["learned"]), "已有的保留 + 缺的补上")
        self.assertIn("soda", st["learned"])

    def test_import_version_mismatch_asks_first(self):
        """PRD 7.3：版本不一致要先问，不能静默覆盖；取消则不导入"""
        self.goto_me()
        self.b.cdp.eval("""(function(){
          window.__asks=[];
          window.confirm=function(m){ window.__asks.push(m); return false; };
          localStorage.setItem('chemapp.v1', JSON.stringify(
            {learned:[], read:[], fav:[], seen:{}, lastOpen:0}));
        })()""")
        self.ctx.open()
        self.b.cdp.eval("""(function(){
          window.__asks=[];
          window.confirm=function(m){ window.__asks.push(m); return false; };
        })()""")
        self.ctx.goto_hash("#/me")
        self.b.wait_js("!!document.getElementById('impFile')", 10)

        self._import({"learned": ["soda"]})   # 故意不带 v
        self.b.wait_js("window.__asks && window.__asks.length>0", 10, "版本不一致必须弹确认")
        msg = self.b.cdp.eval("window.__asks[0]")
        self.assertIn("版本不一致", msg)
        st = json.loads(self.b.get_local("chemapp.v1"))
        self.assertEqual([], st["learned"], "取消后不能导入任何东西")
        self.assertIn("已取消", self.b.cdp.eval("document.getElementById('impinfo').innerText"))

    def test_import_version_mismatch_can_proceed(self):
        self.goto_me()
        self.b.cdp.eval("""localStorage.setItem('chemapp.v1', JSON.stringify(
          {learned:[], read:[], fav:[], seen:{}, lastOpen:0}))""")
        self.ctx.open()
        self.b.cdp.eval("window.confirm=function(){return true;}")
        self.ctx.goto_hash("#/me")
        self.b.wait_js("!!document.getElementById('impFile')", 10)
        self._import({"v": 0, "learned": ["pp"]})
        self.b.wait_js("document.getElementById('impinfo').innerText.indexOf('恢复完成')>=0", 10)
        st = json.loads(self.b.get_local("chemapp.v1"))
        self.assertEqual(["pp"], st["learned"], "确认后应照样导入")


class TestWeeklySnapshot(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ctx = W.App().__enter__()
        cls.b = cls.ctx.browser

    @classmethod
    def tearDownClass(cls):
        cls.ctx.__exit__(None, None, None)

    def seed_snaps(self, arr):
        self.b.cdp.eval("localStorage.setItem('chemapp.snaps', %s)" % json.dumps(json.dumps(arr)))

    def get_snaps(self):
        return json.loads(self.b.cdp.eval("localStorage.getItem('chemapp.snaps') || '[]'"))

    def reload(self):
        self.ctx.open()

    def test_first_open_creates_snapshot(self):
        self.ctx.open()
        self.b.cdp.eval("localStorage.removeItem('chemapp.snaps')")
        self.reload()
        arr = self.get_snaps()
        self.assertEqual(1, len(arr), "首次打开应存下第一份快照")
        self.assertIn("learned", arr[0]["data"])

    def test_no_new_snapshot_within_a_week(self):
        self.ctx.open()
        self.seed_snaps([{"ts": int(time.time() * 1000) - 3600 * 1000, "data": {"learned": []}}])
        self.reload()
        self.assertEqual(1, len(self.get_snaps()), "一周内不应重复存快照")

    def test_snapshot_after_eight_days(self):
        self.ctx.open()
        old = int(time.time() * 1000) - 8 * 86400000
        self.seed_snaps([{"ts": old, "data": {"learned": ["a"]}}])
        self.reload()
        arr = self.get_snaps()
        self.assertEqual(2, len(arr), "超过一周应新增一份")

    def test_keep_only_four(self):
        self.ctx.open()
        old = int(time.time() * 1000) - 8 * 86400000
        seed = [{"ts": old + i, "data": {"learned": ["c%d" % i]}} for i in range(4)]
        self.seed_snaps(seed)
        self.reload()
        arr = self.get_snaps()
        self.assertEqual(4, len(arr), "最多保留 4 份")
        self.assertEqual("c1", arr[0]["data"]["learned"][0], "应删掉最旧的一份")

    def test_listed_on_me_page(self):
        self.ctx.open()
        old = int(time.time() * 1000) - 8 * 86400000
        self.seed_snaps([{"ts": old, "data": {"learned": ["a", "b"], "read": ["x"], "fav": []}}])
        self.reload()
        self.ctx.goto_hash("#/me")
        self.b.wait_js("document.querySelectorAll('#app [data-snap]').length>0", 10,
                       "我的数据页应列出本机快照")
        self.assertIn("本机快照", self.b.app_text())

    def _open_me_with_old_snap(self):
        """造一份 8 天前的快照（含 polyurethane），当前记录清空，然后停在 #/me。

        重新加载时 snapMaybe 会给「当前空记录」补一份新快照，所以不能按第 0 个按钮点，
        要按快照里的实际下标点，才能保证点到的确实是 8 天前那份。
        """
        self.ctx.open()
        self.b.cdp.eval("""localStorage.setItem('chemapp.v1', JSON.stringify(
          {learned:[], read:[], fav:[], seen:{}, lastOpen:0}))""")
        old = int(time.time() * 1000) - 8 * 86400000
        self.seed_snaps([{"ts": old,
                          "data": {"learned": ["polyurethane"], "read": [], "fav": []}}])
        self.reload()
        self.ctx.goto_hash("#/me")
        self.b.wait_js("document.querySelectorAll('#app [data-snap]').length>0", 10)
        arr = self.get_snaps()
        idx = [i for i, s in enumerate(arr)
               if (s.get("data") or {}).get("learned") == ["polyurethane"]]
        self.assertTrue(idx, "应能找到 8 天前那份快照：%r" % arr)
        return idx[0]

    def test_restore_from_snapshot(self):
        """点「恢复」→ 真弹确认 → 点确定 → 记录合并回来"""
        i = self._open_me_with_old_snap()
        self.b.accept_dialogs(True)
        self.b.clear_dialogs()
        self.b.click('[data-snap="%d"]' % i)
        self.assertIn("快照恢复", self.b.last_dialog(), "恢复前必须让用户确认一次")
        self.b.wait_js("document.getElementById('impinfo').innerText.indexOf('快照恢复')>=0",
                       10, "从快照恢复后要有提示")
        st = json.loads(self.b.get_local("chemapp.v1"))
        self.assertIn("polyurethane", st["learned"])

    def test_cancel_snapshot_restore_keeps_data(self):
        """在确认框点取消，就一点都不该恢复"""
        i = self._open_me_with_old_snap()
        self.b.accept_dialogs(False)
        self.b.clear_dialogs()
        self.b.click('[data-snap="%d"]' % i)
        self.assertTrue(self.b.last_dialog(), "应弹出确认框")
        time.sleep(0.2)
        st = json.loads(self.b.get_local("chemapp.v1"))
        self.assertEqual([], st["learned"], "取消后不能恢复任何记录")
        self.b.accept_dialogs(True)


class TestOffline(unittest.TestCase):
    """A16：断网后仍能看到上次内容，并明确显示「离线」"""

    @classmethod
    def setUpClass(cls):
        cls.ctx = W.App().__enter__()
        cls.b = cls.ctx.browser

    @classmethod
    def tearDownClass(cls):
        cls.ctx.__exit__(None, None, None)

    def test_offline_after_first_load(self):
        b = self.ctx.open()
        # 等 Service Worker 接管
        b.cdp.eval("navigator.serviceWorker.ready.then(function(){return true})")
        b.cdp.eval("new Promise(function(r){"
                   "if(navigator.serviceWorker.controller) return r(true);"
                   "navigator.serviceWorker.addEventListener('controllerchange',function(){r(true)});"
                   "setTimeout(function(){r(true)},3000);})")
        b.offline(True)
        try:
            b.cdp.eval("location.reload()")
            time.sleep(1.0)
            b.wait_ready(20)
            b.wait_js("!!document.querySelector('#app .hero')", 25, "断网时应能打开缓存的首屏")
            b.wait_js("document.getElementById('netbar') && !document.getElementById('netbar').hidden",
                      15, "断网必须显示提示条")
            txt = b.cdp.eval("document.getElementById('netbar').innerText")
            self.assertIn("离线", txt)
            self.assertIn("显示", txt, "要说清楚显示的是哪一次的数据")
        finally:
            b.offline(False)
            b.cdp.eval("location.reload()")
            time.sleep(0.5)
            b.wait_ready(20)

    def test_online_hides_banner(self):
        b = self.ctx.open()
        b.offline(False)
        b.cdp.eval("location.reload()")
        time.sleep(0.6)
        b.wait_ready(20)
        b.wait_js("!!document.querySelector('#app .hero')", 20)
        hidden = b.cdp.eval("document.getElementById('netbar').hidden")
        self.assertTrue(hidden, "联网正常时不应显示离线提示")

    def test_all_data_missing_shows_message_not_blank(self):
        """数据全都拿不到时（首次进入就断网），要给提示而不是白屏"""
        root = W.copy_app()
        try:
            for n in ["news.json", "prices.json", "categories.json"]:
                p = os.path.join(root, "data", n)
                if os.path.exists(p):
                    os.remove(p)
            with W.App(root) as a:
                bb = a.open()
                a.goto_hash("#/home")
                bb.wait_js("document.getElementById('app').innerText.indexOf('未能加载数据')>=0",
                           15, "全无数据时要明说")
        finally:
            import shutil
            shutil.rmtree(os.path.dirname(root), ignore_errors=True)


class TestMeEntry(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ctx = W.App().__enter__()
        cls.b = cls.ctx.browser

    @classmethod
    def tearDownClass(cls):
        cls.ctx.__exit__(None, None, None)

    def test_entry_from_home(self):
        self.ctx.open()
        self.ctx.goto_hash("#/home")
        self.b.wait_js("!!document.querySelector('#app .morelink')", 10, "首页应有我的数据入口")
        self.b.click_and_wait_hash("#app .morelink", "#/me")
        self.b.wait_js("!!document.getElementById('exp')", 10)

    def test_me_explains_cache_is_not_backup(self):
        self.ctx.open()
        self.ctx.goto_hash("#/me")
        txt = self.b.app_text()
        self.assertIn("离线缓存不是备份", txt, "PRD 7.4 要求写清楚")


if __name__ == "__main__":
    unittest.main(verbosity=2)
