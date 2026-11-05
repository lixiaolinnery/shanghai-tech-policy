#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""district_d v3: 选定 -> 抓详情 -> 抽取字段 -> 校验 200 -> district_d.json"""
import json, os, re, subprocess, sys, time, collections
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw_district")
OUT = os.path.join(ROOT, "data", "district", "district_d.json")
os.makedirs(os.path.dirname(OUT), exist_ok=True)

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")

FOCUS = ["企业技术中心", "专利试点示范", "重大产业攻关", "揭榜挂帅", "制造业单项冠军"]
ALLOWED_CATS = set(FOCUS + ["高新技术企业", "专精特新中小企业", "创新型中小企业",
                            "科技型中小企业", "科技小巨人", "科技创新券",
                            "专项资金与补贴", "其他科技政策"])
ALLOWED_TYPES = {"政策红头文件", "申报通知", "公示通知", "领补贴通知",
                 "立项与评价通知", "名单公布"}
DISTRICTS = ["杨浦区", "静安区", "普陀区", "长宁区", "奉贤区", "临港新片区"]

JINGAN_EXTRA = [
    ("静安区科技和经济委员会关于组织开展2025年度静安区企业技术中心认定工作的通知",
     "https://www.jingan.gov.cn/govxxgk/JA5/2025-03-24/a85a3a88-cea8-4107-a347-a01a9891335b.html",
     "企业技术中心", "申报通知", "2025-03-24"),
    ("关于2024年度静安区企业技术中心认定结果的通知",
     "https://www.jingan.gov.cn/govxxgk/JA5/2024-09-14/b48888af-7ce3-4228-9d2c-4559d72f8f34.html",
     "企业技术中心", "名单公布", "2024-09-14"),
    ("关于印发《静安区企业技术中心管理办法》的通知",
     "https://www.jingan.gov.cn/govxxgk/JA5/2026-03-09/7e9ca703-c950-4605-b2a9-dff5ad489873.html",
     "企业技术中心", "政策红头文件", "2026-03-09"),
    ("关于开展2026年静安区知识产权资助奖励申报工作的通知",
     "https://www.jingan.gov.cn/govxxgk/JC6/2026-04-08/9df94fa6-c9fe-4526-9cdb-c1ea9a17b2a6.html",
     "专利试点示范", "申报通知", "2026-04-08"),
    ("关于开展2025年静安区数据智能产业高质量发展项目申报工作的通知",
     "https://www.jingan.gov.cn/govxxgk/JA5/2025-09-28/352a85bb-5a26-4af4-9561-5256ff3c5276.html",
     "重大产业攻关", "申报通知", "2025-09-28"),
    ("上海市静安区科技和经济委员会关于征集静安区AI+赋能行业应用场景的通知",
     "https://www.jingan.gov.cn/govxxgk/JA5/2025-08-20/0d0b7c65-4c33-4e01-9008-e39f95efe8b3.html",
     "重大产业攻关", "申报通知", "2025-08-20"),
    ("关于《静安区企业技术中心管理办法（征求意见稿）》征求公众意见的公告",
     "https://www.jingan.gov.cn/govxxgk/JA5/2025-10-22/a9f94cfd-8dbd-4491-bc3a-cadfca82c150.html",
     "企业技术中心", "政策红头文件", "2025-10-22"),
]

SHORT_DEPT = re.compile(r"^(科委|经委|商务委|市场监管局|知识产权局|发改委|科经委|"
                        r"财政局|投促办|数据局|质量技监局)$")


def curl(url, timeout=40, retries=3):
    for i in range(retries):
        try:
            p = subprocess.run(
                ["curl", "-sS", "-L", "--compressed", "-m", str(timeout),
                 "-w", "\n@@HTTP:%{http_code}", "-H", f"User-Agent: {UA}",
                 "-H", "Accept-Language: zh-CN,zh;q=0.9", url],
                capture_output=True, timeout=timeout + 15)
            raw = p.stdout.decode("utf-8", "replace")
            m = re.search(r"@@HTTP:(\d+)\s*$", raw)
            code = int(m.group(1)) if m else 0
            body = raw[: m.start()] if m else raw
            if body.strip():
                return code, body
        except Exception:
            pass
        time.sleep(1.2 * (i + 1))
    return 0, ""


