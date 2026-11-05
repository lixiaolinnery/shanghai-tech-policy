#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""汇总 district_d 所有来源，归类，挑出 5 类重点候选。"""
import json, os, re, sys, datetime, collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw_district")

DISTRICTS = ["杨浦区", "静安区", "普陀区", "长宁区", "奉贤区", "临港新片区"]

CAT_RULES = [
    ("制造业单项冠军", r"单项冠军|制造业冠军|先进制造业冠军"),
    ("企业技术中心", r"企业技术中心"),
    ("揭榜挂帅", r"揭榜挂帅|发榜|揭榜"),
    ("专利试点示范",
     r"专利工作(试点|示范|重点培育|优势)|专利(试点|示范)企业|知识产权(试点|示范|优势)"
     r"|知识产权强(市|区)建设|知识产权(重点培育|高质量)|专利(导航|专项|资助|保险|贯标|人才)"
     r"|知识产权(资助|奖励|扶持|保护|贯标|质押|评议|分析)"),
    ("重大产业攻关",
     r"关键核心技术攻关|重大产业攻关|核心技术攻关|技术攻关|产业攻关|科技攻关"
     r"|重点攻关|攻关方向|攻关项目|攻关成果"),
]


def classify(title):
    for cat, pat in CAT_RULES:
        if re.search(pat, title):
            return cat
    return None


def ts2date(ms):
    try:
        if ms and ms > 1e11:
            return datetime.datetime.fromtimestamp(ms / 1000).strftime("%Y-%m-%d")
    except Exception:
        pass
    return ""


def load(fn):
    p = os.path.join(RAW, fn)
    if not os.path.exists(p):
        return []
    return json.load(open(p, encoding="utf-8"))


def main():
    recs = []
    # API items (杨浦/普陀) - have url + date + agency
    for x in load("api_d.json"):
        recs.append({"district": x["district"], "title": x.get("title", ""),
                     "url": x.get("url", ""), "date": ts2date(x.get("displayDate")),
                     "issuer": x.get("dispatch_agency") or x.get("drafting_unit") or "",
                     "src": x.get("source", "")})
    # 临港政策库 + 奉贤经委
    for x in load("lgfx_d.json"):
        if x["district"] == "临港新片区":
            url = ("https://www.lingang.gov.cn/html/website/lg/index/government/"
                   f"file/{x.get('id')}.html") if x.get("id") else ""
            recs.append({"district": "临港新片区", "title": x.get("title", ""),
                         "url": url, "date": ts2date(x.get("ts")),
                         "issuer": "临港新片区管理委员会", "src": "临港政策库"})
        else:
            recs.append({"district": "奉贤区", "title": x.get("title", ""),
                         "url": x.get("url", ""), "date": "",
                         "issuer": "", "src": x.get("source", "")})
    # server-rendered lists
    for x in load("lists_d.json"):
        recs.append({"district": x["district"], "title": x.get("title", ""),
                     "url": x.get("url", ""), "date": "",
                     "issuer": "", "src": x.get("source", "")})
    # 长宁 columns
    for fn in ("cn_cols.json", "cn_cols2.json"):
        for x in load(fn):
            recs.append({"district": "长宁区", "title": x.get("title", ""),
                         "url": x.get("url", ""), "date": "",
                         "issuer": "", "src": x.get("source", "")})
    # 静安 city-site columns
    for x in load("ja_cols.json"):
        recs.append({"district": "静安区", "title": x.get("title", ""),
                     "url": x.get("url", ""), "date": "",
                     "issuer": "", "src": x.get("source", "")})
    # 统一检索
    for x in load("search_d.json"):
        recs.append({"district": x["district"], "title": x.get("title", ""),
                     "url": "", "date": x.get("displayDate") or "",
                     "issuer": "", "src": "统一检索",
                     "siteId": x.get("siteId"), "businessId": x.get("businessId"),
                     "docNo": x.get("docNo") or ""})

    print("raw recs", len(recs), file=sys.stderr)
    # 归类
    cand = []
    for r in recs:
        c = classify(r["title"])
        if not c:
            continue
        r["category"] = c
        cand.append(r)
    print("classified (focus)", len(cand), file=sys.stderr)

    # 去重：同区同标题优先留带 url 的
    best = {}
    for r in cand:
        k = (r["district"], re.sub(r"\s+", "", r["title"]))
        cur = best.get(k)
        if cur is None:
            best[k] = r
        else:
            if not cur.get("url") and r.get("url"):
                best[k] = r
            elif cur.get("url") and r.get("url"):
                # 保留更短/更官方的
                if len(r["url"]) < len(cur["url"]):
                    best[k] = r
    cand = list(best.values())
    print("deduped", len(cand), file=sys.stderr)

    by = collections.defaultdict(lambda: collections.defaultdict(list))
    for r in cand:
        by[r["district"]][r["category"]].append(r)
    for d in DISTRICTS:
        print(f"## {d}", file=sys.stderr)
        for c, _ in CAT_RULES:
            v = by[d].get(c, [])
            v.sort(key=lambda x: x.get("date") or "", reverse=True)
            print(f"   {c}: {len(v)}", file=sys.stderr)
            for x in v[:30]:
                print(f"      {x.get('date','')} | {x['title'][:64]} | {(x.get('url') or '')[:60]}",
                      file=sys.stderr)
    json.dump(cand, open(os.path.join(RAW, "focus_d.json"), "w"),
              ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
