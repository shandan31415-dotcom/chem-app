# -*- coding: utf-8 -*-
"""把人工补录的政策并进 policies.json。

为什么要有这个入口：工信部、山东省政府政策文件库、省应急厅这几个栏目的列表页
是 JS 异步加载的，静态抓取拿不到（详见 政策来源清单.md）。所以留一条人工通道——
同事每月花十分钟看一遍这几个站，把标题和链接填进 manual_policies.csv，
跑一下本脚本，就并进政策库了。

用法：
    python scripts/merge_manual_policies.py            # 合并
    python scripts/merge_manual_policies.py --dry-run   # 只看结果，不写文件
    python scripts/merge_manual_policies.py --check-url # 额外联网验证链接能否打开（慢）

CSV 列（第一行是表头，别删）：
    标题 | 发文机关 | 层级 | 发布日期 | 原文链接 | 影响提示 | 内部备注

规矩：
  - 只收官方原文，链接域名必须是 .gov.cn（真要收别的，加 --allow-non-gov，慎用）
  - 层级只能填「国家级」或「山东省」——小程序的政策页只有这两个分组
  - 标题以「示例」开头的行会自动跳过，不用删
  - 已经在库里的（链接或标题重复）会跳过，重复填不会出事
"""
import argparse
import csv
import datetime
import json
import os
import re
import sys
from urllib.parse import urlparse

sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
DATA = os.path.join(APP, "data")
CSV_PATH = os.path.join(DATA, "manual_policies.csv")
JSON_PATH = os.path.join(DATA, "policies.json")

LEVELS = ("国家级", "山东省")
MIN_TITLE = 8
MAX_TITLE = 120

COLUMNS = ["标题", "发文机关", "层级", "发布日期", "原文链接", "影响提示", "内部备注"]


# ---------------------------------------------------------------- 读取

def read_rows(path):
    """Excel 存中文 CSV 常是 GBK，UTF-8 打不开就换编码，别让人卡在这一步。"""
    last = None
    for enc in ("utf-8-sig", "utf-8", "gbk", "gb18030"):
        try:
            with open(path, encoding=enc, newline="") as f:
                return list(csv.DictReader(f)), enc
        except UnicodeDecodeError as e:  # noqa: PERF203
            last = e
        except FileNotFoundError:
            raise SystemExit("找不到 %s —— 先建好这个文件（模板已随仓库提供）" % path)
    raise SystemExit("CSV 编码识别失败：%s" % last)


def norm(s):
    return re.sub(r"[\s\u3000\u200b]+", "", str(s or ""))


def parse_date(s):
    """支持 2026-11-01 / 2026/11/1 / 2026.11.1 / 2026年11月1日"""
    t = str(s or "").strip()
    if not t:
        return None
    t = t.replace("年", "-").replace("月", "-").replace("日", "").replace("/", "-").replace(".", "-")
    for fmt in ("%Y-%m-%d", "%Y-%m", "%Y"):
        try:
            d = datetime.datetime.strptime(t, fmt)
            return d
        except ValueError:
            continue
    return None


