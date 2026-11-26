/**
 * 政策采集 —— 跑在云函数里，不经过 GitHub。
 *
 * 原来这段逻辑在 GitHub Actions 上跑（Python，chem-app/scripts/fetch_all.py）。
 * 问题是 Actions 的机器在美国，连国内政府站又慢又容易被断，而数据还得再
 * 绕一圈存到 Pages 上等云函数来取。整条链路三处都依赖跨境网络。
 *
 * 现在把它搬进腾讯云：国内机房直连国内政府站，抓完直接写云数据库。
 * GitHub 只剩一个用途——云库被清空时，拿它的历史快照兜一次底。
 *
 * 判定口径与 Python 版保持一致，改规则时两边要同步改：
 *   1) 标题必须含公文类型词（通知/办法/方案…）
 *   2) 排除解读稿、答记者问、人事表彰类
 *   3) 强相关（含化工行业词）→ 收
 *   4) 强主题（碳市场/零碳工厂…）→ 收，哪怕标题写的是钢铁水泥
 *   5) 弱主题（绿色工厂名单类）→ 收，但先被非化行业词挡一道
 *   6) 行业属性明确的源（省生态环境厅、部令规章等）→ 命中中相关词也收
 */
const { getText, mapLimit } = require('./http');

/* 每个源只抓首页。政策不像新闻滚动那么快，一天新增极少超过 10 条；
   云库里已有历史存量，增量累积即可。多抓一页就多一轮跨境请求的时间。 */
const SOURCES = [
  {
    level: '山东省',
    org: '山东省工业和信息化厅',
    paginate: 'query',
    url: 'http://gxt.shandong.gov.cn/col/col103862/index.html',
    pattern: 'href="([^"]*?/art/\\d{4}/\\d{1,2}/\\d{1,2}/art_\\d+_\\d+\\.html)"[^>]*>\\s*([^<]{8,90}?)\\s*</a>',
  },
  {
    level: '山东省',
    org: '山东省工业和信息化厅',
    paginate: 'query',
    url: 'http://gxt.shandong.gov.cn/col/col103863/index.html',
    pattern: 'href="([^"]*?/art/\\d{4}/\\d{1,2}/\\d{1,2}/art_\\d+_\\d+\\.html)"[^>]*>\\s*([^<]{8,90}?)\\s*</a>',
  },
  {
    level: '国家级',
    org: '国家发展改革委',
    allow: '/xxgk/zcfb/',
    url: 'https://www.ndrc.gov.cn/xxgk/zcfb/ghxwj/',
    pattern: 'href="([^"]*?/t\\d{8}_\\d+\\.html)"[^>]*>\\s*([^<]{8,90}?)\\s*</a>',
  },
  {
    level: '国家级',
    org: '国家发展改革委',
    allow: '/xxgk/zcfb/',
    url: 'https://www.ndrc.gov.cn/xxgk/zcfb/tz/',
    pattern: 'href="([^"]*?/t\\d{8}_\\d+\\.html)"[^>]*>\\s*([^<]{8,90}?)\\s*</a>',
  },
  {
    level: '国家级',
    org: '国家发展改革委',
    allow: '/xxgk/zcfb/',
    url: 'https://www.ndrc.gov.cn/xxgk/zcfb/fzggwl/',
    pattern: 'href="([^"]*?/t\\d{8}_\\d+\\.html)"[^>]*>\\s*([^<]{8,90}?)\\s*</a>',
  },
  {
    level: '国家级',
    org: '生态环境部',
    url: 'https://www.mee.gov.cn/zcwj/',
    pattern: 'href="([^"]*?/t\\d{8}_\\d+\\.s?html)"[^>]*>\\s*([^<]{8,90}?)\\s*</a>',
  },
  {
    level: '国家级',
    org: '生态环境部',
    industry: true,
    url: 'https://www.mee.gov.cn/zcwj/bwj/',
    med: ['园区', '建设项目', '环境影响评价', '排污许可', '危险废物', '固体废物',
      '名录', '新污染物', '两高', '碳排放', '产能'],
    pattern: 'href="([^"]*?/t\\d{8}_\\d+\\.s?html)"[^>]*>\\s*([^<]{8,90}?)\\s*</a>',
  },
  {
    level: '山东省',
    org: '山东省生态环境厅',
    industry: true,
    referer: 'http://xxgk.sdein.gov.cn/',
    url: 'http://xxgk.sdein.gov.cn/zfwj/lhf/',
    pattern: 'href="([^"]*?t\\d{8}_\\d+\\.html)"[^>]*>\\s*([^<]{8,90}?)\\s*</a>',
  },
  {
    level: '山东省',
    org: '山东省生态环境厅',
    industry: true,
    referer: 'http://xxgk.sdein.gov.cn/',
    url: 'http://xxgk.sdein.gov.cn/zfwj/lhh/',
    pattern: 'href="([^"]*?t\\d{8}_\\d+\\.html)"[^>]*>\\s*([^<]{8,90}?)\\s*</a>',
  },
  {
    level: '国家级',
    org: '工业和信息化部原材料工业司',
    allow: '/jgsj/ycls/',
    url: 'https://www.miit.gov.cn/jgsj/ycls/index.html',
    pattern: 'href="([^"]*?/art/\\d{4}/art_[0-9a-f]+\\.html)"[^>]*?title="([^"]{8,90})"',
  },
  {
    level: '山东省',
    org: '山东省发展和改革委员会',
    industry: true,
    url: 'http://fgw.shandong.gov.cn/col/col333896/index.html',
    pattern: 'href="([^"]*?/art/\\d{4}/\\d{1,2}/\\d{1,2}/art_\\d+_\\d+\\.html)"[^>]*>\\s*([^<]{8,90}?)\\s*</a>',
  },
];

