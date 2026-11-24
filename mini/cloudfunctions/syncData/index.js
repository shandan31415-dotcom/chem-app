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

const SOURCES = [
  {
    name: 'github-raw',
    url: 'https://raw.githubusercontent.com/' + REPO + '/' + BRANCH + '/' + FILE,
    timeout: 8000,
  },
  {
    // Pages 是 CDN，命中缓存时最快；daily.yml 提交后会主动触发 Pages 重新部署
    name: 'github-pages',
    url: 'https://shandan31415-dotcom.github.io/chem-app/data/cloud_snapshot.json',
    timeout: 10000,
  },
  {
    name: 'jsdelivr',
    url: 'https://cdn.jsdelivr.net/gh/' + REPO + '@' + BRANCH + '/' + FILE,
    timeout: 12000,
  },
  {
    name: 'jsdelivr-gcore',
    url: 'https://gcore.jsdelivr.net/gh/' + REPO + '@' + BRANCH + '/' + FILE,
    timeout: 12000,
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

exports.main = async () => {
  const startedAt = Date.now();
  const errors = [];

  for (const s of SOURCES) {
    try {
      const txt = await getText(s.url, s.timeout);
      const snap = JSON.parse(txt);
      check(snap);

      const doc = {
        payload: snap,
        synced_at: new Date(),
        source_url: s.url,
        source_name: s.name,
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
        source: s.name,
        policies: doc.policy_count,
        data_date: doc.data_date,
        ms: Date.now() - startedAt,
      };
      console.log('sync ok', JSON.stringify(summary));
      return summary;
    } catch (e) {
      const msg = s.name + ': ' + String((e && e.message) || e).slice(0, 160);
      errors.push(msg);
      console.warn('sync fail', msg);
    }
  }

  // 全挂：保留云库里的旧快照，只记日志，便于下次排查
  try {
    await ensureCollection(LOG_COLLECTION);
    await db.collection(LOG_COLLECTION).add({
      data: { at: new Date(), ok: false, errors: errors, ms: Date.now() - startedAt },
    });
  } catch (e) {
    console.error('写日志失败', e);
  }

  return { ok: false, errors: errors };
};
