#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""增量更新：抓最新通知 -> 重建站点 -> 验证链接 -> 部署到 Cloudflare Pages。

设计要点
--------
* **只抓最新几页**：新通知一律出现在各栏目列表最前面，所以增量模式每个源只抓
  前 N 页（见 sources.json 的 inc 字段），几分钟就能跑完；全量重抓用 --full。
* **原地合并**：抓到的新条目按 URL 去重后合并进现有 `data/raw/list_*.json`，
  不会丢掉历史数据。
* **缺什么补什么**：详情页按 URL 哈希缓存，已抓过的不重复请求；
  链接验活用 --incremental 只测没测过的。
* **区级默认不跑**：区级站点结构各异且容易触发 WAF，默认不纳入每日更新。

用法
----
    python3 scripts/update.py                # 增量更新并部署
    python3 scripts/update.py --no-deploy    # 只更新本地，不推线上
    python3 scripts/update.py --full         # 每个源全量重抓（慢，约 15 分钟）
    python3 scripts/update.py --skip-links   # 跳过链接验活（更快）
"""
import argparse
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import crawl_list as CL            # noqa: E402
import crawl_sheitc as SC          # noqa: E402

SRC_CFG = os.path.join(HERE, "sources.json")


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def load_json(path, default):
    if os.path.exists(path):
        try:
            return json.load(open(path, encoding="utf-8"))
        except Exception:
            pass
    return default


def crawl_one(cfg, incremental, workers=8):
    """抓一个源，返回 (新增条数, 总条数)。"""
    # 脚本型采集器（如文创站的 TrueCMS 接口）直接调脚本，它自己负责写 out 文件
    if cfg.get("runner") == "script":
        script = os.path.join(HERE, cfg["script"])
        before = len(load_json(os.path.join(ROOT, cfg["out"]), {"items": []}).get("items", []))
        subprocess.run([sys.executable, script], cwd=ROOT, capture_output=True)
        after_items = load_json(os.path.join(ROOT, cfg["out"]), {"items": []}).get("items", [])
        log(f"    {cfg['name']:22s} 脚本采集 -> 共 {len(after_items):3d} 条")
        return max(0, len(after_items) - before), len(after_items)

    pages = cfg["inc"] if incremental else cfg["max"]
    out_path = os.path.join(ROOT, cfg["out"])
    old = load_json(out_path, {"items": []})
    old_items = old.get("items", [])
    seen = {it["url"] for it in old_items}

    if cfg["runner"] == "sheitc":
        base = f"https://www.sheitc.sh.gov.cn/{cfg['channel']}/index"
        urls = [f"{base}.html"] + [f"{base}_{i}.html" for i in range(2, pages + 1)]
        parse = lambda t, u: SC.parse_sheitc(t, u, cfg["source"], cfg["channel"])  # noqa
    else:
        urls = CL.urls_from_pattern(cfg["pattern"], pages)
        dc = cfg.get("dateClass", "date")
        parse = lambda t, u: CL.parse_items(t, u, cfg["source"], cfg["channel"], dc)  # noqa

    fresh, errs = [], 0

    def job(u):
        return parse(CL.fetch(u), u)

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(job, u): u for u in urls}
        for f in as_completed(futs):
            try:
                fresh.extend(f.result())
            except Exception as e:
                errs += 1
                if errs <= 2:
                    log(f"    ! {futs[f]} :: {str(e)[:70]}")

    added = [it for it in fresh if it["url"] not in seen]
    merged = added + old_items          # 新条目放前面，便于肉眼看新增
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump({"source": cfg["source"], "channel": cfg["channel"],
                   "count": len(merged), "items": merged,
                   "errors": old.get("errors", [])}, fh, ensure_ascii=False, indent=1)
    log(f"    {cfg['name']:22s} 抓 {pages} 页 -> 新增 {len(added):3d} 条"
        + (f"（{errs} 页失败）" if errs else ""))
    return len(added), len(merged)


def stage_site():
    """生成只含运行必需文件的部署暂存目录。

    默认放在站点目录的上一级 `_pages`（本机用），可用环境变量 STAGE_DIR 覆盖
    （GitHub Actions 里会指到 workspace 下的某个目录）。
    """
    import shutil
    staging = os.environ.get("STAGE_DIR") or os.path.join(ROOT, "..", "_pages")
    if os.path.isdir(staging):
        shutil.rmtree(staging)
    os.makedirs(os.path.join(staging, "assets"), exist_ok=True)
    os.makedirs(os.path.join(staging, "data"), exist_ok=True)
    for rel in ["index.html", "README.md"]:
        src = os.path.join(ROOT, rel)
        if os.path.exists(src):
            shutil.copy2(src, staging)
    for rel in ["assets/style.css", "assets/app.js",
                "data/policies.js", "data/policies.json"]:
        src = os.path.join(ROOT, rel)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(staging, rel))
    return staging


def run(script, *args, title=None):
    cmd = [sys.executable, os.path.join(HERE, script)] + [str(a) for a in args]
    log(f"  $ {script} {' '.join(str(a) for a in args)}")
    p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    tail = [l for l in (p.stdout or "").strip().split("\n") if l.strip()][-3:]
    for l in tail:
        log(f"      {l}")
    if p.returncode != 0:
        log(f"      !! {script} 退出码 {p.returncode}")
        if p.stderr:
            log("      " + p.stderr.strip().split("\n")[-1][:200])
    return p.returncode


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true", help="每个源全量重抓")
    ap.add_argument("--no-deploy", action="store_true", help="不推送到 Cloudflare")
    ap.add_argument("--skip-links", action="store_true", help="跳过链接验活")
    ap.add_argument("--skip-district", action="store_true", help="跳过区级日期校正")
    ap.add_argument("--with-district", action="store_true",
                    help="顺便补抓区级记录的详情页（区级默认不参与每日更新，比较慢）")
    a = ap.parse_args()

    t0 = time.time()
    log("=" * 62)
    log(f"开始{'全量' if a.full else '增量'}更新" + ("" if a.no_deploy else "（完成后自动部署）"))
    log("=" * 62)

    cfg = json.load(open(SRC_CFG, encoding="utf-8"))

    log("[1/6] 抓取各源最新列表")
    total_new = 0
    for src in cfg["sources"]:
        try:
            n, _ = crawl_one(src, not a.full)
            total_new += n
        except Exception as e:
            log(f"    ! {src['name']} 抓取异常：{str(e)[:100]}")
    log(f"  本轮共新增 {total_new} 条列表条目")

    log("[2/6] 合并去重 + 分类")
    run("build_candidates.py", "2020,2021,2022,2023,2024,2025,2026")

    log("[3/6] 抓取新增条目的详情页（已抓过的走缓存）")
    run("fetch_details.py", "data/candidates_tech.json", 0, 12)
    # 区级站点不参与每日抓取，详情也没必要每天重抓；需要时用 --with-district
    if a.with_district and os.path.exists(os.path.join(ROOT, "data", "district_urls.json")):
        log("   （--with-district）顺便补抓区级详情")
        run("fetch_details.py", "data/district_urls.json", 0, 10)
    else:
        log("   跳过区级详情（区级不参与每日更新；需要时加 --with-district）")

    log("[4/6] 抽取结构化字段")
    run("extract_fields.py")

    log("[5/6] 生成站点数据")
    run("build_site.py")

    if not a.skip_links:
        log("[6/6] 链接验活（增量，只测新链接）")
        run("validate_links.py", "--incremental")
        run("build_site.py")          # 应用验活结果
    else:
        log("[6/6] 跳过链接验活")

    meta = load_json(os.path.join(ROOT, "data", "policies.json"), {}).get("meta", {})
    log(f"  当前数据：{meta.get('total')} 条"
        f"（市级 {sum(1 for p in load_json(os.path.join(ROOT,'data','policies.json'),{}).get('policies',[]) if p.get('level')=='市级')}"
        f" / 区级 {sum(1 for p in load_json(os.path.join(ROOT,'data','policies.json'),{}).get('policies',[]) if p.get('level')=='区级')}）"
        f"，深度解读 {len(load_json(os.path.join(ROOT,'data','policies.json'),{}).get('guides',[]))} 类")

    staging = stage_site()
    log(f"  已生成部署暂存目录：{staging}")

    if not a.no_deploy:
        log("部署到 Cloudflare Pages")
        token = os.environ.get("CF_API_TOKEN")
        acct = os.environ.get("CF_ACCOUNT_ID")
        if not token or not acct:
            log("  ! 缺少 CF_API_TOKEN / CF_ACCOUNT_ID，跳过部署")
        else:
            updater = os.path.join(ROOT, "..", "deploy-pages.js")
            if not os.path.exists(updater):
                log("  ! 找不到 deploy-pages.js（Actions 环境下请改用 wrangler 部署）")
            else:
                p = subprocess.run(["node", updater, "shanghai-tech-policy", staging],
                                   cwd=os.path.join(ROOT, ".."),
                                   capture_output=True, text=True)
                for l in (p.stdout or "").strip().split("\n")[-6:]:
                    log(f"      {l}")
                if p.returncode != 0:
                    log("      !! 部署失败：" + (p.stderr or "")[-200:])

    log("=" * 62)
    log(f"更新完成，耗时 {time.time() - t0:.0f} 秒")
    log("=" * 62)
    return 0


if __name__ == "__main__":
    sys.exit(main())
