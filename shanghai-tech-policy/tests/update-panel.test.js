/* 底部「数据更新」面板测试
 *
 * 面板有两种形态，靠探测 /api/status 决定：
 *   1) 本机服务（有更新接口）—— 显示「立即更新」按钮，点击真能触发并轮询进度
 *   2) 静态托管（Cloudflare Pages）—— **隐藏按钮**，只显示上次更新时间与说明，
 *      避免出现"点了没用"的死按钮
 * 另外：数据超过 30 小时会显示「已滞后 N 天」徽标。
 */
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');

const ROOT = path.join(__dirname, '..');
const html = fs.readFileSync(path.join(ROOT, 'index.html'), 'utf8');
const dataJs = fs.readFileSync(path.join(ROOT, 'data', 'policies.js'), 'utf8');
const appJs = fs.readFileSync(path.join(ROOT, 'assets', 'app.js'), 'utf8');

let pass = 0, fail = 0;
function ok(name, cond, extra) {
  if (cond) { pass++; console.log('  ✓ ' + name); }
  else { fail++; console.log('  ✗ ' + name + (extra ? '  -> ' + extra : '')); }
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function boot({ url, fetchImpl }) {
  const dom = new JSDOM(html, {
    runScripts: 'outside-only', pretendToBeVisual: true, url
  });
  const w = dom.window;
  w.scrollTo = () => {};
  w.matchMedia = (q) => ({ matches: false, media: q, addEventListener() {}, removeEventListener() {} });
  w.fetch = fetchImpl;
  w.eval(dataJs);
  w.eval(appJs);
  const $ = (s) => w.document.querySelector(s);
  const click = (el) => el.dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
  return { w, $, click };
}

(async () => {
  console.log('\n== 面板基本渲染 ==');
  {
    const { $ } = boot({
      url: 'https://shanghai-tech-policy.pages.dev/',
      fetchImpl: () => Promise.reject(new Error('no api'))
    });
    await sleep(120);
    ok('面板存在', !!$('#updatebox'));
    ok('显示上次更新时间', /\d{4}-\d{2}-\d{2}/.test($('#ub-last').textContent),
       $('#ub-last').textContent);
    ok('有滞后提示位', !!$('#ub-stale'));
    ok('日志区默认隐藏', $('#ub-log').hidden);
  }

  console.log('\n== 静态托管：隐藏按钮 + 给出说明 ==');
  {
    const { $ } = boot({
      url: 'https://shanghai-tech-policy.pages.dev/',
      fetchImpl: () => Promise.reject(new Error('no api'))
    });
    await sleep(150);
    ok('按钮被隐藏（不再是死按钮）', $('#ub-btn').hidden === true,
       'hidden=' + $('#ub-btn').hidden);
    ok('给出说明文字', !$('#ub-msg').hidden && $('#ub-msg').textContent.length > 10,
       $('#ub-msg').textContent.slice(0, 40));
    ok('说明里点明是静态托管', /静态托管/.test($('#ub-msg').textContent),
       $('#ub-msg').textContent.slice(0, 50));
    ok('说明里提到数据由服务端定时更新', /定时/.test($('#ub-msg').textContent));
  }

  console.log('\n== 本机服务：显示按钮并可触发更新 ==');
  {
    let calls = [];
    let statusN = 0;
    const fetchImpl = (u, opt) => {
      calls.push({ u: String(u), method: (opt && opt.method) || 'GET' });
      if (String(u).includes('api/update')) {
        return Promise.resolve({
          ok: true, headers: { get: () => 'application/json' },
          json: () => Promise.resolve({ ok: true, started: true })
        });
      }
      if (String(u).includes('api/status')) {
        statusN++;
        return Promise.resolve({
          ok: true, headers: { get: () => 'application/json' },
          json: () => Promise.resolve(
            statusN <= 2
              ? { ok: true, running: true, log: ['[1/6] 抓取…', '[2/6] 分类…'] }
              : { ok: true, running: false, lastExit: 0, log: ['[6/6] 完成'] })
        });
      }
      return Promise.reject(new Error('unexpected'));
    };
    const { $, click } = boot({ url: 'http://127.0.0.1:8899/', fetchImpl });
    await sleep(150);
    ok('本机模式显示按钮', $('#ub-btn').hidden === false);
    ok('探测了 /api/status', calls.some((c) => c.u.includes('api/status')));

    click($('#ub-btn'));
    await sleep(200);
    ok('点击后 POST /api/update',
       calls.some((c) => c.u.includes('api/update') && c.method === 'POST'));
    ok('按钮进入禁用态', $('#ub-btn').disabled === true, $('#ub-btn').textContent);
    ok('显示更新日志', !$('#ub-log').hidden && $('#ub-log').textContent.length > 0,
       $('#ub-log').textContent.slice(0, 30));
    await sleep(3200);
    ok('完成后提示成功', /更新完成/.test($('#ub-msg').textContent || ''),
       $('#ub-msg').textContent);
    ok('多次轮询直到结束', statusN >= 3, statusN + ' 次');
  }

  console.log('\n== 数据滞后徽标 ==');
  {
    const w = new JSDOM(html, { runScripts: 'outside-only', pretendToBeVisual: true,
      url: 'https://shanghai-tech-policy.pages.dev/' }).window;
    w.scrollTo = () => {};
    w.matchMedia = (q) => ({ matches: false, media: q, addEventListener() {}, removeEventListener() {} });
    w.fetch = () => Promise.reject(new Error('no api'));
    w.eval(dataJs);
    const old = new Date(Date.now() - 5 * 864e5);
    const pad = (n) => String(n).padStart(2, '0');
    w.__POLICY_DATA__.meta.generatedAt =
      `${old.getFullYear()}-${pad(old.getMonth() + 1)}-${pad(old.getDate())} ` +
      `${pad(old.getHours())}:${pad(old.getMinutes())}`;
    w.eval(appJs);
    await sleep(150);
    const el = w.document.querySelector('#ub-stale');
    ok('滞后徽标显示出来', el && !el.hidden, el ? 'hidden=' + el.hidden : '无元素');
    ok('徽标文案是「已滞后 N 天」', /已滞后\s*\d+\s*天/.test(el.textContent), el.textContent);
  }

  console.log('\n' + '='.repeat(46));
  console.log(`结果：${pass} 通过 / ${fail} 失败`);
  console.log('='.repeat(46));
  process.exit(fail ? 1 : 0);
})();
