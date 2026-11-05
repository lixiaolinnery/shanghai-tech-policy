# 上海科技政策查询

一站式检索**上海市科技类政策**的静态网页。数据来自政府官网公开页面，由脚本自动采集整理，每条记录都保留**官网原文链接**（1618/1618 条），其中 1133 条另有**红头文件 / 原文 PDF 链接**。

## 快速开始

**方式一：直接打开（推荐，零依赖）**

双击 `index.html` 即可。数据已内联在 `data/policies.js`，无需服务器、无需联网。

**方式二：本地起服务**（便于手机/局域网访问）

```bash
python3 -m http.server 8899 --bind 127.0.0.1
# 浏览器打开 http://127.0.0.1:8899/
```

**方式三：发布到公网 —— 已部署在 Cloudflare Pages**

**线上地址：https://shanghai-tech-policy.pages.dev**

本站是纯静态的、没有任何后端，最适合放 CDN。当前托管在 Cloudflare Pages（免费额度足够），
由仓库外的 `../deploy-pages.js` 推送，不依赖任何本机进程长期运行。

更新线上版本：

```bash
cd ..                                  # default-workspace
node deploy-pages.js shanghai-tech-policy _pages
```

`_pages/` 是只含站点运行必需文件的暂存目录（`index.html` + `assets/` + `data/policies.{js,json}` + `README.md`）。
`deploy-pages.js` 复刻了 Cloudflare Pages 的 Direct Upload 协议：先按内容哈希把资源传到
`/pages/assets/upload`，再用 manifest 创建部署。**不要直接传整个项目目录**——里面有 1485 个抓取
中间文件（约 36MB），传上去没有意义。

> 为什么不用官方 `wrangler`：它依赖的 `workerd` 不支持 Android，装不上。
> 为什么不用 Cloudflare Tunnel（`cloudflared`）：本机 `/etc` 指向只读的 `/system/etc`，
> 没有 `resolv.conf`，Go 的解析器回落到 `::1:53` 直接失败。

<details>
<summary>备选方案：SSH 反向隧道（临时地址，仅供本机验证）</summary>

```bash
cd ..                    # default-workspace
bash bin/public.sh       # 启动本地服务 + serveo 隧道；Ctrl-C 结束
```

`../serve.js` 是带 brotli/gzip 的静态服务器：数据文件 `data/policies.js` 原始 1984544 B，
Python 自带的 `http.server` 不压缩，经移动网络隧道首屏要 12 秒以上；`serve.js` 用 brotli q10
压到 234823 B（约 1/8.5），实测约 2 秒。

但 serveo 免费隧道约 1 小时到期即断、重连后地址会变，且子域名里会带本机公网 IP，
**不适合对外分享**，只用于临时验证。
</details>

## 自动更新

线上站点支持**每天定时增量更新**，无需人工干预。

```bash
cd ..                                    # default-workspace
bash bin/start-scheduler.sh              # 启动，默认每天 09:00-18:00 每小时一次（10 次）
bash bin/start-scheduler.sh 09:00-18:00  # 区间写法：每小时一次，含两端
bash bin/start-scheduler.sh 09:00,12:00,18:00   # 逗号分隔指定时刻
bash bin/start-scheduler.sh 08:30        # 只保留一个时间点
# 幂等：已在跑就不会重复启动；要改时间先 kill 掉再跑
```

**默认每天 09:00–18:00 每小时跑一次，共 10 次**（申报季通知更新频繁，按小时跟进）。
因为轮询密集，每轮每个栏目只抓**最新 2 页**（`sources.json` 的 `inc`）——即使某轮漏掉，
下一小时它仍在最新页里会被重新捞到，所以不会丢。
另外带**补跑**：设备关机或 App 被杀后重启，若距上次成功更新超过 20 小时会立刻补一次。

调度器每轮做的事（实测 **20–30 秒**）：

