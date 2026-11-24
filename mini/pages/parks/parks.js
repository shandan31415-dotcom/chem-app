const core = require('../../utils/core.js');
const cfg = require('../../utils/config.js');

const VIEWS = [
  { k: 'heat', n: '重点企业热力' },
  { k: 'cluster', n: '产业集群' },
  { k: 'layout', n: '产业布局' },
];

const HEAT_LEGEND = [
  { color: '#e9edf0', name: '0' },
  { color: '#d3e9e2', name: '1' },
  { color: '#8ec7b9', name: '2–3' },
  { color: '#2b8773', name: '4+' },
];

Page({
  data: {
    q: '',
    kws: ['万华', '轮胎', '地炼', '纯碱', '聚氨酯', '淄博'],
    hits: [],
    hitMore: 0,
    views: VIEWS,
    view: 'heat',
    mapImg: '/assets/map/map-heat.png',
    labels: [],
    legend: HEAT_LEGEND,
    legendTitle: '重点企业',
    mapNote: cfg.MAP_NOTE,
    totals: { parks: 0, ents: 0, high: 0 },
    topHigh: [],
    topEnt: [],
    cityRows: [],
    dataDate: '',
    disclaimer: core.DISCLAIMER,
  },

  onLoad() {
    this.paint();
  },

  onShow() {
    // switchTab 带不了 query：其他页面要搜什么，放这里的 pendingQuery
    const app = getApp();
    const pending = app.globalData.pendingQuery;
    if (pending) {
      app.globalData.pendingQuery = null;
      const all = core.searchHits(pending);
      this.setData({ q: pending, hits: all.slice(0, 40), hitMore: Math.max(0, all.length - 40) });
      return;
    }
    if (!this.data.dataDate) this.paint();
  },

  /* ---------------- 主渲染 ---------------- */
  paint() {
    const st = core.cityStats();
    const T = core.totals();
    const list = core.cityList();

    const labels = core.D.mapmeta.cities.map((c) => {
      const s = st[c.code] || { high: 0, parks: 0 };
      return {
        code: c.code,
        name: c.name,
        x: c.x,
        y: c.y,
        plate: c.plate,
        lv: core.heatLevel(s.high),
        parks: s.parks,
      };
    });

    const topHigh = list
      .slice()
      .sort((a, b) => {
        const sa = st[a.code] || {};
        const sb = st[b.code] || {};
        return sb.high - sa.high || sb.parks - sa.parks;
      })
      .filter((c) => (st[c.code] || {}).high > 0)
      .slice(0, 5)
      .map((c) => ({ code: c.code, name: c.name, ...st[c.code] }));

    const topEnt = list
      .slice()
      .sort((a, b) => (st[b.code] || {}).ents - (st[a.code] || {}).ents)
      .slice(0, 6)
      .map((c) => ({
        code: c.code,
        name: c.name,
        region: c.region || '',
        parks: st[c.code].parks,
        ents: st[c.code].ents,
        chems: (c.chems || []).slice(0, 3).join(' / '),
      }));

    const cityRows = list
      .slice()
      .sort((a, b) => (st[b.code] || {}).high - (st[a.code] || {}).high)
      .map((c) => ({
        code: c.code,
        name: c.name,
        region: c.region || '',
        parks: st[c.code].parks,
        ents: st[c.code].ents,
        high: st[c.code].high,
      }));

    this.setData({
      labels,
      totals: T,
      topHigh,
      topEnt,
      cityRows,
      dataDate: (core.D.parks && core.D.parks.updated_at_text) || '',
    });
  },

  /* ---------------- 视图切换 ---------------- */
  onView(e) {
    const v = e.currentTarget.dataset.v;
    if (v === this.data.view) return;

    let legend = HEAT_LEGEND;
    let legendTitle = '重点企业';
    if (v !== 'heat') {
      const vi = (core.D.industry.views || {})[v];
      legend = (vi.legend || []).map((l) => ({ color: l.color, name: l.name }));
      legendTitle = vi.title || '';
    }

    this.setData({
      view: v,
      mapImg: '/assets/map/map-' + v + '.png',
      legend,
      legendTitle,
    });
  },

  /* ---------------- 搜索 ---------------- */
  onInput(e) {
    const q = e.detail.value;
    const all = core.searchHits(q);
    this.setData({ q, hits: all.slice(0, 40), hitMore: Math.max(0, all.length - 40) });
  },

  pickKw(e) {
    const q = e.currentTarget.dataset.k;
    const all = core.searchHits(q);
    this.setData({ q, hits: all.slice(0, 40), hitMore: Math.max(0, all.length - 40) });
  },

  clearQ() {
    this.setData({ q: '', hits: [], hitMore: 0 });
  },

  /* ---------------- 跳转 ---------------- */
  go(e) {
    const url = e.currentTarget.dataset.url;
    if (url) wx.navigateTo({ url });
  },

  goCity(e) {
    const code = e.currentTarget.dataset.code;
    if (code) wx.navigateTo({ url: '/pages/city/city?code=' + code });
  },

  onShareAppMessage() {
    const T = this.data.totals || {};
    return {
      title: '山东化工地图 · ' + (T.parks || 84) + ' 家园区 / ' + (T.ents || 0) + ' 家企业',
      path: '/pages/parks/parks',
    };
  },
});
