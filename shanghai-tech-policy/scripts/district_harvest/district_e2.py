#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""district_e2: 直接抓区官网列表页（青浦 / 金山 / 崇明 / 虹口）。"""
import json, os, re, subprocess, sys, time, html as ihtml
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw_district")
os.makedirs(RAW, exist_ok=True)

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")

# 标题关键词 -> category
CAT_KW = [
    ("企业技术中心", ["企业技术中心", "技术中心"]),
    ("制造业单项冠军", ["单项冠军"]),
    ("揭榜挂帅", ["揭榜挂帅", "揭榜", "发榜"]),
    ("重大产业攻关", ["攻关"]),
    ("专利试点示范", ["专利", "知识产权"]),
    ("高新技术企业", ["高新技术企业", "高企"]),
    ("专精特新中小企业", ["专精特新"]),
    ("创新型中小企业", ["创新型中小企业"]),
    ("科技型中小企业", ["科技型中小企业"]),
    ("科技小巨人", ["科技小巨人", "小巨人"]),
    ("科技创新券", ["科技创新券"]),
]

TECH_KW = ["企业技术中心", "技术中心", "专利", "知识产权", "攻关", "揭榜", "发榜",
           "单项冠军", "冠军", "高新技术企业", "高企", "专精特新", "创新型中小企业",
           "科技型中小企业", "小巨人", "科技小巨人", "科技创新券", "科技发展基金",
           "科技专项", "科技创新", "研发机构", "工程技术研究中心", "技术改造",
           "首台套", "智能工厂", "科技企业", "科技奖励", "科技项目", "科技计划",
           "孵化器", "众创空间", "科技成果", "科技人才", "产业专项", "专项资金",
           "扶持", "奖励", "补贴", "资助", "认定", "科技", "创新"]


