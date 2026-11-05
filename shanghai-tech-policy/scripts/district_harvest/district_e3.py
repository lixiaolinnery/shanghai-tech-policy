#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""district_e3: 用上海市统一政策检索做一次广覆盖扫描，只保留 5 个目标区。"""
import json, os, re, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw_district")
os.makedirs(RAW, exist_ok=True)

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")

WANT = {"黄浦区": "0071", "虹口区": "0076", "金山区": "0081",
        "青浦区": "0083", "崇明区": "0085"}
NAME_BY_ID = {v: k for k, v in WANT.items()}

QUERIES = [
    "企业技术中心", "区级企业技术中心", "企业技术中心管理办法", "企业技术中心认定",
    "企业技术中心 奖励", "企业技术中心 申报", "企业技术中心 名单",
    "专利试点", "专利工作试点", "专利试点示范单位", "专利示范单位",
    "知识产权试点", "知识产权示范", "知识产权示范单位", "知识产权试点示范",
    "知识产权 扶持", "知识产权 资助", "高价值专利培育", "专利导航",
    "关键核心技术攻关", "核心技术攻关", "产业攻关", "技术攻关",
    "揭榜挂帅", "揭榜挂帅 榜单", "发榜", "揭榜",
    "单项冠军", "制造业单项冠军", "单项冠军 认定", "单项冠军 培育",
    "高新技术企业", "高新技术企业 奖励", "高新技术企业 补贴",
    "专精特新", "专精特新 奖励", "专精特新 名单",
    "创新型中小企业", "科技型中小企业", "科技小巨人", "科技创新券",
    "科技发展基金", "科技创新 若干政策", "科技 专项资金", "科技 扶持",
    "科技攻关", "技术改造", "智能工厂", "首台套",
    "黄浦区 企业技术中心", "虹口区 企业技术中心", "金山区 企业技术中心",
    "青浦区 企业技术中心", "崇明区 企业技术中心",
    "黄浦区 专利试点", "虹口区 专利试点", "金山区 专利试点",
    "青浦区 专利试点", "崇明区 专利试点",
    "黄浦区 知识产权", "虹口区 知识产权", "金山区 知识产权",
    "青浦区 知识产权", "崇明区 知识产权",
    "黄浦区 单项冠军", "虹口区 单项冠军", "金山区 单项冠军",
    "青浦区 单项冠军", "崇明区 单项冠军",
    "黄浦区 揭榜挂帅", "虹口区 揭榜挂帅", "金山区 揭榜挂帅",
    "青浦区 揭榜挂帅", "崇明区 揭榜挂帅",
    "黄浦区 高新技术企业", "虹口区 高新技术企业", "金山区 高新技术企业",
    "青浦区 高新技术企业", "崇明区 高新技术企业",
    "黄浦区 专精特新", "虹口区 专精特新", "金山区 专精特新",
    "青浦区 专精特新", "崇明区 专精特新",
    "黄浦区 科技小巨人", "虹口区 科技小巨人", "金山区 科技小巨人",
    "青浦区 科技小巨人", "崇明区 科技小巨人",
    "黄浦区 科技 奖励", "虹口区 科技 奖励", "金山区 科技 奖励",
    "青浦区 科技 奖励", "崇明区 科技 奖励",
    "黄浦区 科技创新", "虹口区 科技创新", "金山区 科技创新",
    "青浦区 科技创新", "崇明区 科技创新",
    "黄浦区 科技攻关", "虹口区 科技攻关", "金山区 科技攻关",
    "青浦区 科技攻关", "崇明区 科技攻关",
]


def curl(args, timeout=45):
    cmd = ["curl", "-sS", "-L", "-k", "--compressed", "-m", str(timeout),
           "-H", f"User-Agent: {UA}", "-H", "Accept-Language: zh-CN,zh;q=0.9"] + args
    p = subprocess.run(cmd, capture_output=True, timeout=timeout + 25)
    raw = p.stdout
    if not raw:
        raise RuntimeError("empty")
    for enc in ("utf-8", "gb18030"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


def search(q, page=1, size=20, retries=3):
    body = json.dumps({"q": q, "page": page, "size": size}, ensure_ascii=False)
    for i in range(retries):
        try:
            return json.loads(curl(["-H", "Content-Type: text/plain", "-X", "POST",
                                    "-d", body, "https://find.shanghai.gov.cn/search"]))
        except Exception as e:
            if i == retries - 1:
                print(f"  ! {q} p{page}: {e}", file=sys.stderr)
                return None
            time.sleep(1.0 * (i + 1))


def main():
    hits = {}
    for q in QUERIES:
        got = 0
        for page in range(1, 8):
            d = search(q, page)
            if not d or d.get("code") != 0:
                break
            data = d.get("data") or {}
            rl = data.get("resultList") or []
            if not rl:
                break
            n_new = 0
            for r in rl:
                sid = r.get("siteId")
                if sid not in NAME_BY_ID:
                    continue
                key = (sid, r.get("businessId"))
                if key in hits:
                    continue
                hits[key] = r
                n_new += 1
            got += n_new
            total = int(data.get("totalHits") or 0)
            if page * 20 >= total or len(rl) < 20:
                break
            time.sleep(0.25)
        print(f"{q}: +{got} (total {len(hits)})", flush=True)
        time.sleep(0.2)
    json.dump({f"{k[0]}|{k[1]}": v for k, v in hits.items()},
              open(os.path.join(RAW, "e3_hits.json"), "w"),
              ensure_ascii=False, indent=1)
    print("saved", len(hits))
    from collections import Counter
    print(Counter(NAME_BY_ID[k[0]] for k in hits))


if __name__ == "__main__":
    main()