def strip_tags(s):
    s = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", s)
    s = re.sub(r"<[^>]+>", " ", s)
    for a, b in (("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"),
                 ("&gt;", ">"), ("&quot;", '"'), ("&#39;", "'")):
        s = s.replace(a, b)
    return re.sub(r"\s+", " ", s).strip()


DATE_PATS = [
    r"发布日期[：:\s]*(\d{4})[-/年\.](\d{1,2})[-/月\.](\d{1,2})",
    r"发表时间[：:\s]*(\d{4})[-/年\.](\d{1,2})[-/月\.](\d{1,2})",
    r"发布时间[：:\s]*(\d{4})[-/年\.](\d{1,2})[-/月\.](\d{1,2})",
    r"成文日期[：:\s]*(\d{4})[-/年\.](\d{1,2})[-/月\.](\d{1,2})",
    r"发文日期[：:\s]*(\d{4})[-/年\.](\d{1,2})[-/月\.](\d{1,2})",
]


def find_date(text):
    head = text[:12000]
    for p in DATE_PATS:
        m = re.search(p, head)
        if m:
            y, mo, d = m.group(1), int(m.group(2)), int(m.group(3))
            if 2000 <= int(y) <= 2030 and 1 <= mo <= 12 and 1 <= d <= 31:
                return f"{y}-{mo:02d}-{d:02d}"
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})\s*\d{2}:\d{2}", head)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return ""


TITLE_LEAD = re.compile(r"^\s*(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})日?\s*[:：]?\s*")


def clean_title(t):
    m = TITLE_LEAD.match(t or "")
    d = ""
    if m:
        y, mo, dd = m.group(1), int(m.group(2)), int(m.group(3))
        if 1 <= mo <= 12 and 1 <= dd <= 31:
            d = f"{y}-{mo:02d}-{dd:02d}"
        t = TITLE_LEAD.sub("", t).strip()
    return t, d


def url_date(url):
    m = re.search(r"/(\d{4})[-/](\d{1,2})[-/](\d{1,2})/", url)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    m = re.search(r"/(\d{4})(\d{2})(\d{2})/", url)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = re.search(r"/(\d{4})[-/](\d{1,2})/", url)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-01"
    return ""


def meta_content(body, name):
    m = re.search(rf'<meta[^>]+name="{name}"[^>]+content="([^"]*)"', body, re.I)
    if not m:
        m = re.search(rf'<meta[^>]+content="([^"]*)"[^>]+name="{name}"', body, re.I)
    return m.group(1).strip() if m else ""


def extract_issuer(body, text, rec):
    if rec.get("issuer"):
        return rec["issuer"]
    for n in ("ContentSource", "Source", "Author", "ArticleSource", "source"):
        v = meta_content(body, n)
        if v and v not in ("", "-"):
            if SHORT_DEPT.match(v):
                return f"{rec['district']}{v}"
            return v
    m = re.search(r"(?:来源|发布单位|发布机构|发文机关|制发单位)[：:]\s*([^\s，,。;；|]{4,40})",
                  text[:6000])
    if m:
        return m.group(1).strip()
    return ""


def extract_docno(text):
    m = re.search(r"文\s*号[：:\s]*([^\s，,。;；|]{3,40})", text[:8000])
    if m:
        v = m.group(1).strip()
        if 3 < len(v) < 40 and "：" not in v and not v.startswith("无"):
            return v
    return ""


MONEY = re.compile(r"[^。；;]{0,70}?(?:奖励|补贴|资助|扶持|补助|支持|给予)"
                   r"[^。；;]{0,60}?(?:\d[\d,\.]*\s*(?:万元|亿元|万|元))[^。；;]{0,30}")


def extract_benefits(text):
    out = []
    for m in MONEY.finditer(text):
        s = m.group(0).strip(" ，,。;；、")
        if 8 < len(s) < 170 and s not in out:
            out.append(s)
        if len(out) >= 5:
            break
    return out


COND = re.compile(r"(?:申报条件|申请条件|认定条件|基本条件|应当具备|应具备|"
                  r"须?符合下列条件|申报要求)[：:]?\s*([^。]{10,500})")


def extract_conditions(text):
    out = []
    m = COND.search(text)
    if m:
        seg = m.group(1)
        for part in re.split(r"[；;]|\d+[、．.]|（[一二三四五六七八九十]）", seg):
            p = part.strip(" ，,。;；、")
            if 8 <= len(p) <= 130:
                out.append(p)
            if len(out) >= 6:
                break
    return out