1. 抓各栏目**最新几页**（新通知都在列表最前，见 `scripts/sources.json` 的 `inc` 字段）
2. 新条目按 URL 去重后**原地合并**进 `data/raw/*.json`，历史数据不丢
3. 只为新增条目抓详情页（其余走 URL 哈希缓存；失败过的 7 天内不重试）
4. 重新分类 → 抽取字段 → 生成 `policies.json` / `policies.js`
5. **增量链接验活**（只测没测过的链接）
6. 部署到 Cloudflare Pages

也可以手动跑：

```bash
cd shanghai-tech-policy
python3 scripts/update.py                 # 增量更新 + 部署
python3 scripts/update.py --no-deploy     # 只更新本地
python3 scripts/update.py --full          # 每个源全量重抓（约 15 分钟）
python3 scripts/update.py --skip-links    # 跳过验活，更快
python3 scripts/update.py --with-district # 顺带补抓区级详情
```

日志在 `../logs/`：`scheduler.log` 看调度与结果，`update-YYYY-MM-DD.log` 看每轮明细。

### 掉线自愈

调度器是普通后台进程，**App 被系统杀掉时会一起消失**。为此加了一个自愈钩子：
`~/.profile` 里放了一段逻辑，每次启动登录 shell 时检查调度器是否在跑，没跑就自动拉起
（幂等，已在跑不会重复启动；日志见 `../logs/profile-autostart.log`）。

所以 App 重新打开后通常会自愈；万一没有，手动跑一次即可：

```bash
cd /data/user/0/com.dsh.android/files/workspace/deepseek-harness/default-workspace
bash bin/start-scheduler.sh
```

调度器启动时带**补跑**：距上次成功更新超过 20 小时，会立刻补跑一次，然后再进入日程。

### ⚠️ 关于可靠性的实话

调度器是跑在**这台设备**上的常驻进程，所以：

- 设备息屏/睡着、断网、或 DSH App 被杀掉，**更新就会停**；
- App 重启后重新执行一次 `bash bin/start-scheduler.sh` 即可恢复（脚本有补跑逻辑：
  距上次成功更新超过 20 小时，启动时会立刻补一次）；
- 不适合当作 7×24 的生产级定时任务。

**要真正无人值守，应该把这套脚本搬到 GitHub Actions**：定时 workflow 每天拉取 →
跑同样的 `update.py --no-deploy` → 用 `cloudflare/wrangler-action` 或直接调 Pages API 部署。
那样不依赖任何本地设备，失败了 GitHub 还会发邮件告警。需要的话给我一个 GitHub token，
我可以把 workflow 和代码一起准备好。

### 为什么不用系统 cron

这台设备上的 cronie 把 spool 路径编译死成 `/data/data/com.termux/files/usr/var/spool/cron`
（标准 Termux 前缀），而实际前缀是 `/data/user/0/com.dsh.android/files/termux/usr`，
`crontab` 一执行就报 `No such file or directory`，没法用。所以调度器自己维护常驻循环。
（`bin/public.sh` 里那条临时 SSH 隧道方案仍在，但只建议用于本机验证。）

## 手动更新（点一下就行）

自动更新靠不住的时候，用这个。**两种点法，任选**：

### 方式一：手机浏览器里的按钮（推荐）

```bash
cd /data/user/0/com.dsh.android/files/workspace/deepseek-harness/default-workspace
bash bin/打开控制台.sh
```

它会启动本机控制台并打印地址，用手机浏览器打开：

```
http://127.0.0.1:8899/
```

拉到页面最下方，有一个 **「立即更新」** 按钮。点一下就会：抓取最新政策 → 重建站点 →
部署到 Cloudflare Pages，页面上会实时滚动日志，完成后自动刷新。

> 公网版页面最下方也留了一个「在本机打开更新控制台 →」的链接，可以直接跳过来。
> 但本机控制台必须先跑起来（即上面那条命令）。

### 方式二：一条命令

