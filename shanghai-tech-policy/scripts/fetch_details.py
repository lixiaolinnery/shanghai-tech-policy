#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""详情页抓取 + 机械字段抽取。
输出 data/details/<id>.json —— 含正文纯文本、文号、发布单位、日期、PDF/附件链接。
"""
import json, os, re, sys, hashlib, html as ihtml, time
from concurrent.futures import ThreadPoolExecutor, as_completed
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from crawl_list import fetch  # noqa

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
DET = os.path.join(DATA, "details")
TXT = os.path.join(ROOT, "data", "text")
os.makedirs(DET, exist_ok=True)
os.makedirs(TXT, exist_ok=True)

DOCNO_RE = re.compile(r'[\u4e00-\u9fa5]{1,8}〔\d{4}〕\s*\d+\s*号')
DOCNO_LABELED = re.compile(r'文\s*号\s*[：:]\s*([\u4e00-\u9fa5]{1,10}〔\d{4}〕\s*\d+\s*号)')
DOCNO_STANDALONE = re.compile(r'^\s*(?:文号[：:]\s*)?([\u4e00-\u9fa5]{2,10}〔\d{4}〕\s*\d+\s*号)\s*$')
UNIT_RE = re.compile(r'(上海市[^\s，。、]{2,20}(?:委员会|局|办公室|人民政府|中心|协会|厅))')
DATE_IN_BODY = re.compile(r'(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日')
MONEY_RE = re.compile(r'(?:不超过|最高|不超过人民币|给予|按)?\s*([0-9]+(?:\.[0-9]+)?)\s*(万元|亿元|元)')
PCT_RE = re.compile(r'([0-9]+(?:\.[0-9]+)?)\s*%')
DEADLINE_HINTS = ["截止", "前完成", "前报送", "前提交", "前登录", "申报时间", "受理时间",
                  "申请时间", "公示期", "报送时间", "受理截止", "截止时间"]
# 站点名后缀：标题里要剥掉
TITLE_TAIL = re.compile(r'[_\-—|].{0,40}$')


def clean_title(t):
    t = re.sub(r'\s+', ' ', t).strip()
    # 政府站 <title> 常为「正文标题_栏目名_站点名」
    if '_' in t:
        parts = [p.strip() for p in t.split('_') if p.strip()]
        if len(parts) >= 2:
            t = parts[0]
    # 标题里混入元信息时截断
    for mk in ['发布日期', '发布时间', '文号：', '文号:', '信息来源', '来源：', '来源:']:
        i = t.find(mk)
        if i > 4:
            t = t[:i]
    t = t.strip()
    if len(t) > 90:
        t = t[:90]
    return t.strip()


def strip_tags(h):
    h = re.sub(r'<script.*?</script>', ' ', h, flags=re.S | re.I)
    h = re.sub(r'<style.*?</style>', ' ', h, flags=re.S | re.I)
    h = re.sub(r'<br\s*/?>', '\n', h, flags=re.I)
    h = re.sub(r'</(p|div|li|tr|h[1-6])>', '\n', h, flags=re.I)
    h = re.sub(r'<[^>]+>', '', h)
    h = ihtml.unescape(h)
    h = h.replace('\u3000', ' ').replace('\xa0', ' ')
    lines = [re.sub(r'[ \t]+', ' ', l).strip() for l in h.split('\n')]
    return '\n'.join(l for l in lines if l)


def extract_main(htmltext):
    """尽量取正文区域，失败则退化为全页去标签。"""
    cands = []
    for pat in [
        r'<div[^>]*id="ivs_content"[^>]*>(.*?)</div>\s*<div class="xgfj_wrap"',
        r'<div[^>]*class="[^"]*xxgk_content_nr[^"]*"[^>]*>(.*?)</div>\s*<div class="xgfj_wrap"',
        r'<div[^>]*id="ivs_content"[^>]*>(.*?)</div>',
        r'<div[^>]*class="[^"]*(?:article|content|TRS_Editor|zoom|detail)[^"]*"[^>]*>(.*?)</div>',
        r'<body[^>]*>(.*?)</body>',
    ]:
        m = re.search(pat, htmltext, re.S | re.I)
        if m:
            cands.append(m.group(1))
    best = max(cands, key=len) if cands else htmltext
    return best


ATT_RE = re.compile(
    r'<a[^>]+href="([^"]+?\.(?:pdf|docx?|xlsx?|zip|rar|wps))(?:\?[^"]*)?\s*"[^>]*>(.*?)</a>',
    re.S | re.I)


def extract_attachments(htmltext, base):
    from urllib.parse import urljoin
    out = []
    for m in ATT_RE.finditer(htmltext):
        href, name = m.group(1).strip(), strip_tags(m.group(2))
        if not name:
            name = href.rsplit('/', 1)[-1]
        out.append({"name": name[:120], "url": urljoin(base, href)})
    seen, uniq = set(), []
    for a in out:
        if a["url"] in seen:
            continue
        seen.add(a["url"])
        uniq.append(a)
    return uniq


def strip_nav(text, title):
    """去掉正文开头的导航面包屑与标题行，保留真正的正文。"""
    lines = text.split('\n')
    # 找到正文起始：跳过导航行，直到出现标题行之后再往下
    start = 0
    for i, l in enumerate(lines[:40]):
        if '当前位置' in l or re.match(r'^首页\s*[>＞]', l) or l in ('政务公开>', '通知告示>'):
            start = i + 1
    # 跳过标题行/发布日期行/文号行
    for i in range(start, min(start + 12, len(lines))):
        l = lines[i]
        if (l == title or l.startswith(title[:20]) or l.startswith('发布日期')
                or l.startswith('文号') or l.startswith('来源') or l.startswith('发布时间')):
            start = i + 1
        else:
            break
    return '\n'.join(lines[start:])


NAV_JUNK = re.compile(r'^(正文|打印|关闭|分享|上一篇|下一篇|【.*?】|当前位置|[^，。；]{0,12}>|[^，。；]{0,12}>\s*)$')


def drop_nav_junk(text):
    out = []
    for l in text.split('\n'):
        if NAV_JUNK.match(l.strip()) and len(l.strip()) <= 16:
            continue
        out.append(l)
    return '\n'.join(out)


def parse_detail(url, htmltext):
    body_html = extract_main(htmltext)
    raw_text = strip_tags(body_html)
    title = ""
    m = re.search(r'<span[^>]*id="ivs_title"[^>]*>(.*?)<i', htmltext, re.S)
    if not m:
        m = re.search(r'<h1[^>]*>(.*?)</h1>', htmltext, re.S)
    if not m:
        m = re.search(r'<title>(.*?)</title>', htmltext, re.S)
    if m:
        title = clean_title(strip_tags(m.group(1)))
    text = drop_nav_junk(strip_nav(raw_text, title))
    date = ""
    m = re.search(r'id="ivs_date"[^>]*>[^0-9]*(20\d{2}-\d{2}-\d{2})', htmltext)
    if not m:
        m = re.search(r'(20\d{2}-\d{2}-\d{2})', htmltext)
    if m:
        date = m.group(1)
    # 文号：①「文号：」显式标注 ②正文开头独立成行的发文字号 ③留空
    docno = ""
    ml = DOCNO_LABELED.search(raw_text)
    if ml:
        docno = re.sub(r'\s+', '', ml.group(1))
    else:
        for l in text.split('\n')[:24]:
            ms = DOCNO_STANDALONE.match(l)
            if ms:
                docno = re.sub(r'\s+', '', ms.group(1))
                break
    refs = list(dict.fromkeys(re.sub(r'\s+', '', x) for x in DOCNO_RE.findall(text)))[:8]
    unit = ""
    mu = UNIT_RE.search(text[:1200])
    if mu:
        unit = mu.group(1)
    pdfs = [a for a in extract_attachments(htmltext, url) if a["url"].lower().endswith(".pdf")]
    # 时间窗口与金额（机械抽取，供后续人工/模型复核）
    deadlines = []
    for line in text.split('\n'):
        if any(h in line for h in DEADLINE_HINTS):
            for dm in DATE_IN_BODY.finditer(line):
                deadlines.append(f"{dm.group(1)}-{int(dm.group(2)):02d}-{int(dm.group(3)):02d}")
            if len(line) <= 160:
                deadlines.append(line.strip())
    money = [f"{a} {b}" for a, b in MONEY_RE.findall(text)][:12]
    pct = PCT_RE.findall(text)[:8]
    return {
        "url": url, "title": title, "publishDate": date,
        "docNo": docno,
        "docNoRefs": refs,
        "issuer": unit,
        "attachments": extract_attachments(htmltext, url),
        "pdfUrls": [a["url"] for a in pdfs],
        "deadlineHints": list(dict.fromkeys([d for d in deadlines if d]))[:10],
        "moneyHints": list(dict.fromkeys(money))[:10],
        "pctHints": pct,
        "textLen": len(text),
        "text": text,
    }


FAILED = os.path.join(DATA, "fetch_failed.json")
FAIL_TTL = 7 * 24 * 3600      # 抓取失败的 URL 在 7 天内不再重试，避免每天都在同一批死链上耗时间
_failed = {}


def load_failed():
    global _failed
    if os.path.exists(FAILED):
        try:
            _failed = json.load(open(FAILED, encoding="utf-8"))
        except Exception:
            _failed = {}


def save_failed():
    try:
        with open(FAILED, "w", encoding="utf-8") as f:
            json.dump(_failed, f, ensure_ascii=False)
    except Exception:
        pass


def recently_failed(url):
    ts = _failed.get(url)
    return bool(ts) and (time.time() - ts) < FAIL_TTL


def page_id(url):
    return hashlib.md5(url.encode()).hexdigest()[:16]


def already(url):
    p = os.path.join(DET, page_id(url) + ".json")
    if os.path.exists(p) and os.path.getsize(p) > 200:
        return p
    return None


def do_one(rec):
    url = rec["url"]
    if already(url):
        _failed.pop(url, None)
        return {"url": url, "cached": True}
    if recently_failed(url):
        return {"url": url, "skipped": True}      # 最近失败过，本轮不再浪费请求
    try:
        h = fetch(url, timeout=30)
    except Exception as e:
        _failed[url] = time.time()
        return {"url": url, "error": str(e)}
    d = parse_detail(url, h)
    _failed.pop(url, None)
    pid = page_id(url)
    with open(os.path.join(DET, pid + ".json"), "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False)
    with open(os.path.join(TXT, pid + ".txt"), "w", encoding="utf-8") as f:
        f.write(d["title"] + "\n" + d["publishDate"] + "\n" + d["text"])
    return {"url": url, "len": d["textLen"]}


def main():
    src = sys.argv[1]
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    workers = int(sys.argv[3]) if len(sys.argv) > 3 else 8
    recs = json.load(open(src, encoding="utf-8"))
    if limit:
        recs = recs[:limit]
    load_failed()
    before = len(_failed)
    ok = err = cached = skipped = 0
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(do_one, r): r for r in recs}
        for i, f in enumerate(as_completed(futs), 1):
            try:
                r = f.result()
            except Exception as e:
                r = {"error": str(e)}
            if r.get("error"):
                err += 1
            elif r.get("skipped"):
                skipped += 1
            elif r.get("cached"):
                cached += 1
            else:
                ok += 1
            if i % 50 == 0:
                print(f"  {i}/{len(recs)} ok={ok} cached={cached} err={err} "
                      f"{time.time()-t0:.0f}s", file=sys.stderr, flush=True)
    save_failed()
    print(f"done ok={ok} cached={cached} err={err} skipped(近期失败)={skipped} "
          f"failed缓存 {before}->{len(_failed)} in {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
