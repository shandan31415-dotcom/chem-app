/**
 * 纯逻辑层：从 chem-app/app.js 原样移植，不依赖任何 DOM / wx API。
 * 这样 web 与小程序的统计口径天然一致，改一处两边都对得上。
 */
const D = require('../data/index.js');

const DISCLAIMER =
  '本应用为化工行业信息导航工具，内容仅供参考，不构成任何交易或经营决策依据。' +
  '所收录内容均整理自政府公示、企业公开资料等公开渠道，可能存在滞后或疏漏，请以官方发布为准。' +
  '如信息有误或需更正、删除，可在「我的 → 信息更正」提交申请，核实后处理。';

/* ------------------------------------------------ 园区 / 地市 */

function cityList() {
  return (D.parks && D.parks.cities) || [];
}

function cityByCode(code) {
  let hit = null;
  cityList().forEach((c) => {
    if (String(c.code) === String(code)) hit = c;
  });
  return hit;
}

function allParks() {
  const out = [];
  cityList().forEach((c) => {
    (c.parks || []).forEach((p) => {
      const o = Object.assign({}, p);
      o.cityName = c.name;
      o.cityCode = c.code;
      out.push(o);
    });
  });
  return out;
}

function parkById(id) {
  let hit = null;
  allParks().forEach((p) => {
    if (String(p.id) === String(id)) hit = p;
  });
  return hit;
}

/** 每个地市的园区 / 企业 / 高端企业数，与 web 口径完全一致 */
function cityStats() {
  const out = {};
  cityList().forEach((c) => {
    const pk = c.parks || [];
    let ent = 0;
    let high = 0;
    let highParks = 0;
    pk.forEach((p) => {
      const es = p.enterprises || [];
      ent += es.length;
      es.forEach((e) => {
        if (e.high) high += 1;
      });
      if (p.level === '高端为主') highParks += 1;
    });
    (c.enterprises || []).forEach((e) => {
      ent += 1;
      if (e.high) high += 1;
    });
    out[c.code] = { parks: pk.length, ents: ent, high: high, hp: highParks, heOnly: highParks };
  });
  return out;
}

function heatLevel(high) {
  return high >= 4 ? 3 : high >= 2 ? 2 : high >= 1 ? 1 : 0;
}

function totals() {
  const st = cityStats();
  const t = { parks: 0, ents: 0, high: 0 };
  Object.keys(st).forEach((k) => {
    t.parks += st[k].parks;
    t.ents += st[k].ents;
    t.high += st[k].high;
  });
  return t;
}

/* ------------------------------------------------ 品类 / 产业链 / 板块 */

function catById(id) {
  let hit = null;
  (D.cats.items || []).forEach((c) => {
    if (String(c.id) === String(id)) hit = c;
  });
  return hit;
}

function chainStages() {
  return (D.chain && D.chain.stages) || [];
}

function chainStageOf(id) {
  let hit = null;
  chainStages().forEach((s) => {
    if ((s.cats || []).indexOf(id) >= 0) hit = s;
  });
  return hit;
}

function boardByKey(key) {
  let hit = null;
  ((D.boards && D.boards.boards) || []).forEach((b) => {
    if (String(b.key) === String(key)) hit = b;
  });
  return hit;
}

/* ------------------------------------------------ 参考价 */

function allPrices() {
  const out = [];
  ((D.prices && D.prices.groups) || []).forEach((g) => {
    (g.items || []).forEach((i) => {
      const o = Object.assign({}, i);
      o.group = g.name;
      out.push(o);
    });
  });
  return out;
}

function priceByName(name) {
  let hit = null;
  allPrices().forEach((p) => {
    if (p.name === name) hit = p;
  });
  return hit;
}

/* ------------------------------------------------ 格式化 */

function pct(v) {
  if (v === null || v === undefined || isNaN(v)) return { t: '—', c: 'flat' };
  return {
    t: (v > 0 ? '+' : '') + Number(v).toFixed(2) + '%',
    c: v > 0 ? 'up' : v < 0 ? 'down' : 'flat',
  };
}

function px(v) {
  if (v === null || v === undefined) return '—';
  const d = v >= 1000 ? 0 : v >= 100 ? 1 : 2;
  return Number(v).toFixed(d);
}

function dateStr(ts) {
  if (!ts) return '';
  const d = new Date(ts * 1000);
  const p = (n) => ('0' + n).slice(-2);
  return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate());
}

