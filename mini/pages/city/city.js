const core = require('../../utils/core.js');

Page({
  data: {
    c: null,
    stats: { parks: 0, ents: 0, high: 0 },
    parks: [],
    ents: [],
    clusters: [],
    chems: [],
    pillars: [],
    angle: '',
    dataDate: '',
  },

  onLoad(options) {
    const code = options.code;
    const c = core.cityByCode(code);
    if (!c) {
      this.setData({ c: null });
      return;
    }
    const st = core.cityStats()[code] || { parks: 0, ents: 0, high: 0 };

    const parks = (c.parks || []).map((p) => {
      const es = p.enterprises || [];
      return {
        id: p.id,
        name: p.name,
        level: p.level || '',
        lvlCls: p.level === '高端为主' ? 'he' : p.level === '高端+基础' ? 'hem' : '',
        district: p.district || '',
        type: p.type || '',
        ents: es.length,
        high: es.filter((e) => e.high).length,
      };
    });

    const ents = (c.enterprises || []).map((e, i) => ({
      i,
      name: e.name,
      products: String(e.products || '').slice(0, 38),
      high: !!e.high,
      verify: !!e.verify,
    }));

    this.setData({
      c: {
        code: c.code,
        name: c.name,
        tagline: core.stripTags(c.tagline),
        region: c.region || '',
        intro: core.stripTags(c.intro),
        scale: core.stripTags(c.scale),
      },
      stats: st,
      parks,
      ents,
      clusters: (c.clusters || []).map((x) => ({ n: x.n, d: x.d })),
      chems: c.chems || [],
      pillars: (c.pillars || []).map((p) => ({ n: p.n, he: !!p.he })),
      angle: core.stripTags(c.angle),
      dataDate: (core.D.parks && core.D.parks.updated_at_text) || '',
    });

    wx.setNavigationBarTitle({ title: c.name + ' · 化工产业' });
  },

  go(e) {
    const url = e.currentTarget.dataset.url;
    if (url) wx.navigateTo({ url });
  },

  /** 点品种 → 回到地图 tab 搜全省做这个品种的企业 */
  searchChem(e) {
    const f = e.currentTarget.dataset.f;
    getApp().globalData.pendingQuery = f;
    wx.switchTab({ url: '/pages/parks/parks' });
  },

  onShareAppMessage() {
    const c = this.data.c;
    return {
      title: c ? c.name + ' · 化工产业地图' : '山东化工地图',
      path: c ? '/pages/city/city?code=' + c.code : '/pages/parks/parks',
    };
  },
});
