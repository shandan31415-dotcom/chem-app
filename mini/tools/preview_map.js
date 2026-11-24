/**
 * 地图叠字预览：把「PNG 底图 + 按百分比定位的地市名」合成一张图，
 * 用来肉眼确认坐标有没有错位、文字会不会互相压住。
 *
 * 这不是小程序运行结果，是同等几何关系的离线合成图。
 * 用法：node tools/preview_map.js
 */
const fs = require('fs');
const path = require('path');
const { Resvg } = require('@resvg/resvg-js');

const MINI = path.resolve(__dirname, '..');
const mapmeta = require(path.join(MINI, 'data', 'mapmeta.js'));
const parks = require(path.join(MINI, 'data', 'parks.js'));

const W = 750; // 2x 手机宽度，便于看细节
const H = (W * mapmeta.h) / mapmeta.w;

// 与页面同一套口径
const heatLevel = (high) => (high >= 4 ? 3 : high >= 2 ? 2 : high >= 1 ? 1 : 0);
const stats = {};
parks.cities.forEach((c) => {
  let high = 0;
  (c.parks || []).forEach((p) => (p.enterprises || []).forEach((e) => e.high && high++));
  (c.enterprises || []).forEach((e) => e.high && high++);
  stats[c.code] = { high, parks: (c.parks || []).length };
});

const TXT = ['#6f7a84', '#35695d', '#0b4539', '#ffffff'];
const PK = ['#4b7f73', '#4b7f73', '#0b4539', '#eaf5f1'];
const PK_STROKE = ['#ffffff', '#ffffff', '#e8f4f0', '#2f8472'];
const NAME_STROKE = ['#ffffff', '#ffffff', '#e8f4f0', '#2f8472'];

const svgPath = path.join(MINI, 'assets', 'map', 'map-heat.png');
const b64 = fs.readFileSync(svgPath).toString('base64');

let texts = '';
mapmeta.cities.forEach((c) => {
  const s = stats[c.code] || { high: 0, parks: 0 };
  const lv = heatLevel(s.high);
  const cx = (c.x / 100) * W;
  const cy = (c.y / 100) * H;
  // 字号：viewBox 单位 → 像素
  const fs2 = (c.fs / mapmeta.w) * W;
  if (c.plate) {
    const pw = c.name.length * fs2 + 10;
    const ph = fs2 + 8;
    texts +=
      `<rect x="${(cx - pw / 2).toFixed(1)}" y="${(cy - ph / 2 - 2).toFixed(1)}" ` +
      `width="${pw.toFixed(1)}" height="${ph.toFixed(1)}" rx="5" fill="#fff" stroke="#cfdcd9" stroke-width="1"/>`;
  }
  texts +=
    `<text x="${cx.toFixed(1)}" y="${(cy + fs2 * 0.35).toFixed(1)}" text-anchor="middle" ` +
    `font-family="Microsoft YaHei" font-size="${fs2.toFixed(1)}" font-weight="600" ` +
    `fill="${TXT[lv]}" stroke="${NAME_STROKE[lv]}" stroke-width="2.6" paint-order="stroke" ` +
    `stroke-linejoin="round">${c.name}</text>`;
  if (s.parks > 0 && !c.plate) {
    const pfs = Math.max(7, fs2 * 0.62);
    texts +=
      `<text x="${cx.toFixed(1)}" y="${(cy + fs2 * 0.35 + pfs + 6).toFixed(1)}" text-anchor="middle" ` +
      `font-family="Microsoft YaHei" font-size="${pfs.toFixed(1)}" ` +
      `fill="${PK[lv]}" stroke="${PK_STROKE[lv]}" stroke-width="2.2" paint-order="stroke" ` +
      `stroke-linejoin="round">${s.parks}园</text>`;
  }
});

const svg =
  `<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" ` +
  `width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">` +
  `<rect width="${W}" height="${H}" fill="#ffffff"/>` +
  `<image x="0" y="0" width="${W}" height="${H}" xlink:href="data:image/png;base64,${b64}"/>` +
  texts +
  `</svg>`;

const resvg = new Resvg(svg, {
  fitTo: { mode: 'width', value: W },
  font: { loadSystemFonts: true, fontDirs: ['C:/Windows/Fonts'] },
  background: '#ffffff',
});
const png = resvg.render().asPng();
const out = path.join(__dirname, '_preview-overlay.png');
fs.writeFileSync(out, png);
console.log('已生成预览：' + path.relative(MINI, out) + '  ' + (png.length / 1024).toFixed(1) + ' KB');
