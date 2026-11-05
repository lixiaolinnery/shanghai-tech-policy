#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""交付验收：数据完整性 + 分类覆盖 + 栏目非空 + 字段质量。
用法：python3 tests/acceptance.py
"""
import json, os, re, sys, collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PASS, FAIL = [], []


def ck(name, cond, detail=""):
    (PASS if cond else FAIL).append((name, detail))


def main():
    pj = os.path.join(ROOT, "data", "policies.json")
    ck("data/policies.json 存在", os.path.exists(pj))
    payload = json.load(open(pj, encoding="utf-8"))
    P = payload["policies"]
    G = payload["guides"]

    # ---- 规模 ----
    ck("政策记录 ≥ 150 条（用户要求）", len(P) >= 150, f"实际 {len(P)}")
    ck("覆盖年份 ≥ 5 个", len({p["year"] for p in P}) >= 5,
       str(sorted({p["year"] for p in P})))
    ck("政策类型 ≥ 12 类", len({p["category"] for p in P}) >= 12,
       str(len({p["category"] for p in P})))

    # ---- 用户点名的栏目均有内容 ----
    need = {"政策红头文件": 50, "申报通知": 100, "公示通知": 100, "领补贴通知": 5,
            "立项与评价通知": 50, "名单公布": 50}
    cnt = collections.Counter(p["noticeType"] for p in P)
    for k, least in need.items():
        ck(f"栏目「{k}」有内容（≥{least}）", cnt.get(k, 0) >= least, f"实际 {cnt.get(k,0)}")
    ck("深度解读「申报条件与好处」≥8 类", len(G) >= 8, f"实际 {len(G)}")

    # ---- 用户点名的核心政策类型均有覆盖 ----
    for cat, least in [("高新技术企业", 20), ("专精特新中小企业", 10),
                       ("科技型中小企业", 20), ("科技创新券", 5), ("科技小巨人", 5)]:
        n = sum(1 for p in P if p["category"] == cat)
        ck(f"核心类型「{cat}」≥{least} 条", n >= least, f"实际 {n}")

    # ---- 市/区两级 ----
    lv = collections.Counter(p.get("level") for p in P)
    ck("市级记录 ≥ 1000 条", lv.get("市级", 0) >= 1000, f"实际 {lv.get('市级',0)}")
    ck("区级记录 ≥ 50 条", lv.get("区级", 0) >= 50, f"实际 {lv.get('区级',0)}")
    ck("区级记录覆盖 ≥ 5 个区",
       len({p.get("district") for p in P if p.get("level") == "区级"}) >= 5,
       str(sorted({p.get("district") for p in P if p.get("level") == "区级"})))
    ck("层级无误标（区级记录必须来自区级数据源）",
       all(p.get("source") == "district" for p in P if p.get("level") == "区级"))

    # ---- 字段质量 ----
    ck("每条都有标题", all(p["title"].strip() for p in P))
    ck("标题无异常长度（≤95 字）", all(len(p["title"]) <= 95 for p in P),
       str(max(len(p["title"]) for p in P)))
    ck("每条都有 http(s) 原文链接", all(re.match(r"^https?://", p["url"]) for p in P))
    ck("发布日期格式统一 YYYY-MM-DD",
       all(re.match(r"^\d{4}-\d{2}-\d{2}$", p["publishDate"]) for p in P))
    # 发布日期不可能晚于今天（"申报截止日/有效期至"常被误当成发布日期）
    import datetime as _dt
    today = _dt.date.today().isoformat()
    future = [p for p in P if p["publishDate"] > today]
    ck("无未来发布日期", not future,
       f"今天 {today}，异常 {len(future)} 条: " + ", ".join(
           f'{p["publishDate"]} {p["title"][:24]}' for p in future[:3]))
    ck("URL 无重复", len({p["url"] for p in P}) == len(P))
    ck("含文号 ≥ 400 条", sum(1 for p in P if p["docNo"]) >= 400,
       f"实际 {sum(1 for p in P if p['docNo'])}")
    ck("含红头文件 PDF ≥ 600 条", sum(1 for p in P if p["pdfUrls"]) >= 600,
       f"实际 {sum(1 for p in P if p['pdfUrls'])}")
    ck("有结构化字段的记录 ≥ 200 条", sum(1 for p in P if p["depth"] == "full") >= 200,
       f"实际 {sum(1 for p in P if p['depth']=='full')}")
    ck("无外省政策混入",
       not any(("宁夏" in p["title"] or "新疆" in p["title"] or "广东" in p["title"])
               and "上海" not in p["title"] for p in P))

    # ---- 深度解读结构 ----
    for g in G:
        ck(f"解读「{g['category']}」有申报条件",
           bool(g.get("conditions")), f"{len(g.get('conditions') or [])} 条")
        ck(f"解读「{g['category']}」有政策好处",
           bool(g.get("benefits")), f"{len(g.get('benefits') or [])} 条")

    # ---- 链接验活结果 ----
    lc = os.path.join(ROOT, "data", "linkcheck.json")
    if os.path.exists(lc):
        d = json.load(open(lc, encoding="utf-8"))
        rate = d["okPages"] / max(1, len(P))
        ck("原文链接可访问率 ≥ 99%", rate >= 0.99, f"{d['okPages']}/{len(P)} = {rate:.2%}")
        ck("失效链接 ≤ 5 个", len(d["dead"]) <= 5, f"实际 {len(d['dead'])}")
    else:
        ck("存在链接验活报告", False, "data/linkcheck.json 缺失")

    # ---- 前端资源 ----
    for f in ["index.html", "assets/style.css", "assets/app.js", "data/policies.js", "README.md"]:
        ck(f"交付文件存在：{f}", os.path.exists(os.path.join(ROOT, f)))

    print("=" * 62)
    for n, d in PASS:
        print(f"  ✓ {n}" + (f"  [{d}]" if d else ""))
    if FAIL:
        print("-" * 62)
        for n, d in FAIL:
            print(f"  ✗ {n}" + (f"  [{d}]" if d else ""))
    print("=" * 62)
    print(f"验收结果：{len(PASS)} 通过 / {len(FAIL)} 失败")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