```bash
bash bin/更新数据.sh
```

跑完打印条数、耗时和线上地址。失败会明确报错，**线上保留上一次成功的版本**。

### 两种方式的区别

| | 控制台按钮 | 命令行 |
|---|---|---|
| 需要开浏览器 | 是 | 否 |
| 能看到实时日志 | 是（页面滚动） | 是（终端输出） |
| 适合 | 手机上随手点一下 | 电脑/终端操作 |

### 为什么公网版页面上的按钮不能直接更新

Cloudflare Pages 只托管静态文件，浏览器无法连回这台手机去启动 Python 进程。
所以公网页面上的按钮改成了**隐藏**（不再出现点了没反应的死按钮），只显示数据生成时间和
「已滞后 N 天」提示；真要更新就走上面的本机控制台。

## 栏目## 栏目

| 栏目 | 说明 |
|---|---|
| 全部政策 | 全部记录，按年份倒序分组 |
| 政策红头文件 | 管理办法、实施细则、若干措施、工作指引等规范性文件 |
| 申报通知 | 各年度组织申报 / 认定 / 评价 / 培育工作的通知 |
| 公示通知 | 拟认定、拟入库、拟支持、拟立项、拟更名等公示 |
| 领补贴通知 | 资金下达、拨付、兑现、贴息、财政奖励等 |
| 补贴与资金 | 标题或类型涉及资金/经费/补贴/资助/奖励的全部记录 |
| 立项与评价 | 立项通知、绩效评价、评估结果 |
| 名单公布 | 认定名单、入库公告、结果公布 |
| **申报条件与好处** | 按政策类型汇总的深度解读：申报条件、政策好处、时间窗口、材料清单，每条标注来源文件与文号；并可一键跳到本站相关通知 |

列表页还提供**年份快捷条**（各年条数一目了然）、关键词搜索（支持按文号检索）、政策类型 / 层级（市级·区级）/ 年份 / 数据来源 / 发布单位多维筛选。

## 当前数据规模

> 以下数字来自 `data/policies.json` 的 `meta` 字段，重建后请以该字段为准。

| 指标 | 数值 |
|---|---|
| 政策记录 | **3182 条**（市级 2572 + 区级 610） |
| 覆盖年份 | 2016–2026（2020 年起每年 374–578 条） |
| 政策类型 | **34 类** |
| 区级覆盖 | **16 个区 + 临港新片区（全覆盖）** |
| 含文号 | 1158 条 |
| 附红头文件 / 原文 PDF | 1833 条 |
| 含结构化抽取字段 | 1014 条 |
| 深度解读 | **21 类**政策（含申报条件与政策好处） |
| 链接验活 | 5631 / 5657 直接返回 200（99.5%） |

年度分布：2015(1) · 2016(1) · 2018(13) · 2019(6) · 2020(406) · 2021(414) · 2022(444) · 2023(459) · 2024(466) · 2025(578) · 2026(374)

链接验活结果存于 `data/linkcheck.json`，分三类：

| 类别 | 数量 | 页面表现 |
|---|---|---|
| `dead`（HTTP 404） | 2 条（市科委两个 PDF 附件） | 卡片与详情页**标红提示失效** |
| `unverified`（403 限流 / 超时） | 24 条（嘉定 `keji./jingwei.jiading.cn` 22 条、崇明 1、静安 1） | **不标红**；详情页注明「采集时已验证可访问，本轮复检因该站限流未能重新确认」 |
| `sslUnverified`（本机 CA 证书链不全，需跳过校验） | 110 条 | **不标红**；内容正常 |

## 政策覆盖



**市级**：高新技术企业、专精特新中小企业、创新型中小企业、科技型中小企业、科技小巨人（含培育）、科技型中小企业技术创新资金、科技创新券、研发费用加计扣除、科技金融、创新载体与孵化器、研发机构与实验室、科技成果转化、知识产权、科技奖励、科技计划项目、科普、科技人才。

