/* 高端化工 · 行业认知 App */
(function () {
  "use strict";

  var $ = function (id) { return document.getElementById(id); };
  var app = $("app"), nav = $("nav"), ttl = $("ttl"), meta = $("meta");
  var backBtn = $("back"), favBtn = $("favBtn"), refreshBtn = $("refreshBtn");

  var D = { news: null, prices: null, hist: null, cats: null, parks: null, policies: null, meta: null, map: null };
  var DERR = {};   // 各数据文件本次更新失败原因（后端 save_or_keep 写入的 error）
  var DUPD = {};   // 各数据文件自己的更新时间
  var UI = { block: null, city: "", level: null, q: "", mq: "", cq: "", pq: "" };
  var CUR = { key: null, type: null };

  var FILE_LABEL = { news: "资讯", prices: "行情", prices_history: "K线",
                     categories: "品类", parks: "地图", policies: "政策" };
  // 每个模块依赖哪些数据文件（决定在哪个页面提示「本次更新失败」）
  var MOD_FILES = {
    news: ["news"], prices: ["prices", "prices_history"], cats: ["categories"],
    parks: ["parks"], policies: ["policies"]
  };

  /* ------------------------------------------------ 本地存储 */
  var KEY = "chemapp.v1";
  var SNAP = "chemapp.snaps";
  var SNAP_KEEP = 4;                 // 本地快照保留份数（PRD 7.3-3）
  var WEEK = 7 * 86400000;
  var S = { fav: [], read: [], learned: [], lastOpen: 0, seen: {} };

  function storeLoad() {
    try {
      var s = JSON.parse(localStorage.getItem(KEY) || "null");
      if (s) S = Object.assign(S, s);
    } catch (e) {}
    if (!S.seen || typeof S.seen !== "object") S.seen = {};
    S.lastOpen = Date.now();
    snapMaybe();
    storeSave();
  }
  function storeSave() { try { localStorage.setItem(KEY, JSON.stringify(S)); } catch (e) {} }
  function has(a, v) { return a.indexOf(v) >= 0; }
  function toggle(a, v) { var i = a.indexOf(v); if (i >= 0) a.splice(i, 1); else a.push(v); storeSave(); }

  /* ---- 每周本地快照：环形保留 4 份，误操作可回退（PRD 7.3-3） ---- */
  function snapsGet() {
    try { return JSON.parse(localStorage.getItem(SNAP) || "[]"); } catch (e) { return []; }
  }
  function snapsPut(arr) {
    try { localStorage.setItem(SNAP, JSON.stringify(arr)); return true; } catch (e) { return false; }
  }
  function snapTake() {
    return JSON.parse(JSON.stringify({
      learned: S.learned, read: S.read, fav: S.fav, seen: S.seen
    }));
  }
  function snapMaybe(force) {
    var arr = snapsGet();
    var last = arr.length ? arr[arr.length - 1].ts : 0;
    if (!force && Date.now() - last < WEEK) return arr;
    arr.push({ ts: Date.now(), data: snapTake() });
    while (arr.length > SNAP_KEEP) arr.shift();
    if (!snapsPut(arr)) arr.pop();   // 存不下就放弃这次快照，不影响主流程
    return arr;
  }
  function snapRestore(i) {
    var arr = snapsGet();
    var s = arr[i];
    if (!s) return null;
    return applyRestore(s.data);
  }

  /* ---- 合并式恢复：已有的保留，缺的补上（PRD 7.3-2） ---- */
  function applyRestore(o) {
    var r = { learned: 0, learnedExist: 0, read: 0, readExist: 0, fav: 0, favExist: 0 };
    function add(arr, v, hit, miss) {
      if (arr.indexOf(v) >= 0) { r[miss]++; } else { arr.push(v); r[hit]++; }
    }
    (o.learned || []).forEach(function (v) { add(S.learned, v, "learned", "learnedExist"); });
    (o.read || []).forEach(function (v) { add(S.read, v, "read", "readExist"); });
    (o.fav || []).forEach(function (v) { add(S.fav, v, "fav", "favExist"); });
    if (o.seen && typeof o.seen === "object") {
      Object.keys(o.seen).forEach(function (k) { if (!S.seen[k]) S.seen[k] = o.seen[k]; });
    }
    storeSave();
    return r;
  }
  function restoreText(r) {
    return "新增品类 " + r.learned + " / 已存在 " + r.learnedExist +
      "；新增已读 " + r.read + " / 已存在 " + r.readExist +
      "；新增收藏 " + r.fav + " / 已存在 " + r.favExist;
  }

  /* ------------------------------------------------ 工具 */
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function pct(v) {
    if (v === null || v === undefined || isNaN(v)) return { t: "—", c: "flat" };
    return { t: (v > 0 ? "+" : "") + Number(v).toFixed(2) + "%", c: v > 0 ? "up" : (v < 0 ? "down" : "flat") };
  }
  function px(v) {
    if (v === null || v === undefined) return "—";
    var d = v >= 1000 ? 0 : (v >= 100 ? 1 : 2);
    return Number(v).toFixed(d);
  }
  function dayKey(ts) {
    if (!ts) return "";
    var d = new Date(ts * 1000), n = new Date();
    // 只有日期没有具体时间的（如政策、部分资讯），直接显示日期
    if (d.getHours() === 0 && d.getMinutes() === 0) {
      return (d.getMonth() + 1) + "-" + ("0" + d.getDate()).slice(-2);
    }
    var same = d.toDateString() === n.toDateString();
    if (same) return ("0" + d.getHours()).slice(-2) + ":" + ("0" + d.getMinutes()).slice(-2);
    var diff = (n - d) / 86400000;
    if (diff < 2) return "昨天";
    if (diff < 8) return Math.floor(diff) + "天前";
    return (d.getMonth() + 1) + "-" + d.getDate();
  }
  function dateStr(ts) {
    if (!ts) return "";
    var d = new Date(ts * 1000);
    return d.getFullYear() + "-" + ("0" + (d.getMonth() + 1)).slice(-2) + "-" + ("0" + d.getDate()).slice(-2);
  }

  /* ------------------------------------------------ 数据装载 */
  var FILES = ["news", "prices", "prices_history", "categories", "parks", "policies", "meta", "sdmap"];
  function loadAll() {
    return Promise.all(FILES.map(function (f) {
      return fetch("data/" + f + ".json?_=" + Date.now())
        .then(function (r) { return r.ok ? r.json() : null; })
        .catch(function () { return null; });
    })).then(function (arr) {
      D.news = arr[0]; D.prices = arr[1]; D.hist = arr[2];
      D.cats = arr[3]; D.parks = arr[4]; D.policies = arr[5]; D.meta = arr[6];
      D.map = arr[7];
      IDX = null;
      DERR = {}; DUPD = {};
      FILES.forEach(function (f, i) {
        var v = arr[i];
        if (!v || typeof v !== "object") return;
        if (v.updated_at_text) DUPD[f] = v.updated_at_text;
        if (v.error) DERR[f] = v.error;
      });
      if (D.meta && D.meta.updated_at_text) localStorage.setItem("chemapp.updated", D.meta.updated_at_text);
      netUI();
    });
  }

  /* ------------------------------------------------ 顶栏提示（更新失败 / 离线） */
  function curSeg() { return (location.hash.replace(/^#\/?/, "").split("/")[0]) || "home"; }

  function netUI() {
    var el = $("netbar");
    if (!el) return;
    var seg = curSeg();
    var files = MOD_FILES[seg] || FILES;
    var msgs = [];
    if (navigator.onLine === false) {
      msgs.push("离线 · 显示 " + (localStorage.getItem("chemapp.updated") || "上次") + " 的数据");
    }
    files.forEach(function (f) {
      var e = DERR[f];
      if (!e) return;
      var t = DUPD[f] || localStorage.getItem("chemapp.updated") || "上次";
      msgs.push(FILE_LABEL[f] + "本次更新失败（" + (e.msg || "原因未知") + "），显示 " + t + " 的内容");
    });
    el.hidden = !msgs.length;
    el.textContent = msgs.join("；");
  }
  window.addEventListener("online", netUI);
  window.addEventListener("offline", netUI);

  /* ------------------------------------------------ 数据索引 */
  function allNews() {
    var out = [];
    if (D.news && D.news.blocks) D.news.blocks.forEach(function (b) {
      (b.items || []).forEach(function (i) { var c = Object.assign({}, i); c.block = b.name; out.push(c); });
    });
    return out;
  }
  function allPrices() {
    var out = [];
    if (D.prices && D.prices.groups) D.prices.groups.forEach(function (g) {
      (g.items || []).forEach(function (i) { var c = Object.assign({}, i); c.group = g.name; out.push(c); });
    });
    return out;
  }
  function catById(id) {
    if (!D.cats) return null;
    for (var i = 0; i < D.cats.items.length; i++) if (D.cats.items[i].id === id) return D.cats.items[i];
    return null;
  }
  /* ------------------------------------------------ 园区索引（按地市组织） */
  function cityList() { return (D.parks && D.parks.cities) || []; }

  function cityByCode(code) {
    var a = cityList();
    for (var i = 0; i < a.length; i++) if (a[i].code === code) return a[i];
    return null;
  }

  function allParks() {
    var out = [];
    cityList().forEach(function (c) {
      (c.parks || []).forEach(function (p) {
        var q = Object.assign({}, p);
        q.city = c.name; q.code = c.code;
        out.push(q);
      });
    });
    return out;
  }

  function parkById(id) {
    var a = allParks();
    for (var i = 0; i < a.length; i++) if (a[i].id === id) return a[i];
    return null;
  }

  /* 统计每个地市的园区数 / 企业数 / 高端企业数 */
  function cityStats() {
    var out = {};
    cityList().forEach(function (c) {
      var pk = c.parks || [], ent = 0, he = 0, hg = 0;
      pk.forEach(function (p) {
        (p.enterprises || []).forEach(function (e) { ent++; if (e.high) he++; });
      });
      (c.enterprises || []).forEach(function (e) { ent++; if (e.high) he++; });
      (c.parks || []).forEach(function (p) { if (p.level === "高端为主") hg++; });
      out[c.code] = { parks: pk.length, ents: ent, high: he, hp: hg, heOnly: hg };
    });
    return out;
  }

  /* 高端浓度分档：0 无 / 1 少量 / 2 较多 / 3 最集中 */
  function heatLevel(high) { return high >= 4 ? 3 : (high >= 2 ? 2 : (high >= 1 ? 1 : 0)); }

  function priceByName(n) {
    var a = allPrices();
    for (var i = 0; i < a.length; i++) if (a[i].name === n) return a[i];
    return null;
  }

  /* ------------------------------------------------ 头栏 */
  function setHeader(title, opt) {
    opt = opt || {};
    ttl.textContent = title;
    backBtn.style.display = opt.back ? "flex" : "none";
    if (opt.favKey) {
      favBtn.style.display = "flex";
      CUR.key = opt.favKey;
      CUR.type = opt.favType || "item";
      favBtn.textContent = has(S.fav, opt.favKey) ? "★" : "☆";
      favBtn.className = "hbtn" + (has(S.fav, opt.favKey) ? " on" : "");
    } else {
      favBtn.style.display = "none";
      CUR.key = null;
    }
    var up = (D.meta && D.meta.updated_at_text) || localStorage.getItem("chemapp.updated") || "";
    meta.textContent = up ? "数据更新 " + up : "";
    var seg = (location.hash.replace(/^#\/?/, "").split("/")[0]) || "home";
    Array.prototype.forEach.call(nav.children, function (b) {
      b.className = "tab" + (b.dataset.r === seg ? " on" : "");
    });
    netUI();
  }

  /* ------------------------------------------------ 首页（今日课表）
     首页不生产内容，只按 PRD 3.3 的优先级从各库里挑，且每张卡片都能点进真详情。 */

  /* 企业全量索引：园区内企业 + 市级重点企业 */
  function allEnts() {
    var out = [];
    cityList().forEach(function (c) {
      (c.parks || []).forEach(function (p) {
        (p.enterprises || []).forEach(function (e, i) {
          out.push({ e: e, key: p.id, idx: i, city: c, park: p });
        });
      });
      (c.enterprises || []).forEach(function (e, i) {
        out.push({ e: e, key: "c" + c.code, idx: i, city: c, park: null });
      });
    });
    return out;
  }

  /* 按标题反查企业：取命中最长的那个（避免「海化」抢走「山东海化集团」的新闻） */
  function entByTitle(t) {
    var hit = null, best = 2;
    allEnts().forEach(function (x) {
      var n = x.e.name;
      if (n.length >= 3 && t.indexOf(n) >= 0 && n.length > best) { hit = x; best = n.length; }
    });
    return hit;
  }

  function parkByTitle(t) {
    var hit = null, best = 3;
    allParks().forEach(function (p) {
      var n = p.name;
      if (n && n.length >= 4 && t.indexOf(n) >= 0 && n.length > best) { hit = p; best = n.length; }
    });
    return hit;
  }

  /* ① 今日一品：未学过且有当天新闻 → 未学过 → 已学过里最久没看的 */
  function pickTodayCat() {
    if (!D.cats) return null;
    var all = D.cats.items;
    var today = allNews();
    var un = all.filter(function (c) { return !has(S.learned, c.id); });
    var hot = un.filter(function (c) {
      return today.some(function (n) { return (n.cats || []).indexOf(c.name) >= 0; });
    });
    if (hot.length) return hot[0];
    if (un.length) return un[0];
    return all.slice().sort(function (a, b) {
      return (S.seen[a.id] || 0) - (S.seen[b.id] || 0);
    })[0];
  }

  /* ② 今日一策：近 7 天内，有明确产业影响的优先于程序性通知 */
  var POL_IMPACT_KW = ["产能", "环保", "安全", "关税", "准入", "补贴", "淘汰", "限制",
                       "禁止", "园区", "危化", "许可", "标准", "奖补", "投资", "名录"];
  function pickPolicy() {
    var items = (D.policies && D.policies.items) || [];
    if (!items.length) return null;
    var now = Date.now() / 1000;
    var recent = items.filter(function (p) { return p.ts && now - p.ts <= 7 * 86400; });
    var pool = recent.length ? recent : items;
    var scored = pool.map(function (p) {
      var n = 0;
      POL_IMPACT_KW.forEach(function (k) { if (p.title.indexOf(k) >= 0) n++; });
      return { p: p, w: n, ts: p.ts || 0 };
    });
    scored.sort(function (a, b) { return (b.w - a.w) || (b.ts - a.ts); });
    return scored[0].p;
  }

  /* ③ 今日一动：近 7 天，动作强度高的优先，且必须能反查企业或园区 */
  var ACT_STRONG = ["投产", "开工", "试产", "开车", "点火", "建成", "奠基", "签约",
                    "扩产", "扩建", "环评", "并购", "收购", "中标", "获批"];
  var ACT_WEAK = ["获奖", "荣获", "参会", "论坛", "会议", "调研", "座谈", "颁发",
                  "上榜", "入选", "揭牌"];
  function pickMove() {
    var now = Date.now() / 1000;
    var list = allNews().filter(function (n) { return n.ts && now - n.ts <= 7 * 86400; });
    if (!list.length) list = allNews();
    var scored = list.map(function (n) {
      var s = 0;
      ACT_STRONG.forEach(function (k) { if (n.title.indexOf(k) >= 0) s += 3; });
      ACT_WEAK.forEach(function (k) { if (n.title.indexOf(k) >= 0) s += 1; });
      var ent = entByTitle(n.title);
      var park = ent ? null : parkByTitle(n.title);
      return { n: n, s: s, ent: ent, park: park };
    });
    // 优先取「能落到企业/园区」的，其次动作强度，其次离山东更近，最后按时间
    var LOC = { "山东": 2, "全国": 1, "全球": 0 };
    scored.sort(function (a, b) {
      var ra = (a.ent ? 2 : (a.park ? 1 : 0)), rb = (b.ent ? 2 : (b.park ? 1 : 0));
      return (rb - ra) || (b.s - a.s) ||
        ((LOC[b.n.block] || 0) - (LOC[a.n.block] || 0)) ||
        ((b.n.ts || 0) - (a.n.ts || 0));
    });
    return scored[0] || null;
  }

  /* ④ 价格异动：涨跌幅绝对值前 3，同品种不重复 */
  function pickMovers() {
    var ps = allPrices().filter(function (p) {
      return typeof p.chg === "number" && !isNaN(p.chg);
    });
    ps.sort(function (a, b) { return Math.abs(b.chg) - Math.abs(a.chg); });
    var out = [], seen = {};
    ps.forEach(function (p) {
      if (out.length >= 3 || seen[p.name]) return;
      seen[p.name] = 1;
      out.push(p);
    });
    return out;
  }

  function viewHome() {
    setHeader("高端化工", {});
    var cat = pickTodayCat();
    var pol = pickPolicy();
    var mv = pickMove();
    var movers = pickMovers();
    var used = {};   // 首页去重：同一件事只出现一次

    var h = "";
    if (cat) {
      h += '<a href="#/cat/' + cat.id + '" class="hero" style="display:block">' +
        '<div class="k">今日一品 · 今天学这个</div>' +
        '<div class="t">' + esc(cat.name) + '</div>' +
        '<div class="d">' + esc(cat.one_line) + '</div>' +
        '<div class="go">点开看上下游 →</div></a>';
    }

    if (pol) {
      var pid = pol.id || phash(pol);
      used[pol.title] = 1;
      h += '<div class="card"><div class="card-hd">今日一策</div>' +
        '<a class="jrow" href="#/policy/' + esc(pid) + '" style="display:flex">' +
        '<span class="jtag pol">' + esc(pol.level || "政策") + '</span>' +
        '<div class="jmain"><div class="jt">' + esc(pol.title) + '</div>' +
        '<div class="jm">' + esc(pol.org || "") + ' · ' + esc(dateStr(pol.ts)) + '</div>' +
        (pol.impact ? '<div class="jx">' + esc(pol.impact) + '</div>' : '') +
        '</div></a></div>';
    }

    if (mv) {
      var n = mv.n;
      used[n.title] = 1;
      var href, tag, meta;
      if (mv.ent) {
        href = "#/ent/" + mv.ent.key + "/" + mv.ent.idx;
        tag = "企业动向";
        meta = mv.ent.city.name + ' · ' + (mv.ent.park ? mv.ent.park.name : "市级重点企业") +
          ' · ' + dayKey(n.ts);
      } else if (mv.park) {
        href = "#/park/" + mv.park.id;
        tag = "园区动向";
        meta = mv.park.city + ' · ' + mv.park.name + ' · ' + dayKey(n.ts);
      } else {
        href = n.url || "#";
        tag = "行业动向";
        meta = esc(n.source || "") + ' · ' + dayKey(n.ts) + ' · 未匹配到收录企业';
      }
      var ext = /^#\//.test(href) ? "" : ' target="_blank" rel="noopener"';
      h += '<div class="card"><div class="card-hd">今日一动 <span class="n">' +
        esc(n.source || "") + '</span></div>' +
        '<a class="jrow" href="' + esc(href) + '"' + ext + ' style="display:flex">' +
        '<span class="jtag ent">' + tag + '</span>' +
        '<div class="jmain"><div class="jt">' + esc(n.title) + '</div>' +
        '<div class="jm">' + meta + '</div></div></a></div>';
    }

    if (movers.length) {
      h += '<div class="card"><div class="card-hd">价格异动 <span class="n">按当日涨跌幅</span></div>';
      movers.forEach(function (p) {
        var c = pct(p.chg);
        h += '<a class="mover" href="#/price/' + encodeURIComponent(p.name) + '">' +
          '<div class="mn">' + esc(p.name) + '<i>' + esc(p.code) + '</i>' +
          moverNewsLine(p, used) + '</div>' +
          '<div class="mp"><b class="' + c.c + '">' + px(p.price) + '</b>' +
          '<s class="' + c.c + '">' + c.t + '</s></div></a>';
      });
      h += '</div>';
    }

    var total = D.cats ? D.cats.items.length : 0;
    var lr = S.learned.length;
    var polTotal = (D.policies && D.policies.items || []).length;
    var polRead = S.read.filter(function (k) { return String(k).indexOf("pol:") === 0; }).length;
    h += '<div class="card"><div class="card-hd">学习进度</div><div class="prog">' +
      '<div class="lbl"><span>已学品类</span><span>' + lr + ' / ' + total + '</span></div>' +
      '<div class="bar"><i style="width:' + (total ? Math.round(lr / total * 100) : 0) + '%"></i></div>' +
      '<div class="lbl"><span>已读政策</span><span>' + polRead + ' / ' + polTotal + ' 条</span></div>' +
      '<div class="bar"><i style="width:' + (polTotal ? Math.round(polRead / polTotal * 100) : 0) + '%"></i></div>' +
      '<a class="morelink" href="#/me">我的数据 · 导出 / 导入备份 ›</a>' +
      '</div></div>';

    app.innerHTML = h;
  }

  /* 价格异动下面那行「和这有关的新闻」；已被今日一动用掉的新闻不再重复 */
  function moverNewsLine(p, used) {
    var ns = p.news || [];
    for (var i = 0; i < ns.length; i++) {
      if (!used[ns[i].title]) {
        used[ns[i].title] = 1;
        return '<em class="mnews">' + esc(cut(ns[i].title, 24)) + '</em>';
      }
    }
    return '<em class="mnews none">暂无相关报道</em>';
  }

  function cut(s, n) {
    s = String(s || "");
    return s.length > n ? s.slice(0, n) + "…" : s;
  }
  function phash(p) { return "p" + (p.ts || 0) + p.title.length; }

  /* ------------------------------------------------ 资讯 */
  function viewNews() {
    setHeader("资讯", {});
    if (!D.news || !D.news.blocks) { app.innerHTML = '<div class="empty">资讯数据未加载</div>'; return; }
    var blocks = D.news.blocks;
    if (!UI.block || !blocks.some(function (b) { return b.name === UI.block; })) {
      var f = blocks.filter(function (b) { return b.items && b.items.length; })[0];
      UI.block = f ? f.name : blocks[0].name;
    }
    var b = blocks.filter(function (x) { return x.name === UI.block; })[0];
    var items = (b.items || []).slice();
    if (UI.q) {
      var q = UI.q.toLowerCase();
      items = items.filter(function (i) { return i.title.toLowerCase().indexOf(q) >= 0; });
    }

    var h = '<div class="chips">';
    blocks.forEach(function (x) {
      h += '<button class="chip' + (x.name === UI.block ? " on" : "") + '" data-block="' + esc(x.name) + '">' +
        esc(x.name) + ' ' + ((x.items || []).length) + '</button>';
    });
    h += '</div>';
    h += '<div class="card" style="padding:0"><div style="padding:9px 12px">' +
      '<input id="q" placeholder="搜索资讯关键词" value="' + esc(UI.q) + '" ' +
      'style="width:100%;height:36px;border:1px solid var(--line);border-radius:9px;padding:0 12px;font-size:14px;outline:0;background:#fafbfc"></div></div>';

    if (!items.length) {
      h += '<div class="empty">这个板块今天没有收录到高端化工相关内容<br>' +
        '<span style="font-size:12px">换个板块看看，或点右上角 ⟳ 重新抓取</span></div>';
    } else {
      h += '<div class="card">';
      items.forEach(function (i) {
        h += '<a class="row" href="' + esc(i.url) + '" target="_blank" rel="noopener">' +
          '<div class="main"><div class="rt">' + esc(i.title) + '</div>' +
          '<div class="rm"><span class="tag">' + esc(i.source || "") + '</span>' +
          '<span>' + esc(dayKey(i.ts)) + '</span>' +
          (i.cats && i.cats.length ? '<span class="tag cat">' + esc(i.cats[0]) + '</span>' : '') +
          '</div></div><span class="arrow">›</span></a>';
      });
      h += '</div>';
    }
    app.innerHTML = h;

    Array.prototype.forEach.call(app.querySelectorAll(".chip"), function (c) {
      c.onclick = function () { UI.block = c.dataset.block; UI.q = ""; viewNews(); };
    });
    var qi = $("q");
    if (qi) qi.oninput = function () {
      UI.q = qi.value;
      var pos = qi.selectionStart; viewNews();
      var n = $("q"); if (n) { n.focus(); try { n.setSelectionRange(pos, pos); } catch (e) {} }
    };
  }

  /* ------------------------------------------------ 园区地图 */
  function mapSVG(st) {
    var m = D.map;
    if (!m || !m.cities) return '<div class="empty">地图数据未加载</div>';
    var codes = Object.keys(m.cities);
    var s = '<svg class="sdmap" viewBox="' + m.viewBox + '" preserveAspectRatio="xMidYMid meet">';
    codes.forEach(function (code) {
      var c = m.cities[code];
      var d = st[code] || { high: 0 };
      s += '<path d="' + c.d + '" class="mct t' + heatLevel(d.high) + '" data-code="' + code + '"></path>';
    });
    codes.forEach(function (code) {
      var c = m.cities[code];
      var d = st[code] || { high: 0, parks: 0 };
      var lv = heatLevel(d.high);
      var fs = c.fs || 9.2;
      var cx = c.label[0], cy = c.label[1];
      if (c.plate) {
        // 窄地块（淄博）：白底名牌，文字不压在边界上
        var pw = c.name.length * fs + 6.4;
        var ph = fs + 4.8;
        s += '<rect x="' + (cx - pw / 2).toFixed(1) + '" y="' + (cy - ph / 2 - 1.4).toFixed(1) +
          '" width="' + pw.toFixed(1) + '" height="' + ph.toFixed(1) + '" rx="3" ' +
          'fill="#fff" stroke="#cfdcd9" stroke-width=".5"></rect>' +
          '<text class="mlab mp-l" x="' + cx + '" y="' + (cy + fs * 0.36).toFixed(1) +
          '" text-anchor="middle" style="font-size:' + fs + 'px">' + esc(c.name) + '</text>';
      } else if (c.vert) {
        var chs = c.name.split("");
        s += '<text class="mlab u' + lv + '" x="' + cx + '" text-anchor="middle" style="font-size:' + fs + 'px">';
        chs.forEach(function (ch, i) {
          s += '<tspan x="' + cx + '" y="' + (cy - (chs.length - 1) * fs * 0.52 + i * fs * 1.04) + '">' + esc(ch) + '</tspan>';
        });
        s += '</text>';
      } else {
        s += '<text class="mlab u' + lv + '" x="' + cx + '" y="' + (cy + fs * 0.34).toFixed(1) +
          '" text-anchor="middle" style="font-size:' + fs + 'px">' + esc(c.name) + '</text>';
      }
      if (d.parks > 0 && !c.vert && !c.plate) {
        var by = cy + fs * 0.34 + 6.6;
        s += '<text class="mpk u' + lv + '" x="' + cx + '" y="' + by.toFixed(1) +
          '" text-anchor="middle">' + d.parks + '园</text>';
      }
    });
    s += '</svg>';
    return s;
  }

  /* ------------------------------------------------ 检索索引（地市 / 园区 / 企业） */
  var IDX = null;

  function entEntry(e, href, sub) {
    var cc = (e.cats || []).map(catById).filter(Boolean);
    var catNames = cc.map(function (c) { return c.name; }).join(" ");
    var catProd = cc.map(function (c) { return (c.products || []).join(" "); }).join(" ");
    var hay = [e.name, e.products, e.note, sub, catNames, catProd].join(" ").toLowerCase();
    return {
      t: "企业", n: e.name, s: sub + " · " + (e.products || ""),
      href: href, hay: hay, hi: !!e.high
    };
  }

  function buildIndex() {
    if (IDX) return IDX;
    IDX = [];
    cityList().forEach(function (c) {
      var cityHay = [c.name, c.tagline, c.intro, c.scale,
        (c.chems || []).join(" "),
        (c.clusters || []).map(function (x) { return x.n + x.d; }).join(" ")
      ].join(" ").toLowerCase();
      IDX.push({
        t: "地市", n: c.name, s: c.tagline || "",
        href: "#/city/" + c.code, hay: cityHay, hi: false
      });
      (c.parks || []).forEach(function (p) {
        var ph = [p.name, p.district, p.type, p.intro].join(" ").toLowerCase();
        IDX.push({
          t: "园区", n: p.name,
          s: c.name + " · " + (p.district || "") + " · " + (p.type || ""),
          href: "#/park/" + p.id, hay: (ph + " " + cityHay).toLowerCase(),
          hi: p.level === "高端为主"
        });
        (p.enterprises || []).forEach(function (e, i) {
          IDX.push(entEntry(e, "#/ent/" + p.id + "/" + i, c.name + " · " + p.name));
        });
      });
      (c.enterprises || []).forEach(function (e, i) {
        IDX.push(entEntry(e, "#/ent/c" + c.code + "/" + i, c.name + " · 市级重点企业"));
      });
    });
    return IDX;
  }

  function namePos(x, terms) {
    var n = (x.n || "").toLowerCase(), best = 999;
    terms.forEach(function (t) {
      var p = n.indexOf(t);
      if (p >= 0 && p < best) best = p;
    });
    return best;
  }

  function typeRank(t, byName) {
    // 名称命中时，地市优先；仅在内容里命中时，企业优先（搜产品词时想先看到公司）
    if (byName) return t === "地市" ? 0 : (t === "园区" ? 1 : 2);
    return t === "企业" ? 0 : (t === "园区" ? 1 : 2);
  }

  function searchHits(q) {
    var terms = q.toLowerCase().split(/\s+/).filter(Boolean);
    if (!terms.length) return [];
    return buildIndex().filter(function (x) {
      return terms.every(function (t) { return x.hay.indexOf(t) >= 0; });
    }).sort(function (a, b) {
      var pa = namePos(a, terms), pb = namePos(b, terms);
      var ea = (terms.length === 1 && (a.n || "").toLowerCase() === terms[0]) ? 0 : 1;
      var eb = (terms.length === 1 && (b.n || "").toLowerCase() === terms[0]) ? 0 : 1;
      var ka = pa === 999 ? 2 : ea, kb = pb === 999 ? 2 : eb;
      if (ka !== kb) return ka - kb;                 // 完全同名 → 名称含词 → 仅内容命中
      if (pa !== pb) return pa - pb;                 // 名称命中越靠前越优先
      var ta = typeRank(a.t, pa < 999), tb = typeRank(b.t, pb < 999);
      if (ta !== tb) return ta - tb;
      return a.n.length - b.n.length;
    });
  }

  function viewParks() {
    setHeader("山东化工地图", {});
    if (!D.parks) { app.innerHTML = '<div class="empty">园区数据未加载</div>'; return; }
    var st = cityStats();
    var T = { parks: 0, ents: 0, high: 0 };
    Object.keys(st).forEach(function (k) { T.parks += st[k].parks; T.ents += st[k].ents; T.high += st[k].high; });

    /* ---- 搜索栏 ---- */
    var h = '<div class="card" style="padding:10px 12px 4px">' +
      '<div class="sbar"><span class="sic">⌕</span>' +
      '<input id="mq" type="search" placeholder="搜地市 / 园区 / 企业 / 产品" value="' + esc(UI.mq || "") + '">' +
      '<button id="mqx" class="sx"' + ((UI.mq) ? '' : ' style="display:none"') + '>✕</button></div>' +
      '<div class="skw">' +
      ['万华', '轮胎', '地炼', '纯碱', '聚氨酯', '淄博'].map(function (k) {
        return '<button class="chip sm" data-kw="' + k + '">' + k + '</button>';
      }).join("") + '</div></div>';

    h += '<div id="mres"></div>';

    h += '<div id="mmain">';
    h += '<div class="mapcard">' + mapSVG(st) +
      '<div class="legend"><span class="lg">高端企业</span>' +
      '<i class="sw t0"></i><span>0</span>' +
      '<i class="sw t1"></i><span>1</span>' +
      '<i class="sw t2"></i><span>2–3</span>' +
      '<i class="sw t3"></i><span>4+</span>' +
      '</div></div>';

    h += '<div class="card kpis">' +
      '<div class="kp"><b>16</b><span>地市</span></div>' +
      '<div class="kp"><b>' + T.parks + '</b><span>化工园区</span></div>' +
      '<div class="kp"><b>' + T.ents + '</b><span>收录企业</span></div>' +
      '<div class="kp hi"><b>' + T.high + '</b><span>高端企业</span></div>' +
      '</div>';

    var rank = cityList().slice().sort(function (a, b) {
      var sa = st[a.code] || {}, sb = st[b.code] || {};
      return (sb.high - sa.high) || (sb.parks - sa.parks);
    }).filter(function (c) { return (st[c.code] || {}).high > 0; }).slice(0, 5);

    h += '<div class="sec-title">高端化工最集中</div><div class="card">';
    rank.forEach(function (c) {
      var s = st[c.code];
      h += '<a class="row" href="#/city/' + c.code + '">' +
        '<div class="main"><div class="rt">' + esc(c.name) + '</div>' +
        '<div class="rm"><span class="tag he">高端 ' + s.high + '</span>' +
        '<span>' + s.parks + ' 个园区</span><span>' + s.ents + ' 家企业</span></div></div>' +
        '<span class="arrow">›</span></a>';
    });
    h += '</div>';

    var byEnt = cityList().slice().sort(function (a, b) {
      return (st[b.code] || {}).ents - (st[a.code] || {}).ents;
    }).slice(0, 6);
    h += '<div class="sec-title">企业收录最多 <span class="subtle">· 点进去看全量</span></div><div class="card">';
    byEnt.forEach(function (c) {
      var s = st[c.code];
      h += '<a class="row" href="#/city/' + c.code + '">' +
        '<div class="main"><div class="rt">' + esc(c.name) +
        (c.region ? ' <span class="tag">' + esc(c.region) + '</span>' : '') + '</div>' +
        '<div class="rm"><span>' + s.ents + ' 家企业</span>' +
        '<span>' + s.parks + ' 个园区</span>' +
        '<span class="tag cat">' + (c.chems || []).slice(0, 3).join(" / ") + '</span></div></div>' +
        '<span class="arrow">›</span></a>';
    });
    h += '</div></div>';

    h += '<div class="hint">点击地图上任意地市，看该市的化工产业定位、园区与代表企业；' +
      '也可以在顶部搜企业名、园区名或产品（如「MDI」「轮胎」「纯碱」）。' +
      '颜色深浅＝该市收录的高端化工企业数量。整理日期：' + esc(D.parks.updated_at_text || "") + '</div>';

    app.innerHTML = h;

    var svg = app.querySelector(".sdmap");
    if (svg) {
      svg.addEventListener("click", function (e) {
        var t = e.target;
        while (t && t !== svg && !(t.dataset && t.dataset.code)) t = t.parentNode;
        if (t && t.dataset && t.dataset.code) location.hash = "#/city/" + t.dataset.code;
      });
    }

    /* ---- 搜索交互（局部刷新，不打断输入） ---- */
    var qi = $("mq"), box = $("mres"), main = $("mmain"), clr = $("mqx");

    function paint() {
      var q = (UI.mq || "").trim();
      if (clr) clr.style.display = q ? "flex" : "none";
      if (!q) { box.innerHTML = ""; box.style.display = "none"; main.style.display = ""; return; }
      var hits = searchHits(q);
      main.style.display = "none";
      box.style.display = "";
      if (!hits.length) {
        box.innerHTML = '<div class="card"><div class="empty">没有找到「' + esc(q) + '」<br>' +
          '<span style="font-size:12px">试试企业简称（万华、京博）或产品（MDI、烧碱、轮胎）</span></div></div>';
        return;
      }
      var cap = 40, shown = hits.slice(0, cap);
      var s = '<div class="hint" style="padding:2px 2px 8px">匹配 ' + hits.length + ' 条' +
        (hits.length > cap ? '，显示前 ' + cap + ' 条，再输入一个字缩小范围' : '') + '</div>';
      s += '<div class="card">';
      shown.forEach(function (x) {
        s += '<a class="row" href="' + esc(x.href) + '">' +
          '<div class="main"><div class="rt">' + esc(x.n) +
          (x.hi ? ' <span class="tag he">高端</span>' : '') + '</div>' +
          '<div class="rm"><span class="tag cat">' + esc(x.t) + '</span>' +
          '<span>' + esc((x.s || "").slice(0, 52)) + '</span></div></div>' +
          '<span class="arrow">›</span></a>';
      });
      s += '</div>';
      box.innerHTML = s;
    }

    if (qi) qi.oninput = function () { UI.mq = qi.value; paint(); };
    if (clr) clr.onclick = function () {
      UI.mq = ""; if (qi) { qi.value = ""; qi.focus(); } paint();
    };
    Array.prototype.forEach.call(app.querySelectorAll(".chip.sm"), function (b) {
      b.onclick = function () {
        UI.mq = b.dataset.kw;
        if (qi) { qi.value = UI.mq; qi.focus(); }
        paint();
      };
    });
    paint();
  }

  /* ------------------------------------------------ 地市详情 */
  function viewCity(code) {
    var c = cityByCode(code);
    if (!c) { app.innerHTML = '<div class="empty">未找到该地市</div>'; return; }
    setHeader(c.name + " · 化工产业", { back: true });
    var s = cityStats()[code] || { parks: 0, ents: 0, high: 0 };

    var h = '<div class="dt">' + esc(c.name) + '</div>' +
      '<div class="dsub">' + esc(c.tagline) + '</div>';

    h += '<div class="card kpis">' +
      '<div class="kp"><b>' + (c.parks || []).length + '</b><span>化工园区</span></div>' +
      '<div class="kp"><b>' + s.ents + '</b><span>收录企业</span></div>' +
      '<div class="kp hi"><b>' + s.high + '</b><span>高端企业</span></div>' +
      '</div>';

    h += '<div class="card"><div class="card-hd">产业概况' +
      (c.region ? '<span class="n">' + esc(c.region) + '</span>' : '') + '</div>' +
      (c.scale ? '<div class="scalebar">' + esc(c.scale) + '</div>' : '') +
      '<div class="card-bd" style="font-size:14px;line-height:1.72">' + esc(c.intro) + '</div></div>';

    if (c.clusters && c.clusters.length) {
      h += '<div class="sec-title">产业集群 ' + c.clusters.length + '</div><div class="card">';
      c.clusters.forEach(function (x) {
        h += '<div class="field"><div class="fk">' + esc(x.n) + '</div>' +
          '<div class="fv" style="font-size:13.5px;line-height:1.6">' + esc(x.d) + '</div></div>';
      });
      h += '</div>';
    }

    if (c.chems && c.chems.length) {
      h += '<div class="sec-title">本地重点品种</div><div class="pills">';
      c.chems.forEach(function (x) {
        h += '<span class="pill tap" data-f="' + esc(x) + '">' + esc(x) + '</span>';
      });
      h += '</div><div class="hint" style="padding:2px 2px 10px">点品种可跳到地图页，搜出全省做这个品种的企业。</div>';
    }

    if (c.angle) {
      h += '<div class="angle">' + c.angle + '</div>';
    }

    if (c.pillars && c.pillars.length) {
      h += '<div class="sec-title">主导方向 <span class="subtle">◆ 为高端环节</span></div><div class="pills">';
      c.pillars.forEach(function (p) {
        h += '<span class="pill' + (p.he ? " he" : "") + '">' + (p.he ? "◆ " : "") + esc(p.n) + '</span>';
      });
      h += '</div>';
    }

    h += '<div class="sec-title">化工园区 ' + (c.parks || []).length + '</div>';
    if ((c.parks || []).length) {
      h += '<div class="card">';
      c.parks.forEach(function (p) {
        var ents = p.enterprises || [];
        var hp = ents.filter(function (e) { return e.high; }).length;
        var lvl = p.level === "高端为主" ? "he" : (p.level === "高端+基础" ? "hem" : "");
        h += '<a class="row" href="#/park/' + p.id + '">' +
          '<div class="main"><div class="rt">' + esc(p.name) + '</div>' +
          '<div class="rm">' + (lvl ? '<span class="tag ' + lvl + '">' + esc(p.level) + '</span>' : '<span class="tag">' + esc(p.level) + '</span>') +
          '<span>' + esc(p.district || "") + '</span>' +
          '<span>' + ents.length + ' 家' + (hp ? ' · 高端 ' + hp : '') + '</span></div>' +
          '<div class="rm">' + esc(p.type || "") + '</div></div>' +
          '<span class="arrow">›</span></a>';
      });
      h += '</div>';
    } else {
      h += '<div class="card"><div class="empty" style="padding:26px 20px">暂未收录该市的化工园区<br>' +
        '<span style="font-size:12px">没有可靠来源时留空，不拼凑</span></div></div>';
    }

    if ((c.enterprises || []).length) {
      h += '<div class="sec-title">市级代表企业 ' + c.enterprises.length + '</div><div class="card">';
      c.enterprises.forEach(function (e, i) {
        var dyn = entNews(e);
        h += '<a class="row" href="#/ent/c' + code + '/' + i + '">' +
          '<div class="main"><div class="rt">' + esc(e.name) + '</div>' +
          '<div class="rm">' + (e.high ? '<span class="tag he">高端</span>' : '') +
          '<span>' + esc(e.products).slice(0, 38) + '</span>' +
          (e.verify ? '<span class="tag wr">待核</span>' : '') +
          (dyn.length ? '<span class="tag cat">动态 ' + dyn.length + '</span>' : '') +
          '</div></div><span class="arrow">›</span></a>';
      });
      h += '</div>';
    }

    h += '<div class="hint">' + (c.note ? esc(c.note) + '<br>' : '') +
      '「高端为主 / 高端+基础 / 基础为主」是按园区主导方向判断，不是高端企业占比。' +
      '园区与企业为人工整理，标「待核」的条目建议以官方公示核对。整理日期：' +
      esc(D.parks.updated_at_text || "") + '</div>';

    app.innerHTML = h;

    Array.prototype.forEach.call(app.querySelectorAll(".pill.tap"), function (b) {
      b.onclick = function () {
        UI.mq = b.dataset.f || "";
        if (location.hash === "#/parks") viewParks();
        else location.hash = "#/parks";
      };
    });
  }

  /* ------------------------------------------------ 园区详情 */
  function viewPark(id) {
    var p = parkById(id);
    if (!p) { app.innerHTML = '<div class="empty">未找到该园区</div>'; return; }
    setHeader(p.name, { back: true });
    var lvl = p.level === "高端为主" ? "he" : (p.level === "高端+基础" ? "hem" : "");
    var h = '<div class="dt">' + esc(p.name) + '</div>' +
      '<div class="dsub">' + esc(p.city) + ' · ' + esc(p.district || "") + ' · ' + esc(p.type || "") + '</div>';
    h += '<div class="card"><div class="card-bd" style="padding-bottom:8px">' +
      '<span class="tag ' + (lvl || "") + '" style="font-size:11.5px;padding:3px 9px">' + esc(p.level) + '</span>' +
      '</div><div class="card-bd" style="font-size:14px;line-height:1.72;padding-top:0">' + esc(p.intro) + '</div></div>';
    h += '<div class="sec-title">园内代表企业 ' + (p.enterprises || []).length + ' 家</div><div class="card">';
    (p.enterprises || []).forEach(function (e, i) {
      var dyn = entNews(e);
      h += '<a class="row" href="#/ent/' + p.id + '/' + i + '">' +
        '<div class="main"><div class="rt">' + esc(e.name) + '</div>' +
        '<div class="rm">' + (e.high ? '<span class="tag he">高端</span>' : '') +
        '<span>' + esc(e.products).slice(0, 38) + '</span>' +
        (e.verify ? '<span class="tag wr">待核</span>' : '') +
        (dyn.length ? '<span class="tag cat">动态 ' + dyn.length + '</span>' : '') +
        '</div></div><span class="arrow">›</span></a>';
    });
    h += '</div><div class="hint">整理日期：' + esc(D.parks.updated_at_text || "") + '</div>';
    app.innerHTML = h;
  }

  function entNews(e) {
    var keys = e.match || [e.name];
    return allNews().filter(function (n) {
      return keys.some(function (k) { return n.title.indexOf(k) >= 0; });
    }).sort(function (a, b) { return (b.ts || 0) - (a.ts || 0); });
  }

  /* 超过 3 个月的动态灰掉：企业页最怕拿三个月前的旧闻当现状（G12） */
  function isOld(ts) { return !!ts && (Date.now() / 1000 - ts) > 90 * 86400; }

  function viewEnt(key, idx) {
    var c = null, p = null, e = null;
    if (/^c\d{6}$/.test(key)) {
      c = cityByCode(key.slice(1));
      if (c) e = (c.enterprises || [])[idx];
    } else {
      p = parkById(key);
      if (p) { e = (p.enterprises || [])[idx]; c = cityByCode(p.code); }
    }
    if (!e) { app.innerHTML = '<div class="empty">未找到该企业</div>'; return; }
    setHeader(e.name, { back: true, favKey: "ent:" + key + ":" + idx });
    var dyn = entNews(e);
    var cats = (e.cats || []).map(catById).filter(Boolean);

    var h = '<div class="dt">' + esc(e.name) + '</div>' +
      '<div class="dsub">' + (p ? esc(p.name) + ' · ' : '') + (c ? esc(c.name) : '') + '</div>';

    if (e.high) {
      h += '<div class="hint" style="padding:0 2px 10px"><span class="tag he">◆ 高端化工环节</span></div>';
    }

    h += '<div class="card"><div class="field"><div class="fk">主营产品范围</div>' +
      '<div class="fv">' + esc(e.products) + '</div></div>' +
      (e.note ? '<div class="field"><div class="fk">一句话印象</div><div class="fv">' + esc(e.note) + '</div></div>' : '') +
      (e.verify ? '<div class="field"><div class="fk">待核</div><div class="fv" style="font-size:12.5px;color:var(--sub)">' +
        '这条的园区归属或产品线建议以官方公示核对后再引用</div></div>' : '') +
      '</div>';

    if (cats.length) {
      h += '<div class="sec-title">所属品类</div><div class="card">';
      cats.forEach(function (cc) {
        h += '<a class="row" href="#/cat/' + cc.id + '"><div class="main"><div class="rt">' + esc(cc.name) + '</div>' +
          '<div class="rm">' + esc(cc.one_line) + '</div></div><span class="arrow">›</span></a>';
      });
      h += '</div>';
    }

    if (c) {
      h += '<div class="sec-title">所属地市</div><div class="card">' +
        '<a class="row" href="#/city/' + c.code + '"><div class="main">' +
        '<div class="rt">' + esc(c.name) + ' · 化工产业</div>' +
        '<div class="rm"><span>' + esc(c.tagline) + '</span></div></div><span class="arrow">›</span></a></div>';
    }

    h += '<div class="sec-title">企业动态 <span class="subtle">· 由资讯自动匹配</span></div>';
    if (dyn.length) {
      h += '<div class="card">';
      dyn.slice(0, 8).forEach(function (n) {
        h += '<a class="row" href="' + esc(n.url) + '" target="_blank" rel="noopener">' +
          '<div class="main"><div class="rt">' + esc(n.title) + '</div>' +
          '<div class="rm"><span class="tag">' + esc(n.source) + '</span>' +
          '<span' + (isOld(n.ts) ? ' class="old"' : '') + '>' + esc(dateStr(n.ts)) +
          (isOld(n.ts) ? ' · 3个月前' : '') + '</span></div>' +
          '</div><span class="arrow">›</span></a>';
      });
      h += '</div>';
    } else {
      h += '<div class="card"><div class="empty" style="padding:28px 20px">近期暂无收录<br>' +
        '<span style="font-size:12px">资讯流里还没有匹配到这家企业的报道，不做编造</span></div></div>';
    }
    app.innerHTML = h;
  }

  /* ------------------------------------------------ 品类 */
  function viewCats() {
    setHeader("化工品类", {});
    if (!D.cats) { app.innerHTML = '<div class="empty">品类数据未加载</div>'; return; }
    var h = '<div class="card" style="padding:10px 12px 4px">' +
      '<div class="sbar"><span class="sic">⌕</span>' +
      '<input id="cq" type="search" placeholder="搜品类或产品，如 MDI / 纯碱 / 轮胎" value="' + esc(UI.cq || "") + '"></div></div>';

    var q = (UI.cq || "").trim().toLowerCase();
    var total = D.cats.items.length;

    if (q) {
      var hits = D.cats.items.filter(function (c) {
        var hay = [c.name, c.one_line, c.shandong, (c.products || []).join(" "),
          (c.leaders || []).map(function (x) { return x.name; }).join(" ")].join(" ").toLowerCase();
        return hay.indexOf(q) >= 0;
      });
      h += '<div class="hint" style="padding:2px 2px 8px">匹配 ' + hits.length + ' / ' + total + ' 个品类</div>';
      if (!hits.length) {
        h += '<div class="card"><div class="empty">没有找到「' + esc(q) + '」<br>' +
          '<span style="font-size:12px">换个说法试试，比如「聚丙烯」而不是「PP 料」</span></div></div>';
      } else {
        h += '<div class="card">';
        hits.forEach(function (c) {
          h += '<a class="row" href="#/cat/' + c.id + '">' +
            '<div class="main"><div class="rt">' + esc(c.name) + '</div>' +
            '<div class="rm">' + esc(c.one_line || '') + '</div></div><span class="arrow">›</span></a>';
        });
        h += '</div>';
      }
    } else {
      D.cats.groups.forEach(function (g) {
        h += '<div class="sec-title">' + esc(g.name) + ' <span class="subtle">' + g.items.length + '</span></div><div class="card">';
        g.items.forEach(function (id) {
          var c = catById(id);
          if (!c) return;
          var done = has(S.learned, c.id);
          h += '<a class="row" href="#/cat/' + c.id + '">' +
            '<div class="main"><div class="rt">' + esc(c.name) + (done ? ' <span class="tag cat">已学</span>' : '') + '</div>' +
            '<div class="rm">' + esc(c.one_line) + '</div></div><span class="arrow">›</span></a>';
        });
        h += '</div>';
      });
      h += '<div class="hint">共 ' + total + ' 个品类 / ' + D.cats.groups.length + ' 组 · 每个品类都按成本锚、需求锚、供给、山东位置、流向、储运门槛六问展开 · 整理日期 ' +
        esc(D.cats.updated_at_text || "") + '</div>';
    }

    app.innerHTML = h;

    var qi = $("cq");
    if (qi) qi.oninput = function () {
      UI.cq = qi.value;
      var pos = qi.selectionStart; viewCats();
      var n = $("cq"); if (n) { n.focus(); try { n.setSelectionRange(pos, pos); } catch (e) {} }
    };
  }

  function viewCat(id) {
    var c = catById(id);
    if (!c) { app.innerHTML = '<div class="empty">未找到品类</div>'; return; }
    if (!has(S.learned, c.id)) { S.learned.push(c.id); storeSave(); }
    S.seen[c.id] = Date.now();   // 记录「最久没看」，供首页今日一品挑选用
    storeSave();
    setHeader(c.name, { back: true, favKey: "cat:" + c.id });

    var fields = [
      ["成本锚", c.cost], ["需求锚", c.demand], ["供给格局", c.supply],
      ["山东的位置", c.shandong], ["流向", c.flow], ["储运门槛", c.logistics]
    ];
    var h = '<div class="dt">' + esc(c.name) + '</div><div class="dsub">' + esc(c.one_line) + '</div>';
    h += '<div class="card">';
    fields.forEach(function (f) {
      h += '<div class="field"><div class="fk">' + f[0] + '</div><div class="fv">' + esc(f[1]) + '</div></div>';
    });
    h += '</div>';

    h += '<div class="sec-title">代表产品</div><div class="card"><div class="card-bd" style="display:flex;flex-wrap:wrap;gap:7px">';
    (c.products || []).forEach(function (p) {
      h += '<span class="tag cat" style="font-size:12px;padding:4px 9px">' + esc(p) + '</span>';
    });
    h += '</div></div>';

    h += '<div class="sec-title">头部企业</div><div class="card">';
    (c.leaders || []).forEach(function (l) {
      var hit = findEnt(l.name);
      if (hit) {
        h += '<a class="row" href="#/ent/' + hit.key + '/' + hit.idx + '">' +
          '<div class="main"><div class="rt">' + esc(l.name) + '</div>' +
          '<div class="rm">' + esc(l.note || '') + ' · 园区收录</div></div>' +
          '<span class="arrow">›</span></a>';
      } else {
        /* 省外/国外公司：不做成可点链接（点了没反应更糟），
           标明不在山东名录里，并给一个「查它有没有山东据点」的入口 */
        h += '<div class="row"><div class="main">' +
          '<div class="rt">' + esc(l.name) + '</div>' +
          '<div class="rm"><span class="leader off">' + (l.note ? esc(l.note) + ' · ' : '') +
          '不在山东名录<i>省外/国外</i></span>' +
          '<a class="lk" href="#/parks/' + encodeURIComponent(l.name) + '">查山东据点</a>' +
          '</div></div></div>';
      }
    });
    h += '</div>';

    if (c.price_links && c.price_links.length) {
      h += '<div class="sec-title">相关行情</div><div class="card">';
      c.price_links.forEach(function (n) {
        var p = priceByName(n);
        if (!p) return;
        var cc = pct(p.chg);
        h += '<a class="mover" href="#/price/' + encodeURIComponent(n) + '">' +
          '<div class="mn">' + esc(n) + '</div><div class="mp"><b class="' + cc.c + '">' + px(p.price) + '</b>' +
          '<s class="' + cc.c + '">' + cc.t + '</s></div></a>';
      });
      h += '<div class="hint" style="padding:2px 12px 10px">这一项是该品类的同品种或成本锚期货，' +
        '不是这个品种本身的现货成交价。</div></div>';
    } else {
      h += '<div class="sec-title">相关行情</div><div class="card"><div class="empty" ' +
        'style="padding:22px 20px">暂无对应期货品种<br>' +
        '<span style="font-size:12px">这个品类在国内期货市场没有上市合约，不硬凑一个品种给你</span>' +
        '</div></div>';
    }

    var rel = allNews().filter(function (n) {
      return (n.cats || []).indexOf(c.name) >= 0;
    });
    if (rel.length) {
      h += '<div class="sec-title">相关资讯</div><div class="card">';
      rel.slice(0, 6).forEach(function (n) {
        h += '<a class="row" href="' + esc(n.url) + '" target="_blank" rel="noopener">' +
          '<div class="main"><div class="rt">' + esc(n.title) + '</div>' +
          '<div class="rm"><span class="tag">' + esc(n.source) + '</span><span>' + esc(dayKey(n.ts)) + '</span></div>' +
          '</div><span class="arrow">›</span></a>';
      });
      h += '</div>';
    }
    h += '<div class="hint">品类知识为人工整理，行业变化快，发现出入请指出。</div>';
    app.innerHTML = h;
  }

  function findEnt(name) {
    if (!D.parks) return null;
    var a = allParks();
    for (var i = 0; i < a.length; i++) {
      var p = a[i];
      for (var j = 0; j < (p.enterprises || []).length; j++) {
        if (p.enterprises[j].name.indexOf(name) >= 0 || name.indexOf(p.enterprises[j].name) >= 0) {
          return { key: p.id, idx: j };
        }
      }
    }
    var cs = cityList();
    for (var k = 0; k < cs.length; k++) {
      var es = cs[k].enterprises || [];
      for (var m = 0; m < es.length; m++) {
        if (es[m].name.indexOf(name) >= 0 || name.indexOf(es[m].name) >= 0) {
          return { key: "c" + cs[k].code, idx: m };
        }
      }
    }
    return null;
  }

  /* ------------------------------------------------ 行情 */
  function viewPrices() {
    setHeader("化工原料行情", {});
    if (!D.prices) { app.innerHTML = '<div class="empty">行情数据未加载</div>'; return; }
    var q = UI.q.toLowerCase();
    var h = '<div class="card" style="padding:0"><div style="padding:9px 12px">' +
      '<input id="q" placeholder="搜索品种" value="' + esc(UI.q) + '" ' +
      'style="width:100%;height:36px;border:1px solid var(--line);border-radius:9px;padding:0 12px;font-size:14px;outline:0;background:#fafbfc"></div></div>';
    var any = false;
    D.prices.groups.forEach(function (g) {
      var items = g.items.filter(function (i) { return !q || i.name.toLowerCase().indexOf(q) >= 0; });
      if (!items.length) return;
      any = true;
      h += '<div class="card"><div class="card-hd">' + esc(g.name) +
        '<span class="n">' + items.length + ' 个</span></div>';
      items.forEach(function (p) {
        var c = pct(p.chg);
        h += '<a class="mover" href="#/price/' + encodeURIComponent(p.name) + '">' +
          '<div class="mn">' + esc(p.name) + '<i>' + esc(p.code) + '</i></div>' +
          '<div class="mp"><b class="' + c.c + '">' + px(p.price) + '</b>' +
          '<s class="' + c.c + '">' + c.t + '</s></div></a>';
      });
      h += '</div>';
    });
    if (!any) h += '<div class="empty">没有匹配的品种</div>';
    h += '<div class="hint">价格为期货主连收盘/最新价，红涨绿跌。期货价不等于现货成交价。</div>';
    app.innerHTML = h;
    var qi = $("q");
    if (qi) qi.oninput = function () {
      UI.q = qi.value; var pos = qi.selectionStart; viewPrices();
      var n = $("q"); if (n) { n.focus(); try { n.setSelectionRange(pos, pos); } catch (e) {} }
    };
  }

  function viewPrice(name) {
    var p = priceByName(name);
    if (!p) { app.innerHTML = '<div class="empty">未找到该品种</div>'; return; }
    setHeader(name, { back: true, favKey: "px:" + name });
    var c = pct(p.chg);
    var h = '<div class="dt">' + esc(p.name) + '</div>' +
      '<div class="dsub">' + esc(p.ex) + ' · ' + esc(p.code) + ' · ' + esc(p.group) + '</div>';

    h += '<div class="card"><div class="big">' +
      '<div class="px ' + c.c + '">' + px(p.price) + '</div>' +
      '<div class="ch ' + c.c + '">' + c.t + (p.chg_amt !== null && p.chg_amt !== undefined ? '（' + (p.chg_amt > 0 ? '+' : '') + px(p.chg_amt) + '）' : '') + '</div>' +
      '</div></div>';

    h += '<div class="card"><div class="card-hd">K 线 <span class="n" id="klabel">近 30 个交易日</span></div>' +
      '<canvas id="kline"></canvas><div class="periods" id="periods">' +
      '<button data-d="30" class="on">30 天</button><button data-d="90">90 天</button><button data-d="250">250 天</button>' +
      '</div></div>';

    var rows = (D.hist && D.hist.series && D.hist.series[p.name]) || [];
    var stats = "";
    if (rows.length > 20) {
      var last = rows[rows.length - 1][2];
      var ago = rows[Math.max(0, rows.length - 21)][2];
      var ch30 = (last - ago) / ago * 100;
      var hi = Math.max.apply(null, rows.slice(-30).map(function (r) { return r[3]; }));
      var lo = Math.min.apply(null, rows.slice(-30).map(function (r) { return r[4]; }));
      stats = '<div class="kv"><span class="k">近 30 日涨跌</span><span class="v ' + (ch30 >= 0 ? "up" : "down") + '">' +
        (ch30 >= 0 ? "+" : "") + ch30.toFixed(2) + '%</span></div>' +
        '<div class="kv"><span class="k">近 30 日最高 / 最低</span><span class="v">' + px(hi) + ' / ' + px(lo) + '</span></div>';
    }
    if (stats) h += '<div class="card">' + stats + '</div>';

    if (p.reason) {
      h += '<div class="card"><div class="card-hd">影响原因</div>' +
        '<div class="ai"><div class="lb">AI 推断 · 仅供参考</div>' +
        '<div class="tx">' + esc(p.reason.text) + '</div>' +
        '<div class="bs">推断依据来自下列新闻标题，未做人工核实</div></div>';
    }

    if (p.news && p.news.length) {
      h += '<div class="sec-title">相关新闻' + (p.reason ? '' : '（暂无可推断原因，仅列原文）') + '</div><div class="card">';
      p.news.forEach(function (n) {
        h += '<a class="row" href="' + esc(n.url) + '" target="_blank" rel="noopener">' +
          '<div class="main"><div class="rt">' + esc(n.title) + '</div>' +
          '<div class="rm"><span class="tag">' + esc(n.source) + '</span><span>' + esc(dayKey(n.ts)) + '</span></div>' +
          '</div><span class="arrow">›</span></a>';
      });
      h += '</div>';
    } else {
      h += '<div class="card"><div class="empty" style="padding:26px 20px">暂无关联新闻<br>' +
        '<span style="font-size:12px">拿不到依据时不做猜测</span></div></div>';
    }

    app.innerHTML = h;

    var cv = $("kline"), cur = 30;
    function redraw() {
      var sel = rows.slice(-cur);
      drawK(cv, sel);
      var lb = $("klabel");
      if (lb) lb.textContent = "近 " + sel.length + " 个交易日";
    }
    if (rows.length) redraw(); else cv.parentNode.insertAdjacentHTML("beforeend",
      '<div class="empty" style="padding:20px">暂无 K 线数据</div>');

    Array.prototype.forEach.call(document.querySelectorAll("#periods button"), function (b) {
      b.onclick = function () {
        Array.prototype.forEach.call(document.querySelectorAll("#periods button"), function (x) { x.className = ""; });
        b.className = "on"; cur = parseInt(b.dataset.d, 10); redraw();
      };
    });
  }

  function drawK(cv, rows) {
    if (!cv || !rows.length) return;
    var dpr = window.devicePixelRatio || 1;
    var W = cv.clientWidth || cv.parentNode.clientWidth - 28;
    var H = 190;
    cv.width = W * dpr; cv.height = H * dpr;
    cv.style.width = W + "px"; cv.style.height = H + "px";
    var c = cv.getContext("2d");
    c.setTransform(dpr, 0, 0, dpr, 0, 0);
    c.clearRect(0, 0, W, H);

    var padL = 34, padR = 8, padT = 10, padB = 18;
    var iw = W - padL - padR, ih = H - padT - padB;
    var hi = -Infinity, lo = Infinity;
    rows.forEach(function (r) { hi = Math.max(hi, r[3]); lo = Math.min(lo, r[4]); });
    var span = hi - lo || 1;
    hi += span * 0.06; lo -= span * 0.06; span = hi - lo;
    function y(v) { return padT + (hi - v) / span * ih; }

    // 网格
    c.strokeStyle = "#f0f2f5"; c.lineWidth = 1;
    for (var g = 0; g <= 3; g++) {
      var gy = padT + ih / 3 * g;
      c.beginPath(); c.moveTo(padL, gy); c.lineTo(W - padR, gy); c.stroke();
    }
    // 刻度
    c.fillStyle = "#a8aeb8"; c.font = "10px -apple-system,sans-serif"; c.textAlign = "right";
    for (var g2 = 0; g2 <= 3; g2++) {
      var v = hi - span / 3 * g2;
      c.fillText(v.toFixed(v > 1000 ? 0 : 1), padL - 5, padT + ih / 3 * g2 + 3);
    }

    var n = rows.length;
    var step = iw / n;
    var bw = Math.max(1.2, step * 0.62);

    rows.forEach(function (r, i) {
      var o = r[1], cl = r[2], h2 = r[3], l2 = r[4];
      var up = cl >= o;
      c.strokeStyle = up ? "#e03131" : "#0ca678";
      c.fillStyle = up ? "#e03131" : "#0ca678";
      var x = padL + step * i + step / 2;
      // 影线
      c.beginPath();
      c.moveTo(x, y(h2)); c.lineTo(x, y(l2));
      c.lineWidth = 1; c.stroke();
      // 实体
      var yo = y(o), yc = y(cl);
      var top = Math.min(yo, yc), hgt = Math.max(1, Math.abs(yc - yo));
      c.fillRect(x - bw / 2, top, bw, hgt);
    });

    // 最后一天日期
    c.fillStyle = "#b3b9c2"; c.textAlign = "left";
    c.fillText(rows[0][0].slice(5), padL, H - 5);
    c.textAlign = "right";
    c.fillText(rows[n - 1][0].slice(5), W - padR, H - 5);
  }

  /* ------------------------------------------------ 政策 */
  /* ------------------------------------------------ 政策 */
  /* 搜政策时的大白话映射：用户说「环保」，文件里写的是「生态环境部」 */
  var POL_SYN = {
    "环保": ["环境", "生态", "排污", "污染"],
    "安全": ["安全生产", "应急", "危化"],
    "补贴": ["奖补", "补助", "资金", "支持"],
    "园区": ["化工园区", "扩区", "调区"],
    "能耗": ["节能", "双碳", "碳", "能效"],
    "投资": ["项目", "备案", "核准", "审批"]
  };

  function viewPolicies() {
    setHeader("化工政策", {});
    if (!D.policies || !D.policies.items) { app.innerHTML = '<div class="empty">政策数据未加载</div>'; return; }
    var items = D.policies.items.slice();
    var levels = [];
    items.forEach(function (p) { if (levels.indexOf(p.level) < 0) levels.push(p.level); });
    if (!UI.level || levels.indexOf(UI.level) < 0) {
      var f = levels.filter(function (lv) { return items.some(function (p) { return p.level === lv; }); })[0];
      UI.level = f || "国家级";
    }

    var h = '<div class="card" style="padding:0"><div style="padding:9px 12px">' +
      '<input id="q" placeholder="搜政策：标题 / 机关 / 影响" value="' + esc(UI.q) + '" ' +
      'style="width:100%;height:36px;border:1px solid var(--line);border-radius:9px;padding:0 12px;font-size:14px;outline:0;background:#fafbfc"></div></div>';

    var q = (UI.q || "").toLowerCase();
    /* 大白话也得搜得到：文件里写「生态环境部」，人嘴上说的是「环保」 */
    var WORDS = [[q]];
    Object.keys(POL_SYN).forEach(function (k) {
      if (q.indexOf(k) >= 0) WORDS.push(POL_SYN[k]);
    });
    var list, head;

    if (q) {
      /* 搜索跨两级：找政策时不该被「国家级/山东省」挡住 */
      list = items.filter(function (p) {
        var hay = [p.title, p.org, p.impact, p.level].join(" ").toLowerCase();
        return WORDS.some(function (ws) {
          return ws.some(function (w) { return w && hay.indexOf(w) >= 0; });
        });
      });
      head = '<div class="sec-title">搜索结果 <span class="subtle">· ' + list.length +
        ' 条（含国家级与山东省）</span></div>';
    } else {
      h += '<div class="chips">';
      ["国家级", "山东省"].forEach(function (lv) {
        var cnt = items.filter(function (p) { return p.level === lv; }).length;
        h += '<button class="chip' + (UI.level === lv ? " on" : "") + '" data-lv="' + lv + '">' + lv + ' ' + cnt + '</button>';
      });
      h += '</div>';
      list = items.filter(function (p) { return p.level === UI.level; });
      head = "";
    }

    h += head;
    if (!list.length) {
      h += '<div class="empty">没有匹配的政策<br><span style="font-size:12px">' +
        (q ? '换个词试试，比如「环保」「园区」「奖补」' : '这一级暂无收录，政策源还在补充中') +
        '</span></div>';
    } else {
      h += '<div class="card">';
      list.forEach(function (p) {
        var read = has(S.read, "pol:" + (p.id || phash(p)));
        h += '<a class="row" href="#/policy/' + esc(p.id || phash(p)) + '">' +
          '<div class="main"><div class="rt">' + esc(p.title) + '</div>' +
          '<div class="rm"><span class="tag">' + esc(p.level) + '</span>' +
          '<span>' + esc(p.org) + '</span>' +
          '<span>' + esc(dateStr(p.ts)) + '</span>' +
          (read ? '<span class="tag cat">已读</span>' : '') + '</div></div>' +
          '<span class="arrow">›</span></a>';
      });
      h += '</div>';
    }
    h += '<div class="hint">第一版政策源：山东省工信厅 + 国家发改委 + 生态环境部。国家级政策源仍在补充。</div>';
    app.innerHTML = h;

    var qi = $("q");
    if (qi) qi.oninput = function () {
      UI.q = qi.value; var pos = qi.selectionStart; viewPolicies();
      var n = $("q"); if (n) { n.focus(); try { n.setSelectionRange(pos, pos); } catch (e) {} }
    };
    Array.prototype.forEach.call(app.querySelectorAll(".chip"), function (c) {
      c.onclick = function () { UI.level = c.dataset.lv; viewPolicies(); };
    });
  }

  function viewPolicy(id) {
    var p = null;
    (D.policies && D.policies.items || []).forEach(function (x) {
      if (String(x.id || phash(x)) === String(id)) p = x;
    });
    if (!p) { app.innerHTML = '<div class="empty">未找到该政策</div>'; return; }
    var key = "pol:" + id;
    if (!has(S.read, key)) { S.read.push(key); storeSave(); }
    setHeader("政策详情", { back: true, favKey: key });

    var h = '<div class="dt" style="font-size:18px;line-height:1.45">' + esc(p.title) + '</div>' +
      '<div class="dsub">' + esc(p.level) + ' · ' + esc(p.org) + '</div>';
    h += '<div class="card">' +
      '<div class="kv"><span class="k">发布层级</span><span class="v">' + esc(p.level) + '</span></div>' +
      '<div class="kv"><span class="k">发文机关</span><span class="v">' + esc(p.org) + '</span></div>' +
      '<div class="kv"><span class="k">发布日期</span><span class="v">' + esc(dateStr(p.ts) || "—") + '</span></div>' +
      '</div>';
    if (p.impact) {
      h += '<div class="sec-title">对撮合的影响</div><div class="card">' +
        '<div class="field"><div class="fv">' + esc(p.impact) + '</div></div>' +
        '<div class="hint" style="padding:0">' +
        (p.impact_src === "rule" ? '按标题关键词自动归类，仅供参考。' : '') +
        '具体条款以原文为准。</div></div>';
    }
    h += '<div class="card"><a class="row" href="' + esc(p.url) + '" target="_blank" rel="noopener">' +
      '<div class="main"><div class="rt">查看政策原文</div>' +
      '<div class="rm">跳转到发布机关官网</div></div><span class="arrow">›</span></a></div>';
    h += '<div class="hint">第一版只做收录与原文跳转，不做全文摘要（避免误读政策）。</div>';
    app.innerHTML = h;
  }

  /* ------------------------------------------------ 我的（本地数据 / 备份） */
  var EXPORT_V = 1;

  function viewMe() {
    setHeader("我的数据", { back: true });
    var arr = snapsGet();
    var h = '';

    h += '<div class="sec-title">本机记录</div><div class="card">' +
      '<div class="kv"><span class="k">已学品类</span><span class="v">' + S.learned.length +
      (D.cats ? ' / ' + D.cats.items.length : '') + '</span></div>' +
      '<div class="kv"><span class="k">已读政策</span><span class="v">' +
      S.read.filter(function (k) { return String(k).indexOf("pol:") === 0; }).length +
      (D.policies ? ' / ' + D.policies.items.length : '') + '</span></div>' +
      '<div class="kv"><span class="k">收藏</span><span class="v">' + S.fav.length + '</span></div>' +
      '</div>';

    h += '<div class="card"><div class="btnrow">' +
      '<button class="btn pri" id="exp">导出我的数据</button>' +
      '<button class="btn" id="imp">导入恢复</button>' +
      '</div>' +
      '<input id="impFile" type="file" accept=".json,application/json" hidden>' +
      '<div id="impinfo"></div>' +
      '<div class="hint">导出得到一个纯文本 json（含 learned / read / fav 三个字段），' +
      '换手机或清缓存后导入即可恢复。导入是<b>合并</b>，不会用旧备份冲掉新记录。</div></div>';

    h += '<div class="sec-title">本机快照 <span class="subtle">每周自动存一份，留最近 ' +
      SNAP_KEEP + ' 份</span></div>';
    if (!arr.length) {
      h += '<div class="card"><div class="empty" style="padding:24px 20px">还没有快照<br>' +
        '<span style="font-size:12px">第一次打开 App 时开始计时，满一周自动存一份</span></div></div>';
    } else {
      h += '<div class="card">';
      arr.slice().reverse().forEach(function (s, k) {
        var idx = arr.length - 1 - k;
        h += '<div class="row"><div class="main">' +
          '<div class="rt">' + esc(dateTime(s.ts)) + '</div>' +
          '<div class="rm"><span>品类 ' + ((s.data && s.data.learned) || []).length + '</span>' +
          '<span>已读 ' + ((s.data && s.data.read) || []).length + '</span>' +
          '<span>收藏 ' + ((s.data && s.data.fav) || []).length + '</span></div></div>' +
          '<button class="btn sm" data-snap="' + idx + '">恢复</button></div>';
      });
      h += '</div>';
    }

    h += '<div class="card"><div class="btnrow"><button class="btn" id="snapnow">立即存一份快照</button></div>' +
      '<div class="hint">每周自动存，也可以手动存一份再做大改动。</div></div>';

    h += '<div class="card"><div class="btnrow"><button class="btn" id="clear">清空本机记录</button></div>' +
      '<div class="hint">只看资讯和行情的话，这些记录不影响任何内容。清空后学习进度归零。</div></div>';

    h += '<div class="hint">离线缓存不是备份：App 断网时还能看到上次的内容，那是缓存，' +
      '系统清理缓存或重装就没了。<b>真正属于你的只有已学 / 已读 / 收藏三项</b>，请定期导出。</div>' +
      '<div class="hint">内容数据（资讯、行情、园区、品类、政策）不用备份，下次更新自动覆盖；' +
      '数据整理日期：' + esc((D.meta && D.meta.updated_at_text) || "") + '</div>';

    app.innerHTML = h;

    $("exp").onclick = function () {
      var payload = {
        v: EXPORT_V, app: "chem-app", exported_at: new Date().toISOString(),
        learned: S.learned, read: S.read, fav: S.fav, seen: S.seen
      };
      var text = JSON.stringify(payload, null, 2);
      window.__lastExport = text;   // 便于自测核对文件内容，不影响用户
      var blob = new Blob([text], { type: "application/json" });
      var a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = "高端化工-我的数据-" + dateStr(Date.now() / 1000) + ".json";
      a.click();
      setTimeout(function () { URL.revokeObjectURL(a.href); }, 3000);
      var box = $("impinfo");
      if (box) box.innerHTML = '<div class="hint ok">已导出：品类 ' + S.learned.length +
        ' · 已读 ' + S.read.length + ' · 收藏 ' + S.fav.length + '（文件名带日期）</div>';
    };

    $("imp").onclick = function () { $("impFile").click(); };

    $("impFile").onchange = function () {
      var f = this.files && this.files[0];
      if (!f) return;
      var fr = new FileReader();
      fr.onload = function () {
        var o;
        try {
          o = JSON.parse(fr.result);
          if (!o || typeof o !== "object") throw new Error("不是合法的 json 对象");
        } catch (e) {
          $("impinfo").innerHTML = '<div class="hint err">导入失败：文件不是可读的 json（' +
            esc(e.message) + '）</div>';
          return;
        }
        if (String(o.v) !== String(EXPORT_V)) {
          var msg = "版本不一致（文件 v=" + (o.v === undefined ? "无" : o.v) + "，本机 v=" +
            EXPORT_V + "），仍要导入吗？";
          if (!confirm(msg)) {
            $("impinfo").innerHTML = '<div class="hint">已取消导入（版本不一致，你没有确认）。</div>';
            return;
          }
        }
        var r = applyRestore(o);
        viewMe();
        $("impinfo").innerHTML = '<div class="hint ok">恢复完成：' + esc(restoreText(r)) + '</div>';
      };
      fr.readAsText(f);
    };

    $("snapnow").onclick = function () { snapMaybe(true); viewMe(); };

    Array.prototype.forEach.call(app.querySelectorAll("[data-snap]"), function (b) {
      b.onclick = function () {
        var i = parseInt(b.dataset.snap, 10);
        var s = snapsGet()[i];
        if (!s) return;
        if (!confirm("用 " + dateTime(s.ts) + " 的快照恢复？会合并进当前记录，不会删掉现有内容。")) return;
        var r = snapRestore(i);
        viewMe();
        $("impinfo").innerHTML = '<div class="hint ok">已从快照恢复：' + esc(restoreText(r)) + '</div>';
      };
    });

    $("clear").onclick = function () {
      if (!confirm("确定清空本机的已学、已读、收藏？此操作不可恢复。")) return;
      S.learned = []; S.read = []; S.fav = []; S.seen = {};
      storeSave(); viewMe();
    };
  }

  function dateTime(ts) {
    var d = new Date(ts);
    return d.getFullYear() + "-" + ("0" + (d.getMonth() + 1)).slice(-2) + "-" +
      ("0" + d.getDate()).slice(-2) + " " + ("0" + d.getHours()).slice(-2) + ":" +
      ("0" + d.getMinutes()).slice(-2);
  }

  /* ------------------------------------------------ 路由 */
  function route() {
    if (!D.cats && !D.news && !D.prices) {
      app.innerHTML = '<div class="empty">未能加载数据<br>' +
        '<span style="font-size:12px">请检查网络，或点右上角 ⟳ 重新加载；' +
        '已经缓存过的内容在断网时也能打开</span></div>';
      netUI();
      return;
    }
    var p = location.hash.replace(/^#\/?/, "").split("/").filter(Boolean);
    var seg = p[0] || "home";
    if (seg === "home") viewHome();
    else if (seg === "news") viewNews();
    else if (seg === "parks") { if (p[1]) UI.mq = decodeURIComponent(p[1]); viewParks(); }
    else if (seg === "city") viewCity(p[1]);
    else if (seg === "park") viewPark(p[1]);
    else if (seg === "ent") viewEnt(p[1], parseInt(p[2], 10));
    else if (seg === "cats") viewCats();
    else if (seg === "cat") viewCat(p[1]);
    else if (seg === "prices") viewPrices();
    else if (seg === "price") viewPrice(decodeURIComponent(p[1] || ""));
    else if (seg === "policies") viewPolicies();
    else if (seg === "policy") viewPolicy(p[1]);
    else if (seg === "me") viewMe();
    else viewHome();
    window.scrollTo(0, 0);
  }

  /* ------------------------------------------------ 事件 */
  nav.addEventListener("click", function (e) {
    var b = e.target.closest(".tab");
    if (!b) return;
    UI.q = ""; UI.city = "";
    location.hash = "#/" + b.dataset.r;
  });

  backBtn.onclick = function () {
    if (history.length > 1) history.back();
    else location.hash = "#/home";
  };

  refreshBtn.onclick = function () {
    meta.textContent = "正在更新…";
    loadAll().then(route);
  };

  favBtn.onclick = function () {
    if (!CUR.key) return;
    toggle(S.fav, CUR.key);
    var on = has(S.fav, CUR.key);
    favBtn.textContent = on ? "★" : "☆";
    favBtn.className = "hbtn" + (on ? " on" : "");
  };

  window.addEventListener("hashchange", route);

  // 双击标题进入「我的数据」
  var tapCount = 0, tapTimer = null;
  ttl.addEventListener("click", function () {
    tapCount++;
    clearTimeout(tapTimer);
    tapTimer = setTimeout(function () { tapCount = 0; }, 600);
    if (tapCount >= 2) { tapCount = 0; location.hash = "#/me"; }
  });

  if ("serviceWorker" in navigator) {
    window.addEventListener("load", function () {
      navigator.serviceWorker.register("./sw.js").catch(function () {});
    });
  }

  storeLoad();
  loadAll().then(function () {
    route();
  }).catch(function () {
    app.innerHTML = '<div class="empty">数据加载失败<br>请检查网络后点右上角 ⟳</div>';
  });
})();
