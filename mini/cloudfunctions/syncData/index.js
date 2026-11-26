/**
 * 云函数 syncData —— 政策与行情都由它自己在国内机房抓，抓完写云数据库。
 *
 * 架构在 2026-11-26 改过一轮。原来是把 GitHub Actions 采集好的快照搬进来，
 * 问题是那条链三处都在境外：采集在美国机器上跑（连不上东财、连国内政府站也慢），
 * 数据存在 GitHub Pages 上，云函数再去取。任何一处抽风，小程序就停更。
 *
 * 现在：
 *   政策 → crawlPolicies() 直接抓 11 个政府栏目，解析、判定、与库里的历史合并
 *   行情 → fetchSinaPrices() 直接抓新浪期货主力连续
 *   两者互不依赖，并行执行，典型 1~2 秒跑完
 *
 * GitHub 只剩一个用途：云库为空时（首次部署或集合被误删），从备份快照里借一次底子。
 * 日常运行完全不经过它——断网也不影响小程序。
 *
 * 部署：微信开发者工具 → 右键 cloudfunctions/syncData → 「上传并部署：云端安装依赖」
 * 触发器：见同目录 config.json（每天 10:10 / 16:10 / 23:50），改完要在开发者工具里
 *        右键云函数「上传触发器」，只传代码不会更新定时。
 *
 * 全部失败时**不动云库**，保留上一次成功的数据，小程序照样能读。
 */
const cloud = require('wx-server-sdk');
const https = require('https');
const zlib = require('zlib');
const { crawlPolicies } = require('./policies');

cloud.init({ env: cloud.DYNAMIC_CURRENT_ENV });
const db = cloud.database();

const REPO = 'shandan31415-dotcom/chem-app';
const BRANCH = 'main';
const FILE = 'chem-app/data/cloud_snapshot.json';

const COLLECTION = 'snapshot';
const DOC_ID = 'latest';
const LOG_COLLECTION = 'sync_log';
const CATALOG_COLLECTION = 'catalog';

/**
 * 取数通道。**全部并发发起，谁先成功用谁**——串行试是上一版超时的根因：
 * 四个源各自 8~12 秒超时，串起来 42 秒，超过了云函数的时间上限。
 *
 * 腾讯云函数在国内访问 GitHub 域名不稳定，所以额外挂两个公共加速代理兜底。
 * 代理只做透明转发，返回内容仍要过 check() 结构校验，且首选的仍是自家 Pages。
 */
const RAW = 'https://raw.githubusercontent.com/' + REPO + '/' + BRANCH + '/' + FILE;

/**
 * 源分两档，这是踩过坑之后的结论。
 *
 * jsDelivr 对 GitHub 文件做长期边缘缓存（默认 12 小时，热门资源更久），
 * 它回得最快，但内容可能是半天前的。之前的「谁先回用谁」让缓存源屡屡抢跑，
 * 出现过云库里写着 50 条政策、GitHub 上其实已经是 67 条的静默错版。
 * 所以：先只问「不带长期缓存」的一档，这一档任意一个成功就是最新提交；
 * 全挂了才退到 CDN 档，并把它标成 stale。
 */
const SOURCES_FRESH = [
  // 代理只做透明转发，不缓存内容
  { name: 'gh-proxy', url: 'https://gh-proxy.com/' + RAW, timeout: 5000 },
  { name: 'ghfast', url: 'https://ghfast.top/' + RAW, timeout: 5000 },
  { name: 'github-raw', url: RAW, timeout: 5000 },
];

/** 带长期缓存的源，仅兜底 */
const SOURCES_CDN = [
  {
    name: 'jsdelivr-gcore',
    url: 'https://gcore.jsdelivr.net/gh/' + REPO + '@' + BRANCH + '/' + FILE,
    timeout: 5000,
  },
  {
    name: 'jsdelivr',
    url: 'https://cdn.jsdelivr.net/gh/' + REPO + '@' + BRANCH + '/' + FILE,
    timeout: 5000,
  },
];

/* ---------------------------------------------------------------- 取数 */

