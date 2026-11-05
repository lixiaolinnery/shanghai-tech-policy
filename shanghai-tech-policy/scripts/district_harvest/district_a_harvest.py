#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""上海 5 个区级科技类政策通知采集 —— 最终版。

每个区只使用已验证可访问的官网入口：
  浦东新区  POST https://www.pudong.gov.cn/zwgk-search-front/api/pudong/search
  徐汇区    POST https://ss.shanghai.gov.cn/manda-app/api/app/search/v1/qjoz2x/search
  闵行区    https://zwgk.shmh.gov.cn/mh-xxgk-cms/website/mh_xxgk/xxgk_kw_bmwj_bbmf/List/list_N.htm
  嘉定区    https://keji.jiading.cn/publicity/fdzdgknr/gg/zwgg_N  (+ jingwei 同名栏目)
  松江区    POST https://www.songjiang.gov.cn/shsj-application-front/rest/commonapiaction/getgovinfolist
  补充源    上海市政府统一政策发布平台检索 https://find.shanghai.gov.cn/search
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
        raise RuntimeError(f"empty rc={p.returncode} {p.stderr[:120]!r}")
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
    print("   ! fail:", last, file=sys.stderr)
    return None


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


def ts2date(v):
    if v in (None, "", 0):
        return ""
    s = str(v)
    if s.isdigit():
        n = int(s)
        if n > 10 ** 11:
            n //= 1000
        try:
            return datetime.datetime.fromtimestamp(n, datetime.timezone.utc).strftime("%Y-%m-%d")
        except Exception:
            return ""
    m = re.match(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", s)
    return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}" if m else ""


# ================================================================ 浦东
PD_QUERIES = ["高新技术企业", "高新技术企业 资助", "高新技术企业 奖励", "高新技术企业 补贴",
              "专精特新", "专精特新 立项", "专精特新 资助", "创新型中小企业",
              "科技型中小企业", "科技小巨人", "科技小巨人 配套资金", "科技创新券",
              "科技创新券 立项", "科技发展基金", "企业技术中心", "研发机构 认定",
              "科技 专项资金", "科技 扶持", "科技 补贴"]


def collect_pudong():
    seen, out = set(), []
    for kw in PD_QUERIES:
        for page in (1, 2):
            body = json.dumps({"keyword": kw, "pageNo": page, "pageSize": 50},
                              ensure_ascii=False)
            r = retry(lambda: json.loads(curl(
                ["-H", "Content-Type: application/json", "-X", "POST", "-d", body,
                 "https://www.pudong.gov.cn/zwgk-search-front/api/pudong/search"])))
            if not r or r.get("code") != 0:
                break
            lst = (r.get("data") or {}).get("list") or []
            if not lst:
                break
            for it in lst:
                u = (it.get("url") or "").strip()
                key = it.get("id") or u
                if not u or key in seen:
                    continue
                seen.add(key)
                dn = ""
                if it.get("docNumType") and it.get("docNumNo"):
                    dn = f"{it['docNumType']}〔{it.get('docNumYear','')}〕{it['docNumNo']}号"
                ag = it.get("dispatchAgency") or ""
                out.append({
                    "title": (it.get("title") or "").strip(),
                    "publishDate": ts2date(it.get("issueDate")) or ts2date(it.get("writtenDate"))
                                   or ts2date(it.get("displayDate")),
                    "url": u, "docNo": dn,
                    "issuer": ("上海市浦东新区" + ag) if ag else "",
                    "district": "浦东新区",
                    "pdfUrls": [it["pdfFileUrl"]] if it.get("pdfFileUrl") else [],
                    "_src": "pudong",
                })
            time.sleep(0.2)
    return out


# ================================================================ 嘉定
JD_SOURCES = [
    ("https://keji.jiading.cn/publicity/fdzdgknr/gg/zwgg", "上海市嘉定区科学技术委员会"),
    ("https://jingwei.jiading.cn/publicity/fdzdgknr/gg/zwgg", "上海市嘉定区经济委员会"),
]


def collect_jiading():
    seen, out = set(), []
    for base, issuer in JD_SOURCES:
        host = base.split("//", 1)[1].split("/", 1)[0]
        for page in range(1, 40):
            url = base if page == 1 else f"{base}_{page}"
            h = retry(lambda: curl([url]))
            if not h:
                break
            items = re.findall(
                r'<li>\s*<a href="([^"]+)"[^>]*title="标题：([^"]*?)\s*点击数',
                h, re.S)
            if not items:
                break
            # 日期
            dates = re.findall(r'<span class="dateRight">([\d\-]+)</span>', h)
            for i, (href, title) in enumerate(items):
                full = href if href.startswith("http") else f"https://{host}{href}"
                if full in seen:
                    continue
                seen.add(full)
                out.append({
                    "title": ihtml.unescape(title).strip(),
                    "publishDate": dates[i] if i < len(dates) else "",
                    "url": full, "docNo": "", "issuer": issuer,
                    "district": "嘉定区", "pdfUrls": [], "_src": "jiading",
                })
            time.sleep(0.2)
    return out


