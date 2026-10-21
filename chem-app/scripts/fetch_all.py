#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
高端化工行业认知 App · 数据采集
纯标准库，无需安装依赖。

产出：
  data/prices.json          行情快照
  data/prices_history.json  各品种日线（K线）
  data/news.json            资讯（全球/全国/山东）
  data/policies.json        政策（国家级/山东省）
"""

import json
import os
import re
import html
import time
import urllib.request
import urllib.error
from email.utils import parsedate_to_datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, "data")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")

os.makedirs(DATA, exist_ok=True)


# ---------------------------------------------------------------- 基础
def http_get(url, referer=None, timeout=25, retries=2):
    last = None
    for i in range(retries + 1):
        try:
            h = {"User-Agent": UA, "Accept": "*/*", "Accept-Language": "zh-CN,zh;q=0.9"}
            if referer:
                h["Referer"] = referer
            req = urllib.request.Request(url, headers=h)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            last = e
            if i < retries:
                time.sleep(1.2 * (i + 1))
    raise last


TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"[ \t\u3000]+")


def clean(s, limit=None):
    if not s:
        return ""
    s = TAG_RE.sub(" ", str(s))
    s = html.unescape(s).replace("\r", " ").replace("\n", " ")
    s = WS_RE.sub(" ", s).strip()
    if limit and len(s) > limit:
        s = s[:limit].rstrip() + "…"
    return s


def save(name, obj):
    p = os.path.join(DATA, name)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
    print("  -> %s (%.1f KB)" % (name, os.path.getsize(p) / 1024))


def load(name, default):
    p = os.path.join(DATA, name)
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return default


# ---------------------------------------------------------------- 行情
# 品种名 -> (分组, 交易所market, 别名)
PRODUCTS = [
    ("原油", "原油与油品"), ("燃料油", "原油与油品"), ("液化石油气", "原油与油品"),
    ("沥青", "原油与油品"), ("低硫燃料油", "原油与油品"),
    ("聚乙烯", "聚烯烃与氯碱"), ("聚丙烯", "聚烯烃与氯碱"), ("PVC", "聚烯烃与氯碱"),
    ("苯乙烯", "聚烯烃与氯碱"), ("烧碱", "聚烯烃与氯碱"),
    ("对二甲苯", "聚酯产业链"), ("PTA", "聚酯产业链"), ("乙二醇", "聚酯产业链"),
    ("短纤", "聚酯产业链"), ("瓶片", "聚酯产业链"),
    ("甲醇", "煤化工与建材"), ("尿素", "煤化工与建材"), ("纯碱", "煤化工与建材"),
    ("玻璃", "煤化工与建材"), ("焦炭", "煤化工与建材"), ("焦煤", "煤化工与建材"),
    ("天然橡胶", "橡胶与纸浆"), ("20号胶", "橡胶与纸浆"), ("纸浆", "橡胶与纸浆"),
]
ALIAS = {
    "聚乙烯": ["聚乙烯", "塑料", "LLDPE"], "燃料油": ["燃料油", "燃油"],
    "天然橡胶": ["天然橡胶", "橡胶"], "液化石油气": ["液化石油气", "液化气", "LPG"],
}
MARKETS = {"m:113": "上期所", "m:114": "大商所", "m:115": "郑商所", "m:142": "上期能源"}
GROUP_ORDER = ["原油与油品", "聚烯烃与氯碱", "聚酯产业链", "煤化工与建材", "橡胶与纸浆"]
FIELDS = "f2,f3,f4,f12,f13,f14"


def fetch_prices():
    items = []
    for mk, ex in MARKETS.items():
        for pn in range(1, 8):
            u = ("https://push2.eastmoney.com/api/qt/clist/get?pn=%d&pz=100&po=0&np=1"
                 "&fltt=2&invt=2&fid=f12&fs=%s&fields=%s" % (pn, mk, FIELDS))
            d = json.loads(http_get(u, referer="https://quote.eastmoney.com/").decode("utf-8", "ignore"))
            arr = (d.get("data") or {}).get("diff") or []
            if not arr:
                break
            for x in arr:
                x["_ex"] = ex
            items += arr
            if len(arr) < 100:
                break

    by_name = {}
    for x in items:
        nm = str(x.get("f14") or "")
        if nm.endswith("主连"):
            by_name.setdefault(nm[:-2], x)

    rows = []
    for want, grp in PRODUCTS:
        hit = by_name.get(want)
        if hit is None:
            for alt in ALIAS.get(want, []):
                if alt in by_name:
                    hit = by_name[alt]
                    break
        if hit is None:
            continue
        px = hit.get("f2")
        if not isinstance(px, (int, float)) or px <= 0:
            continue
        rows.append({
            "name": want, "group": grp,
            "code": str(hit.get("f12") or ""),
            "secid": "%s.%s" % (hit.get("f13"), hit.get("f12")),
            "ex": hit["_ex"], "price": px,
            "chg": hit.get("f3") if isinstance(hit.get("f3"), (int, float)) else None,
            "chg_amt": hit.get("f4") if isinstance(hit.get("f4"), (int, float)) else None,
        })
    return rows


def fetch_kline(secid, lmt=130):
    u = ("https://push2his.eastmoney.com/api/qt/stock/kline/get?secid=%s&klt=101&fqt=1"
         "&beg=0&end=20500101&lmt=%d&fields1=f1,f2,f3,f4,f5,f6"
         "&fields2=f51,f52,f53,f54,f55,f56,f57" % (secid, lmt))
    d = json.loads(http_get(u, referer="https://quote.eastmoney.com/").decode("utf-8", "ignore"))
    ks = (d.get("data") or {}).get("klines") or []
    out = []
    for k in ks:
        p = k.split(",")
        # 日期,开,收,高,低,成交量
        try:
            out.append([p[0], round(float(p[1]), 1), round(float(p[2]), 1),
                        round(float(p[3]), 1), round(float(p[4]), 1), int(float(p[5]))])
        except Exception:  # noqa: BLE001
            continue
    return out[-lmt:]


# ---------------------------------------------------------------- 资讯
# 高端化工关键词（宽泛不漏算）
KW_CATEGORY = [
    ("聚氨酯", ["MDI", "TDI", "聚氨酯", "聚醚", "己二酸"]),
    ("氟硅材料", ["有机硅", "氟化工", "含氟", "氟材料", "硅橡胶", "硅油", "PTFE", "PVDF", "六氟"]),
    ("尼龙及己内酰胺", ["尼龙", "己内酰胺", "PA6", "PA66", "己二胺", "己二腈"]),
    ("可降解材料", ["可降解", "PBAT", "PLA", "PGA", "PBS", "生物基", "聚乳酸"]),
    ("电子化学品", ["电子化学品", "电子特气", "光刻胶", "湿电子", "电子级", "半导体材料", "高纯试剂"]),
    ("高端聚烯烃", ["POE", "茂金属", "mPE", "高端聚烯烃", "α-烯烃", "EVA", "聚烯烃弹性体"]),
    ("工程塑料", ["工程塑料", "聚碳酸酯", "PC", "POM", "PBT", "PPS", "改性塑料", "特种工程"]),
    ("碳纤维及复合材料", ["碳纤维", "复合材料", "预浸料", "原丝"]),
    ("精细化工中间体", ["中间体", "精细化工", "医药中间体", "农药中间体", "精细化学品"]),
    ("涂料与胶粘剂", ["涂料", "胶粘剂", "油墨", "树脂"]),
    ("膜材料", ["膜材料", "分离膜", "光学膜", "隔膜", "反渗透"]),
    ("炼化一体化下游", ["炼化一体化", "差别化", "聚酯", "PX", "重整", "芳烃", "润滑油"]),
]
KW_HIGH = ["新材料", "高端", "特种", "精细化工", "国产替代", "专精特新", "技术突破", "中试",
           "投产", "产业链", "一体化", "绿色", "低碳", "循环"]
KW_CHEM = ["化工", "石化", "化学", "炼化", "乙烯", "丙烯", "聚合物", "合成", "催化", "装置",
           "树脂", "材料"]

SD_CITIES = ["山东", "淄博", "东营", "潍坊", "烟台", "滨州", "菏泽", "德州", "济宁",
             "聊城", "临沂", "青岛", "威海", "泰安", "日照", "枣庄", "济南", "齐鲁"]
GLOBAL_WORDS = ["全球", "国际", "美国", "欧洲", "欧盟", "日本", "韩国", "中东", "俄罗斯",
                "东南亚", "海外", "印度", "德国", "沙特", "进口", "出口", "海外市场", "境外"]


def tag_category(text):
    hits = []
    up = text.upper() if "PC" in text or "PTA" in text else text
    for cat, kws in KW_CATEGORY:
        for k in kws:
            if k in text or k.upper() in up:
                hits.append(cat)
                break
    return hits


def is_high_end(text):
    if tag_category(text):
        return True
    return any(k in text for k in KW_CHEM) and any(k in text for k in KW_HIGH)


def pick_block(text):
    if any(c in text for c in SD_CITIES):
        return "山东"
    if any(c in text for c in GLOBAL_WORDS):
        return "全球"
    return "全国"


def parse_oilchem(s):
    """隆众：URL 形如 /26-1021-07-<hash>.html（年-月日-时）"""
    out, seen = [], set()
    pat = (r'href="(https://www\.oilchem\.net/(\d\d)-(\d\d)(\d\d)-(\d\d)-[0-9a-f]+\.html)"'
           r'[^>]*>\s*([^<]{8,90}?)\s*</a>')
    for m in re.finditer(pat, s, re.S):
        url, yy, mm, dd, hh, title = m.group(1), m.group(2), m.group(3), m.group(4), m.group(5), clean(m.group(6))
        if not title or len(title) < 8 or title in seen:
            continue
        seen.add(title)
        try:
            ts = time.mktime(time.strptime("20%s-%s-%s %s:00" % (yy, mm, dd, hh), "%Y-%m-%d %H:%M"))
        except Exception:  # noqa: BLE001
            ts = None
        out.append({"title": title, "url": url, "summary": "",
                    "ts": int(ts) if ts else None, "source": "隆众资讯"})
    return out


def parse_chemnews(s):
    out = []
    pat = r'href="(/c/(\d{4}-\d{2}-\d{2})/(\d+)\.shtml)"[^>]*>\s*([^<]{8,80}?)\s*</a>'
    for m in re.finditer(pat, s):
        url, date, _, title = m.group(1), m.group(2), m.group(3), clean(m.group(4))
        if not title or len(title) < 6:
            continue
        try:
            ts = time.mktime(time.strptime(date, "%Y-%m-%d"))
        except Exception:  # noqa: BLE001
            ts = None
        out.append({"title": title, "url": "https://www.chemnews.com.cn" + url,
                    "summary": "", "ts": int(ts) if ts else None, "source": "中国化工信息周刊"})
    return out


def sd_enterprise_keys():
    """从园区名录里取出山东企业关键词，用于判定「山东」归属"""
    keys = set()
    try:
        p = os.path.join(DATA, "parks.json")
        with open(p, encoding="utf-8") as f:
            parks = json.load(f)
        for park in parks.get("parks", []):
            for e in park.get("enterprises", []):
                for k in (e.get("match") or []):
                    if len(k) >= 2:
                        keys.add(k)
    except Exception:  # noqa: BLE001
        pass
    return keys


SD_KEYS = None


def enrich(items):
    """打标 + 分板块 + 去重（只用标题判断归属，稳定且不额外请求）"""
    global SD_KEYS
    if SD_KEYS is None:
        SD_KEYS = sd_enterprise_keys()

    seen, res = set(), []
    for it in items:
        text = (it["title"] + " " + (it.get("summary") or ""))
        intl_ok = it.get("_intl") and any(k in text for k in KW_CHEM)
        if not is_high_end(text) and not intl_ok:
            continue
        key = re.sub(r"[\s\u3000·,，。.、:：;；!！?？\"'“”‘’()（）\[\]【】\-—_|/\\]", "", it["title"])[:30]
        if key in seen:
            continue
        seen.add(key)

        t = it["title"]
        # 山东优先：地名 或 山东本地企业
        if any(c in t for c in SD_CITIES) or any(k in t for k in SD_KEYS):
            it["block"] = "山东"
        elif it.get("_intl") or any(c in t for c in GLOBAL_WORDS):
            it["block"] = "全球"
        else:
            it["block"] = "全国"

        it["cats"] = tag_category(text)
        res.append(it)

    res.sort(key=lambda x: (x.get("ts") or 0), reverse=True)
    return res[:45]


def parse_ccin(s, base="http://www.ccin.com.cn"):
    """中化新网（中国化工报）：/detail/xxx 形式，标题质量最高"""
    out, seen = [], set()
    pat = r'href="(/detail/[A-Za-z0-9]+(?:/news)?)"[^>]*>\s*([^<]{8,80}?)\s*</a>'
    for m in re.finditer(pat, s, re.S):
        url, title = m.group(1), clean(m.group(2))
        if not title or len(title) < 8 or title in seen:
            continue
        if any(k in title for k in ["征订", "电子版", "广告", "订阅"]):
            continue
        seen.add(title)
        out.append({"title": title, "url": base + url, "summary": "",
                    "ts": None, "source": "中国化工报"})
    return out


def fill_ccin_dates(items, limit=14):
    """逐条取发布日期（限量，避免请求过多）"""
    for it in items[:limit]:
        if it.get("ts"):
            continue
        try:
            s = http_get(it["url"]).decode("utf-8", "ignore")
            m = re.search(r"(20\d{2})[-/年](\d{1,2})[-/月](\d{1,2})", s)
            if m:
                it["ts"] = int(time.mktime(time.strptime(
                    "%s-%s-%s" % (m.group(1), "%02d" % int(m.group(2)), "%02d" % int(m.group(3))),
                    "%Y-%m-%d")))
        except Exception:  # noqa: BLE001
            pass
    return items


def fetch_news():
    """返回全部原始资讯（未过滤）"""
    raw = []
    jobs = [
        ("中国化工报", "http://www.ccin.com.cn/", parse_ccin),
        ("中国化工信息周刊", "https://www.chemnews.com.cn/", parse_chemnews),
        ("隆众资讯", "https://www.oilchem.net/", parse_oilchem),
    ]
    for name, url, fn in jobs:
        try:
            got = fn(http_get(url).decode("utf-8", "ignore"))
            if name == "中国化工报":
                got = fill_ccin_dates(got)
            raw += got
            print("     %s: %d 条" % (name, len(got)))
        except Exception as e:  # noqa: BLE001
            print("  [!] %s 失败: %s" % (name, str(e)[:60]))

    # 补充：中新网（筛高端化工），增加全球/山东覆盖
    import xml.etree.ElementTree as ET
    for cid, cname in [("finance", "财经"), ("china", "国内"), ("world", "国际")]:
        try:
            s = http_get("https://www.chinanews.com.cn/rss/%s.xml" % cid).decode("utf-8", "ignore")
            root = ET.fromstring(s)
            n = 0
            for it in root.iter("item"):
                t = clean(it.findtext("title"))
                link = (it.findtext("link") or "").strip()
                if not t or not link:
                    continue
                ts = None
                p = (it.findtext("pubDate") or "").strip()
                if p:
                    try:
                        ts = int(parsedate_to_datetime(p).timestamp())
                    except Exception:  # noqa: BLE001
                        pass
                raw.append({"title": t, "url": link,
                            "summary": clean(it.findtext("description"), 100),
                            "ts": ts, "source": "中新网", "_intl": cid == "world"})
                n += 1
            print("     中新网-%s: %d 条" % (cname, n))
        except Exception as e:  # noqa: BLE001
            print("  [!] 中新网 %s 失败: %s" % (cname, str(e)[:40]))

    return raw


# ---------------------------------------------------------------- 政策
KW_POLICY = ["化工", "石化", "化学", "新材料", "危险化学品", "园区", "炼化", "塑料", "橡胶", "涂料"]
KW_DOCTYPE = ["通知", "意见", "方案", "办法", "规划", "条例", "公告", "决定", "批复",
              "细则", "导则", "指南", "规定", "目录", "标准"]

POLICY_SOURCES = [
    {"level": "山东省", "org": "山东省工业和信息化厅",
     "url": "http://gxt.shandong.gov.cn/col/col103862/index.html",
     "pattern": r'href="([^"]*?/art/\d{4}/\d{1,2}/\d{1,2}/art_\d+_\d+\.html)"[^>]*>\s*([^<]{8,90}?)\s*</a>'},
    {"level": "山东省", "org": "山东省工业和信息化厅",
     "url": "http://gxt.shandong.gov.cn/col/col103863/index.html",
     "pattern": r'href="([^"]*?/art/\d{4}/\d{1,2}/\d{1,2}/art_\d+_\d+\.html)"[^>]*>\s*([^<]{8,90}?)\s*</a>'},
    {"level": "国家级", "org": "国家发展改革委",
     "url": "https://www.ndrc.gov.cn/xxgk/zcfb/ghxwj/",
     "pattern": r'href="([^"]*?/t\d{8}_\d+\.html)"[^>]*>\s*([^<]{8,90}?)\s*</a>'},
    {"level": "国家级", "org": "国家发展改革委",
     "url": "https://www.ndrc.gov.cn/xxgk/zcfb/tz/",
     "pattern": r'href="([^"]*?/t\d{8}_\d+\.html)"[^>]*>\s*([^<]{8,90}?)\s*</a>'},
    {"level": "国家级", "org": "生态环境部",
     "url": "https://www.mee.gov.cn/zcwj/",
     "pattern": r'href="([^"]*?/t\d{8}_\d+\.s?html)"[^>]*>\s*([^<]{8,90}?)\s*</a>'},
]


def fetch_policies():
    out, seen = [], set()
    for src in POLICY_SOURCES:
        try:
            s = http_get(src["url"]).decode("utf-8", "ignore")
        except Exception as e:  # noqa: BLE001
            print("  [!] 政策源失败 %s: %s" % (src["org"], str(e)[:50]))
            continue
        got = 0
        for h, t in re.findall(src["pattern"], s):
            title = clean(t)
            if not title or len(title) < 8 or title in seen:
                continue
            # 必须同时命中「化工主题」和「公文类型」，避免把新闻当政策
            if not any(k in title for k in KW_POLICY):
                continue
            if not any(k in title for k in KW_DOCTYPE):
                continue
            seen.add(title)
            url = h if h.startswith("http") else src["url"].split("/col/")[0].rstrip("/") + "/" + h.lstrip("./")
            m = re.search(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})", url)
            ts = None
            if m:
                try:
                    ts = int(time.mktime(time.strptime(
                        "%s-%02d-%02d" % (m.group(1), int(m.group(2)), int(m.group(3))), "%Y-%m-%d")))
                except Exception:  # noqa: BLE001
                    pass
            out.append({"id": "pol%d" % (len(out) + 1), "title": title, "url": url,
                        "level": src["level"], "org": src["org"], "ts": ts})
            got += 1
        print("     %s %s: %d 条" % (src["level"], src["org"], got))
    out.sort(key=lambda x: (x.get("ts") or 0), reverse=True)
    for i, x in enumerate(out):
        x["id"] = "pol%d" % (i + 1)
    return out


# ---------------------------------------------------------------- 影响原因（规则推断）
FACTORS = [
    ("成本端", ["原油", "油价", "OPEC", "地缘", "减产", "天然气", "煤炭", "石脑油", "成本"]),
    ("供给端", ["检修", "停车", "装置", "开工率", "减产", "新增产能", "投产", "供应"]),
    ("需求端", ["需求", "订单", "下游", "开工", "房地产", "出口", "消费", "采购"]),
    ("库存", ["库存", "累库", "去库", "港口", "社会库存"]),
    ("政策", ["政策", "关税", "环保", "限产", "配额", "标准"]),
]


def infer_reason(name, news):
    """基于关联新闻标题做因子提取。找不到依据就返回 None，不硬编。"""
    if not news:
        return None
    hit = {}
    for n in news:
        t = n["title"]
        for fac, kws in FACTORS:
            if any(k in t for k in kws):
                hit.setdefault(fac, []).append(n)
                break
    if not hit:
        return None
    order = ["成本端", "供给端", "需求端", "库存", "政策"]
    facs = [f for f in order if f in hit]
    top = hit[facs[0]][0]
    text = "近期%s因素较受关注（据：%s）" % ("、".join(facs[:2]), top["title"][:36])
    return {"factors": facs, "text": text,
            "basis": [{"title": n["title"], "url": n["url"], "source": n["source"]}
                      for n in hit[facs[0]][:2]]}


def match_price_news(raw, rows):
    """按品种名从原始资讯里匹配关联新闻"""
    out = {}
    for r in rows:
        nm = r["name"]
        keys = [nm] + ALIAS.get(nm, [])
        got = [n for n in raw if any(k in n["title"] for k in keys)]
        got.sort(key=lambda x: (x.get("ts") or 0), reverse=True)
        out[nm] = got[:6]
    return out


# ---------------------------------------------------------------- 主流程
def main():
    now = int(time.time())
    stamp = time.strftime("%Y-%m-%d %H:%M", time.localtime(now))
    print("采集行情…")
    rows = []
    try:
        rows = fetch_prices()
        groups = []
        for g in GROUP_ORDER:
            sub = [r for r in rows if r["group"] == g]
            if sub:
                groups.append({"name": g, "items": sub})

        hist = load("prices_history.json", {"series": {}})
        series = hist.get("series", {})
        for r in rows:
            try:
                k = fetch_kline(r["secid"], 250)
                if k:
                    series[r["name"]] = k
            except Exception as e:  # noqa: BLE001
                print("     K线失败 %s: %s" % (r["name"], str(e)[:40]))
        save("prices_history.json", {"updated_at": now, "series": series})
    except Exception as e:  # noqa: BLE001
        print("  [!] 行情整体失败:", str(e)[:80])

    print("采集资讯…")
    raw = []
    try:
        raw = fetch_news()
        good = enrich(raw)
        blocks = {"全球": [], "全国": [], "山东": []}
        for it in good:
            blocks[it["block"]].append(it)
        save("news.json", {"updated_at": now, "updated_at_text": stamp,
                           "blocks": [{"name": k, "items": v} for k, v in blocks.items()],
                           "total": len(good), "raw_count": len(raw)})
        print("     原始 %d 条 → 高端化工 %d 条" % (len(raw), len(good)))
    except Exception as e:  # noqa: BLE001
        print("  [!] 资讯失败:", str(e)[:80])

    if rows:
        print("关联行情新闻…")
        pn = match_price_news(raw, rows)
        groups = []
        for g in GROUP_ORDER:
            sub = []
            for r in rows:
                if r["group"] != g:
                    continue
                news = pn.get(r["name"], [])
                r2 = dict(r)
                r2["news"] = [{"title": n["title"], "url": n["url"],
                               "source": n["source"], "ts": n.get("ts")} for n in news]
                r2["reason"] = infer_reason(r["name"], news)
                sub.append(r2)
            if sub:
                groups.append({"name": g, "items": sub})
        save("prices.json", {"updated_at": now, "updated_at_text": stamp,
                             "groups": groups, "count": len(rows)})

    print("采集政策…")
    try:
        pol = fetch_policies()
        save("policies.json", {"updated_at": now, "updated_at_text": stamp, "items": pol})
    except Exception as e:  # noqa: BLE001
        print("  [!] 政策失败:", str(e)[:80])

    save("meta.json", {"updated_at": now, "updated_at_text": stamp})


if __name__ == "__main__":
    main()