def find_pdfs(body):
    res = []
    for u in re.findall(r'href="([^"]+\.pdf)"', body, re.I):
        if u.startswith("//"):
            u = "https:" + u
        elif not u.startswith("http"):
            continue
        if u not in res:
            res.append(u)
    return res[:5]


NT_RULES = [
    ("公示通知", r"公示|拟认定|拟立项|征求意见|征询"),
    ("名单公布", r"名单|公布|认定结果|下达|批复|确定"),
    ("立项与评价通知", r"立项|评价|验收|考核"),
    ("领补贴通知", r"拨付|领取|兑现|办理.{0,6}奖励|资助申报"),
    ("政策红头文件", r"办法|实施方案|实施意见|若干政策|若干措施|规定|细则|指南$"),
    ("申报通知", r"申报|征集|开展|组织|发榜|揭榜|申请|通知"),
]


def infer_type(title):
    for n, p in NT_RULES:
        if re.search(p, title):
            return n
    return "申报通知"


def work(rec):
    url = rec.get("url") or ""
    if not url:
        return rec, 0, ""
    code, body = curl(url)
    return rec, code, body


def main():
    sel = json.load(open(os.path.join(RAW, "selection_d.json"), encoding="utf-8"))
    for t, u, cat, nt, dt in JINGAN_EXTRA:
        sel.append({"district": "静安区", "title": t, "url": u, "date": dt,
                    "category": cat, "issuer": "", "src": "人工核对", "forceType": nt})
    # 去重
    seen, s2 = set(), []
    for r in sel:
        if r["url"] in seen:
            continue
        seen.add(r["url"])
        s2.append(r)
    sel = s2
    print(f"fetching {len(sel)} detail pages...", file=sys.stderr)

    results = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(work, r): r for r in sel}
        done = 0
        for f in as_completed(futs):
            rec, code, body = f.result()
            results[rec["url"]] = (code, body)
            done += 1
            if done % 30 == 0:
                print(f"  {done}/{len(sel)}", file=sys.stderr)

    out, failed = [], []
    for r in sel:
        code, body = results.get(r["url"], (0, ""))
        if code != 200 or not body:
            failed.append((r["title"], r["url"], code))
            continue
        text = strip_tags(body)
        title = r["title"].strip()
        if not title:
            m = re.search(r"<title>([^<]*)</title>", body)
            title = (m.group(1).strip() if m else "")
        title, tdate = clean_title(title)
        if not title:
            continue
        pdate = find_date(text) or tdate or r.get("date") or "" or url_date(r["url"])
        if not find_date(text):
            ym = re.search(r"(20\d{2})\s*年", title)
            if ym and ("shanghai.gov.cn" in r["url"]):
                m2 = re.search(rf"{ym.group(1)}年(\d{{1,2}})月(\d{{1,2}})日", text[:6000])
                if m2:
                    pdate = f"{ym.group(1)}-{int(m2.group(1)):02d}-{int(m2.group(2)):02d}"
        cat = r["category"] if r["category"] in ALLOWED_CATS else "其他科技政策"
        nt = r.get("forceType") or infer_type(title)
        if nt not in ALLOWED_TYPES:
            nt = "申报通知"
        out.append({
            "title": title,
            "publishDate": pdate,
            "url": r["url"],
            "docNo": extract_docno(text),
            "issuer": extract_issuer(body, text, r),
            "district": r["district"],
            "category": cat,
            "noticeType": nt,
            "conditions": extract_conditions(text),
            "benefits": extract_benefits(text),
            "pdfUrls": find_pdfs(body),
        })

    json.dump(out, open(OUT, "w"), ensure_ascii=False, indent=1)
    cnt = collections.Counter(x["district"] for x in out)
    ccnt = collections.Counter(x["category"] for x in out)
    print(f"written {len(out)} -> {OUT}", file=sys.stderr)
    print("districts:", dict(cnt), file=sys.stderr)
    print("categories:", dict(ccnt), file=sys.stderr)
    print(f"failed({len(failed)}):", file=sys.stderr)
    for t, u, c in failed[:20]:
        print(f"  [{c}] {t[:50]} {u}", file=sys.stderr)


if __name__ == "__main__":
    main()
