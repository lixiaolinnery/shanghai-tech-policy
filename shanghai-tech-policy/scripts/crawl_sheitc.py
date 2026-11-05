#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""多源列表采集器：sheitc（经信委）各频道。"""
import json, re, sys, time, html as ihtml
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from crawl_list import fetch  # noqa

SHEITC_ITEM = re.compile(
    r'<li[^>]*>\s*<a\s+href="([^"]+)"\s+title="([^"]*)"[^>]*>\s*<div>.*?'
    r'<span>\s*(\d{4}-\d{2}-\d{2})\s*</span>',
    re.S)


def parse_sheitc(text, base, source, channel):
    out, seen = [], set()
    for m in SHEITC_ITEM.finditer(text):
        href, title, date = m.group(1), ihtml.unescape(m.group(2)).strip(), m.group(3)
        if not title:
            continue
        url = urljoin(base, href)
        if url in seen:
            continue
        seen.add(url)
        out.append({"title": title, "date": date, "url": url,
                    "source": source, "channel": channel})
    return out


def crawl_channel(channel, pages, worker=5):
    items, errs = [], []
    def job(i):
        u = (f"https://www.sheitc.sh.gov.cn/{channel}/index.html" if i == 1
             else f"https://www.sheitc.sh.gov.cn/{channel}/index_{i}.html")
        t = fetch(u)
        return parse_sheitc(t, u, "sheitc", channel)
    with ThreadPoolExecutor(max_workers=worker) as ex:
        futs = {ex.submit(job, i): i for i in range(1, pages + 1)}
        for f in as_completed(futs):
            i = futs[f]
            try:
                g = f.result()
                items.extend(g)
            except Exception as e:
                errs.append({"page": i, "error": str(e)})
    # dedupe by url
    seen, uniq = set(), []
    for x in items:
        if x["url"] in seen:
            continue
        seen.add(x["url"])
        uniq.append(x)
    return uniq, errs


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--channel")
    ap.add_argument("--pages", type=int)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    CH = {"cyfz": 85, "gg": 69, "bmgzjxgwj": 31, "sjxwxgwj": 11, "tzgg": 1}
    if a.channel:
        pages = a.pages or CH.get(a.channel)
        if not pages:
            print(f"未知频道 {a.channel}，请用 --pages 指定页数", file=sys.stderr)
            sys.exit(2)
        CH = {a.channel: pages}
    allitems, allerrs = [], []
    for ch, pages in CH.items():
        it, er = crawl_channel(ch, pages, a.workers)
        print(f"  sheitc/{ch}: {len(it)} items, {len(er)} errors", file=sys.stderr, flush=True)
        allitems.extend(it)
        allerrs.extend(er)
    seen, uniq = set(), []
    for x in allitems:
        if x["url"] in seen:
            continue
        seen.add(x["url"])
        uniq.append(x)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump({"source": "sheitc", "count": len(uniq),
                   "items": uniq, "errors": allerrs}, f, ensure_ascii=False, indent=1)
    print(f"[sheitc] total unique={len(uniq)} errors={len(allerrs)} -> {a.out}")
