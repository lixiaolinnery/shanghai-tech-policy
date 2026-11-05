#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""district_e4: 金山（API）+ 青浦（列表页）直抓，产出候选 JSON。"""
import json, os, re, subprocess, sys, time, html as ihtml, datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw_district")
os.makedirs(RAW, exist_ok=True)

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")

CAT_KW = [
    ("企业技术中心", ["企业技术中心", "区级技术中心"]),
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
           "单项冠军", "高新技术企业", "高企", "专精特新", "创新型中小企业",
           "科技型中小企业", "小巨人", "科技创新券", "科技发展基金",
           "科技专项", "科技创新", "研发机构", "工程技术研究中心", "技术改造",
           "首台套", "智能工厂", "科技企业", "科技奖励", "科技项目", "科技计划",
           "孵化器", "众创空间", "科技成果", "科技人才", "产业专项",
           "专项资金", "科技扶持", "创新券"]

EXCLUDE_KW = ["体育", "招生", "学校", "教育", "养老", "老龄", "残疾", "卫生",
              "动物疫情", "绿化", "垃圾分类", "粮食", "农业", "宗教", "体育",
              "人事任免", "职务任免", "职级", "干部", "预算", "决算",
              "应急预案", "防汛", "河道", "水务", "体育", "文化", "旅游"]


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


def get(url, timeout=40, retries=3):
    for i in range(retries):
        try:
            t = curl([url], timeout)
            if t:
                return t
        except Exception:
            pass
        time.sleep(1.0 * (i + 1))
    return ""


def post_json(url, body, timeout=45, retries=3):
    payload = json.dumps(body, ensure_ascii=False)
    for i in range(retries):
        try:
            t = curl(["-H", "Content-Type: application/json", "-X", "POST",
                      "-d", payload, url], timeout)
            return json.loads(t)
        except Exception as e:
            if i == retries - 1:
                print("  ! post", url, e, file=sys.stderr)
                return {}
            time.sleep(1.0 * (i + 1))


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


def classify_cat(title, txt=""):
    for c, kws in CAT_KW:
        if any(k in title for k in kws):
            return c
    return ""


def is_tech(title):
    if any(k in title for k in EXCLUDE_KW):
        # 除非标题里明确有科技类关键词
        if not any(k in title for k in ["企业技术中心", "专利", "知识产权", "攻关",
                                        "揭榜", "单项冠军", "高新技术企业",
                                        "专精特新", "科技", "创新券"]):
            return False
    return any(k in title for k in TECH_KW)


# ============================================================ 金山区
JS = "https://www.jinshan.gov.cn"
JS_COLUMNS = {
    "11184": "区科委 政策文件",
    "10928": "区科委 主动公开",
    "11106": "区经委 政策文件",
    "10926": "区经委 主动公开",
    "11769": "区市场监管局 政策文件",
    "10943": "区市场监管局 主动公开",
}


def js_fetch_col(cid, max_pages=40):
    out, page = [], 1
    while page <= max_pages:
        d = post_json(f"{JS}/front/api/data/search",
                      {"channelList": [cid], "pageNo": page, "pageSize": 50})
        if not d or d.get("code") != 0:
            break
        data = d.get("data") or {}
        lst = data.get("list") or []
        if not lst:
            break
        for it in lst:
            out.append(it)
        total = int(data.get("totalPage") or 0)
        if page >= total:
            break
        page += 1
        time.sleep(0.2)
    return out


def js_run():
    rows = []
    for cid, name in JS_COLUMNS.items():
        items = js_fetch_col(cid)
        print(f" 金山 {name}({cid}): {len(items)}")
        for it in items:
            title = (it.get("title") or "").strip()
            if not is_tech(title):
                continue
            ts = it.get("display_date") or 0
            try:
                ds = datetime.datetime.fromtimestamp(
                    ts / 1000, datetime.timezone.utc).strftime("%Y-%m-%d") if ts else ""
            except Exception:
                ds = ""
            url = (it.get("url") or "")
            if url.startswith("/"):
                url = JS + url
            pdf = it.get("pdf_file_url") or ""
            if pdf.startswith("/"):
                pdf = JS + pdf
            docno = ""
            dt = (it.get("doc_num_type") or "").strip()
            dy = (it.get("doc_num_year") or "").strip()
            dn = (it.get("doc_num_no") or "").strip()
            if dt and dn:
                docno = f"{dt}〔{dy}〕{dn}号" if dy else f"{dt}{dn}号"
            rows.append({
                "title": title, "publishDate": ds, "url": url, "docNo": docno,
                "issuer": (it.get("dispatch_agency") or "").strip(),
                "district": "金山区", "category": classify_cat(title),
                "noticeType": "", "conditions": [], "benefits": [],
                "pdfUrls": [pdf] if pdf else [],
                "_src": f"jinshan-api:{cid}",
                "_id": it.get("id"),
            })
    print(" 金山候选", len(rows))
    json.dump(rows, open(os.path.join(RAW, "e4_jinshan.json"), "w"),
              ensure_ascii=False, indent=1)


