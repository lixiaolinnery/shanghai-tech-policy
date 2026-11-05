#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""区级记录发布日期核验 / 校正。

区级站点列表页给的日期常是「栏目入库日」，与正文发布日不一致。
本脚本抓取每条记录的详情页，按优先级取：meta PubDate > 正文「发布时间/发布日期」
> 「成文日期/印发日期」，与记录现有 publishDate 比对。

用法：
  python3 scripts/verify_district_dates.py            # 只报告
  python3 scripts/verify_district_dates.py --fix      # 就地修正 data/district/*.json
"""
import json, os, re, sys, glob, subprocess, collections
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")

META_PUB = re.compile(
    r'<meta[^>]+name=["\'](?:PubDate|pubDate|publishdate|firstpublishedtime)["\'][^>]*>', re.I)
META_CONTENT = re.compile(r'content=["\']([^"\']+)["\']', re.I)
DATE_ANY = re.compile(r'(20\d{2})[-/年.](\d{1,2})[-/月.](\d{1,2})')

# 正文日期标签，按可信度从高到低。政府站「发布时间/发表时间」是单篇真实发布时间；
# 部分站点（如临港）的 <meta PubDate> 是模板固定值，必须优先读正文标签。
LABELS = ["发布日期", "成文日期", "印发日期", "发文日期", "发布时间", "发表时间",
          "录入时间", "更新时间"]


def norm(y, m, d):
    return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"


def fetch(url, timeout=30):
    p = subprocess.run(
        ["curl", "-sS", "-k", "-L", "--compressed", "-m", str(timeout),
         "-H", f"User-Agent: {UA}", url],
        capture_output=True, timeout=timeout + 12)
    raw = p.stdout
    for enc in ("utf-8", "gb18030"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


def page_date(html):
    """返回 (日期, 来源说明)。规则：正文标签优先，meta PubDate 兜底。

    原因：临港等站的 meta PubDate 是模板固定值（如 2022-12-31），
    而正文「发表时间」才是单篇的准确发布时间。
    """
    text = re.sub(r'<script.*?</script>', ' ', html, flags=re.S | re.I)
    text = re.sub(r'<style.*?</style>', ' ', text, flags=re.S | re.I)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = text.replace('&nbsp;', ' ')
    text = re.sub(r'\s+', ' ', text)          # 折叠空白，让标签与日期相邻

    for lb in LABELS:
        m = re.search(re.escape(lb) + r'\s*[：:]?\s*(.{0,40})', text)
        if m:
            dm = DATE_ANY.search(m.group(1))
            if dm:
                return norm(*dm.groups()), f"label:{lb}"

    for m in META_PUB.finditer(html):
        c = META_CONTENT.search(m.group(0))
        if c:
            dm = DATE_ANY.search(c.group(1))
            if dm:
                return norm(*dm.groups()), "meta"
    return "", ""


def judge(rec):
    url = rec["url"]
    try:
        html = fetch(url)
    except Exception as e:
        return {"url": url, "ok": False, "err": str(e)[:60]}
    pd, src = page_date(html)
    if not pd:
        return {"url": url, "ok": False, "err": "no-date-on-page"}
    return {"url": url, "ok": True, "pageDate": pd, "src": src,
            "recDate": rec.get("publishDate", ""),
            "match": pd == rec.get("publishDate", "")}


def main():
    do_fix = "--fix" in sys.argv
    files = sorted(glob.glob(os.path.join(ROOT, "data", "district", "district_*.json")))
    report, fixes = [], collections.defaultdict(dict)
    for f in files:
        recs = json.load(open(f, encoding="utf-8"))
        print(f"\n[{os.path.basename(f)}] {len(recs)} 条", flush=True)
        res = []
        with ThreadPoolExecutor(max_workers=10) as ex:
            futs = {ex.submit(judge, r): r for r in recs}
            for fu in as_completed(futs):
                res.append(fu.result())
        n_ok = sum(1 for r in res if r["ok"])
        n_match = sum(1 for r in res if r.get("match"))
        n_diff = n_ok - n_match
        n_nod = len(res) - n_ok
        print(f"  页面可取日期 {n_ok}/{len(res)}；与记录一致 {n_match}，不一致 {n_diff}，取不到日期 {n_nod}")

        # 迁移/模板日期防护：同一站点上 ≥3 条记录取到完全相同的「页面日期」，
        # 且各自的记录日期并不相同 —— 该页面日期是整站迁移日/模板值，不能用于覆盖。
        host_date = collections.Counter()
        for r in res:
            if r.get("ok") and not r.get("match"):
                host = r["url"].split("/")[2]
                host_date[(host, r["pageDate"])] += 1
        suspicious = {k for k, v in host_date.items() if v >= 3}
        if suspicious:
            print(f"  ⚠ 检测到疑似整站迁移/模板日期，已跳过：{sorted(suspicious)}")

        for r in res:
            if not (r.get("ok") and not r.get("match")):
                if not r.get("ok"):
                    print(f"    ? {r['err']}  {r['url'][:78]}")
                report.append(r)
                continue
            host = r["url"].split("/")[2]
            if (host, r["pageDate"]) in suspicious:
                print(f"    ⊘ 跳过（迁移日） {r['recDate']} (保留) vs {r['pageDate']}  {r['url'][:70]}")
            else:
                print(f"    ✗ {r['recDate']} -> {r['pageDate']} ({r['src']})  {r['url'][:78]}")
                fixes[os.path.basename(f)][r["url"]] = r["pageDate"]
            report.append(r)

    if do_fix and fixes:
        for f in files:
            base = os.path.basename(f)
            if base not in fixes:
                continue
            recs = json.load(open(f, encoding="utf-8"))
            n = 0
            for r in recs:
                if r["url"] in fixes[base]:
                    r["publishDate"] = fixes[base][r["url"]]
                    n += 1
            with open(f, "w", encoding="utf-8") as fh:
                json.dump(recs, fh, ensure_ascii=False, indent=1)
            print(f"  [已修正] {base}: {n} 条")
    total_fix = sum(len(v) for v in fixes.values())
    print(f"\n合计需修正 {total_fix} 条" + ("（已写入）" if do_fix else "（未写入，加 --fix 生效）"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
