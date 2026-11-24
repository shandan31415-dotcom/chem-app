const core = require('../../utils/core.js');
const store = require('../../utils/store.js');
const fix = require('../../utils/fix.js');

Page({
  data: {
    e: null,
    favKey: '',
    faved: false,
    cats: [],
    city: null,
  },

  onLoad(options) {
    let e = null;
    let city = null;
    let park = null;
    let favKey = '';

    if (options.pid !== undefined) {
      park = core.parkById(options.pid);
      if (park) {
        e = (park.enterprises || [])[Number(options.i || 0)];
        city = core.cityByCode(park.cityCode);
        favKey = 'ent:' + options.pid + ':' + (options.i || 0);
      }
    } else if (options.cid !== undefined) {
      city = core.cityByCode(options.cid);
      if (city) {
        e = (city.enterprises || [])[Number(options.i || 0)];
        favKey = 'ent:c' + options.cid + ':' + (options.i || 0);
      }
    }

    if (!e) {
      this.setData({ e: null });
      return;
    }

    const cats = (e.cats || []).map(core.catById).filter(Boolean).map((c) => ({
      id: c.id,
      name: c.name,
      one_line: c.one_line || '',
    }));

    this.setData({
      e: {
        name: e.name,
        products: e.products || '',
        note: e.note || '',
        high: !!e.high,
        verify: !!e.verify,
        sub: (park ? park.name + ' · ' : '') + (city ? city.name : ''),
      },
      cats,
      city: city ? { code: city.code, name: city.name, tagline: core.stripTags(city.tagline) } : null,
      favKey,
      faved: store.has('fav', favKey),
    });

    wx.setNavigationBarTitle({ title: e.name });
  },

  go(e) {
    const url = e.currentTarget.dataset.url;
    if (url) wx.navigateTo({ url });
  },

  onFav() {
    if (!this.data.favKey) return;
    store.toggle('fav', this.data.favKey);
    const on = store.has('fav', this.data.favKey);
    this.setData({ faved: on });
    wx.showToast({ title: on ? '已收藏' : '已取消', icon: 'none' });
  },

  /** 企业名带上，对方发邮件时不用再说明是哪一条 */
  onFix() {
    const e = this.data.e;
    fix.showFixModal(e ? '需处理的条目：' + e.name + '（' + e.sub + '）' : '');
  },

  onShareAppMessage() {
    const e = this.data.e;
    return {
      title: e ? e.name : '化工企业',
      path: e ? '/pages/parks/parks' : '/pages/parks/parks',
    };
  },
});
