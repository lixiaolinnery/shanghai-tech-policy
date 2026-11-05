#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""district_e8: 合并全部候选 -> 去重 -> 过滤 -> HTTP 验证 -> 产出 district_e.json。"""
import json, os, re, subprocess, sys, time, html as ihtml
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw_district")
OUT = os.path.join(ROOT, "data", "district", "district_e.json")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")

TARGET = ["黄浦区", "虹口区", "金山区", "青浦区", "崇明区"]

CAT_PRIORITY = ["企业技术中心", "专利试点示范", "重大产业攻关", "揭榜挂帅",
                "制造业单项冠军", "高新技术企业", "专精特新中小企业",
                "创新型中小企业", "科技型中小企业", "科技小巨人", "科技创新券",
                "专项资金与补贴", "其他科技政策"]

CAT_KW = [
    ("企业技术中心", ["企业技术中心", "区级技术中心"]),
    ("制造业单项冠军", ["单项冠军"]),
    ("揭榜挂帅", ["揭榜挂帅", "揭榜", "发榜"]),
    ("重大产业攻关", ["攻关"]),
    ("专利试点示范", ["专利试点", "专利工作试点", "专利示范", "高价值专利",
                      "知识产权试点", "知识产权示范", "专利培育", "专利",
                      "知识产权"]),
    ("高新技术企业", ["高新技术企业", "高企"]),
    ("专精特新中小企业", ["专精特新"]),
    ("创新型中小企业", ["创新型中小企业", "创新型企业总部"]),
    ("科技型中小企业", ["科技型中小企业"]),
    ("科技小巨人", ["科技小巨人", "小巨人"]),
    ("科技创新券", ["科技创新券"]),
]

TECH_KW = ["企业技术中心", "技术中心", "专利", "知识产权", "攻关", "揭榜", "发榜",
           "单项冠军", "高新技术企业", "高企", "专精特新", "创新型中小企业",
           "创新型企业总部", "科技型中小企业", "小巨人", "科技小巨人", "科技创新券",
           "科技发展基金", "科技专项", "科技创新", "研发机构", "工程技术研究中心",
           "技术改造", "首台套", "智能工厂", "科技企业", "科技奖励", "科技项目",
           "科技计划", "孵化器", "众创空间", "科技成果", "产业专项", "专项资金",
           "科技扶持", "技术合同", "产学研", "创新"]

BAD = ["政策解读", "一图读懂", "图文解读", "跟踪解读", "视频解读", "草案",
       "征求意见", "废止", "十五五", "十四五", "规划纲要", "工作总结",
       "工作要点", "应急预案", "行政裁决", "抽查", "处罚",
       "主副食品", "时尚产业", "地方教育附加", "节能减排", "品牌创新",
       "营商环境", "创业创新大赛", "银发经济", "体育", "养老"]

FORCE_CAT = {
    "https://www.shanghai.gov.cn/tszczq-qtqj2/20250610/5dfd2e3e70d54a418fc458f4f810829a.html":
        "专精特新中小企业",
}

NOTICE_RULES = [
    ("政策红头文件", ["管理办法", "实施细则", "若干措施", "实施办法", "暂行办法",
                      "实施意见", "操作办法", "工作指引", "认定办法", "奖励办法",
                      "资助办法", "扶持办法", "若干政策", "政策措施", "办法",
                      "实施方案", "行动方案", "若干举措", "管理细则", "细则",
                      "管理规定"]),
    ("公示通知", ["公示", "拟认定", "拟支持", "拟奖励", "拟立项", "拟入库",
                  "拟通过", "拟补助", "拟获评"]),
    ("名单公布", ["名单", "公布", "结果", "公告"]),
    ("立项与评价通知", ["立项", "验收", "评价", "评估", "绩效", "复评"]),
    ("领补贴通知", ["拨付", "兑现", "发放", "下达", "领取", "资金安排",
                    "奖励资金", "资助资金"]),
    ("申报通知", ["申报", "征集", "开展", "推荐", "认定", "复核", "备案",
                  "申请", "组织", "通知", "工作", "启动"]),
]