const KW_POLICY = ['化工', '石化', '化学', '炼化', '炼油', '氯碱', '化肥', '农药', '轮胎',
  '橡胶', '涂料', '塑料', '新材料', '危险化学品', '危化', '精细化工',
  '煤化工', '盐化工', '纯碱', '烧碱', '甲醇', '烯烃', '芳烃', '树脂',
  '氟化工', '硅材料', '锂电材料', '助剂', '石化行业', '化工园区', '焦化'];

const KW_POLICY_MED = ['园区', '产能', '两高', '重点行业', '制造业', '技改', '数智化',
  '数字化转型', '安全生产', '排污', '环评', '新污染物', '危险废物',
  '固废', '排放', '能耗', '碳达峰', '双碳', '许可', '储备',
  '环境影响评价', '建设项目', '名录', '绿色', '节能', '能效',
  '降碳', '循环', '清洁生产', '综合利用'];

const KW_POLICY_CROSS_STRONG = ['碳市场', '碳排放权', '碳交易', '碳配额', '碳足迹', '碳标签',
  '碳关税', 'CBAM', '零碳工厂', '零碳园区', '近零碳',
  '能耗双控', '节能降碳', '绿电', '绿证', '碳排放'];

const KW_POLICY_CROSS_WEAK = ['绿色工厂', '绿色制造', '绿色工业园区', '绿色供应链',
  '清洁生产', '循环经济', '资源综合利用', '再生资源', '工业固废'];

const KW_DOCTYPE = ['通知', '意见', '方案', '办法', '规划', '条例', '公告', '决定', '批复',
  '细则', '导则', '指南', '规定', '目录', '标准', '清单', '规则'];

const KW_POLICY_ADMIN_EXCL = ['答记者问', '一图读懂', '图解', '解读', '政策问答',
  '新闻发布会', '专访', '评论', '专家推荐', '职称', '表彰',
  '培训', '招聘'];

