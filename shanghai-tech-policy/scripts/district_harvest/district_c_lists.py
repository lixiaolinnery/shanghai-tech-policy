#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""district_c：闵行 / 嘉定 / 宝山 列表页深度抓取（含分页与退避重试）。"""
import json, os, re, subprocess, sys, time, html as ihtml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw_district_c")
os.makedirs(RAW, exist_ok=True)

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")


def curl(url, timeout=45, retries=3, backoff=3.0):
    cmd = ["curl", "-sS", "-L", "-k", "--compressed", "-m", str(timeout),
           "-H", f"User-Agent: {UA}", "-H", "Accept-Language: zh-CN,zh;q=0.9",
           "-H", f"Referer: {url}", url]
    for i in range(retries):
        try:
            p = subprocess.run(cmd, capture_output=True, timeout=timeout + 20)
            if p.stdout:
                for enc in ("utf-8", "gb18030"):
                    try:
                        return p.stdout.decode(enc)
                    except UnicodeDecodeError:
                        continue
                return p.stdout.decode("utf-8", "replace")
            time.sleep(backoff * (i + 1))
        except Exception:
            time.sleep(backoff * (i + 1))
    return None


# ---------------------------------------------------------------- 闵行 kc
def minhang_kc(maxpage=30):
    out, seen = [], set()
    for n in range(1, maxpage + 1):
        h = curl(f"https://kc.shmh.gov.cn/list/17/page_{n}.html")
        if not h:
            print(f"  mh-kc page{n} FAIL", file=sys.stderr)
            break
        items = re.findall(
            r'<a href="(/article/17/(\d+)\.html)"[^>]*title="([^"]*)">.*?'
            r'<span class="time">([\d\-]+)</span>', h, re.S)
        if not items:
            break
        for path, _id, title, date in items:
            u = "https://kc.shmh.gov.cn" + path
            if u in seen:
                continue
            seen.add(u)
            out.append({"district": "闵行区", "title": ihtml.unescape(title).strip(),
                        "publishDate": date, "url": u,
                        "issuer": "上海市闵行区科学技术委员会",
                        "_src": "minhang-kc"})
        print(f"  mh-kc page{n}: {len(items)} total {len(out)}", file=sys.stderr)
        time.sleep(0.4)
    return out


# ---------------------------------------------------------------- 闵行 科委 zwgk
def minhang_kw(maxpage=15):
    base = ("https://zwgk.shmh.gov.cn/mh-xxgk-cms/website/mh_xxgk/"
            "xxgk_kw_bmwj_bbmf")
    out, seen = [], set()
    for n in range(0, maxpage):
        h = curl(f"{base}/List/list_{n}.htm")
        if not h:
            break
        items = re.findall(
            r'<li><span class=" ?f_float">([\d\-]+)</span><a[^>]+href="([^"]+)"'
            r'[^>]*title="([^"]*)"', h)
        if not items:
            break
        new = 0
        for date, href, title in items:
            full = ("https://zwgk.shmh.gov.cn/mh-xxgk-cms/website/mh_xxgk/"
                    + href.replace("../../", ""))
            if full in seen:
                continue
            seen.add(full)
            new += 1
            out.append({"district": "闵行区", "title": ihtml.unescape(title).strip(),
                        "publishDate": date, "url": full,
                        "issuer": "上海市闵行区科学技术委员会",
                        "_src": "minhang-kw"})
        print(f"  mh-kw page{n}: {new} total {len(out)}", file=sys.stderr)
        time.sleep(0.4)
    return out


# ---------------------------------------------------------------- 嘉定
JD_RE = re.compile(
    r'<a href="([^"]+)"[^>]*title="标题：([^"]*?)\s*点击数[^"]*?'
    r'发表时间：([\d\-]+)"', re.S)


