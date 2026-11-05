#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""最终筛选 + 收尾：从已校验 200 的池子里挑出每区 12 条，再复验一次。"""
import json, os, re, subprocess, collections
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw_district")
OUT = os.path.join(ROOT, "data", "district", "district_a.json")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")

# 明确排除：活动/新闻稿、内部事务，不是面向企业的政策通知
DROP_TITLE = ["走进商汤", "千帆计划", "创?在上海", "企业送上", "徐汇推出",
              "开放月", "审核指导小组", "领导小组成员", "职务任免",
              "双创讲堂", "活动预告", "讲座", "对接专场", "政策宣讲",
              "授牌仪式", "展演", "竞赛", "培训会", "辅导预约", "统计培训",
              "工作经费", "合作交流活动", "全国科技大会", "整改结果", "审计调查",
              "获颁", "政策解读会", "为何集中涌现", "老总说", "融资平台",
              "一图读懂", "开始啦", "正式发布", "政策申报导读", "维护的通知",
              "关于废止"]

TARGET = ["高新技术企业", "高企", "专精特新", "创新型中小企业",
          "科技型中小企业", "科技小巨人", "科技创新券"]


def classify_notice(t):
    if any(k in t for k in ["管理办法", "实施细则", "若干措施", "实施办法", "暂行办法",
                            "实施意见", "操作细则", "工作指引", "认定办法", "奖励办法",
                            "资助办法", "办法（试行）", "若干政策", "支持政策", "细则"]):
        return "政策红头文件"
    if any(k in t for k in ["公示", "拟认定", "拟支持", "拟奖励", "拟立项", "拟入库"]):
        return "公示通知"
    if any(k in t for k in ["名单", "入库", "公布", "证书"]):
        return "名单公布"
    if any(k in t for k in ["立项", "验收", "评价结果", "绩效评价", "评估", "课题"]):
        return "立项与评价通知"
    if any(k in t for k in ["拨付", "兑现", "发放", "下达", "资金安排", "给予",
                            "资助", "奖励资金", "补贴"]):
        return "领补贴通知"
    if any(k in t for k in ["申报", "征集", "开展", "推荐", "认定", "复核", "评价",
                            "备案", "申请"]):
        return "申报通知"
    return "政策红头文件"


def classify_category(t):
    if "高新技术企业" in t or "高企" in t:
        return "高新技术企业"
    if "专精特新" in t:
        return "专精特新中小企业"
    if "创新型中小企业" in t:
        return "创新型中小企业"
    if "科技型中小企业" in t:
        return "科技型中小企业"
    if "科技小巨人" in t:
        return "科技小巨人"
    if "科技创新券" in t or "科技双创券" in t:
        return "科技创新券"
    if any(k in t for k in ["专项资金", "科技发展基金", "扶持资金", "资助", "补贴",
                            "奖励", "资金", "兑现", "拨付", "后补助", "扶持", "若干意见"]):
        return "专项资金与补贴"
    return "其他科技政策"


def score(r):
    s = 0
    cat = r["category"]
    s += {"高新技术企业": 70, "专精特新中小企业": 70, "创新型中小企业": 70,
          "科技型中小企业": 66, "科技小巨人": 66, "科技创新券": 66,
          "专项资金与补贴": 45, "其他科技政策": 28}.get(cat, 20)
    y = (r.get("publishDate") or "")[:4]
    s += {"2026": 60, "2025": 48, "2024": 34, "2023": 16, "2022": 6}.get(y, 0)
    nt = r.get("noticeType")
    s += 12 if nt in ("申报通知", "公示通知", "领补贴通知", "名单公布", "立项与评价通知") else 0
    if any(k in r["title"] for k in TARGET):
        s += 18
    if r.get("benefits"):
        s += 6
    if r.get("conditions"):
        s += 6
    if r.get("docNo"):
        s += 3
    if not r.get("publishDate"):
        s -= 20
    return s


import html as ihtml


def curl(args, timeout=35):
    cmd = ["curl", "-sS", "-L", "-k", "--compressed", "-m", str(timeout),
           "-H", f"User-Agent: {UA}"] + args
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