def check_row(row, lineno, allow_non_gov):
    """返回 (item 或 None, 错误说明 或 '')"""
    title = str(row.get("标题") or "").strip()
    org = str(row.get("发文机关") or "").strip()
    level = str(row.get("层级") or "").strip()
    date_raw = row.get("发布日期") or ""
    url = str(row.get("原文链接") or "").strip()
    hint = str(row.get("影响提示") or "").strip()
    note = str(row.get("内部备注") or "").strip()

    if not title and not url:
        return None, ""  # 空行，静默跳过
    if title.startswith("示例"):
        return None, ""

    if len(title) < MIN_TITLE:
        return None, "标题太短（至少 %d 字）" % MIN_TITLE
    if len(title) > MAX_TITLE:
        return None, "标题太长（超过 %d 字），确认是不是粘错了整段" % MAX_TITLE
    if not org:
        return None, "发文机关空着"
    if level not in LEVELS:
        return None, "层级只能填「国家级」或「山东省」，当前是「%s」" % level

    d = parse_date(date_raw)
    if not d:
        return None, "发布日期认不出来：「%s」，请写成 2026-11-01" % str(date_raw).strip()

    if not re.match(r"^https?://", url, re.I):
        return None, "原文链接要以 http:// 或 https:// 开头"
    host = (urlparse(url).hostname or "").lower()
    if not host:
        return None, "原文链接不合法"
    if not allow_non_gov and not host.endswith(".gov.cn"):
        return None, "链接域名 %s 不是 .gov.cn，按口径只收官方站（确需收录加 --allow-non-gov）" % host

    ts = int(datetime.datetime(d.year, d.month, d.day).timestamp())
    return {
        "id": "",
        "title": title,
        "url": url,
        "level": level,
        "org": org,
        "ts": ts,
        "date": d.strftime("%Y-%m-%d"),
        "impact": hint,
        "impact_src": "manual" if hint else "",
        "source": "manual",
        "note": note,
        "added_at": datetime.date.today().strftime("%Y-%m-%d"),
    }, ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="只打印结果，不写文件")
    ap.add_argument("--check-url", action="store_true", help="联网验证链接能否打开（慢）")
    ap.add_argument("--allow-non-gov", action="store_true", help="允许非 .gov.cn 链接")
    args = ap.parse_args()

    rows, enc = read_rows(CSV_PATH)
    print("读入 %s（编码 %s，%d 行）" % (os.path.basename(CSV_PATH), enc, len(rows)))

    data = json.load(open(JSON_PATH, encoding="utf-8"))
    items = data.get("items", [])

    seen_url = {norm(x.get("url")) for x in items}
    seen_title = {norm(x.get("title")) for x in items}

    added, skipped, errors = [], [], []
    for i, row in enumerate(rows, start=2):  # 第 2 行起是数据
        try:
            item, err = check_row(row, i, args.allow_non_gov)
        except Exception as e:  # noqa: BLE001
            errors.append("第 %d 行：解析异常 %s" % (i, str(e)[:60]))
            continue
        if err:
            errors.append("第 %d 行：%s" % (i, err))
            continue
        if item is None:
            continue

        if norm(item["url"]) in seen_url:
            skipped.append("第 %d 行：链接已在库中 —— %s" % (i, item["title"][:28]))
            continue
        if norm(item["title"]) in seen_title:
            skipped.append("第 %d 行：标题已在库中 —— %s" % (i, item["title"][:28]))
            continue

        if args.check_url:
            try:
                sys.path.insert(0, HERE)
                import fetch_all as F
                ok, page_title = F.policy_url_alive(item["url"])
                if not ok:
                    errors.append("第 %d 行：链接打不开（页标题=%s）" % (i, (page_title or "空")[:16]))
                    continue
            except Exception as e:  # noqa: BLE001
                print("  [!] 跳过链接验证：%s" % str(e)[:50])

        seen_url.add(norm(item["url"]))
        seen_title.add(norm(item["title"]))
        added.append(item)

    print("\n新增 %d 条 / 跳过 %d 条 / 出错 %d 条" % (len(added), len(skipped), len(errors)))
    for s in skipped:
        print("  · 跳过  " + s)
    for e in errors:
        print("  ! 错误  " + e)

    if not added:
        print("\n没有要新增的条目，policies.json 未改动。")
        return

    merged = items + added
    merged.sort(key=lambda x: -(x.get("ts") or 0))
    for i, x in enumerate(merged):
        x["id"] = "pol%d" % (i + 1)
    data["items"] = merged

    print("\n合并后共 %d 条（其中人工补录 %d 条）"
          % (len(merged), sum(1 for x in merged if x.get("source") == "manual")))
    for x in added:
        print("  + %s | %s | %s" % (x["date"], x["org"], x["title"][:40]))

    if args.dry_run:
        print("\n--dry-run：未写入 policies.json。")
        return

    with open(JSON_PATH, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print("\n已写入 policies.json。接着跑：")
    print("  cd ../mini && python scripts/build_data.py     # 重建小程序数据与云端快照")


if __name__ == "__main__":
    main()
