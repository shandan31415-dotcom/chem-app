# -*- coding: utf-8 -*-
"""把补充数据合并进 data/parks.json 与 data/categories.json
运行： python scripts/build_enrich.py
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
sys.path.insert(0, HERE)

from _data_city import CITY_META          # noqa: E402
from _data_ent import CITY_ENTS, NEW_PARKS, to_ent  # noqa: E402
from _data_cat import VAR_ID, SD, EXTRA, GROUPS     # noqa: E402

PRICE_MAP = {
    "pp": "聚丙烯", "pe": "聚乙烯", "pvc": "PVC", "sm": "苯乙烯",
    "chloralkali": "烧碱", "pta": "PTA", "meg": "乙二醇",
    "polyester": "短纤", "methanol": "甲醇", "fertilizer": "尿素",
    "soda": "纯碱", "coke": "焦炭", "sr": "天然橡胶",
}

# 品种全名过长或简称有歧义时，指定展示名
NAME_OVERRIDE = {
    "二甲基硅氧烷混合环体": "有机硅 DMC",
    "甲苯二异氰酸酯": "甲苯二异氰酸酯（TDI）",
    "精对苯二甲酸": "精对苯二甲酸（PTA）",
    "二氟甲烷": "二氟甲烷（R32）",
    "五氟乙烷/四氟乙烷": "R125 / R134a",
    "己内酰胺": "己内酰胺（CPL）",
}


def build_parks():
    path = os.path.join(DATA, "parks.json")
    d = json.load(open(path, encoding="utf-8"))
    cities = d["cities"]

    # 1) 地市产业信息
    for c in cities:
        m = CITY_META.get(c["code"])
        if not m:
            continue
        c["region"] = m["region"]
        c["intro"] = m["intro"]
        c["scale"] = m["scale"]
        c["clusters"] = m["clusters"]
        c["chems"] = m["chems"]
        c["angle"] = m["angle"]

    by_code = {c["code"]: c for c in cities}

    # 2) 补充园区
    for pid, code, name, district, typ, level, intro, ents in NEW_PARKS:
        c = by_code.get(code)
        if not c:
            continue
        if any(p["id"] == pid for p in c["parks"]):
            continue
        c["parks"].append({
            "id": pid, "name": name, "district": district, "type": typ,
            "level": level, "intro": intro,
            "enterprises": [to_ent(t) for t in ents],
        })

    # 3) 市级重点企业（去重）
    for code, rows in CITY_ENTS.items():
        c = by_code.get(code)
        if not c:
            continue
        exists = set()
        for p in c["parks"]:
            for e in p.get("enterprises", []):
                exists.add(e["name"])
        for e in c.get("enterprises", []):
            exists.add(e["name"])
        for t in rows:
            if t[0] in exists:
                continue
            c.setdefault("enterprises", []).append(to_ent(t))
            exists.add(t[0])

    # 4) 统计与署名
    d["updated_at_text"] = "2026-10-21"
    d["source"] = "人工整理 + 资料库《山东化工产业地图》《化工品种速查手册》"
    d["note"] = ("以地市为单位的化工产业与企业整理，不限高端化工，覆盖全省化工主要企业。" 
                 "园区归属、产品范围为人工整理，标注「待核」的条目建议以官方公示核对；"
                 "本名录为「重点/代表性企业」，不是全量工商名录。"
                 "企业动态由资讯流自动匹配，匹配不到会明确显示「暂无收录」，不做编造。")
    tot_p = sum(len(c["parks"]) for c in cities)
    tot_e = sum(len(p["enterprises"]) for c in cities for p in c["parks"]) + \
        sum(len(c.get("enterprises", [])) for c in cities)
    d["counts"] = {"cities": len(cities), "parks": tot_p, "ents": tot_e}
    json.dump(d, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("parks.json ->  地市 %d / 园区 %d / 企业 %d" % (len(cities), tot_p, tot_e))


def build_cats():
    path = os.path.join(DATA, "categories.json")
    d = json.load(open(path, encoding="utf-8"))
    items = {i["id"]: i for i in d["items"]}

    # A. 从品种速查手册生成的条目
    src = json.load(open(os.path.join(HERE, "varieties_src.json"), encoding="utf-8"))
    added = 0
    for v in src:
        cid = VAR_ID.get(v["n"], "?")
        if not cid:
            continue  # 并入已有品类
        if cid in items:
            continue
        # 名称：短名直接用，长名用行业简称
        name = NAME_OVERRIDE.get(v["n"])
        if not name:
            name = v["n"]
            abbr = v.get("a", "")
            if len(name) > 9 and abbr and abbr != name:
                name = abbr
        abbr = v.get("a", "")
        products = [x.strip() for x in abbr.split("/") if x.strip()]
        if v["n"] not in products:
            products.insert(0, v["n"])
        leaders = []
        for seg in (v.get("p") or "").split("、"):
            seg = seg.strip()
            if seg:
                leaders.append({"name": seg, "note": ""})
        item = {
            "id": cid,
            "name": name,
            "one_line": v.get("t", ""),
            "cost": v.get("u", ""),
            "demand": v.get("d", ""),
            "supply": v.get("g", ""),
            "shandong": SD.get(cid, ""),
            "flow": v.get("f", ""),
            "logistics": v.get("h", ""),
            "products": products,
            "leaders": leaders,
            "price_links": [PRICE_MAP[cid]] if cid in PRICE_MAP else [],
        }
        items[cid] = item
        added += 1

    # B. 手工补写（山东特色）
    for it in EXTRA:
        if it["id"] in items:
            continue
        it = dict(it)
        it.setdefault("price_links", [PRICE_MAP[it["id"]]] if it["id"] in PRICE_MAP else [])
        items[it["id"]] = it
        added += 1

    # C. 补行情链接到原有品类
    for cid in list(items):
        it = items[cid]
        if not it.get("price_links") and cid in PRICE_MAP:
            it["price_links"] = [PRICE_MAP[cid]]

    # D. 分组（丢掉不存在的 id）
    groups = []
    used = set()
    for g in GROUPS:
        keep = [x for x in g["items"] if x in items]
        if keep:
            groups.append({"name": g["name"], "items": keep})
            used.update(keep)
    rest = [k for k in items if k not in used]
    if rest:
        groups.append({"name": "其他", "items": rest})

    flat = []
    for g in groups:
        for cid in g["items"]:
            flat.append(items[cid])
    d["groups"] = groups
    d["items"] = flat
    d["updated_at_text"] = "2026-10-21"
    d["note"] = ("品类知识为人工整理，品种口径参考资料库《化工品种速查手册》，"
                 "行业变化快，发现出入请指出，我改。")
    json.dump(d, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("categories.json ->  分组 %d / 品类 %d（新增 %d）" % (len(groups), len(flat), added))


if __name__ == "__main__":
    build_parks()
    build_cats()
