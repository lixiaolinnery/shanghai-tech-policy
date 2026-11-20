// 兜底触发器：Cloudflare Workers 定时检查 GitHub Actions 是否按时跑过，
// 超过 55 分钟没有新运行就手动 dispatch 一次工作流。
const REPO = 'lixiaolinnery/shanghai-tech-policy';
const WORKFLOW = 'update.yml';

async function latestRun(headers) {
  const res = await fetch(`https://api.github.com/repos/${REPO}/actions/runs?per_page=5`, {
    headers: { 'User-Agent': 'dsh-policy-watchdog', Accept: 'application/vnd.github+json', ...headers }
  });
  if (!res.ok) return { error: res.status };
  const data = await res.json();
  const runs = data.workflow_runs || [];
  return { runs };
}

async function check(env) {
  const headers = env.GITHUB_TOKEN ? { Authorization: `Bearer ${env.GITHUB_TOKEN}` } : {};
  const info = await latestRun(headers);
  if (info.error) return { ok: false, step: 'list-runs', status: info.error };
  const now = Date.now();
  const newest = info.runs[0];
  const ageMin = newest ? (now - new Date(newest.created_at).getTime()) / 60000 : 9999;
  if (ageMin < 25) return { ok: true, skipped: true, ageMin: Math.round(ageMin), last: newest.created_at, event: newest.event };
  const res = await fetch(`https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW}/dispatches`, {
    method: 'POST',
    headers: { 'User-Agent': 'dsh-policy-watchdog', Accept: 'application/vnd.github+json', 'Content-Type': 'application/json', ...headers },
    body: JSON.stringify({ ref: 'main' })
  });
  return { ok: res.ok, dispatched: res.status, ageMin: Math.round(ageMin), last: newest ? newest.created_at : null };
}

export default {
  async scheduled(event, env, ctx) {
    const out = await check(env);
    console.log('watchdog', JSON.stringify(out));
  },
  async fetch(request, env) {
    const out = await check(env);
    return new Response(JSON.stringify(out, null, 2), { headers: { 'Content-Type': 'application/json; charset=utf-8' } });
  }
};
