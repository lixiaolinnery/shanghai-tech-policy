/* 移动端折叠筛选栏测试：用 jsdom 模拟窄屏（matchMedia matches=true） */
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');

const ROOT = path.join(__dirname, '..');
const html = fs.readFileSync(path.join(ROOT, 'index.html'), 'utf8');

let pass = 0, fail = 0;
function ok(name, cond, extra) {
  if (cond) { pass++; console.log('  ✓ ' + name); }
  else { fail++; console.log('  ✗ ' + name + (extra ? '  -> ' + extra : '')); }
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/** 用指定断点建一个新的页面实例 */
function boot(mobile) {
  const dom = new JSDOM(html, { runScripts: 'outside-only', pretendToBeVisual: true });
  const w = dom.window;
  const listeners = [];
  w.matchMedia = (q) => ({
    matches: mobile, media: q,
    addEventListener: (_, fn) => listeners.push(fn),
    removeEventListener: () => {},
    addListener: (fn) => listeners.push(fn),
    removeListener: () => {}
  });
  w.scrollTo = () => {};
  w.eval(fs.readFileSync(path.join(ROOT, 'data', 'policies.js'), 'utf8'));
  w.eval(fs.readFileSync(path.join(ROOT, 'assets', 'app.js'), 'utf8'));
  const $ = (s) => w.document.querySelector(s);
  const $$ = (s) => Array.from(w.document.querySelectorAll(s));
  const click = (el) => el.dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
  const change = (el) => el.dispatchEvent(new w.Event('change', { bubbles: true }));
  return { w, $, $$, click, change, listeners };
}

(async () => {
  console.log('\n== 窄屏：默认收起 ==');
  {
    const { $, $$, click, change } = boot(true);
    ok('筛选控件区默认隐藏', $('#filters').style.display === 'none', $('#filters').style.display);
    ok('年份快捷条默认隐藏', $('#yearbar').style.display === 'none', $('#yearbar').style.display);
    ok('折叠按钮存在', !!$('#filterToggle'));
    ok('折叠按钮 aria-expanded=false', $('#filterToggle').getAttribute('aria-expanded') === 'false');
    ok('折叠条上显示结果条数', /\d+\s*条/.test($('#fres').textContent), $('#fres').textContent);
    ok('无筛选时徽标为空', $('#fcount').textContent === '', JSON.stringify($('#fcount').textContent));
    ok('列表照常渲染（收起不影响结果）', $$('#list .card').length === 40, $$('#list .card').length);

    console.log('\n== 窄屏：点击展开 ==');
    click($('#filterToggle'));
    ok('筛选控件区展开', $('#filters').style.display === 'flex', $('#filters').style.display);
    ok('年份快捷条展开', $('#yearbar').style.display === 'flex', $('#yearbar').style.display);
    ok('aria-expanded=true', $('#filterToggle').getAttribute('aria-expanded') === 'true');

    console.log('\n== 窄屏：筛选计数徽标 ==');
    $('#f-cat').value = '企业技术中心';
    change($('#f-cat'));
    ok('选了 1 个筛选条件后徽标显示 1', $('#fcount').textContent === '1', $('#fcount').textContent);
    const n1 = $('#list').querySelectorAll('.card').length;
    ok('结果被筛选', $('#fres').textContent !== '', $('#fres').textContent);
    $('#f-year').value = '2026';
    change($('#f-year'));
    ok('再选年份后徽标显示 2', $('#fcount').textContent === '2', $('#fcount').textContent);

    console.log('\n== 窄屏：收起后筛选依然生效 ==');
    click($('#filterToggle'));
    ok('再次收起', $('#filters').style.display === 'none');
    ok('收起后徽标保留', $('#fcount').textContent === '2', $('#fcount').textContent);
    ok('收起后结果条数保留', /\d+\s*条/.test($('#fres').textContent), $('#fres').textContent);
    const cards = Array.from($('#list').querySelectorAll('.card'));
    ok('收起后列表仍是被筛选的结果',
       cards.length > 0 && cards.every((c) => c.querySelector('.tag.cat').textContent === '企业技术中心'),
       cards.length + ' 张');

    console.log('\n== 窄屏：重置筛选 ==');
    click($('#filterToggle'));
    click($('#reset'));
    ok('重置后徽标清空', $('#fcount').textContent === '', JSON.stringify($('#fcount').textContent));
    ok('重置后结果恢复', $('#list').querySelectorAll('.card').length === 40,
       $('#list').querySelectorAll('.card').length);
    ok('重置不改变展开状态', $('#filters').style.display === 'flex', $('#filters').style.display);
  }

  console.log('\n== 窄屏：深度解读视图 ==');
  {
    const { $, $$, click } = boot(true);
    click($$('#tabs .tab').find((t) => t.textContent.includes('申报条件与好处')));
    ok('解读视图下折叠条也隐藏', $('#filterBar').style.display === 'none', $('#filterBar').style.display);
    ok('解读卡片渲染', $$('#list .guide').length > 0, $$('#list .guide').length);
    click($$('#tabs .tab').find((t) => t.textContent.includes('全部政策')));
    ok('切回列表后恢复默认收起', $('#filters').style.display === 'none', $('#filters').style.display);
  }

  console.log('\n== 桌面端：不折叠 ==');
  {
    const { $, $$, click } = boot(false);
    ok('桌面端筛选区可见', $('#filters').style.display === 'flex', $('#filters').style.display);
    ok('桌面端年份条可见', $('#yearbar').style.display === 'flex', $('#yearbar').style.display);
    ok('桌面端折叠条由 CSS 隐藏（style 不设值）', $('#filterBar').style.display === '',
       JSON.stringify($('#filterBar').style.display));
    click($('#filterToggle'));
    ok('桌面端点折叠按钮不影响筛选区', $('#filters').style.display === 'flex', $('#filters').style.display);
    ok('列表正常', $$('#list .card').length === 40, $$('#list .card').length);
  }

  console.log('\n== 断点切换（横竖屏 / 改窗口）==');
  {
    const { $, listeners } = boot(true);
    ok('初始为窄屏收起', $('#filters').style.display === 'none');
    ok('注册了断点监听', listeners.length > 0, listeners.length);
  }

  console.log('\n' + '='.repeat(46));
  console.log(`结果：${pass} 通过 / ${fail} 失败`);
  console.log('='.repeat(46));
  process.exit(fail ? 1 : 0);
})();
