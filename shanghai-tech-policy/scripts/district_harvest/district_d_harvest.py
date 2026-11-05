#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""district_d: 采集上海 6 个区（杨浦/静安/普陀/长宁/奉贤/临港）5 类政策。

5 类：企业技术中心 / 专利试点示范 / 重大产业攻关 / 揭榜挂帅 / 制造业单项冠军

入口：上海市政府统一政策检索 POST https://find.shanghai.gov.cn/search
详情：POST https://www.shanghai.gov.cn/gwk/policy/detail  -> originUrl / txt / docNo
"""
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

# 每类多个关键词，尽量召回
QUERIES = {
    "企业技术中心": ["企业技术中心"],
    "专利试点示范": ["专利试点", "专利示范", "知识产权试点", "知识产权示范",
                     "知识产权优势企业", "专利工作试点"],
    "重大产业攻关": ["关键核心技术攻关", "重大产业攻关", "技术攻关", "产业攻关",
                     "揭榜挂帅攻关", "科技攻关"],
    "揭榜挂帅": ["揭榜挂帅", "发榜", "需求征集", "揭榜"],
    "制造业单项冠军": ["制造业单项冠军", "单项冠军", "先进制造业冠军",
                       "制造业冠军"],
    "高新技术企业": ["高新技术企业认定", "高新技术企业奖励"],
    "专精特新中小企业": ["专精特新"],
    "创新型中小企业": ["创新型中小企业"],
    "科技型中小企业": ["科技型中小企业"],
    "科技小巨人": ["科技小巨人"],
    "科技创新券": ["科技创新券"],
    "专项资金与补贴": ["科技专项资金", "科技创新奖励"],
}

# 归类正则：标题命中才算（优先）
CAT_PATTERNS = [
    ("企业技术中心", r"企业技术中心"),
    ("制造业单项冠军", r"单项冠军|制造业冠军|先进制造业冠军"),
    ("揭榜挂帅", r"揭榜挂帅|发榜|揭榜"),
    ("专利试点示范", r"专利.{0,6}(试点|示范|优势)|知识产权.{0,8}(试点|示范|优势|保护)|专利工作试点"),
    ("重大产业攻关", r"关键核心技术攻关|重大产业攻关|技术攻关|产业攻关|科技攻关"),
    ("科技小巨人", r"科技小巨人|小巨人"),
    ("高新技术企业", r"高新技术企业|高企"),
    ("专精特新中小企业", r"专精特新"),
    ("创新型中小企业", r"创新型中小企业"),
    ("科技型中小企业", r"科技型中小企业"),
    ("科技创新券", r"科技创新券"),
    ("专项资金与补贴", r"专项资金|扶持资金|补贴|资助|奖励"),
]


def curl(args, timeout=45):
    cmd = ["curl", "-sS", "-L", "--compressed", "-m", str(timeout),
           "-H", f"User-Agent: {UA}", "-H", "Accept-Language: zh-CN,zh;q=0.9"] + args
    p = subprocess.run(cmd, capture_output=True, timeout=timeout + 20)
    raw = p.stdout
    if not raw:
        raise RuntimeError(f"empty rc={p.returncode} err={p.stderr[:150]!r}")
    for enc in ("utf-8", "gb18030"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


def search(q, site_id, page=1, size=30, retries=3):
    body = json.dumps({"q": q, "page": page, "size": size, "siteId": [site_id]},
                      ensure_ascii=False)
    for i in range(retries):
        try:
            txt = curl(["-H", "Content-Type: text/plain", "-X", "POST",
                        "-d", body, "https://find.shanghai.gov.cn/search"], 45)
            return json.loads(txt)
        except Exception as e:  # noqa
            if i == retries - 1:
                print(f"  ! search fail {q}/{site_id}: {e}", file=sys.stderr)
                return None
            time.sleep(1.5 * (i + 1))


def detail(site_id, business_id, retries=3):
    body = json.dumps({"siteId": site_id, "businessId": business_id})
    for i in range(retries):
        try:
            txt = curl(["-H", "Content-Type: application/json", "-X", "POST",
                        "-d", body,
                        "https://www.shanghai.gov.cn/gwk/policy/detail"], 45)
            j = json.loads(txt)
            if j.get("code") == 0:
                return j.get("data")
            return None
        except Exception:  # noqa
            if i == retries - 1:
                return None
            time.sleep(1.2 * (i + 1))


def classify(title):
    for cat, pat in CAT_PATTERNS:
        if re.search(pat, title):
            return cat
    return "其他科技政策"


NEG = re.compile(r"十五五|十四五|规划|纲要|方案|实施意见|管理办法|行动计划|"
                 r"工作方案|制度|指南|普法|公开日|活动|预告|招聘|人事|"
                 r"垃圾分类|养老服务|体育事业|交通发展|教育|卫生|统计")


def main():
    cands = {}
    for dname, sid in DISTRICTS.items():
        print(f"=== {dname} ({sid}) ===", file=sys.stderr)
        for cat, kws in QUERIES.items():
            for kw in kws:
                j = search(kw, sid, page=1, size=30)
                if not j:
                    continue
                data = j.get("data") or {}
                lst = data.get("resultList") or []
                got = 0
                for it in lst:
                    if it.get("siteId") != sid:
                        continue
                    bid = it.get("businessId")
                    if not bid:
                        continue
                    key = f"{sid}:{bid}"
                    title = (it.get("title") or "").strip()
                    if not title:
                        continue
                    if key not in cands:
                        cands[key] = {
                            "siteId": sid, "businessId": bid,
                            "district": dname, "title": title,
                            "displayDate": (it.get("displayDate") or "")[:10],
                            "publishDate": (it.get("publishDate") or "")[:10],
                            "docNo": (it.get("docNo") or "").strip(),
                            "origin": it.get("origin") or "",
                            "queryHits": [f"{cat}:{kw}"],
                        }
                        got += 1
                    else:
                        cands[key]["queryHits"].append(f"{cat}:{kw}")
                print(f"  {cat}/{kw}: {len(lst)} hits, +{got} new", file=sys.stderr)
                time.sleep(0.4)
    out = os.path.join(RAW, "cands_d.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(list(cands.values()), f, ensure_ascii=False, indent=1)
    print(f"total candidates: {len(cands)} -> {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
