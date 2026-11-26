# -*- coding: utf-8 -*-
"""把 chem-app/data/*.json 转成小程序可直接 require 的 JS 模块。

设计铁律：源数据只有一份（chem-app/data），本脚本单向生成，绝不反向写回。
任何人工修正都改 chem-app 的源 JSON，然后重跑本脚本。

用法：
    python scripts/build_data.py
"""
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
MINI = os.path.dirname(HERE)
SRC = os.path.join(os.path.dirname(MINI), "chem-app", "data")
DST = os.path.join(MINI, "data")

# 行情条目里只保留展示必需字段：剥离 news（内容聚合风险 + 外链打不开）
PRICE_ITEM_KEYS = ("name", "group", "code", "ex", "price", "chg", "chg_amt", "src")


def load(name):
    with open(os.path.join(SRC, name + ".json"), encoding="utf-8") as f:
        return json.load(f)


def dump(name, obj):
    """输出 module.exports = {...};  用 ensure_ascii=False 保留中文。"""
    text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    path = os.path.join(DST, name + ".js")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("module.exports=" + text + ";\n")
    return len(text.encode("utf-8")), path


def slim_prices(p):
    groups = []
    for g in p.get("groups", []):
        items = []
        for it in g.get("items", []):
            items.append({k: it[k] for k in PRICE_ITEM_KEYS if k in it})
        groups.append({"name": g.get("name", ""), "items": items})
    return {
        "updated_at": p.get("updated_at"),
        "updated_at_text": p.get("updated_at_text", ""),
        "source": p.get("source", ""),
        "count": p.get("count") or sum(len(g["items"]) for g in groups),
        "groups": groups,
    }


def slim_history(h, keep=250):
    """走势图只需要「日期 + 收盘价」。

    刻意丢掉开高低收与成交量：一是体积从 284KB 降到 ~90KB，
    二是小程序里只画一条收盘折线，不出现 K 线蜡烛图——审核上更安全。
    """
    out = {}
    for name, rows in (h.get("series") or {}).items():
        out[name] = [[r[0][5:], r[2]] for r in rows[-keep:]]  # 只留 MM-DD，省字节
    return {"updated_at": h.get("updated_at"), "series": out,
            "sources": h.get("sources") or {}}


def dump_cloud(policies, prices, meta):
    """生成云开发同步用的快照，落到 chem-app/data/cloud_snapshot.json。

    只放「每天都在变」的三样：政策、参考价、数据日期。
    园区 / 企业 / 品类是人工整理的稳定数据，留在代码包里——省云库容量，
    也避免「云端旧数据覆盖刚发的新包」这种乱子。

    云函数 cloudfunctions/syncData 每天把它拉进云数据库，
    小程序启动时从云库读，读不到就退回包内数据。
    """
    manual = sum(1 for x in policies.get("items", []) if x.get("source") == "manual")

    # 数据日期取三份里最新的那个：meta.json 只反映「整条管线最后一次跑通」，
    # 政策/行情单独更新时它会落后，直接用会让用户看到过期日期。
    cands = [
        (int(meta.get("updated_at") or 0), meta.get("updated_at_text", "")),
        (int(policies.get("updated_at") or 0), policies.get("updated_at_text", "")),
        (int(prices.get("updated_at") or 0), prices.get("updated_at_text", "")),
    ]
    mts, mtext = max(cands, key=lambda x: x[0])

    snap = {
        "schema": 1,
        "meta": {"updated_at": mts, "updated_at_text": mtext},
        "policies": {
            "updated_at": policies.get("updated_at"),
            "updated_at_text": policies.get("updated_at_text", ""),
            "items": policies.get("items", []),
        },
        "prices": prices,
        "manual_count": manual,
        "note": "由 mini/scripts/build_data.py 从 chem-app/data 单向生成，请勿手改。",
    }
    path = os.path.join(SRC, "cloud_snapshot.json")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(snap, f, ensure_ascii=False, indent=1)
    return os.path.getsize(path), len(snap["policies"]["items"])


