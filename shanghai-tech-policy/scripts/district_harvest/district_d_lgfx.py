#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""district_d: 临港 baseSelect 政策库 + 奉贤经委通知公告。"""
import json, os, re, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw_district")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")


def curl(args, timeout=45, retries=3):
    for i in range(retries):
        try:
            p = subprocess.run(["curl", "-sS", "-L", "--compressed", "-m", str(timeout),
                                "-H", f"User-Agent: {UA}"] + args,
                               capture_output=True, timeout=timeout + 20)
            if p.stdout:
                return p.stdout.decode("utf-8", "replace")
        except Exception:
            pass
        time.sleep(1.2 * (i + 1))
    return ""


def lg_page(page, table="view_zhengcewenjian", size=20):
    body = json.dumps({
        "pageSize": size, "pageNumber": page, "tableName": table,
        "betweenMap": [], "orSql": "", "orderBy": "CONTENT_DATETIME desc",
        "inMap": {}, "eqMap": {}, "map": {}}, ensure_ascii=False)
    t = curl(["-H", "Content-Type: application/json;charset=utf8",
              "-X", "POST", "-d", body, "https://www.lingang.gov.cn/baseSelect"])
    try:
        return json.loads(t)
    except Exception:
        return None


def lg_work(page):
    j = lg_page(page)
    if not j:
        return page, []
    dd = j.get("data") or {}
    out = []
    for x in (dd.get("list") or []):
        out.append({
            "district": "临港新片区", "source": "临港政策库",
            "title": (x.get("content_title") or "").strip(),
            "id": x.get("id"),
            "ts": x.get("content_datetime"),
            "category_id": x.get("category_id"),
        })
    return page, out


def crawl_lingang():
    j = lg_page(1)
    dd = (j or {}).get("data") or {}
    pages = dd.get("pages") or 0
    print(f"临港政策库 pages={pages} total={dd.get('total')}", file=sys.stderr)
    items = list(lg_work(1)[1])
    with ThreadPoolExecutor(max_workers=5) as ex:
        futs = [ex.submit(lg_work, p) for p in range(2, pages + 1)]
        done = 0
        for f in as_completed(futs):
            _, res = f.result()
            items.extend(res)
            done += 1
            if done % 40 == 0:
                print(f"  lg {done}/{pages-1} {len(items)}", file=sys.stderr)
    return items


A_RE = re.compile(r'<a\s[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.S | re.I)
FX_PAT = re.compile(r"/jw/xwzx/tzgg/\d{8}/[0-9a-zA-Z\-]+\.html")


def strip_tags(s):
    s = re.sub(r"<[^>]+>", "", s).replace("&nbsp;", " ").replace("&amp;", "&")
    return re.sub(r"\s+", " ", s).strip()


def crawl_fx_jw():
    out = []
    for i in range(1, 16):
        u = ("https://www.fengxian.gov.cn/jw/xwzx/tzgg/index.html" if i == 1
             else f"https://www.fengxian.gov.cn/jw/xwzx/tzgg/index_{i}.html")
        h = curl([u])
        n = 0
        for m in A_RE.finditer(h):
            href, inner = m.group(1), m.group(2)
            if not FX_PAT.search(href):
                continue
            t = strip_tags(inner)
            if len(t) < 6:
                tm = re.search(r'title="([^"]+)"', m.group(0))
                if tm:
                    t = tm.group(1).strip()
            if len(t) < 6:
                continue
            out.append({"district": "奉贤区", "source": "奉贤经委-通知公告",
                        "title": t,
                        "url": "https://www.fengxian.gov.cn" + href,
                        "page": i})
            n += 1
        print(f"  fx-jw p{i}: {n}", file=sys.stderr)
        time.sleep(0.3)
    return out


def main():
    lg = crawl_lingang()
    fx = crawl_fx_jw()
    dedup = {}
    for x in lg:
        k = "LG:" + (x.get("title") or "") + str(x.get("id"))
        dedup[k] = x
    for x in fx:
        dedup["FX:" + x["url"]] = x
    res = list(dedup.values())
    out = os.path.join(RAW, "lgfx_d.json")
    json.dump(res, open(out, "w"), ensure_ascii=False, indent=1)
    print(f"lg={len(lg)} fx={len(fx)} total={len(res)} -> {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
