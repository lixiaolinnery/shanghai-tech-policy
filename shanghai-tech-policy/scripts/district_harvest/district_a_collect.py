#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""上海 5 区级科技类政策通知采集（district_a）。

每个区使用其官网可访问的真实入口：
  浦东新区  POST https://www.pudong.gov.cn/zwgk-search-front/api/pudong/search
  嘉定区    https://keji.jiading.cn/publicity/fdzdgknr/gg/zwgg_N  (+ jingwei)
  闵行区    https://zwgk.shmh.gov.cn/mh-xxgk-cms/website/mh_xxgk/xxgk_kw_bmwj_bbmf/List/list_N.htm
  徐汇区 / 松江区  市政府统一平台检索 https://find.shanghai.gov.cn/search (siteId 过滤)
  全部区  同上市检索接口作补充
"""
import json, os, re, subprocess, sys, time, html as ihtml, datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw_district")
OUT_DIR = os.path.join(ROOT, "data", "district")
os.makedirs(RAW, exist_ok=True)
os.makedirs(OUT_DIR, exist_ok=True)

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")

DISTRICTS = {"浦东新区": "0070", "徐汇区": "0073", "闵行区": "0079",
             "嘉定区": "0080", "松江区": "0082"}


def curl(args, timeout=45):
    cmd = ["curl", "-sS", "-L", "-k", "--compressed", "-m", str(timeout),
           "-H", f"User-Agent: {UA}", "-H", "Accept-Language: zh-CN,zh;q=0.9"] + args
    p = subprocess.run(cmd, capture_output=True, timeout=timeout + 20)
    raw = p.stdout
    if not raw:
        raise RuntimeError(f"empty body rc={p.returncode} err={p.stderr[:160]!r}")
    for enc in ("utf-8", "gb18030"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


def retry(fn, n=3, delay=1.0):
    last = None
    for i in range(n):
        try:
            return fn()
        except Exception as e:  # noqa
            last = e
            time.sleep(delay * (i + 1))
    print("  ! fail:", last, file=sys.stderr)
    return None


# ---------------------------------------------------------------- 检索接口
def city_search(q, site_id, page=1, size=20):
    body = json.dumps({"q": q, "page": page, "size": size, "siteId": [site_id]},
                      ensure_ascii=False)
    txt = curl(["-H", "Content-Type: text/plain", "-X", "POST", "-d", body,
                "https://find.shanghai.gov.cn/search"])
    return json.loads(txt)


def city_detail(site_id, business_id):
    body = json.dumps({"siteId": site_id, "businessId": business_id})
    txt = curl(["-H", "Content-Type: application/json", "-X", "POST", "-d", body,
                "https://www.shanghai.gov.cn/gwk/policy/detail"])
    return json.loads(txt)


def pd_search(kw, page=1, size=50):
    body = json.dumps({"keyword": kw, "pageNo": page, "pageSize": size},
                      ensure_ascii=False)
    txt = curl(["-H", "Content-Type: application/json", "-X", "POST", "-d", body,
                "https://www.pudong.gov.cn/zwgk-search-front/api/pudong/search"])
    return json.loads(txt)


# ---------------------------------------------------------------- 关键词
TARGET_KW = ["高新技术企业", "高企", "专精特新", "创新型中小企业", "科技型中小企业",
             "科技小巨人", "科技创新券", "科技发展基金", "企业技术中心",
             "科技企业孵化器", "科技小巨人工程"]

CITY_QUERIES = ["高新技术企业", "高新技术企业认定 申报", "高新技术企业 奖励 公示",
                "专精特新", "专精特新 申报", "专精特新 名单 公示",
                "创新型中小企业", "创新型中小企业 申报", "科技型中小企业",
                "科技型中小企业 入库", "科技小巨人", "科技小巨人 立项",
                "科技创新券", "科技发展基金", "企业技术中心 申报",
                "高新技术企业 补贴", "高新技术企业 资助"]

PD_QUERIES = ["高新技术企业", "专精特新", "创新型中小企业", "科技型中小企业",
              "科技小巨人", "科技创新券", "科技发展基金", "企业技术中心",
              "高新技术企业 资助", "专精特新 立项", "科技小巨人 配套资金",
              "科技创新券 立项", "研发机构 认定", "科技企业 扶持"]


def ts2date(v):
    if v in (None, "", 0):
        return ""
    if isinstance(v, (int, float)) or (isinstance(v, str) and v.isdigit()):
        try:
            n = int(v)
            if n > 10 ** 11:
                n //= 1000
            return datetime.datetime.utcfromtimestamp(n).strftime("%Y-%m-%d")
        except Exception:
            return ""
    s = str(v)
    m = re.match(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", s)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    return ""


# ================================================================ 采集
def collect_pudong():
    """浦东新区：官方政务公开检索接口。"""
    seen, out = set(), []
    for kw in PD_QUERIES:
        for page in (1, 2):
            r = retry(lambda: pd_search(kw, page))
            if not r or r.get("code") != 0:
                continue
            data = r.get("data") or {}
            lst = data.get("list") or []
            if not lst:
                break
            for it in lst:
                u = it.get("url") or ""
                key = it.get("id") or u or it.get("title")
                if key in seen or not u:
                    continue
                seen.add(key)
                dn = ""
                if it.get("docNumType") and it.get("docNumNo"):
                    dn = f"{it['docNumType']}〔{it.get('docNumYear','')}〕{it['docNumNo']}号"
                out.append({
                    "title": (it.get("title") or "").strip(),
                    "publishDate": (ts2date(it.get("issueDate")) or ts2date(it.get("writtenDate"))
                                    or ts2date(it.get("displayDate"))),
                    "url": u,
                    "docNo": dn,
                    "issuer": f"上海市浦东新区{it.get('dispatchAgency','')}" if it.get("dispatchAgency") else "",
                    "district": "浦东新区",
                    "pdfUrls": [it["pdfFileUrl"]] if it.get("pdfFileUrl") else [],
                    "_src": "pudong-api",
                    "_kw": kw,
                })
            time.sleep(0.2)
    return out


def parse_jd_list(html_text, base):
    items = []
    for m in re.finditer(
            r'<li>\s*<a href="([^"]+)"[^>]*title="标题：([^"]*?)\s*\n?点击数',
            html_text, re.S):
        href, title = m.group(1), m.group(2)
        items.append((ihtml.unescape(title).strip(), href))
    return items


def collect_jiading():
    """嘉定区：科委(keji) + 经委(jingwei) 通知公告列表。"""
    sources = [
        ("https://keji.jiading.cn/publicity/fdzdgknr/gg/zwgg", "上海市嘉定区科学技术委员会"),
        ("https://jingwei.jiading.cn/publicity/fdzdgknr/gg/zwgg", "上海市嘉定区经济委员会"),
    ]
    seen, out = set(), []
    for base, issuer in sources:
        for page in range(1, 16):
            url = base if page == 1 else f"{base}_{page}"
            h = retry(lambda: curl([url]))
            if not h:
                break
            items = parse_jd_list(h, base)
            if not items:
                break
            new = 0
            for title, href in items:
                full = href if href.startswith("http") else "https://" + url.split("//", 1)[1].split("/", 1)[0] + href
                if full in seen:
                    continue
                seen.add(full)
                new += 1
                out.append({
                    "title": title, "publishDate": "", "url": full, "docNo": "",
                    "issuer": issuer, "district": "嘉定区", "pdfUrls": [],
                    "_src": "jiading-list",
                })
            # 只有标题里含目标关键词的才继续翻页？否，翻满 15 页
            if new == 0 and page > 1:
                pass
            time.sleep(0.2)
    return out


def collect_minhang():
    """闵行区：政务公开 CMS 科委本部门发文。"""
    base = ("https://zwgk.shmh.gov.cn/mh-xxgk-cms/website/mh_xxgk/"
            "xxgk_kw_bmwj_bbmf")
    seen, out = set(), []
    for page in range(0, 12):
        url = f"{base}/List/list_{page}.htm"
        h = retry(lambda: curl([url]))
        if not h:
            break
        items = re.findall(
            r'<li><span class=" ?f_float">([\d\-]+)</span><a[^>]+href="([^"]+)"[^>]*title="([^"]*)"',
            h)
        if not items:
            break
        for date, href, title in items:
            full = "https://zwgk.shmh.gov.cn/mh-xxgk-cms/website/mh_xxgk/" + \
                   href.replace("../../", "")
            if full in seen:
                continue
            seen.add(full)
            out.append({
                "title": ihtml.unescape(title).strip(), "publishDate": date,
                "url": full, "docNo": "",
                "issuer": "上海市闵行区科学技术委员会", "district": "闵行区",
                "pdfUrls": [], "_src": "minhang-cms",
            })
        time.sleep(0.2)
    return out


def collect_city():
    """市政府统一政策发布平台检索：覆盖 5 区的通知公告与政策文件。"""
    seen, out = set(), []
    for dname, sid in DISTRICTS.items():
        for q in CITY_QUERIES:
            r = retry(lambda: city_search(q, sid, 1, 20))
            if not r or r.get("code") != 0:
                continue
            data = r.get("data") or {}
            for it in (data.get("resultList") or []):
                bid = it.get("businessId")
                key = (sid, bid)
                if not bid or key in seen:
                    continue
                seen.add(key)
                attrs = it.get("attrs") or {}
                out.append({
                    "title": (it.get("title") or "").strip(),
                    "publishDate": (it.get("publishDate") or it.get("displayDate") or "")[:10],
                    "url": "",
                    "docNo": "",
                    "issuer": attrs.get("agency") or "",
                    "district": dname,
                    "pdfUrls": [],
                    "_src": "city-search",
                    "_siteId": sid,
                    "_businessId": bid,
                    "_docType": it.get("docType") or "",
                    "_docYear": it.get("docYear") or "",
                    "_docNo": it.get("docNo") or "",
                    "_pdfPath": attrs.get("zwPDFUrl") or "",
                })
            time.sleep(0.2)
    return out


def enrich_city(recs):
    """给 city-search 记录补 originUrl / PDF / 正文。"""
    def work(r):
        d = retry(lambda: city_detail(r["_siteId"], r["_businessId"]), n=2)
        data = (d or {}).get("data") or {}
        url = data.get("originUrl") or ""
        # 徐汇源站 CMS 内网地址修正
        url = re.sub(r"^https?://10\.10\.10\.94:8014/", "https://www.xuhui.gov.cn/", url)
        if url.startswith("https127.0.0.1/"):
            url = "https://www.xuhui.gov.cn/" + url.split("/", 1)[1]
        r["url"] = url
        if r["_docType"] and r["_docNo"]:
            r["docNo"] = f"{r['_docType']}〔{r['_docYear']}〕{r['_docNo']}号"
        if not r["issuer"]:
            r["issuer"] = data.get("draftingUnit") or ""
        r["_txt"] = strip_html(data.get("txt") or data.get("content") or "")
        p = r.get("_pdfPath") or ""
        if p.startswith("/"):
            r["pdfUrls"] = ["https://www.shanghai.gov.cn/gwk/resource/file?pathname="
                            + p.split("pathname=", 1)[-1]]
        return r

    with ThreadPoolExecutor(max_workers=6) as ex:
        list(ex.map(work, recs))
    return recs


def strip_html(s):
    if not s:
        return ""
    s = re.sub(r"<script.*?</script>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<style.*?</style>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = ihtml.unescape(s)
    s = re.sub(r"[\u3000\xa0]", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def main():
    stage = sys.argv[1] if len(sys.argv) > 1 else "all"
    if stage in ("all", "collect"):
        print("== 浦东 ==");   pd = collect_pudong();   print("  ", len(pd))
        print("== 嘉定 ==");   jd = collect_jiading();  print("  ", len(jd))
        print("== 闵行 ==");   mh = collect_minhang();  print("  ", len(mh))
        print("== 市平台 =="); ct = collect_city();     print("  ", len(ct))
        json.dump({"pudong": pd, "jiading": jd, "minhang": mh, "city": ct},
                  open(os.path.join(RAW, "cands_a.json"), "w"), ensure_ascii=False, indent=1)
    if stage in ("all", "enrich"):
        d = json.load(open(os.path.join(RAW, "cands_a.json")))
        print("== 补全市平台详情 ==")
        d["city"] = enrich_city(d["city"])
        json.dump(d, open(os.path.join(RAW, "cands_a_enriched.json"), "w"),
                  ensure_ascii=False, indent=1)
        print("done")


if __name__ == "__main__":
    main()