function getText(url, timeout, extraHeaders) {
  return new Promise((resolve, reject) => {
    const req = https.get(
      url,
      {
        headers: Object.assign(
          {
            'User-Agent': 'chem-mini-sync/1.0 (+wechat-miniprogram)',
            'Accept-Encoding': 'gzip, deflate, br',
            'Cache-Control': 'no-cache',
            Pragma: 'no-cache',
          },
          extraHeaders || {}
        ),
      },
      (res) => {
        if (res.statusCode !== 200) {
          res.resume();
          reject(new Error('HTTP ' + res.statusCode));
          return;
        }
        const enc = String(res.headers['content-encoding'] || '').toLowerCase();
        let stream = res;
        if (enc === 'gzip') stream = res.pipe(zlib.createGunzip());
        else if (enc === 'deflate') stream = res.pipe(zlib.createInflate());
        else if (enc === 'br') stream = res.pipe(zlib.createBrotliDecompress());

        const chunks = [];
        stream.on('data', (c) => chunks.push(c));
        stream.on('end', () => resolve(Buffer.concat(chunks).toString('utf8')));
        stream.on('error', reject);
      }
    );
    req.setTimeout(timeout, () => req.destroy(new Error('timeout ' + timeout + 'ms')));
    req.on('error', reject);
  });
}

/* ---------------------------------------------------------------- 校验 */

/**
 * 结构不对宁可不写。云库里放着一份坏数据，小程序会一直读到它，
 * 比「同步失败保留旧数据」糟得多。
 */
function check(snap) {
  if (!snap || typeof snap !== 'object') throw new Error('快照不是对象');
  const pol = snap.policies;
  if (!pol || !Array.isArray(pol.items) || pol.items.length < 5) {
    throw new Error('政策条数异常');
  }
  for (const p of pol.items) {
    if (!p || !p.title || !p.url) throw new Error('政策条缺少 title/url');
    if (!/^https?:\/\//i.test(p.url)) throw new Error('政策链接不是 http(s)');
  }
  const meta = snap.meta || {};
  if (!meta.updated_at_text) throw new Error('缺 meta.updated_at_text');
  return true;
}

async function ensureCollection(name) {
  try {
    await db.createCollection(name);
    return true;
  } catch (e) {
    // -501001 / 已存在，忽略
    return false;
  }
}

/* ------------------------------------------------------- 行情直连兜底 */

/**
 * 为什么云函数要自己抓行情：GitHub Actions 的出口 IP 在美国，东方财富的
 * push2 接口对境外 IP 直接断连，导致价格能连着几天不动，而页面看着一切正常。
 * 云函数跑在腾讯云国内机房，访问新浪没有任何问题——所以行情在这里自己取，
 * 不再把「价格是否新鲜」赌在 GitHub 上。
 *
 * 只抓「快照里已经存在的品种」，品种清单跟着快照走，不在这里维护第二份。
 * 映射表里没有的名字原样保留旧价格，不会凭空丢条。
 */
const SINA_CODE = {
  '原油': 'nf_SC0', '燃料油': 'nf_FU0', '低硫燃料油': 'nf_LU0', '液化石油气': 'nf_PG0',
  '沥青': 'nf_BU0', '聚乙烯': 'nf_L0', '聚丙烯': 'nf_PP0', 'PVC': 'nf_V0',
  '苯乙烯': 'nf_EB0', '烧碱': 'nf_SH0', '对二甲苯': 'nf_PX0', 'PTA': 'nf_TA0',
  '乙二醇': 'nf_EG0', '短纤': 'nf_PF0', '瓶片': 'nf_PR0', '甲醇': 'nf_MA0',
  '尿素': 'nf_UR0', '纯碱': 'nf_SA0', '玻璃': 'nf_FG0', '焦炭': 'nf_J0',
  '焦煤': 'nf_JM0', '天然橡胶': 'nf_RU0', '20号胶': 'nf_NR0', '纸浆': 'nf_SP0',
};

/** 快照行情超过这么久没动，就认为 GitHub 那条链断了，自己下场抓。可用环境变量调，便于本地复现 */
const ENV_STALE = process.env.PRICE_STALE_SEC;
const PRICE_STALE_SEC = ENV_STALE !== undefined && ENV_STALE !== '' ? Number(ENV_STALE) : 6 * 3600;

function beijingStamp(d) {
  // 云函数默认 UTC，页面上展示的是北京时间，这里统一 +8 小时自己算
  const t = new Date(d.getTime() + 8 * 3600 * 1000);
  const p = (n) => String(n).padStart(2, '0');
  return (
    t.getUTCFullYear() + '-' + p(t.getUTCMonth() + 1) + '-' + p(t.getUTCDate()) +
    ' ' + p(t.getUTCHours()) + ':' + p(t.getUTCMinutes())
  );
}

/**
 * 新浪期货主力连续：字段 0 名称 / 1 时间 / 2 开 / 3 高 / 4 低 / 6 买 / 7 卖 /
 * 8 最新 / 9 结算 / 10 昨结算 / 17 日期。涨跌幅按「最新 vs 昨结算」算，
 * 与国内期货软件口径一致。
 *
 * 接口返回 GBK，这里不做转码：只需要数字和合约代码，而 GBK 的双字节
 * 次字节最小是 0x40，不会与逗号（0x2C）、引号（0x22）混淆，按 utf8 读也安全。
 */
async function fetchSinaPrices() {
  const codes = Object.values(SINA_CODE);
  const txt = await getText('https://hq.sinajs.cn/list=' + codes.join(','), 5000, {
    Referer: 'https://finance.sina.com.cn',
  });
  const quotes = {};
  let stamp = '';
  for (const m of txt.matchAll(/hq_str_(\w+)="([^"]*)"/g)) {
    const f = m[2].split(',');
    if (f.length < 18) continue;
    const price = parseFloat(f[8]);
    const pre = parseFloat(f[10]);
    if (!isFinite(price) || price <= 0) continue;
    quotes[m[1]] = {
      price,
      chg: pre > 0 ? Math.round(((price - pre) / pre) * 10000) / 100 : null,
      amt: pre > 0 ? Math.round((price - pre) * 100) / 100 : null,
    };
    if (!stamp && /^\d{4}-\d{2}-\d{2}$/.test(f[17])) {
      const hhmm = String(f[1]).replace(/^(\d{2})(\d{2}).*$/, '$1:$2');
      stamp = f[17] + (hhmm.length === 5 ? ' ' + hhmm : '');
    }
  }
  return { quotes, stamp };
}

