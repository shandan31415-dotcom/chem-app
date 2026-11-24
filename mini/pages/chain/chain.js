const core = require('../../utils/core.js');

Page({
  data: {
    s: null,
    stages: [],
    cats: [],
    disclaimer: core.DISCLAIMER,
  },

  onLoad(options) {
    this.build(options.key);
  },

  build(key) {
    const stages = core.chainStages();
    const s = stages.filter((x) => x.key === key)[0];
    if (!s) {
      this.setData({ s: null });
      return;
    }

    this.setData({
      s: {
        key: s.key,
        name: s.name,
        short: s.short,
        count: (s.cats || []).length,
        desc: core.stripTags(s.desc),
      },
      stages: stages.map((x) => ({
        key: x.key,
        short: x.short,
        count: (x.cats || []).length,
        on: x.key === key,
      })),
      cats: (s.cats || [])
        .map((id) => core.catById(id))
        .filter(Boolean)
        .map((c) => ({ id: c.id, name: c.name, one_line: c.one_line || '' })),
    });

    wx.setNavigationBarTitle({ title: s.short + ' · 产业链' });
  },

  /** 段内切换：原地换数据，不叠页面栈 */
  switchStage(e) {
    const key = e.currentTarget.dataset.key;
    if (key && (!this.data.s || key !== this.data.s.key)) this.build(key);
  },

  go(e) {
    const url = e.currentTarget.dataset.url;
    if (url) wx.navigateTo({ url });
  },

  onShareAppMessage() {
    const s = this.data.s;
    return {
      title: s ? s.name + ' · 化工产业链' : '化工产业链',
      path: s ? '/pages/chain/chain?key=' + s.key : '/pages/cats/cats',
    };
  },
});