def curl(args, timeout=45):
    cmd = ["curl", "-sS", "-L", "-k", "--compressed", "-m", str(timeout),
           "-H", f"User-Agent: {UA}", "-H", "Accept-Language: zh-CN,zh;q=0.9"] + args
    p = subprocess.run(cmd, capture_output=True, timeout=timeout + 25)
    raw = p.stdout
    if not raw:
        return ""
    for enc in ("utf-8", "gb18030"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


def get(url, timeout=45, retries=3):
    for i in range(retries):
        try:
            t = curl([url], timeout)
            if t:
                return t
        except Exception:
            pass
        time.sleep(1.0 * (i + 1))
    return ""


def http_status(url, timeout=30):
    cmd = ["curl", "-sS", "-L", "-k", "-o", "/dev/null", "-m", str(timeout),
           "-H", f"User-Agent: {UA}", "-w", "%{http_code}", url]
    for _ in range(2):
        try:
            p = subprocess.run(cmd, capture_output=True, timeout=timeout + 15)
            return p.stdout.decode().strip() or "000"
        except Exception:
            time.sleep(1)
    return "000"


def strip_html(s):
    if not s:
        return ""
    s = re.sub(r"<script.*?</script>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<style.*?</style>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = ihtml.unescape(s)
    s = re.sub(r"[\u3000\xa0]", " ", s)
    s = re.sub(r"[ \t\r\f\v]+", " ", s)
    s = re.sub(r"\n\s*\n+", "\n", s)
    return s.strip()


def classify_cat(title):
    for c, kws in CAT_KW:
        if any(k in title for k in kws):
            return c
    return ""


def classify_notice(title):
    rules = [
        ("政策红头文件", ["管理办法", "实施细则", "若干措施", "实施办法", "暂行办法",
                          "实施意见", "操作办法", "工作指引", "认定办法", "奖励办法",
                          "资助办法", "扶持办法", "若干政策", "政策措施", "办法",
                          "实施方案", "行动方案", "专项规划"]),
        ("公示通知", ["公示", "拟认定", "拟支持", "拟奖励", "拟立项", "拟入库", "拟通过", "拟补助"]),
        ("名单公布", ["名单", "公布", "结果", "公告"]),
        ("立项与评价通知", ["立项", "验收", "评价", "评估", "绩效"]),
        ("领补贴通知", ["拨付", "兑现", "发放", "下达", "领取", "资金安排", "奖励资金", "资助资金"]),
        ("申报通知", ["申报", "征集", "开展", "推荐", "认定", "复核", "备案", "申请", "组织"]),
    ]
    for nt, kws in rules:
        if any(k in title for k in kws):
            return nt
    return "申报通知"


MONEY_RE = re.compile(
    r"[^。；;\n]{0,80}?(?:给予|一次性|最高|按|不超过|奖励|补贴|资助|支持|扶持)"
    r"[^。；;\n]{0,60}?(?:\d[\d,\.]*\s*(?:万元|万|元))[^。；;\n]{0,40}")
COND_RE = re.compile(
    r"[^。；;\n]{0,30}?(?:申报条件|申请条件|支持对象|申报对象|认定条件|应符合|应当符合|"
    r"基本条件|申报范围|支持范围|培育对象)[^。；;\n]{0,140}")


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


def norm_date(v):
    if not v:
        return ""
    m = re.match(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", str(v))
    return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}" if m else ""


def make_url(href, base):
    if href.startswith("http"):
        return href
    if href.startswith("/"):
        return base + href
    return base + "/" + href


# ============================================================== 青浦区
QP = "https://www.shqp.gov.cn"
QP_COLS = [
    "/scien/kwzwgk/ml/yw/", "/scien/kwzwgk/ml/zc/", "/scien/kwzwgk/ml/qt/",
    "/econ/jwzwgk/ml/yw/", "/econ/jwzwgk/ml/qt/",
    "/cindu/sczwgk/ml/yw/", "/cindu/sczwgk/ml/qt/",
    "/shqp/zwgk/zcwj/",
]


def qp_list(col, max_pages=6):
    items = []
    for p in range(1, max_pages + 1):
        url = f"{QP}{col}index.html" if p == 1 else f"{QP}{col}index_{p}.html"
        h = get(url, timeout=30)
        if not h:
            break
        found = re.findall(
            r'<a href="([^"]+\.html)"[^>]*title="([^"]*)"', h)
        n = 0
        for href, title in found:
            if re.search(r"/(20\d{2})\d{4}/\d+\.html", href):
                items.append((title.strip(), make_url(href, QP)))
                n += 1
        if n == 0:
            break
        time.sleep(0.3)
    return items


def qp_detail(url):
    h = get(url, timeout=40)
    if not h:
        return {}
    title = ""
    m = re.search(r"<title>(.*?)</title>", h, re.S)
    if m:
        title = re.sub(r"\s+", " ", ihtml.unescape(m.group(1))).strip()
        title = re.sub(r"^上海市?青浦区.*?[—\-|_].*", lambda x: "", title) or title
    # 更可靠：页面里的 h1 / 正文标题
    m2 = re.search(r'<h1[^>]*>(.*?)</h1>', h, re.S)
    if m2:
        t2 = re.sub(r"<[^>]+>", "", m2.group(1)).strip()
        if len(t2) > 6:
            title = ihtml.unescape(t2)
    date = ""
    m3 = re.search(r"(20\d{2}[-./]\d{1,2}[-./]\d{1,2})", h)
    if m3:
        date = norm_date(m3.group(1))
    docno = ""
    m4 = re.search(r"([\u4e00-\u9fa5]{1,12}[〔\[]20\d{2}[〕\]]\s*\d+\s*号)", h)
    if m4:
        docno = m4.group(1)
    return {"raw": h, "title": title, "date": date, "docno": docno,
            "text": strip_html(h)[:20000]}


# ============================================================== 金山区
JS = "https://www.jinshan.gov.cn"
JS_COLS = []


def js_discover():
    """从金山政务公开页发现部门栏目。"""
    h = get(f"{JS}/zhengwu/", timeout=30)
    cols = set(re.findall(r'href="(/zhengwu/[a-z0-9\-]+/[^"]*?)"', h))
    return sorted(cols)


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "qp"
    if mode == "qp":
        allitems = []
        for col in QP_COLS:
            its = qp_list(col)
            print(f"{col}: {len(its)}")
            for t, u in its:
                allitems.append({"title": t, "url": u, "col": col})
        # 去重
        seen, uniq = set(), []
        for it in allitems:
            if it["url"] in seen:
                continue
            seen.add(it["url"])
            uniq.append(it)
        print("uniq", len(uniq))
        json.dump(uniq, open(os.path.join(RAW, "qp_list.json"), "w"),
                  ensure_ascii=False, indent=1)
    elif mode == "js":
        cols = js_discover()
        print(len(cols))
        for c in cols[:80]:
            print(" ", c)
        json.dump(cols, open(os.path.join(RAW, "js_cols.json"), "w"),
                  ensure_ascii=False, indent=1)
