/**
 * 生成整改效果预览：把真实 wxss 注入 HTML，用相同类名复刻三处改动，
 * 保证「预览看到的」和「真机看到的」是同一套样式，而不是另画一版。
 */
const fs = require('fs');
const path = require('path');

const MINI = path.resolve(__dirname, '..');

function read(p) {
  try {
    return fs.readFileSync(path.join(MINI, p), 'utf8');
  } catch (e) {
    return '';
  }
}

// wxss 无 rpx、无嵌套，只把 page 选择器换成容器类即可当 css 用
const css = [read('app.wxss'), read('pages/parks/parks.wxss'), read('pages/ent/ent.wxss'), read('pages/me/me.wxss')]
  .join('\n')
  .replace(/(^|\n)page\s*\{/g, '$1.phone-body {');

const phone = (title, extraCls, body) => `
<div class="phone">
  <div class="navbar">${title}</div>
  <div class="phone-body ${extraCls}">${body}</div>
</div>`;

const screen1 = phone(
  '地图',
  '',
  `
  <div class="wrap">
    <div class="mapcard">
      <div class="mapwrap">
        <img class="mapimg" src="../assets/map/map-heat.png" alt="山东化工分布示意" />
      </div>
      <div class="legend">
        <span class="lg">重点企业</span>
        <span class="sw" style="background:#e9edf0"></span><span>0</span>
        <span class="sw" style="background:#d3e9e2"></span><span>1</span>
        <span class="sw" style="background:#8ec7b9"></span><span>2–3</span>
        <span class="sw" style="background:#2b8773"></span><span>4+</span>
      </div>
      <div class="mapnote">行政区划示意图，不作为边界或区划依据</div>
    </div>

    <div class="card kpis">
      <div class="kp"><span class="kpn">16</span><span class="kpl">地市</span></div>
      <div class="kp"><span class="kpn">84</span><span class="kpl">化工园区</span></div>
      <div class="kp"><span class="kpn">220</span><span class="kpl">收录企业</span></div>
      <div class="kp hi"><span class="kpn">40</span><span class="kpl">重点企业</span></div>
    </div>

    <div class="mark">
      <b>改动 1</b> 图注新增「示意图」声明，规避不规范地图投诉；「高端企业」全部改为「重点企业」。
    </div>
  </div>`
);

const screen2 = phone(
  '万华化学',
  '',
  `
  <div class="wrap">
    <div class="dt">万华化学</div>
    <div class="dsub">烟台化工产业园 · 烟台</div>

    <div class="hint" style="padding:0 2px 10px">
      <span class="tag he">◆ 重点企业</span>
    </div>

    <div class="card">
      <div class="field">
        <div class="fk">主营产品范围</div>
        <div class="fv">MDI、TDI、聚醚多元醇、ADI、新材料</div>
      </div>
      <div class="field">
        <div class="fk">一句话印象</div>
        <div class="fv">全球 MDI 龙头，山东高端化工的代表</div>
      </div>
    </div>

    <div class="card">
      <div class="btnrow"><div class="btn">☆ 收藏这家企业</div></div>
    </div>

    <div class="hint">
      企业信息为人工整理，来自政府公示与企业公开资料；未收录联系电话与联系人。
      不构成合作、采购或投资建议。
    </div>

    <div class="fixbar">信息有误，或希望撤下本页内容？<span class="fixlink">申请更正 / 删除</span></div>

    <div class="mark">
      <b>改动 2</b> 详情页底部新增「通知—删除」入口，这是《民法典》1195 条的免责前提。
    </div>
  </div>`
);

const screen3 = phone(
  '我的',
  '',
  `
  <div class="wrap">
    <div class="sec-title">本机记录</div>
    <div class="card">
      <div class="kv"><span class="k">已学品类</span><span class="v">12 / 73</span></div>
      <div class="kv"><span class="k">已读政策</span><span class="v">3 / 10</span></div>
      <div class="kv"><span class="k">收藏</span><span class="v">5</span></div>
    </div>

    <div class="sec-title">信息与合规</div>
    <div class="card">
      <div class="row">
        <div class="main">
          <div class="rt">信息来源说明</div>
          <div class="rm">园区 / 企业 / 参考价 / 政策 各自的出处</div>
        </div>
        <span class="arrow">›</span>
      </div>
      <div class="row">
        <div class="main">
          <div class="rt">信息更正 / 申请删除</div>
          <div class="rm">收录信息来自公开渠道，如有出入可联系处理</div>
        </div>
        <span class="arrow">›</span>
      </div>
    </div>

    <div class="disclaimer">本应用为化工行业信息导航工具，内容仅供参考，不构成任何投资、交易或经营决策依据。所收录内容均整理自政府公示、企业公开资料等公开渠道，可能存在滞后或疏漏，请以官方发布为准。如信息有误或需更正、删除，可在「我的 → 信息更正」提交申请，核实后处理。</div>

    <div class="mark">
      <b>改动 3</b> 「我的」页新增合规区块，每一条来源都能单独答得上来。
    </div>
  </div>`
);

const html = `<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<title>小程序整改效果预览</title>
<style>
  * { box-sizing: border-box; }
  body {
    margin: 0; padding: 26px 20px 40px;
    background: #eef0f4;
    font-family: -apple-system, "PingFang SC", "Helvetica Neue", sans-serif;
    color: #141821;
  }
  .hd { max-width: 1220px; margin: 0 auto 20px; }
  .hd h1 { font-size: 19px; font-weight: 600; margin: 0 0 6px; }
  .hd p { font-size: 13px; color: #6b7280; margin: 0; line-height: 1.7; }
  .hd code { background: #e2e5ea; padding: 1px 5px; border-radius: 4px; font-size: 12px; }

  .stage { display: flex; gap: 22px; max-width: 1220px; margin: 0 auto; flex-wrap: wrap; }
  .phone {
    width: 375px; height: 700px; background: #f4f5f7;
    border-radius: 26px; overflow: hidden;
    box-shadow: 0 6px 20px rgba(16,24,40,.10);
    display: flex; flex-direction: column; flex: 0 0 auto;
  }
  .navbar {
    height: 52px; flex: 0 0 52px; background: #111827; color: #fff;
    display: flex; align-items: center; justify-content: center;
    font-size: 15px; font-weight: 500; letter-spacing: .3px;
  }
  .phone-body { flex: 1; overflow-y: auto; }

${css}

  /* 预览专用标注，不属于小程序代码 */
  .mark {
    margin: 14px 2px 6px; padding: 10px 12px;
    background: #fff8e6; border-left: 3px solid #e0a83a;
    border-radius: 0 8px 8px 0;
    font-size: 11.5px; line-height: 1.65; color: #7a5b12;
  }
  .mark b { color: #8a5a00; }
</style>
</head>
<body>

<div class="hd">
  <h1>小程序整改效果预览</h1>
  <p>以下三屏使用 <code>app.wxss</code> 原始样式渲染，类名与页面结构一一对应，改动后的真机观感与此一致。
     可滚动查看完整内容。</p>
</div>

<div class="stage">
${screen1}
${screen2}
${screen3}
</div>

</body>
</html>`;

const out = path.join(__dirname, 'preview.html');
fs.writeFileSync(out, html, 'utf8');
console.log('已生成 ' + out);
console.log('样式注入 ' + (css.length / 1024).toFixed(1) + ' KB');
