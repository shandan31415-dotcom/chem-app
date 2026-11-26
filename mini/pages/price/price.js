const core = require('../../utils/core.js');
const store = require('../../utils/store.js');

const PERIODS = [
  { d: 30, n: '30 天' },
  { d: 90, n: '90 天' },
  { d: 250, n: '250 天' },
];

Page({
  data: {
    p: null,
    periods: PERIODS,
    cur: 30,
    label: '',
    stats: null,
    faved: false,
    hasChart: false,
    histSrc: '',
    disclaimer: core.DISCLAIMER,
  },

  onLoad(options) {
    const name = decodeURIComponent(options.name || '');
    const p = core.priceByName(name);
    if (!p) {
      this.setData({ p: null });
      return;
    }
    const c = core.pct(p.chg);
    const rows = this.rowsOf(name);

    let stats = null;
    if (rows.length > 20) {
      const last = rows[rows.length - 1][1];
      const ago = rows[Math.max(0, rows.length - 21)][1];
      const ch30 = ((last - ago) / ago) * 100;
      const slice = rows.slice(-30).map((r) => r[1]);
      stats = {
        chg: (ch30 >= 0 ? '+' : '') + ch30.toFixed(2) + '%',
        cls: ch30 >= 0 ? 'up' : 'down',
        hi: core.px(Math.max.apply(null, slice)),
        lo: core.px(Math.min.apply(null, slice)),
      };
    }

    this.setData({
      p: {
        name: p.name,
        code: p.code || '',
        ex: p.ex || '',
        group: p.group || '',
        price: core.px(p.price),
        chg: c.t,
        cls: c.c,
        src: p.src || '',
        amt:
          p.chg_amt === null || p.chg_amt === undefined
            ? ''
            : (p.chg_amt > 0 ? '+' : '') + core.px(p.chg_amt),
      },
      stats,
      hasChart: rows.length > 1,
      histSrc: this.histSourceOf(name),
      faved: store.has('fav', 'px:' + name),
    });

    this.priceName = name;
    wx.setNavigationBarTitle({ title: name });

    if (rows.length > 1) {
      // 等布局稳定后再取 canvas 尺寸
      setTimeout(() => this.draw(), 60);
    }
  },

  rowsOf(name) {
    const s = core.D.hist && core.D.hist.series ? core.D.hist.series[name] : null;
    return s || [];
  },

  histSourceOf(name) {
    const m = (core.D.hist && core.D.hist.sources) || {};
    return m[name] || '';
  },

  onPeriod(e) {
    const d = Number(e.currentTarget.dataset.d);
    if (d === this.data.cur) return;
    this.setData({ cur: d }, () => this.draw());
  },

  draw() {
    const name = this.priceName;
    const all = this.rowsOf(name);
    if (!all.length) return;
    const rows = all.slice(-this.data.cur);

    this.setData({ label: '近 ' + rows.length + ' 日' });

    wx.createSelectorQuery()
      .in(this)
      .select('#chart')
      .fields({ node: true, size: true })
      .exec((res) => {
        if (!res || !res[0] || !res[0].node) return;
        const canvas = res[0].node;
        const ctx = canvas.getContext('2d');
        const info = wx.getWindowInfo ? wx.getWindowInfo() : wx.getSystemInfoSync();
        const dpr = info.pixelRatio || 2;
        const W = res[0].width;
        const H = res[0].height;

        canvas.width = W * dpr;
        canvas.height = H * dpr;
        ctx.scale(dpr, dpr);
        ctx.clearRect(0, 0, W, H);

        const padL = 8;
        const padR = 8;
        const padT = 12;
        const padB = 18;
        const cw = W - padL - padR;
        const chh = H - padT - padB;

        const vals = rows.map((r) => r[1]);
        let min = Math.min.apply(null, vals);
        let max = Math.max.apply(null, vals);
        if (max === min) {
          max += 1;
          min -= 1;
        }
        const span = max - min;
        min -= span * 0.08;
        max += span * 0.08;

        const X = (i) => padL + (rows.length === 1 ? cw / 2 : (cw * i) / (rows.length - 1));
        const Y = (v) => padT + chh - ((v - min) / (max - min)) * chh;

        // 横向参考线
        ctx.strokeStyle = '#f0f2f5';
        ctx.lineWidth = 1;
        for (let g = 0; g <= 3; g++) {
          const y = padT + (chh * g) / 3;
          ctx.beginPath();
          ctx.moveTo(padL, y);
          ctx.lineTo(W - padR, y);
          ctx.stroke();
        }

        const up = vals[vals.length - 1] >= vals[0];
        const line = up ? '#e03131' : '#0ca678';

        // 面积
        const grad = ctx.createLinearGradient(0, padT, 0, padT + chh);
        grad.addColorStop(0, up ? 'rgba(224,49,49,0.16)' : 'rgba(12,166,120,0.16)');
        grad.addColorStop(1, 'rgba(255,255,255,0)');
        ctx.beginPath();
        ctx.moveTo(X(0), Y(vals[0]));
        for (let i = 1; i < vals.length; i++) ctx.lineTo(X(i), Y(vals[i]));
        ctx.lineTo(X(vals.length - 1), padT + chh);
        ctx.lineTo(X(0), padT + chh);
        ctx.closePath();
        ctx.fillStyle = grad;
        ctx.fill();

        // 折线
        ctx.beginPath();
        ctx.moveTo(X(0), Y(vals[0]));
        for (let i = 1; i < vals.length; i++) ctx.lineTo(X(i), Y(vals[i]));
        ctx.strokeStyle = line;
        ctx.lineWidth = 1.6;
        ctx.lineJoin = 'round';
        ctx.stroke();

        // 末点
        const lx = X(vals.length - 1);
        const ly = Y(vals[vals.length - 1]);
        ctx.beginPath();
        ctx.arc(lx, ly, 2.8, 0, Math.PI * 2);
        ctx.fillStyle = line;
        ctx.fill();

        // 首末日期
        ctx.fillStyle = '#a8aeb8';
        ctx.font = '10px sans-serif';
        ctx.textBaseline = 'top';
        ctx.textAlign = 'left';
        ctx.fillText(rows[0][0], padL, padT + chh + 5);
        ctx.textAlign = 'right';
        ctx.fillText(rows[rows.length - 1][0], W - padR, padT + chh + 5);
      });
  },

  onFav() {
    const name = this.priceName;
    if (!name) return;
    store.toggle('fav', 'px:' + name);
    const on = store.has('fav', 'px:' + name);
    this.setData({ faved: on });
    wx.showToast({ title: on ? '已收藏' : '已取消', icon: 'none' });
  },

  onShareAppMessage() {
    const p = this.data.p;
    return {
      title: p ? p.name + ' 参考价' : '化工市场参考价',
      path: p ? '/pages/price/price?name=' + encodeURIComponent(p.name) : '/pages/prices/prices',
    };
  },
});
