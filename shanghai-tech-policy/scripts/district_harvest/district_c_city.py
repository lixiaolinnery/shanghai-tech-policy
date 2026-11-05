#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""市统一检索：6 区 × 5 类关键词 -> detail 取 originUrl/docNo/正文。"""
import json, os, re, subprocess, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw_district_c")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")

SITES = {"浦东新区": "0070", "徐汇区": "0073", "宝山区": "0078",
         "闵行区": "0079", "嘉定区": "0080", "松江区": "0082"}

KWS = ["企业技术中心", "技术中心 认定", "技术中心 申报", "专利试点", "专利示范",
       "专利工作试点单位", "知识产权试点", "知识产权示范", "知识产权示范单位",
       "攻关", "科技攻关", "关键核心技术", "产业攻关", "揭榜挂帅", "揭榜", "发榜",
       "技术需求", "单项冠军", "制造业单项冠军", "先进制造业", "制造业冠军",
       "创新联合体", "联合攻关"]

TARGET = re.compile(
    r"企业技术中心|技术中心|专利.{0,6}(试点|示范)|知识产权.{0,8}(试点|示范|优势)|"
    r"试点示范|攻关|揭榜|挂帅|发榜|单项冠军|制造业冠军|冠军企业|"
    r"先进制造业.{0,8}冠军|创新联合体")


def curl(args, timeout=40):
    cmd = ["curl", "-sS", "-L", "-k", "--compressed", "-m", str(timeout),
           "-H", f"User-Agent: {UA}", "-H", "Accept-Language: zh-CN,zh;q=0.9"] + args
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


def city_search(q, sid, page=1, size=50):
    body = json.dumps({"q": q, "page": page, "size": size, "siteId": [sid]},
                      ensure_ascii=False)
    return json.loads(curl(["-H", "Content-Type: text/plain", "-X", "POST",
                            "-d", body, "https://find.shanghai.gov.cn/search"]))


def city_detail(sid, bid):
    body = json.dumps({"siteId": sid, "businessId": bid})
    return json.loads(curl(["-H", "Content-Type: application/json", "-X", "POST",
                            "-d", body,
                            "https://www.shanghai.gov.cn/gwk/policy/detail"]))


def strip_html(s):
    import html as ihtml
    s = re.sub(r"<script.*?</script>", " ", s or "", flags=re.S | re.I)
    s = re.sub(r"<style.*?</style>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = ihtml.unescape(s)
    s = re.sub(r"[\u3000\xa0]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def main():
    cand = {}
    for d, sid in SITES.items():
        for kw in KWS:
            try:
                r = city_search(kw, sid, 1, 50)
            except Exception as e:  # noqa
                print("!", d, kw, e, file=sys.stderr)
                continue
            for it in ((r.get("data") or {}).get("resultList") or []):
                t = (it.get("title") or "").strip()
                if not TARGET.search(t):
                    continue
                bid = it.get("businessId")
                if not bid:
                    continue
                attrs = it.get("attrs") or {}
                cand[bid] = {"district": d, "siteId": sid, "title": t,
                             "businessId": bid,
                             "publishDate": (it.get("publishDate") or "")[:10],
                             "issuer": attrs.get("agency") or "",
                             "docType": it.get("docType") or "",
                             "docYear": it.get("docYear") or "",
                             "docNoRaw": it.get("docNo") or "",
                             "pdfPath": attrs.get("zwPDFUrl") or "",
                             "_kw": kw}
            time.sleep(0.3)
        print(d, len(cand), file=sys.stderr)
    rows = []
    for i, c in enumerate(cand.values()):
        try:
            dd = city_detail(c["siteId"], c["businessId"])
        except Exception as e:  # noqa
            print("! detail", c["title"][:30], e, file=sys.stderr)
            continue
        data = (dd or {}).get("data") or {}
        url = data.get("originUrl") or ""
        url = re.sub(r"^https?://10\.10\.10\.94:8014/", "https://www.xuhui.gov.cn/", url)
        if url.startswith("https127.0.0.1/"):
            url = "https://www.xuhui.gov.cn/" + url.split("/", 1)[1]
        dn = ""
        if c["docType"] and c["docNoRaw"]:
            dn = f"{c['docType']}〔{c['docYear']}〕{c['docNoRaw']}号"
        elif data.get("docType") and data.get("docNo"):
            dn = f"{data['docType']}〔{data.get('docYear','')}〕{data['docNo']}号"
        pdfs = []
        if c["pdfPath"]:
            pdfs = ["https://www.shanghai.gov.cn/gwk/resource/file?pathname="
                    + c["pdfPath"].split("pathname=", 1)[-1]]
        rows.append({"district": c["district"], "title": c["title"],
                     "publishDate": (data.get("publishDate") or c["publishDate"] or "")[:10],
                     "url": url, "docNo": dn,
                     "issuer": c["issuer"] or data.get("draftingUnit") or "",
                     "pdfUrls": pdfs, "text": strip_html(data.get("txt") or "")[:8000],
                     "_kw": c["_kw"], "_src": "city-search"})
        print(f"[{i+1}/{len(cand)}] {c['district']} {c['title'][:40]}", file=sys.stderr)
        time.sleep(0.2)
    json.dump(rows, open(os.path.join(RAW, "city_detail.json"), "w",
                         encoding="utf-8"), ensure_ascii=False, indent=1)
    print("city_detail", len(rows))


if __name__ == "__main__":
    main()
