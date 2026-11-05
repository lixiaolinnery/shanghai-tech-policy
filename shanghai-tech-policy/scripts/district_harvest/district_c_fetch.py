#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""抓取 district_c 线索页面：HTTP 状态、<title>、日期、正文、PDF 链接。"""
import json, os, re, subprocess, sys, time, html as ihtml, hashlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw_district_c")
OUT = os.path.join(RAW, "fetched")
os.makedirs(OUT, exist_ok=True)

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")


JAR = os.path.join(RAW, "cookies.txt")


def curl(args, timeout=40, referer=None):
    cmd = ["curl", "-sS", "-L", "-k", "--compressed", "-m", str(timeout),
           "-c", JAR, "-b", JAR,
           "-H", f"User-Agent: {UA}", "-H", "Accept-Language: zh-CN,zh;q=0.9"]
    if referer:
        cmd += ["-H", f"Referer: {referer}"]
    cmd += args
    p = subprocess.run(cmd, capture_output=True, timeout=timeout + 20)
    return p.stdout


def fetch(url, timeout=40):
    """返回 (code, final_url, body_text_or_None)。"""
    out = curl(["-w", "\n@@@%{http_code}@@@%{url_effective}@@@%{content_type}",
                url], timeout=timeout)
    tail = out.rsplit(b"\n@@@", 1)
    meta = tail[-1] if len(tail) > 1 else b""
    body = tail[0] if len(tail) > 1 else out
    parts = meta.split(b"@@@")
    code = parts[0].decode("ascii", "replace") if parts else "000"
    final = parts[1].decode("utf-8", "replace") if len(parts) > 1 else url
    ctype = parts[2].decode("utf-8", "replace") if len(parts) > 2 else ""
    txt = None
    if code == "200":
        for enc in ("utf-8", "gb18030"):
            try:
                txt = body.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        if txt is None:
            txt = body.decode("utf-8", "replace")
    return code, final, ctype, txt


def strip_html(s):
    if not s:
        return ""
    s = re.sub(r"<script.*?</script>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<style.*?</style>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = ihtml.unescape(s)
    s = re.sub(r"[\u3000\xa0]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


DATE_RE = re.compile(r"(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})")


def norm_date(s):
    m = DATE_RE.search(s or "")
    if not m:
        return ""
    return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"


def analyze(url, district="", hint=""):
    code, final, ctype, body = fetch(url)
    rec = {"url": url, "final": final, "http": code, "ctype": ctype,
           "district": district, "hint": hint,
           "title": "", "date": "", "text": "", "pdfs": []}
    if code == "200" and body:
        m = re.search(r"<title[^>]*>(.*?)</title>", body, re.S | re.I)
        if m:
            rec["title"] = strip_html(m.group(1))
        # 正文标题（很多站点 <title> 只写站名）
        for pat in (r'<h[12][^>]*(?:id="ivs_title"|Article-title|article-title|'
                    r'class="[^"]*title[^"]*")[^>]*>(.*?)</h[12]>',
                    r"<h1[^>]*>(.*?)</h1>"):
            m4 = re.search(pat, body, re.S | re.I)
            if m4:
                h = strip_html(re.sub(r"<small.*?</small>", " ", m4.group(1),
                                      flags=re.S | re.I))
                if h and len(h) >= 6:
                    rec["heading"] = h[:200]
                    break
        rec["text"] = strip_html(body)[:6000]
        # 正文日期（含 ivs_date 之类）
        m5 = re.search(r'(?:ivs_date|Article-time|article-time)[^>]*>\s*'
                       r'(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})', body, re.I)
        if m5:
            rec["date"] = f"{m5.group(1)}-{int(m5.group(2)):02d}-{int(m5.group(3)):02d}"
        # 正文区域常见日期
        if not rec["date"]:
            for pat in (r"(?:发布时间|发布日期|成文日期|发文日期|日期)[^0-9]{0,12}"
                        r"(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})", DATE_RE.pattern):
                m2 = re.search(pat, body)
                if m2:
                    rec["date"] = (f"{m2.group(1)}-{int(m2.group(2)):02d}-"
                                   f"{int(m2.group(3)):02d}")
                    break
        # 文号
        m6 = re.search(r"([\u4e00-\u9fa5]{2,8}[〔\[]\s*20\d{2}\s*[〕\]]\s*"
                       r"第?\s*\d+\s*号)", rec["text"])
        rec["docNo"] = m6.group(1).replace(" ", "") if m6 else ""
        # 发文机关
        m7 = re.search(r"(上海市[\u4e00-\u9fa5]{2,10}(?:区|市)"
                       r"[\u4e00-\u9fa5]{0,12}(?:委员会|局|办公室|人民政府|管委会))",
                       rec["text"])
        rec["issuer"] = m7.group(1) if m7 else ""
        pdfs = set()
        for m3 in re.finditer(r'href="([^"]+\.(?:pdf|doc|docx|xls|xlsx))"', body, re.I):
            u = m3.group(1)
            if u.startswith("//"):
                u = "https:" + u
            elif u.startswith("/"):
                mm = re.match(r"https?://[^/]+", final)
                u = (mm.group(0) if mm else "") + u
            elif not u.startswith("http"):
                u = final.rsplit("/", 1)[0] + "/" + u
            pdfs.add(u)
        rec["pdfs"] = sorted(pdfs)[:8]
        # 软 404 / 空壳页检测（HTTP 200 但内容无效）
        probe = strip_html(body)
        if len(probe) < 120 or re.search(
                r"您访问的页面不存在|页面不存在|网页已删除或移动|404 Not Found|"
                r"您访问的页面已删除", rec["title"] + " " + probe[:600]):
            rec["soft404"] = True
    return rec


def main():
    leads_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(RAW, "leads.json")
    leads = json.load(open(leads_path, encoding="utf-8"))
    results = []
    for i, ld in enumerate(leads):
        url = ld["url"] if isinstance(ld, dict) else ld
        dist = ld.get("district", "") if isinstance(ld, dict) else ""
        hint = ld.get("hint", "") if isinstance(ld, dict) else ""
        try:
            r = analyze(url, dist, hint)
        except Exception as e:  # noqa
            r = {"url": url, "http": "ERR", "error": str(e)[:150],
                 "district": dist, "hint": hint, "title": "", "date": "",
                 "text": "", "pdfs": []}
        results.append(r)
        print(f"[{i+1}/{len(leads)}] {r['http']} {r.get('date','')} "
              f"{(r.get('title') or '')[:50]}", file=sys.stderr)
        time.sleep(0.3)
    h = hashlib.md5((leads_path + str(len(leads))).encode()).hexdigest()[:8]
    outp = os.path.join(OUT, f"fetch_{h}.json")
    json.dump(results, open(outp, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("saved", outp)
    bad = [r for r in results if r["http"] != "200"]
    print(f"ok {len(results)-len(bad)} / {len(results)}; non-200: {len(bad)}")
    for r in bad[:20]:
        print("  ", r["http"], r["url"][:110])


if __name__ == "__main__":
    main()
