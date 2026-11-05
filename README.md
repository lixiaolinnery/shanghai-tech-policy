# 上海科技政策查询站（自动更新）

https://shanghai-tech-policy.pages.dev

本仓库由 GitHub Actions 定时（北京时间 09:00–18:00 每小时）执行增量抓取，
重新生成 `shanghai-tech-policy/data/policies.json` / `policies.js` 并部署到 Cloudflare Pages。

手动触发：Actions → update-policy-site → Run workflow

需要两个仓库密钥（Settings → Secrets and variables → Actions）：
- `CLOUDFLARE_API_TOKEN`（Cloudflare Pages:Edit 权限）
- `CLOUDFLARE_ACCOUNT_ID`

本地运行：`python3 shanghai-tech-policy/scripts/update.py`（需要根目录 `deploy-pages.js` 与 `node_modules`）
