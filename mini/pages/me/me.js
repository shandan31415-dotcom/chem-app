const core = require('../../utils/core.js');
const store = require('../../utils/store.js');
const cfg = require('../../utils/config.js');
const fix = require('../../utils/fix.js');

Page({
  data: {
    learned: 0,
    learnedTotal: 0,
    read: 0,
    readTotal: 0,
    fav: 0,
    dataDate: '',
    statText: '',
    disclaimer: core.DISCLAIMER,
    fixTitle: cfg.FIX_TITLE,
    holder: cfg.HOLDER,
    icp: cfg.ICP_NO,
  },

  onShow() {
    this.refresh();
  },

  refresh() {
    const c = store.counts();
    const T = core.totals();
    const nCat = (core.D.cats.items || []).length;
    this.setData({
      statText: T.parks + ' 园区 / ' + T.ents + ' 企业 / ' + nCat + ' 品类',
      learned: c.learned,
      learnedTotal: (core.D.cats.items || []).length,
      read: c.read,
      readTotal: (core.D.policies.items || []).length,
      fav: c.fav,
      dataDate: (core.D.meta && core.D.meta.updated_at_text) || '',
    });
  },

  /** 导出：小程序没有下载目录，改为复制 JSON 到剪贴板，粘到备忘录/文件传输助手即可 */
  onExport() {
    const text = store.exportJSON();
    wx.setClipboardData({
      data: text,
      success: () => {
        wx.showModal({
          title: '已复制备份',
          content: '备份内容已复制到剪贴板。建议粘贴到「文件传输助手」或备忘录留存，换手机时再复制回来点「导入恢复」。',
          showCancel: false,
          confirmText: '知道了',
        });
      },
    });
  },

  onImport() {
    wx.getClipboardData({
      success: (res) => {
        let obj = null;
        try {
          obj = JSON.parse(res.data);
        } catch (e) {
          wx.showModal({ title: '导入失败', content: '剪贴板里不是可读的备份内容。', showCancel: false });
          return;
        }
        if (!obj || typeof obj !== 'object') {
          wx.showModal({ title: '导入失败', content: '剪贴板里不是可读的备份内容。', showCancel: false });
          return;
        }
        let r;
        try {
          r = store.mergeImport(obj);
        } catch (e) {
          wx.showModal({ title: '导入失败', content: e.message || '备份格式不正确', showCancel: false });
          return;
        }
        this.refresh();
        wx.showModal({
          title: '恢复完成',
          content:
            '新增 品类 ' + r.learned + ' · 已读 ' + r.read + ' · 收藏 ' + r.fav +
            '。导入是合并，不会冲掉现有记录。',
          showCancel: false,
        });
      },
      fail: () => {
        wx.showModal({ title: '读取失败', content: '拿不到剪贴板内容，请重试。', showCancel: false });
      },
    });
  },

  onClear() {
    wx.showModal({
      title: '确认清空',
      content: '确定清空本机的已学、已读、收藏？此操作不可恢复。',
      confirmColor: '#e03131',
      success: (res) => {
        if (!res.confirm) return;
        store.clear();
        this.refresh();
        wx.showToast({ title: '已清空', icon: 'success' });
      },
    });
  },

  onFix() {
    fix.showFixModal('');
  },

  onSources() {
    fix.showSources();
  },

  onShareAppMessage() {
    return { title: '化工产业地图 · 山东版', path: '/pages/parks/parks' };
  },
});
