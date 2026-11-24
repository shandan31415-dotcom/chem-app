/**
 * 本机记录：已学品类 / 已读政策 / 收藏。
 * 字段名与 web 版一致（learned / read / fav / seen），导出 JSON 可以两边互通。
 */
const KEY = 'chemapp.state.v1';
const EXPORT_V = 1;

const DEF = () => ({ learned: [], read: [], fav: [], seen: {} });

let S = DEF();

function load() {
  try {
    const raw = wx.getStorageSync(KEY);
    if (!raw || typeof raw !== 'object') return S;
    S = {
      learned: Array.isArray(raw.learned) ? raw.learned : [],
      read: Array.isArray(raw.read) ? raw.read : [],
      fav: Array.isArray(raw.fav) ? raw.fav : [],
      seen: raw.seen && typeof raw.seen === 'object' ? raw.seen : {},
    };
  } catch (e) {
    S = DEF();
  }
  return S;
}

function save() {
  try {
    wx.setStorageSync(KEY, S);
  } catch (e) {
    /* 存储满了不该让页面崩，静默处理 */
  }
}

function has(field, v) {
  return S[field].indexOf(v) >= 0;
}

function toggle(field, v) {
  const i = S[field].indexOf(v);
  if (i >= 0) S[field].splice(i, 1);
  else S[field].push(v);
  save();
}

function add(field, v) {
  if (!has(field, v)) {
    S[field].push(v);
    save();
  }
}

function counts() {
  return {
    learned: S.learned.length,
    read: S.read.filter((k) => String(k).indexOf('pol:') === 0).length,
    readAll: S.read.length,
    fav: S.fav.length,
  };
}

function exportJSON() {
  return JSON.stringify({
    v: EXPORT_V,
    app: 'chem-mini',
    exported_at: new Date().toISOString(),
    learned: S.learned,
    read: S.read,
    fav: S.fav,
    seen: S.seen,
  }, null, 2);
}

/** 合并导入：不覆盖，只补齐。返回补了多少条 */
function mergeImport(obj) {
  if (!obj || typeof obj !== 'object') throw new Error('不是合法的 json 对象');
  const fields = ['learned', 'read', 'fav'];
  const before = counts();
  fields.forEach((f) => {
    if (!Array.isArray(obj[f])) return;
    obj[f].forEach((v) => {
      if (S[f].indexOf(v) < 0) S[f].push(v);
    });
  });
  if (obj.seen && typeof obj.seen === 'object') {
    Object.keys(obj.seen).forEach((k) => {
      S.seen[k] = S.seen[k] || obj.seen[k];
    });
  }
  save();
  const after = counts();
  return {
    learned: after.learned - before.learned,
    read: after.readAll - before.readAll,
    fav: after.fav - before.fav,
  };
}

function clear() {
  S = DEF();
  save();
}

module.exports = { EXPORT_V, load, save, has, toggle, add, counts, exportJSON, mergeImport, clear };
