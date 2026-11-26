/**
 * 本地跑一遍 syncData 云函数：把 wx-server-sdk 与数据库换成内存桩，网络请求走真的。
 *
 * 为什么需要它：云函数的逻辑（拉快照 → 判行情是否过期 → 自己抓新浪 → 写库）
 * 在开发者工具里只能靠「手动测试」看结果，改一次跑一次太慢。
 * 这个脚本能在本机 10 秒内验证同一套逻辑。
 *
 * 跑法：
 *   node mini/tools/test_sync.js                 # 正常路径（真抓 11 个政府栏目 + 新浪行情）
 *   MOCK_EMPTY=1 node mini/tools/test_sync.js        # 云库空，走 GitHub 冷启动
 *   MOCK_OFFLINE=1 node mini/tools/test_sync.js      # GitHub 全挂（验证冷启动失败）
 *   MOCK_POLICY_DOWN=1 node mini/tools/test_sync.js  # 政府站全挂，政策沿用云库
 */
const path = require('path');
const fs = require('fs');
const Module = require('module');

const OFFLINE = process.env.MOCK_OFFLINE === '1';
const EMPTY = process.env.MOCK_EMPTY === '1';
const POLICY_DOWN = process.env.MOCK_POLICY_DOWN === '1';
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
const writtenAll = {};
let logged = [];

const dbMock = {
  collection: (name) => ({
    doc: () => ({
      set: async ({ data }) => {
        written = { name, data };
        writtenAll[name] = data;
      },
      get: async () => {
        // 名录集合初始为空，走「首次写入」分支
        if (name === 'catalog') throw new Error('document does not exist');
        if (EMPTY) throw new Error('document does not exist');
        return { data: { payload: cloudSnap } };
      },
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

if (OFFLINE || POLICY_DOWN) {
  // 掐掉指定域名，模拟「这条腿断了」。新浪放行时要验证的正是另一半还能不能续上。
  const https = require('https');
  const http = require('http');
  const origHttps = https.get;
  const origHttp = http.get;
  const { PassThrough } = require('stream');
  const githubRe = /github|jsdelivr|ghfast|gh-proxy/;
  const govRe = /shandong\.gov\.cn|ndrc\.gov\.cn|mee\.gov\.cn|miit\.gov\.cn|sdein\.gov\.cn/;

  const make = (orig, hit) => function (url) {
    if (typeof url === 'string' && hit.test(url)) {
      const req = new PassThrough();
      req.setTimeout = () => req;
      req.destroy = () => {};
      process.nextTick(() => req.emit('error', new Error('mock: unreachable')));
      return req;
    }
    return orig.apply(this, arguments);
  };

  if (OFFLINE) https.get = make(origHttps, githubRe);
  if (POLICY_DOWN) {
    https.get = make(https.get, govRe);
    http.get = make(origHttp, govRe);
  }
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
    if (writtenAll.catalog) {
      const cat = writtenAll.catalog;
      console.log('名录落库：%d 个地市 | 园区 %d | 企业 %d | 日期 %s',
        cat.city_count, cat.park_count, cat.company_count, cat.data_date);
    } else {
      console.log('名录未落库（云库已有新版或拉取失败）');
    }
    if (logged.length) console.log('日志：', JSON.stringify(logged));
    process.exit(0);
  })
  .catch((e) => {
    console.error('失败：', e);
    process.exit(1);
  });