/** 把抓到的行情写回快照，返回命中的品种数 */
function applyPrices(snap, quotes, stamp) {
  const groups = (snap.prices && snap.prices.groups) || [];
  let hit = 0;
  let total = 0;
  groups.forEach((g) => {
    (g.items || []).forEach((it) => {
      total += 1;
      const v = quotes[SINA_CODE[it.name]];
      if (!v) return;
      it.price = v.price;
      it.chg = v.chg;
      it.chg_amt = v.amt;
      it.src = '新浪财经';
      hit += 1;
    });
  });
  if (!hit) return 0;
  snap.prices.source = '新浪财经';
  snap.prices.updated_at = Math.floor(Date.now() / 1000);
  snap.prices.updated_at_text = stamp || beijingStamp(new Date());
  snap.prices.count = total;
  return hit;
}

/** 行情是否该刷新：时间戳缺失、或已超过 PRICE_STALE_SEC 都算 */
function pricesStale(snap) {
  const ts = Number((snap.prices && snap.prices.updated_at) || 0);
  if (!ts) return true;
  return Date.now() / 1000 - ts > PRICE_STALE_SEC;
}

/* ---------------------------------------------------------------- 入口 */

/** 并发竞速：第一个通过结构校验的快照胜出；全部失败时抛出错误清单 */
function raceOk(sources) {
  return new Promise((resolve, reject) => {
    const errors = [];
    let left = sources.length;
    if (!left) {
      reject(['没有可用数据源']);
      return;
    }
    sources.forEach((s) => {
      getText(s.url, s.timeout)
        .then((txt) => {
          const snap = JSON.parse(txt);
          check(snap);
          resolve({ snap: snap, source: s.name, url: s.url });
        })
        .catch((e) => {
          errors.push(s.name + ': ' + String((e && e.message) || e).slice(0, 120));
          left -= 1;
          if (left === 0) reject(errors);
        });
    });
  });
}

/** 读云库里现存的快照。GitHub 全挂时拿它当底子，至少把行情续上。 */
async function loadCloudSnap() {
  try {
    const r = await db.collection(COLLECTION).doc(DOC_ID).get();
    const snap = r && r.data && r.data.payload;
    return snap && snap.policies && snap.meta ? snap : null;
  } catch (e) {
    return null;
  }
}

/** 快照的时间戳，形如 2026-11-26 10:08，定长可直接比大小 */
function stampOf(snap) {
  return (snap && snap.meta && snap.meta.updated_at_text) || '';
}

/** 降级留痕：接口照样返回 ok，但政策或价格已经停更了，翻 sync_log 能看出来 */
async function logDegraded(payload) {
  try {
    await ensureCollection(LOG_COLLECTION);
    await db.collection(LOG_COLLECTION).add({
      data: Object.assign({ at: new Date(), ok: false, degraded: true }, payload),
    });
  } catch (e) {
    console.error('写降级日志失败', e);
  }
}

/** 冷启动：云库为空时，从 GitHub 的备份里借一份历史底子 */
async function bootstrapFromGithub() {
  const errs = [];
  for (const group of [SOURCES_FRESH, SOURCES_CDN]) {
    try {
      const hit = await raceOk(group);
      return { hit: hit, errs: errs };
    } catch (errors) {
      errs.push.apply(errs, Array.isArray(errors) ? errors : [String(errors)]);
    }
  }
  return { hit: null, errs: errs };
}

