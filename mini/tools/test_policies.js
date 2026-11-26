/**
 * 本地验证云函数里的政策采集模块（policies.js）。
 *
 * 不用部署、不用开发者工具，直接在本机跑一遍抓取与合并：
 *   node mini/tools/test_policies.js
 *   node mini/tools/test_policies.js --verify-off   # 跳过死链抽检，只看抓取
 *
 * 期望：11 个源大部分成功；新增数 ≥ 0；合并后总数不少于现有条数。
 */
const path = require('path');
const fs = require('fs');

const ROOT = path.join(__dirname, '..', '..');
const pol = require(path.join(ROOT, 'mini', 'cloudfunctions', 'syncData', 'policies.js'));

const existing = JSON.parse(
  fs.readFileSync(path.join(ROOT, 'chem-app', 'data', 'policies.json'), 'utf8')
).items;

const skipVerify = process.argv.indexOf('--verify-off') >= 0;

crawl_()
  .then((r) => {
    console.log('\n=== 各源结果 ===');
    r.sources.forEach((s) => {
      console.log(
        '  ' + (s.ok ? 'OK  ' : 'FAIL') + ' ' + s.org.padEnd(14, ' ') +
        (s.ok ? '新增 ' + s.count : s.err)
      );
    });
    console.log('\n现有 %d 条 → 合并后 %d 条，本轮新增 %d 条，耗时 %dms',
      existing.length, r.total, r.added, r.ms);
    console.log('回源补日期 %d 条，死链剔除 %d 条，无日期丢弃 %d 条',
      r.enriched, r.dead, r.dropped_no_ts);

    const byLv = {};
    r.items.forEach((x) => { byLv[x.level] = (byLv[x.level] || 0) + 1; });
    console.log('层级分布：', JSON.stringify(byLv));

    const tagCnt = {};
    r.items.forEach((x) => (x.tags || []).forEach((t) => { tagCnt[t] = (tagCnt[t] || 0) + 1; }));
    console.log('标签分布：', JSON.stringify(tagCnt));
    console.log('无标签：', r.items.filter((x) => !(x.tags || []).length).length);

    console.log('\n最近 6 条：');
    r.items.slice(0, 6).forEach((x) => {
      const d = new Date((x.ts + 8 * 3600) * 1000).toISOString().slice(0, 10);
      console.log('  ' + d + ' [' + (x.tags || []).join('/') + '] ' + x.title.slice(0, 40));
    });

    const bad = r.items.filter((x) => !x.url || !/^https?:\/\//.test(x.url) || !x.ts);
    console.log('\n字段异常条目：', bad.length);

    // 把结果写出来，方便和现网数据 diff
    fs.writeFileSync(
      path.join(ROOT, 'mini', 'tools', '.policies_out.json'),
      JSON.stringify(r.items, null, 1)
    );
    console.log('已写出 mini/tools/.policies_out.json');
  })
  .catch((e) => {
    console.error('失败：', e);
    process.exit(1);
  });

function crawl_() {
  return pol.crawlPolicies(existing, { skipVerify: skipVerify }).then((r) => r);
}
