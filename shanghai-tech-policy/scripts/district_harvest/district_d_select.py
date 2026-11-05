#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""district_d v2: 以 5 类重点为主，控制旧条目比例，补充近年条目。"""
import json, os, re, sys, datetime, collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw_district")
DISTRICTS = ["杨浦区", "静安区", "普陀区", "长宁区", "奉贤区", "临港新片区"]
FOCUS = ["企业技术中心", "专利试点示范", "重大产业攻关", "揭榜挂帅", "制造业单项冠军"]
CUTOFF = "2023-01-01"
MAX_OLD_PER_DISTRICT = 6


def ts2date(ms):
    try:
        if ms and ms > 1e11:
            return datetime.datetime.fromtimestamp(ms / 1000).strftime("%Y-%m-%d")
    except Exception:
        pass
    return ""


FULL_RULES = [
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
    ("科技小巨人", r"小巨人"),
    ("高新技术企业", r"高新技术企业|高企"),
    ("专精特新中小企业", r"专精特新"),
    ("创新型中小企业", r"创新型中小企业"),
    ("科技型中小企业", r"科技型中小企业"),
    ("科技创新券", r"科技创新券"),
    ("专项资金与补贴", r"专项资金|专项扶持|扶持资金|补贴|资助|奖励|拨款"),
]


def classify(title):
    for cat, pat in FULL_RULES:
        if re.search(pat, title):
            return cat
    return None


def load(fn):
    p = os.path.join(RAW, fn)
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else []


def build_pool():
    """返回 {district: [ {title,url,date,category,issuer,src} ]}"""
    pool = collections.defaultdict(list)

    def add(d, title, url, date, issuer, src):
        if not title or not url:
            return
        c = classify(title)
        if not c:
            return
        pool[d].append({"district": d, "title": title, "url": url,
                        "date": date or "", "category": c,
                        "issuer": issuer or "", "src": src})

    for x in load("api_d.json"):
        add(x["district"], x.get("title", ""), x.get("url", ""),
            ts2date(x.get("displayDate")),
            x.get("dispatch_agency") or x.get("drafting_unit"), x.get("source", ""))
    for x in load("lgfx_d.json"):
        if x["district"] == "临港新片区":
            url = ("https://www.lingang.gov.cn/html/website/lg/index/government/"
                   f"file/{x.get('id')}.html") if x.get("id") else ""
            add("临港新片区", x.get("title", ""), url, ts2date(x.get("ts")),
                "中国（上海）自由贸易试验区临港新片区管理委员会", "临港政策库")
        else:
            add("奉贤区", x.get("title", ""), x.get("url", ""), "",
                "", x.get("source", ""))
    for x in load("lists_d.json"):
        add(x["district"], x.get("title", ""), x.get("url", ""), "",
            "", x.get("source", ""))
    for fn in ("cn_cols.json", "cn_cols2.json"):
        for x in load(fn):
            add("长宁区", x.get("title", ""), x.get("url", ""), "",
                "", x.get("source", ""))
    for x in load("ja_cols.json"):
        add("静安区", x.get("title", ""), x.get("url", ""), "",
            "", x.get("source", ""))
    return pool


def url_date(url):
    m = re.search(r"/(\d{4})[-/](\d{1,2})(?:[-/](\d{1,2}))?/", url)
    if m:
        d = m.group(3) or "15"
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(d):02d}"
    m = re.search(r"/(\d{4})(\d{2})(\d{2})/", url)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = re.search(r"/(\d{4})-(\d{2})-(\d{2})/", url)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return ""


CAP = 14


def main():
    pool = build_pool()
    sel = []
    for d in DISTRICTS:
        items = pool.get(d, [])
        # 去重
        best = {}
        for it in items:
            k = re.sub(r"\s+", "", it["title"])
            if k not in best:
                best[k] = it
        items = list(best.values())
        for x in items:
            x["pdate"] = x["date"] or url_date(x["url"])
        focus = [x for x in items if x["category"] in FOCUS]
        focus.sort(key=lambda x: (x["pdate"] or "0000-00-00"), reverse=True)
        recent = [x for x in focus if x["pdate"] and x["pdate"] >= CUTOFF]
        old = [x for x in focus if not (x["pdate"] and x["pdate"] >= CUTOFF)]
        # 每个重点类最多 4 条，保证类别分散
        picked, percat = [], collections.Counter()
        for x in recent:
            if len(picked) >= CAP:
                break
            if percat[x["category"]] >= 4:
                continue
            picked.append(x)
            percat[x["category"]] += 1
        for x in old[:MAX_OLD_PER_DISTRICT]:
            picked.append(x)
        # 补足到 10 条：用近年非重点类
        if len(picked) < 10:
            others = [x for x in items if x["category"] not in FOCUS
                      and x["pdate"] and x["pdate"] >= CUTOFF]
            others.sort(key=lambda x: x["pdate"], reverse=True)
            for x in others:
                if len(picked) >= 10:
                    break
                picked.append(x)
        sel.extend(picked)
        print(f"{d}: focus={len(focus)} recent={len(recent)} old={len(old)} "
              f"picked={len(picked)}", file=sys.stderr)

    json.dump(sel, open(os.path.join(RAW, "selection_d.json"), "w"),
              ensure_ascii=False, indent=1)
    print("selection", len(sel), file=sys.stderr)


if __name__ == "__main__":
    main()
