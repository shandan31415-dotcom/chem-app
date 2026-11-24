/**
 * 生成 tabBar 图标（81×81 PNG，微信要求不带 svg / 单张 <40KB）
 * 线性图标，描边 5px，未选中 #9AA3AD，选中 #0B6B5E（与 tabBar selectedColor 一致）
 */
const fs = require('fs');
const path = require('path');
const { Resvg } = require('@resvg/resvg-js');

const OUT = path.join(__dirname, '..', 'assets', 'tab');
const SIZES = 81;

const NORMAL = '#9AA3AD';
const ACTIVE = '#0B6B5E';

// 每个图标只画路径，配色由外层注入
const ICONS = {
  // 地图：定位针
  map: `
    <path d="M40.5 11c-12.4 0-22.5 9.9-22.5 22.1 0 16.6 22.5 36.9 22.5 36.9S63 49.7 63 33.1C63 20.9 52.9 11 40.5 11z"/>
    <circle cx="40.5" cy="33" r="8.4"/>
  `,
  // 品类：四宫格
  cats: `
    <rect x="12" y="12" width="24" height="24" rx="6"/>
    <rect x="45" y="12" width="24" height="24" rx="6"/>
    <rect x="12" y="45" width="24" height="24" rx="6"/>
    <rect x="45" y="45" width="24" height="24" rx="6"/>
  `,
  // 参考价：坐标轴 + 走势折线
  prices: `
    <path d="M13 13v55h55"/>
    <path d="M22 52l13-14 10 8 13-20"/>
  `,
  // 政策：文件 + 文字行
  policies: `
    <rect x="17" y="11" width="47" height="59" rx="6"/>
    <path d="M27 28h27M27 41h27M27 54h16"/>
  `,
  // 我的：人像
  me: `
    <circle cx="40.5" cy="27" r="11.5"/>
    <path d="M18.5 68c0-12.1 9.8-20 22-20s22 7.9 22 20"/>
  `,
};

function svg(body, color) {
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${SIZES}" height="${SIZES}" viewBox="0 0 81 81" fill="none" stroke="${color}" stroke-width="5" stroke-linecap="round" stroke-linejoin="round">${body}</svg>`;
}

fs.mkdirSync(OUT, { recursive: true });

let count = 0;
for (const [name, body] of Object.entries(ICONS)) {
  for (const [suffix, color] of [['', NORMAL], ['-on', ACTIVE]]) {
    const png = new Resvg(svg(body, color), {
      fitTo: { mode: 'width', value: SIZES },
      background: 'rgba(0,0,0,0)',
    }).render().asPng();
    const file = path.join(OUT, name + suffix + '.png');
    fs.writeFileSync(file, png);
    count++;
    console.log('  %s  %d bytes', path.basename(file), png.length);
  }
}
console.log('生成 %d 个图标 → %s', count, OUT);
