const core = require('../../utils/core.js');
const live = require('../../utils/live.js');

Page({
  data: {
    q: '',
    groups: [],
    total: 0,
    dataDate: '',
    disclaimer: core.DISCLAIMER,
  },

  onLoad() {
    this.paint('');
    this._off = live.onUpdate(() => this.paint(this.data.q));
  },

  onShow() {
    this.paint(this.data.q);
  },

  onUnload() {
    if (this._off) this._off();
  },

  onPullDownRefresh() {
    live.refresh().then(() => {
      this.paint(this.data.q);
      wx.stopPullDownRefresh();
      const st = live.ready();
      wx.showToast({
        title: st.source === 'cloud' ? '已同步最新' : '当前为离线数据',
        icon: 'none',
      });
    });
  },

  paint(q) {
    const key = String(q || '').trim().toLowerCase();
    let total = 0;
    const groups = [];
    ((core.D.prices && core.D.prices.groups) || []).forEach((g) => {
      const items = (g.items || [])
        .filter((i) => !key || i.name.toLowerCase().indexOf(key) >= 0 || String(i.code || '').toLowerCase().indexOf(key) >= 0)
        .map((i) => {
          const c = core.pct(i.chg);
          return {
            name: i.name,
            code: i.code || '',
            price: core.px(i.price),
            chg: c.t,
            cls: c.c,
          };
        });
      if (!items.length) return;
      total += items.length;
      groups.push({ name: g.name, count: items.length, items });
    });

    this.setData({
      q: q,
      groups,
      total,
      dataDate: (core.D.prices && core.D.prices.updated_at_text) || '',
    });
  },

  onInput(e) {
    this.paint(e.detail.value);
  },

  clearQ() {
    this.paint('');
  },

  go(e) {
    const name = e.currentTarget.dataset.name;
    wx.navigateTo({ url: '/pages/price/price?name=' + encodeURIComponent(name) });
  },

  onShareAppMessage() {
    return { title: '化工原料市场参考价', path: '/pages/prices/prices' };
  },
});
