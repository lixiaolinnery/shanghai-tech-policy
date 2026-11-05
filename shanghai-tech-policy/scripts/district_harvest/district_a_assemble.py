#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""最终整理：筛选 -> 抓正文 -> 分类/抽取 -> 校验 URL -> 输出 district_a.json"""
import json, os, re, subprocess, sys, time, html as ihtml
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw_district")
OUT = os.path.join(ROOT, "data", "district", "district_a.json")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")

TARGET = ["高新技术企业", "高企", "专精特新", "创新型中小企业",
          "科技型中小企业", "科技小巨人", "科技创新券"]

JUNK = ["消费券", "招聘", "招标", "中标", "采购", "竞争性磋商", "听证", "处罚",
        "论坛", "大礼包", "开放月", "工作经费", "预约", "开始啦", "送上", "推出",
        "决算", "预算", "任免", "职务", "科普", "展演", "体育", "招生", "医疗",
        "养老", "垃圾分类", "绿化", "道路", "广告", "培训", "请示", "统计",
        "辅导", "会议", "视察", "调研", "巡察", "党建", "廉政", "安全生产",
        "防汛", "消防", "名录", "非物质文化", "旅游", "文物", "档案", "信访",
        "拆迁", "征收", "土地", "规划纲要", "五年规划", "十五五", "十四五",
        "环境保护", "水务", "交通", "教育发展", "卫生", "民政", "就业",
        "乡村振兴", "城市更新", "住房", "公园", "国资国企", "营商环境"]

ACTION = ["申报", "公示", "名单", "立项", "认定", "奖励", "补贴", "资助", "资金",
          "办法", "措施", "政策", "兑现", "拨付", "备案", "入库", "复核",
          "计划", "方案", "细则", "意见", "通知"]


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


def http_status(url):
    try:
        p = subprocess.run(
            ["curl", "-sS", "-L", "-k", "-o", "/dev/null", "-m", "25",
             "-H", f"User-Agent: {UA}", "-w", "%{http_code}", url],
            capture_output=True, timeout=40)
        return p.stdout.decode().strip()
    except Exception:
        return "000"


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
    if "科技创新券" in t:
        return "科技创新券"
    if any(k in t for k in ["专项资金", "科技发展基金", "扶持资金", "资助", "补贴",
                            "奖励", "资金", "兑现", "拨付", "后补助", "扶持"]):
        return "专项资金与补贴"
    return "其他科技政策"


def classify_notice(t):
    if any(k in t for k in ["管理办法", "实施细则", "若干措施", "实施办法", "暂行办法",
                            "实施意见", "操作细则", "工作指引", "认定办法", "奖励办法",
                            "资助办法", "办法（试行）", "若干政策", "支持政策",
                            "管理办法（试行）", "细则"]):
        return "政策红头文件"
    if any(k in t for k in ["公示", "拟认定", "拟支持", "拟奖励", "拟立项", "拟入库"]):
        return "公示通知"
    if any(k in t for k in ["名单", "入库", "公布"]):
        return "名单公布"
    if any(k in t for k in ["立项", "验收", "评价结果", "绩效评价", "评估"]):
        return "立项与评价通知"
    if any(k in t for k in ["拨付", "兑现", "发放", "下达", "领取", "资金安排", "给予"]):
        return "领补贴通知"
    if any(k in t for k in ["申报", "征集", "开展", "推荐", "认定", "复核", "评价",
                            "备案", "申请"]):
        return "申报通知"
    return "政策红头文件"


MONEY_RE = re.compile(
    r"[^。；;\n]{0,90}?(?:给予|一次性|最高|不超过|奖励|补贴|资助|支持|配套)"
    r"[^。；;\n]{0,70}?\d[\d,\.]*\s*(?:万元|万|元)[^。；;\n]{0,30}")
COND_RE = re.compile(
    r"[^。；;\n]{0,20}?(?:申报条件|申请条件|支持对象|申报对象|认定条件|基本条件|"
    r"应符合|应当符合|申报要求)[^。；;\n]{0,150}")


def extract_benefits(txt):
    out, seen = [], set()
    for m in MONEY_RE.finditer(txt or ""):
        s = re.sub(r"\s+", " ", m.group(0)).strip(" ,，、。；")
        if len(s) < 10 or s in seen:
            continue
        seen.add(s); out.append(s)
        if len(out) >= 3:
            break
    return out


def extract_conditions(txt):
    out, seen = [], set()
    for m in COND_RE.finditer(txt or ""):
        s = re.sub(r"\s+", " ", m.group(0)).strip(" ,，、：:。；")
        if len(s) < 12 or s in seen:
            continue
        seen.add(s); out.append(s)
        if len(out) >= 3:
            break
    return out


def relevant(t):
    if any(x in t for x in JUNK):
        return False
    if any(k in t for k in TARGET):
        return True
    if any(k in t for k in ["科技", "科创", "研发", "创新", "技术中心", "专项资金",
                            "孵化器", "众创空间", "成果转化", "知识产权"]):
        return any(a in t for a in ACTION)
    return False


