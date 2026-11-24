/**
 * 信息更正 / 删除的入口，企业详情页与「我的」页共用。
 *
 * 法律依据：《民法典》第 1195 条「通知—删除」规则 ——
 * 网络服务提供者接到侵权通知后及时采取必要措施的，不承担赔偿责任。
 * 所以关键不是"有没有收录"，而是"有没有一个能被通知到的通道，且收到就处理"。
 */
const cfg = require('./config.js');

function showFixModal(extra) {
  const lines = [];
  if (extra) lines.push(extra);
  lines.push(cfg.FIX_DESC);
  lines.push('联系邮箱：' + cfg.CONTACT.email);
  if (cfg.CONTACT.phone) lines.push('联系电话：' + cfg.CONTACT.phone);

  wx.showModal({
    title: cfg.FIX_TITLE,
    content: lines.join('\n\n'),
    confirmText: '复制邮箱',
    cancelText: '关闭',
    success(res) {
      if (!res.confirm) return;
      wx.setClipboardData({
        data: cfg.CONTACT.email,
        success() {
          wx.showToast({ title: '邮箱已复制', icon: 'none' });
        },
      });
    },
  });
}

function showSources() {
  const body = cfg.SOURCES.map((s) => '· ' + s.k + '：' + s.v).join('\n');
  wx.showModal({
    title: '信息来源说明',
    content: body,
    showCancel: false,
    confirmText: '知道了',
  });
}

module.exports = { showFixModal, showSources };
