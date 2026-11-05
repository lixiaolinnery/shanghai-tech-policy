#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""district_e7: 手工线索 URL 抓元数据 + 组装最终 district_e.json。

最终输出只保留 HTTP 200 的 URL（黄浦区官网被瑞数 WAF 拦截，统一返回 202，
这类条目一律改用 shanghai.gov.cn 镜像；确实无镜像的剔除并在报告中说明）。
"""
import json, os, re, subprocess, sys, time, html as ihtml
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw_district")
OUT = os.path.join(ROOT, "data", "district", "district_e.json")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")

CAT_PRIORITY = ["企业技术中心", "专利试点示范", "重大产业攻关", "揭榜挂帅",
                "制造业单项冠军", "高新技术企业", "专精特新中小企业",
                "创新型中小企业", "科技型中小企业", "科技小巨人", "科技创新券",
                "专项资金与补贴", "其他科技政策"]

CAT_KW = [
    ("企业技术中心", ["企业技术中心", "区级技术中心"]),
    ("制造业单项冠军", ["单项冠军"]),
    ("揭榜挂帅", ["揭榜挂帅", "揭榜", "发榜"]),
    ("重大产业攻关", ["攻关"]),
    ("专利试点示范", ["专利试点", "专利工作试点", "专利示范", "高价值专利",
                      "知识产权试点", "知识产权示范", "专利培育", "专利",
                      "知识产权"]),
    ("高新技术企业", ["高新技术企业", "高企"]),
    ("专精特新中小企业", ["专精特新"]),
    ("创新型中小企业", ["创新型中小企业", "创新型企业总部"]),
    ("科技型中小企业", ["科技型中小企业"]),
    ("科技小巨人", ["科技小巨人", "小巨人"]),
    ("科技创新券", ["科技创新券"]),
]

TECH_KW = ["企业技术中心", "技术中心", "专利", "知识产权", "攻关", "揭榜", "发榜",
           "单项冠军", "高新技术企业", "高企", "专精特新", "创新型中小企业",
           "创新型企业总部", "科技型中小企业", "小巨人", "科技小巨人", "科技创新券",
           "科技发展基金", "科技专项", "科技创新", "研发机构", "工程技术研究中心",
           "技术改造", "首台套", "智能工厂", "科技企业", "科技奖励", "科技项目",
           "科技计划", "孵化器", "众创空间", "科技成果", "产业专项", "专项资金",
           "科技扶持", "技术合同", "智慧城市"]

BAD_TITLE = ["政策解读", "一图读懂", "图文解读", "跟踪解读", "视频解读", "草案",
             "征求意见", "废止"]

TITLE_OVERRIDE = {
    "https://www.shhk.gov.cn/hkxxgk/showinfo.html?infoGuid=2d602e7e-8f48-4de3-92f2-2372f7271739":
        "关于开展2026年度虹口区企业技术中心申报工作的通知",
    "https://www.shhk.gov.cn/hkxxgk/showinfo.html?infoGuid=63f8974e-42cb-4263-b393-13a4e40bddf7":
        "关于印发《2024年度虹口区企业技术中心（第十五批）名单》的通知",
}

CLEAR_DATE = {
    "https://www.shhk.gov.cn/hkxxgk/showinfo.html?infoGuid=2d602e7e-8f48-4de3-92f2-2372f7271739",
    "https://www.shhk.gov.cn/hkxxgk/showinfo.html?infoGuid=63f8974e-42cb-4263-b393-13a4e40bddf7",
}

MANUAL = [
    # ---------------- 虹口区 ----------------
    ("虹口区", "https://www.shhk.gov.cn/hkxxgk/showinfo.html?infoGuid=2d602e7e-8f48-4de3-92f2-2372f7271739"),
    ("虹口区", "https://www.shanghai.gov.cn/nw17239/20250718/79ff0ee395e54fd09945ec79355a12d8.html"),
    ("虹口区", "https://www.shanghai.gov.cn/tsqygs-zjfcqj7/20250709/85689727f2e74b96a1ebdf48f53ed32e_f7a.html"),
    ("虹口区", "https://www.shanghai.gov.cn/tsqygs-zjfcqj7/20250709/39b59d2c556e44ab90ce909966d31f7c_f7a.html"),
    ("虹口区", "https://www.shhk.gov.cn/hkxxgk/showinfo.html?infoGuid=63f8974e-42cb-4263-b393-13a4e40bddf7"),
    ("虹口区", "https://www.shhk.gov.cn/xwzx/002002/20250516/a69cc509-6ee2-4a98-930e-de215e7d18d6.html"),
    ("虹口区", "https://www.shhk.gov.cn/slh/038002/20250123/a6b2f3e4-8c89-4275-8da5-de76b78a8d3e.html"),
    ("虹口区", "https://www.shanghai.gov.cn/tsqygs-zjfcqj7/20251023/d1edbd1f74e343798a9904ad3168ca98.html"),
    ("虹口区", "https://www.shanghai.gov.cn/tszczq-qtqj7/20251119/96041bf09b594af0b6c252c9f0e3d0aa.html"),
    ("虹口区", "https://www.shanghai.gov.cn/tszczq-qtqj7/20250610/e5e498be57da4518b148c881b09c9dd1.html"),
    ("虹口区", "https://www.shanghai.gov.cn/tszczq-qtqj7/20250610/abef38e5a03c4f2582db9aa651df03c3.html"),
    ("虹口区", "https://www.shhk.gov.cn/xwzx/002014/20250707/d1e8529f-fb5c-46bc-8274-643aa2e3ffb6.html"),
    # ---------------- 黄浦区 ----------------
    ("黄浦区", "https://www.shanghai.gov.cn/jszx-gqwj2/20250724/c1fe698d3cc34f07ac8f33a152890e27.html"),
    ("黄浦区", "https://www.shanghai.gov.cn/tszczq-qtqj2/20250610/5dfd2e3e70d54a418fc458f4f810829a.html"),
    ("黄浦区", "https://www.shanghai.gov.cn/tsqygs-zjfcqj2/20251013/45812d6548be47d7975ac9f886b9b19d.html"),
    ("黄浦区", "https://www.shanghai.gov.cn/tsqygs-zjfcqj2/20251013/5b9e41a381914ba6a48a8db5faef7ab0.html"),
    ("黄浦区", "https://www.shanghai.gov.cn/tszczq-qtqj2/20260115/2efd2f73ff1f4f7bb78c27442de2217e.html"),
    ("黄浦区", "https://www.shanghai.gov.cn/tszczq-qtqj2/20260115/6d34226e46a04655b7f2e17a5439701f.html"),
    ("黄浦区", "https://www.shanghai.gov.cn/tszczq-qtqj2/20250928/01633cced4e24e7b95ef1fa870b2aacd.html"),
    ("黄浦区", "https://www.shanghai.gov.cn/tszczq-qtqj2/20251119/615fd1fd74c640c8bfe37762bbb547d5.html"),
    ("黄浦区", "https://www.shanghai.gov.cn/tszczq-qtqj2/20250610/b0d1022afe90461ba7639886485985df.html"),
    ("黄浦区", "https://www.shanghai.gov.cn/cxcy-gqwj2/20230511/b11aae11eea94abf96ad1ad0fa1808e4.html"),
    ("黄浦区", "https://www.shanghai.gov.cn/tszczq-qtqj2/20250610/cca4091b45b640438a482331bcc369f7.html"),
    # ---------------- 崇明区 ----------------
    ("崇明区", "https://www.shcm.gov.cn/govxxgk/qjw/2025-04-21/36d89c4e-348c-4c25-9da8-236f3c9ecb1d.html"),
    ("崇明区", "https://www.shcm.gov.cn/govxxgk/qjw/2024-11-15/14e0c464-4c44-45e3-b975-efde2505f7a0.html"),
    ("崇明区", "https://www.shcm.gov.cn/bmpd/019001/019001002/20241115/61d1c519-1f93-441d-8897-d94c59b4fe4b.html"),
    ("崇明区", "https://www.shcm.gov.cn/bmpd/019001/019001002/20240920/c39a43b7-b587-4891-afb0-d54eae31a706.html"),
    ("崇明区", "https://www.shcm.gov.cn/govxxgk/qjw/2026-07-28/1acb2e7a-3c41-4821-a986-e27473141f06.html"),
    ("崇明区", "https://www.shcm.gov.cn/govxxgk/qjw/2022-08-17/6f1ddb7c-4e50-461b-bec6-9d06e093cf9e.html"),
    ("崇明区", "https://www.shanghai.gov.cn/tsqygs-zjfcqj16/20250709/3015dfa0477b4c22ae2b8e237a1c38f0_bcb.html"),
    ("崇明区", "https://www.shanghai.gov.cn/tsqygs-zjfcqj16/20250709/58427686a99f4b69bad0ffd632a81604_bcb.html"),
    ("崇明区", "https://www.shanghai.gov.cn/tszczq-qtqj16/20251111/6023057b7510492f829ebcc007803f18.html"),
    ("崇明区", "https://shcm.gov.cn/govxxgk/qscjgj/2024-05-11/a34dea83-ecec-47ba-9e59-c88ae8c59f1a.html"),
    # ---------------- 青浦区 ----------------
    ("青浦区", "https://www.shqp.gov.cn/econ/tzgg/20260316/1366242.html"),
    ("青浦区", "https://www.shqp.gov.cn/econ/tzgg/20260904/1394239.html"),
    ("青浦区", "https://www.shqp.gov.cn/econ/tzgg/20260904/1394240.html"),
    ("青浦区", "https://www.shqp.gov.cn/econ/tzgg/20261010/1396967.html"),
    ("青浦区", "https://www.shqp.gov.cn/econ/tzgg/20260902/1394002.html"),
    ("青浦区", "https://www.shqp.gov.cn/econ/tzgg/20250630/1286786.html"),
    ("青浦区", "https://www.shqp.gov.cn/shqp/zwgk/zfgb/2026/5/20260701/1375675.html"),
    # ---------------- 金山区 ----------------
    ("金山区", "https://www.jinshan.gov.cn/ywdt-tzgg/20260108/875029.html"),
]


def curl(args, timeout=40):
    cmd = ["curl", "-sS", "-L", "-k", "--compressed", "-m", str(timeout),
           "-H", f"User-Agent: {UA}", "-H", "Accept-Language: zh-CN,zh;q=0.9"] + args
    p = subprocess.run(cmd, capture_output=True, timeout=timeout + 20)
    raw = p.stdout
    if not raw:
        return ""
    for enc in ("utf-8", "gb18030"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


def strip_html(s):
    if not s:
        return ""
    s = re.sub(r"<script.*?</script>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<style.*?</style>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = ihtml.unescape(s)
    s = re.sub(r"[\u3000\xa0]", " ", s)
    s = re.sub(r"[ \t\r\f\v]+", " ", s)
    s = re.sub(r"\n\s*\n+", "\n", s)
    return s.strip()


def http_status(url, timeout=30):
    cmd = ["curl", "-sS", "-L", "-k", "-o", "/dev/null", "-m", str(timeout),
           "-H", f"User-Agent: {UA}", "-w", "%{http_code}", url]
    for _ in range(2):
        try:
            p = subprocess.run(cmd, capture_output=True, timeout=timeout + 15)
            return p.stdout.decode().strip() or "000"
        except Exception:
            time.sleep(1)
    return "000"


def meta_from_page(url):
    h = curl([url])
    if not h:
        return None
    title = ""
    for pat in (r'name="ArticleTitle" content="([^"]*)"',
                r'id="ivs_title"[^>]*>(.*?)</p>',
                r"<h1[^>]*>(.*?)</h1>",
                r"<title>(.*?)</title>"):
        m = re.search(pat, h, re.S | re.I)
        if m:
            t = ihtml.unescape(re.sub(r"<[^>]+>", "", m.group(1))).strip()
            t = re.sub(r"\s+", " ", t)
            if len(t) > 6 and t not in ("信息公开内容详情页", "信息详情"):
                title = t
                break
    # 标题去掉站点后缀
    title = re.sub(r"[-_—|]\s*上海市.*$", "", title).strip()
    date = ""
    for pat in (r'name="PubDate" content="([^"]*)"',
                r"发布时间[：:]\s*(?:<[^>]+>)*\s*(20\d{2}[-年]\d{1,2}[-月]\d{1,2})",
                r"印发日期[：:]\s*(?:<[^>]+>)*\s*(20\d{2}[-年]\d{1,2}[-月]\d{1,2})",
                r"(20\d{2}年\d{1,2}月\d{1,2}日)"):
        m = re.search(pat, h)
        if m:
            mm = re.match(r"(\d{4})[-/.年](\d{1,2})[-/.月](\d{1,2})", m.group(1).strip())
            if mm:
                date = f"{mm.group(1)}-{int(mm.group(2)):02d}-{int(mm.group(3)):02d}"
                break
    docno = ""
    m = re.search(r"([\u4e00-\u9fa5]{1,14}[〔\[]20\d{2}[〕\]]\s*\d+\s*号)", h)
    if m:
        docno = m.group(1)
    issuer = ""
    m = re.search(r"信息来源[：:]\s*(?:<[^>]+>)*\s*([^<\s]{2,30})", h)
    if m:
        issuer = m.group(1).strip()
    if not issuer:
        m = re.search(r'name="ContentSource" content="([^"]*)"', h)
    if m:
        issuer = ihtml.unescape(m.group(1)).strip()
    if not issuer:
        m = re.search(r"([\u4e00-\u9fa5]{2,20}(?:委员会|局|办公室|政府))[^。\n]{0,10}(?:关于|印发|发布)",
                      strip_html(h)[:4000])
        if m:
            issuer = m.group(1)
    pdfs = re.findall(r'href="([^"]+\.pdf)"', h, re.I)
    base = re.match(r"(https?://[^/]+)", url)
    pdfs = [(p if p.startswith("http") else (base.group(1) + p if p.startswith("/") else url.rsplit("/", 1)[0] + "/" + p))
            for p in pdfs]
    return {"title": title, "date": date, "docno": docno, "issuer": issuer,
            "text": strip_html(h)[:20000], "pdfUrls": list(dict.fromkeys(pdfs))[:3]}


def classify_notice(title):
    rules = [
        ("政策红头文件", ["管理办法", "实施细则", "若干措施", "实施办法", "暂行办法",
                          "实施意见", "操作办法", "工作指引", "认定办法", "奖励办法",
                          "资助办法", "扶持办法", "若干政策", "政策措施", "办法",
                          "实施方案", "行动方案", "若干举措", "管理细则", "细则"]),
        ("公示通知", ["公示", "拟认定", "拟支持", "拟奖励", "拟立项", "拟入库",
                      "拟通过", "拟补助", "拟获评"]),
        ("名单公布", ["名单", "公布", "结果", "公告"]),
        ("立项与评价通知", ["立项", "验收", "评价", "评估", "绩效", "复评"]),
        ("领补贴通知", ["拨付", "兑现", "发放", "下达", "领取", "资金安排",
                        "奖励资金", "资助资金"]),
        ("申报通知", ["申报", "征集", "开展", "推荐", "认定", "复核", "备案",
                      "申请", "组织", "通知", "工作"]),
    ]
    for nt, kws in rules:
        if any(k in title for k in kws):
            return nt
    return "申报通知"


MONEY_RE = re.compile(
    r"[^。；;\n]{0,90}?(?:给予|一次性|最高|按|不超过|奖励|补贴|资助|支持|扶持|每家|每个)"
    r"[^。；;\n]{0,70}?(?:\d[\d,\.]*\s*(?:万元|万|元))[^。；;\n]{0,40}")
COND_RE = re.compile(
    r"[^。；;\n]{0,40}?(?:申报条件|申请条件|支持对象|申报对象|认定条件|应符合|应当符合|"
    r"基本条件|申报范围|支持范围|培育对象|申报主体|支持标准)[^。；;\n]{0,160}")


def extract(regex, txt, n=4, minlen=8):
    out, seen = [], set()
    if not txt:
        return out
    for m in regex.finditer(txt):
        s = re.sub(r"\s+", " ", m.group(0)).strip(" ,，、：:")
        if len(s) < minlen or s in seen:
            continue
        seen.add(s)
        out.append(s)
        if len(out) >= n:
            break
    return out


def classify_cat(title):
    for c, kws in CAT_KW:
        if any(k in title for k in kws):
            return c
    return ""


def is_relevant(title):
    if any(k in title for k in BAD_TITLE):
        return False
    if "十五五" in title or "十四五" in title or "规划纲要" in title:
        return False
    return any(k in title for k in TECH_KW) or bool(classify_cat(title))


LEAK = re.compile(
    r"\s*(?:印发日期|发布日期|发布时间|发布时|来源[：:]|信息来源|字号[：:]|保护视力色|"
    r"各有关单位|各有关企业|各镇|区政府各|20\d{2}[-年]\d{1,2}[-月]\d{1,2}).*$",
    re.S)


def clean_title(t):
    if not t:
        return ""
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"^文章标题[:：]?\s*", "", t).strip()
    t = LEAK.sub("", t).strip()
    t = t.strip(" 　-—_|")
    return t[:120]


def main():
    # ---- 手工线索 ----
    manual = []
    def work(item):
        dist, url = item
        code = http_status(url)
        if code != "200":
            return {"district": dist, "url": url, "_http": code, "title": ""}
        m = meta_from_page(url)
        if not m:
            return {"district": dist, "url": url, "_http": code, "title": ""}
        t = TITLE_OVERRIDE.get(url) or clean_title(m["title"])
        if url in CLEAR_DATE:
            m["date"] = ""
        if not is_relevant(t):
            return {"district": dist, "url": url, "_http": code, "title": t}
        return {
            "title": t, "publishDate": m["date"], "url": url,
            "docNo": m["docno"], "issuer": m["issuer"], "district": dist,
            "category": classify_cat(t), "noticeType": classify_notice(t),
            "conditions": extract(COND_RE, m["text"]),
            "benefits": extract(MONEY_RE, m["text"]),
            "pdfUrls": m["pdfUrls"], "_src": "manual", "_http": code,
            "_text": m["text"][:3000],
        }
    with ThreadPoolExecutor(max_workers=4) as ex:
        manual = list(ex.map(work, MANUAL))
    json.dump(manual, open(os.path.join(RAW, "e7_manual.json"), "w"),
              ensure_ascii=False, indent=1)
    ok = [x for x in manual if x.get("_http") == "200" and x.get("title")]
    print("manual verified 200:", len(ok), "/", len(MANUAL))
    for x in manual:
        if x.get("_http") != "200" or not x.get("title"):
            print("   !!", x["_http"], x["url"][:95])
    print("manual relevant:", sum(1 for x in ok if is_relevant(x["title"])))
    for x in ok:
        pass
    return manual


if __name__ == "__main__":
    main()