const KW_POLICY_EXCL = ['钢铁', '水泥', '玻璃', '陶瓷', '有色金属', '造纸', '印染', '核电',
  '农村', '宅基地', '土壤', '地下水', '生态保护', '自然保护区', '湿地',
  '草原', '海洋生态', '碳汇', '生态补偿', '火电', '核技术', '轨道交通',
  '机动车', '汽车', '纺织', '服装', '食品', '家电', '家具', '船舶',
  '航空', '医药', '冶炼', '人事',
  '表彰', '培训', '会议', '招聘'];

const TAGS = [
  ['绿色低碳', ['绿色工厂', '绿色制造', '绿色工业园区', '绿色供应链', '零碳', '近零碳',
    '节能', '能效', '降碳', '碳达峰', '双碳', '绿电', '绿证', '清洁生产',
    '循环经济', '资源综合利用', '再生资源', '节能审查', '碳排放评价',
    '领跑者', '低碳', '绿色化']],
  ['碳市场', ['碳市场', '碳排放权', '碳交易', '碳配额', '碳足迹', '碳标签', '碳关税',
    'CBAM', 'CCER', '自愿减排', '碳汇', '碳核算', '碳排放']],
  ['安全环保', ['危险化学品', '危化', '安全生产', '排污', '环评', '环境影响评价',
    '危险废物', '固废', '固体废物', '新污染物', '污染防治', '环境管理',
    '应急', '事故', '环保', '超低排放', '土壤污染', '化学物质',
    '生态环境标准', '环境标准']],
  ['产业政策', ['产业结构', '产能置换', '产能', '园区', '扩区', '新材料', '技改',
    '技术改造', '数字化转型', '智能制造', '揭榜挂帅', '规范条件', '准入',
    '目录', '规划', '计划', '实施方案', '行动方案',
    '奖补', '标杆', '稳增长', '清单', '储备', '保供', '审批', '投资']],
];

const IMPACTS = [
  [['化学物质', '名录', '登记'], '涉及化学物质名录与环境管理登记，影响新产品上市与进口合规'],
  [['奖补', '补贴', '数智化', '改造'], '涉及财政奖补与改造支持，符合条件的企业可申报'],
  [['投资', '项目管理', '审批'], '涉及化工项目投资管理与审批口径，影响新项目能不能落地'],
  [['稳增长', '行动方案', '发展规划', '实施方案'], '属于行业发展部署，方向性信号，具体支持看配套细则'],
  [['危险化学品', '危化'], '涉及危化品生产储存的合规要求，园区内相关企业要对照自查'],
  [['化工园区', '园区'], '涉及化工园区认定与管理口径，影响园内企业的准入与配套'],
  [['环保', '生态环境', '排放', '污染', '治理'], '涉及环保排放与治理要求，可能抬高技改与运行成本'],
  [['安全生产', '安全'], '涉及安全生产要求，影响装置运行、检修与验收安排'],
  [['产能', '置换', '新增'], '涉及产能置换与项目审批，影响在建与拟建装置的节奏'],
  [['淘汰', '限制', '禁止', '退出'], '涉及落后产能退出与限制类目录，影响存量装置能不能继续干'],
  [['标准', '规范', '指南', '导则'], '涉及标准与规范口径，可能改变下游采购与验收依据'],
  [['新材料', '高端', '精细化工'], '涉及高端新材料方向的支持口径，与品类升级相关'],
];

/* 失效状态：省发改委列表里每行带「有效 / 废止 / 失效」小字，
   抓到就存下来，前端提示「该文件已废止」，避免会员拿旧文件当依据。 */
const STATUS_WORDS = ['废止', '失效', '已修改', '已修订', '有效'];

const KEEP_MAX = 150;
const KEEP_YEARS = 12;

const ZW_RE = /[\u200b-\u200f\u2028\u2029\ufeff]/g;
const TAG_RE = /<[^>]*>/g;

function clean(s, limit) {
  if (!s) return '';
  let t = String(s).replace(TAG_RE, ' ');
  t = t
    .replace(/&nbsp;/g, ' ')
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#(\d+);/g, (m, d) => String.fromCharCode(Number(d)));
  t = t.replace(/[\r\n]/g, ' ');
  t = t.replace(ZW_RE, '');
  t = t.replace(/[（(]有效性[：:][^）)]*[）)]?\s*$/, '');
  t = t.replace(/\s+/g, ' ').trim();
  if (limit && t.length > limit) t = t.slice(0, limit).replace(/\s+$/, '') + '…';
  return t;
}

