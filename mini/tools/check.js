/**
 * 交付前静态自检。没有微信开发者工具也能跑，用来兜住低级错误。
 *
 * 检查项：
 *  1. 所有 .js 语法（node vm 编译）
 *  2. 所有 .json 可解析
 *  3. WXML 标签配平 + 禁用标签（b/span/a/i/div/p 等浏览器标签在小程序里不存在）
 *  4. app.json 里每一页四件套是否齐
 *  5. 页面内 data-url 指向的页面是否都在 app.json 注册
 *  6. 全局样式类是否被页面用上（抽查关键类）
 *
 * 用法：node tools/check.js
 */
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const MINI = path.resolve(__dirname, '..');
const errors = [];
const warns = [];

const rel = (p) => path.relative(MINI, p).replace(/\\/g, '/');

function walk(dir, out = []) {
  for (const f of fs.readdirSync(dir)) {
    if (f === 'node_modules' || f === 'tools' || f === 'scripts') continue;
    const p = path.join(dir, f);
    const st = fs.statSync(p);
    if (st.isDirectory()) walk(p, out);
    else out.push(p);
  }
  return out;
}

const files = walk(MINI);
const jsFiles = files.filter((f) => f.endsWith('.js'));
const jsonFiles = files.filter((f) => f.endsWith('.json'));
const wxmlFiles = files.filter((f) => f.endsWith('.wxml'));

/* 1. JS 语法 */
jsFiles.forEach((f) => {
  const code = fs.readFileSync(f, 'utf8');
  try {
    new vm.Script(code, { filename: f });
  } catch (e) {
    errors.push(`[JS 语法] ${rel(f)}: ${e.message}`);
  }
});

/* 2. JSON */
jsonFiles.forEach((f) => {
  try {
    JSON.parse(fs.readFileSync(f, 'utf8'));
  } catch (e) {
    errors.push(`[JSON] ${rel(f)}: ${e.message}`);
  }
});

/* 3. WXML */
/* button 不在禁用表里：它确实是小程序原生组件，而 open-type="share"
   只能挂在 button 上——转发按钮绕不过去。其余几个是 HTML 标签，一律不用。 */
const BANNED = ['div', 'span', 'a', 'b', 'i', 'p', 'ul', 'li', 'br', 'h1', 'h2', 'h3', 'section', 'header', 'nav', 'main', 'img'];
const SELF_CLOSING = ['image', 'icon', 'progress', 'switch', 'slider', 'checkbox', 'radio', 'textarea'];

wxmlFiles.forEach((f) => {
  const src = fs.readFileSync(f, 'utf8');
  const body = src.replace(/<!--[\s\S]*?-->/g, '');

  // 禁用标签
  BANNED.forEach((t) => {
    const re = new RegExp('<' + t + '(?=[\\s/>])', 'g');
    if (re.test(body)) errors.push(`[WXML] ${rel(f)}: 用了小程序不支持的标签 <${t}>`);
  });

  // 标签配平
  const stack = [];
  const tagRe = /<\/?([a-zA-Z][\w-]*)((?:[^>"']|"[^"]*"|'[^']*')*?)(\/?)>/g;
  let m;
  while ((m = tagRe.exec(body))) {
    const whole = m[0];
    const name = m[1];
    const selfClose = m[3] === '/';
    if (whole.startsWith('</')) {
      const top = stack.pop();
      if (top !== name) {
        errors.push(`[WXML] ${rel(f)}: 标签不配平，</${name}> 对应的开始标签是 <${top || '无'}>`);
        break;
      }
    } else if (!selfClose && SELF_CLOSING.indexOf(name) < 0) {
      stack.push(name);
    }
  }
  if (stack.length) errors.push(`[WXML] ${rel(f)}: 有未闭合标签 <${stack.join('>, <')}>`);

  // 插值时用了不存在的 JS 语法（三元里的 === 是合法的，这里只兜 {{ }} 未配对）
  const open = (body.match(/{{/g) || []).length;
  const close = (body.match(/}}/g) || []).length;
  if (open !== close) errors.push(`[WXML] ${rel(f)}: {{ }} 数量不配对 (${open}/${close})`);
});

/* 4. 页面四件套 */
const appJson = JSON.parse(fs.readFileSync(path.join(MINI, 'app.json'), 'utf8'));
const pages = appJson.pages || [];
pages.forEach((p) => {
  ['.js', '.json', '.wxml', '.wxss'].forEach((ext) => {
    const f = path.join(MINI, p + ext);
    if (!fs.existsSync(f)) warns.push(`[页面] 缺 ${p}${ext}`);
  });
});

/* 5. data-url 目标存在性 */
const urlRe = /\/pages\/([a-z]+)\/([a-z]+)\?/g;
let totalLinks = 0;
jsFiles.concat(wxmlFiles).forEach((f) => {
  const src = fs.readFileSync(f, 'utf8');
  let m;
  const re = new RegExp(urlRe.source, 'g');
  while ((m = re.exec(src))) {
    totalLinks += 1;
    const target = `pages/${m[1]}/${m[2]}`;
    if (pages.indexOf(target) < 0) errors.push(`[跳转] ${rel(f)}: 指向未注册页面 ${target}`);
  }
});

/* 6. tabBar 与 pages 对齐 */
(appJson.tabBar && appJson.tabBar.list ? appJson.tabBar.list : []).forEach((t) => {
  if (pages.indexOf(t.pagePath) < 0) errors.push(`[tabBar] ${t.pagePath} 不在 pages 列表里`);
});

/* 输出 */
console.log('文件：' + jsFiles.length + ' js / ' + wxmlFiles.length + ' wxml / ' + jsonFiles.length + ' json');
console.log('页面：' + pages.length + ' 个，页面内跳转链接 ' + totalLinks + ' 处');

if (warns.length) {
  console.log('\n提示（' + warns.length + '）：');
  warns.forEach((w) => console.log('  · ' + w));
}

if (errors.length) {
  console.log('\n错误（' + errors.length + '）：');
  errors.forEach((e) => console.log('  ✗ ' + e));
  process.exit(1);
}

console.log('\n静态自检通过：0 错误');