/**
 * 企业与园区名录（catalog）。
 *
 * 这份数据更新频率以「月」计，和每天变的政策不是一回事，所以单独一个集合。
 * 同步策略：只有 GitHub 上那份比云库新才覆盖。协会在云开发控制台的
 * 数据库里手改过之后，云库的 updated_at 会变成修改时间，一般情况下
 * 就不会再被旧备份盖回去——除非有人在仓库里改了名录并更新了 updated_at。
 *
 * 三条链路全挂就跳过，不影响政策与行情的同步。
 */
const CATALOG_URL = 'https://raw.githubusercontent.com/' + REPO + '/' + BRANCH +
  '/chem-app/data/catalog.json';

function pullCatalogOnce(timeout) {
  const urls = [
    'https://gh-proxy.com/' + CATALOG_URL,
    'https://ghfast.top/' + CATALOG_URL,
    CATALOG_URL,
  ];
  return new Promise((resolve) => {
    let done = false;
    const finish = (v) => {
      if (!done) {
        done = true;
        resolve(v);
      }
    };
    urls.forEach((u) => {
      getText(u, timeout)
        .then((t) => {
          const d = JSON.parse(t);
          if (d && Array.isArray(d.cities) && d.cities.length >= 5) finish(d);
        })
        .catch(() => {});
    });
    setTimeout(() => finish(null), timeout + 500);
  });
}

async function syncCatalog() {
  let cur = null;
  let curDoc = null;
  try {
    const r = await db.collection(CATALOG_COLLECTION).doc(DOC_ID).get();
    curDoc = (r && r.data) || null;
    cur = curDoc && curDoc.payload;
  } catch (e) {
    cur = null;
  }

  // 名录以月为单位变化，没必要每次触发都去 GitHub 问一遍。
  // 12 小时内查过就跳过——省下的是云函数每次 3 秒的等待。
  const checked = curDoc && curDoc.checked_at ? new Date(curDoc.checked_at).getTime() : 0;
  if (checked && Date.now() - checked < 12 * 3600 * 1000) {
    return { ok: true, note: '今日已检查' };
  }

  const remote = await pullCatalogOnce(3000);
  if (!remote) {
    // 记下检查时间，免得每次触发都白等 3 秒
    try {
      await db.collection(CATALOG_COLLECTION).doc(DOC_ID)
        .update({ data: { checked_at: new Date() } });
    } catch (e) { /* 集合都不存在就没什么可记的 */ }
    return { ok: false, note: '拉取失败，沿用云库' };
  }

  const remoteTs = Number(remote.updated_at || 0);
  const curTs = Number((cur && cur.updated_at) || 0);
  if (cur && remoteTs && remoteTs <= curTs) {
    try {
      await db.collection(CATALOG_COLLECTION).doc(DOC_ID)
        .update({ data: { checked_at: new Date() } });
    } catch (e) { /* 同上 */ }
    return { ok: true, note: '云库已是新版', cities: (cur.cities || []).length };
  }

  const doc = {
    payload: remote,
    synced_at: new Date(),
    checked_at: new Date(),
    city_count: remote.cities.length,
    park_count: (remote.counts && remote.counts.parks) || 0,
    company_count: (remote.counts && remote.counts.companies) || 0,
    data_date: remote.updated_at_text || '',
  };
  try {
    await db.collection(CATALOG_COLLECTION).doc(DOC_ID).set({ data: doc });
  } catch (e) {
    await ensureCollection(CATALOG_COLLECTION);
    await db.collection(CATALOG_COLLECTION).doc(DOC_ID).set({ data: doc });
  }
  return { ok: true, note: cur ? '已更新' : '首次写入', cities: remote.cities.length };
}