def jiading(host, issuer, maxpage=30, tag=""):
    out, seen = [], set()
    for n in range(1, maxpage + 1):
        u = (f"https://{host}/publicity/fdzdgknr/gg/zwgg" if n == 1
             else f"https://{host}/publicity/fdzdgknr/gg/zwgg_{n}")
        h = curl(u, timeout=40, retries=4, backoff=4.0)
        if not h:
            print(f"  jd-{tag} page{n} FAIL", file=sys.stderr)
            continue
        items = JD_RE.findall(h)
        if not items:
            print(f"  jd-{tag} page{n} no items", file=sys.stderr)
            if n > 2:
                break
            continue
        new = 0
        for path, title, date in items:
            full = path if path.startswith("http") else f"https://{host}" + path
            if full in seen:
                continue
            seen.add(full)
            new += 1
            out.append({"district": "嘉定区",
                        "title": ihtml.unescape(title).replace("\u3000", " ").strip(),
                        "publishDate": date, "url": full, "issuer": issuer,
                        "_src": f"jiading-{tag}"})
        print(f"  jd-{tag} page{n}: {new} total {len(out)}", file=sys.stderr)
        time.sleep(0.6)
    return out


# ---------------------------------------------------------------- 宝山
def baoshan_gsgg(maxpage=12):
    out, seen = [], set()
    for n in range(1, maxpage + 1):
        u = ("https://www.shbsq.gov.cn/shbs/gsgg/index.html" if n == 1
             else f"https://www.shbsq.gov.cn/shbs/gsgg/index_{n}.html")
        h = curl(u)
        if not h:
            break
        items = re.findall(
            r'<a href="(/shbs/gsgg/(\d{8})/(\d+)\.html)"[^>]*title="([^"]*)"',
            h)
        if not items:
            break
        new = 0
        for path, d8, _id, title in items:
            full = "https://www.shbsq.gov.cn" + path
            if full in seen or not title:
                continue
            seen.add(full)
            new += 1
            out.append({"district": "宝山区", "title": ihtml.unescape(title).strip(),
                        "publishDate": f"{d8[:4]}-{d8[4:6]}-{d8[6:]}",
                        "url": full, "issuer": "上海市宝山区人民政府",
                        "_src": "baoshan-gsgg"})
        print(f"  bs-gsgg page{n}: {new} total {len(out)}", file=sys.stderr)
        time.sleep(0.4)
    return out


def baoshan_cyzc(maxpage=12):
    out, seen = [], set()
    for n in range(1, maxpage + 1):
        u = ("https://www.shbsq.gov.cn/shbs/cyzc/index.html" if n == 1
             else f"https://www.shbsq.gov.cn/shbs/cyzc/index_{n}.html")
        h = curl(u)
        if not h:
            break
        items = re.findall(
            r'<a href="(/shbs/cyzc/(\d{8})/(\d+)\.html)"[^>]*title="([^"]*)"',
            h)
        if not items:
            break
        for path, d8, _id, title in items:
            full = "https://www.shbsq.gov.cn" + path
            if full in seen or not title:
                continue
            seen.add(full)
            out.append({"district": "宝山区", "title": ihtml.unescape(title).strip(),
                        "publishDate": f"{d8[:4]}-{d8[4:6]}-{d8[6:]}",
                        "url": full, "issuer": "上海市宝山区人民政府",
                        "_src": "baoshan-cyzc"})
        time.sleep(0.4)
    return out


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    allout = {}
    if which in ("all", "mh"):
        print("== 闵行 kc ==", file=sys.stderr)
        allout["minhang_kc"] = minhang_kc()
        print("== 闵行 科委 ==", file=sys.stderr)
        allout["minhang_kw"] = minhang_kw()
    if which in ("all", "jd"):
        print("== 嘉定经委 ==", file=sys.stderr)
        allout["jiading_jw"] = jiading("jingwei.jiading.cn",
                                       "上海市嘉定区经济委员会", tag="jw")
        print("== 嘉定科委 ==", file=sys.stderr)
        allout["jiading_kj"] = jiading("keji.jiading.cn",
                                       "上海市嘉定区科学技术委员会", tag="kj")
    if which in ("all", "bs"):
        print("== 宝山 gsgg ==", file=sys.stderr)
        allout["baoshan_gsgg"] = baoshan_gsgg()
        allout["baoshan_cyzc"] = baoshan_cyzc()
    json.dump(allout, open(os.path.join(RAW, f"lists_{which}.json"), "w",
                           encoding="utf-8"), ensure_ascii=False, indent=1)
    for k, v in allout.items():
        print(k, len(v))
