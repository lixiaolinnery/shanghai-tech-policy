#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""district_e6: 抓 shanghai.gov.cn 区级政策聚合页 (tsqygs-zjfcqjN) 的全部条目。"""
import json, os, re, subprocess, sys, time, html as ihtml
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw_district")
os.makedirs(RAW, exist_ok=True)

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")

AGG = {"2": "黄浦区", "7": "虹口区", "12": "金山区", "14": "青浦区", "16": "崇明区"}
FAMILIES = ["tsqygs-zjfcqj", "tszczq-qtqj", "fzhj-gqwj", "jszx-gqwj"]
BASE = "https://www.shanghai.gov.cn"


def curl(args, timeout=40):
    cmd = ["curl", "-sS", "-L", "-k", "--compressed", "-m", str(timeout),
           "-H", f"User-Agent: {UA}", "-H", "Accept-Language: zh-CN,zh;q=0.9"] + args
    p = subprocess.run(cmd, capture_output=True, timeout=timeout + 20)
    raw = p.stdout
    if not raw:
        return ""
    for enc in ("utf-8", "gb18030"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


def get(url, retries=3):
    for i in range(retries):
        try:
            t = curl([url])
            if t:
                return t
        except Exception:
            pass
        time.sleep(1 + i)
    return ""


def strip_html(s):
    if not s:
        return ""
    s = re.sub(r"<script.*?</script>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<style.*?</style>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = ihtml.unescape(s)
    s = re.sub(r"[\u3000\xa0]", " ", s)
    s = re.sub(r"[ \t\r\f\v]+", " ", s)
    s = re.sub(r"\n\s*\n+", "\n", s)
    return s.strip()


def agg_list(fam, n, max_pages=8):
    items = []
    for p in range(1, max_pages + 1):
        url = f"{BASE}/{fam}{n}/index.html" if p == 1 \
            else f"{BASE}/{fam}{n}/index_{p}.html"
        h = get(url)
        if not h:
            break
        n0 = 0
        for href, txt in re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', h, re.S):
            t = strip_html(txt)
            if not t or len(t) < 8:
                continue
            if "tsqygs" in href or "affairs_affairs" in href or "tszczq" in href \
                    or "fzhj-gqwj" in href:
                full = href if href.startswith("http") else BASE + href
                items.append((t, full))
                n0 += 1
        if n0 == 0:
            break
        time.sleep(0.4)
    return items


def page_meta(url):
    h = get(url)
    if not h:
        return {}
    title = ""
    m = re.search(r'name="ArticleTitle" content="([^"]*)"', h)
    if m:
        title = ihtml.unescape(m.group(1)).strip()
    if not title:
        m = re.search(r"<title>(.*?)</title>", h, re.S)
        if m:
            title = re.sub(r"\s+", " ", ihtml.unescape(m.group(1))).strip()
    date = ""
    for pat in (r'name="PubDate" content="([^"]*)"',
                r"(\d{4})年(\d{1,2})月(\d{1,2})日",
                r"(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})"):
        m = re.search(pat, h)
        if m:
            if m.lastindex == 3 and "年" in pat:
                date = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
            else:
                mm = re.match(r"(\d{4})[-/.年](\d{1,2})[-/.月](\d{1,2})", m.group(1))
                if mm:
                    date = f"{mm.group(1)}-{int(mm.group(2)):02d}-{int(mm.group(3)):02d}"
            if date:
                break
    docno = ""
    m = re.search(r"([\u4e00-\u9fa5]{1,14}[〔\[]20\d{2}[〕\]]\s*\d+\s*号)", h)
    if m:
        docno = m.group(1)
    issuer = ""
    m = re.search(r'name="ContentSource" content="([^"]*)"', h)
    if m:
        issuer = ihtml.unescape(m.group(1)).strip()
    return {"title": title, "date": date, "docno": docno, "issuer": issuer,
            "text": strip_html(h)[:20000]}


def main():
    out = []
    for fam in FAMILIES:
      for n, dist in AGG.items():
        items = agg_list(fam, n)
        print(dist, fam, n, len(items), flush=True)
        with ThreadPoolExecutor(max_workers=4) as ex:
            futs = {ex.submit(page_meta, u): (t, u) for t, u in items}
            for f in as_completed(futs):
                t, u = futs[f]
                try:
                    m = f.result()
                except Exception:
                    m = {}
                out.append({
                    "title": m.get("title") or t,
                    "publishDate": m.get("date", ""),
                    "url": u, "docNo": m.get("docno", ""),
                    "issuer": m.get("issuer", ""), "district": dist,
                    "category": "", "noticeType": "",
                    "conditions": [], "benefits": [], "pdfUrls": [],
                    "_src": f"{fam}{n}",
                    "_text": (m.get("text") or "")[:4000],
                })
    json.dump(out, open(os.path.join(RAW, "e6_agg.json"), "w"),
              ensure_ascii=False, indent=1)
    print("total", len(out))


if __name__ == "__main__":
    main()
