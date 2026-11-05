#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""district_c 后处理：基于 pool.json 重新分类 / 去新闻 / 均衡取样 -> district_c.json
（不重新联网，可快速迭代）"""
import json, os, re, sys
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw_district_c")
OUT = os.path.join(ROOT, "data", "district", "district_c.json")

DOC_MARK = re.compile(r"通知|公告|公示|名单|办法|细则|方案|指南|规定|批复|榜单|"
                      r"指引|措施|解读|标准|意见")
NEWS_MARK = re.compile(r"入选|入围|获评|出炉|走访|调研|座谈|宣讲|大会|论坛|启动|"
                       r"举行|加冕|揭牌|圆满|落幕|举办|本区|我区|速看|看过来|"
                       r"来袭|再添|出炉|视频|澎湃|上观")
POLICYISH = re.compile(r"通知|办法|细则|指南|公示|公告|名单|方案|规定|措施|指引|"
                       r"批复|申报|立项")


def is_news(t):
    if DOC_MARK.search(t):
        return False
    return bool(NEWS_MARK.search(t))


def classify_cat(t):
    if re.search(r"揭榜|挂帅|发榜", t):
        return "揭榜挂帅"
    if re.search(r"企业技术中心|技术中心", t):
        return "企业技术中心"
    if re.search(r"单项冠军|制造业冠军|冠军企业|先进制造业.{0,8}冠军", t):
        return "制造业单项冠军"
    if re.search(r"攻关", t):
        return "重大产业攻关"
    if re.search(r"专利.{0,6}(试点|示范)|知识产权.{0,8}(试点|示范|优势)|试点示范", t):
        return "专利试点示范"
    if re.search(r"知识产权|专利", t):
        return "专利试点示范"
    if re.search(r"创新联合体", t):
        return "重大产业攻关"
    return "其他科技政策"


def classify_type(t):
    if re.search(r"公示|拟认定|拟支持|拟立项|征求意见", t):
        return "公示通知"
    if re.search(r"立项|验收|评价结果|评价工作|结题|评估结果", t):
        return "立项与评价通知"
    if re.search(r"奖励|资助|经费|拨付|兑现|补贴|专项资金", t):
        return "领补贴通知"
    if re.search(r"申报|征集|组织开展|申请|榜单", t):
        return "申报通知"
    if re.search(r"名单", t) or (re.search(r"认定", t) and "通知" in t) \
            or re.search(r"下达", t):
        return "名单公布"
    if re.search(r"办法|细则|措施|指引|方案|意见|规定|指南", t):
        return "政策红头文件"
    if re.search(r"通知|公告", t):
        return "申报通知"
    return "政策红头文件"


def norm_date(s):
    m = re.search(r"(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})", s or "")
    return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}" if m else ""


def extract_conds(text):
    out = []
    for sent in re.split(r"(?<=[。；;])", text or ""):
        s = sent.strip()
        if 12 <= len(s) <= 220 and re.search(
                r"应当具备|应具备|申报条件|申请条件|基本条件|须同时满足|"
                r"符合以下条件|具备以下", s):
            out.append(s)
        if len(out) >= 3:
            break
    return out


def extract_benefits(text):
    out = []
    for sent in re.split(r"(?<=[。；;])", text or ""):
        s = sent.strip()
        if 8 <= len(s) <= 220 and re.search(r"给予|奖励|资助|补贴|支持", s) \
                and re.search(r"万元|亿元|%|比例", s):
            out.append(s)
        if len(out) >= 3:
            break
    return out


def dedup(rows):
    def key(r):
        return (r["district"], re.sub(r"[《》\s（）()]|（.*?）", "", r["title"]))
    best = {}
    for r in rows:
        k = key(r)
        if k not in best:
            best[k] = r
            continue
        sc = lambda x: (1 if x["publishDate"] else 0) + \
                       (1 if x["docNo"] else 0) + (1 if x["benefits"] else 0)
        if sc(r) > sc(best[k]):
            best[k] = r
    return list(best.values())


def select_balanced(rows, per_dist=16, per_cat=6, min_dist=10):
    by_d = defaultdict(list)
    for r in rows:
        by_d[r["district"]].append(r)
    picked = []
    for dist, items in by_d.items():
        by_c = defaultdict(list)
        for r in items:
            by_c[r["category"]].append(r)
        chosen, used = [], set()
        for cat, rs in by_c.items():
            rs = sorted(rs, key=lambda x: (
                x["publishDate"][:4] >= "2023",
                bool(POLICYISH.search(x["title"])),
                x["publishDate"]), reverse=True)
            for r in rs[:per_cat]:
                chosen.append(r)
                used.add(r["url"])
        chosen.sort(key=lambda x: (
            x["publishDate"][:4] >= "2023",
            bool(POLICYISH.search(x["title"])),
            x["publishDate"]), reverse=True)
        chosen = chosen[:per_dist]
        if len(chosen) < min_dist:
            rest = [r for r in items if r["url"] not in used
                    and r["url"] not in {c["url"] for c in chosen}]
            rest.sort(key=lambda x: (x["publishDate"][:4] >= "2023",
                                     x["publishDate"]), reverse=True)
            chosen += rest[:min_dist - len(chosen)]
        picked += chosen
    return picked


def main():
    pool = json.load(open(os.path.join(RAW, "pool.json"), encoding="utf-8"))
    kept = [r for r in pool if not is_news(r["title"])]
    print(f"pool {len(pool)} -> after news filter {len(kept)}", file=sys.stderr)
    final = []
    for r in kept:
        final.append({
            "title": r["title"],
            "publishDate": norm_date(r["publishDate"]) or norm_date(r["text"][:400]),
            "url": r["url"],
            "docNo": r.get("docNo", "") or "",
            "issuer": r.get("issuer", "") or "",
            "district": r["district"],
            "category": classify_cat(r["title"]),
            "noticeType": classify_type(r["title"]),
            "conditions": extract_conds(r.get("text", "")),
            "benefits": extract_benefits(r.get("text", "")),
            "pdfUrls": r.get("pdfUrls", []) or [],
            "_http": 200,
        })
    final = dedup(final)
    final = select_balanced(final)
    final.sort(key=lambda x: (x["district"], x["category"], x["publishDate"]))
    json.dump(final, open(OUT, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("wrote", OUT, len(final))
    print("district:", dict(Counter(x["district"] for x in final)))
    print("category:", dict(Counter(x["category"] for x in final)))
    print("noticeType:", dict(Counter(x["noticeType"] for x in final)))


if __name__ == "__main__":
    main()
