#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""通用政府站列表页采集器：抓取列表页 -> 结构化条目 (title, date, url, source, channel)."""
import argparse, json, re, sys, time, html as ihtml
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin
import urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")

def fetch(url, timeout=25, retries=2):
    """用 curl 抓取（比 urllib 在部分政府站快 20 倍以上）。失败回退 urllib。"""
    last = None
    for i in range(retries + 1):
        try:
            return _fetch_curl(url, timeout)
        except Exception as e:  # noqa
            last = e
            try:
                return _fetch_urllib(url, timeout)
            except Exception as e2:  # noqa
                last = e2
            time.sleep(0.6 * (i + 1))
    raise last


def _fetch_curl(url, timeout):
    import subprocess
    cmd = ["curl", "-sS", "-L", "--compressed", "-m", str(timeout),
           "-H", f"User-Agent: {UA}",
           "-H", "Accept-Language: zh-CN,zh;q=0.9",
           url]
    p = subprocess.run(cmd, capture_output=True, timeout=timeout + 10)
    if p.returncode != 0:
        raise RuntimeError(f"curl rc={p.returncode}: {p.stderr[:200]!r}")
    raw = p.stdout
    if not raw:
        raise RuntimeError("curl empty body")
    for enc in ("utf-8", "gb18030"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


def _fetch_urllib(url, timeout):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9",
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
    for enc in ("utf-8", "gb18030"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")

ITEM_RE = re.compile(
    r'<span\s+class="date"[^>]*>\s*([\d]{4}-[\d]{2}-[\d]{2})\s*</span>\s*'
    r'<a\s+href="([^"]+)"[^>]*?title="([^"]*)"',
    re.S)
ITEM_RE2 = re.compile(
    r'<a\s+href="([^"]+)"[^>]*?title="([^"]*)"[^>]*>.*?</a>\s*'
    r'<span\s+class="date"[^>]*>\s*([\d]{4}-[\d]{2}-[\d]{2})',
    re.S)

def make_patterns(date_class):
    """按站点实际使用的日期元素类名生成规则（多数站是 date，知识产权局是 time）。"""
    dc = re.escape(date_class)
    before = re.compile(
        r'<span\s+class="' + dc + r'"[^>]*>\s*([\d]{4}-[\d]{2}-[\d]{2})\s*</span>\s*'
        r'<a\s+href="([^"]+)"[^>]*?title="([^"]*)"', re.S)
    after = re.compile(
        r'<a\s+href="([^"]+)"[^>]*?title="([^"]*)"[^>]*>.*?</a>\s*'
        r'<span\s+class="' + dc + r'"[^>]*>\s*([\d]{4}-[\d]{2}-[\d]{2})', re.S)
    return before, after


def parse_items(htmltext, base, source, channel, date_class="date"):
    out, seen = [], set()
    r1, r2 = make_patterns(date_class)
    for m in r1.finditer(htmltext):
        date, href, title = m.group(1), m.group(2), ihtml.unescape(m.group(3)).strip()
        out.append((title, date, href))
    for m in r2.finditer(htmltext):
        href, title, date = m.group(1), ihtml.unescape(m.group(2)).strip(), m.group(3)
        out.append((title, date, href))
    res = []
    for title, date, href in out:
        if not title:
            continue
        url = urljoin(base, href)
        if url in seen:
            continue
        seen.add(url)
        res.append({"title": title, "date": date, "url": url,
                    "source": source, "channel": channel})
    return res

def urls_from_pattern(pattern, total, start=1, first_plain=True):
    """pattern 形如 https://x/list/index_{i}.html ; i=1 用 index.html"""
    urls = []
    for i in range(start, total + 1):
        if i == 1 and first_plain:
            urls.append(pattern.replace("index_{i}.html", "index.html"))
        else:
            urls.append(pattern.replace("{i}", str(i)))
    return urls

def crawl(urls, source, channel, workers=5, date_class="date"):
    items, errs = [], []
    def job(u):
        t = fetch(u)
        return parse_items(t, u, source, channel, date_class)
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(job, u): u for u in urls}
        for f in as_completed(futs):
            u = futs[f]
            try:
                got = f.result()
                items.extend(got)
                print(f"  ok  {len(got):3d}  {u}", file=sys.stderr)
            except Exception as e:
                errs.append({"url": u, "error": str(e)})
                print(f"  ERR {u} :: {e}", file=sys.stderr)
    return items, errs

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pattern", required=True, help="https://host/path/index_{i}.html")
    ap.add_argument("--pages", type=int, default=1)
    ap.add_argument("--source", required=True)
    ap.add_argument("--channel", default="")
    ap.add_argument("--workers", type=int, default=5)
    ap.add_argument("--date-class", default="date",
                    help="列表页日期元素的 class 名，默认为 date（知识产权局是 time）")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    urls = urls_from_pattern(a.pattern, a.pages)
    items, errs = crawl(urls, a.source, a.channel, a.workers, a.date_class)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump({"source": a.source, "channel": a.channel,
                   "count": len(items), "items": items, "errors": errs},
                  f, ensure_ascii=False, indent=1)
    print(f"[{a.source}/{a.channel}] items={len(items)} errors={len(errs)} -> {a.out}")

if __name__ == "__main__":
    main()
