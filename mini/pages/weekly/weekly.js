/**
 * 政策周报 —— 给会员转发用的那一页。
 *
 * 会员真正需要的是「这周有什么新政策」，不是「你自己去查」。这一页把
 * 最近的政策按主题归拢成一段，既可以整页转发，也可以一键复制成纯文字发到群里。
 *
 * 数据直接在本地算，不经过云函数：政策列表本来就已经在 core.D 里了，
 * 再让服务端生成一份纯属重复劳动，还多一次失败的可能。
 *
 * 一个细节：周一早上打开时「本周」往往只有一两条（甚至零条），
 * 所以不足 3 条时自动退成「近 7 天」，免得用户以为系统坏了。
 */
const core = require('../../utils/core.js');
const cfg = require('../../utils/config.js');
const live = require('../../utils/live.js');

const DAY = 86400;
const ORDER = ['绿色低碳', '碳市场', '安全环保', '产业政策', '其他'];

Page({
  data: {
    mode: 'week',
    rangeText: '',
    startText: '',
    endText: '',
    total: 0,
    groups: [],
    updatedText: '',
    holder: cfg.HOLDER,
    disclaimer: core.DISCLAIMER,
  },

  onLoad() {
    this.build();
    // 云端数据可能在页面画完之后才到，到了重算一次
    this._off = live.onUpdate(() => this.build());
  },

  onUnload() {
    if (this._off) this._off();
  },

  build() {
    const items = (core.D.policies && core.D.policies.items) || [];
    const now = Math.floor(Date.now() / 1000);

    // 本周一零点（周记为一周之始）
    const d = new Date();
    d.setHours(0, 0, 0, 0);
    const dow = (d.getDay() + 6) % 7;
    const weekStart = Math.floor(d.getTime() / 1000) - dow * DAY;

    let mode = 'week';
    let from = weekStart;
    let picked = items.filter((x) => (x.ts || 0) >= from);

    if (picked.length < 3) {
      mode = '7d';
      from = now - 7 * DAY;
      picked = items.filter((x) => (x.ts || 0) >= from);
    }

    const startText = core.dateStr(from);
    const endText = core.dateStr(now);
    const rangeText = mode === 'week' ? '本周' : '近 7 天';

    // 按主题归组。一份文件可能同时挂两个主题，所以各组条数加起来会大于总数。
    const bucket = {};
    picked.forEach((x) => {
      const tags = x.tags && x.tags.length ? x.tags : ['其他'];
      tags.forEach((t) => {
        if (!bucket[t]) bucket[t] = [];
        bucket[t].push(x);
      });
    });

    const groups = ORDER.filter((t) => bucket[t] && bucket[t].length).map((t) => ({
      title: t,
      count: bucket[t].length,
      items: bucket[t].slice(0, 8).map((x) => ({
        id: x.id,
        title: x.title,
        org: x.org || '',
        level: x.level || '',
        date: x.date || core.dateStr(x.ts),
      })),
      more: Math.max(0, bucket[t].length - 8),
    }));

    this.setData({
      mode: mode,
      rangeText: rangeText,
      startText: startText,
      endText: endText,
      total: picked.length,
      groups: groups,
      updatedText: (core.D.policies && core.D.policies.updated_at_text) || '',
    });
  },

  go(e) {
    const id = e.currentTarget.dataset.id;
    if (!id) return;
    wx.navigateTo({ url: '/pages/policy/policy?id=' + id });
  },

  /** 复制成纯文字，直接贴到协会的会员群里 */
  copyText() {
    const lines = [];
    lines.push('【化工政策周报】' + this.data.startText + ' ~ ' + this.data.endText);
    if (!this.data.total) {
      lines.push('');
      lines.push('这段时间没有新的政策文件发布。');
    } else {
      lines.push('新增 ' + this.data.total + ' 条，按主题整理如下：');
      this.data.groups.forEach((g) => {
        lines.push('');
        lines.push('◆ ' + g.title + '（' + g.count + ' 条）');
        g.items.forEach((p) => {
          lines.push('· ' + p.title);
          lines.push('  ' + p.org + '　' + p.date);
        });
        if (g.more) lines.push('  ……另有 ' + g.more + ' 条，见小程序');
      });
    }
    lines.push('');
    lines.push('—— ' + this.data.holder);
    lines.push('（政策原文请以政府网站为准，本清单仅作索引）');

    wx.setClipboardData({
      data: lines.join('\n'),
      success: () => {
        wx.showToast({ title: '已复制，可直接发群', icon: 'none' });
      },
    });
  },

  onShareAppMessage() {
    const t = this.data.total;
    return {
      title: t
        ? this.data.rangeText + '化工政策 ' + t + ' 条（' + this.data.holder + '）'
        : this.data.rangeText + '化工政策周报',
      path: '/pages/weekly/weekly',
    };
  },
});
