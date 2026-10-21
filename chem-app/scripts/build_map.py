# -*- coding: utf-8 -*-
"""把山东地市 GeoJSON 转成轻量 SVG 路径，供 App 内嵌使用。
投影：等距圆柱 + 纬度余弦修正（省内范围足够准确），y 轴翻转。
简化：Douglas-Peucker，容差按画布尺寸调，去掉海上小岛噪点。
"""
import json, math, os

SRC = os.path.join(os.path.dirname(__file__), "sd_raw.json")
OUT = os.path.join(os.path.dirname(__file__), "..", "data", "sdmap.json")

W = 320.0          # 画布宽度（SVG 单位）
PAD = 4.0
TOL = 0.55         # 简化容差（SVG 单位）
MIN_AREA = 6.0     # 小于此面积(平方 SVG 单位)的碎岛丢弃
BASE_FS = 9.2      # 地名字号（SVG 单位，1 单位≈1.14 屏幕像素 @ 390 宽手机）

d = json.load(open(SRC, encoding="utf-8"))
feats = d["features"]

# ---------- 收集所有点，求包围盒 ----------
allpts = []
for f in feats:
    g = f["geometry"]
    polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
    for poly in polys:
        for ring in poly:
            for lon, lat in ring:
                allpts.append((lon, lat))

lons = [p[0] for p in allpts]
lats = [p[1] for p in allpts]
lat0 = (min(lats) + max(lats)) / 2.0
k = math.cos(math.radians(lat0))      # 经度压缩系数
xs = [lon * k for lon in lons]
ys = [-lat for lat in lats]
minx, maxx = min(xs), max(xs)
miny, maxy = min(ys), max(ys)
scale = (W - 2 * PAD) / (maxx - minx)
H = (maxy - miny) * scale + 2 * PAD


def proj(lon, lat):
    return ((lon * k - minx) * scale + PAD, (-lat - miny) * scale + PAD)


def area(pts):
    s = 0.0
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


def inside(pts, x, y):
    """射线法判断点是否在多边形内"""
    n = len(pts)
    c = False
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        if ((y1 > y) != (y2 > y)) and (x < (x2 - x1) * (y - y1) / (y2 - y1 + 1e-12) + x1):
            c = not c
    return c


def dist_to_edge(pts, x, y):
    best = 1e18
    n = len(pts)
    for i in range(n):
        ax, ay = pts[i]
        bx, by = pts[(i + 1) % n]
        dx, dy = bx - ax, by - ay
        L = dx * dx + dy * dy
        if L == 0:
            d = math.hypot(x - ax, y - ay)
        else:
            t = max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / L))
            d = math.hypot(x - (ax + t * dx), y - (ay + t * dy))
        if d < best:
            best = d
    return best


def best_inside_point(ring, step=2.0):
    """网格采样求「离边界最远」的内部点，作为城市标注位置"""
    xs2 = [q[0] for q in ring]
    ys2 = [q[1] for q in ring]
    x0, x1 = min(xs2), max(xs2)
    y0, y1 = min(ys2), max(ys2)
    best, bp = -1.0, ((x0 + x1) / 2.0, (y0 + y1) / 2.0)
    y = y0
    while y <= y1:
        x = x0
        while x <= x1:
            if inside(ring, x, y):
                d = dist_to_edge(ring, x, y)
                if d > best:
                    best, bp = d, (x, y)
            x += step
        y += step
    return bp, best


def dp(pts, tol):
    """Douglas-Peucker 简化（闭合环按首尾同点处理）"""
    if len(pts) < 4:
        return pts
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        a, b = stack.pop()
        if b - a < 2:
            continue
        ax, ay = pts[a]
        bx, by = pts[b]
        dx, dy = bx - ax, by - ay
        L = math.hypot(dx, dy)
        best, bi = -1.0, -1
        for i in range(a + 1, b):
            px, py = pts[i]
            if L == 0:
                dist = math.hypot(px - ax, py - ay)
            else:
                dist = abs(dy * (px - ax) - dx * (py - ay)) / L
            if dist > best:
                best, bi = dist, i
        if best > tol:
            keep[bi] = True
            stack.append((a, bi))
            stack.append((bi, b))
    return [p for p, kp in zip(pts, keep) if kp]


out = {"viewBox": "0 0 %.1f %.1f" % (W, H), "w": round(W, 1), "h": round(H, 1), "cities": {}}

for f in feats:
    p = f["properties"]
    adcode = str(p["adcode"])
    name = p["name"]
    g = f["geometry"]
    polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]

    paths, biggest, biggest_a = [], None, 0
    for poly in polys:
        ring = [proj(lon, lat) for lon, lat in poly[0]]
        a = area(ring)
        if a < MIN_AREA:
            continue
        simp = dp(ring, TOL)
        if len(simp) < 3:
            continue
        if a > biggest_a:
            biggest_a, biggest = a, simp
        seg = "M" + " ".join("%.1f %.1f" % (x, y) for x, y in simp) + "Z"
        paths.append(seg)

    if not paths:
        continue

    # 标签点：在最大环内部做网格采样，取离边界最远的点（近似最大内切圆圆心）
    # 单纯用包围盒中心，遇到烟台/威海这种狭长形状会落到海里
    (cx, cy), r = best_inside_point(biggest)
    # 地名宽度必须落在城市轮廓内；放不下就改成竖排（淄博这类南北狭长的会用到）
    # 字号按城市宽度自适应（淄博这类狭长的会小一号），再靠描边光晕保证跨边界也读得清
    nchar = len(name.replace("市", ""))
    fs = round(min(BASE_FS, max(7.8, (r - 0.8) * 2.0 / nchar)), 1)
    # 地块太窄（字号被迫缩小）时改用白底名牌，避免文字压到边界上糊成一团
    plate = fs < BASE_FS
    out["cities"][adcode] = {
        "name": name.replace("市", ""),
        "d": "".join(paths),
        "label": [round(cx, 1), round(cy, 1)],
        "fs": round(fs, 1),
    }
    if plate:
        out["cities"][adcode]["plate"] = 1

json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
print("viewBox", out["viewBox"])
print("cities", len(out["cities"]))
print("size %.1f KB" % (os.path.getsize(OUT) / 1024))
for code, c in out["cities"].items():
    print("  ", code, c["name"], "pts", c["d"].count("M"), "label", c["label"])
