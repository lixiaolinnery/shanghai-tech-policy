#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""district_d: 深度分页统一检索，按站点过滤，收集 5 类重点文档。"""
import json, os, re, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw_district")
os.makedirs(RAW, exist_ok=True)

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")

DISTRICTS = {
    "杨浦区": "0077",
    "静安区": "0072",
    "普陀区": "0075",
    "长宁区": "0074",
    "奉贤区": "0084",
    "临港新片区": "0058",
}

QUERIES = [
    "企业技术中心",
    "专利试点", "专利示范", "知识产权试点", "知识产权示范",
    "知识产权优势企业", "专利工作试点",
    "技术攻关", "关键核心技术攻关", "揭榜挂帅",
    "单项冠军", "制造业单项冠军",
]


def curl(args, timeout=45):
    cmd = ["curl", "-sS", "-L", "--compressed", "-m", str(timeout),
           "-H", f"User-Agent: {UA}", "-H", "Accept-Language: zh-CN,zh;q=0.9"] + args
    p = subprocess.run(cmd, capture_output=True, timeout=timeout + 20)
    raw = p.stdout
    if not raw:
        raise RuntimeError("empty")
    for enc in ("utf-8", "gb18030"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


def search(q, site_id, page, size=30, retries=4):
    body = json.dumps({"q": q, "page": page, "size": size,
                       "siteId": [site_id]}, ensure_ascii=False)
    for i in range(retries):
        try:
            return json.loads(curl(["-H", "Content-Type: text/plain", "-X", "POST",
                                    "-d", body,
                                    "https://find.shanghai.gov.cn/search"]))
        except Exception:
            time.sleep(1.5 * (i + 1))
    return None


def job(args):
    dname, sid, q, page = args
    j = search(q, sid, page)
    if not j:
        return dname, q, page, []
    data = j.get("data") or {}
    out = []
    for it in (data.get("resultList") or []):
        if it.get("siteId") != sid:
            continue
        out.append({
            "district": dname, "siteId": sid,
            "businessId": it.get("businessId"),
            "title": (it.get("title") or "").strip(),
            "displayDate": (it.get("displayDate") or "")[:10],
            "publishDate": (it.get("publishDate") or "")[:10],
            "docNo": (it.get("docNo") or "").strip(),
            "origin": it.get("origin") or "",
            "query": q,
        })
    return dname, q, page, out


PAGES = 5


def main():
    jobs = []
    for dname, sid in DISTRICTS.items():
        for q in QUERIES:
            for page in range(1, PAGES + 1):
                jobs.append((dname, sid, q, page))
    print(f"jobs {len(jobs)}", file=sys.stderr)
    store = {}
    with ThreadPoolExecutor(max_workers=5) as ex:
        futs = [ex.submit(job, j) for j in jobs]
        done = 0
        for f in as_completed(futs):
            dname, q, page, items = f.result()
            done += 1
            for x in items:
                if not x["businessId"] or not x["title"]:
                    continue
                k = f"{x['siteId']}:{x['businessId']}"
                if k not in store:
                    x["hits"] = [f"{q}#{page}"]
                    store[k] = x
                else:
                    store[k]["hits"].append(f"{q}#{page}")
            if done % 40 == 0:
                print(f"  {done}/{len(jobs)} {len(store)} uniq", file=sys.stderr)
    out = os.path.join(RAW, "search_d.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(list(store.values()), f, ensure_ascii=False, indent=1)
    print(f"unique docs: {len(store)} -> {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
