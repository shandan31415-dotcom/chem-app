/**
 * 生成小程序头像候选（512x512 PNG）
 * 微信要求：png/jpg，建议 144x144 以上，2MB 以内；列表里常被裁成圆形，核心图形留足边距
 */
const { Resvg } = require('@resvg/resvg-js');
const fs = require('fs');
const path = require('path');

const OUT = path.join(__dirname, 'brand');
fs.mkdirSync(OUT, { recursive: true });

function render(name, svg) {
  const r = new Resvg(svg, {
    fitTo: { mode: 'width', value: 512 },
    font: { loadSystemFonts: true, defaultFontFamily: 'Microsoft YaHei' },
  });
  const png = r.render().asPng();
  const p = path.join(OUT, name + '.png');
  fs.writeFileSync(p, png);
  console.log('  %s  %s KB', (name + '.png').padEnd(18), (png.length / 1024).toFixed(1));
}

const GREEN = '#0B6B5E';
const INK = '#141821';

/* A. 单字版：深绿底 + 白「化」 */
const A = `<svg width="512" height="512" xmlns="http://www.w3.org/2000/svg">
<rect width="512" height="512" fill="${GREEN}"/>
<text x="256" y="264" font-family="Microsoft YaHei" font-size="300" font-weight="700"
 fill="#FFFFFF" text-anchor="middle" dominant-baseline="central">化</text>
</svg>`;

/* B. 双字版：深绿底 + 白「鲁化」 */
const B = `<svg width="512" height="512" xmlns="http://www.w3.org/2000/svg">
<rect width="512" height="512" fill="${GREEN}"/>
<text x="256" y="264" font-family="Microsoft YaHei" font-size="196" font-weight="700"
 fill="#FFFFFF" text-anchor="middle" dominant-baseline="central" letter-spacing="6">鲁化</text>
</svg>`;

/* C. 图形版：深绿底 + 白色六边形（化工意象）+ 内部折线（趋势） */
const C = `<svg width="512" height="512" xmlns="http://www.w3.org/2000/svg">
<rect width="512" height="512" fill="${GREEN}"/>
<path d="M256 104 L392 182 L392 330 L256 408 L120 330 L120 182 Z"
 fill="none" stroke="#FFFFFF" stroke-width="26" stroke-linejoin="round"/>
<path d="M168 276 L222 226 L272 258 L344 186"
 fill="none" stroke="#FFFFFF" stroke-width="24" stroke-linecap="round" stroke-linejoin="round"/>
</svg>`;

/* D. 墨色版：近黑底 + 白「化」+ 绿色下横（低饱和，名单里更沉稳） */
const D = `<svg width="512" height="512" xmlns="http://www.w3.org/2000/svg">
<rect width="512" height="512" fill="${INK}"/>
<text x="256" y="238" font-family="Microsoft YaHei" font-size="260" font-weight="700"
 fill="#FFFFFF" text-anchor="middle" dominant-baseline="central">化</text>
<rect x="176" y="392" width="160" height="14" rx="7" fill="${GREEN}"/>
</svg>`;

console.log('生成头像：');
render('icon-a-单字绿', A);
render('icon-b-鲁化', B);
render('icon-c-六边形', C);
render('icon-d-单字墨', D);
console.log('\n输出目录：' + OUT);
