/**
 * 把 chem-app/data/sdmap.json 的手绘山东 SVG 渲染成 3 张 PNG。
 *
 * 为什么烧成图片：小程序 WXML 没有 <svg>，canvas 重绘要自己解析路径且易踩坑。
 * 这张图本来就是示意图（无经纬度）、数据静态、配色固定 3 套，所以预渲染是等价且最省的选择。
 *
 * 关键取舍：图里【不烧文字】。中文标签用 WXML 绝对定位叠上去
 * （见 data/mapmeta.js 的百分比坐标），这样字体渲染不依赖设备、园数可动态变。
 *
 * 用法：node tools/render_map.js
 */
const fs = require("fs");
const path = require("path");
const { Resvg } = require("@resvg/resvg-js");

const MINI = path.resolve(__dirname, "..");
const SRC = path.resolve(MINI, "..", "chem-app", "data");
const OUT = path.join(MINI, "assets", "map");

const read = (n) => JSON.parse(fs.readFileSync(path.join(SRC, n + ".json"), "utf8"));

// 与 chem-app/styles.css 的 .mct.t0~t3 严格一致
const HEAT = ["#e9edf0", "#d3e9e2", "#8ec7b9", "#2b8773"];
const STROKE = "#ffffff";
const STROKE_W = 1.05;
const EMPTY = "#e9edf0";

const sdmap = read("sdmap");
const industry = read("industry");
const parks = read("parks");

// —— 每个地市的高端企业数，决定热力等级（与 app.js heatLevel 同口径）——
const heatLevel = (high) => (high >= 4 ? 3 : high >= 2 ? 2 : high >= 1 ? 1 : 0);
const stats = {};
parks.cities.forEach((c) => {
  let high = 0;
  (c.parks || []).forEach((p) => {
    (p.enterprises || []).forEach((e) => {
      if (e.high) high++;
    });
  });
  (c.enterprises || []).forEach((e) => {
    if (e.high) high++;
  });
  stats[c.code] = { high };
});

function buildSvg(fillOf) {
  const parts = [];
  Object.keys(sdmap.cities).forEach((code) => {
    const c = sdmap.cities[code];
    parts.push(
      `<path d="${c.d}" fill="${fillOf(code)}" stroke="${STROKE}" stroke-width="${STROKE_W}" stroke-linejoin="round"/>`
    );
  });
  return (
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${sdmap.viewBox}" ` +
    `width="${sdmap.w}" height="${sdmap.h}">${parts.join("")}</svg>`
  );
}

function render(name, svg) {
  const resvg = new Resvg(svg, {
    fitTo: { mode: "width", value: 960 }, // 3x，手机上不糊
    background: "rgba(0,0,0,0)",
  });
  const png = resvg.render().asPng();
  const p = path.join(OUT, name);
  fs.writeFileSync(p, png);
  console.log(`  ${name.padEnd(18)} ${(png.length / 1024).toFixed(1)} KB`);
}

fs.mkdirSync(OUT, { recursive: true });
console.log("渲染山东地图：");

// 1) 高端热力
render("map-heat.png", buildSvg((code) => HEAT[heatLevel((stats[code] || { high: 0 }).high)]));

// 2) 产业集群 / 3) 1+3+2 布局：取该市 legend 首项颜色
["cluster", "layout"].forEach((view) => {
  const v = industry.views[view];
  const cmap = {};
  v.legend.forEach((l) => (cmap[l.key] = l.color));
  render(
    `map-${view}.png`,
    buildSvg((code) => {
      const keys = v.cities[code] || [];
      return cmap[keys[0]] || EMPTY;
    })
  );
});

console.log("完成 → assets/map/");
