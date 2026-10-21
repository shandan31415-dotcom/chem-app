#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
每日资讯聚合抓取脚本（纯标准库，无需安装任何依赖）

用法：
    python fetch.py            # 抓取并写入 data.json
    python fetch.py --out x.json

设计原则：
1. 任何单个源失败都不影响整体，失败信息写进对应分类的 error 字段；
2. 抓取失败时保留上一次的数据，不让文件变空；
3. 同一事件按标题指纹去重。
"""

import argparse
import html
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")

BASE = os.path.dirname(os.path.abspath(__file__))


# ---------------------------------------------------------------- 工具函数
def http_get(url, referer=None, timeout=25, retries=2):
    last = None
    for i in range(retries + 1):
        try:
            headers = {
                "User-Agent": UA,
                "Accept": "*/*",
                "Accept-Language": "zh-CN,zh;q=0.9",
            }
            if referer:
                headers["Referer"] = referer
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except Exception as e:  # noqa: BLE001
            last = e
            if i < retries:
                time.sleep(1.5 * (i + 1))
    raise last


TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"[ \t\u3000]+")


def clean_text(s, limit=None):
    if not s:
        return ""
    s = TAG_RE.sub(" ", str(s))
    s = html.unescape(s)
    s = s.replace("\r", " ").replace("\n", " ")
    s = WS_RE.sub(" ", s).strip()
    if limit and len(s) > limit:
        s = s[:limit].rstrip() + "…"
    return s


def fp(title):
    """标题指纹，用于跨源去重"""
    s = re.sub(r"[\s\u3000·,，。.、:：;；!！?？\"'“”‘’()（）\[\]【】\-—_|/\\]", "", str(title))
    return s[:36].lower()


def fmt_time(ts):
    if not ts:
        return ""
    now = time.time()
    lt = time.localtime(ts)
    today = time.localtime(now)[:3]
    if lt[:3] == today:
        return time.strftime("%H:%M", lt)
    diff_day = (now - ts) / 86400
    if diff_day < 2:
        return "昨天 " + time.strftime("%H:%M", lt)
    if diff_day < 7:
        return "%d天前" % int(diff_day)
    return time.strftime("%m-%d", lt)


# ---------------------------------------------------------------- 解析器
def parse_rss(raw, source):
    out = []
    root = ET.fromstring(raw)
    for it in root.iter("item"):
        title = clean_text(it.findtext("title"))
        link = (it.findtext("link") or "").strip()
        if not title or not link:
            continue
        desc = clean_text(it.findtext("description"), 110)
        ts = None
        p = (it.findtext("pubDate") or "").strip()
        if p:
            try:
                ts = int(parsedate_to_datetime(p).timestamp())
            except Exception:  # noqa: BLE001
                ts = None
        out.append({
            "title": title,
            "url": link,
            "summary": desc,
            "ts": ts,
            "source": source,
        })
    return out


def parse_wscn(raw, source):
    d = json.loads(raw.decode("utf-8", "ignore"))
    items = ((d.get("data") or {}).get("items")) or []
    out = []
    for x in items:
        if not isinstance(x, dict):
            continue
        title = clean_text(x.get("title") or x.get("content_text"))
        if not title:
            continue
        url = x.get("uri") or ""
        if url and not str(url).startswith("http"):
            url = "https://wallstreetcn.com" + str(url)
        out.append({
            "title": title,
            "url": url,
            "summary": clean_text(x.get("content_text"), 120) if x.get("title") else "",
            "ts": x.get("display_time"),
            "source": source,
        })
    return out


# ---------------------------------------------------------------- 抓新闻
def fetch_news(cfg):
    cats = []
    for s in cfg.get("news", []):
        if not s.get("enabled", True):
            continue
        cat = {"id": s["id"], "name": s["name"], "type": "news",
               "items": [], "error": None}
        try:
            raw = http_get(s["url"])
            if s.get("type") == "wscn":
                items = parse_wscn(raw, s.get("source", ""))
            else:
                items = parse_rss(raw, s.get("source", ""))
            if not items:
                raise ValueError("解析到 0 条内容（接口格式可能已变化）")
            items.sort(key=lambda x: (x.get("ts") or 0), reverse=True)
            cat["items"] = items[:40]
        except Exception as e:  # noqa: BLE001
            cat["error"] = "%s: %s" % (type(e).__name__, str(e)[:80])
            print("  [!] %s 抓取失败: %s" % (s["name"], cat["error"]))
        cats.append(cat)
    return cats


# ---------------------------------------------------------------- 抓价格
PRICE_FIELDS = "f2,f3,f4,f12,f13,f14"


def fetch_prices(pcfg):
    cat = {"id": "prices", "name": pcfg.get("name", "化工价格"),
           "type": "prices", "groups": [], "error": None}
    try:
        allitems = []
        for mk, exname in pcfg["markets"].items():
            for pn in range(1, 8):
                u = ("https://push2.eastmoney.com/api/qt/clist/get"
                     "?pn=%d&pz=100&po=0&np=1&fltt=2&invt=2&fid=f12&fs=%s&fields=%s"
                     % (pn, mk, PRICE_FIELDS))
                raw = http_get(u, referer="https://quote.eastmoney.com/", retries=1)
                d = json.loads(raw.decode("utf-8", "ignore"))
                its = (d.get("data") or {}).get("diff") or []
                if not its:
                    break
                for x in its:
                    x["_ex"] = exname
                allitems.extend(its)
                if len(its) < 100:
                    break
        if not allitems:
            raise ValueError("未取到任何行情数据")

        by_name = {}
        for x in allitems:
            nm = str(x.get("f14") or "")
            if nm.endswith("主连"):
                by_name.setdefault(nm[:-2], x)
        # 代码兜底：部分品种名不带"主连"后缀差异，用代码字典再补一次
        aliases = pcfg.get("aliases", {})

        groups = []
        for g in pcfg.get("groups", []):
            rows = []
            for want in g["items"]:
                hit = by_name.get(want)
                if hit is None:
                    for alt in aliases.get(want, []):
                        if alt in by_name:
                            hit = by_name[alt]
                            break
                if hit is None:
                    continue
                price = hit.get("f2")
                chg = hit.get("f3")
                if not isinstance(price, (int, float)) or price <= 0:
                    continue
                rows.append({
                    "name": want,
                    "code": str(hit.get("f12") or ""),
                    "ex": hit["_ex"],
                    "price": price,
                    "chg": chg if isinstance(chg, (int, float)) else None,
                    "chg_amt": hit.get("f4") if isinstance(hit.get("f4"), (int, float)) else None,
                })
            if rows:
                groups.append({"name": g["name"], "items": rows})
        if not groups:
            raise ValueError("行情接口可用，但没有匹配到化工品种")
        cat["groups"] = groups
        cat["count"] = sum(len(g["items"]) for g in groups)
    except Exception as e:  # noqa: BLE001
        cat["error"] = "%s: %s" % (type(e).__name__, str(e)[:80])
        print("  [!] 价格抓取失败: %s" % cat["error"])
    return cat


# ---------------------------------------------------------------- 主流程
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(BASE, "data.json"))
    ap.add_argument("--sources", default=os.path.join(BASE, "sources.json"))
    args = ap.parse_args()

    with open(args.sources, encoding="utf-8") as f:
        cfg = json.load(f)

    print("开始抓取…")
    cats = []
    pcfg = cfg.get("prices") or {}
    if pcfg.get("enabled", True):
        print(" - 化工价格")
        cats.append(fetch_prices(pcfg))
    cats.extend(fetch_news(cfg))

    # 跨分类去重：同一标题只保留第一次出现
    seen = set()
    for c in cats:
        if c.get("type") != "news":
            continue
        keep = []
        for it in c["items"]:
            k = fp(it["title"])
            if k and k in seen:
                continue
            seen.add(k)
            it["time_text"] = fmt_time(it.get("ts"))
            keep.append(it)
        c["items"] = keep

    now = int(time.time())
    payload = {
        "generated_at": now,
        "generated_at_text": time.strftime("%Y-%m-%d %H:%M", time.localtime(now)),
        "categories": cats,
    }

    ok_cats = [c for c in cats if (c.get("items") or c.get("groups"))]
    if not ok_cats:
        print("\n[!] 所有源都失败了，保留旧文件不动。")
        return 1

    # 部分失败时，把上一次的同类内容补进来，避免打开看到空白
    if os.path.exists(args.out):
        try:
            with open(args.out, encoding="utf-8") as f:
                old = json.load(f)
            oldmap = {c["id"]: c for c in old.get("categories", [])}
            for c in cats:
                if c.get("error") and c["id"] in oldmap:
                    o = oldmap[c["id"]]
                    if c.get("type") == "news":
                        c["items"] = o.get("items", [])
                        c["stale"] = True
                    else:
                        c["groups"] = o.get("groups", [])
                        c["stale"] = True
        except Exception:  # noqa: BLE001
            pass

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    print("完成 → %s" % args.out)
    for c in cats:
        n = c.get("count") if c.get("type") == "prices" else len(c.get("items") or [])
        print("   %-8s %3s 条 %s" % (c["name"], n, "（沿用上次数据）" if c.get("stale") else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
