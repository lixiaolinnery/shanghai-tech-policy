#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""浦东 / 徐汇 官网检索接口关键词清扫。"""
import json, os, re, subprocess, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw_district_c")
os.makedirs(RAW, exist_ok=True)

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")

KWS = [
    "企业技术中心", "技术中心 认定", "技术中心 申报", "区级企业技术中心",
    "专利试点", "专利示范", "专利工作试点单位", "专利工作示范单位",
    "知识产权试点", "知识产权示范", "知识产权示范单位", "知识产权 认定",
    "知识产权 资助", "知识产权 奖励", "攻关", "科技攻关", "关键核心技术",
    "产业攻关", "揭榜挂帅", "揭榜", "发榜", "技术需求",
    "单项冠军", "制造业单项冠军", "先进制造业", "制造业冠军", "冠军企业",
    "创新联合体", "技术中心 评价", "技术中心 公示", "技术中心 奖励",
]

TARGET = re.compile(
    r"企业技术中心|技术中心|专利.{0,4}(试点|示范)|知识产权.{0,6}(试点|示范|优势)|"
    r"试点示范单位|攻关|揭榜|挂帅|发榜|单项冠军|制造业冠军|先进制造业.{0,6}冠军|"
    r"冠军企业|创新联合体")


def curl(args, timeout=45):
    cmd = ["curl", "-sS", "-L", "-k", "--compressed", "-m", str(timeout),
           "-H", f"User-Agent: {UA}", "-H", "Accept-Language: zh-CN,zh;q=0.9"] + args
    p = subprocess.run(cmd, capture_output=True, timeout=timeout + 20)
    raw = p.stdout
    if not raw:
        raise RuntimeError(f"empty rc={p.returncode}")
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


def ts2date(v):
    if v in (None, "", 0):
        return ""
    if isinstance(v, (int, float)) or (isinstance(v, str) and v.isdigit()):
        try:
            n = int(v)
            if n > 10 ** 11:
                n //= 1000
            import datetime
            return datetime.datetime.utcfromtimestamp(n).strftime("%Y-%m-%d")
        except Exception:
            return ""
    m = re.match(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", str(v))
    return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}" if m else ""


def pudong(kw, page=1):
    body = json.dumps({"keyword": kw, "pageNo": page, "pageSize": 50},
                      ensure_ascii=False)
    return json.loads(curl(["-H", "Content-Type: application/json", "-X", "POST",
                            "-d", body,
                            "https://www.pudong.gov.cn/zwgk-search-front/api/pudong/search"]))


def xuhui(kw, cur=1):
    body = json.dumps({"query": kw, "cid": "qjoz2x", "size": 20, "current": cur},
                      ensure_ascii=False)
    return json.loads(curl(["-H", "Content-Type: application/json", "-X", "POST",
                            "-d", body,
                            "https://ss.shanghai.gov.cn/manda-app/api/app/search/v1/qjoz2x/search"]))


def sweep_pudong():
    rows = {}
    for kw in KWS:
        for page in (1, 2):
            r = retry(lambda: pudong(kw, page))
            if not r or r.get("code") != 0:
                break
            lst = (r.get("data") or {}).get("list") or []
            if not lst:
                break
            for it in lst:
                u = it.get("url") or ""
                t = (it.get("title") or "").strip()
                if not u or not TARGET.search(t):
                    continue
                dn = ""
                if it.get("docNumType") and it.get("docNumNo"):
                    dn = (f"{it['docNumType']}〔{it.get('docNumYear','')}〕"
                          f"{it['docNumNo']}号")
                rows[u] = {
                    "district": "浦东新区", "title": t,
                    "publishDate": ts2date(it.get("issueDate")) or ts2date(it.get("writtenDate")),
                    "url": u, "docNo": dn,
                    "issuer": ("上海市浦东新区" + it["dispatchAgency"]
                               if it.get("dispatchAgency") else ""),
                    "pdfUrls": [it["pdfFileUrl"]] if it.get("pdfFileUrl") else [],
                    "_kw": kw, "_src": "pudong-api",
                }
            time.sleep(0.25)
        print(f"[浦东] {kw} cum {len(rows)}", file=sys.stderr)
    return list(rows.values())


def sweep_xuhui():
    rows = {}
    for kw in KWS:
        for cur in (1, 2):
            r = retry(lambda: xuhui(kw, cur))
            if not r or not r.get("success"):
                break
            items = ((r.get("result") or {}).get("items")) or []
            if not items:
                break
            for it in items:
                t = ((it.get("title") or {}).get("raw") or "").strip()
                u = ((it.get("url") or {}).get("raw") or "").strip()
                if not u or not TARGET.search(t):
                    continue
                if "xuhui.gov.cn" not in u:
                    continue
                d = it.get("date") or it.get("attrs", {}).get("raw", {}).get("date") or ""
                rows[u] = {"district": "徐汇区", "title": t,
                           "publishDate": ts2date(d), "url": u, "docNo": "",
                           "issuer": "", "pdfUrls": [], "_kw": kw,
                           "_src": "xuhui-manda"}
            time.sleep(0.25)
        print(f"[徐汇] {kw} cum {len(rows)}", file=sys.stderr)
    return list(rows.values())


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "both"
    out = {}
    if which in ("both", "pd"):
        out["pudong"] = sweep_pudong()
        print("浦东", len(out["pudong"]))
    if which in ("both", "xh"):
        out["xuhui"] = sweep_xuhui()
        print("徐汇", len(out["xuhui"]))
    json.dump(out, open(os.path.join(RAW, f"sweep_{which}.json"), "w",
                        encoding="utf-8"), ensure_ascii=False, indent=1)
    print("done")
