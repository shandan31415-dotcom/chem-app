/**
 * 云端数据通道（云开发）—— 三级回退，任何一级失败都不影响页面打开。
 *
 *   1. 云数据库                   ← 云函数每天跑 4 次，最新
 *   2. 本机缓存（Storage）         ← 上次成功拉到的那份，断网也能用
 *   3. 代码包内静态数据 data/*.js  ← 兜底，永远不会白屏
 *
 * 拉取成功后直接改 core.D 的属性，页面里都是 `core.D.xxx` 这种写法，
 * 改属性即全局生效。页面订阅 onUpdate 后自行重绘即可。
 *
 * 同步三样东西：
 *   snapshot/latest → 政策 + 参考价 + 数据日期（每天都在变）
 *   catalog/latest  → 企业与园区名录（月级变化，但协会要能自己改）
 *
 * 名录走云库的意义：原来加一家会员企业就得改代码重新发版，
 * 现在在云开发控制台的数据库里直接改，小程序下拉刷新就生效。
 *
 * 设计约束：
 *   - 云端版本必须不比包内旧才采用，防止云端落后时把新包覆盖回旧数据。
 *   - 任何异常都吞掉，只记在 state.error 里，不弹窗、不打断用户。
 */
const core = require('./core.js');
const CFG = require('./config.js');

const CACHE_KEY = 'live_snapshot_v1';
const CATALOG_KEY = 'live_catalog_v1';
/** 同一次启动内，多少毫秒之内不重复拉（切 tab 回来不重复请求） */
const MIN_GAP = 10 * 60 * 1000;

const state = {
  /** 'static' | 'cache' | 'cloud' */
  source: 'static',
  /** 云端/缓存那份的数据日期文案 */
  updatedText: '',
  /** 每次数据真正变化就 +1，页面用它判断要不要重绘 */
  rev: 0,
  error: '',
  loading: false,
  /** 名录来源：'static' | 'cache' | 'cloud' */
  catalogSource: 'static',
};

let envInited = false;
let lastPullAt = 0;
let listeners = [];

/* ---------------------------------------------------------------- 工具 */

function hasCloud() {
  return typeof wx !== 'undefined' && wx.cloud && typeof wx.cloud.init === 'function';
}

function logErr(e) {
  state.error = String((e && (e.errMsg || e.message)) || e || '').slice(0, 200);
}

function readCache() {
  try {
    if (typeof wx === 'undefined' || !wx.getStorageSync) return null;
    const raw = wx.getStorageSync(CACHE_KEY);
    if (!raw || typeof raw !== 'object') return null;
    // 缓存超过 7 天就当没有，避免长期拿着过期数据还以为是最新的
    if (!raw._at || Date.now() - raw._at > 7 * 86400 * 1000) return null;
    return raw.data || null;
  } catch (e) {
    return null;
  }
}

function writeCache(data) {
  try {
    if (typeof wx !== 'undefined' && wx.setStorageSync) {
      wx.setStorageSync(CACHE_KEY, { _at: Date.now(), data: data });
    }
  } catch (e) {
    /* 存储满了也不影响使用 */
  }
}

/** 结构校验：宁可不用，也不能拿半截数据把页面搞乱 */
function valid(snap) {
  if (!snap || typeof snap !== 'object') return false;
  const pol = snap.policies;
  if (!pol || !Array.isArray(pol.items) || pol.items.length < 5) return false;
  const bad = pol.items.some((p) => !p || !p.title || !p.url);
  if (bad) return false;
  if (snap.prices && snap.prices.groups && !Array.isArray(snap.prices.groups)) return false;
  return true;
}

/** 云端时间戳是否比包内数据新（相等也接受，用于首次灌数据） */
function newerThanPacked(snap) {
  const cloudTs = Number((snap.meta && snap.meta.updated_at) || 0);
  const packTs = Number((core.D.meta && core.D.meta.updated_at) || 0);
  if (!cloudTs) return true;
  return cloudTs >= packTs;
}

