const core = require('../../utils/core.js');

Page({
  data: {
    b: null,
    leaders: [],
    cats: [],
    source: '',
    disclaimer: core.DISCLAIMER,
  },

  onLoad(options) {
    const b = core.boardByKey(options.key);
    if (!b) {
      this.setData({ b: null });
      return;
    }

    const entIdx = core.buildIndex();
    const cats = (b.cat_ids || [])
      .map((id) => core.catById(id))
      .filter(Boolean)
      .map((c) => ({ id: c.id, name: c.name, one_line: c.one_line || '' }));

    this.setData({
      b: {
        key: b.key,
        name: b.name,
        count: (b.cat_ids || []).length,
        intro: core.stripTags(b.intro),
      },
      leaders: (b.leaders || []).map((name) => {
        const hit = entIdx.filter((x) => x.t === '企业' && x.n === name)[0];
        return { name, url: hit ? hit.url : '', where: hit ? hit.s : '' };
      }),
      cats,
      source: (core.D.boards && core.D.boards.source) || '人工整理',
    });

    wx.setNavigationBarTitle({ title: b.name + ' · 七大板块' });
  },

  go(e) {
    const url = e.currentTarget.dataset.url;
    if (url) wx.navigateTo({ url });
  },

  onShareAppMessage() {
    const b = this.data.b;
    return {
      title: b ? b.name + ' · 山东化工七大板块' : '山东化工七大板块',
      path: b ? '/pages/board/board?key=' + b.key : '/pages/cats/cats',
    };
  },
});