# ================================================================ 闵行
MH_CHANNELS = [
    ("xxgk_kw_bmwj_bbmf", "上海市闵行区科学技术委员会", 12),
    ("qzfwj_rsrm", "上海市闵行区人民政府", 8),
]


def collect_minhang():
    seen, out = set(), []
    base = "https://zwgk.shmh.gov.cn/mh-xxgk-cms/website/mh_xxgk"
    for chan, issuer, pages in MH_CHANNELS:
        for page in range(0, pages):
            url = f"{base}/{chan}/List/list_{page}.htm"
            h = retry(lambda: curl([url]))
            if not h:
                break
            items = re.findall(
                r'<li><span class=" ?f_float">([\d\-]+)</span><a[^>]+href="([^"]+)"[^>]*title="([^"]*)"',
                h)
            if not items:
                break
            new = 0
            for date, href, title in items:
                if f"/{chan}/" not in href:
                    continue           # 该页已回落到别的栏目，丢弃
                full = f"{base}/{href.replace('../../', '')}"
                if full in seen:
                    continue
                seen.add(full); new += 1
                out.append({
                    "title": ihtml.unescape(title).strip(), "publishDate": date,
                    "url": full, "docNo": "", "issuer": issuer,
                    "district": "闵行区", "pdfUrls": [], "_src": "minhang",
                })
            if new == 0:
                break
            time.sleep(0.2)
    return out


# ================================================================ 松江
SJ_DEPTS = [("002006", "上海市松江区科学技术委员会"),
            ("002002", "上海市松江区经济委员会")]


def collect_songjiang():
    seen, out = set(), []
    api = ("https://www.songjiang.gov.cn/shsj-application-front/rest/"
           "commonapiaction/getgovinfolist")
    for dept, issuer in SJ_DEPTS:
        for page in range(1, 15):
            p = json.dumps({"categorynum": "009", "deptcode": dept, "gktype": "1",
                            "pageNumber": str(page), "pageSize": "20"}, ensure_ascii=False)
            r = retry(lambda: json.loads(curl(
                ["--data-urlencode", "params=" + p, api])))
            if not r:
                break
            lst = (r.get("custom") or {}).get("data") or []
            if not lst:
                break
            for it in lst:
                vu = it.get("visiturl") or ""
                if not vu:
                    continue
                full = vu if vu.startswith("http") else "https://www.songjiang.gov.cn" + vu
                if full in seen:
                    continue
                seen.add(full)
                out.append({
                    "title": (it.get("title") or "").strip(),
                    "publishDate": ts2date(it.get("infodate")),
                    "url": full, "docNo": (it.get("documentnumber") or "").strip(),
                    "issuer": issuer, "district": "松江区",
                    "pdfUrls": [], "_src": "songjiang",
                })
            time.sleep(0.2)
    return out


# ================================================================ 徐汇
XH_QUERIES = ["高新技术企业", "高新技术企业 认定", "高新技术企业 奖励", "高新技术企业 补贴",
              "专精特新", "专精特新 认定", "专精特新 奖励", "创新型中小企业",
              "创新型中小企业 申报", "科技型中小企业", "科技小巨人", "科技小巨人 申报",
              "科技创新券", "科技 专项资金", "企业技术中心 申报", "科技 扶持 申报",
              "科技政策 申报", "科技 项目 立项", "科技 补贴", "科技 奖励"]


def collect_xuhui():
    seen, out = set(), []
    for q in XH_QUERIES:
        for page in (1, 2, 3):
            body = json.dumps({"cid": "rucilw", "query": q, "current": page, "size": 20},
                              ensure_ascii=False)
            r = retry(lambda: json.loads(curl(
                ["-H", "Content-Type: text/plain", "-X", "POST", "-d", body,
                 "https://ss.shanghai.gov.cn/manda-app/api/app/search/v1/qjoz2x/search"])))
            if not r or not r.get("success"):
                break
            items = ((r.get("result") or {}).get("items")) or []
            if not items:
                break
            for it in items:
                u = ((it.get("url") or {}).get("raw") or "").strip()
                t = ((it.get("title") or {}).get("raw") or "").strip()
                view = ((it.get("view") or {}).get("raw") or "").strip()
                if not u.startswith("https://www.xuhui.gov.cn/"):
                    continue
                if view in ("wsbs",):
                    continue
                if u in seen:
                    continue
                seen.add(u)
                out.append({
                    "title": t, "publishDate": ts2date((it.get("date") or {}).get("raw")),
                    "url": u, "docNo": "", "issuer": "", "district": "徐汇区",
                    "pdfUrls": [], "_src": "xuhui", "_view": view,
                })
            time.sleep(0.2)
    return out


