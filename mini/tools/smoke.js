/**
 * 逻辑冒烟：在 Node 里跑一遍 utils/core.js，验证统计口径与 web 版一致。
 * 小程序端跑不了的（渲染、wx API）不测，只测「数对不对」。
 *
 * 用法：node tools/smoke.js
 */
const path = require('path');

// 最小 wx 桩：store.js 只用到同步存储
const mem = {};
global.wx = {
  getStorageSync: (k) => (k in mem ? mem[k] : ''),
  setStorageSync: (k, v) => {
    mem[k] = v;
  },
};

const core = require(path.resolve(__dirname, '..', 'utils', 'core.js'));
const store = require(path.resolve(__dirname, '..', 'utils', 'store.js'));

let fail = 0;
function ok(cond, label, extra) {
  if (cond) {
    console.log('  ✓ ' + label + (extra ? '  ' + extra : ''));
  } else {
    console.log('  ✗ ' + label + (extra ? '  ' + extra : ''));
    fail += 1;
  }
}

console.log('\n[规模]');
const T = core.totals();
const st = core.cityStats();
ok(core.cityList().length === 16, '地市 16 个', '实际 ' + core.cityList().length);
ok(T.parks === 84, '园区 84 家', '实际 ' + T.parks);
ok(T.ents === 220, '企业 220 家', '实际 ' + T.ents);
ok(core.D.cats.items.length === 73, '品类 73 个', '实际 ' + core.D.cats.items.length);
ok(core.D.cats.groups.length === 12, '品类分组 12 组', '实际 ' + core.D.cats.groups.length);
ok(core.D.boards.boards.length === 7, '七大板块', '实际 ' + core.D.boards.boards.length);
ok(core.chainStages().length === 3, '产业链 3 段');
ok(core.allPrices().length === 23, '参考价 23 个品种', '实际 ' + core.allPrices().length);
ok(core.D.policies.items.length >= 20, '政策不少于 20 条', '实际 ' + core.D.policies.items.length);
ok(core.D.policies.items.some(p => p.org === '山东省生态环境厅'), '政策含省级环保口径（生态环境厅）');

console.log('\n[一致性]');
// 每个地市只要园区/企业数对得上，说明 cityStats 没算漏
let sumHigh = 0;
Object.keys(st).forEach((k) => {
  sumHigh += st[k].high;
});
ok(sumHigh === T.high, '高端企业分市求和 = 总数', T.high + ' 家');
ok(Object.keys(st).length === 16, 'cityStats 覆盖 16 个地市');
// 空企业园区必须仍是 53 家（缺口的真实反映，不能凭空补）
const emptyParks = core.allParks().filter((p) => !(p.enterprises || []).length);
ok(emptyParks.length === 53, '空企业园区 53 家（未编造数据）', '实际 ' + emptyParks.length);

console.log('\n[检索]');
const h1 = core.searchHits('万华');
ok(h1.length > 0, '搜「万华」有结果', h1.length + ' 条');
ok(h1.some((x) => x.t === '企业'), '「万华」命中企业');
const h2 = core.searchHits('淄博');
ok(h2.some((x) => x.t === '地市'), '搜「淄博」命中地市');
const h3 = core.searchHits('MDI');
ok(h3.length > 0, '搜「MDI」有结果', h3.length + ' 条');
const h4 = core.searchHits('不存在的品种xyz');
ok(h4.length === 0, '搜不存在关键词返回空');
const idx = core.buildIndex();
ok(idx.length > 200, '检索索引规模正常', idx.length + ' 条');
idx.forEach((x) => {
  if (!x.url || x.url.indexOf('/pages/') !== 0) {
    console.log('  ✗ 索引里有非法跳转：' + x.n + ' → ' + x.url);
    fail += 1;
  }
});

console.log('\n[品类]');
ok(core.catById('polyurethane') && core.catById('polyurethane').name === '聚氨酯', '按 id 取品类正常');
ok(core.catSearch('mdi').length > 0, '品类搜「mdi」有结果');
const c = core.catById('polyurethane');
['cost', 'demand', 'supply', 'shandong', 'flow', 'logistics'].forEach((k) => {
  if (!c[k] || String(c[k]).length < 10) {
    console.log('  ✗ 聚氨酯缺六问字段：' + k);
    fail += 1;
  }
});
ok(core.chainStageOf('refining') !== null, '产业链归属可查');
ok(core.boardByKey('refining') !== null, '板块可查');

console.log('\n[参考价]');
const p = core.priceByName('原油');
ok(!!p, '按名取品种');
ok(!('news' in p), '行情条目已剥离 news（审核要求）');
const all = core.allPrices();
ok(all.every((x) => !('news' in x)), '23 个品种全部无 news 字段');
ok(core.pct(2.5).c === 'up' && core.pct(-1).c === 'down', '红涨绿跌口径');
ok(core.pct(null).t === '—', '空值显示 —');

console.log('\n[走势数据]');
const series = core.D.hist.series;
ok(Object.keys(series).length === 23, '23 个品种都有走势', '实际 ' + Object.keys(series).length);
let badRows = [];
Object.keys(series).forEach((k) => {
  series[k].forEach((r) => {
    if (r.length !== 2 || typeof r[1] !== 'number' || isNaN(r[1])) badRows.push(k);
  });
});
ok(badRows.length === 0, '走势行格式正确（日期+收盘价）', badRows.slice(0, 3).join(','));
ok(series['原油'].length >= 200, '原油走势条数够', series['原油'].length + ' 根');

console.log('\n[地图坐标]');
const mm = core.D.mapmeta;
ok(mm.cities.length === 16, '16 个地市标签');
ok(
  mm.cities.every((x) => x.x >= 0 && x.x <= 100 && x.y >= 0 && x.y <= 100),
  '标签坐标都在 0-100% 内'
);
const out = mm.cities.filter((x) => x.x < 2 || x.x > 98 || x.y < 2 || x.y > 98);
ok(out.length === 0, '没有贴边标签（会被裁掉）', out.map((x) => x.name).join(','));

console.log('\n[本机记录]');
store.clear();
store.add('learned', 'polyurethane');
store.add('learned', 'polyurethane');
ok(store.counts().learned === 1, '重复标记不重复计数');
store.toggle('fav', 'px:原油');
ok(store.has('fav', 'px:原油'), '收藏可写入');
const json = store.exportJSON();
ok(JSON.parse(json).app === 'chem-mini', '导出的 JSON 可解析');
store.mergeImport({ learned: ['pp'], read: ['pol:pol1'], fav: [] });
ok(store.counts().learned === 2, '导入是合并不是覆盖');
store.clear();
ok(store.counts().learned === 0, '清空生效');

console.log('');
if (fail) {
  console.log('冒烟失败：' + fail + ' 项');
  process.exit(1);
}
console.log('冒烟通过：0 失败');