**市 + 区两级（用户点名补充的第一批）**：

| 类型 | 市级 | 区级 | 合计 |
|---|---|---|---|
| 企业技术中心 | 26 | 69 | 95 |
| 专利试点示范 | 29 | 17 | 46 |
| 重大产业攻关 | 20 | 13 | 33 |
| 揭榜挂帅 | 22 | 22 | 44 |
| 制造业单项冠军 | 11 | 7 | 18 |

**市 + 区两级（用户点名补充的第二批）**：

| 类型 | 市级 | 区级 | 合计 |
|---|---|---|---|
| 文化创意资金 | 55 | 29 | 84 |
| 服务业引导资金 | 24 | 48 | 72 |
| 创新创业大赛（中国创新创业大赛、创客中国等） | 37 | 19 | 56 |
| 「创·在上海」国际创新创业大赛 | 10 | 16 | 26 |
| 张江示范区 | 25 | 35 | 60 |
| 技术改造（含技术先进性改造、设备更新） | 16 | 43 | 59 |
| 产学研合作 | 7 | 28 | 35 |
| 专精特新「小巨人」 | 4 | 15 | 19 |
| 张江科学城 | 6 | 2 | 8 |

数据源：上海市科学技术委员会、上海市经济和信息化委员会、上海市知识产权局、
上海市人民政府（政策文件库）、**上海市文化创意产业推进领导小组办公室**（cms.odb.sh.cn，新增），
以及 16 个区 + 临港新片区的区科委 / 区经委 / 区市场监管局 / 区文旅局官网。

**「创·在上海」单独成类**：它是上海规模最大的创新创业赛事（市科委主办、市科技创业中心承办），
与中国创新创业大赛上海赛区、创客中国上海赛区是**不同赛事**，站内已拆开，未混为一谈。
覆盖 2021–2026 六届，含市级征集/举办通知、获奖名单、以赛代评的创新资金立项，以及各赛区的
赛点遴选、赛程安排、晋级复赛名单公示。

> 注：**专精特新「小巨人」**（工信部国家级）与 **科技小巨人**（市科委）、**专精特新中小企业**（市级）
> 是三个不同层级的资质，站内分列为独立政策类型，未混用。

## 目录结构

```
index.html              站点入口
assets/
  style.css             样式
  app.js                前端逻辑（无依赖，原生 JS）
data/
  policies.js           ★ 最终数据（内联 JS，供页面直接加载）
  policies.json         同一份数据的 JSON 版本（供二次开发）
  district/             区级采集结果（构建时并入 policies）
  guides/               深度解读原始数据（逐条核实官方文件后写入）
  candidates_all.json   去重后全部条目（未做科技类筛选）
  candidates_tech.json  筛选后的科技类政策条目
  details/              每篇原文的抓取与抽取结果（正文、文号、PDF、时间、金额）
  extracted.json        申报条件/好处/材料/时间的章节抽取结果
  linkcheck.json        链接验活报告
  raw/                  列表页采集原始结果（市级）
  district_urls.json    区级记录 URL 清单（供 fetch_details 抓详情）

> `details/`、`raw/`、`extracted.json` 是管线中间产物，保留以支持增量重建与复核；
> 抓取过程中产生的大量原始 HTML 与区级采集临时文件已清理，`fetch_details.py`
> 需要时会重新生成 `text/`。交付时整个目录约 28 MB。
scripts/
  crawl_list.py         通用列表页采集器（curl 后端）
  crawl_sheitc.py       市经信委频道采集器
  build_candidates.py   合并去重 + 政策类型/通知类型分类
  fetch_details.py      详情页抓取 + 文号/单位/PDF/时间/金额抽取
  extract_fields.py     申报条件/好处/材料/时间 章节抽取
  build_site.py         汇总生成 policies.json / policies.js
  validate_links.py     全量链接验活（带重试 + SSL 证书链回退）
  verify_district_dates.py 区级记录发布日期核验/校正（含迁移日防护）
  district_crawl.py     区级站点列表采集
  district_harvest/     区级各站点的专项采集脚本（按区/批次归档，共 34 个，可复跑）
tests/
  dom.test.js           jsdom 真实 DOM 功能测试（61 项）
  acceptance.py         交付验收断言（54 项）
```