/** 人工整理的长文里夹了 <b> 之类的标记，小程序端统一清成纯文本 */
function stripTags(s) {
  return String(s == null ? '' : s).replace(/<[^>]+>/g, '');
}

/* ------------------------------------------------ 全站检索索引 */

let IDX = null;

function entEntry(e, url, sub, catNames, catProd) {
  const hay = [e.name, e.products, e.note, sub, catNames, catProd].join(' ').toLowerCase();
  return {
    t: '企业',
    n: e.name,
    s: sub + ' · ' + (e.products || ''),
    url: url,
    hay: hay,
    hi: !!e.high,
  };
}

function buildIndex() {
  if (IDX) return IDX;
  IDX = [];
  cityList().forEach((c) => {
    const cityHay = [
      c.name,
      c.tagline,
      c.intro,
      c.scale,
      (c.chems || []).join(' '),
      (c.clusters || []).map((x) => x.n + x.d).join(' '),
    ]
      .join(' ')
      .toLowerCase();

    IDX.push({
      t: '地市',
      n: c.name,
      s: c.tagline || '',
      url: '/pages/city/city?code=' + c.code,
      hay: cityHay,
      hi: false,
    });

    (c.parks || []).forEach((p) => {
      const ph = [p.name, p.district, p.type, p.intro].join(' ').toLowerCase();
      IDX.push({
        t: '园区',
        n: p.name,
        s: c.name + ' · ' + (p.district || '') + ' · ' + (p.type || ''),
        url: '/pages/park/park?id=' + p.id,
        hay: ph + ' ' + cityHay,
        hi: p.level === '高端为主',
      });
      (p.enterprises || []).forEach((e, i) => {
        const ccs = (e.cats || []).map(catById).filter(Boolean);
        IDX.push(
          entEntry(
            e,
            '/pages/ent/ent?pid=' + p.id + '&i=' + i,
            c.name + ' · ' + p.name,
            ccs.map((x) => x.name).join(' '),
            ccs.map((x) => (x.products || []).join(' ')).join(' ')
          )
        );
      });
    });

    (c.enterprises || []).forEach((e, i) => {
      const ccs = (e.cats || []).map(catById).filter(Boolean);
      IDX.push(
        entEntry(
          e,
          '/pages/ent/ent?cid=' + c.code + '&i=' + i,
          c.name + ' · 市级重点企业',
          ccs.map((x) => x.name).join(' '),
          ccs.map((x) => (x.products || []).join(' ')).join(' ')
        )
      );
    });
  });
  return IDX;
}

function searchHits(q) {
  const key = String(q || '').trim().toLowerCase();
  if (!key) return [];
  const idx = buildIndex();
  const terms = key.split(/\s+/).filter(Boolean);
  const out = [];
  idx.forEach((x) => {
    let ok = true;
    for (let i = 0; i < terms.length; i++) {
      if (x.hay.indexOf(terms[i]) < 0) {
        ok = false;
        break;
      }
    }
    if (ok) out.push(x);
  });
  // 名称命中优先
  out.sort((a, b) => {
    const an = a.n.toLowerCase().indexOf(terms[0]) >= 0 ? 0 : 1;
    const bn = b.n.toLowerCase().indexOf(terms[0]) >= 0 ? 0 : 1;
    return an - bn || (b.hi ? 1 : 0) - (a.hi ? 1 : 0);
  });
  return out;
}

/** 品类搜索：名称 / 一句话 / 山东 / 产品 / 头部企业 */
function catSearch(q) {
  const key = String(q || '').trim().toLowerCase();
  if (!key) return D.cats.items;
  return D.cats.items.filter((c) => {
    const hay = [
      c.name,
      c.one_line,
      c.shandong,
      (c.products || []).join(' '),
      (c.leaders || []).map((x) => x.name).join(' '),
    ]
      .join(' ')
      .toLowerCase();
    return hay.indexOf(key) >= 0;
  });
}

module.exports = {
  D,
  DISCLAIMER,
  cityList,
  cityByCode,
  allParks,
  parkById,
  cityStats,
  heatLevel,
  totals,
  catById,
  chainStages,
  chainStageOf,
  boardByKey,
  allPrices,
  priceByName,
  pct,
  px,
  dateStr,
  stripTags,
  buildIndex,
  searchHits,
  catSearch,
};