exports.main = async () => {
  const startedAt = Date.now();
  const notes = [];

  let cloud = await loadCloudSnap();

  // 日常运行完全不碰 GitHub：政策由下面的 crawlPolicies 在国内机房直接抓。
  // 这里只在云库为空时（首次部署、或集合被误删）去借一次历史数据。
  if (!cloud) {
    const boot = await bootstrapFromGithub();
    if (!boot.hit) {
      await logDegraded({ errors: boot.errs, reason: '冷启动失败：云库空且 GitHub 不可用',
        ms: Date.now() - startedAt });
      return { ok: false, errors: boot.errs, ms: Date.now() - startedAt };
    }
    cloud = boot.hit.snap;
    notes.push('冷启动取数：' + boot.hit.source);
  }

  const existing = (cloud.policies && cloud.policies.items) || [];

  // 政策与行情互不依赖，并行抓。串行白等一倍时间，而云函数总共只有 20 秒。
  const [pol, px] = await Promise.all([
    crawlPolicies(existing).then((v) => ({ ok: true, v: v })).catch((e) => ({ ok: false, e: e })),
    fetchSinaPrices().then((v) => ({ ok: true, v: v })).catch((e) => ({ ok: false, e: e })),
  ]);

  const now = new Date();
  const nowTs = Math.floor(now.getTime() / 1000);
  const snap = JSON.parse(JSON.stringify(cloud));

  /* ---------------------------------------------------------------- 政策 */
  let policyNote = '';
  let policyAdded = 0;
  let policySrcOk = 0;
  let policySrcAll = 0;
  if (pol.ok && pol.v.items.length >= 5) {
    snap.policies = {
      updated_at: nowTs,
      updated_at_text: beijingStamp(now),
      items: pol.v.items,
    };
    policyAdded = pol.v.added;
    policySrcAll = pol.v.sources.length;
    policySrcOk = pol.v.sources.filter((s) => s.ok).length;
    policyNote = policySrcOk === 0 ? '全部源失败，沿用云库' : 'crawl';
    const failed = pol.v.sources.filter((s) => !s.ok).map((s) => s.org);
    if (failed.length) notes.push('政策源失败：' + failed.join('、'));
  } else {
    policyNote = pol.ok
      ? '条数异常，沿用云库'
      : '抓取异常：' + String((pol.e && pol.e.message) || pol.e).slice(0, 80);
    notes.push('政策未更新：' + policyNote);
  }

  /* ---------------------------------------------------------------- 行情 */
  let priceHit = 0;
  let priceNote = '';
  if (px.ok) {
    priceHit = applyPrices(snap, px.v.quotes, px.v.stamp);
    priceNote = priceHit > 0 ? 'sina' : 'sina-empty';
  } else {
    priceNote = 'sina-fail: ' + String((px.e && px.e.message) || px.e).slice(0, 80);
    notes.push('行情未更新：' + priceNote);
  }

  /* ------------------------------------------------------- 数据日期 = 较晚者 */
  const cands = [
    [snap.policies.updated_at || 0, snap.policies.updated_at_text || ''],
    [(snap.prices && snap.prices.updated_at) || 0, (snap.prices && snap.prices.updated_at_text) || ''],
  ].sort((a, b) => b[0] - a[0]);
  snap.meta = {
    updated_at: cands[0][0] || nowTs,
    updated_at_text: cands[0][1] || beijingStamp(now),
  };

  // 结构不对宁可不写：库里放着一份坏数据，小程序会一直读到它
  try {
    check(snap);
  } catch (e) {
    await logDegraded({ errors: [String(e.message)], reason: '快照校验未通过', ms: Date.now() - startedAt });
    return { ok: false, errors: [String(e.message)], ms: Date.now() - startedAt };
  }

  const doc = {
    payload: snap,
    synced_at: now,
    mode: 'local-crawl',
    policy_count: snap.policies.items.length,
    policy_added: policyAdded,
    price_count: (snap.prices && snap.prices.count) || 0,
    price_source: (snap.prices && snap.prices.source) || '',
    price_date: (snap.prices && snap.prices.updated_at_text) || '',
    price_refreshed: priceHit,
    data_date: snap.meta.updated_at_text,
  };

  try {
    await db.collection(COLLECTION).doc(DOC_ID).set({ data: doc });
  } catch (e) {
    await ensureCollection(COLLECTION);
    await db.collection(COLLECTION).doc(DOC_ID).set({ data: doc });
  }

  // 名录单独同步，出问题不影响政策与行情
  let catalogNote = '';
  try {
    const c = await syncCatalog();
    catalogNote = c.note;
  } catch (e) {
    catalogNote = '异常：' + String((e && e.message) || e).slice(0, 60);
  }

  const summary = {
    ok: true,
    mode: 'local-crawl',
    policies: doc.policy_count,
    policy_added: policyAdded,
    policy_sources: policySrcOk + '/' + policySrcAll,
    data_date: doc.data_date,
    prices: doc.price_count,
    price_source: doc.price_source,
    price_note: priceNote,
    catalog: catalogNote,
    notes: notes,
    ms: Date.now() - startedAt,
  };
  console.log('sync ok', JSON.stringify(summary));

  if (policySrcOk === 0 || priceHit === 0) {
    await logDegraded({ errors: notes, ms: Date.now() - startedAt });
  }

  return summary;
};
