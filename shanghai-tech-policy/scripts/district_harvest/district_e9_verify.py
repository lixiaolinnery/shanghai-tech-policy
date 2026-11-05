#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""district_e9: 最终校验。逐条请求 URL，确认 200，并比对页面标题与记录标题。"""
import json, os, re, subprocess, html as ihtml, sys
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "district", "district_e.json")
REPORT = os.path.join(ROOT, "data", "raw_district", "e9_verify.json")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")


def fetch(url):
    cmd = ["curl", "-sS", "-L", "-k", "--compressed", "-m", "30",
           "-H", f"User-Agent: {UA}", "-w", "\n@@@%{http_code}",
           "-o", "-", url]
    try:
        p = subprocess.run(cmd, capture_output=True, timeout=50)
        raw = p.stdout
        txt = raw.decode("utf-8", "replace")
        m = re.search(r"@@@(\d{3})$", txt.strip())
        code = m.group(1) if m else "000"
        body = txt[:m.start()] if m else txt
        return code, body
    except Exception:
        return "000", ""


def page_title(body):
    for pat in (r'name="ArticleTitle" content="([^"]*)"',
                r'id="ivs_title"[^>]*>(.*?)</p>',
                r"<h1[^>]*>(.*?)</h1>",
                r"<title>(.*?)</title>"):
        m = re.search(pat, body, re.S | re.I)
        if m:
            t = ihtml.unescape(re.sub(r"<[^>]+>", "", m.group(1))).strip()
            t = re.sub(r"\s+", " ", t)
            if len(t) > 4:
                return t
    return ""


def norm(s):
    return re.sub(r"[\s《》「」【】()（）“”\"'·、,，。.：:;；\-—_]|上海市|上海", "", s or "")


def main():
    recs = json.load(open(OUT))
    print("records", len(recs))

    def work(r):
        code, body = fetch(r["url"])
        pt = page_title(body)
        ok_title = norm(r["title"])[:20] in norm(pt) or norm(pt)[:20] in norm(r["title"])
        return {"title": r["title"], "url": r["url"], "district": r["district"],
                "http": code, "pageTitle": pt[:90], "titleMatch": bool(ok_title),
                "bodyLen": len(body)}

    with ThreadPoolExecutor(max_workers=3) as ex:
        res = list(ex.map(work, recs))
    json.dump(res, open(REPORT, "w"), ensure_ascii=False, indent=1)
    bad = [x for x in res if x["http"] != "200"]
    mism = [x for x in res if x["http"] == "200" and not x["titleMatch"]]
    print("HTTP 200:", sum(1 for x in res if x["http"] == "200"), "/", len(res))
    print("非200:")
    for x in bad:
        print("  ", x["http"], x["district"], x["url"][:100])
    print("标题不匹配:", len(mism))
    for x in mism:
        print("  rec:", x["title"][:60])
        print("  page:", x["pageTitle"][:60])
        print("  url:", x["url"][:100])


if __name__ == "__main__":
    main()
