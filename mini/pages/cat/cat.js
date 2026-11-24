const core = require('../../utils/core.js');
const store = require('../../utils/store.js');

const FIELDS = [
  ['成本锚', 'cost'],
  ['需求锚', 'demand'],
  ['供给格局', 'supply'],
  ['山东的位置', 'shandong'],
  ['流向', 'flow'],
  ['储运门槛', 'logistics'],
];

Page({
  data: {
    c: null,
    fields: [],
    stage: null,
    products: [],
    leaders: [],
    prices: [],
    priceHint: '',
  },

  onLoad(options) {
    const c = core.catById(options.id);
    if (!c) {
      this.setData({ c: null });
      return;
    }

    // 打开即记为「已学」，与 web 版一致
    store.add('learned', c.id);

    const ch = core.chainStageOf(c.id);
    const idx = ch ? core.chainStages().indexOf(ch) : -1;

    // 头部企业：能在山东名录里找到的直接跳过去，找不到的老实标「不在山东名录」
    const entIdx = core.buildIndex();
    const leaders = (c.leaders || []).map((l) => {
      const hit = entIdx.filter((x) => x.t === '企业' && x.n === l.name)[0];
      return {
        name: l.name,
        note: l.note || '',
        url: hit ? hit.url : '',
        where: hit ? hit.s : '',
      };
    });

    const prices = (c.price_links || [])
      .map((n) => {
        const p = core.priceByName(n);
        if (!p) return null;
        const cc = core.pct(p.chg);
        return { name: n, price: core.px(p.price), chg: cc.t, cls: cc.c };
      })
      .filter(Boolean);

    this.setData({
      c: {
        id: c.id,
        name: c.name,
        one_line: c.one_line || '',
      },
      fields: FIELDS.map(([k, key]) => ({ k, v: core.stripTags(c[key]) })),
      stage: ch ? { short: ch.short, desc: ch.desc || '', idx: idx >= 0 ? idx : 0 } : null,
      products: c.products || [],
      leaders,
      prices,
      priceHint: prices.length
        ? '这一项是该品类的同品种或成本锚的公开报价，不是这个品种本身的现货成交价。'
        : '',
    });

    wx.setNavigationBarTitle({ title: c.name });
  },

  go(e) {
    const url = e.currentTarget.dataset.url;
    if (url) wx.navigateTo({ url });
  },

  /** 省外/国外头部企业：回地图页搜它有没有山东据点 */
  searchEnt(e) {
    getApp().globalData.pendingQuery = e.currentTarget.dataset.n;
    wx.switchTab({ url: '/pages/parks/parks' });
  },

  onShareAppMessage() {
    const c = this.data.c;
    return {
      title: c ? c.name + ' · 六问速查' : '化工品类',
      path: c ? '/pages/cat/cat?id=' + c.id : '/pages/cats/cats',
    };
  },
});
