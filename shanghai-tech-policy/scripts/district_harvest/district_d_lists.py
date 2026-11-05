#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""district_d: 爬取 server-rendered 栏目列表（奉贤/长宁/临港/静安）。"""
import json, os, re, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw_district")
os.makedirs(RAW, exist_ok=True)

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")


def curl(url, timeout=40, retries=3):
    for i in range(retries):
        try:
            p = subprocess.run(
                ["curl", "-sS", "-L", "--compressed", "-m", str(timeout),
                 "-H", f"User-Agent: {UA}",
                 "-H", "Accept-Language: zh-CN,zh;q=0.9", url],
                capture_output=True, timeout=timeout + 15)
            if p.stdout:
                for enc in ("utf-8", "gb18030"):
                    try:
                        return p.stdout.decode(enc)
                    except UnicodeDecodeError:
                        continue
                return p.stdout.decode("utf-8", "replace")
        except Exception:
            pass
        time.sleep(1.0 * (i + 1))
    return ""


# 每个源: (区, 名称, url 生成器, 页数, 链接正则)
def fx(i):
    return ("https://www.fengxian.gov.cn/kw/tzgg/index.html" if i == 1
            else f"https://www.fengxian.gov.cn/kw/tzgg/index_{i}.html")


def cn(i):
    return ("https://www.shcn.gov.cn/col11010/" if i == 1
            else f"https://www.shcn.gov.cn/col11010/index_{i}.html")


def lg(i):
    return ("https://www.lingang.gov.cn/html/website/lg/index/government/"
            "gonggaogongshi/qitagongshi/index.html" if i == 1 else
            "https://www.lingang.gov.cn/html/website/lg/index/government/"
            f"gonggaogongshi/qitagongshi/list-{i}.html")


def ja(i):
    return ("https://www.shanghai.gov.cn/tsqygs-zjfcqj3/index.html" if i == 1
            else f"https://www.shanghai.gov.cn/tsqygs-zjfcqj3/index_{i}.html")


SOURCES = [
    ("奉贤区", "奉贤科委-通知公告", fx, 62, r"/kw/tzgg/\d{8}/\d+\.html"),
    ("长宁区", "长宁科委-通知公告", cn, 11, r"/col11010/\d{8}/\d+\.html"),
    ("临港新片区", "临港-其他公告", lg, 51,
     r"/qitagongshi/\d+\.html"),
    ("静安区", "静安-市政府栏目", ja, 2,
     r"/tsqygs-zjfcqj3/\d{8}/[0-9a-f]+(?:_aaf)?\.html"),
]

A_RE = re.compile(r'<a\s[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.S | re.I)


def strip_tags(s):
    s = re.sub(r"<[^>]+>", "", s)
    s = s.replace("&nbsp;", " ").replace("&amp;", "&")
    s = s.replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')
    return re.sub(r"\s+", " ", s).strip()


def parse(html, pat, base):
    out = []
    rx = re.compile(pat)
    for m in A_RE.finditer(html):
        href, inner = m.group(1), m.group(2)
        if not rx.search(href):
            continue
        title = strip_tags(inner)
        if len(title) < 6:
            # 标题可能在 title= 属性里
            tm = re.search(r'title="([^"]+)"', m.group(0))
            if tm:
                title = tm.group(1).strip()
        if len(title) < 6:
            continue
        if href.startswith("http"):
            url = href
        elif href.startswith("/"):
            url = base + href
        else:
            continue
        out.append({"title": title, "url": url})
    # 去重保序
    seen, res = set(), []
    for x in out:
        if x["url"] in seen:
            continue
        seen.add(x["url"])
        res.append(x)
    return res


def work(args):
    dname, sname, fn, i, pat, base = args
    html = curl(fn(i))
    if not html:
        return dname, sname, i, []
    return dname, sname, i, parse(html, pat, base)


def main():
    jobs = []
    for dname, sname, fn, pages, pat in SOURCES:
        base = re.match(r"(https?://[^/]+)", fn(1)).group(1)
        for i in range(1, pages + 1):
            jobs.append((dname, sname, fn, i, pat, base))
    print(f"jobs: {len(jobs)}", file=sys.stderr)
    allitems = []
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = {ex.submit(work, j): j for j in jobs}
        done = 0
        for f in as_completed(futs):
            dname, sname, i, items = f.result()
            done += 1
            for x in items:
                x["district"] = dname
                x["source"] = sname
                x["page"] = i
            allitems.extend(items)
            if done % 20 == 0:
                print(f"  {done}/{len(jobs)} pages, {len(allitems)} items",
                      file=sys.stderr)
    # 全局去重
    seen, res = set(), []
    for x in allitems:
        if x["url"] in seen:
            continue
        seen.add(x["url"])
        res.append(x)
    out = os.path.join(RAW, "lists_d.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    print(f"total list items: {len(res)} -> {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
