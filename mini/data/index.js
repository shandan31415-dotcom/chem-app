/**
 * 数据入口。
 * 本目录下所有 *.js 都由 mini/scripts/build_data.py 从 chem-app/data/*.json 生成，
 * 不要手改，也不要把数据双写到两处。
 */
module.exports = {
  parks: require('./parks.js'),
  cats: require('./categories.js'),
  boards: require('./boards.js'),
  chain: require('./chain.js'),
  industry: require('./industry.js'),
  sdmap: require('./sdmap.js'),
  prices: require('./prices.js'),
  hist: require('./hist.js'),
  policies: require('./policies.js'),
  meta: require('./meta.js'),
  mapmeta: require('./mapmeta.js'),
};
