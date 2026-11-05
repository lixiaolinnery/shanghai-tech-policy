#!/usr/bin/env node
/**
 * 用 Cloudflare Pages 官方 Direct Upload 协议部署静态站点。
 *
 * 为什么不用 wrangler：它依赖的 workerd 不支持 Android，装不上。
 * 这里按 wrangler 内部实现（v3 pages/upload.ts + pages/deploy.ts）复刻协议：
 *
 *   1. GET  /accounts/{aid}/pages/projects/{proj}/upload-token   -> { jwt }
 *   2. POST /pages/assets/check-missing   { hashes }            -> 缺失的 hash
 *   3. POST /pages/assets/upload          [{key,value(base64),metadata:{contentType},base64:true}]
 *   4. POST /pages/assets/upsert-hashes   { hashes }
 *   5. POST /accounts/{aid}/pages/projects/{proj}/deployments
 *          multipart：manifest(JSON 字符串) + branch    ← 只放清单，不带文件内容
 *
 * 文件 hash 规则（wrangler src/pages/hash.ts）：
 *   blake3( base64(内容) + 扩展名(不含点) ).hex.slice(0,32)
 *
 * 用法：
 *   CF_API_TOKEN=xxx CF_ACCOUNT_ID=yyy node deploy-pages.js [项目名] [站点目录]
 * token 需要的权限：Account → Cloudflare Pages → Edit
 */
'use strict';
const fs = require('fs');
const path = require('path');
const { blake3 } = require('@noble/hashes/blake3.js');

const TOKEN = process.env.CF_API_TOKEN;
const ACCOUNT = process.env.CF_ACCOUNT_ID;
const PROJECT = process.argv[2] || 'shanghai-tech-policy';
const SITE = path.resolve(process.argv[3] || 'shanghai-tech-policy');
const BRANCH = process.env.CF_BRANCH || 'main';
const API = 'https://api.cloudflare.com/client/v4';

const MIME = {
  '.html': 'text/html', '.htm': 'text/html', '.js': 'application/javascript',
  '.mjs': 'application/javascript', '.css': 'text/css', '.json': 'application/json',
  '.svg': 'image/svg+xml', '.png': 'image/png', '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg', '.gif': 'image/gif', '.ico': 'image/x-icon',
  '.woff': 'font/woff', '.woff2': 'font/woff2', '.txt': 'text/plain',
  '.md': 'text/markdown', '.pdf': 'application/pdf', '.webp': 'image/webp'
};
// wrangler 的 Pages 忽略清单
const IGNORE = ['_worker.js', '_routes.json', 'functions', '**/.DS_Store',
                '**/node_modules', '**/.git'];

function contentType(name) {
  return MIME[path.extname(name).toLowerCase()] || 'application/octet-stream';
}

/** wrangler src/pages/hash.ts */
function hashFile(buf, filepath) {
  const ext = path.extname(filepath).substring(1);
  const payload = buf.toString('base64') + ext;
  return Buffer.from(blake3(new TextEncoder().encode(payload)))
    .toString('hex').slice(0, 32);
}

function walk(dir, base = '') {
  const out = [];
  for (const name of fs.readdirSync(dir)) {
    const full = path.join(dir, name);
    const rel = base ? `${base}/${name}` : name;
    if (IGNORE.some((p) => rel === p || rel.endsWith('/' + p))) continue;
    const st = fs.statSync(full);
    if (st.isDirectory()) out.push(...walk(full, rel));
    else if (st.isFile() && !name.startsWith('.')) out.push({ rel, full, size: st.size });
  }
  return out;
}

async function api(url, opts = {}) {
  const res = await fetch(url, {
    ...opts,
    headers: { Authorization: `Bearer ${opts.jwt || TOKEN}`, ...(opts.headers || {}) }
  });
  const text = await res.text();
  let json;
  try { json = JSON.parse(text); } catch { json = { raw: text.slice(0, 400) }; }
  return { status: res.status, json };
}

async function ensureProject() {
  const get = await api(`${API}/accounts/${ACCOUNT}/pages/projects/${PROJECT}`);
  if (get.json.success) { console.log(`  ✓ 项目已存在：${PROJECT}`); return; }
  const create = await api(`${API}/accounts/${ACCOUNT}/pages/projects`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: PROJECT, production_branch: BRANCH })
  });
  if (create.json.success) { console.log('  ✓ 项目已创建'); return; }
  const codes = (create.json.errors || []).map((e) => e.code);
  if (codes.some((c) => [8000007, 8000019].includes(c))) {
    console.log('  ✓ 项目已存在'); return;
  }
  throw new Error('创建项目失败: ' + JSON.stringify(create.json.errors));
}

