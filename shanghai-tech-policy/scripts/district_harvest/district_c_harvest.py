#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""district_c 采集：上海 6 个区的 5 类政策（企业技术中心 / 专利试点示范 /
重大产业攻关 / 揭榜挂帅 / 制造业单项冠军）。

主入口为上海市政府统一政策检索：
  POST https://find.shanghai.gov.cn/search          -> resultList(含 businessId/日期/单位)
  POST https://www.shanghai.gov.cn/gwk/policy/detail -> originUrl(区官网) + docNo + txt
"""
import json, os, re, subprocess, sys, time, datetime, html as ihtml
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw_district_c")
os.makedirs(RAW, exist_ok=True)

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")

DISTRICTS = {
    "浦东新区": "0070",
    "徐汇区": "0073",
    "宝山区": "0078",
    "闵行区": "0079",
    "嘉定区": "0080",
    "松江区": "0082",
}

# 查询词：覆盖 5 类
QUERIES = [
    # 企业技术中心
    "企业技术中心", "区级企业技术中心", "企业技术中心 认定", "企业技术中心 名单",
    "企业技术中心 奖励", "企业技术中心 评价",
    # 专利试点示范 / 知识产权
    "专利工作试点单位", "专利试点", "专利示范", "知识产权试点", "知识产权示范",
    "知识产权试点示范单位", "专利工作示范单位", "知识产权 认定 名单",
    # 重大产业攻关 / 技术攻关
    "关键核心技术攻关", "技术攻关", "产业攻关", "攻关项目", "重大产业项目 攻关",
    "科技攻关 立项",
    # 揭榜挂帅
    "揭榜挂帅", "揭榜", "发榜", "技术需求 征集",
    # 制造业单项冠军 / 先进制造业
    "制造业单项冠军", "单项冠军", "先进制造业 冠军", "制造业 冠军 培育",
    "专精特新 小巨人 制造业",
]


def curl(args, timeout=45):
    cmd = ["curl", "-sS", "-L", "-k", "--compressed", "-m", str(timeout),
           "-H", f"User-Agent: {UA}", "-H", "Accept-Language: zh-CN,zh;q=0.9"] + args
    p = subprocess.run(cmd, capture_output=True, timeout=timeout + 20)
    raw = p.stdout
    if not raw:
        raise RuntimeError(f"empty body rc={p.returncode} err={p.stderr[:160]!r}")
    for enc in ("utf-8", "gb18030"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


def retry(fn, n=3, delay=1.0):
    last = None
    for i in range(n):
        try:
            return fn()
        except Exception as e:  # noqa
            last = e
            time.sleep(delay * (i + 1))
    print("  ! fail:", last, file=sys.stderr)
    return None


def city_search(q, site_id, page=1, size=50):
    body = json.dumps({"q": q, "page": page, "size": size, "siteId": [site_id]},
                      ensure_ascii=False)
    txt = curl(["-H", "Content-Type: text/plain", "-X", "POST", "-d", body,
                "https://find.shanghai.gov.cn/search"])
    return json.loads(txt)


def city_detail(site_id, business_id):
    body = json.dumps({"siteId": site_id, "businessId": business_id})
    txt = curl(["-H", "Content-Type: application/json", "-X", "POST", "-d", body,
                "https://www.shanghai.gov.cn/gwk/policy/detail"])
    return json.loads(txt)


def harvest():
    raw_path = os.path.join(RAW, "search_results.json")
    if os.path.exists(raw_path):
        return json.load(open(raw_path, encoding="utf-8"))
    all_rows = {}
    for dname, sid in DISTRICTS.items():
        for q in QUERIES:
            for page in (1, 2):
                r = retry(lambda: city_search(q, sid, page))
                if not r or r.get("code") != 0:
                    continue
                lst = (r.get("data") or {}).get("resultList") or []
                if not lst:
                    break
                for x in lst:
                    bid = x.get("businessId")
                    if not bid:
                        continue
                    x["_district"] = dname
                    x["_siteId"] = sid
                    x["_query"] = q
                    all_rows.setdefault(bid, x)
                if len(lst) < 50:
                    break
                time.sleep(0.4)
            time.sleep(0.3)
        print(f"[{dname}] cumulative {len(all_rows)}", file=sys.stderr)
    rows = list(all_rows.values())
    json.dump(rows, open(raw_path, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    return rows


if __name__ == "__main__":
    rows = harvest()
    print(f"total unique {len(rows)}")
