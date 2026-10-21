#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
高端化工行业认知 App · 数据采集
纯标准库，无需安装依赖。

产出：
  data/prices.json          行情快照（含关联新闻与因素推断）
  data/prices_history.json  各品种日线（K线，只增不删）
  data/news.json            资讯（全球/全国/山东，已跨源去重）
  data/policies.json        政策（国家级/山东省）
  data/meta.json            更新时间
  backups/YYYY-MM-DD-*.json 每日快照，保留最近 30 天

设计要点（对应 PRD 7.2 / 开发计划 P1）：
  - save() 原子替换，避免半截文件
  - save_or_keep() 采集失败不清空旧数据，只补 error 字段
  - 同一事件跨源跨板块只留一条（山东 > 全国 > 全球），留 dup_of 痕迹
  - 山东判定四级信号：山东/市名 → 省属信号词 → 收录企业名 → 济南等别名
  - 全球判定：境外主体 / 境外市场词 / 国际化工频道来源
"""

import json
import os
import re
import html
import shutil
import time
import urllib.request
import urllib.error
from email.utils import parsedate_to_datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, "data")
BACKUPS = os.path.join(BASE, "backups")
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
WS_RE = re.compile(r"[ \t\u3000\xa0]+")


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
    """原子写入：先写 .tmp 再 replace，避免进程被杀留下半截 JSON"""
    p = os.path.join(DATA, name)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, p)
    print("  -> %s (%.1f KB)" % (name, os.path.getsize(p) / 1024))


def load(name, default):
    p = os.path.join(DATA, name)
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return default


def save_or_keep(name, obj, err, stamp):
    """采集失败时不清空旧数据，只追加 error 说明（PRD 7.2-3）"""
    if obj is None:
        old = load(name, {})
        if not isinstance(old, dict):
            old = {}
        old["error"] = {"msg": str(err)[:200] if err else "未知原因", "at": stamp}
        save(name, old)
        print("  [!] %s 本次更新失败，已保留上次内容：%s" % (name, str(err)[:70]))
    else:
        obj.pop("error", None)
        save(name, obj)
    return obj


# ---------------------------------------------------------------- 每日快照
BACKUP_FILES = ["news.json", "prices.json", "prices_history.json", "policies.json"]


def rotate_backups(bk_dir, keep_days=30):
    """按文件名前 10 位日期分组，只保留最近 keep_days 天，返回被删文件名"""
    if not os.path.isdir(bk_dir):
        return []
    names = os.listdir(bk_dir)
    days = sorted({n[:10] for n in names if re.match(r"^\d{4}-\d{2}-\d{2}", n)})
    if len(days) <= keep_days:
        return []
    drop = set(days[:-keep_days])
    removed = []
    for n in names:
        if n[:10] in drop:
            try:
                os.remove(os.path.join(bk_dir, n))
                removed.append(n)
            except OSError:
                pass
    return removed


def snapshot_backups(today=None, data_dir=None, bk_dir=None, keep_days=30):
    """把 4 个会变的数据文件复制成 backups/YYYY-MM-DD-xxx.json，并轮转"""
    data_dir = data_dir or DATA
    bk_dir = bk_dir or BACKUPS
    os.makedirs(bk_dir, exist_ok=True)
    day = today or time.strftime("%Y-%m-%d")
    n = 0
    for fn in BACKUP_FILES:
        src = os.path.join(data_dir, fn)
        if os.path.exists(src):
            shutil.copy(src, os.path.join(bk_dir, "%s-%s" % (day, fn)))
            n += 1
    removed = rotate_backups(bk_dir, keep_days)
    if removed:
        print("     备份轮转：删除 %d 个旧文件" % len(removed))
    return n


# ---------------------------------------------------------------- 行情
# 品种名 -> 分组
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

# 别名表：每个品种补足「同义名 / 工艺路线 / 上位词 / 主要下游」，
# 用于把「品种」和「相关新闻」连起来（P1-6）。命中标题优先，只命中摘要的标「摘要提及」。
ALIAS = {
    "原油": ["原油", "油价", "布伦特", "WTI", "OPEC"],
    "燃料油": ["燃料油", "燃油", "渣油"],
    "液化石油气": ["液化石油气", "液化气", "LPG", "丙烷", "丁烷"],
    "沥青": ["沥青", "道路沥青", "渣油"],
    "低硫燃料油": ["低硫燃料油", "低硫", "船燃"],
    "聚乙烯": ["聚乙烯", "LLDPE", "PE", "塑料"],
    "聚丙烯": ["聚丙烯", "PP", "拉丝", "均聚"],
    "PVC": ["PVC", "聚氯乙烯", "电石法", "乙烯法", "型材"],
    "苯乙烯": ["苯乙烯", "SM", "乙苯", "EPS", "ABS"],
    "烧碱": ["烧碱", "液碱", "片碱", "氯碱"],
    "对二甲苯": ["对二甲苯", "PX", "芳烃"],
    "PTA": ["PTA", "精对苯二甲酸", "聚酯"],
    "乙二醇": ["乙二醇", "MEG", "聚酯"],
    "短纤": ["短纤", "涤纶", "聚酯切片"],
    "瓶片": ["瓶片", "瓶级", "涤纶", "聚酯切片"],
    "甲醇": ["甲醇", "煤制甲醇", "MTO", "甲醛"],
    "尿素": ["尿素", "氮肥", "合成氨", "车用尿素", "化肥"],
    "纯碱": ["纯碱", "联碱", "氨碱", "重碱", "轻碱", "玻璃"],
    "玻璃": ["玻璃", "浮法", "光伏玻璃"],
    "焦炭": ["焦炭", "炼焦", "焦化", "煤焦"],
    "焦煤": ["焦煤", "炼焦", "焦化"],
    "天然橡胶": ["天然橡胶", "天胶", "标胶", "橡胶", "轮胎"],
    "20号胶": ["20号胶", "天胶", "标胶", "轮胎"],
    "纸浆": ["纸浆", "木浆", "针叶浆", "阔叶浆", "浆价"],
}
# 山东本地口径来源：中国化工报「化工号」里的山东企业栏目（企业供稿，本身就是化工口径）
SD_CHANNELS = [
    ("鲁北集团", "http://www.ccin.com.cn/c/lubei"),
    ("金正大", "http://www.ccin.com.cn/c/kingenta"),
    ("海湾集团", "http://www.ccin.com.cn/c/qdhw"),
]
# 这些明显不是行业动向，拒收（避免企业党建/工会稿占满山东板块）
SD_CHANNEL_DROP = ["工会", "党建", "党委", "文艺", "慰问", "篮球", "运动会", "征文", "摄影",
                   "廉洁", "主题教育", "表彰大会", "演讲", "人事", "标兵", "暖人心", "炼成",
                   "作对", "风采", "故事", "一线", "人物", "班组", "思政", "决战四季度",
                   "生产经营分析会", "月度工作会"]

# 明显是卖报告/卖数据的推广稿，不是新闻
AD_WORDS = ["年度报告目录", "市场年度报告", "预售", "数据包", "定制数据", "项目建议书",
            "订阅", "征订", "广告"]
# 全国口径词：山东企业栏目里转发的宏观/全国稿，不能算山东本地新闻
NATIONAL_WORDS = ["我国", "全国", "全球", "国际", "世界", "国家统计局", "海关总署", "工信部",
                  "国家发展改革委", "生态环境部", "中方", "中国石化", "中国石油"]

# 品种排除词：标题里出现这些，说明讲的是另一个东西，不能算这个品种的新闻
ALIAS_EXCL = {
    "沥青": ["煤沥青", "改质沥青"],
    "烧碱": ["甲烷氯化物", "氯化石蜡"],
    "甲醇": ["冰醋酸", "二甲醚", "甲醇汽油"],
    "尿素": ["车用尿素溶液"],
    "焦煤": ["焦煤油"],
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


def fetch_kline(secid, lmt=250):
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
           "树脂"]

# 山东判定：16 市名 + 省名（高置信）
CITY_NAMES = ["山东", "济南", "青岛", "淄博", "枣庄", "东营", "烟台", "潍坊", "济宁", "泰安",
              "威海", "日照", "临沂", "德州", "聊城", "滨州", "菏泽"]
# 山东判定：省属信号词（园区/机构/区域品牌）
SD_SIGNALS = ["山东省", "省工信厅", "省发改委", "齐鲁", "鲁西", "鲁北", "黄三角",
              "裕龙", "万华", "齐鲁石化", "东明石化", "利华益", "华鲁恒升", "鲁西化工",
              "京博", "海科", "富海", "齐翔腾达", "滨化", "东岳", "金诚", "汇丰石化",
              "亚星化学", "海化集团", "信发", "新龙", "恒通化工", "清源集团"]
# 全球判定：境外主体 / 境外市场相关
GLOBAL_WORDS = ["全球", "国际", "美国", "欧洲", "欧盟", "欧元区", "日本", "韩国", "中东",
                "俄罗斯", "东南亚", "海外", "印度", "德国", "沙特", "进口", "出口",
                "境外", "外盘", "反倾销", "关税", "海外装置", "国际市场", "全球市场",
                "伊朗", "挪威", "巴西", "墨西哥", "土耳其", "越南", "缅甸", "委内瑞拉",
                "乌克兰", "卡塔尔", "比利时", "法国", "英国", "意大利", "荷兰"]
FOREIGN_FIRMS = ["巴斯夫", "陶氏", "科思创", "亨斯迈", "沙特阿美", "埃克森", "美孚", "SABIC",
                 "三井", "旭化成", "三菱", "住友", "东丽", "LG", "乐天", "SK", "赢创",
                 "汉高", "阿科玛", "朗盛", "索尔维", "帝斯曼", "科莱恩", "PPG",
                 "阿克苏诺贝尔", "雪佛龙", "道达尔", "壳牌", "BP", "埃尼", "北欧化工",
                 "伊士曼", "塞拉尼斯", "托普索", "德之馨", "富士胶片", "施耐德电气"]


def tag_category(text):
    hits = []
    up = text.upper() if "PC" in text or "PTA" in text else text
    for cat, kws in KW_CATEGORY:
        for k in kws:
            if k in text or k.upper() in up:
                hits.append(cat)
                break
    return hits


def is_high_end(text, known_entity=False):
    """known_entity=True：标题里出现我们收录库中的化工企业名 / 知名外企，
    这类标题即使没有「化工」二字，主题也确定在化工范围内（否则会漏掉
    「访滨化集团营销中心总经理」这种纯企业访谈）。"""
    if tag_category(text):
        return True
    if known_entity:
        # 标题里出现我们收录库中的化工企业名（万华、金正大、滨化…）或知名外企，
        # 这条新闻的主题就确定在化工行业内了，不必再要求出现「化工」二字。
        return True
    return any(k in text for k in KW_CHEM) and any(k in text for k in KW_HIGH)


def is_shandong(title, summary=""):
    """山东判定：市名/省名 → 省属信号词（企业名由 enrich 另外叠加）。

    只看标题，不看摘要：摘要里顺带提一句「山东」不代表这条是山东新闻。
    宁可少归，也不把全国宏观数据算成山东本地消息。
    summary 参数保留是为了兼容调用方签名。
    """
    if any(c in title for c in CITY_NAMES):
        return True
    if any(s in title for s in SD_SIGNALS):
        return True
    return False


def norm_title(t):
    return re.sub(r"[\s\-—－·|｜:：,，。.、!！?？\"'“”‘’()（）\[\]【】/\\]", "", t or "")


def bigrams(s):
    return {s[i:i + 2] for i in range(len(s) - 1)} or {s}


def day_of(ts):
    if not ts:
        return ""
    return time.strftime("%Y-%m-%d", time.localtime(ts))


def dedup_cross(items, thr=0.72):
    """同一事件跨源跨板块只留一条：保留更具体的层级（山东 > 全国 > 全球），并留 dup_of 痕迹"""
    rank = {"山东": 0, "全国": 1, "全球": 2}
    items = sorted(items, key=lambda x: (rank.get(x.get("block"), 9), -(x.get("ts") or 0)))
    kept = []
    for it in items:
        a = bigrams(norm_title(it["title"]))
        d = it.get("day") or day_of(it.get("ts"))
        dup = False
        for k in kept:
            if (k.get("day") or day_of(k.get("ts"))) != d:
                continue
            b = bigrams(norm_title(k["title"]))
            j = len(a & b) / max(1, len(a | b))
            if j > thr:
                dup = True
                it["dup_of"] = k["title"]
                break
        if not dup:
            kept.append(it)
    return kept


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


def parse_ccin_list(s):
    """中国化工报列表页：news-box 里带标题 / 摘要 / 日期，一次拿全，不用逐条回源"""
    out = []
    for chunk in s.split('<div class="news-box">')[1:]:
        m = re.search(r'<h2>\s*<a href="(/detail/[^"]+)"[^>]*>(.*?)</a>\s*</h2>', chunk, re.S)
        if not m:
            continue
        url, title = m.group(1), clean(m.group(2))
        if not title or len(title) < 8:
            continue
        if any(k in title for k in ["征订", "电子版", "广告", "订阅"]):
            continue
        sm = re.search(r"<p>(.*?)</p>", chunk, re.S)
        dt = re.search(r'<div class="news-tag">\s*(\d{4})-(\d{1,2})-(\d{1,2})', chunk)
        ts = None
        if dt:
            try:
                ts = int(time.mktime(time.strptime(
                    "%s-%02d-%02d" % (dt.group(1), int(dt.group(2)), int(dt.group(3))), "%Y-%m-%d")))
            except Exception:  # noqa: BLE001
                ts = None
        out.append({"title": title, "url": "http://www.ccin.com.cn" + url,
                    "summary": clean(sm.group(1), 120) if sm else "",
                    "ts": ts, "source": "中国化工报"})
    return out


def parse_em_futures(s):
    """东方财富期货：<a href="https://finance.eastmoney.com/a/YYYYMMDDnnn.html" title="完整标题">
    这类是期货品种评论/外盘速递，用来给「品种详情 → 关联新闻」提供依据（不进资讯板块，
    除非标题本身就是高端化工主题）。日期直接取 URL 里的 8 位数字。"""
    out, seen = [], set()
    pat = r'href="(https://finance\.eastmoney\.com/a/(\d{8})\d+\.html)"[^>]*title="([^"]{8,90})"'
    for url, d, title in re.findall(pat, s):
        t = clean(title)
        if not t or t in seen:
            continue
        seen.add(t)
        try:
            ts = int(time.mktime(time.strptime(d, "%Y%m%d")))
        except Exception:  # noqa: BLE001
            ts = None
        out.append({"title": t, "url": url, "summary": "", "ts": ts,
                    "source": "东方财富·期货", "_px": True})
    return out


def parse_ccin(s, base="http://www.ccin.com.cn"):
    """兜底：只有标题、没有日期时用（旧首页结构）"""
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


def sd_enterprise_keys():
    """从园区名录里取出山东企业关键词，用于判定「山东」归属。

    注意：parks.json 是 cities -> parks -> enterprises 三层结构，
    早期版本误按 parks["parks"] 读，导致关键词永远为空（山东板块 0 条的根因之一）。
    """
    stop = {"化工", "集团", "石化", "新材料", "股份", "有限公司", "科技", "实业"}
    keys = set()
    d = load("parks.json", {})
    for c in d.get("cities", []) or []:
        if c.get("name"):
            keys.add(c["name"])
        buckets = [e for p in (c.get("parks") or []) for e in (p.get("enterprises") or [])]
        buckets += c.get("enterprises") or []
        for e in buckets:
            for k in (e.get("match") or [e.get("name")]):
                if k and len(k) >= 2 and k not in stop:
                    keys.add(k)
    return keys


SD_KEYS = None


def enrich(items):
    """打标 + 分板块（不做跨源去重，去重由 dedup_cross 负责）"""
    global SD_KEYS
    if SD_KEYS is None:
        SD_KEYS = sd_enterprise_keys()

    seen, res = set(), []
    for it in items:
        text = (it["title"] + " " + (it.get("summary") or ""))
        known = (any(k in it["title"] for k in SD_KEYS)
                 or any(k in it["title"] for k in FOREIGN_FIRMS)
                 or any(k in it["title"] for k in SD_SIGNALS))
        if any(w in it["title"] for w in AD_WORDS):
            continue
        ok = (is_high_end(text, known)
              or (it.get("_intl") and any(k in text for k in KW_CHEM)))
        if not ok:
            continue
        key = norm_title(it["title"])[:30]
        if key in seen:
            continue
        seen.add(key)

        t = it["title"]
        it["cats"] = tag_category(text)
        it["day"] = day_of(it.get("ts"))
        # 归属只看标题本身：地名 / 省属信号词 / 收录企业名。
        # 来源栏目（_sd）只作溯源标记，不参与归属——企业栏目也会转发全国宏观稿。
        if is_shandong(t) or any(k in t for k in SD_KEYS):
            it["block"] = "山东"
        elif it.get("_intl") or any(c in t for c in GLOBAL_WORDS) or any(c in t for c in FOREIGN_FIRMS):
            it["block"] = "全球"
        else:
            it["block"] = "全国"
        res.append(it)
    return res


def fetch_news():
    """返回全部原始资讯（未过滤）"""
    raw = []
    jobs = [
        ("中国化工报", "http://www.ccin.com.cn/", parse_ccin_list, False),
        ("中国化工信息周刊", "https://www.chemnews.com.cn/", parse_chemnews, False),
        ("隆众资讯", "https://www.oilchem.net/", parse_oilchem, False),
        # 国际化工频道：本身就是境外口径，整栏收，用来补「全球」板块（P1-5）
        ("中国化工报·国际化工", "http://www.ccin.com.cn/c/int", parse_ccin_list, True),
        # 期货品种评论：品种详情页「关联新闻」的主要依据（不进资讯板块，除非本身是化工主题）
        ("东方财富·期货", "https://futures.eastmoney.com/", parse_em_futures, False),
    ]
    for name, url, fn, intl in jobs:
        try:
            got = fn(http_get(url).decode("utf-8", "ignore"))
            if got and not any(g.get("ts") for g in got):
                got = fill_ccin_dates(got, 10)
            if intl:
                for g in got:
                    g["_intl"] = True
                    g["source"] = "中国化工报·国际化工"
            raw += got
            print("     %s: %d 条" % (name, len(got)))
        except Exception as e:  # noqa: BLE001
            print("  [!] %s 失败: %s" % (name, str(e)[:60]))

    # 山东本地口径来源（P1-4）：企业化工厂栏目，整栏收但每栏限量、去掉非行业稿
    for cname, url in SD_CHANNELS:
        try:
            got = parse_ccin_list(http_get(url).decode("utf-8", "ignore"))
            got = [g for g in got if not any(k in g["title"] for k in SD_CHANNEL_DROP)][:6]
            for g in got:
                g["_sd"] = True
                g["source"] = "中国化工报·%s" % cname
            raw += got
            print("     山东·%s: %d 条" % (cname, len(got)))
        except Exception as e:  # noqa: BLE001
            print("  [!] 山东栏目 %s 失败: %s" % (cname, str(e)[:40]))

    # 补充：中新网 RSS（国际频道用于全球板块兜底）
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


def date_from_url(url):
    """从 URL 里取日期：支持 2026/10/21、20261021、t20261021 三种写法"""
    m = re.search(r"(20\d{2})[/-](\d{1,2})[/-](\d{1,2})", url)
    if not m:
        m = re.search(r"(20\d{2})(\d{2})(\d{2})", url)
    if not m:
        return None
    try:
        return int(time.mktime(time.strptime(
            "%s-%02d-%02d" % (m.group(1), int(m.group(2)), int(m.group(3))), "%Y-%m-%d")))
    except Exception:  # noqa: BLE001
        return None


def date_from_page(url):
    """URL 里没有日期时，回源取页面上的发布日期（限量，失败就返回 None）"""
    try:
        s = http_get(url, timeout=15, retries=0).decode("utf-8", "ignore")
    except Exception:  # noqa: BLE001
        return None
    for pat in [r'发布[日时]期?[：:]\s*</?[^>]*>\s*(20\d{2})[-/年.](\d{1,2})[-/月.](\d{1,2})',
                r'id="?pubDate"?[^>]*>\s*(20\d{2})[-/年.](\d{1,2})[-/月.](\d{1,2})',
                r'(20\d{2})[-/年.](\d{1,2})[-/月.](\d{1,2})']:
        m = re.search(pat, s)
        if m:
            try:
                return int(time.mktime(time.strptime(
                    "%s-%02d-%02d" % (m.group(1), int(m.group(2)), int(m.group(3))), "%Y-%m-%d")))
            except Exception:  # noqa: BLE001
                continue
    return None


# 政策影响：按标题关键词归纳「这条大概影响什么」，不做结论性判断，也不编数字。
# impact_src 标 rule，前端标「规则归纳」，与 AI 推断同等对待，不冒充官方解读。
POLICY_IMPACT = [
    (["化学物质", "名录", "登记"], "涉及化学物质名录与环境管理登记，影响新产品上市与进口合规"),
    (["奖补", "补贴", "数智化", "改造"], "涉及财政奖补与改造支持，符合条件的企业可申报"),
    (["投资", "项目管理", "审批"], "涉及化工项目投资管理与审批口径，影响新项目能不能落地"),
    (["稳增长", "行动方案", "发展规划", "实施方案"], "属于行业发展部署，方向性信号，具体支持看配套细则"),
    (["危险化学品", "危化"], "涉及危化品生产储存的合规要求，园区内相关企业要对照自查"),
    (["化工园区", "园区"], "涉及化工园区认定与管理口径，影响园内企业的准入与配套"),
    (["环保", "生态环境", "排放", "污染", "治理"], "涉及环保排放与治理要求，可能抬高技改与运行成本"),
    (["安全生产", "安全"], "涉及安全生产要求，影响装置运行、检修与验收安排"),
    (["产能", "置换", "新增"], "涉及产能置换与项目审批，影响在建与拟建装置的节奏"),
    (["淘汰", "限制", "禁止", "退出"], "涉及落后产能退出与限制类目录，影响存量装置能不能继续干"),
    (["标准", "规范", "指南", "导则"], "涉及标准与规范口径，可能改变下游采购与验收依据"),
    (["新材料", "高端", "精细化工"], "涉及高端新材料方向的支持口径，与品类升级相关"),
]


def policy_impact(title):
    for kws, txt in POLICY_IMPACT:
        if any(k in title for k in kws):
            return txt
    return ""


def resolve_policy_url(h, src):
    if h.startswith("http"):
        return h
    root = src["url"].split("/col/")[0].rstrip("/")
    return root + "/" + h.lstrip("./")


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
            url = resolve_policy_url(h, src)
            ts = date_from_url(url)
            out.append({"id": "pol%d" % (len(out) + 1), "title": title, "url": url,
                        "level": src["level"], "org": src["org"], "ts": ts,
                        "impact": policy_impact(title), "impact_src": "rule"})
            got += 1
        print("     %s %s: %d 条" % (src["level"], src["org"], got))

    # URL 里没有日期的，回源补一次（限量 12 条，避免请求过多）
    missing = [x for x in out if not x.get("ts")][:12]
    for x in missing:
        x["ts"] = date_from_page(x["url"])
    still = [x for x in out if not x.get("ts")]
    if still:
        print("     [!] 仍有 %d 条取不到日期，页面会显示「—」" % len(still))

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


def match_price_news(raw, rows, cap=6):
    """按品种名 + 别名从原始资讯里匹配关联新闻。

    标题命中优先排序在前，只命中摘要的标 via=summary，前端显示「摘要提及」。
    """
    out = {}
    for r in rows:
        nm = r["name"]
        keys = [nm] + ALIAS.get(nm, [])
        excl = ALIAS_EXCL.get(nm, [])
        th, sh = [], []
        for n in raw:
            t = n.get("title") or ""
            sm = n.get("summary") or ""
            if excl and any(x in t for x in excl):
                continue
            if any(k in t for k in keys):
                th.append(dict(n, via="title"))
            elif any(k in sm for k in keys):
                sh.append(dict(n, via="summary"))
        th.sort(key=lambda x: (x.get("ts") or 0), reverse=True)
        sh.sort(key=lambda x: (x.get("ts") or 0), reverse=True)
        out[nm] = (th + sh)[:cap]
    return out


# ---------------------------------------------------------------- 主流程
def build_news(raw):
    """raw -> 结构化 news.json 内容（打标 → 跨源去重 → 分板块）"""
    tagged = enrich(raw)
    uniq = dedup_cross(tagged)
    uniq.sort(key=lambda x: (x.get("ts") or 0), reverse=True)
    blocks = {"全球": [], "全国": [], "山东": []}
    for it in uniq:
        blocks[it["block"]].append(it)
    for k in blocks:
        blocks[k] = blocks[k][:30]
    return {
        "blocks": [{"name": k, "items": v} for k, v in blocks.items()],
        "total": sum(len(v) for v in blocks.values()),
        "raw_count": len(raw),
        "dedup_dropped": len(tagged) - len(uniq),
    }


def main():
    now = int(time.time())
    stamp = time.strftime("%Y-%m-%d %H:%M", time.localtime(now))
    print("采集行情…")

    rows, err_p = [], None
    try:
        rows = fetch_prices()
        if not rows:
            raise RuntimeError("行情返回空列表")
    except Exception as e:  # noqa: BLE001
        err_p = e
        print("  [!] 行情失败: %s" % str(e)[:80])

    # K 线：只增不删，失败的品种保留旧序列
    if rows:
        hist = load("prices_history.json", {"series": {}})
        series = hist.get("series", {}) if isinstance(hist, dict) else {}
        for r in rows:
            try:
                k = fetch_kline(r["secid"], 250)
                if k:
                    series[r["name"]] = k
            except Exception as e:  # noqa: BLE001
                print("     K线失败 %s: %s" % (r["name"], str(e)[:40]))
        save("prices_history.json", {"updated_at": now, "series": series})
    else:
        save_or_keep("prices_history.json", None, err_p, stamp)

    print("采集资讯…")
    raw, err_n, news_obj = [], None, None
    try:
        raw = fetch_news()
        if not raw:
            raise RuntimeError("全部资讯源返回空")
        news_obj = build_news(raw)
        news_obj["updated_at"] = now
        news_obj["updated_at_text"] = stamp
    except Exception as e:  # noqa: BLE001
        err_n = e
        print("  [!] 资讯失败: %s" % str(e)[:80])
        old = load("news.json", {})
        for b in (old.get("blocks") or []):
            raw += b.get("items") or []

    save_or_keep("news.json", news_obj, err_n, stamp)
    if news_obj:
        print("     原始 %d 条 → 高端化工 %d 条（去重丢 %d）" % (
            news_obj["raw_count"], news_obj["total"], news_obj["dedup_dropped"]))

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
                r2["news"] = [{"title": n["title"], "url": n["url"], "source": n["source"],
                               "ts": n.get("ts"), "via": n.get("via", "title")} for n in news]
                r2["reason"] = infer_reason(r["name"], news)
                sub.append(r2)
            if sub:
                groups.append({"name": g, "items": sub})
        save_or_keep("prices.json", {"updated_at": now, "updated_at_text": stamp,
                                     "groups": groups, "count": len(rows)}, None, stamp)
    else:
        save_or_keep("prices.json", None, err_p, stamp)

    print("采集政策…")
    pol, err_pol = None, None
    try:
        pol = fetch_policies()
        if not pol:
            raise RuntimeError("政策源全部为空")
    except Exception as e:  # noqa: BLE001
        err_pol = e
        print("  [!] 政策失败: %s" % str(e)[:80])
    save_or_keep("policies.json", {"updated_at": now, "updated_at_text": stamp, "items": pol}
                 if pol is not None else None, err_pol, stamp)

    save("meta.json", {"updated_at": now, "updated_at_text": stamp})

    print("写每日快照…")
    n = snapshot_backups()
    print("     备份 %d 个文件" % n)


if __name__ == "__main__":
    main()
