#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""上海市文化创意产业网（cms.odb.sh.cn）采集器。

这个站是 JS 渲染的，列表走 TrueCMS 的接口：
    POST https://cms.odb.sh.cn/TrueCMS/messageController/getMessage.do
         columnId=<栏目id>&pageNo=1&pageSize=10
返回 XML 包裹的 <li> 片段，含标题 / 链接 / 日期。
"""
import json
import os
import re
import sys
import time
import html as ihtml

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from crawl_list import fetch  # noqa: E402  （curl 后端）

ROOT = os.path.dirname(HERE)
API = "https://cms.odb.sh.cn/TrueCMS/messageController/getMessage.do"
BASE = "https://cms.odb.sh.cn"
PAGE = 10

# 栏目：id -> 名称
COLUMNS = {
    "21ca65e7-259d-4d6e-b5d3-2a489b228cb8": "公告通知",
    "a7207fd0-0371-45de-8c05-b0400bf06de3": "市级文创资讯",
    "aea9020b-7a6f-4baa-ab88-26534b20241e": "文创园区动态",
    "a8de7f19-b9a1-49ec-a550-d34d367d10ab": "信息公开",
}

REC_RE = re.compile(r'<li>.*?<a href="([^"]+)"[^>]*>(.*?)</a>\s*<span>\s*([\d]{4})/(\d{1,2})/(\d{1,2})\s*</span>', re.S)


def fetch_page(column_id, start_record, per_page=PAGE):
    """按 jpage 插件的真实参数走 GET（startrecord/endrecord/perpage）。

    接口返回 {"result": "<datastore>..."}，先剥掉 JSON 外壳再解析，
    否则里面的引号与斜杠转义会让正则匹配不到。
    """
    import subprocess
    UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")
    end = start_record + per_page - 1
    cmd = ["curl", "-sS", "-k", "-m", "30", "-G",
           "-H", f"User-Agent: {UA}",
           "--data-urlencode", f"startrecord={start_record}",
           "--data-urlencode", f"endrecord={end}",
           "--data-urlencode", f"perpage={per_page}",
           "--data-urlencode", "contentTemplate=",
           "--data-urlencode", f"columnId={column_id}",
           API]
    p = subprocess.run(cmd, capture_output=True, timeout=45)
    raw = p.stdout.decode("utf-8", "replace")
    try:
        return json.loads(raw).get("result", "")
    except Exception:
        return raw


def parse(text, column_name):
    out = []
    for m in REC_RE.finditer(text):
        href, title, y, mo, d = m.groups()
        title = ihtml.unescape(re.sub(r"<[^>]+>", "", title)).strip()
        if not title:
            continue
        out.append({
            "title": title,
            "date": f"{y}-{int(mo):02d}-{int(d):02d}",
            "url": BASE + href if href.startswith("/") else href,
            "source": "wenchuang",
            "channel": column_name,
        })
    return out


def main():
    all_items, seen = [], set()
    for cid, name in COLUMNS.items():
        first = fetch_page(cid, 1)
        m = re.search(r"<totalrecord>(\d+)</totalrecord>", first)
        total = int(m.group(1)) if m else 0
        pages = max(1, (total + PAGE - 1) // PAGE)
        print(f"  {name}: 共 {total} 条，{pages} 页", file=sys.stderr, flush=True)
        got = parse(first, name)
        for i in range(1, pages):
            time.sleep(0.4)
            got.extend(parse(fetch_page(cid, i * PAGE + 1), name))
        for it in got:
            if it["url"] in seen:
                continue
            seen.add(it["url"])
            all_items.append(it)

    out_path = os.path.join(ROOT, "data", "raw", "list_wenchuang.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"source": "wenchuang", "channel": "文创",
                   "count": len(all_items), "items": all_items, "errors": []},
                  f, ensure_ascii=False, indent=1)
    print(f"[wenchuang] items={len(all_items)} -> {out_path}")


if __name__ == "__main__":
    main()
