/**
 * 云端数据通道冒烟：验证「云库 → 缓存 → 包内静态」这条链不会把页面搞坏。
 * 用假的 wx 对象模拟，不联网、不依赖开发者工具。
 *
 * 用法：node tools/smoke_live.js
 */
const path = require('path');

const mem = {};
global.wx = {
  getStorageSync: (k) => (k in mem ? mem[k] : ''),
  setStorageSync: (k, v) => {
    mem[k] = v;
  },
};

const root = path.resolve(__dirname, '..');
const core = require(path.join(root, 'utils', 'core.js'));
const live = require(path.join(root, 'utils', 'live.js'));

let fail = 0;
function ok(cond, label, extra) {
  console.log((cond ? '  ✓ ' : '  ✗ ') + label + (extra ? '  ' + extra : ''));
  if (!cond) fail += 1;
}

/** 造一份「云端快照」：条数比包内少，但日期更新，用来验证它确实替换了数据 */
function makeSnap(count, opts) {
  const o = opts || {};
  const items = [];
  for (let i = 0; i < count; i++) {
    items.push({
      id: 'pol' + (i + 1),
      title: o.titlePrefix ? o.titlePrefix + i : '云端测试政策第 ' + (i + 1) + ' 号',
      url: 'https://www.miit.gov.cn/test/' + i + '.html',
      level: i % 2 ? '山东省' : '国家级',
      org: '测试机关',
      ts: 1793000000 + i,
      date: '2026-11-01',
    });
  }
  return {
    schema: 1,
    meta: { updated_at: o.ts || 1793000000, updated_at_text: '2026-11-24 06:30' },
    policies: { updated_at: o.ts || 1793000000, updated_at_text: '2026-11-24 06:30', items },
    prices: { updated_at: 1793000000, updated_at_text: '2026-11-24', count: 1, groups: [{ name: '测试', items: [] }] },
  };
}

function stubCloud(payload, opts) {
  const o = opts || {};
  global.wx.cloud = {
    init() {
      if (o.initThrows) throw new Error('cloud init error');
    },
    database() {
      return {
        collection() {
          return {
            doc() {
              return {
                get() {
                  if (o.reject) return Promise.reject(new Error('collection not exists'));
                  return Promise.resolve({ data: o.bare ? payload : { _id: 'latest', payload: payload } });
                },
              };
            },
          };
        },
      };
    },
  };
}

(async function () {
  const packedN = core.D.policies.items.length;
  const packedTs = Number(core.D.meta.updated_at) || 0;
  // 云端快照必须比包内新才会被采用，所以时间戳从包内那份往前推，别写死日期
  let t = packedTs;
  const nextTs = () => {
    t += 86400;
    return t;
  };

  console.log('\n[无云环境]');
  let st = await live.pull(true);
  ok(st.source === 'static', '没有 wx.cloud 时退回包内数据', 'source=' + st.source);
  ok(core.D.policies.items.length === packedN, '包内政策条数不变');

  console.log('\n[云库有更新]');
  const snap = makeSnap(12, { ts: nextTs() });
  stubCloud(snap);
  st = await live.pull(true);
  ok(st.source === 'cloud', '标记为云端来源', 'source=' + st.source);
  ok(core.D.policies.items.length === 12, '政策被替换为云端 12 条', '实际 ' + core.D.policies.items.length);
  ok(core.D.policies.items[0].title.indexOf('云端测试政策') === 0, '内容确实是云端那份');
  ok(st.updatedText === '2026-11-24 06:30', '数据日期跟着云端', st.updatedText);
  ok(!!mem.live_snapshot_v1, '写入本机缓存');

  console.log('\n[页面订阅]');
  let hit = 0;
  const off = live.onUpdate(() => { hit += 1; });
  stubCloud(makeSnap(13, { ts: nextTs() }));
  await live.refresh();
  ok(hit === 1, '数据变化时通知订阅者一次', '回调 ' + hit + ' 次');
  off();
  stubCloud(makeSnap(14, { ts: nextTs() }));
  await live.refresh();
  ok(hit === 1, '取消订阅后不再回调');

  console.log('\n[异常兜底]');
  const before = core.D.policies.items.length;
  stubCloud(null, { reject: true });
  st = await live.pull(true);
  ok(core.D.policies.items.length === before, '云库读失败时保留现有数据', '仍有 ' + before + ' 条');
  ok(/collection|not exists|err/i.test(st.error) || st.error === '', '错误被吞掉不抛出', st.error);

  stubCloud(makeSnap(3, { ts: nextTs() }), { initThrows: true });
  st = await live.pull(true);
  ok(st.source !== 'cloud' || core.D.policies.items.length >= 3, 'init 抛错不影响流程');

  console.log('\n[坏数据不落地]');
  const good = core.D.policies.items.length;
  stubCloud({ meta: { updated_at: nextTs() }, policies: { items: [] } });
  st = await live.pull(true);
  ok(core.D.policies.items.length === good, '空政策数组被拒绝，页面不会变空');

  stubCloud({ meta: { updated_at: nextTs() }, policies: { items: [{ title: '缺链接' }] } });
  st = await live.pull(true);
  ok(core.D.policies.items.length === good, '缺 url 的条目被拒绝');

  console.log('\n[日期更旧的云端数据不采用]');
  const keepN = core.D.policies.items.length;
  stubCloud(makeSnap(20, { ts: 1, titlePrefix: '旧数据' }));
  st = await live.pull(true);
  ok(core.D.policies.items.length === keepN, '云端比包内旧时保持现状', '仍有 ' + keepN + ' 条');

  console.log('');
  if (fail) {
    console.log('云端通道冒烟失败：' + fail + ' 项');
    process.exit(1);
  }
  console.log('云端通道冒烟通过：0 失败（包内原始 ' + packedN + ' 条，包内时间戳 ' + packedTs + '）');
})();