# ================================================================ 市平台补充
CITY_QUERIES = ["高新技术企业", "高新技术企业认定 申报", "高新技术企业 奖励 公示",
                "专精特新 申报", "专精特新 名单 公示", "创新型中小企业 申报",
                "科技型中小企业 评价", "科技小巨人 立项", "科技创新券",
                "科技发展基金", "企业技术中心 申报", "科技 专项资金 申报"]


def collect_city():
    seen, out = set(), []
    for dname, sid in DISTRICTS.items():
        for q in CITY_QUERIES:
            for page in (1, 2):
                body = json.dumps({"q": q, "page": page, "size": 20, "siteId": [sid]},
                                  ensure_ascii=False)
                r = retry(lambda: json.loads(curl(
                    ["-H", "Content-Type: text/plain", "-X", "POST", "-d", body,
                     "https://find.shanghai.gov.cn/search"])))
                if not r or r.get("code") != 0:
                    break
                data = r.get("data") or {}
                lst = data.get("resultList") or []
                if not lst:
                    break
                for it in lst:
                    bid = it.get("businessId")
                    if not bid or (sid, bid) in seen:
                        continue
                    seen.add((sid, bid))
                    attrs = it.get("attrs") or {}
                    out.append({
                        "title": (it.get("title") or "").strip(),
                        "publishDate": ts2date(it.get("publishDate") or it.get("displayDate")),
                        "url": "", "docNo": "", "issuer": attrs.get("agency") or "",
                        "district": dname, "pdfUrls": [], "_src": "city",
                        "_siteId": sid, "_businessId": bid,
                        "_docType": it.get("docType") or "",
                        "_docYear": it.get("docYear") or "",
                        "_docNo": it.get("docNo") or "",
                        "_pdfPath": attrs.get("zwPDFUrl") or "",
                    })
                time.sleep(0.2)
    return out


def enrich_city(recs):
    def work(r):
        body = json.dumps({"siteId": r["_siteId"], "businessId": r["_businessId"]})
        d = retry(lambda: json.loads(curl(
            ["-H", "Content-Type: application/json", "-X", "POST", "-d", body,
             "https://www.shanghai.gov.cn/gwk/policy/detail"])), n=2)
        data = (d or {}).get("data") or {}
        url = data.get("originUrl") or ""
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

    with ThreadPoolExecutor(max_workers=8) as ex:
        list(ex.map(work, recs))
    return recs


# ================================================================ 正文抓取
def fetch_text(url):
    h = retry(lambda: curl([url], timeout=35), n=2)
    if not h:
        return ""
    # 尽量只取正文区域
    for pat in (r'<div[^>]+class="[^"]*(?:content|article|detail|TRS_Editor|view|zoom)[^"]*"[^>]*>(.*?)</div>\s*</div>',
                r'<div[^>]+id="(?:content|zoom|ivs_content|mainText)"[^>]*>(.*?)</div>'):
        m = re.search(pat, h, re.S | re.I)
        if m and len(m.group(1)) > 400:
            return strip_html(m.group(1))
    return strip_html(h)


def main():
    stage = sys.argv[1] if len(sys.argv) > 1 else "collect"

    if stage == "collect":
        res = {}
        print("== 浦东 ==");   res["pudong"] = collect_pudong();     print("  ", len(res["pudong"]))
        print("== 嘉定 ==");   res["jiading"] = collect_jiading();   print("  ", len(res["jiading"]))
        print("== 闵行 ==");   res["minhang"] = collect_minhang();   print("  ", len(res["minhang"]))
        print("== 松江 ==");   res["songjiang"] = collect_songjiang(); print("  ", len(res["songjiang"]))
        print("== 徐汇 ==");   res["xuhui"] = collect_xuhui();       print("  ", len(res["xuhui"]))
        print("== 市平台 =="); res["city"] = collect_city();         print("  ", len(res["city"]))
        print("== 市平台详情 ==")
        res["city"] = enrich_city(res["city"])
        json.dump(res, open(os.path.join(RAW, "final_cands.json"), "w"),
                  ensure_ascii=False, indent=1)
        print("saved final_cands.json")

    elif stage == "text":
        res = json.load(open(os.path.join(RAW, "final_cands.json")))
        flat = []
        for k, v in res.items():
            for r in v:
                r["_srcgrp"] = k
                flat.append(r)
        print("待抓正文:", len(flat))
        todo = []
        for r in flat:
            if r.get("_txt"):
                continue
            todo.append(r)

        def work(r):
            r["_txt"] = fetch_text(r["url"])
            return r

        done = 0
        with ThreadPoolExecutor(max_workers=8) as ex:
            futs = [ex.submit(work, r) for r in todo]
            for f in as_completed(futs):
                done += 1
                if done % 25 == 0:
                    print(f"   {done}/{len(todo)}")
        json.dump(flat, open(os.path.join(RAW, "final_flat.json"), "w"),
                  ensure_ascii=False, indent=1)
        print("saved final_flat.json")


if __name__ == "__main__":
    main()