function relevant(title, src) {
  if (!KW_DOCTYPE.some((k) => title.indexOf(k) >= 0)) return false;
  if (KW_POLICY_ADMIN_EXCL.some((k) => title.indexOf(k) >= 0)) return false;
  if (title.indexOf('专家') >= 0 && ['推荐', '评选', '遴选', '征集'].some((k) => title.indexOf(k) >= 0)) {
    return false;
  }
  if (KW_POLICY.some((k) => title.indexOf(k) >= 0)) return true;
  if (KW_POLICY_CROSS_STRONG.some((k) => title.indexOf(k) >= 0)) return true;
  if (KW_POLICY_EXCL.some((k) => title.indexOf(k) >= 0)) return false;
  if (KW_POLICY_CROSS_WEAK.some((k) => title.indexOf(k) >= 0)) return true;
  const med = src.med || KW_POLICY_MED;
  if (src.industry && med.some((k) => title.indexOf(k) >= 0)) return true;
  return false;
}

function tagsOf(title) {
  const t = title || '';
  return TAGS.filter(([, kws]) => kws.some((k) => t.indexOf(k) >= 0)).map(([n]) => n);
}

function impactOf(title) {
  const t = title || '';
  for (const [kws, txt] of IMPACTS) {
    if (kws.some((k) => t.indexOf(k) >= 0)) return txt;
  }
  return '';
}

/** URL 里的日期。支持 2026/11/6、t20261106 两种写法，取不到返回 null */
function tsFromUrl(url) {
  let m = /(20\d{2})\/(\d{1,2})\/(\d{1,2})/.exec(url);
  if (!m) m = /(20\d{2})(\d{2})(\d{2})/.exec(url);
  if (!m) return null;
  const y = Number(m[1]);
  const mo = Number(m[2]);
  const d = Number(m[3]);
  if (mo < 1 || mo > 12 || d < 1 || d > 31) return null;
  // 政府文件的日期按北京时间的零点算，和已有数据保持一致
  return Math.floor(Date.UTC(y, mo - 1, d) / 1000) - 8 * 3600;
}

function pageUrl(src, i) {
  if (i === 0) return src.url;
  const mode = src.paginate || 'none';
  if (mode === 'query') return src.url + '?pageNum=' + (i + 1);
  if (mode === 'html') return src.url + 'index_' + i + '.html';
  if (mode === 'shtml') return src.url + 'index_' + i + '.shtml';
  return null;
}

