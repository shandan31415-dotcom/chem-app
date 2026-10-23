#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据断言脚本（纯标准库）。每批次回归都跑它。

用法：
    python scripts/qa.py            # 已知问题记 XFAIL，其余必须 PASS；有真失败退出码 1
    python scripts/qa.py --strict   # XFAIL 也算失败（P5 全量回归用）

XFAIL 只允许放「本批次已知、下一批次必然修掉」的问题，且必须写清对应差距编号。
每批次结束要检查 XFAIL 是否按计划缩小。
"""

import json
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, "data")

# 已知问题 -> 对应差距编号。P5 必须清空。
XFAIL = {}

# 头部企业允许 <3 家的白名单（品类 id -> (下限, 原因)）。必须逐步清空。
LEADER_WHITELIST = {}


def load(name):
    with open(os.path.join(DATA, name), encoding="utf-8") as f:
        return json.load(f)


def try_load(name):
    try:
        return load(name), None
    except Exception as e:  # noqa: BLE001
        return None, e


def blank(v):
    if v is None:
        return True
    if isinstance(v, str):
        return not v.strip()
    if isinstance(v, (list, dict)):
        return len(v) == 0
    return False


def all_prices(d):
    out = []
    for g in d.get("groups", []):
        for i in g.get("items", []):
            i = dict(i)
            i["group"] = g.get("name")
            out.append(i)
    return out


def all_news(d):
    out = []
    for b in d.get("blocks", []):
        for i in b.get("items", []):
            i = dict(i)
            i["block"] = b.get("name")
            out.append(i)
    return out


def all_ents(p):
    """返回 [(地市, 园区名或 None, 企业)]"""
    out = []
    for c in p.get("cities", []):
        for pk in c.get("parks", []):
            for e in pk.get("enterprises", []):
                out.append((c.get("name"), pk.get("name"), e))
        for e in c.get("enterprises", []):
            out.append((c.get("name"), None, e))
    return out


# ------------------------------------------------------------------ 断言
def a1_files():
    names = ["meta.json", "overview.json", "news.json", "parks.json", "categories.json",
             "prices.json", "prices_history.json", "policies.json", "sdmap.json", "industry.json",
             "boards.json"]
    bad = []
    for n in names:
        if n == "overview.json":
            continue  # 首页由其它库实时挑选，不单独存文件（PRD 5.1「不单独维护」）
        p = os.path.join(DATA, n)
        if not os.path.exists(p):
            bad.append(n + " 缺失")
            continue
        d, err = try_load(n)
        if d is None:
            bad.append("%s 解析失败 %s" % (n, err))
            continue
        if not isinstance(d.get("updated_at"), (int, float)):
            bad.append(n + " 无 updated_at")
    return (not bad), ("全部含 updated_at" if not bad else "; ".join(bad))


def a2_city_fields():
    d, err = try_load("parks.json")
    if d is None:
        return False, "parks.json 不可用: %s" % err
    cities = d.get("cities", [])
    if len(cities) != 16:
        return False, "地市 %d 个（应 16）" % len(cities)
    bad = []
    for c in cities:
        for f in ["tagline", "intro", "clusters", "chems", "angle"]:
            if blank(c.get(f)):
                bad.append("%s.%s 空" % (c.get("name"), f))
        if len(c.get("clusters") or []) < 3:
            bad.append("%s.clusters<3" % c.get("name"))
        if len(c.get("chems") or []) < 3:
            bad.append("%s.chems<3" % c.get("name"))
    return (not bad), ("16 市五字段齐全" if not bad else "; ".join(bad[:8]))


def a3_scale():
    d, err = try_load("parks.json")
    if d is None:
        return False, "parks.json 不可用: %s" % err
    ents = all_ents(d)
    parks = sum(len(c.get("parks", [])) for c in d.get("cities", []))
    names = [e.get("name") for _, _, e in ents]
    dups = sorted({n for n in names if names.count(n) > 1})
    bad = []
    if len(ents) < 150:
        bad.append("企业 %d（应 ≥150）" % len(ents))
    if parks < 30:
        bad.append("园区 %d（应 ≥30）" % parks)
    if dups:
        bad.append("重名企业 " + "、".join(dups[:5]))
    detail = "企业 %d / 园区 %d / 重名 %d" % (len(ents), parks, len(dups))
    return (not bad), (detail if not bad else "; ".join(bad))


def a4_cats():
    d, err = try_load("categories.json")
    if d is None:
        return False, "categories.json 不可用: %s" % err
    items = d.get("items", [])
    bad = []
    if len(items) < 70:
        bad.append("品类 %d（应 ≥70）" % len(items))
    six = ["cost", "demand", "supply", "shandong", "flow", "logistics"]
    for it in items:
        for f in six:
            if blank(it.get(f)):
                bad.append("%s.%s 空" % (it.get("id"), f))
        low = LEADER_WHITELIST.get(it.get("id"), (3, ""))[0]
        if len(it.get("leaders") or []) < low:
            bad.append("%s 头部企业 %d<3" % (it.get("id"), len(it.get("leaders") or [])))
    detail = "品类 %d，六问齐全率 %d%%，头部<3 的 %d 个" % (
        len(items),
        round(100 * sum(1 for it in items if all(not blank(it.get(f)) for f in six)) / max(1, len(items))),
        sum(1 for it in items if len(it.get("leaders") or []) < 3),
    )
    return (not bad), (detail if not bad else "; ".join(bad[:8]))


def a5_price_links():
    cd, e1 = try_load("categories.json")
    pd, e2 = try_load("prices.json")
    if cd is None or pd is None:
        return False, "数据不可用: %s %s" % (e1, e2)
    names = {p.get("name") for p in all_prices(pd)}
    bad = []
    for it in cd.get("items", []):
        for n in it.get("price_links") or []:
            if n not in names:
                bad.append("%s -> %s 不存在" % (it.get("id"), n))
    linked = sum(1 for it in cd.get("items", []) if it.get("price_links"))
    detail = "price_links 有效，%d/%d 个品类有行情入口" % (linked, len(cd.get("items", [])))
    return (not bad), (detail if not bad else "; ".join(bad[:6]))


def a6_prices():
    pd, e1 = try_load("prices.json")
    hd, e2 = try_load("prices_history.json")
    if pd is None or hd is None:
        return False, "数据不可用: %s %s" % (e1, e2)
    ps = all_prices(pd)
    bad = []
    if len(ps) < 23:
        bad.append("品种 %d（应 23）" % len(ps))
    series = hd.get("series", {})
    for p in ps:
        if not isinstance(p.get("price"), (int, float)) or p["price"] <= 0:
            bad.append("%s 无价格" % p.get("name"))
        if not isinstance(p.get("chg"), (int, float)):
            bad.append("%s 无涨跌幅" % p.get("name"))
        if len(series.get(p.get("name")) or []) < 30:
            bad.append("%s K线 %d<30" % (p.get("name"), len(series.get(p.get("name")) or [])))
    minbar = min((len(series.get(p.get("name")) or []) for p in ps), default=0)
    detail = "%d 品种，K线最少 %d 根" % (len(ps), minbar)
    return (not bad), (detail if not bad else "; ".join(bad[:6]))


def a7_policies():
    d, err = try_load("policies.json")
    if d is None:
        return False, "policies.json 不可用: %s" % err
    items = d.get("items", [])
    bad = []
    for lv in ["国家级", "山东省"]:
        sub = [p for p in items if p.get("level") == lv]
        if not sub:
            bad.append("%s 0 条" % lv)
        for p in sub:
            for f in ["title", "org", "url"]:
                if blank(p.get(f)):
                    bad.append("%s 缺 %s" % (p.get("id"), f))
            if not p.get("ts"):
                bad.append("%s 缺日期" % p.get("id"))
    detail = "国家 %d / 山东 %d" % (
        sum(1 for p in items if p.get("level") == "国家级"),
        sum(1 for p in items if p.get("level") == "山东省"))
    return (not bad), (detail if not bad else "; ".join(bad[:6]))


def a8_news_blocks():
    d, err = try_load("news.json")
    if d is None:
        return False, "news.json 不可用: %s" % err
    cnt = {b.get("name"): len(b.get("items") or []) for b in d.get("blocks", [])}
    bad = []
    for k in ["全球", "全国", "山东"]:
        if k not in cnt:
            bad.append("缺板块 " + k)
        elif cnt[k] < 3:
            bad.append("%s %d<3" % (k, cnt[k]))
    detail = " / ".join("%s %d" % (k, cnt.get(k, 0)) for k in ["全球", "全国", "山东"])
    return (not bad), (detail if not bad else detail)


def a9_price_news():
    pd, err = try_load("prices.json")
    if pd is None:
        return False, "prices.json 不可用: %s" % err
    ps = all_prices(pd)
    withn = [p for p in ps if p.get("news")]
    detail = "有新闻的品种 %d/%d" % (len(withn), len(ps))
    return (len(withn) >= 15), detail


def a10_industry():
    d, err = try_load("industry.json")
    if d is None:
        return False, "industry.json 不可用: %s" % err
    # 合法地市 code（与 parks.json 一致）
    pd, e2 = try_load("parks.json")
    if pd is None:
        return False, "parks.json 不可用: %s" % e2
    valid_codes = {c.get("code") for c in pd.get("cities", [])}
    views = d.get("views", {})
    bad = []
    for vk in ["cluster", "layout"]:
        v = views.get(vk)
        if not v:
            bad.append("缺视图 " + vk)
            continue
        legend = v.get("legend") or []
        if not legend:
            bad.append(vk + " 无 legend")
        # legend key 唯一 + 有 color
        keys = [l.get("key") for l in legend]
        if len(keys) != len(set(keys)):
            bad.append(vk + " legend key 重复")
        for l in legend:
            if not l.get("color") or not l.get("name"):
                bad.append(vk + " legend 缺 color/name")
        cities = v.get("cities") or {}
        # 每个地市都应有归属，且 code 合法、标签在 legend 内
        for code, tags in cities.items():
            if code not in valid_codes:
                bad.append(vk + " 非法 code " + str(code))
            if not tags or not isinstance(tags, list):
                bad.append(vk + " %s 无标签" % code)
            else:
                for t in tags:
                    if t not in keys:
                        bad.append(vk + " %s 标签 %s 不在 legend" % (code, t))
        # 覆盖度：16 地市都应出现
        missing = valid_codes - set(cities.keys())
        if missing:
            bad.append(vk + " 漏地市 " + ",".join(sorted(missing)))
    detail = "两视图齐全，地市覆盖 %d/%d" % (
        len(valid_codes - ({c for c in views.get('cluster', {}).get('cities', {})} |
                           {c for c in views.get('layout', {}).get('cities', {})})),
        len(valid_codes))
    return (not bad), (detail if not bad else "; ".join(bad[:8]))


def a11_boards():
    bd, e1 = try_load("boards.json")
    cd, e2 = try_load("categories.json")
    if bd is None or cd is None:
        return False, "数据不可用: %s %s" % (e1, e2)
    boards = bd.get("boards", [])
    all_ids = {it.get("id") for it in cd.get("items", [])}
    bad = []
    if len(boards) != 7:
        bad.append("板块 %d（应 7）" % len(boards))
    # 七大板块名称（PPT 第 17 页口径）
    need = {"炼化", "化肥", "无机化工", "有机化工", "橡胶加工", "精细化工", "合成材料"}
    names = {b.get("name") for b in boards}
    if names != need:
        bad.append("板块名不符：%s" % (names - need or need - names))
    assigned = set()
    for b in boards:
        if not b.get("key") or not b.get("intro"):
            bad.append("%s 缺 key/intro" % b.get("name"))
        if len(b.get("leaders") or []) < 3:
            bad.append("%s 标杆企业 <3" % b.get("name"))
        if len(b.get("cat_ids") or []) < 1:
            bad.append("%s 无品类" % b.get("name"))
        for cid in b.get("cat_ids") or []:
            if cid not in all_ids:
                bad.append("%s 引用了不存在的品类 %s" % (b.get("name"), cid))
            assigned.add(cid)
    missing = all_ids - assigned
    if missing:
        bad.append("未归类的品类 " + ",".join(sorted(missing)[:6]))
    if len(assigned) != len(all_ids):
        bad.append("品类重复归类")
    detail = "七板块齐全，品类覆盖 %d/%d" % (len(assigned), len(all_ids))
    return (not bad), (detail if not bad else "; ".join(bad[:8]))


def a12_chain():
    cd, e1 = try_load("chain.json")
    cats, e2 = try_load("categories.json")
    if cd is None or cats is None:
        return False, "数据不可用: %s %s" % (e1, e2)
    stages = cd.get("stages", [])
    all_ids = {it.get("id") for it in cats.get("items", [])}
    bad = []
    if len(stages) != 3:
        bad.append("产业链环节 %d（应 3）" % len(stages))
    need = {"up", "mid", "down"}
    keys = {s.get("key") for s in stages}
    if keys != need:
        bad.append("环节 key 不符：%s" % (keys - need or need - keys))
    assigned = set()
    for s in stages:
        if not s.get("name") or not s.get("desc"):
            bad.append("%s 缺 name/desc" % s.get("key"))
        for cid in s.get("cats") or []:
            if cid not in all_ids:
                bad.append("%s 引用了不存在的品类 %s" % (s.get("key"), cid))
            if cid in assigned:
                bad.append("品类 %s 重复归类" % cid)
            assigned.add(cid)
    missing = all_ids - assigned
    if missing:
        bad.append("未归类的品类 " + ",".join(sorted(missing)[:6]))
    detail = "三段齐全，品类覆盖 %d/%d" % (len(assigned), len(all_ids))
    return (not bad), (detail if not bad else "; ".join(bad[:8]))


CHECKS = [
    ("1 数据文件含 updated_at", a1_files),
    ("2 地市五字段齐全", a2_city_fields),
    ("3 企业/园区规模与重名", a3_scale),
    ("4 品类六问与头部企业", a4_cats),
    ("5 品类→行情指向有效", a5_price_links),
    ("6 行情价格与K线", a6_prices),
    ("7 政策两级齐全", a7_policies),
    ("8 资讯三板块条数", a8_news_blocks),
    ("9 品种关联新闻覆盖", a9_price_news),
    ("10 产业格局数据完整", a10_industry),
    ("11 七大板块归类完整", a11_boards),
    ("12 产业链三段归类完整", a12_chain),
]


def run_all():
    """返回 [(名称, 状态 PASS/FAIL/XFAIL, 说明)]，供 qa.py 与单元测试共用"""
    out = []
    for name, fn in CHECKS:
        key = name.split(" ")[0]
        try:
            ok, detail = fn()
        except Exception as e:  # noqa: BLE001
            ok, detail = False, "断言抛异常: %r" % (e,)
        if ok:
            out.append((name, "PASS", detail))
        elif key in XFAIL:
            out.append((name, "XFAIL", "%s | 已知: %s" % (detail, XFAIL[key])))
        else:
            out.append((name, "FAIL", detail))
    return out


def main(argv):
    strict = "--strict" in argv
    rows = run_all()
    w = max(len(r[0]) for r in rows)
    fails = 0
    xfails = 0
    for name, st, detail in rows:
        print("%-6s %-*s %s" % (st, w, name, detail))
        if st == "FAIL":
            fails += 1
        elif st == "XFAIL":
            xfails += 1
    print("-" * 60)
    print("通过 %d / 共 %d，XFAIL %d，失败 %d" % (
        len(rows) - fails - xfails, len(rows), xfails, fails))
    if fails:
        return 1
    if strict and xfails:
        print("--strict：存在 XFAIL，视为失败")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