MONEY_RE = re.compile(
    r"[^。；;\n]{0,90}?(?:给予|一次性|最高|按|不超过|奖励|补贴|资助|支持|扶持|每家|每个)"
    r"[^。；;\n]{0,70}?(?:\d[\d,\.]*\s*(?:万元|万|元))[^。；;\n]{0,40}")
COND_RE = re.compile(
    r"[^。；;\n]{0,40}?(?:申报条件|申请条件|支持对象|申报对象|认定条件|应符合|应当符合|"
    r"基本条件|申报范围|支持范围|培育对象|申报主体|支持标准)[^。；;\n]{0,160}")


def curl(args, timeout=30):
    cmd = ["curl", "-sS", "-L", "-k", "--compressed", "-m", str(timeout),
           "-H", f"User-Agent: {UA}"] + args
    p = subprocess.run(cmd, capture_output=True, timeout=timeout + 15)
    return p.stdout.decode("utf-8", "replace")


def http_status(url):
    try:
        out = curl(["-o", "/dev/null", "-w", "%{http_code}", url])
        return out.strip() or "000"
    except Exception:
        return "000"


def classify_cat(title):
    for c, kws in CAT_KW:
        if any(k in title for k in kws):
            return c
    return ""


def classify_notice(t):
    for nt, kws in NOTICE_RULES:
        if any(k in t for k in kws):
            return nt
    return "申报通知"


def is_relevant(title, url=""):
    if not title:
        return False
    if any(k in title for k in BAD):
        return False
    if url in FORCE_CAT:
        return True
    return any(k in title for k in TECH_KW) or bool(classify_cat(title))


def extract(regex, txt, n=4, minlen=8):
    out, seen = [], set()
    if not txt:
        return out
    for m in regex.finditer(txt):
        s = re.sub(r"\s+", " ", m.group(0)).strip(" ,，、：:")
        if len(s) < minlen or s in seen:
            continue
        seen.add(s)
        out.append(s)
        if len(out) >= n:
            break
    return out


def load(name):
    p = os.path.join(RAW, name)
    if not os.path.exists(p):
        return []
    try:
        return json.load(open(p))
    except Exception:
        return []


def norm_title(t):
    t = re.sub(r"\s+", "", t or "")
    t = re.sub(r"^(上海市|上海)?", "", t)
    t = re.sub(r"[《》「」【】()（）\[\]“”\"'·、,，。.：:;；\-—_]", "", t)
    return t[:60]


