#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""最终校验：逐条独立复检 HTTP 200、枚举合法性、标题与页面一致性。"""
import json, os, re, subprocess, sys, time, html as ihtml
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "district", "district_c.json")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")
JAR = os.path.join(ROOT, "data", "raw_district_c", "cookies.txt")

DISTRICTS = {"浦东新区", "徐汇区", "闵行区", "嘉定区", "松江区", "宝山区"}
CATS = {"企业技术中心", "专利试点示范", "重大产业攻关", "揭榜挂帅",
        "制造业单项冠军", "高新技术企业", "专精特新中小企业", "创新型中小企业",
        "科技型中小企业", "科技小巨人", "科技创新券", "专项资金与补贴",
        "其他科技政策"}
TYPES = {"政策红头文件", "申报通知", "公示通知", "领补贴通知",
         "立项与评价通知", "名单公布"}
FIELDS = ["title", "publishDate", "url", "docNo", "issuer", "district",
          "category", "noticeType", "conditions", "benefits", "pdfUrls"]


def check(r):
    cmd = ["curl", "-sS", "-L", "-k", "--compressed", "-m", "35", "-o", "-",
           "-w", "\n@@@%{http_code}", "-b", JAR, "-c", JAR,
           "-H", f"User-Agent: {UA}", "-H", "Accept-Language: zh-CN,zh;q=0.9",
           r["url"]]
    for attempt in range(3):
        try:
            p = subprocess.run(cmd, capture_output=True, timeout=60)
            raw = p.stdout
            idx = raw.rfind(b"\n@@@")
            code = raw[idx + 4:].decode("ascii", "replace") if idx > 0 else "000"
            if code == "200":
                body = raw[:idx].decode("utf-8", "replace")
                for enc in ("utf-8", "gb18030"):
                    try:
                        body = raw[:idx].decode(enc)
                        break
                    except UnicodeDecodeError:
                        continue
                title_ok = r["title"][:12] in body
                dm = re.match(r"https?://[^/]+", r["url"])
                return {"url": r["url"], "http": code, "titleOk": title_ok,
                        "host": dm.group(0) if dm else ""}
            time.sleep(3 * (attempt + 1))
        except Exception:
            time.sleep(3 * (attempt + 1))
    return {"url": r["url"], "http": code if 'code' in dir() else "000",
            "titleOk": False, "host": ""}


def main():
    rows = json.load(open(OUT, encoding="utf-8"))
    errors, warn = [], []
    for i, r in enumerate(rows):
        for f in FIELDS:
            if f not in r:
                errors.append(f"[{i}] 缺字段 {f}")
        if r["district"] not in DISTRICTS:
            errors.append(f"[{i}] district 非法: {r['district']}")
        if r["category"] not in CATS:
            errors.append(f"[{i}] category 非法: {r['category']}")
        if r["noticeType"] not in TYPES:
            errors.append(f"[{i}] noticeType 非法: {r['noticeType']}")
        if r["publishDate"] and not re.fullmatch(r"\d{4}-\d{2}-\d{2}",
                                                 r["publishDate"]):
            errors.append(f"[{i}] publishDate 非法: {r['publishDate']}")
        for k in ("conditions", "benefits", "pdfUrls"):
            if not isinstance(r[k], list):
                errors.append(f"[{i}] {k} 非数组")
        if not r["url"].startswith("https://") and not r["url"].startswith("http://"):
            errors.append(f"[{i}] url 非法")
    print(f"schema errors: {len(errors)}")
    for e in errors[:20]:
        print("  ", e)

    try:
        subprocess.run(["curl", "-sS", "-k", "-m", "30", "-c", JAR, "-b", JAR,
                        "-o", "/dev/null", "-H", f"User-Agent: {UA}",
                        "https://www.songjiang.gov.cn/"], timeout=45)
    except Exception:
        pass
    with ThreadPoolExecutor(max_workers=4) as ex:
        res = list(ex.map(check, rows))
    ok = [x for x in res if x["http"] == "200"]
    bad = [x for x in res if x["http"] != "200"]
    notitle = [x for x in ok if not x["titleOk"]]
    print(f"\nURL 复检: 200 = {len(ok)}/{len(res)}")
    for x in bad:
        print("  NON-200:", x["http"], x["url"][:110])
    print(f"标题未在页面命中: {len(notitle)}")
    for x in notitle[:15]:
        print("  ?", x["url"][:110])
    json.dump({"ok": len(ok), "total": len(res), "bad": bad,
               "titleMiss": [x["url"] for x in notitle]},
              open(os.path.join(ROOT, "data", "raw_district_c",
                                "final_linkcheck.json"), "w",
                   encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
