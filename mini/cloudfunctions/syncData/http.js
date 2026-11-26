/**
 * 云函数里的通用 GET。
 *
 * 有两个坑必须在这里处理掉，否则政策源会一片失败：
 *   1) 山东的几个站（省工信厅、省生态环境厅、省发改委）还是 http 明文，
 *      原来只写了 https.get，请求直接扑空。
 *   2) 政府站大量使用 301/302 跳转（尤其是 http→https、栏目改版），
 *      不跟跳转就只能拿到一个空的 302 响应。
 *
 * 解压逻辑保留 gzip/deflate/br 三种，政府站有相当一部分是压缩过的。
 */
const http = require('http');
const https = require('https');
const zlib = require('zlib');

const UA =
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) ' +
  'Chrome/120.0.0.0 Safari/537.36';

function once(url, timeout, extraHeaders, redirects) {
  return new Promise((resolve, reject) => {
    let u;
    try {
      u = new URL(url);
    } catch (e) {
      reject(new Error('地址不合法: ' + url));
      return;
    }
    const mod = u.protocol === 'http:' ? http : https;
    const req = mod.get(
      url,
      {
        headers: Object.assign(
          {
            'User-Agent': UA,
            Accept: 'text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Cache-Control': 'no-cache',
          },
          extraHeaders || {}
        ),
      },
      (res) => {
        const code = res.statusCode;
        if (code >= 300 && code < 400 && res.headers.location) {
          res.resume();
          if (redirects <= 0) {
            reject(new Error('跳转过多'));
            return;
          }
          let next;
          try {
            next = new URL(res.headers.location, url).href;
          } catch (e) {
            reject(new Error('跳转地址不合法'));
            return;
          }
          once(next, timeout, extraHeaders, redirects - 1).then(resolve, reject);
          return;
        }
        if (code !== 200) {
          res.resume();
          reject(new Error('HTTP ' + code));
          return;
        }
        const enc = String(res.headers['content-encoding'] || '').toLowerCase();
        let stream = res;
        if (enc === 'gzip') stream = res.pipe(zlib.createGunzip());
        else if (enc === 'deflate') stream = res.pipe(zlib.createInflate());
        else if (enc === 'br') stream = res.pipe(zlib.createBrotliDecompress());

        const chunks = [];
        stream.on('data', (c) => chunks.push(c));
        stream.on('end', () => resolve(Buffer.concat(chunks).toString('utf8')));
        stream.on('error', reject);
      }
    );
    req.setTimeout(timeout, () => req.destroy(new Error('超时 ' + timeout + 'ms')));
    req.on('error', reject);
  });
}

/** 取文本，最多跟 3 次跳转 */
function getText(url, timeout, extraHeaders) {
  return once(url, timeout || 8000, extraHeaders, 3);
}

/** 并发上限受控的批量请求：政策源十来个，一把全发出去容易被限流 */
async function mapLimit(items, limit, fn) {
  const out = new Array(items.length);
  let i = 0;
  const workers = new Array(Math.min(limit, items.length)).fill(0).map(async () => {
    for (;;) {
      const idx = i++;
      if (idx >= items.length) return;
      try {
        out[idx] = { ok: true, value: await fn(items[idx], idx) };
      } catch (e) {
        out[idx] = { ok: false, error: String((e && e.message) || e) };
      }
    }
  });
  await Promise.all(workers);
  return out;
}

module.exports = { getText, mapLimit, UA };