/** 列表页 HTML → 候选条目 */
function parseList(html, src) {
  // 省发改委把标题写成 title="<!--articletitle-->"，注释里的 > 会截断匹配
  const h = html.replace(/<!--[\s\S]*?-->/g, '');
  const re = new RegExp(src.pattern, 'g');
  const out = [];
  let m;
  while ((m = re.exec(h)) !== null) {
    const href = m[1];
    const rawTitle = m[2];
    if (!href || !rawTitle) continue;
    const title = clean(rawTitle);
    if (!title || title.length < 8) continue;
    let url;
    try {
      url = new URL(href, src.url).href;
    } catch (e) {
      continue;
    }
    if (!/^https?:\/\//i.test(url)) continue;
    // 栏目白名单：发改委的列表页侧栏挂着「相关解读」，不挡的话
    // /xxgk/jd/jd/ 下的解读稿会被当成文件收进来（同一份文件的二次加工）。
    if (src.allow && url.indexOf(src.allow) < 0) continue;
    if (!relevant(title, src)) continue;
    out.push({ title: title, url: url, level: src.level, org: src.org });
  }
  return out;
}

/** 抓一个源的第一页 */
async function fetchSource(src) {
  const html = await getText(src.url, 6000, src.referer ? { Referer: src.referer } : null);
  return parseList(html, src);
}

const DEAD_MARKERS = ['页面不存在', '文件不存在', '网页不存在', '页面已删除', '已被删除',
  '404 Not Found', '404错误', '系统维护', '无法找到', '您访问的页面'];

/** 页面上的发布日期。政府站写法五花八门，按可靠度依次试三种 */
function dateFromPage(html) {
  const pats = [
    /发布[日时]期?[：:]\s*(?:<\/?[^>]*>\s*)*(20\d{2})[-/年.](\d{1,2})[-/月.](\d{1,2})/,
    /id="?pubDate"?[^>]*>\s*(20\d{2})[-/年.](\d{1,2})[-/月.](\d{1,2})/,
    /(20\d{2})[-/年.](\d{1,2})[-/月.](\d{1,2})/,
  ];
  for (const p of pats) {
    const m = p.exec(html);
    if (!m) continue;
    const y = Number(m[1]);
    const mo = Number(m[2]);
    const d = Number(m[3]);
    if (y < 2000 || y > 2100 || mo < 1 || mo > 12 || d < 1 || d > 31) continue;
    return Math.floor(Date.UTC(y, mo - 1, d) / 1000) - 8 * 3600;
  }
  return null;
}

/**
 * 处理「URL 里读不出日期」的条目：回源一次，顺手把存活和日期一起验掉。
 *
 * 为什么要专门处理这类：发改委的 /t20261126_1234.html 能读出日期，
 * 但工信部、部分省厅的 /art/2026/art_xxxx.html 读不出来，
 * 不补日期就会被下面的「无日期不展示」规则丢掉——明明是新文件却进不了库。
 *
 * 只跑这类条目、最多 8 条：云函数总共 20 秒，不能为了几条边角料拖垮主流程。
 */
async function enrichUnknown(items) {
  const todo = items.filter((x) => !x.ts).slice(0, 8);
  if (!todo.length) return { checked: 0, dead: [] };
  const res = await mapLimit(todo, 8, async (x) => {
    const html = await getText(x.url, 5000);
    if (html.length < 1200) throw new Error('内容过短');
    if (DEAD_MARKERS.some((k) => html.indexOf(k) >= 0) && html.length < 6000) {
      throw new Error('死链特征');
    }
    return dateFromPage(html);
  });
  const dead = [];
  todo.forEach((x, i) => {
    const r = res[i];
    if (!r.ok) {
      dead.push(x);
      return;
    }
    if (r.value) x.ts = r.value;
    // 页面打开了但读不出日期：先放着，下一轮抓取时再看
    if (!x.ts) dead.push(x);
  });
  return { checked: todo.length, dead: dead };
}

function docKey(t) {
  const m = /《([^》]{6,})》/.exec(t || '');
  return m ? m[1] : '';
}

function stripNo(t) {
  return (t || '').replace(/\s*[（(][^）)]*〔\d{4}〕[^）)]*[）)]\s*$/, '');
}

/**
 * 抓政策并与库里的历史合并。
 *
 * existing：云库里现有的 items。政策只增不删——一旦抓到就留住，
 * 不能每轮重抓，否则只留得住「此刻还在列表首页」的几条。
 */