def main():
    pool = []
    pool += load("e7_manual.json")
    sweep = load("e5_all.json")
    for r in sweep:
        r["_http"] = None
        pool.append(r)
    for r in load("e6_agg.json"):
        r["_http"] = None
        pool.append(r)
    for f in ("e4_jinshan.json", "e4_qingpu.json"):
        for r in load(f):
            r["_http"] = None
            pool.append(r)

    # 规整
    recs = []
    seen_u = set()
    for r in pool:
        d = r.get("district")
        if d not in TARGET:
            continue
        t = re.sub(r"\s+", " ", (r.get("title") or "")).strip()
        t = re.sub(r"^文章标题[:：]?\s*", "", t).strip()
        u = (r.get("url") or "").strip()
        # 青浦统一 https + 去掉 :80
        u = re.sub(r"^http://www\.shqp\.gov\.cn:80", "https://www.shqp.gov.cn", u)
        u = re.sub(r"^http://www\.shqp\.gov\.cn", "https://www.shqp.gov.cn", u)
        if not t or not u.startswith("http"):
            continue
        if u in seen_u:
            continue
        if not is_relevant(t, u):
            continue
        seen_u.add(u)
        cat = FORCE_CAT.get(u) or r.get("category") or classify_cat(t)
        if not cat:
            if any(k in t for k in ["专项资金", "奖励", "补贴", "资助", "资金",
                                    "兑现", "拨付", "扶持", "基金"]):
                cat = "专项资金与补贴"
            else:
                cat = "其他科技政策"
        date = r.get("publishDate") or ""
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
            date = ""
        recs.append({
            "title": t,
            "publishDate": date,
            "url": u,
            "docNo": (r.get("docNo") or "").strip(),
            "issuer": (r.get("issuer") or "").strip(),
            "district": d,
            "category": cat,
            "noticeType": r.get("noticeType") or classify_notice(t),
            "conditions": r.get("conditions") or extract(COND_RE, r.get("_text", "")),
            "benefits": r.get("benefits") or extract(MONEY_RE, r.get("_text", "")),
            "pdfUrls": [x for x in (r.get("pdfUrls") or []) if x][:3],
            "_src": r.get("_src", ""),
            "_http": r.get("_http"),
        })
    print("normalized", len(recs))

    # 去重（同区同标题）
    bykey = {}
    for r in recs:
        k = (r["district"], norm_title(r["title"]))
        cur = bykey.get(k)
        if cur is None:
            bykey[k] = r
            continue
        def score(x):
            s = 0
            if x.get("_http") == "200":
                s += 100
            if x["url"].startswith("https://www.shanghai.gov.cn"):
                s += 25
            if "shhuangpu.gov.cn" in x["url"]:
                s -= 60
            if x["publishDate"]:
                s += 4
            if x["category"] in CAT_PRIORITY[:5]:
                s += 3
            if x.get("benefits"):
                s += 2
            if x.get("docNo"):
                s += 1
            return s
        if score(r) > score(cur):
            bykey[k] = r
    recs = list(bykey.values())
    print("dedup", len(recs))

    # HTTP 验证（低并发，避免被限流）
    todo = [r for r in recs if r.get("_http") != "200"]
    print("to verify", len(todo))
    with ThreadPoolExecutor(max_workers=3) as ex:
        futs = {ex.submit(http_status, r["url"]): r for r in todo}
        for i, f in enumerate(as_completed(futs), 1):
            r = futs[f]
            try:
                r["_http"] = f.result()
            except Exception:
                r["_http"] = "000"
            if i % 50 == 0:
                print("  verified", i, flush=True)

    ok = [r for r in recs if r["_http"] == "200"]
    bad = [r for r in recs if r["_http"] != "200"]
    print("200:", len(ok), " non-200:", len(bad))
    print("non-200 dist:", Counter((r["district"], r["_http"]) for r in bad))
    json.dump(bad, open(os.path.join(RAW, "e8_bad.json"), "w"),
              ensure_ascii=False, indent=1)

    # 选取
    selected = {}
    for dist in TARGET:
        rows = [r for r in ok if r["district"] == dist]
        # 排序：目标类别 > 近年
        def score(r):
            s = 0
            if r["category"] in CAT_PRIORITY:
                s += (20 - CAT_PRIORITY.index(r["category"])) * 10
            y = r["publishDate"][:4]
            if y in ("2023", "2024", "2025", "2026"):
                s += 40
            elif y in ("2021", "2022"):
                s += 10
            if r["publishDate"]:
                s += int(y) - 2000
            if r["_src"] == "manual":
                s += 6
            if r.get("benefits"):
                s += 2
            return -s
        rows.sort(key=score)
        # 目标类别优先，然后补足
        picked, seen_cat = [], Counter()
        for r in rows:
            if len(picked) >= 16:
                break
            if seen_cat[r["category"]] >= 5:
                continue
            picked.append(r)
            seen_cat[r["category"]] += 1
        selected[dist] = picked
        print(dist, len(rows), "->", len(picked), dict(seen_cat))

    final = []
    for dist in TARGET:
        final += selected[dist]
    # 清理内部字段
    for r in final:
        for k in ("_src", "_http", "_text"):
            r.pop(k, None)
        r["pdfUrls"] = [x for x in r.get("pdfUrls", []) if isinstance(x, str)]
    json.dump(final, open(OUT, "w"), ensure_ascii=False, indent=1)
    print("written", OUT, len(final))
    print(Counter(r["district"] for r in final))
    print(Counter(r["category"] for r in final))
    print("with date:", sum(1 for r in final if r["publishDate"]))
    print("2023-2026:", sum(1 for r in final if r["publishDate"][:4] in
                            ("2023", "2024", "2025", "2026")))
    print("with docNo:", sum(1 for r in final if r["docNo"]))
    print("with benefits:", sum(1 for r in final if r["benefits"]))


if __name__ == "__main__":
    main()
