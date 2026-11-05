#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""district_e: 黄浦区 / 虹口区 / 金山区 / 青浦区 / 崇明区  区级科技政策采集。

数据源：上海市政府官网统一政策检索
  POST https://find.shanghai.gov.cn/search        (siteId 过滤到 5 个区)
  POST https://www.shanghai.gov.cn/gwk/policy/detail  -> originUrl / txt / docNo
"""
import json, os, re, subprocess, sys, time, html as ihtml
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw_district")
OUT = os.path.join(ROOT, "data", "district", "district_e.json")
os.makedirs(RAW, exist_ok=True)

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")

DISTRICTS = {"黄浦区": "0071", "虹口区": "0076", "金山区": "0081",
             "青浦区": "0083", "崇明区": "0085"}

# (query, 标题必须命中的关键词) —— 保证召回精度
QUERIES = [
    ("企业技术中心", ["企业技术中心", "技术中心"]),
    ("企业技术中心 认定", ["企业技术中心", "技术中心"]),
    ("企业技术中心 奖励", ["企业技术中心", "技术中心"]),
    ("专利试点", ["专利"]),
    ("高价值专利", ["专利"]),
    ("专利工作试点示范", ["专利"]),
    ("知识产权试点示范", ["知识产权"]),
    ("知识产权 示范单位", ["知识产权"]),
    ("知识产权 扶持", ["知识产权"]),
    ("关键核心技术攻关", ["攻关"]),
    ("产业攻关 项目", ["攻关"]),
    ("技术攻关 揭榜", ["攻关", "揭榜"]),
    ("揭榜挂帅", ["揭榜", "发榜"]),
    ("发榜 需求", ["揭榜", "发榜"]),
    ("制造业单项冠军", ["单项冠军", "冠军"]),
    ("单项冠军 培育 认定", ["单项冠军", "冠军"]),
    ("高新技术企业 奖励", ["高新技术企业", "高企"]),
    ("高新技术企业 补贴 资助", ["高新技术企业", "高企"]),
    ("专精特新", ["专精特新"]),
    ("创新型中小企业", ["创新型中小企业"]),
    ("科技型中小企业", ["科技型中小企业"]),
    ("科技小巨人", ["科技小巨人", "小巨人"]),
    ("科技创新券", ["科技创新券"]),
    ("科技发展基金 专项资金", ["科技", "专项", "扶持", "奖励", "资助", "基金"]),
    ("科技创新 若干政策", ["科技", "创新", "研发", "产业"]),
    ("技术改造 智能工厂", ["技术改造", "智能工厂", "首台套", "技术改造专项"]),
    ("科技企业孵化器 众创空间", ["孵化器", "众创空间"]),
    ("科技 奖励 兑现 拨付", ["科技", "奖励", "兑现", "拨付", "资助"]),
    ("研发机构 认定", ["研发机构", "技术中心", "工程技术"]),
]

CAT_TITLE_RULES = [
    ("企业技术中心", ["企业技术中心", "区级技术中心"]),
    ("制造业单项冠军", ["单项冠军"]),
    ("揭榜挂帅", ["揭榜挂帅", "揭榜", "发榜"]),
    ("重大产业攻关", ["攻关"]),
    ("专利试点示范", ["专利试点", "专利工作试点", "专利示范", "知识产权试点",
                      "知识产权示范", "专利培育", "高价值专利", "专利"]),
    ("高新技术企业", ["高新技术企业", "高企"]),
    ("专精特新中小企业", ["专精特新"]),
    ("创新型中小企业", ["创新型中小企业"]),
    ("科技型中小企业", ["科技型中小企业"]),
    ("科技小巨人", ["科技小巨人", "小巨人"]),
    ("科技创新券", ["科技创新券"]),
]

NOTICE_RULES = [
    ("政策红头文件", ["管理办法", "实施细则", "若干措施", "实施办法", "暂行办法",
                      "实施意见", "操作办法", "工作指引", "认定办法", "奖励办法",
                      "资助办法", "扶持办法", "若干政策", "政策措施", "工作方案",
                      "行动方案", "专项规划", "发展规划", "实施方案", "办法"]),
    ("公示通知", ["公示", "拟认定", "拟支持", "拟奖励", "拟立项", "拟入库", "拟通过", "拟补助"]),
    ("名单公布", ["名单", "公布", "结果", "公告"]),
    ("立项与评价通知", ["立项", "验收", "评价", "评估", "绩效"]),
    ("领补贴通知", ["拨付", "兑现", "发放", "下达", "领取", "资金安排", "奖励资金", "资助资金"]),
    ("申报通知", ["申报", "征集", "开展", "推荐", "认定", "复核", "备案", "申请", "组织"]),
]


def curl(args, timeout=45):
    cmd = ["curl", "-sS", "-L", "-k", "--compressed", "-m", str(timeout),
           "-H", f"User-Agent: {UA}", "-H", "Accept-Language: zh-CN,zh;q=0.9"] + args
    p = subprocess.run(cmd, capture_output=True, timeout=timeout + 25)
    raw = p.stdout
    if not raw:
        raise RuntimeError(f"empty rc={p.returncode} {p.stderr[:120]!r}")
    for enc in ("utf-8", "gb18030"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


def search(q, site_ids, page=1, size=50, retries=3):
    body = json.dumps({"q": q, "page": page, "size": size, "siteId": site_ids},
                      ensure_ascii=False)
    for i in range(retries):
        try:
            return json.loads(curl(["-H", "Content-Type: text/plain", "-X", "POST",
                                    "-d", body, "https://find.shanghai.gov.cn/search"]))
        except Exception as e:
            if i == retries - 1:
                print(f"  ! search {q} p{page}: {e}", file=sys.stderr)
                return None
            time.sleep(1.0 * (i + 1))


def detail(site_id, business_id, retries=3):
    body = json.dumps({"siteId": site_id, "businessId": business_id})
    for i in range(retries):
        try:
            d = json.loads(curl(["-H", "Content-Type: application/json", "-X", "POST",
                                 "-d", body,
                                 "https://www.shanghai.gov.cn/gwk/policy/detail"]))
            return (d.get("data") or {})
        except Exception as e:
            if i == retries - 1:
                print(f"  ! detail {business_id}: {e}", file=sys.stderr)
                return {}
            time.sleep(1.0 * (i + 1))


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


def classify_cat(title, txt):
    for cat, kws in CAT_TITLE_RULES:
        if any(k in title for k in kws):
            return cat
    for cat, kws in CAT_TITLE_RULES:
        if any(k in (txt or "")[:1500] for k in kws):
            return cat
    if any(k in title for k in ["专项资金", "奖励", "补贴", "资助", "资金", "兑现",
                                "拨付", "扶持", "基金"]):
        return "专项资金与补贴"
    return "其他科技政策"


def classify_notice(title):
    for nt, kws in NOTICE_RULES:
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


def pdf_urls(detail_data):
    urls = []
    for k in ("zwPDFUrl",):
        v = (detail_data or {}).get(k)
        if v and v.startswith("/"):
            urls.append("https://www.shanghai.gov.cn/gwk/resource/file?pathname="
                        + v.split("pathname=", 1)[-1])
    attrs = (detail_data or {}).get("attrs") or {}
    for k in ("zwPDFUrl",):
        v = attrs.get(k)
        if v and isinstance(v, str) and v.startswith("/"):
            urls.append("https://www.shanghai.gov.cn/gwk/resource/file?pathname="
                        + v.split("pathname=", 1)[-1])
    return list(dict.fromkeys(urls))


def valid_docno(r):
    dt = (r.get("docType") or "").strip()
    dy = (r.get("docYear") or "").strip()
    dn = (r.get("docNo") or "").strip()
    if not dt or dt.lower() == "null" or not dn or dn.lower() == "null":
        return ""
    if not re.match(r"^[0-9]+$", dn):
        # 有些 docNo 直接写成完整文号
        if "〔" in dn or "[" in dn:
            return dn
        return ""
    return f"{dt}〔{dy or ''}〕{dn}号"


def norm_date(v):
    if not v:
        return ""
    m = re.match(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", str(v))
    return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}" if m else ""


def main():
    site_ids = list(DISTRICTS.values())
    id2name = {v: k for k, v in DISTRICTS.items()}

    # ---------- 1. 检索 ----------
    hits = {}
    for q, musts in QUERIES:
        for page in (1, 2):
            d = search(q, site_ids, page=page)
            if not d or d.get("code") != 0:
                break
            rl = (d.get("data") or {}).get("resultList") or []
            if not rl:
                break
            added = 0
            for r in rl:
                t = r.get("title") or ""
                if not any(k in t for k in musts):
                    continue
                key = (r.get("siteId"), r.get("businessId"))
                if key in hits:
                    continue
                hits[key] = r
                added += 1
            print(f"  {q} p{page}: +{added} (total {len(hits)})")
            if len(rl) < 50:
                break
            time.sleep(0.4)
        time.sleep(0.3)

    print(f"== 检索命中 {len(hits)} 条，开始取详情 ==")

    # ---------- 2. 详情 ----------
    keys = list(hits.keys())
    details = {}
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = {ex.submit(detail, k[0], k[1]): k for k in keys}
        for i, f in enumerate(as_completed(futs), 1):
            k = futs[f]
            try:
                details[k] = f.result()
            except Exception:
                details[k] = {}
            if i % 30 == 0:
                print(f"  detail {i}/{len(keys)}")

    # ---------- 3. 组记录 ----------
    recs = []
    for k in keys:
        r = hits[k]
        dt = details.get(k) or {}
        url = (dt.get("originUrl") or "").strip()
        if not url.startswith("http"):
            continue
        title = (dt.get("title") or r.get("title") or "").strip()
        txt = strip_html(dt.get("txt") or "")
        attrs = dt.get("attrs") or {}
        rec = {
            "title": title,
            "publishDate": norm_date(dt.get("publishDate") or r.get("publishDate")
                                     or r.get("displayDate")),
            "url": url,
            "docNo": valid_docno(r),
            "issuer": (attrs.get("agency") or "").strip(),
            "district": id2name.get(k[0], ""),
            "category": classify_cat(title, txt),
            "noticeType": classify_notice(title),
            "conditions": extract(COND_RE, txt, n=4, minlen=10),
            "benefits": extract(MONEY_RE, txt, n=4, minlen=8),
            "pdfUrls": pdf_urls(dt),
            "_siteId": k[0],
            "_businessId": k[1],
        }
        if not rec["district"]:
            continue
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", rec["publishDate"]):
            rec["publishDate"] = ""
        recs.append(rec)

    # 去掉明显与科技/产业政策无关的规划类噪音（保留含关键词的）
    print(f"== 组出 {len(recs)} 条，开始验证 URL ==")

    # ---------- 4. HTTP 验证 ----------
    def check(rec):
        rec["_http"] = http_status(rec["url"])
        return rec

    with ThreadPoolExecutor(max_workers=8) as ex:
        recs = list(ex.map(check, recs))

    ok = [r for r in recs if r["_http"] == "200"]
    bad = [r for r in recs if r["_http"] != "200"]
    print(f"== 200: {len(ok)}  非200: {len(bad)} ==")
    from collections import Counter
    print("非200 分布:", Counter((r["district"], r["_http"]) for r in bad))

    json.dump(recs, open(os.path.join(RAW, "district_e_all.json"), "w"),
              ensure_ascii=False, indent=1)
    json.dump(ok, open(OUT, "w"), ensure_ascii=False, indent=1)
    print("written:", OUT, len(ok))


if __name__ == "__main__":
    main()
