const core = require('../../utils/core.js');
const store = require('../../utils/store.js');

Page({
  data: {
    q: '',
    boardList: [],
    stages: [],
    chainFilter: '',
    groups: [],
    hits: [],
    total: 0,
    groupCount: 0,
    dataDate: '',
    disclaimer: core.DISCLAIMER,
  },

  onLoad() {
    const boards = (core.D.boards && core.D.boards.boards) || [];
    const stages = core.chainStages();
    this.setData({
      boardList: boards.map((b) => ({
        key: b.key,
        name: b.name,
        count: (b.cat_ids || []).length,
      })),
      stages: stages.map((s) => ({
        key: s.key,
        short: s.short,
        name: s.name,
        count: (s.cats || []).length,
      })),
      total: (core.D.cats.items || []).length,
      groupCount: (core.D.cats.groups || []).length,
      dataDate: (core.D.cats && core.D.cats.updated_at_text) || '',
    });
    this.paint();
  },

  onShow() {
    this.paint();
  },

  paint() {
    const q = this.data.q.trim().toLowerCase();
    const filter = this.data.chainFilter;

    if (q) {
      const hits = core.catSearch(q).map((c) => ({
        id: c.id,
        name: c.name,
        one_line: c.one_line || '',
      }));
      this.setData({ hits, groups: [] });
      return;
    }

    const stage = filter ? core.chainStages().filter((s) => s.key === filter)[0] : null;
    const groups = [];
    (core.D.cats.groups || []).forEach((g) => {
      let ids = g.items || [];
      if (stage) ids = ids.filter((id) => (stage.cats || []).indexOf(id) >= 0);
      if (!ids.length) return;
      const items = [];
      ids.forEach((id) => {
        const c = core.catById(id);
        if (!c) return;
        const ch = core.chainStageOf(c.id);
        const i = core.chainStages().indexOf(ch);
        items.push({
          id: c.id,
          name: c.name,
          one_line: c.one_line || '',
          chShort: ch ? ch.short : '',
          chIdx: i >= 0 ? i : 0,
          learned: store.has('learned', c.id),
        });
      });
      groups.push({ name: g.name, count: items.length, items });
    });

    this.setData({ groups, hits: [] });
  },

  onInput(e) {
    this.setData({ q: e.detail.value }, () => this.paint());
  },

  clearQ() {
    this.setData({ q: '' }, () => this.paint());
  },

  onChain(e) {
    const k = e.currentTarget.dataset.k || '';
    this.setData({ chainFilter: this.data.chainFilter === k ? '' : k }, () => this.paint());
  },

  go(e) {
    const url = e.currentTarget.dataset.url;
    if (url) wx.navigateTo({ url });
  },

  onShareAppMessage() {
    return { title: '73 个化工品类 · 六问速查', path: '/pages/cats/cats' };
  },
});
