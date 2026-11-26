/**
 * 本地跑一遍 syncData 云函数：把 wx-server-sdk 与数据库换成内存桩，网络请求走真的。
 *
 * 为什么需要它：云函数的逻辑（拉快照 → 判行情是否过期 → 自己抓新浪 → 写库）
 * 在开发者工具里只能靠「手动测试」看结果，改一次跑一次太慢。
 * 这个脚本能在本机 10 秒内验证同一套逻辑。
 *
 * 跑法：
 *   node mini/tools/test_sync.js                 # 正常路径
 *   PRICE_STALE_SEC=0 node mini/tools/test_sync.js   # 强制走行情直抓
 *   MOCK_OFFLINE=1 node mini/tools/test_sync.js      # 模拟 GitHub 全挂，验证降级
 *   CLOUD_NEWER=1 node mini/tools/test_sync.js       # 模拟远程命中 CDN 缓存（比云库旧）
 */
const path = require('path');
const fs = require('fs');
const Module = require('module');

const OFFLINE = process.env.MOCK_OFFLINE === '1';
const ROOT = path.join(__dirname, '..');

// GitHub 侧全挂时，云库里应当还躺着一份旧快照——这里用仓库里现成的快照文件充当
const cloudSnap = JSON.parse(
  fs.readFileSync(path.join(ROOT, '..', 'chem-app', 'data', 'cloud_snapshot.json'), 'utf8')
);
// 把行情时间戳改成一天前，确保进入「需要刷新」分支
if (cloudSnap.prices) cloudSnap.prices.updated_at = Math.floor(Date.now() / 1000) - 86400;

// 模拟「远程源命中了 CDN 缓存，内容比云库还旧」：把云库时间改到未来。
// 期望结果：source 回落成 cloud-cache，snapshot_stale=true，不拿旧数据覆盖。
if (process.env.CLOUD_NEWER === '1' && cloudSnap.meta) {
  cloudSnap.meta.updated_at_text = '2026-12-31 23:59';
}

let written = null;
let logged = [];

const dbMock = {
  collection: (name) => ({
    doc: () => ({
      set: async ({ data }) => {
        written = { name, data };
      },
      get: async () => ({ data: { payload: cloudSnap } }),
    }),
    add: async ({ data }) => {
      logged.push(data);
      return {};
    },
  }),
  createCollection: async () => {},
};

const load = Module._load;
Module._load = function (req, parent, isMain) {
  if (req === 'wx-server-sdk') {
    return { init() {}, DYNAMIC_CURRENT_ENV: 'test', database: () => dbMock };
  }
  return load.call(this, req, parent, isMain);
};

if (OFFLINE) {
  // 只掐 GitHub 系域名，新浪照常放行——要验证的正是「快照挂了行情还能续」
  const https = require('https');
  const origGet = https.get;
  const { PassThrough } = require('stream');
  https.get = function (url) {
    if (typeof url === 'string' && /github|jsdelivr|ghfast|gh-proxy/.test(url)) {
      const req = new PassThrough();
      req.setTimeout = () => req;
      req.destroy = () => {};
      process.nextTick(() => req.emit('error', new Error('mock: github unreachable')));
      return req;
    }
    return origGet.apply(this, arguments);
  };
}

const fn = require(path.join(ROOT, 'cloudfunctions', 'syncData', 'index.js'));

fn.main()
  .then((r) => {
    console.log('返回：', JSON.stringify(r, null, 1));
    if (!written) {
      console.log('未写库');
      return;
    }
    const p = written.data.payload.prices;
    console.log(
      '落库：政策 %d 条 | 行情 %d 条 | 来源 %s | 行情日期 %s | 本次直抓 %d 条 | 快照源 %s',
      written.data.policy_count, written.data.price_count, p.source,
      p.updated_at_text, written.data.price_refreshed, written.data.source_name
    );
    const it = p.groups[0].items[0];
    console.log('样例：%s %s %s%% src=%s', it.name, it.price, it.chg, it.src);
    if (logged.length) console.log('日志：', JSON.stringify(logged));
    process.exit(0);
  })
  .catch((e) => {
    console.error('失败：', e);
    process.exit(1);
  });