async function crawlPolicies(existing, opts) {
  const started = Date.now();
  const options = opts || {};
  const prev = (existing || []).filter((p) => p && p.url && p.title);

  const seenUrl = new Set(prev.map((p) => p.url));
  const seenTitle = new Set(prev.map((p) => p.title));

  const results = await mapLimit(SOURCES, 11, fetchSource);

  const fresh = [];
  const report = [];
  results.forEach((r, i) => {
    const src = SOURCES[i];
    if (!r.ok) {
      report.push({ org: src.org, ok: false, err: String(r.error).slice(0, 60) });
      return;
    }
    let added = 0;
    for (const it of r.value) {
      if (seenTitle.has(it.title) || seenUrl.has(it.url)) continue;
      seenTitle.add(it.title);
      seenUrl.add(it.url);
      fresh.push({
        id: '',
        title: it.title,
        url: it.url,
        level: it.level,
        org: it.org,
        ts: tsFromUrl(it.url),
        impact: impactOf(it.title),
        impact_src: 'rule',
        tags: tagsOf(it.title),
      });
      added += 1;
    }
    report.push({ org: src.org, ok: true, count: added });
  });

  let enriched = 0;
  let deadCount = 0;
  if (fresh.length && !options.skipVerify) {
    const v = await enrichUnknown(fresh);
    enriched = v.checked;
    deadCount = v.dead.length;
    if (deadCount) {
      const deadUrls = new Set(v.dead.map((x) => x.url));
      for (let i = fresh.length - 1; i >= 0; i -= 1) {
        if (deadUrls.has(fresh[i].url)) fresh.splice(i, 1);
      }
    }
  }

  const now = Math.floor(Date.now() / 1000);
  for (const x of fresh) x.verified_at = now;

  let out = prev.concat(fresh);

  // 取不到日期的不展示，页面上会是一堆「—」
  const beforeDrop = out.length;
  out = out.filter((x) => x.ts);
  const droppedNoTs = beforeDrop - out.length;
  out.sort((a, b) => (b.ts || 0) - (a.ts || 0));

  // 标签全量重算：规则一改，历史条目跟着变，不会新旧割裂
  for (const x of out) x.tags = tagsOf(x.title);

  // 人工补录的条目不参与自动去重（同事逐条核过，被算法吞掉等于白录）
  const manual = out.filter((x) => x.source === 'manual');
  out = out.filter((x) => x.source !== 'manual');

  const kept = new Map();
  const merged = [];
  for (const x of out) {
    const k = docKey(x.title);
    if (!k) {
      const base = stripNo(x.title);
      const dup = merged.find(
        (m) => docKey(m.title) && base.indexOf(docKey(m.title)) >= 0
          && Math.abs((m.ts || 0) - (x.ts || 0)) < 90 * 86400
      );
      if (dup) {
        if (x.title.length > dup.title.length) merged[merged.indexOf(dup)] = x;
        continue;
      }
      merged.push(x);
      continue;
    }
    const same = kept.get(k);
    if (same && Math.abs((same.ts || 0) - (x.ts || 0)) < 90 * 86400) {
      if (x.title.length > same.title.length) {
        kept.set(k, x);
        merged[merged.indexOf(same)] = x;
      }
      continue;
    }
    kept.set(k, x);
    merged.push(x);
  }

  // 反向补一刀：「XX印发《YY》」与「YY（发文字号）」两条并存时只留一条
  const final = [];
  for (const x of merged) {
    const c = docKey(x.title);
    if (c) {
      const twin = final.find(
        (m) => !docKey(m.title)
          && [c, c + '的通知', c + '通知'].indexOf(stripNo(m.title).replace(/^[。\s]+|[。\s]+$/g, '')) >= 0
      );
      if (twin) continue;
    }
    final.push(x);
  }

  const cutoff = Math.floor(Date.now() / 1000) - KEEP_YEARS * 365 * 86400;
  let items = final.concat(manual).filter((x) => (x.ts || 0) >= cutoff);
  items.sort((a, b) => (b.ts || 0) - (a.ts || 0));
  items = items.slice(0, KEEP_MAX);
  items.forEach((x, i) => {
    x.id = 'pol' + (i + 1);
  });

  return {
    items: items,
    added: fresh.length,
    total: items.length,
    enriched: enriched,
    dead: deadCount,
    dropped_no_ts: droppedNoTs,
    sources: report,
    debug_fresh: options.debug ? fresh : undefined,
    ms: Date.now() - started,
  };
}

module.exports = {
  crawlPolicies: crawlPolicies,
  SOURCES: SOURCES,
  tagsOf: tagsOf,
  impactOf: impactOf,
  tsFromUrl: tsFromUrl,
  relevant: relevant,
  clean: clean,
};
