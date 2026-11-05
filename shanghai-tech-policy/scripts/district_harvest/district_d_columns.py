#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""发现普陀/杨浦站点的栏目 id：抓栏目页里的 ids:'NNN'。"""
import json, os, re, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw_district")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")


def curl(url, timeout=30, retries=2):
    for i in range(retries):
        try:
            p = subprocess.run(["curl", "-sS", "-L", "--compressed", "-m", str(timeout),
                                "-H", f"User-Agent: {UA}", url],
                               capture_output=True, timeout=timeout + 15)
            if p.stdout:
                for enc in ("utf-8", "gb18030"):
                    try:
                        return p.stdout.decode(enc)
                    except UnicodeDecodeError:
                        continue
                return p.stdout.decode("utf-8", "replace")
        except Exception:
            pass
        time.sleep(1.0)
    return ""


IDS_RE = re.compile(r"ids\s*:\s*['\"]?(\d+)")
NAME_RE = re.compile(r'ColumnName"\s+content="([^"]*)"')


def probe(base, slug):
    url = f"{base}/zhengwu/{slug}/"
    h = curl(url)
    if not h or len(h) < 500:
        return None
    m = IDS_RE.search(h)
    if not m:
        return None
    n = NAME_RE.search(h)
    return {"base": base, "slug": slug, "channelId": m.group(1),
            "columnName": n.group(1) if n else ""}


def discover(base):
    idx = curl(f"{base}/zhengwu/")
    slugs = set(re.findall(r"/zhengwu/([a-z0-9_\-]+)/", idx))
    print(f"{base}: {len(slugs)} slugs from index", file=sys.stderr)
    # 补充 tzgg-* 候选
    depts = ["kw", "scjgj", "sww", "fgw", "rsj", "czj", "sjj", "wjw",
             "jyj", "sthjj", "jsj", "ghzyj", "ajj", "sj", "tyj", "wl"]
    for d in depts:
        slugs.add(f"tzgg-{d}zdgz")
        slugs.add(f"tzgg-{d}")
        slugs.add(f"{d}-tzgg")
    res = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = [ex.submit(probe, base, s) for s in sorted(slugs)]
        for f in as_completed(futs):
            r = f.result()
            if r:
                res.append(r)
    return res


def main():
    out = {}
    for base in ["https://www.shpt.gov.cn", "https://www.shyp.gov.cn"]:
        r = discover(base)
        out[base] = r
        print(f"{base}: found {len(r)} columns", file=sys.stderr)
    p = os.path.join(RAW, "columns_d.json")
    json.dump(out, open(p, "w"), ensure_ascii=False, indent=1)
    print("->", p, file=sys.stderr)
    for b, r in out.items():
        print(b)
        for x in sorted(r, key=lambda y: y["slug"]):
            print("  ", x["slug"], x["channelId"], x["columnName"])


if __name__ == "__main__":
    main()