function emit() {
  const fn = listeners.slice();
  for (let i = 0; i < fn.length; i++) {
    try {
      fn[i](state);
    } catch (e) {
      /* 单个页面出错不影响其它页面 */
    }
  }
}

/** 数据指纹：用于判断「这次真的是新数据」还是「缓存和云端是同一份」 */
function fingerprint(snap) {
  const pol = snap.policies || {};
  const items = pol.items || [];
  return [
    (snap.meta && snap.meta.updated_at) || 0,
    pol.updated_at || 0,
    items.length,
    items.length ? items[0].title : '',
  ].join('|');
}

let lastKey = '';

/** 把快照写进 core.D，返回「内容是否真的换了」（内容相同的重复应用返回 false） */
function apply(snap, source) {
  if (!valid(snap)) return false;

  const key = fingerprint(snap);
  let changed = false;

  if (newerThanPacked(snap)) {
    if (snap.policies) {
      core.D.policies = snap.policies;
      changed = true;
    }
    if (snap.prices && (snap.prices.groups || []).length) {
      core.D.prices = snap.prices;
      changed = true;
    }
    if (snap.meta) {
      core.D.meta = snap.meta;
      if (snap.meta.updated_at_text) {
        state.updatedText = snap.meta.updated_at_text;
      }
    }
    if (snap.manual_note) state.manualNote = snap.manual_note;
  }

  // 来源要更新（页面上「云端已同步」那个标记靠它），但内容没变就不必让页面重绘
  if (changed || source === 'static') state.source = source;
  if (!changed || key === lastKey) return false;

  lastKey = key;
  state.rev += 1;
  return true;
}

/* ------------------------------------------------------------ 名录（catalog） */

function validCatalog(c) {
  if (!c || !Array.isArray(c.cities) || c.cities.length < 5) return false;
  return c.cities.every((x) => x && x.code && x.name);
}

function readCatalogCache() {
  try {
    if (typeof wx === 'undefined' || !wx.getStorageSync) return null;
    const raw = wx.getStorageSync(CATALOG_KEY);
    if (!raw || typeof raw !== 'object') return null;
    if (!raw._at || Date.now() - raw._at > 7 * 86400 * 1000) return null;
    return raw.data || null;
  } catch (e) {
    return null;
  }
}

function writeCatalogCache(data) {
  try {
    if (typeof wx !== 'undefined' && wx.setStorageSync) {
      wx.setStorageSync(CATALOG_KEY, { _at: Date.now(), data: data });
    }
  } catch (e) {
    /* 名录 86KB，个别机型存储紧张时写不进去，不影响当次使用 */
  }
}

/**
 * 名录合并进 core.D.parks。
 *
 * 只覆盖 cities / counts / 时间三样，note、source 这些长文本保留包内的，
 * 免得云端精简版把页脚那段说明弄丢。
 */
function applyCatalog(cat, source) {
  if (!validCatalog(cat)) return false;
  const prev = core.D.parks || {};
  const ts = Number(cat.updated_at || 0);
  const prevTs = Number(prev.updated_at || 0);
  // 云端比包内旧就忽略；相等时采用云端——协会在控制台手改之后
  // 往往不会去动 updated_at，相等也必须让云库赢，否则手改永远不生效
  if (ts && prevTs && ts < prevTs) return false;
  core.D.parks = Object.assign({}, prev, {
    updated_at: cat.updated_at || prev.updated_at,
    updated_at_text: cat.updated_at_text || prev.updated_at_text,
    counts: cat.counts || prev.counts,
    cities: cat.cities,
  });
  state.catalogSource = source;
  return true;
}

