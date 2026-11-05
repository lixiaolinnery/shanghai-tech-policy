#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""采集上海 5 个区级科技类政策通知。

数据源：上海市政府官网统一政策发布平台的检索接口
  POST https://find.shanghai.gov.cn/search   (Content-Type: text/plain)
详情：POST https://www.shanghai.gov.cn/gwk/policy/detail  -> originUrl / txt / docNo
附件 PDF：https://www.shanghai.gov.cn/gwk/resource/file?pathname=...
"""
import json, os, re, subprocess, sys, time, html as ihtml
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "data", "district")
RAW_DIR = os.path.join(ROOT, "data", "raw_district")
os.makedirs(OUT_DIR, exist_ok=True)
os.makedirs(RAW_DIR, exist_ok=True)

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")

DISTRICTS = {
    "浦东新区": "0070",
    "徐汇区": "0073",
    "闵行区": "0079",
    "嘉定区": "0080",
    "松江区": "0082",
}

# 检索关键词 -> 归类
QUERIES = [
    ("高新技术企业", ["高新技术企业认定", "高新技术企业奖励", "高企"]),
    ("专精特新中小企业", ["专精特新中小企业", "专精特新"]),
    ("创新型中小企业", ["创新型中小企业"]),
    ("科技型中小企业", ["科技型中小企业", "科技型中小企业评价"]),
    ("科技小巨人", ["科技小巨人"]),
    ("科技创新券", ["科技创新券"]),
    ("专项资金与补贴", ["科技专项资金", "科技发展基金", "科技创新奖励"]),
]


def curl(args, timeout=40):
    cmd = ["curl", "-sS", "-L", "--compressed", "-m", str(timeout),
           "-H", f"User-Agent: {UA}", "-H", "Accept-Language: zh-CN,zh;q=0.9"] + args
    p = subprocess.run(cmd, capture_output=True, timeout=timeout + 15)
    raw = p.stdout
    if not raw:
        raise RuntimeError(f"empty body rc={p.returncode} err={p.stderr[:200]!r}")
    for enc in ("utf-8", "gb18030"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


def search(q, site_id, page=1, size=20, retries=3):
    body = json.dumps({"q": q, "page": page, "size": size, "siteId": [site_id]},
                      ensure_ascii=False)
    for i in range(retries):
        try:
            txt = curl(["-H", "Content-Type: text/plain", "-X", "POST",
                        "-d", body, "https://find.shanghai.gov.cn/search"])
            return json.loads(txt)
        except Exception as e:  # noqa
            if i == retries - 1:
                print(f"  ! search fail {q} {site_id}: {e}", file=sys.stderr)
                return None
            time.sleep(1.2 * (i + 1))


def detail(site_id, business_id, retries=3):
    body = json.dumps({"siteId": site_id, "businessId": business_id})
    for i in range(retries):
        try:
            txt = curl(["-H", "Content-Type: application/json", "-X", "POST",
                        "-d", body, "https://www.shanghai.gov.cn/gwk/policy/detail"])
            return json.loads(txt)
        except Exception as e:  # noqa
            if i == retries - 1:
                print(f"  ! detail fail {business_id}: {e}", file=sys.stderr)
                return None
            time.sleep(1.2 * (i + 1))


def http_status(url, timeout=30):
    """返回 (status_code, content_type)。"""
    cmd = ["curl", "-sS", "-L", "-k", "-o", "/dev/null", "-m", str(timeout),
           "-H", f"User-Agent: {UA}", "-w", "%{http_code} %{content_type}", url]
    try:
        p = subprocess.run(cmd, capture_output=True, timeout=timeout + 15)
        out = p.stdout.decode("utf-8", "replace").strip()
        code = out.split(" ")[0] if out else "000"
        return code, out
    except Exception:
        return "000", ""


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


TITLE_RULES = [
    ("高新技术企业", ["高新技术企业", "高企"]),
    ("专精特新中小企业", ["专精特新"]),
    ("创新型中小企业", ["创新型中小企业"]),
    ("科技型中小企业", ["科技型中小企业"]),
    ("科技小巨人", ["科技小巨人"]),
    ("科技创新券", ["科技创新券"]),
]


def classify_category(title, txt_head):
    for cat, kws in TITLE_RULES:
        if any(k in title for k in kws):
            return cat
    for cat, kws in TITLE_RULES:
        if any(k in txt_head for k in kws):
            return cat
    if any(k in title for k in ["专项资金", "奖励", "补贴", "资助", "资金", "兑现", "拨付"]):
        return "专项资金与补贴"
    return "其他科技政策"


def classify_notice(title):
    t = title
    if any(k in t for k in ["管理办法", "实施细则", "若干措施", "实施办法", "暂行办法",
                            "实施意见", "操作办法", "工作指引", "认定办法", "奖励办法",
                            "资助办法", "办法（试行）", "若干政策"]):
        return "政策红头文件"
    if any(k in t for k in ["公示", "拟认定", "拟支持", "拟奖励", "拟立项", "拟入库", "拟通过"]):
        return "公示通知"
    if any(k in t for k in ["名单", "公布", "结果"]):
        return "名单公布"
    if any(k in t for k in ["立项", "验收", "评价结果", "绩效评价", "评估"]):
        return "立项与评价通知"
    if any(k in t for k in ["拨付", "兑现", "发放", "下达", "领取", "资金安排", "奖励资金"]):
        return "领补贴通知"
    if any(k in t for k in ["申报", "征集", "开展", "推荐", "认定", "复核", "评价", "备案", "申请"]):
        return "申报通知"
    return "其他"


MONEY_RE = re.compile(
    r"[^。；;\n]{0,80}?(?:给予|一次性|最高|按|不超过|奖励|补贴|资助|支持)[^。；;\n]{0,60}?"
    r"(?:\d[\d,\.]*\s*(?:万元|万|元))[^。；;\n]{0,40}")


def extract_benefits(txt):
    out, seen = [], set()
    for m in MONEY_RE.finditer(txt):
        s = re.sub(r"\s+", " ", m.group(0)).strip(" ,，、")
        if len(s) < 8:
            continue
        if s in seen:
            continue
        seen.add(s)
        out.append(s)
        if len(out) >= 4:
            break
    return out


COND_RE = re.compile(
    r"[^。；;\n]{0,30}?(?:申报条件|申请条件|支持对象|申报对象|认定条件|应符合|应当符合|基本条件)"
    r"[^。；;\n]{0,140}")


def extract_conditions(txt):
    out, seen = [], set()
    for m in COND_RE.finditer(txt):
        s = re.sub(r"\s+", " ", m.group(0)).strip(" ,，、：:")
        if len(s) < 10:
            continue
        if s in seen:
            continue
        seen.add(s)
        out.append(s)
        if len(out) >= 4:
            break
    return out


def pdf_urls(attrs):
    urls = []
    for key in ("zwPDFUrl",):
        p = attrs.get(key)
        if p and p.startswith("/"):
            urls.append("https://www.shanghai.gov.cn/gwk/resource/file?pathname="
                        + p.split("pathname=", 1)[-1])
    return urls


def main():
    cands = {}
    for dname, sid in DISTRICTS.items():
        for cat, kws in QUERIES:
            for kw in kws:
                r = search(kw, sid, page=1, size=20)
                if not r or r.get("code") != 0:
                    continue
                rl = (r.get("data") or {}).get("resultList") or []
                print(f"[{dname}] {kw!r}: {len(rl)} / total={r['data'].get('totalHits')}")
                for it in rl:
                    bid = it.get("businessId")
                    if not bid:
                        continue
                    key = (sid, bid)
                    if key not in cands:
                        it["_district"] = dname
                        it["_query_cat"] = cat
                        cands[key] = it
                time.sleep(0.25)

    print(f"\n候选合计: {len(cands)}")
    json.dump(list(cands.values()), open(os.path.join(RAW_DIR, "candidates.json"), "w"),
              ensure_ascii=False, indent=1)

    # 拉详情
    items = list(cands.items())

    def work(kv):
        (sid, bid), it = kv
        d = detail(sid, bid)
        return (sid, bid), it, d

    results = []
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = [ex.submit(work, kv) for kv in items]
        for n, f in enumerate(as_completed(futs), 1):
            try:
                results.append(f.result())
            except Exception as e:  # noqa
                print("detail err", e, file=sys.stderr)
            if n % 40 == 0:
                print(f"  detail {n}/{len(items)}")

    recs = []
    for (sid, bid), it, d in results:
        data = (d or {}).get("data") or {}
        title = data.get("title") or it.get("title") or ""
        if not title:
            continue
        txt = strip_html(data.get("txt") or data.get("content") or "")
        attrs = data.get("attrs") or it.get("attrs") or {}
        origin_url = data.get("originUrl") or it.get("originUrl") or ""
        pub = (data.get("publishDate") or it.get("publishDate")
               or it.get("displayDate") or "")[:10]
        doc_type = data.get("docType") or it.get("docType") or ""
        doc_year = data.get("docYear") or it.get("docYear") or ""
        doc_no = data.get("docNo") or it.get("docNo") or ""
        docno = ""
        if doc_type and doc_no:
            docno = f"{doc_type}〔{doc_year}〕{doc_no}号" if doc_year else f"{doc_type}{doc_no}号"
        agency = attrs.get("agency") or data.get("agency") or ""
        recs.append({
            "title": re.sub(r"\s+", " ", title).strip(),
            "publishDate": pub,
            "url": origin_url,
            "_shgov_detail": f"https://www.shanghai.gov.cn/zhengce/detail?businessId={bid}&siteId={sid}",
            "docNo": docno,
            "issuer": agency,
            "district": it.get("_district") or data.get("origin") or "",
            "category": classify_category(title, txt[:400]),
            "noticeType": classify_notice(title),
            "conditions": extract_conditions(txt),
            "benefits": extract_benefits(txt),
            "pdfUrls": pdf_urls(attrs),
            "_siteId": sid,
            "_businessId": bid,
            "_txtLen": len(txt),
            "_txt": txt[:6000],
        })

    # 去重
    seen, uniq = set(), []
    for r in recs:
        k = r["title"]
        if k in seen:
            continue
        seen.add(k)
        uniq.append(r)
    print(f"详情完成: {len(uniq)}")
    json.dump(uniq, open(os.path.join(RAW_DIR, "details_all.json"), "w"),
              ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
