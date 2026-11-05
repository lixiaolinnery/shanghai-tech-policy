#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Manda 站点搜索清扫（宝山 appCode=1lvxqqb，cids 见下）。"""
import json, os, re, subprocess, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw_district_c")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")

KWS = [
    "企业技术中心", "技术中心", "区级企业技术中心", "技术中心 认定", "技术中心 评价",
    "技术中心 奖励", "技术中心 名单", "专利试点", "专利示范", "专利工作试点单位",
    "专利工作示范单位", "知识产权试点", "知识产权示范", "知识产权示范单位",
    "知识产权", "攻关", "科技攻关", "关键核心技术", "产业攻关", "揭榜挂帅",
    "揭榜", "发榜", "技术需求", "单项冠军", "制造业单项冠军", "先进制造业",
    "制造业冠军", "冠军企业", "创新联合体",
]

TARGET = re.compile(
    r"企业技术中心|技术中心|专利.{0,6}(试点|示范)|知识产权.{0,8}(试点|示范|优势)|"
    r"试点示范|攻关|揭榜|挂帅|发榜|单项冠军|制造业冠军|冠军企业|"
    r"先进制造业.{0,8}冠军|创新联合体")


def curl(args, timeout=40):
    cmd = ["curl", "-sS", "-L", "-k", "--compressed", "-m", str(timeout),
           "-H", f"User-Agent: {UA}", "-H", "Accept-Language: zh-CN,zh;q=0.9"] + args
    p = subprocess.run(cmd, capture_output=True, timeout=timeout + 15)
    raw = p.stdout
    if not raw:
        raise RuntimeError("empty")
    for enc in ("utf-8", "gb18030"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


def manda_search(app, cid, query, cur=1, size=20):
    body = json.dumps({"query": query, "cid": cid, "size": size, "current": cur},
                      ensure_ascii=False)
    txt = curl(["-H", "Content-Type: application/json", "-X", "POST", "-d", body,
                f"https://ss.shanghai.gov.cn/manda-app/api/app/search/v1/{app}/search"])
    return json.loads(txt)


def sweep(app, cid, district, maxpage=3):
    rows = {}
    for kw in KWS:
        for cur in range(1, maxpage + 1):
            try:
                r = manda_search(app, cid, kw, cur)
            except Exception as e:  # noqa
                print(f"  ! {kw} p{cur}: {e}", file=sys.stderr)
                time.sleep(1.5)
                continue
            if not r or not r.get("success"):
                break
            items = ((r.get("result") or {}).get("items")) or []
            if not items:
                break
            for it in items:
                t = ((it.get("title") or {}).get("raw") or "").strip()
                u = ((it.get("url") or {}).get("raw") or "").strip()
                if not u or not TARGET.search(t):
                    continue
                d = ((it.get("date") or {}).get("raw") or "").strip()
                wh = ((it.get("wh") or {}).get("raw") or "").strip()
                rows[u] = {"district": district, "title": t, "publishDate": d,
                           "url": u, "docNo": wh, "issuer": "", "pdfUrls": [],
                           "_kw": kw, "_src": "manda"}
            time.sleep(0.25)
        print(f"[{district}] {kw} cum {len(rows)}", file=sys.stderr)
    return list(rows.values())


if __name__ == "__main__":
    app = sys.argv[1]
    cid = sys.argv[2]
    dist = sys.argv[3]
    mp = int(sys.argv[4]) if len(sys.argv) > 4 else 3
    out = sweep(app, cid, dist, mp)
    p = os.path.join(RAW, f"manda_{dist}.json")
    json.dump(out, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(dist, len(out), p)
