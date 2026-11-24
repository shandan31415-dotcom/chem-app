const store = require('./utils/store.js');
const live = require('./utils/live.js');

App({
  onLaunch() {
    store.load();
    // 云端数据是「增强项」，异步拉，拉不到就用包内数据，绝不阻塞启动
    live.init();
    live.pull().then((st) => {
      this.globalData.liveSource = st.source;
      this.globalData.liveUpdatedText = st.updatedText;
      this.globalData.dataDate = st.updatedText || '';
    });
  },

  globalData: {
    /** 数据整理日期，页脚统一用 */
    dataDate: '',
    /** 当前数据来自哪里：cloud / cache / static */
    liveSource: 'static',
    liveUpdatedText: '',
    /** 跨 tab 传参：switchTab 不能带 query，用这里中转（eg. 城市页点品种 → 地图页搜索） */
    pendingQuery: null,
  },
});