/** 拉名录。与主快照并行，失败就用包内数据，不打扰用户 */
function pullCatalog(env) {
  if (!hasCloud()) return Promise.resolve(false);

  const cached = readCatalogCache();
  let changed = false;
  if (cached && applyCatalog(cached, 'cache')) changed = true;

  return new Promise((resolve) => {
    let db;
    try {
      db = wx.cloud.database({ env: env });
    } catch (e) {
      resolve(changed);
      return;
    }
    const timer = setTimeout(() => resolve(changed), 8000);
    db.collection(CFG.CLOUD_CATALOG_COLLECTION)
      .doc(CFG.CLOUD_DOC_ID)
      .get()
      .then((res) => {
        clearTimeout(timer);
        const doc = (res && res.data) || null;
        const cat = doc && (doc.payload || doc);
        if (cat && applyCatalog(cat, 'cloud')) {
          writeCatalogCache(cat);
          resolve(true);
        } else {
          resolve(changed);
        }
      })
      .catch(() => {
        clearTimeout(timer);
        resolve(changed);
      });
  });
}

/* ---------------------------------------------------------------- 主体 */

function init() {
  const env = (CFG.CLOUD_ENV || '').trim();
  if (!env) {
    state.source = 'static';
    return;
  }
  if (!hasCloud()) {
    // 老基础库或非小程序环境：直接用包内数据
    state.source = 'static';
    return;
  }
  if (envInited) return;
  try {
    wx.cloud.init({ env: env, traceUser: false });
    envInited = true;
  } catch (e) {
    // 环境 ID 写错、云开发没开通时会走到这里。下次 pull 再试一次，不弹窗。
    logErr(e);
  }
}

/**
 * 拉一次最新数据。force=true 时忽略冷却时间。
 * 返回 Promise，永远 resolve（失败也是 resolve），方便页面无脑 await。
 */
function pull(force) {
  const now = Date.now();
  if (!force && now - lastPullAt < MIN_GAP) return Promise.resolve(state);
  lastPullAt = now;

  // 先上缓存：即使云端这次失败，用户看到的也是上次那份，而不是更旧的包内数据
  const cached = readCache();
  if (cached && apply(cached, 'cache')) emit();

  const env = (CFG.CLOUD_ENV || '').trim();
  if (!env || !hasCloud()) return Promise.resolve(state);

  init();
  state.loading = true;

  // 名录单独走一条，不耽误主快照；拿到后如果内容变了就让页面重绘一次
  pullCatalog(env)
    .then((changed) => {
      if (changed) {
        state.rev += 1;
        emit();
      }
    })
    .catch(() => {});

  return new Promise((resolve) => {
    let db;
    try {
      db = wx.cloud.database({ env: env });
    } catch (e) {
      logErr(e);
      state.loading = false;
      return resolve(state);
    }
    // 给个 8 秒超时：云函数没部署好时不会让页面一直转圈
    const timer = setTimeout(() => {
      state.loading = false;
      resolve(state);
    }, 8000);

    db.collection(CFG.CLOUD_COLLECTION)
      .doc(CFG.CLOUD_DOC_ID)
      .get()
      .then((res) => {
        clearTimeout(timer);
        const doc = (res && res.data) || null;
        // 云函数写进来的文档形如 { _id:'latest', payload:{...}, synced_at: 1690000000 }
        const snap = doc && (doc.payload || doc);
        if (apply(snap, 'cloud')) {
          writeCache(snap);
          emit();
        } else if (!valid(snap)) {
          state.error = '云端口径不符，已忽略';
        }
        state.loading = false;
        resolve(state);
      })
      .catch((e) => {
        clearTimeout(timer);
        logErr(e);
        state.loading = false;
        resolve(state);
      });
  });
}

/** 订阅数据变化，返回取消订阅函数 */
function onUpdate(fn) {
  if (typeof fn !== 'function') return function () {};
  listeners.push(fn);
  return function () {
    const i = listeners.indexOf(fn);
    if (i >= 0) listeners.splice(i, 1);
  };
}

function ready() {
  return state;
}

/** 强制刷新（下拉刷新时用），会绕过 10 分钟冷却 */
function refresh() {
  return pull(true);
}

module.exports = {
  init,
  pull,
  refresh,
  onUpdate,
  ready,
  state,
};
