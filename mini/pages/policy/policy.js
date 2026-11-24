const core = require('../../utils/core.js');
const store = require('../../utils/store.js');

Page({
  data: {
    p: null,
    impactHint: '',
    faved: false,
    disclaimer: core.DISCLAIMER,
  },

  onLoad(options) {
    const id = options.id;
    const p = ((core.D.policies && core.D.policies.items) || []).filter(
      (x) => String(x.id) === String(id)
    )[0];

    if (!p) {
      this.setData({ p: null });
      return;
    }

    // 打开即记为「已读」，与 web 版一致
    store.add('read', 'pol:' + id);

    this.setData({
      p: {
        id: p.id,
        title: p.title,
        level: p.level || '',
        org: p.org || '',
        date: p.date || core.dateStr(p.ts) || '—',
        impact: p.impact || '',
        url: p.url || '',
      },
      impactHint: p.impact_src === 'rule' ? '按标题关键词自动归类，仅供参考。' : '',
      faved: store.has('fav', 'pol:' + id),
    });

    wx.setNavigationBarTitle({ title: '政策详情' });
  },

  /** 小程序不能直接开政府网站（业务域名校验过不了），只能复制链接让用户去浏览器打开 */
  onCopy() {
    const url = this.data.p && this.data.p.url;
    if (!url) return;
    wx.setClipboardData({
      data: url,
      success: () => {
        wx.showModal({
          title: '链接已复制',
          content: '微信内不能直接打开政府网站。请打开手机浏览器，粘贴访问原文。',
          showCancel: false,
          confirmText: '知道了',
        });
      },
    });
  },

  onFav() {
    const p = this.data.p;
    if (!p) return;
    store.toggle('fav', 'pol:' + p.id);
    const on = store.has('fav', 'pol:' + p.id);
    this.setData({ faved: on });
    wx.showToast({ title: on ? '已收藏' : '已取消', icon: 'none' });
  },

  onShareAppMessage() {
    const p = this.data.p;
    return {
      title: p ? p.title : '化工政策',
      path: p ? '/pages/policy/policy?id=' + p.id : '/pages/policies/policies',
    };
  },
});