# ============================================================ 青浦区
QP = "https://www.shqp.gov.cn"
QP_COLS = [
    "/scien/kwzwgk/ml/yw/", "/scien/kwzwgk/ml/zc/", "/scien/kwzwgk/ml/qt/",
    "/econ/jwzwgk/ml/yw/", "/econ/jwzwgk/ml/qt/",
    "/cindu/sczwgk/ml/yw/", "/cindu/sczwgk/ml/qt/",
    "/shqp/zwgk/zcwj/",
    "/econ/tzgg/",
    "/cindu/tzgg/",
]


def qp_list_col(col, max_pages=8):
    items = []
    for p in range(1, max_pages + 1):
        url = f"{QP}{col}index.html" if p == 1 else f"{QP}{col}index_{p}.html"
        h = get(url, timeout=30)
        if not h:
            break
        found = re.findall(r'<a href="([^"]+\.html)"[^>]*title="([^"]*)"', h)
        n = 0
        for href, title in found:
            if re.search(r"/20\d{2}\d{4}/\d+\.html", href):
                items.append((title.strip(), href if href.startswith("http")
                              else QP + href))
                n += 1
        if n == 0:
            break
        time.sleep(0.25)
    return items


def qp_detail(url):
    h = get(url, timeout=40)
    if not h:
        return {}
    title = ""
    m = re.search(r'<h1[^>]*>(.*?)</h1>', h, re.S)
    if m:
        title = ihtml.unescape(re.sub(r"<[^>]+>", "", m.group(1))).strip()
    if not title:
        m = re.search(r'name="ArticleTitle" content="([^"]*)"', h)
        if m:
            title = ihtml.unescape(m.group(1)).strip()
    date = ""
    for pat in (r'name="PubDate" content="([^"]*)"',
                r'id="pubdate"[^>]*>([^<]*)<',
                r'(20\d{2}[-./]\d{1,2}[-./]\d{1,2})'):
        m = re.search(pat, h)
        if m:
            mm = re.match(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", m.group(1))
            if mm:
                date = f"{mm.group(1)}-{int(mm.group(2)):02d}-{int(mm.group(3)):02d}"
                break
    docno = ""
    m = re.search(r"([\u4e00-\u9fa5]{1,14}[〔\[]20\d{2}[〕\]]\s*\d+\s*号)", h)
    if m:
        docno = m.group(1)
    issuer = ""
    m = re.search(r'name="ContentSource" content="([^"]*)"', h)
    if m:
        issuer = ihtml.unescape(m.group(1)).strip()
    return {"title": title, "date": date, "docno": docno, "issuer": issuer,
            "text": strip_html(h)[:20000]}


def qp_run():
    cand = {}
    for col in QP_COLS:
        its = qp_list_col(col)
        print(f" 青浦 {col}: {len(its)}")
        for t, u in its:
            if u not in cand:
                cand[u] = (t, col)
    print(" 青浦列表去重", len(cand))
    keep = {u: v for u, v in cand.items() if is_tech(v[0])}
    print(" 青浦关键词命中", len(keep))
    rows = []
    with ThreadPoolExecutor(max_workers=3) as ex:
        futs = {ex.submit(qp_detail, u): u for u in keep}
        for f in as_completed(futs):
            u = futs[f]
            try:
                d = f.result()
            except Exception:
                d = {}
            t0 = keep[u][0]
            title = d.get("title") or t0
            if not is_tech(title):
                continue
            rows.append({
                "title": title, "publishDate": d.get("date", ""), "url": u,
                "docNo": d.get("docno", ""), "issuer": d.get("issuer", ""),
                "district": "青浦区", "category": classify_cat(title),
                "noticeType": "", "conditions": [], "benefits": [],
                "pdfUrls": [], "_src": "qingpu-list",
                "_text": d.get("text", "")[:4000],
            })
    print(" 青浦候选", len(rows))
    json.dump(rows, open(os.path.join(RAW, "e4_qingpu.json"), "w"),
              ensure_ascii=False, indent=1)


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    if what in ("all", "js"):
        js_run()
    if what in ("all", "qp"):
        qp_run()
