/**
 * 云函数 syncData —— 每天把 GitHub 上的数据快照灌进云数据库。
 *
 * 为什么绕这一圈：小程序端不能随便请求外部域名（要在后台配合法域名），
 * GitHub 在国内也不稳定。云函数跑在腾讯云里，由它去取，小程序只读云数据库，
 * 一次配置，之后不用管。
 *
 * 部署：微信开发者工具 → 右键 cloudfunctions/syncData → 「上传并部署：云端安装依赖」
 * 触发器：见同目录 config.json（每天 06:30 一次），上传后到云开发控制台
 *        「云函数 → syncData → 触发器」确认已生效。
 *
 * 取数顺序：GitHub raw（最实时）→ jsDelivr → jsDelivr 备用节点。
 * 三个都失败时**不动云库**，保留上一次成功的快照，小程序照样能读。
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

function getText(url, timeout) {
  return new Promise((resolve, reject) => {
    const req = https.get(
      url,
      {
        headers: {
          'User-Agent': 'chem-mini-sync/1.0 (+wechat-miniprogram)',
          'Accept-Encoding': 'gzip, deflate, br',
          'Cache-Control': 'no-cache',
          Pragma: 'no-cache',
        },
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

exports.main = async () => {
  const startedAt = Date.now();
  let hit;
  try {
    hit = await raceOk(SOURCES);
  } catch (errors) {
    // 全挂：保留云库里的旧快照，只记日志，便于下次排查
    const errs = Array.isArray(errors) ? errors : [String(errors)];
    try {
      await ensureCollection(LOG_COLLECTION);
      await db.collection(LOG_COLLECTION).add({
        data: { at: new Date(), ok: false, errors: errs, ms: Date.now() - startedAt },
      });
    } catch (e) {
      console.error('写日志失败', e);
    }
    console.warn('sync 全部失败', errs.join(' | '));
    return { ok: false, errors: errs, ms: Date.now() - startedAt };
  }

  const snap = hit.snap;
  const doc = {
    payload: snap,
    synced_at: new Date(),
    source_url: hit.url,
    source_name: hit.source,
    policy_count: snap.policies.items.length,
    price_count: (snap.prices && snap.prices.count) || 0,
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
    source: hit.source,
    policies: doc.policy_count,
    data_date: doc.data_date,
    ms: Date.now() - startedAt,
  };
  console.log('sync ok', JSON.stringify(summary));
  return summary;
};
