const core = require('../../utils/core.js');

Page({
  data: {
    p: null,
    ents: [],
    dataDate: '',
  },

  onLoad(options) {
    const p = core.parkById(options.id);
    if (!p) {
      this.setData({ p: null });
      return;
    }
    this.setData({
      p: {
        id: p.id,
        name: p.name,
        cityName: p.cityName || '',
        cityCode: p.cityCode || '',
        district: p.district || '',
        type: p.type || '',
        level: p.level || '',
        lvlCls: p.level === '高端为主' ? 'he' : p.level === '高端+基础' ? 'hem' : '',
        intro: core.stripTags(p.intro),
      },
      ents: (p.enterprises || []).map((e, i) => ({
        i,
        name: e.name,
        products: String(e.products || '').slice(0, 38),
        high: !!e.high,
        verify: !!e.verify,
      })),
      dataDate: (core.D.parks && core.D.parks.updated_at_text) || '',
    });

    wx.setNavigationBarTitle({ title: p.name });
  },

  go(e) {
    const url = e.currentTarget.dataset.url;
    if (url) wx.navigateTo({ url });
  },

  onShareAppMessage() {
    const p = this.data.p;
    return {
      title: p ? p.name : '山东化工园区',
      path: p ? '/pages/park/park?id=' + p.id : '/pages/parks/parks',
    };
  },
});