(async () => {
  if (!TOKEN || !ACCOUNT) {
    console.error('缺少环境变量：需要 CF_API_TOKEN 与 CF_ACCOUNT_ID');
    process.exit(2);
  }
  if (!fs.existsSync(path.join(SITE, 'index.html'))) {
    console.error('站点目录里没有 index.html：' + SITE);
    process.exit(2);
  }

  console.log('检查 token ...');
  const v = await api(`${API}/user/tokens/verify`);
  if (!v.json.success) throw new Error('token 校验失败：' + JSON.stringify(v.json.errors));
  console.log('  ✓ token 有效：' + v.json.result.status);

  await ensureProject();

  // 1) 收集文件 + 算 hash
  const files = walk(SITE);
  const total = files.reduce((a, f) => a + f.size, 0);
  const items = files.map((f) => {
    const buf = fs.readFileSync(f.full);
    const name = f.rel.split(path.sep).join('/');
    return { name, buf, size: f.size, hash: hashFile(buf, f.full), type: contentType(name) };
  });
  console.log(`  待部署 ${items.length} 个文件 / ${(total / 1024 / 1024).toFixed(2)} MB`);

  // 2) 取上传用 JWT
  console.log('获取上传凭证 ...');
  const t = await api(`${API}/accounts/${ACCOUNT}/pages/projects/${PROJECT}/upload-token`);
  if (!t.json.success) throw new Error('获取 upload-token 失败：' + JSON.stringify(t.json.errors));
  const jwt = t.json.result.jwt;
  console.log('  ✓ 已获取');

  // 3) 查缺失（内容寻址，已存在的不用重传）
  const hashes = items.map((i) => i.hash);
  const chk = await api(`${API}/pages/assets/check-missing`, {
    method: 'POST', jwt,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ hashes })
  });
  if (!chk.json.success) throw new Error('check-missing 失败：' + JSON.stringify(chk.json.errors));
  const missing = new Set(chk.json.result || []);
  const toUpload = items.filter((i) => missing.has(i.hash));
  console.log(`  需上传 ${toUpload.length} 个（${items.length - toUpload.length} 个已在云端）`);

  // 4) 上传缺失资源（分桶，wrangler 用 3 并发 / 单桶 ~50MiB）
  const MAX_BUCKET = 40 * 1024 * 1024;
  const buckets = [];
  let cur = { size: 0, list: [] };
  for (const it of [...toUpload].sort((a, b) => b.size - a.size)) {
    if (cur.size + it.size > MAX_BUCKET && cur.list.length) { buckets.push(cur); cur = { size: 0, list: [] }; }
    cur.list.push(it); cur.size += it.size;
  }
  if (cur.list.length) buckets.push(cur);

  for (let bi = 0; bi < buckets.length; bi++) {
    const payload = buckets[bi].list.map((it) => ({
      key: it.hash,
      value: it.buf.toString('base64'),
      metadata: { contentType: it.type },
      base64: true
    }));
    const r = await api(`${API}/pages/assets/upload`, {
      method: 'POST', jwt,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    if (!r.json.success) throw new Error('assets/upload 失败：' + JSON.stringify(r.json.errors));
    console.log(`  已上传分桶 ${bi + 1}/${buckets.length}（${buckets[bi].list.length} 个文件）`);
  }

  // 5) 登记 hash
  if (toUpload.length) {
    const up = await api(`${API}/pages/assets/upsert-hashes`, {
      method: 'POST', jwt,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ hashes })
    });
    if (!up.json.success) console.warn('  ! upsert-hashes 失败（不影响本次访问）：' + JSON.stringify(up.json.errors));
    else console.log('  ✓ hash 已登记');
  }

  // 6) 创建部署：multipart 里只放 manifest
  const manifest = {};
  for (const it of items) manifest['/' + it.name] = it.hash;

  const form = new FormData();
  form.append('manifest', JSON.stringify(manifest));
  form.append('branch', BRANCH);

  console.log('创建部署 ...');
  // 注意：/pages/assets/* 用上传 JWT，而创建部署要用 API token（wrangler 亦如此）
  const dep = await api(`${API}/accounts/${ACCOUNT}/pages/projects/${PROJECT}/deployments`, {
    method: 'POST', body: form
  });
  if (!dep.json.success) throw new Error('部署失败：' + JSON.stringify(dep.json.errors, null, 2));

  const r = dep.json.result;
  console.log('\n部署成功 ✅');
  console.log('  生产地址 : https://' + PROJECT + '.pages.dev');
  console.log('  本次部署 : ' + r.url);
  console.log('  部署 ID  : ' + r.id);
  console.log('  文件数   : ' + Object.keys(manifest).length);
})().catch((e) => {
  console.error('\n' + e.message);
  process.exit(1);
});
