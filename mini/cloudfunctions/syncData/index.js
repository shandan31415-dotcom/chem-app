/**
 * 云函数 syncData —— 把最新数据快照灌进云数据库，并在快照行情过期时自己去抓。
 *
 * 为什么绕这一圈：小程序端不能随便请求外部域名（要在后台配合法域名），
 * GitHub 在国内也不稳定。云函数跑在腾讯云里，由它去取，小程序只读云数据库，
 * 一次配置，之后不用管。
 *
 * 部署：微信开发者工具 → 右键 cloudfunctions/syncData → 「上传并部署：云端安装依赖」
 * 触发器：见同目录 config.json（每天 10:10 / 16:10 / 23:50），改完要在开发者工具里
 *        右键云函数「上传触发器」，只传代码不会更新定时。
 *
 * 两条腿走路：
 *   1) 政策 + 静态数据 → 拉 GitHub 上的快照（raw / Pages / jsDelivr / 加速代理，并发竞速）
 *   2) 行情 → 发现快照里的价格超过 6 小时没动，就自己找新浪抓一次覆盖掉。
 *      东方财富对 GitHub Actions 的境外 IP 是直接断连的，行情曾经因此停更数天。
 *
 * 全部失败时**不动云库**，保留上一次成功的快照，小程序照样能读。
 */
const cloud = require('wx-server-sdk');
const https = require('https');
const zlib = require('zlib');

cloud.init({ env: cloud.DYNAMIC_CURRENT_ENV });
const db = cloud.database();

const REPO = 'shandan31415-dotcom/chem-app';
const BRANCH = 'main';
const FILE = 'chem-app/data/cloud_snapshot.json';

const COLLECTION = 'snapshot';
const DOC_ID = 'latest';
const LOG_COLLECTION = 'sync_log';

/**
 * 取数通道。**全部并发发起，谁先成功用谁**——串行试是上一版超时的根因：
 * 四个源各自 8~12 秒超时，串起来 42 秒，超过了云函数的时间上限。
 *
 * 腾讯云函数在国内访问 GitHub 域名不稳定，所以额外挂两个公共加速代理兜底。
 * 代理只做透明转发，返回内容仍要过 check() 结构校验，且首选的仍是自家 Pages。
 */
const RAW = 'https://raw.githubusercontent.com/' + REPO + '/' + BRANCH + '/' + FILE;

const SOURCES = [
  {
    // 自家 CDN，最可信；daily.yml 提交后会主动触发 Pages 重新部署
    name: 'github-pages',
    url: 'https://shandan31415-dotcom.github.io/chem-app/data/cloud_snapshot.json',
    timeout: 6000,
  },
  { name: 'github-raw', url: RAW, timeout: 6000 },
  { name: 'ghfast', url: 'https://ghfast.top/' + RAW, timeout: 6000 },
  { name: 'gh-proxy', url: 'https://gh-proxy.com/' + RAW, timeout: 6000 },
  {
    name: 'jsdelivr-gcore',
    url: 'https://gcore.jsdelivr.net/gh/' + REPO + '@' + BRANCH + '/' + FILE,
    timeout: 6000,
  },
  {
    name: 'jsdelivr',
    url: 'https://cdn.jsdelivr.net/gh/' + REPO + '@' + BRANCH + '/' + FILE,
    timeout: 6000,
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

exports.main = async () => {
  const startedAt = Date.now();
  let hit = null;
  let errs = [];
  try {
    hit = await raceOk(SOURCES);
  } catch (errors) {
    errs = Array.isArray(errors) ? errors : [String(errors)];
    console.warn('快照源全部失败，尝试用云库里的旧快照续行情', errs.join(' | '));
  }

  let snap;
  let srcName;
  let srcUrl = '';
  if (hit) {
    snap = hit.snap;
    srcName = hit.source;
    srcUrl = hit.url;
  } else {
    // GitHub 那条链断了≠整个应用停摆：云库里还有一份昨天的快照，
    // 政策旧几天没关系，价格继续由我们自己去抓，用户看到的仍是最新价。
    snap = await loadCloudSnap();
    srcName = 'cloud-cache';
    if (!snap) {
      try {
        await ensureCollection(LOG_COLLECTION);
        await db.collection(LOG_COLLECTION).add({
          data: { at: new Date(), ok: false, errors: errs, ms: Date.now() - startedAt },
        });
      } catch (e) {
        console.error('写日志失败', e);
      }
      return { ok: false, errors: errs, ms: Date.now() - startedAt };
    }
  }

  // 快照里的行情是 GitHub 那边采的。它一旦因为境外 IP 被拦就会停更，
  // 而快照本身照旧写得进来——所以这里要单独判一次「价格还新鲜吗」。
  let priceHit = 0;
  let priceNote = 'fresh';
  if (pricesStale(snap)) {
    try {
      const { quotes, stamp } = await fetchSinaPrices();
      priceHit = applyPrices(snap, quotes, stamp);
      priceNote = priceHit > 0 ? 'refreshed-sina' : 'sina-empty';
    } catch (e) {
      priceNote = 'sina-fail: ' + String((e && e.message) || e).slice(0, 80);
      console.warn('行情直连失败，沿用快照里的价格', priceNote);
    }
  }

  const doc = {
    payload: snap,
    synced_at: new Date(),
    source_url: srcUrl,
    source_name: srcName,
    policy_count: snap.policies.items.length,
    price_count: (snap.prices && snap.prices.count) || 0,
    price_source: (snap.prices && snap.prices.source) || '',
    price_date: (snap.prices && snap.prices.updated_at_text) || '',
    price_refreshed: priceHit,
    data_date: snap.meta.updated_at_text,
  };

  try {
    await db.collection(COLLECTION).doc(DOC_ID).set({ data: doc });
  } catch (e) {
    // 集合还没建：建一次再写
    await ensureCollection(COLLECTION);
    await db.collection(COLLECTION).doc(DOC_ID).set({ data: doc });
  }

  const summary = {
    ok: true,
    source: srcName,
    policies: doc.policy_count,
    data_date: doc.data_date,
    prices: doc.price_count,
    price_source: doc.price_source,
    price_date: doc.price_date,
    price_note: priceNote,
    snapshot_errors: errs,
    ms: Date.now() - startedAt,
  };
  console.log('sync ok', JSON.stringify(summary));

  // 降级运行要留痕：快照源全挂时虽然接口返回 ok，但政策已经停止更新了，
  // 翻 sync_log 能一眼看出是哪天开始靠云库续命的。
  if (!hit) {
    try {
      await ensureCollection(LOG_COLLECTION);
      await db.collection(LOG_COLLECTION).add({
        data: {
          at: new Date(), ok: false, degraded: true,
          errors: errs, ms: Date.now() - startedAt,
        },
      });
    } catch (e) {
      console.error('写降级日志失败', e);
    }
  }

  return summary;
};
