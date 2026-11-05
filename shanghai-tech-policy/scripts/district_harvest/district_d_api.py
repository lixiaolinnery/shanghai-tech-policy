#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""district_d: 用 /front/api/data/affair 分页抓取普陀/杨浦栏目全量条目。"""
import json, os, re, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw_district")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")

TARGETS = [
    # (区, host, channelId, 栏目名)
    ("杨浦区", "https://www.shyp.gov.cn", "241", "杨浦科经委"),
    ("杨浦区", "https://www.shyp.gov.cn", "860", "杨浦市场监管局"),
    ("杨浦区", "https://www.shyp.gov.cn", "136", "杨浦商务委"),
    ("杨浦区", "https://www.shyp.gov.cn", "86", "杨浦发改委"),
    ("杨浦区", "https://www.shyp.gov.cn", "2492", "杨浦涉企补贴"),
    ("杨浦区", "https://www.shyp.gov.cn", "1315", "杨浦投资促进办"),
    ("杨浦区", "https://www.shyp.gov.cn", "2041", "杨浦政策解读"),
    ("普陀区", "https://www.shpt.gov.cn", "298", "普陀科委通知公告"),
    ("普陀区", "https://www.shpt.gov.cn", "3134", "普陀公示公告"),
    ("普陀区", "https://www.shpt.gov.cn", "3", "普陀区政府文件"),
    ("普陀区", "https://www.shpt.gov.cn", "1616", "普陀委办局规范性文件"),
]


def curl_json(host, path, body, timeout=40, retries=3):
    for i in range(retries):
        try:
            p = subprocess.run(
                ["curl", "-sS", "-L", "--compressed", "-m", str(timeout),
                 "-H", f"User-Agent: {UA}",
                 "-H", "Content-Type: application/json",
                 "-X", "POST", "-d", body, host + path],
                capture_output=True, timeout=timeout + 15)
            if p.stdout:
                return json.loads(p.stdout.decode("utf-8", "replace"))
        except Exception:
            pass
        time.sleep(1.0 * (i + 1))
    return None


def fetch_channel(dname, host, cid, cname):
    items = []
    page = 1
    total = None
    while True:
        body = json.dumps({"channelList": [cid], "pageNo": page,
                           "pageSize": 50}, ensure_ascii=False)
        j = curl_json(host, "/front/api/data/affair", body)
        if not j or j.get("code") != 0:
            break
        d = j.get("data") or {}
        if total is None:
            total = d.get("totalCount") or 0
        lst = d.get("list") or []
        if not lst:
            break
        for it in lst:
            items.append({
                "district": dname, "source": cname, "channelId": cid,
                "title": (it.get("title") or "").strip(),
                "url": it.get("url") or "",
                "displayDate": (it.get("display_date") or 0),
                "dispatch_agency": it.get("dispatch_agency") or "",
                "drafting_unit": it.get("drafting_unit") or "",
                "doc_flag": it.get("doc_flag") or "",
                "channel_name": it.get("channel_name") or "",
            })
        tp = d.get("totalPage") or 1
        if page >= tp or page >= 200:
            break
        page += 1
        time.sleep(0.25)
    print(f"  {dname}/{cname}({cid}): {total} total, got {len(items)}",
          file=sys.stderr)
    return items


def main():
    allitems = []
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = [ex.submit(fetch_channel, *t) for t in TARGETS]
        for f in as_completed(futs):
            try:
                allitems.extend(f.result())
            except Exception as e:
                print("  !", e, file=sys.stderr)
    seen, res = set(), []
    for x in allitems:
        k = x["url"] or (x["district"] + x["title"])
        if k in seen:
            continue
        seen.add(k)
        res.append(x)
    out = os.path.join(RAW, "api_d.json")
    json.dump(res, open(out, "w"), ensure_ascii=False, indent=1)
    print(f"api items: {len(res)} -> {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
