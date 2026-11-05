/* 上海科技政策查询 —— 前端逻辑（无依赖，支持 file:// 直接打开） */
(function () {
  'use strict';
  var D = window.__POLICY_DATA__ || { policies: [], guides: [], meta: {} };
  var P = D.policies || [];
  var GUIDES = D.guides || [];

  var TABS = [
    { k: 'all', label: '全部政策', nt: null },
    { k: 'doc', label: '政策红头文件', nt: '政策红头文件' },
    { k: 'apply', label: '申报通知', nt: '申报通知' },
    { k: 'pub', label: '公示通知', nt: '公示通知' },
    { k: 'subsidy', label: '领补贴通知', nt: '领补贴通知' },
    { k: 'fund', label: '补贴与资金', fund: true },
    { k: 'proj', label: '立项与评价', nt: '立项与评价通知' },
    { k: 'list', label: '名单公布', nt: '名单公布' },
    { k: 'guide', label: '申报条件与好处', nt: null }
  ];

  var state = { tab: 'all', q: '', cat: '', level: '', year: '', src: '', issuer: '',
                shown: 40, fcollapsed: true };
  var PAGE = 40;

  // 窄屏时筛选区默认收起，只留一条细栏，避免上下滑动时被筛选控件占满视野
  var MQ = (typeof window.matchMedia === 'function')
    ? window.matchMedia('(max-width: 640px)') : null;
  function isMobile() { return !!(MQ && MQ.matches); }
  state.fcollapsed = isMobile();

  function activeFilterCount() {
    return ['q', 'cat', 'level', 'year', 'src', 'issuer'].filter(function (k) {
      return state[k];
    }).length;
  }

  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c];
    });
  }
  function uniq(a) { var s = {}, o = []; a.forEach(function (x) { if (x && !s[x]) { s[x] = 1; o.push(x); } }); return o; }

  /* ---------------- 初始化统计与筛选器 ---------------- */
  var YEARS = uniq(P.map(function (x) { return x.year; })).sort().reverse();
  var CATS = uniq(P.map(function (x) { return x.category; })).sort();
  var SRCS = uniq(P.map(function (x) { return x.sourceName || x.source; })).sort();
  var ISSUERS = uniq(P.map(function (x) { return x.issuer; })).filter(function (x) { return x && x.length > 4; }).sort();

  function countOf(t) {
    if (t.fund) return P.filter(function (x) { return x.isFunding; }).length;
    if (!t.nt) return P.length;
    return P.filter(function (x) { return x.noticeType === t.nt; }).length;
  }

  function buildTabs() {
    $('#tabs').innerHTML = TABS.map(function (t) {
      var n = t.k === 'guide' ? GUIDES.length : countOf(t);
      return '<button class="tab" data-tab="' + t.k + '">' + esc(t.label) +
        '<span class="n">' + n + '</span></button>';
    }).join('');
  }

  function opt(v, label) { return '<option value="' + esc(v) + '">' + esc(label) + '</option>'; }

  function buildFilters() {
    $('#f-cat').innerHTML = opt('', '全部政策类型') + CATS.map(function (c) { return opt(c, c); }).join('');
    $('#f-year').innerHTML = opt('', '全部年份') + YEARS.map(function (y) { return opt(y, y + ' 年'); }).join('');
    $('#f-src').innerHTML = opt('', '全部数据来源') + SRCS.map(function (s) { return opt(s, s); }).join('');
    $('#f-issuer').innerHTML = opt('', '全部发布单位') +
      ISSUERS.slice(0, 90).map(function (s) { return opt(s, s.length > 22 ? s.slice(0, 22) + '…' : s); }).join('');
  }

  function buildStats() {
    var yrs = YEARS.length ? YEARS[YEARS.length - 1] + '–' + YEARS[0] : '—';
    var deep = P.filter(function (x) { return x.depth === 'full'; }).length;
    var docs = P.filter(function (x) { return x.docNo; }).length;
    var pdfs = P.filter(function (x) { return x.pdfUrls && x.pdfUrls.length; }).length;
    var city = P.filter(function (x) { return (x.level || '市级') === '市级'; }).length;
    var dist = P.filter(function (x) { return x.level === '区级'; }).length;
    var items = [
      [P.length, '条政策记录'],
      [yrs, '覆盖年份'],
      [CATS.length, '个政策类型'],
      [GUIDES.length, '类深度解读'],
      [docs, '条含文号'],
      [pdfs, '条附红头文件 PDF']
    ];
    if (dist) items.splice(1, 0, [city + ' / ' + dist, '市级 / 区级']);
    $('#stats').innerHTML = items.map(function (x) {
      return '<div class="stat"><b>' + esc(x[0]) + '</b><span>' + x[1] + '</span></div>';
    }).join('');
  }

  /* ---------------- 过滤 ---------------- */
  function currentList() {
    var t = TABS.filter(function (x) { return x.k === state.tab; })[0] || TABS[0];
    var q = state.q.trim().toLowerCase();
    return P.filter(function (x) {
      if (t.fund && !x.isFunding) return false;
      if (t.nt && x.noticeType !== t.nt) return false;
      if (state.cat && x.category !== state.cat) return false;
      if (state.level && (x.level || '市级') !== state.level) return false;
      if (state.year && x.year !== state.year) return false;
      if (state.src && (x.sourceName || x.source) !== state.src) return false;
      if (state.issuer && x.issuer !== state.issuer) return false;
      if (q) {
        var hay = (x.title + ' ' + (x.docNo || '') + ' ' + (x.issuer || '') + ' ' +
          (x.summary || '') + ' ' + (x.category || '') + ' ' + ((x.keywords || []).join(' '))).toLowerCase();
        if (hay.indexOf(q) < 0) return false;
      }
      return true;
    });
  }

  var NT_CLASS = {
    '政策红头文件': 't-政策红头文件', '申报通知': 't-申报通知', '公示通知': 't-公示通知',
    '领补贴通知': 't-领补贴通知', '立项与评价通知': 't-立项与评价通知',
    '名单公布': 't-名单公布', '政策解读': 't-政策解读'
  };

  function cardHTML(x, i) {
    var cls = NT_CLASS[x.noticeType] || '';
    var tags = '';
    tags += '<span class="tag nt">' + esc(x.noticeType) + '</span>';
    tags += '<span class="tag cat">' + esc(x.category) + '</span>';
    if (x.docNo) tags += '<span class="tag doc">' + esc(x.docNo) + '</span>';
    if (x.level === '区级') tags += '<span class="tag">' + esc(x.district || '区级') + '</span>';
    if (x.depth === 'full') tags += '<span class="tag deep">含结构化抽取</span>';
    var pdf = (x.pdfUrls && x.pdfUrls.length)
      ? '<a href="' + esc(x.pdfUrls[0]) + '" target="_blank" rel="noopener" onclick="event.stopPropagation()">红头文件 PDF</a>' : '';
    return '<article class="card ' + cls + '" data-i="' + i + '">' +
      '<h3>' + esc(x.title) + '</h3>' +
      '<div class="meta">' + tags +
      '<span>' + esc(x.publishDate) + '</span>' +
      (x.issuer ? '<span>· ' + esc(x.issuer) + '</span>' : '') +
      '<span>· ' + esc(x.sourceName || x.source) + '</span></div>' +
      (x.summary ? '<p class="sum">' + esc(x.summary) + '</p>' : '') +
      '<div class="acts">' + (x.linkOk === false ? '<span class="tag" style="background:#fdecec;color:#b0242b;border-color:#f3d5d6">原文链接已失效</span>' : '') +
      '<a href="' + esc(x.url) + '" target="_blank" rel="noopener" onclick="event.stopPropagation()">查看原文 ↗</a>' + pdf + '</div>' +
      '</article>';
  }

  function renderList() {
    var list = currentList();
    var box = $('#list');
    if (!list.length) {
      box.innerHTML = '<div class="empty"><b>没有匹配的政策</b>换个关键词，或点上面的「重置筛选」。</div>';
      $('#resultbar').innerHTML = '';
      return;
    }
    var slice = list.slice(0, state.shown);
    // 按年份分组（组内计数用该年总数，而非已显示条数）
    var totals = {};
    list.forEach(function (x) { totals[x.year || '未知'] = (totals[x.year || '未知'] || 0) + 1; });
    var groups = {}, order = [];
    slice.forEach(function (x, i) {
      var y = x.year || '未知';
      if (!groups[y]) { groups[y] = []; order.push(y); }
      groups[y].push({ x: x, i: i });
    });
    box.innerHTML = order.map(function (y) {
      var g = groups[y];
      return '<section class="yeargroup"><div class="yearhead"><h2>' + esc(y) + ' 年</h2>' +
        '<span class="c">共 ' + (totals[y] || g.length) + ' 条，本页显示 ' + g.length + '</span>' +
        '<span class="line"></span></div>' +
        g.map(function (o) { return cardHTML(o.x, o.i); }).join('') + '</section>';
    }).join('');
    if (list.length > state.shown) {
      box.innerHTML += '<div class="more"><button class="btn" id="more">加载更多（还有 ' +
        (list.length - state.shown) + ' 条）</button></div>';
      $('#more').onclick = function () { state.shown += PAGE; renderList(); };
    }
    $('#resultbar').innerHTML = '<div class="cnt">共 <b>' + list.length + '</b> 条，已显示 ' +
      Math.min(state.shown, list.length) + ' 条</div>' + chipsHTML();
    // 收起状态下，把条数摘到折叠条上，这样不展开也知道筛出来多少
    var res = $('#fres');
    if (res) res.textContent = list.length + ' 条';
  }

  function chipsHTML() {
    var c = [];
    if (state.q) c.push(['q', '关键词：' + state.q]);
    if (state.cat) c.push(['cat', '类型：' + state.cat]);
    if (state.level) c.push(['level', '层级：' + state.level]);
    if (state.year) c.push(['year', '年份：' + state.year + ' 年']);
    if (state.src) c.push(['src', '来源：' + state.src]);
    if (state.issuer) c.push(['issuer', '单位：' + state.issuer]);
    if (!c.length) return '';
    return '<div class="chips">' + c.map(function (x) {
      return '<span class="chip x" data-clear="' + x[0] + '">' + esc(x[1]) + '</span>';
    }).join('') + '<span class="chip" data-clear="all">重置筛选</span></div>';
  }

  /* ---------------- 政策速查 ---------------- */
  function relatedCount(g) {
    var terms = g.matchTerms || [g.category];
    return P.filter(function (x) {
      return terms.some(function (t) { return x.title.indexOf(t) >= 0; });
    }).length;
  }

  function renderGuides() {
    if (!GUIDES.length) {
      $('#list').innerHTML = '<div class="empty"><b>深度解读数据未加载</b>请先运行构建脚本生成 guides。</div>';
      $('#resultbar').innerHTML = '';
      return;
    }
    $('#resultbar').innerHTML = '<div class="cnt">按政策类型汇总的申报条件与政策好处，共 <b>' +
      GUIDES.length + '</b> 类。每条均标注来源文件。</div>';
    $('#list').innerHTML = '<div class="guides">' + GUIDES.map(function (g) {
      function blk(title, arr) {
        if (!arr || !arr.length) return '';
        return '<div class="blk"><h5>' + title + '</h5><ul>' + arr.map(function (it) {
          var t = typeof it === 'string' ? it : it.text;
          var s = typeof it === 'string' ? '' : (it.source || '');
          return '<li>' + esc(t) + (s ? ' <span class="src">〔' + esc(s) + '〕</span>' : '') + '</li>';
        }).join('') + '</ul></div>';
      }
      return '<div class="guide"><h3>' + esc(g.category) + '</h3>' +
        '<div class="org">' + esc(g.authority || '') + '</div>' +
        (g.intro ? '<p style="font-size:12.5px;color:#4a5158;margin:0 0 11px">' + esc(g.intro) + '</p>' : '') +
        blk('申报条件', g.conditions) + blk('政策好处', g.benefits) +
        (g.timeline ? '<div class="blk"><h5>申报时间</h5><p style="font-size:12.5px;color:#4a5158;margin:0">' + esc(g.timeline) + '</p></div>' : '') +
        blk('申报材料', g.materials) +
        (function () {
          var n = relatedCount(g);
          if (!n) return '';
          return '<div class="blk"><button class="btn primary relate" data-term="' +
            esc((g.matchTerms || [g.category])[0]) + '" style="font-size:12.5px;padding:6px 12px">' +
            '查看本站 ' + n + ' 条相关通知 →</button></div>';
        })() +
        (g.applyUrl ? '<div class="open"><a href="' + esc(g.applyUrl) + '" target="_blank" rel="noopener">申报入口 ↗</a></div>' : '') +
        (g.refs && g.refs.length ? '<div class="open">' + g.refs.map(function (r) {
          return '<a href="' + esc(r.url) + '" target="_blank" rel="noopener" style="margin-right:12px;font-size:12px">' + esc(r.title) + ' ↗</a>';
        }).join('') + '</div>' : '') +
        (g.notes ? '<div class="note" style="margin-top:10px">' + esc(g.notes) + '</div>' : '') +
        '</div>';
    }).join('') + '</div>';
  }

  function guideFor(category) {
    if (!category) return null;
    var exact = GUIDES.filter(function (g) { return g.category === category; })[0];
    if (exact) return exact;
    return GUIDES.filter(function (g) {
      var terms = g.matchTerms || [g.category];
      return terms.some(function (t) { return category.indexOf(t) >= 0 || t.indexOf(category) >= 0; });
    })[0] || null;
  }

  /* ---------------- 详情抽屉 ---------------- */
  function openDetail(x) {
    var h = [];
    h.push('<div class="dhead"><div style="flex:1"><h2>' + esc(x.title) + '</h2>' +
      '<div class="meta" style="display:flex;gap:8px;flex-wrap:wrap;font-size:12px;color:#8b939c">' +
      '<span class="tag nt">' + esc(x.noticeType) + '</span>' +
      '<span class="tag cat">' + esc(x.category) + '</span>' +
      (x.docNo ? '<span class="tag doc">' + esc(x.docNo) + '</span>' : '') +
      '</div></div><button class="x" id="dclose">✕</button></div>');

    h.push('<div class="dbody">');
    h.push('<div class="dsec"><h4>基本信息</h4><dl class="kv">' +
      '<dt>发布日期</dt><dd>' + esc(x.publishDate) + '</dd>' +
      '<dt>发布单位</dt><dd>' + esc(x.issuer || ('页面未标注，来源：' + (x.sourceName || x.source))) + '</dd>' +
      '<dt>文号</dt><dd>' + esc(x.docNo || '未标注') + '</dd>' +
      '<dt>政策类型</dt><dd>' + esc(x.category) + '</dd>' +
      '<dt>通知类型</dt><dd>' + esc(x.noticeType) + '</dd>' +
      '<dt>层级</dt><dd>' + esc(x.level || '市级') + '</dd>' +
      '<dt>数据来源</dt><dd>' + esc(x.sourceName || x.source) + '</dd>' +
      (x.linkOk === false ? '<dt>链接状态</dt><dd style="color:#b0242b">官网原文链接当前不可访问，建议在官网站内按标题检索</dd>' : '') +
      (x.linkNote === 'unverified' ? '<dt>链接状态</dt><dd style="color:#8a6a2f">采集时已验证可访问，本轮复检因该站限流未能重新确认</dd>' : '') +
      '</dl></div>');

    h.push('<div class="dsec"><h4>原文链接</h4>' +
      '<div class="att"><a href="' + esc(x.url) + '" target="_blank" rel="noopener">官网原文页面 ↗</a></div>');
    if (x.linkOk === false) {
      h.push('<div class="att" style="color:#b0242b">该链接已失效，可在对应官网用标题检索</div>');
    }
    (x.pdfUrls || []).forEach(function (u, i) {
      h.push('<div class="att"><a href="' + esc(u) + '" target="_blank" rel="noopener">红头文件 / 原文 PDF' + (x.pdfUrls.length > 1 ? ' ' + (i + 1) : '') + ' ↗</a></div>');
    });
    if (x.pdfOk === false) {
      h.push('<div class="att" style="color:#b0242b">红头文件 PDF 链接当前不可访问，请以官网原文页面为准</div>');
    }
    (x.attachments || []).forEach(function (a) {
      if (x.pdfUrls && x.pdfUrls.indexOf(a.url) >= 0) return;
      h.push('<div class="att"><a href="' + esc(a.url) + '" target="_blank" rel="noopener">附件：' + esc(a.name) + ' ↗</a></div>');
    });
    h.push('</div>');

    if (x.summary) h.push('<div class="dsec"><h4>内容摘要</h4><p style="font-size:13.5px;color:#4a5158;margin:0">' + esc(x.summary) + '</p></div>');

    if (x.conditions && x.conditions.length) {
      h.push('<div class="dsec"><h4>申报条件</h4><ul>' + x.conditions.map(function (c) { return '<li>' + esc(c) + '</li>'; }).join('') + '</ul></div>');
    }
    if (x.benefits && x.benefits.length) {
      h.push('<div class="dsec"><h4>政策好处</h4><ul>' + x.benefits.map(function (c) { return '<li>' + esc(c) + '</li>'; }).join('') + '</ul></div>');
    }
    if (x.moneyHints && x.moneyHints.length) {
      h.push('<div class="dsec"><h4>涉及金额</h4><div>' + x.moneyHints.map(function (m) { return '<span class="money">' + esc(m) + '</span>'; }).join('') + '</div></div>');
    }
    if (x.timeHints && x.timeHints.length) {
      h.push('<div class="dsec"><h4>时间节点</h4><div>' + x.timeHints.map(function (m) { return '<span class="timechip">' + esc(m) + '</span>'; }).join('') + '</div></div>');
    }
    if (x.timeline && x.timeline.length) {
      h.push('<div class="dsec"><h4>申报时间说明</h4><ul>' + x.timeline.map(function (c) { return '<li>' + esc(c) + '</li>'; }).join('') + '</ul></div>');
    }
    if (x.materials && x.materials.length) {
      h.push('<div class="dsec"><h4>申报材料清单</h4><ul>' + x.materials.map(function (c) { return '<li>' + esc(c) + '</li>'; }).join('') + '</ul></div>');
    }
    var hasAuto = (x.conditions && x.conditions.length) || (x.benefits && x.benefits.length) ||
      (x.materials && x.materials.length) || (x.timeline && x.timeline.length);
    var gi = guideFor(x.category);
    if (gi) {
      h.push('<div class="dsec"><h4>权威口径</h4><div class="note" style="background:#eef4fc;border-color:#d6e3f5;color:#1f5fa8">' +
        '这类政策的「申报条件 / 政策好处」经过原文核实，请看 ' +
        '<a href="javascript:void(0)" id="gotoguide" style="font-weight:700">《' + esc(gi.category) + '》深度解读 →</a></div></div>');
    }
    if (hasAuto) {
      h.push('<div class="dsec"><div class="note">以上「申报条件 / 政策好处 / 材料清单 / 时间节点」由程序从原文<b>自动抽取</b>，可能不完整或有偏差，仅供快速浏览。权威口径请以上方深度解读或官网原文为准。</div></div>');
    }
    h.push('<div class="dsec"><div class="note">本页信息由程序从政府官网公开页面采集，仅供检索参考，不构成申报依据。请务必点开原文链接核对最新要求。</div></div>');
    h.push('</div>');

    $('#drawer').innerHTML = h.join('');
    $('#drawer').classList.add('on');
    $('#mask').classList.add('on');
    $('#dclose').onclick = closeDetail;
    var gg = $('#gotoguide');
    if (gg) {
      gg.onclick = function (e) {
        e.preventDefault();
        closeDetail();
        state.tab = 'guide'; state.q = ''; state.shown = PAGE;
        $('#q').value = '';
        render();
        window.scrollTo({ top: 0, behavior: 'smooth' });
      };
    }
    $('#drawer').scrollTop = 0;
  }
  function closeDetail() {
    $('#drawer').classList.remove('on');
    $('#mask').classList.remove('on');
  }

  /* ---------------- 渲染调度 ---------------- */
  function buildYearBar() {
    var bar = $('#yearbar');
    if (!bar) return;
    var t = TABS.filter(function (x) { return x.k === state.tab; })[0] || TABS[0];
    // 统计当前栏目下各年份条数
    var counts = {};
    P.forEach(function (x) {
      if (t.fund && !x.isFunding) return;
      if (t.nt && x.noticeType !== t.nt) return;
      counts[x.year] = (counts[x.year] || 0) + 1;
    });
    var ys = Object.keys(counts).sort().reverse();
    bar.innerHTML = '<span class="yl">按年份：</span>' +
      '<button class="ybtn' + (state.year ? '' : ' on') + '" data-y="">全部<span class="n">' +
      (t.k === 'guide' ? '' : Object.keys(counts).reduce(function (a, k) { return a + counts[k]; }, 0)) + '</span></button>' +
      ys.map(function (y) {
        return '<button class="ybtn' + (state.year === y ? ' on' : '') + '" data-y="' + y + '">' +
          y + '<span class="n">' + counts[y] + '</span></button>';
      }).join('');
  }

  function bindYearBar() {
    $('#yearbar').addEventListener('click', function (e) {
      var b = e.target.closest('.ybtn');
      if (!b) return;
      state.year = b.dataset.y;
      if ($('#f-year')) $('#f-year').value = state.year;
      state.shown = PAGE;
      render();
    });
  }

  function render() {
    var isGuide = state.tab === 'guide';
    // 窄屏收起时把整个筛选控件区藏起来，只留折叠条
    var collapsed = isMobile() && state.fcollapsed;
    $('#filters').style.display = (isGuide || collapsed) ? 'none' : 'flex';
    $('#yearbar').style.display = (isGuide || collapsed) ? 'none' : 'flex';
    $('#filterBar').style.display = isGuide ? 'none' : '';
    var tg = $('#filterToggle');
    if (tg) {
      tg.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
      var n = activeFilterCount();
      $('#fcount').textContent = n ? String(n) : '';
    }
    buildYearBar();
    $$('.tab').forEach(function (b) { b.classList.toggle('on', b.dataset.tab === state.tab); });
    if (isGuide) { renderGuides(); return; }
    renderList();
  }

  function bind() {
    $('#tabs').addEventListener('click', function (e) {
      var b = e.target.closest('.tab');
      if (!b) return;
      state.tab = b.dataset.tab; state.shown = PAGE; render();
      window.scrollTo({ top: 0, behavior: 'smooth' });
    });
    var q = $('#q');
    var timer;
    q.addEventListener('input', function () {
      clearTimeout(timer);
      timer = setTimeout(function () { state.q = q.value; state.shown = PAGE; render(); }, 180);
    });
    ['cat', 'level', 'year', 'src', 'issuer'].forEach(function (k) {
      $('#f-' + k).addEventListener('change', function (e) {
        state[k === 'src' ? 'src' : k] = e.target.value; state.shown = PAGE; render();
      });
    });
    $('#reset').addEventListener('click', function () {
      state.q = ''; state.cat = ''; state.level = ''; state.year = ''; state.src = ''; state.issuer = '';
      state.shown = PAGE;
      q.value = ''; $('#f-cat').value = ''; $('#f-level').value = ''; $('#f-year').value = ''; $('#f-src').value = ''; $('#f-issuer').value = '';
      render();
    });
    $('#list').addEventListener('click', function (e) {
      var rel = e.target.closest('.relate');
      if (rel) {
        state.tab = 'all'; state.q = rel.dataset.term; state.shown = PAGE;
        q.value = rel.dataset.term;
        render();
        window.scrollTo({ top: 260, behavior: 'smooth' });
        return;
      }
      var c = e.target.closest('.card');
      if (!c) return;
      var list = currentList();
      var x = list[+c.dataset.i];
      if (x) openDetail(x);
    });
    $('#resultbar').addEventListener('click', function (e) {
      var ch = e.target.closest('.chip');
      if (!ch) return;
      var k = ch.dataset.clear;
      if (k === 'all') { $('#reset').click(); return; }
      state[k] = '';
      if (k === 'q') q.value = '';
      var el = $('#f-' + k); if (el) el.value = '';
      state.shown = PAGE; render();
    });
    $('#mask').addEventListener('click', closeDetail);
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape') closeDetail(); });
    bindYearBar();

    // 折叠/展开筛选区（窄屏用；桌面端折叠条被 CSS 隐藏，点了也无副作用）
    $('#filterToggle').addEventListener('click', function () {
      state.fcollapsed = !state.fcollapsed;
      render();
    });
    // 横竖屏切换 / 改窗口宽度时，按当前断点重新决定默认状态
    var onMq = function () { state.fcollapsed = isMobile(); render(); };
    if (MQ) {
      if (MQ.addEventListener) MQ.addEventListener('change', onMq);
      else if (MQ.addListener) MQ.addListener(onMq);
    }
  }

  /* ---------------- 数据更新面板 ---------------- */
  // 与本机调度器保持一致的自动更新节奏：每天 09:00-18:00 每小时一次
  function nextAutoUpdate(from) {
    var now = from || new Date();
    for (var d = 0; d < 8; d++) {
      var day = new Date(now);
      day.setDate(now.getDate() + d);
      for (var h = 9; h <= 18; h++) {
        var t = new Date(day);
        t.setHours(h, 0, 0, 0);
        if (t > now) return t;
      }
    }
    return null;
  }

  function pad2(n) { return (n < 10 ? '0' : '') + n; }

  function fmtWhen(t) {
    if (!t) return '—';
    return t.getFullYear() + '-' + pad2(t.getMonth() + 1) + '-' + pad2(t.getDate()) +
      ' ' + pad2(t.getHours()) + ':00';
  }

  function initUpdatePanel() {
    var box = $('#updatebox');
    if (!box) return;

    var last = (D.meta && D.meta.generatedAt) || '';
    $('#ub-last').textContent = last || '—';

    // 数据滞后提示：超过 30 小时就明确告诉用户
    (function () {
      var el = $('#ub-stale');
      if (!el || !last) return;
      var t = new Date(last.replace(' ', 'T'));
      if (isNaN(t.getTime())) return;
      var hours = (Date.now() - t.getTime()) / 36e5;
      if (hours >= 30) {
        var days = Math.floor(hours / 24);
        el.hidden = false;
        el.className = 'ub-stale' + (days >= 1 ? '' : ' warn');
        el.textContent = days >= 1 ? '已滞后 ' + days + ' 天' : '已滞后 ' + Math.round(hours) + ' 小时';
        el.title = '数据生成于 ' + last + '，可能不含最近发布的通知';
      }
    })();

    var btn = $('#ub-btn'), msg = $('#ub-msg'), logEl = $('#ub-log');
    var nx = nextAutoUpdate();

    function showMsg(text, kind) {
      msg.hidden = false;
      msg.className = 'ub-msg' + (kind ? ' ' + kind : '');
      msg.textContent = text;
    }
    function reset() {
      btn.disabled = false;
      btn.textContent = '立即更新';
    }

    function poll() {
      fetch('api/status', { cache: 'no-store' })
        .then(function (r) { return r.json(); })
        .then(function (j) {
          if (j.log && j.log.length) {
            logEl.hidden = false;
            logEl.textContent = j.log.join('\n');
            logEl.scrollTop = logEl.scrollHeight;
          }
          if (j.running) { setTimeout(poll, 1200); return; }
          if (j.lastExit === 0) {
            showMsg('更新完成，正在刷新页面…', 'ok');
            setTimeout(function () {
              location.href = location.pathname + '?t=' + Date.now();
            }, 900);
          } else {
            showMsg('更新结束，但返回码为 ' + j.lastExit + '，请查看上方日志。', 'err');
            reset();
          }
        })
        .catch(function () { setTimeout(poll, 1500); });
    }

    // 先探一下本机更新接口在不在：在就显示按钮（只有本机服务才提供），
    // 不在就是静态托管 —— 隐藏按钮，避免出现"点了没用"的死按钮。
    var probe = (typeof fetch === 'function')
      ? fetch('api/status', { cache: 'no-store' }).then(function (r) {
          if (!r.ok) throw new Error('no-api');
          return r.json();
        })
      : Promise.reject(new Error('no-fetch'));

    probe.then(function (j) {
      btn.hidden = false;
      if (j && j.running) {
        btn.disabled = true;
        btn.textContent = '更新中…';
        showMsg('本机正在更新，请稍候…', 'ok');
        poll();
      }
      btn.addEventListener('click', function () {
        btn.disabled = true;
        btn.textContent = '更新中…';
        msg.hidden = true;
        logEl.hidden = true;
        fetch('api/update', { method: 'POST' })
          .then(function (r) {
            var ct = r.headers.get('content-type') || '';
            if (!r.ok || ct.indexOf('application/json') < 0) throw new Error('no-api');
            return r.json();
          })
          .then(function (r) {
            showMsg(r.started ? '已开始更新，正在抓取最新通知…' : '已有更新在进行中…', 'ok');
            poll();
          })
          .catch(function () {
            showMsg('触发失败，请在本机终端执行：node bin/scheduler.js --once', 'err');
            reset();
          });
      });
    }).catch(function () {
      // 静态托管模式：没有更新接口，不显示按钮，改为给出可点击的本机控制台入口
      btn.hidden = true;
      var when = nx ? fmtWhen(nx) : '';
      showMsg(
        '本站是静态托管页面（Cloudflare Pages），浏览器无法直接触发后台更新。'
        + '数据由服务端定时任务更新，上面的时间就是这份数据的生成时间。'
        + (when ? '若后台调度正常，下一次更新大约是 ' + when + '。' : '')
      );
      // 如果是在这台设备上打开，可以走本机控制台一键更新
      var a = document.createElement('a');
      a.href = 'http://127.0.0.1:8899/';
      a.target = '_blank';
      a.rel = 'noopener';
      a.className = 'ub-link';
      a.textContent = '在本机打开更新控制台 →';
      msg.appendChild(document.createElement('br'));
      msg.appendChild(a);
      var hint = document.createElement('span');
      hint.className = 'ub-hint';
      hint.textContent = '（仅在这台手机且控制台正在运行时有效；启动命令：bash bin/打开控制台.sh）';
      msg.appendChild(document.createElement('br'));
      msg.appendChild(hint);
    });
  }

  buildTabs(); buildFilters(); buildStats(); bind(); render(); initUpdatePanel();
})();