def strip_html(s):
    if not s:
        return ""
    s = re.sub(r"<script.*?</script>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<style.*?</style>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<!--.*?-->", " ", s, flags=re.S)
    s = re.sub(r"<[^>]+>", " ", s)
    s = ihtml.unescape(s)
    s = re.sub(r"[\u3000\xa0]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def fetch_text(url):
    for _ in range(2):
        try:
            h = curl([url])
            break
        except Exception:
            h = None
    if not h:
        return ""
    for pat in (r'<div[^>]+(?:class|id)="[^"]*(?:content|article|detail|TRS_Editor|zoom|view|mainText)[^"]*"[^>]*>(.*?)</div>',
                r'<div[^>]+id="(?:zoom|content|ivs_content|mainText)"[^>]*>(.*?)</div>'):
        m = re.search(pat, h, re.S | re.I)
        if m and len(m.group(1)) > 400:
            return strip_html(m.group(1))
    return strip_html(h)


MONEY_RE = re.compile(
    r"[^。；;\n]{0,90}?(?:给予|一次性|最高|不超过|奖励|补贴|资助|支持|配套)"
    r"[^。；;\n]{0,70}?\d[\d,\.]*\s*(?:万元|万|元)[^。；;\n]{0,30}")
COND_RE = re.compile(
    r"[^。；;\n]{0,20}?(?:申报条件|申请条件|支持对象|申报对象|认定条件|基本条件|"
    r"应符合|应当符合|申报要求)[^。；;\n]{0,150}")


def extract_benefits(txt):
    out, seen = [], set()
    for m in MONEY_RE.finditer(txt or ""):
        v = re.sub(r"\s+", " ", m.group(0)).strip(" ,，、。；")
        if len(v) < 10 or v in seen:
            continue
        seen.add(v); out.append(v)
        if len(out) >= 3:
            break
    return out


def extract_conditions(txt):
    out, seen = [], set()
    for m in COND_RE.finditer(txt or ""):
        v = re.sub(r"\s+", " ", m.group(0)).strip(" ,，、：:。；")
        if len(v) < 12 or v in seen:
            continue
        seen.add(v); out.append(v)
        if len(out) >= 3:
            break
    return out


def norm_issuer(issuer, district):
    if not issuer:
        return ""
    a = issuer.strip()
    a = a.replace("上海市", "").replace("上海", "")
    for d in ["浦东新区", "徐汇区", "闵行区", "嘉定区", "松江区"]:
        a = a.replace(d, "")
    a = a.strip(" 、,，")
    return f"上海市{district}{a}" if a else f"上海市{district}"


def http_status(url):
    try:
        p = subprocess.run(["curl", "-sS", "-L", "-k", "-o", "/dev/null", "-m", "25",
                            "-H", f"User-Agent: {UA}", "-w", "%{http_code}", url],
                           capture_output=True, timeout=40)
        return p.stdout.decode().strip()
    except Exception:
        return "000"


def main():
    rel = json.load(open(os.path.join(RAW, "rel_cands.json")))
    st = json.load(open(os.path.join(RAW, "url_status.json")))
    pool = [r for r in rel if st.get(r["url"]) == "200"
            and not any(k in r["title"] for k in DROP_TITLE)
            and (not (r.get("publishDate") or "")[:4].isdigit()
                 or int((r["publishDate"])[:4]) >= 2016)]
    print("可用池:", len(pool), collections.Counter(r["district"] for r in pool))

    by = collections.defaultdict(list)
    for r in pool:
        r["category"] = r.get("category") or classify_category(r["title"])
        r["noticeType"] = classify_notice(r["title"])
        by[r["district"]].append(r)

    final = []
    for dist in ["浦东新区", "徐汇区", "闵行区", "嘉定区", "松江区"]:
        lst = sorted(by[dist], key=score, reverse=True)
        picked, percat = [], {}
        caps = {"其他科技政策": 2, "专项资金与补贴": 3}
        for r in lst:
            c = r["category"]
            if percat.get(c, 0) >= caps.get(c, 3):
                continue
            percat[c] = percat.get(c, 0) + 1
            picked.append(r)
            if len(picked) >= 12:
                break
        print(f"{dist}: 池 {len(lst)} -> 选 {len(picked)}  {dict(percat)}")
        final.extend(picked)

    # 复验
    print("复验", len(final), "条 …")
    with ThreadPoolExecutor(max_workers=6) as ex:
        codes = list(ex.map(lambda r: http_status(r["url"]), final))
    bad = [(r["title"], r["url"], c) for r, c in zip(final, codes) if c != "200"]
    print("复验非 200:", len(bad))
    for t, u, c in bad:
        print("   ", c, t[:50], u[:80])
    final = [r for r, c in zip(final, codes) if c == "200"]

    print("抓取正文并抽取条件/奖励 …")
    def work(r):
        t = fetch_text(r["url"])
        r["_txt"] = t
        r["conditions"] = extract_conditions(t)
        r["benefits"] = extract_benefits(t)
        return r
    with ThreadPoolExecutor(max_workers=6) as ex:
        final = list(ex.map(work, final))
    print("  含奖励信息:", sum(1 for r in final if r["benefits"]),
          " 含申报条件:", sum(1 for r in final if r["conditions"]))

    out = [{
        "title": r["title"],
        "publishDate": r.get("publishDate") or "",
        "url": r["url"],
        "docNo": r.get("docNo") or "",
        "issuer": norm_issuer(r.get("issuer") or "", r["district"]),
        "district": r["district"],
        "category": r["category"],
        "noticeType": r["noticeType"],
        "conditions": r.get("conditions") or [],
        "benefits": r.get("benefits") or [],
        "pdfUrls": r.get("pdfUrls") or [],
    } for r in final]

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(out, open(OUT, "w"), ensure_ascii=False, indent=1)
    print("写出", OUT, len(out))
    print("每区:", collections.Counter(x["district"] for x in out))
    print("类别:", collections.Counter(x["category"] for x in out))
    print("类型:", collections.Counter(x["noticeType"] for x in out))
    print("年份:", dict(sorted(collections.Counter(x["publishDate"][:4] for x in out).items(),
                              reverse=True)))


if __name__ == "__main__":
    main()
