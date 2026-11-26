const core = require('../../utils/core.js');
const store = require('../../utils/store.js');
const live = require('../../utils/live.js');

/* 大白话也得搜得到：文件里写「生态环境部」，人嘴上说的是「环保」 */
const POL_SYN = {
  环保: ['环境', '生态', '排污', '污染'],
  安全: ['安全生产', '应急', '危化'],
  补贴: ['奖补', '补助', '资金', '支持'],
  园区: ['化工园区', '扩区', '调区'],
  能耗: ['节能', '双碳', '碳', '能效'],
  投资: ['项目', '备案', '核准', '审批'],
};

const TAG_ORDER = ['绿色低碳', '碳市场', '安全环保', '产业政策'];

Page({
  data: {
    q: '',
    level: '国家级',
    levelCount: { '国家级': 0, '山东省': 0 },
    tag: '',
    tagList: [],
    updatedText: '',
    levels: [],
    list: [],
    resultCount: 0,
    fromCloud: false,
    disclaimer: core.DISCLAIMER,
  },

  onLoad() {
    this.rebuild();
    // 云端快照通常晚于首屏几百毫秒到达，到了就重绘一次
    this._off = live.onUpdate(() => this.rebuild());
  },

  onShow() {
    this.rebuild();
  },

  onUnload() {
    if (this._off) this._off();
  },

  /* 下拉刷新：手动催一下云端（绕过 10 分钟冷却） */
  onPullDownRefresh() {
    live.refresh().then(() => {
      this.rebuild();
      wx.stopPullDownRefresh();
      const st = live.ready();
      wx.showToast({
        title: st.source === 'cloud' ? '已同步最新' : '当前为离线数据',
        icon: 'none',
      });
    });
  },

  rebuild() {
    const items = (core.D.policies && core.D.policies.items) || [];
    const levels = ['国家级', '山东省'].map((lv) => ({
      lv,
      count: items.filter((p) => p.level === lv).length,
    }));
    const lc = { '国家级': 0, '山东省': 0 };
    items.forEach((p) => { lc[p.level] = (lc[p.level] || 0) + 1; });

    // 主题标签：只列出当前层级里真实存在的，数量为 0 的不占位置
    const scope = items.filter((p) => p.level === this.data.level);
    const tagList = TAG_ORDER.map((t) => ({
      t,
      count: scope.filter((p) => (p.tags || []).indexOf(t) >= 0).length,
    })).filter((x) => x.count > 0);

    const st = live.ready();
    this.setData({
      levels,
      levelCount: lc,
      tagList,
      tag: tagList.some((x) => x.t === this.data.tag) ? this.data.tag : '',
      fromCloud: st.source === 'cloud' || st.source === 'cache',
      updatedText: (core.D.policies && core.D.policies.updated_at_text) || '',
    });
    this.paint();
  },

  paint() {
    const items = (core.D.policies && core.D.policies.items) || [];
    const q = this.data.q.trim().toLowerCase();

    let list = [];
    if (q) {
      const words = [[q]];
      Object.keys(POL_SYN).forEach((k) => {
        if (q.indexOf(k) >= 0) words.push(POL_SYN[k]);
      });
      list = items.filter((p) => {
        const hay = [p.title, p.org, p.impact, p.level].join(' ').toLowerCase();
        return words.some((ws) => ws.some((w) => w && hay.indexOf(w) >= 0));
      });
    } else {
      const tag = this.data.tag;
      list = items.filter(
        (p) => p.level === this.data.level && (!tag || (p.tags || []).indexOf(tag) >= 0)
      );
    }

    this.setData({
      resultCount: list.length,
      list: list.map((p) => ({
        id: p.id,
        title: p.title,
        org: p.org || '',
        level: p.level || '',
        tags: p.tags || [],
        date: p.date || core.dateStr(p.ts),
        read: store.has('read', 'pol:' + p.id),
      })),
    });
  },

  onInput(e) {
    this.setData({ q: e.detail.value }, () => this.paint());
  },

  clearQ() {
    this.setData({ q: '' }, () => this.paint());
  },

  onLevel(e) {
    this.setData({ level: e.currentTarget.dataset.lv, q: '', tag: '' }, () => this.rebuild());
  },

  onTag(e) {
    const t = e.currentTarget.dataset.t;
    this.setData({ tag: this.data.tag === t ? '' : t }, () => this.paint());
  },

  go(e) {
    const id = e.currentTarget.dataset.id;
    wx.navigateTo({ url: '/pages/policy/policy?id=' + id });
  },

  onShareAppMessage() {
    return { title: '化工政策原文汇总', path: '/pages/policies/policies' };
  },
});