def score(r):
    s = 0
    if r["category"] in ("高新技术企业", "专精特新中小企业", "创新型中小企业",
                         "科技型中小企业", "科技小巨人", "科技创新券"):
        s += 100
    elif r["category"] == "专项资金与补贴":
        s += 45
    else:
        s += 10
    y = r["publishDate"][:4]
    s += {"2026": 40, "2025": 30, "2024": 20, "2023": 8}.get(y, 0)
    if r["noticeType"] in ("申报通知", "公示通知", "领补贴通知", "名单公布", "立项与评价通知"):
        s += 15
    if r.get("benefits"):
        s += 6
    if r.get("conditions"):
        s += 6
    if r.get("docNo"):
        s += 3
    if not r["publishDate"]:
        s -= 15
    return s


def main():
    d = json.load(open(os.path.join(RAW, "final_cands.json")))
    flat = []
    for grp, items in d.items():
        for r in items:
            r["_grp"] = grp
            flat.append(r)
    extra_p = os.path.join(RAW, "jd_extra.json")
    if os.path.exists(extra_p):
        for r in json.load(open(extra_p)):
            r["_grp"] = "jd_extra"
            flat.append(r)
    print("原始:", len(flat))

    seen, uniq = set(), []
    for r in flat:
        u = r.get("url") or ""
        if u.startswith("http://") and "jiading" in u:
            r["url"] = "https://" + u.split("://", 1)[1]
        k = re.sub(r"\s+", "", r.get("title", ""))
        if not k or k in seen or not r.get("url"):
            continue
        seen.add(k); uniq.append(r)
    print("去重:", len(uniq))

    rel = [r for r in uniq if relevant(r["title"])]
    print("相关:", len(rel))
    json.dump(rel, open(os.path.join(RAW, "rel_cands.json"), "w"),
              ensure_ascii=False, indent=1)

    # 抓正文（已有 _txt 的跳过）
    todo = [r for r in rel if not r.get("_txt")]
    print("抓正文:", len(todo))
    done = [0]

    def work(r):
        r["_txt"] = fetch_text(r["url"])
        done[0] += 1
        if done[0] % 40 == 0:
            print("   ", done[0], "/", len(todo))
        return r

    with ThreadPoolExecutor(max_workers=8) as ex:
        list(ex.map(work, todo))

    for r in rel:
        r["category"] = classify_category(r["title"])
        r["noticeType"] = classify_notice(r["title"])
        r["conditions"] = extract_conditions(r.get("_txt", ""))
        r["benefits"] = extract_benefits(r.get("_txt", ""))
        if not r.get("publishDate"):
            m = re.search(r"/(20\d{2})(\d{2})(\d{2})/", r["url"])
            if m:
                r["publishDate"] = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"

    # URL 校验
    urls = sorted({r["url"] for r in rel})
    print("校验 URL:", len(urls))
    status = {}
    with ThreadPoolExecutor(max_workers=10) as ex:
        futs = {ex.submit(http_status, u): u for u in urls}
        for f in as_completed(futs):
            status[futs[f]] = f.result()
    ok = sum(1 for v in status.values() if v == "200")
    print(f"HTTP 200: {ok}/{len(urls)}")
    # 失败项放慢节奏复验一次（部分站点限流）
    bad = [u for u, v in status.items() if v != "200"]
    print(f"复验失败项: {len(bad)}")
    for u in bad:
        time.sleep(2.0)
        c = http_status(u)
        if c == "200":
            status[u] = "200"
    ok2 = sum(1 for v in status.values() if v == "200")
    print(f"复验后 HTTP 200: {ok2}/{len(urls)}")

    good = [r for r in rel if status.get(r["url"]) == "200"]
    by = {}
    for r in good:
        by.setdefault(r["district"], []).append(r)

    final = []
    for dist in ["浦东新区", "徐汇区", "闵行区", "嘉定区", "松江区"]:
        lst = sorted(by.get(dist, []), key=score, reverse=True)
        picked, percat = [], {}
        for r in lst:
            c = r["category"]
            if percat.get(c, 0) >= 5:
                continue
            percat[c] = percat.get(c, 0) + 1
            picked.append(r)
            if len(picked) >= 12:
                break
        print(f"{dist}: 可用 {len(lst):3d} -> 选取 {len(picked)}")
        final.extend(picked)

    out = [{
        "title": r["title"], "publishDate": r["publishDate"], "url": r["url"],
        "docNo": r.get("docNo", ""), "issuer": r.get("issuer", ""),
        "district": r["district"], "category": r["category"],
        "noticeType": r["noticeType"], "conditions": r["conditions"],
        "benefits": r["benefits"], "pdfUrls": r.get("pdfUrls", []),
    } for r in final]

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(out, open(OUT, "w"), ensure_ascii=False, indent=1)
    json.dump(status, open(os.path.join(RAW, "url_status.json"), "w"),
              ensure_ascii=False, indent=1)
    print("写出:", OUT, "共", len(out), "条")


if __name__ == "__main__":
    main()
