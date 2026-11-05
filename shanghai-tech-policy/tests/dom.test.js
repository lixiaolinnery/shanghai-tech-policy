/* 用 jsdom 对站点做真实 DOM 功能测试 */
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');

const ROOT = path.join(__dirname, '..');
const html = fs.readFileSync(path.join(ROOT, 'index.html'), 'utf8');
const dom = new JSDOM(html, { runScripts: 'outside-only', pretendToBeVisual: true });
const { window } = dom;
window.scrollTo = () => {};

// 手动注入脚本（模拟浏览器按顺序加载）
window.eval(fs.readFileSync(path.join(ROOT, 'data', 'policies.js'), 'utf8'));
window.eval(fs.readFileSync(path.join(ROOT, 'assets', 'app.js'), 'utf8'));

let pass = 0, fail = 0;
function ok(name, cond, extra) {
  if (cond) { pass++; console.log('  ✓ ' + name); }
  else { fail++; console.log('  ✗ ' + name + (extra ? '  -> ' + extra : '')); }
}
const $ = (s) => window.document.querySelector(s);
const $$ = (s) => Array.from(window.document.querySelectorAll(s));

(async function main(){
console.log('\n== 1. 初始渲染 ==');
const D = window.__POLICY_DATA__;
ok('数据已加载', D && D.policies.length > 1000, D && D.policies.length);
ok('栏目 tab 已渲染', $$('#tabs .tab').length >= 8, $$('#tabs .tab').length);
ok('首个 tab 处于选中态', !!$('#tabs .tab.on'));
ok('统计区有数字', $$('#stats .stat').length >= 5, $$('#stats .stat').length);

const cards0 = $$('#list .card');
ok('列表渲染出卡片', cards0.length === 40, cards0.length);
ok('卡片按年份分组', $$('#list .yeargroup').length > 0, $$('#list .yeargroup').length);
ok('结果计数栏非空', $('#resultbar').textContent.includes('共'));
ok('筛选下拉已填充', $$('#f-cat option').length > 5 && $$('#f-year option').length > 3,
   $$('#f-cat option').length + '/' + $$('#f-year option').length);

console.log('\n== 2. 栏目切换 ==');
const tabs = $$('#tabs .tab');
ok('存在「政策红头文件」栏目', tabs.some(t => t.textContent.includes('政策红头文件')));
ok('存在「申报通知」栏目', tabs.some(t => t.textContent.includes('申报通知')));
ok('存在「公示通知」栏目', tabs.some(t => t.textContent.includes('公示通知')));
ok('存在「领补贴通知」栏目', tabs.some(t => t.textContent.includes('领补贴通知')));
ok('存在「申报条件与好处」栏目', tabs.some(t => t.textContent.includes('申报条件与好处')));

function clickTab(text) {
  const t = $$('#tabs .tab').find(x => x.textContent.includes(text));
  t.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
  return t;
}
clickTab('政策红头文件');
let shown = $$('#list .card');
ok('红头文件栏目有内容', shown.length > 0, shown.length);
ok('红头文件栏目内类型一致',
   D.policies.filter(p => shown.some(c => c.querySelector('h3').textContent === p.title))
     .every(p => p.noticeType === '政策红头文件'));
ok('该栏目 tab 高亮', $$('#tabs .tab.on')[0].textContent.includes('政策红头文件'));

clickTab('申报通知');
ok('申报通知栏目有内容', $$('#list .card').length > 0, $$('#list .card').length);

clickTab('申报条件与好处');
ok('深度解读视图渲染', $$('#list .guide').length === D.guides.length, $$('#list .guide').length);
ok('解读卡片含「申报条件」', $('#list').innerHTML.includes('申报条件'));
ok('解读卡片含「政策好处」', $('#list').innerHTML.includes('政策好处'));
ok('筛选栏在解读视图隐藏', $('#filters').style.display === 'none');
clickTab('全部政策');
ok('回到列表后筛选栏恢复', $('#filters').style.display !== 'none');

console.log('\n== 3. 搜索与筛选 ==');
const q = $('#q');
function search(v) {
  q.value = v;
  q.dispatchEvent(new window.Event('input', { bubbles: true }));
}
// input 有 180ms 防抖，必须让事件循环跑起来
const tick = (ms) => new Promise(r => setTimeout(r, ms));
search('高新技术企业');
await tick(260);
ok('搜索「高新技术企业」有结果', $$('#list .card').length > 0, $$('#list .card').length);
// 搜索是跨字段的（标题/文号/类型/关键词/摘要），所以不能要求标题一定含关键词。
// 下面这条才是真正的约束：凡命中结果，其可检索字段里必须确实出现过关键词。
ok('命中记录在可检索字段中确实包含关键词',
   (function () {
     const terms = $$('#list .card h3').map(h => h.textContent);
     const hit = D.policies.filter(p => terms.includes(p.title));
     return hit.length > 0 && hit.every(p =>
       [p.title, p.docNo, p.category, (p.keywords || []).join(' '), p.summary]
         .join(' ').includes('高新技术企业'));
   })(),
   $$('#list .card h3').slice(0, 3).map(h => h.textContent).join(' | '));
ok('出现可清除的筛选标签', $$('#resultbar .chip').length > 0);

search('专精特新');
await tick(260);
ok('搜索「专精特新」有结果', $$('#list .card').length > 0, $$('#list .card').length);

search('沪科〔2026〕89号');
await tick(260);
ok('可按文号检索', $$('#list .card').length >= 1, $$('#list .card').length);

search('zzzz不存在的政策xyz');
await tick(260);
ok('无结果时显示空状态', !!$('#list .empty'), $('#list').textContent.slice(0, 40));

$('#reset').dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
await tick(60);
ok('重置后恢复全部', $$('#list .card').length === 40, $$('#list .card').length);

const sel = $('#f-year');
sel.value = '2025';
sel.dispatchEvent(new window.Event('change', { bubbles: true }));
await tick(60);
ok('按年份筛选生效', $$('#list .card').length > 0 && $('#list').textContent.includes('2025'));

$('#reset').dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
await tick(60);
const cat = $('#f-cat');
cat.value = '科技型中小企业';
cat.dispatchEvent(new window.Event('change', { bubbles: true }));
await tick(60);
ok('按政策类型筛选生效',
   $$('#list .card .tag.cat').every(t => t.textContent === '科技型中小企业'),
   $$('#list .card .tag.cat').length);

$('#reset').dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
await tick(60);

console.log('\n== 4. 详情抽屉 ==');
const card = $('#list .card');
card.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
await tick(60);
ok('抽屉已打开', $('#drawer').classList.contains('on'));
ok('遮罩已显示', $('#mask').classList.contains('on'));
const dtxt = $('#drawer').textContent;
ok('抽屉含「基本信息」', dtxt.includes('基本信息'));
ok('抽屉含「原文链接」', dtxt.includes('原文链接'));
ok('抽屉含免责提示', dtxt.includes('仅供检索参考'));
ok('抽屉含关闭按钮', !!$('#dclose'));
const link = $('#drawer a[href^="http"]');
ok('原文链接为 http(s)', !!link && /^https?:\/\//.test(link.getAttribute('href')),
   link && link.getAttribute('href'));
$('#mask').dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
await tick(60);
ok('点遮罩可关闭抽屉', !$('#drawer').classList.contains('on'));

console.log('\n== 5. 加载更多 ==');
$('#reset').dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
await tick(60);
const before = $$('#list .card').length;
const more = $('#more');
ok('存在「加载更多」按钮', !!more);
if (more) {
  more.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
  await tick(60);
  ok('加载更多后卡片增加', $$('#list .card').length > before,
     before + ' -> ' + $$('#list .card').length);
}

console.log('\n== 5b. 年份快捷条 ==');
$('#reset').dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
await tick(60);
const ybtns = $$('#yearbar .ybtn');
ok('年份按钮已渲染', ybtns.length >= 7, ybtns.length);
ok('含「全部」按钮', ybtns[0].dataset.y === '');
const y2024 = ybtns.find(b => b.dataset.y === '2024');
ok('存在 2024 按钮', !!y2024);
y2024.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
await tick(60);
ok('点年份后高亮切换', $$('#yearbar .ybtn.on')[0].dataset.y === '2024');
ok('列表只剩该年份', $$('#list .yearhead h2').every(h => h.textContent.startsWith('2024')),
   $$('#list .yearhead h2').map(h => h.textContent).join(','));
ok('年份分组显示该年总数（非分页数）',
   $$('#list .yearhead .c').every(c => /共 \d+ 条/.test(c.textContent)),
   $$('#list .yearhead .c').map(c => c.textContent).join('|'));

console.log('\n== 5c. 层级筛选 ==');
$('#reset').dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
await tick(60);
const lv = $('#f-level');
ok('存在层级下拉', !!lv);
lv.value = '区级';
lv.dispatchEvent(new window.Event('change', { bubbles: true }));
await tick(60);
const qjCards = $$('#list .card');
ok('区级筛选出记录', qjCards.length > 0, qjCards.length);
ok('区级筛选结果确实都是区级',
   qjCards.every(c => {
     const t = c.querySelector('h3').textContent;
     const p = D.policies.find(x => x.title === t);
     return p && p.level === '区级';
   }),
   qjCards.length + ' 张卡片');
lv.value = '市级';
lv.dispatchEvent(new window.Event('change', { bubbles: true }));
await tick(60);
ok('市级筛选有结果', $$('#list .card').length > 0, $$('#list .card').length);
$('#reset').dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
await tick(60);

console.log('\n== 6. 数据完整性 ==');
ok('每条都有标题', D.policies.every(p => p.title));
ok('每条都有可点击 URL',
   D.policies.every(p => /^https?:\/\//.test(p.url)));
ok('每条都有日期', D.policies.every(p => /^\d{4}-\d{2}-\d{2}$/.test(p.publishDate)));
ok('每条都有通知类型', D.policies.every(p => p.noticeType));
ok('至少 600 条含文号', D.policies.filter(p => p.docNo).length >= 600,
   D.policies.filter(p => p.docNo).length);
ok('至少 800 条含 PDF 链接', D.policies.filter(p => p.pdfUrls.length).length >= 800,
   D.policies.filter(p => p.pdfUrls.length).length);
ok('深度解读 ≥ 8 类', D.guides.length >= 8, D.guides.length);
ok('解读数据含来源标注',
   D.guides.every(g => (g.conditions || []).every(c => typeof c === 'string' || c.source)));
ok('覆盖 2020-2026', ['2020', '2021', '2022', '2023', '2024', '2025', '2026']
   .every(y => D.policies.some(p => p.year === y)));

console.log('\n' + '='.repeat(46));
console.log(`结果：${pass} 通过 / ${fail} 失败`);
console.log('='.repeat(46));
process.exit(fail ? 1 : 0);
})();