def dump_catalog(parks):
    """企业与园区名录的云端副本，落到 chem-app/data/catalog.json。

    这两样原来只存在于代码包里——加一家会员企业、改一个园区的主导产业，
    都得改代码重新发版。现在额外生成一份，云函数把它灌进云数据库的
    catalog 集合，小程序优先读云库。

    协会在云开发控制台的「数据库 → catalog → latest」里直接改 cities 里的
    JSON，改完小程序下拉刷新就能看到，不用发版、不用找开发。

    只放名录本身（cities 及其下的 parks / enterprises）和计数，
    不放 note 那段长说明，少推几十 KB。
    """
    doc = {
        "updated_at": parks.get("updated_at"),
        "updated_at_text": parks.get("updated_at_text", ""),
        "counts": parks.get("counts", {}),
        "cities": parks.get("cities", []),
    }
    path = os.path.join(SRC, "catalog.json")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))
    return os.path.getsize(path), len(doc["cities"])


def build_mapmeta(sd):
    """把 label 坐标换算成百分比，供 WXML 绝对定位叠字用（图里不烧字）。"""
    m = re.match(r"\s*0\s+0\s+([\d.]+)\s+([\d.]+)", sd.get("viewBox", "0 0 320 205.5"))
    w = float(m.group(1)) if m else 320.0
    h = float(m.group(2)) if m else 205.5
    cities = []
    for code, c in sd.get("cities", {}).items():
        lx, ly = c.get("label", [0, 0])
        cities.append({
            "code": code,
            "name": c.get("name", ""),
            "x": round(lx / w * 100, 2),
            "y": round(ly / h * 100, 2),
            "fs": c.get("fs", 9.2),
            "plate": 1 if c.get("plate") else 0,
            "vert": 1 if c.get("vert") else 0,
        })
    return {"viewBox": sd.get("viewBox", ""), "w": w, "h": h, "cities": cities}


def main():
    os.makedirs(DST, exist_ok=True)

    parks = load("parks")
    cats = load("categories")
    boards = load("boards")
    chain = load("chain")
    industry = load("industry")
    sdmap = load("sdmap")
    prices = slim_prices(load("prices"))
    hist = slim_history(load("prices_history"))
    policies = load("policies")
    meta = load("meta")

    # 政策：补一个字数友好的日期串，页面直接用，避免每个页面都算
    for it in policies.get("items", []):
        ts = it.get("ts")
        if ts:
            import datetime
            it["date"] = datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d")

    total = 0
    count = 0
    for name, obj in [
        ("parks", parks),
        ("categories", cats),
        ("boards", boards),
        ("chain", chain),
        ("industry", industry),
        ("sdmap", sdmap),
        ("prices", prices),
        ("hist", hist),
        ("policies", policies),
        ("meta", meta),
        ("mapmeta", build_mapmeta(sdmap)),
    ]:
        size, path = dump(name, obj)
        total += size
        count += 1
        print("  %-12s %7.1f KB" % (name + ".js", size / 1024.0))

    print("\n生成完毕：%d 个文件，合计 %.1f KB" % (count, total / 1024.0))

    cloud_size, cloud_pol = dump_cloud(policies, prices, meta)
    print("  云端快照     %7.1f KB  （%d 条政策，供云函数同步）"
          % (cloud_size / 1024.0, cloud_pol))

    cat_size, cat_cities = dump_catalog(parks)
    print("  云端名录     %7.1f KB  （%d 个地市的企业与园区，云库可改，改完不用发版）"
          % (cat_size / 1024.0, cat_cities))

    # 自检：行情必须已剥离 news
    leaked = [it["name"] for g in prices["groups"] for it in g["items"] if "news" in it]
    assert not leaked, "行情仍残留 news 字段：%s" % leaked
    print("自检通过：行情已剥离 news / 园区 %d 家 / 品类 %d 个 / 政策 %d 条" % (
        parks["counts"]["parks"], len(cats["items"]), len(policies["items"])))


if __name__ == "__main__":
    main()