### 数据规模

| 项 | 值 |
|---|---|
| 市级来源 | 上海市科学技术委员会（stcsm.sh.gov.cn）、上海市经济和信息化委员会（sheitc.sh.gov.cn） |
| 区级来源 | 浦东、徐汇、闵行、嘉定、松江、杨浦、普陀、奉贤、长宁、宝山、静安、临港新片区官网 |

**已知局限**：
- 区级采集覆盖 11 个区 + 临港新片区，**未覆盖黄浦、虹口、金山、青浦、崇明 5 个区**。
- 明细页的「申报条件 / 政策好处 / 材料清单 / 时间节点」为**程序自动抽取**，页面已明确标注，权威口径请以「申报条件与好处」栏目或官网原文为准。
- 2 条红头文件 PDF 链接已 404，页面会标红提示。

## 数据字段

```jsonc
{
  "title": "关于开展2026年度高新技术企业认定管理相关工作的通知",
  "docNo": "沪科〔2026〕89号",
  "issuer": "上海市科学技术委员会",
  "publishDate": "2026-04-30",
  "year": "2026",
  "category": "高新技术企业",
  "noticeType": "申报通知",
  "level": "市级",              // 市级 / 区级
  "district": "",               // 区级政策填写区名
  "url": "https://...",         // 官网原文页
  "pdfUrls": ["https://..."],   // 红头文件 / 原文 PDF
  "attachments": [{"name": "", "url": ""}],
  "conditions": ["申报条件要点"],
  "benefits": ["政策好处要点"],
  "materials": ["申报材料清单"],
  "timeline": ["申报时间说明"],
  "timeHints": ["2026-10-10"],  // 正文中抽取到的时间点
  "moneyHints": ["50 万元"],    // 正文中抽取到的金额
  "depth": "full",              // full=有结构化字段；basic=仅机械抽取
  "isFunding": true
}
```

## 重新构建

```bash
# 1. 采集列表
python3 scripts/crawl_list.py --pattern "https://stcsm.sh.gov.cn/zwgk/tzgs/gsgg/index_{i}.html" \
    --pages 181 --source stcsm --channel 通知告示 --out data/raw/list_stcsm.json

# 2. 分类筛选
python3 scripts/build_candidates.py 2020,2021,2022,2023,2024,2025,2026

# 3. 抓详情 + 抽取 + 构建
python3 scripts/fetch_details.py data/candidates_tech.json 0 10
python3 scripts/extract_fields.py
python3 scripts/build_site.py

# 4. 校验
node tests/dom.test.js
python3 scripts/validate_links.py
```

## 测试

```bash
# 交付验收（数据完整性、栏目覆盖、字段质量、链接可访问率）
python3 tests/acceptance.py

# 前端功能测试（jsdom 真实 DOM）
pnpm add jsdom --store-dir ../.pnpm-store/v11   # 首次
node tests/dom.test.js

# 全量链接验活（约 3 分钟）
python3 scripts/validate_links.py
```

`tests/dom.test.js` 覆盖 61 项：初始渲染、9 个栏目切换、关键词搜索、文号检索、年份快捷条、年份/类型/层级筛选、空状态、详情抽屉开合与交叉跳转、加载更多、数据完整性。

`tests/acceptance.py` 覆盖 54 项验收断言。

## 免责声明

本站是政策**检索工具**，不构成申报依据或法律意见。申报条件、补贴金额、时间窗口可能随时调整，请务必点击「官网原文」核对最新要求。所有内容版权归原发布单位所有。
