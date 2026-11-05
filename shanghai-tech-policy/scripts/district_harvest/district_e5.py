#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""district_e5: 取详情 + 合并 + 组装 district_e.json"""
import json, os, re, subprocess, sys, time, html as ihtml
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw_district")
OUT = os.path.join(ROOT, "data", "district", "district_e.json")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")

DISTRICTS = {"黄浦区": "0071", "虹口区": "0076", "金山区": "0081",
             "青浦区": "0083", "崇明区": "0085"}
NAME_BY_ID = {v: k for k, v in DISTRICTS.items()}

CAT_PRIORITY = ["企业技术中心", "制造业单项冠军", "揭榜挂帅", "重大产业攻关",
                "专利试点示范", "高新技术企业", "专精特新中小企业",
                "创新型中小企业", "科技型中小企业", "科技小巨人", "科技创新券"]

CAT_KW = [
    ("企业技术中心", ["企业技术中心", "区级技术中心"]),
    ("制造业单项冠军", ["单项冠军"]),
    ("揭榜挂帅", ["揭榜挂帅", "揭榜", "发榜"]),
    ("重大产业攻关", ["攻关"]),
    ("专利试点示范", ["专利试点", "专利工作试点", "专利示范", "高价值专利",
                      "知识产权试点", "知识产权示范", "专利培育", "专利"]),
    ("高新技术企业", ["高新技术企业", "高企"]),
    ("专精特新中小企业", ["专精特新"]),
    ("创新型中小企业", ["创新型中小企业"]),
    ("科技型中小企业", ["科技型中小企业"]),
    ("科技小巨人", ["科技小巨人", "小巨人"]),
    ("科技创新券", ["科技创新券"]),
]

TECH_KW = ["企业技术中心", "技术中心", "专利", "知识产权", "攻关", "揭榜", "发榜",
           "单项冠军", "高新技术企业", "高企", "专精特新", "创新型中小企业",
           "科技型中小企业", "小巨人", "科技小巨人", "科技创新券", "科技发展基金",
           "科技专项", "科技创新", "研发机构", "工程技术研究中心", "技术改造",
           "首台套", "智能工厂", "科技企业", "科技奖励", "科技项目", "科技计划",
           "孵化器", "众创空间", "科技成果", "产业专项", "专项资金", "科技扶持",
           "科技", "创新"]

STRONG = ["企业技术中心", "专利", "知识产权", "攻关", "揭榜", "单项冠军",
          "高新技术企业", "高企", "专精特新", "科技型中小企业", "科技小巨人",
          "科技创新券", "科技发展基金", "科技专项", "科技创新", "科技奖励",
          "科技项目", "科技计划", "智能工厂", "技术改造", "首台套", "研发机构",
          "工程技术研究中心"]

EXCLUDE = ["体育", "招生", "学校", "教育", "养老", "老龄", "残疾", "卫生",
           "动物疫情", "绿化", "垃圾分类", "粮食", "宗教", "人事任免",
           "职务任免", "职级", "应急预案", "防汛", "河道", "水务", "文化",
           "旅游", "妇联", "共青团", "双拥", "征兵", "信访", "档案",
           "审计", "气象", "地震", "消防", "交通", "食品安全", "药品",
           "医保", "低保", "救助", "殡葬", "婚姻", "就业", "培训", "技能",
           "人才公寓", "住房", "公积金", "规划", "土地", "征收", "拆迁",
           "环保", "水务", "林业", "畜牧", "渔业", "农机", "蔬菜",
           "工作总结", "工作要点", "十四五", "十五五", "规划纲要", "党组",
           "党建", "纪检", "表彰", "慰问", "宣传周", "培训班", "调查问卷",
           "征求意见", "行政复议", "处罚", "裁决", "抽查", "检查结果",
           "清单", "目录", "预算", "决算", "三公", "绩效目标"]

TARGET_YEARS = {"2023", "2024", "2025", "2026"}


def curl(args, timeout=45):
    cmd = ["curl", "-sS", "-L", "-k", "--compressed", "-m", str(timeout),
           "-H", f"User-Agent: {UA}", "-H", "Accept-Language: zh-CN,zh;q=0.9"] + args
    p = subprocess.run(cmd, capture_output=True, timeout=timeout + 25)
    raw = p.stdout
    if not raw:
        return ""
    for enc in ("utf-8", "gb18030"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


def post_json(url, body, headers=None, timeout=45, retries=3):
    payload = json.dumps(body, ensure_ascii=False)
    hs = headers or ["-H", "Content-Type: application/json"]
    for i in range(retries):
        try:
            return json.loads(curl(hs + ["-X", "POST", "-d", payload, url], timeout))
        except Exception:
            if i == retries - 1:
                return {}
            time.sleep(0.8 * (i + 1))


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


def classify_cat(title, txt=""):
    for c, kws in CAT_KW:
        if any(k in title for k in kws):
            return c
    return ""


def classify_notice(title):
    rules = [
        ("政策红头文件", ["管理办法", "实施细则", "若干措施", "实施办法", "暂行办法",
                          "实施意见", "操作办法", "工作指引", "认定办法", "奖励办法",
                          "资助办法", "扶持办法", "若干政策", "政策措施", "办法",
                          "实施方案", "行动方案", "若干举措", "意见"]),
        ("公示通知", ["公示", "拟认定", "拟支持", "拟奖励", "拟立项", "拟入库",
                      "拟通过", "拟补助", "拟获评"]),
        ("名单公布", ["名单", "公布", "结果", "公告"]),
        ("立项与评价通知", ["立项", "验收", "评价", "评估", "绩效", "复评"]),
        ("领补贴通知", ["拨付", "兑现", "发放", "下达", "领取", "资金安排",
                        "奖励资金", "资助资金", "资金"]),
        ("申报通知", ["申报", "征集", "开展", "推荐", "认定", "复核", "备案",
                      "申请", "组织", "通知"]),
    ]
    for nt, kws in rules:
        if any(k in title for k in kws):
            return nt
    return "申报通知"


MONEY_RE = re.compile(
    r"[^。；;\n]{0,80}?(?:给予|一次性|最高|按|不超过|奖励|补贴|资助|支持|扶持)"
    r"[^。；;\n]{0,60}?(?:\d[\d,\.]*\s*(?:万元|万|元))[^。；;\n]{0,40}")
COND_RE = re.compile(
    r"[^。；;\n]{0,30}?(?:申报条件|申请条件|支持对象|申报对象|认定条件|应符合|应当符合|"
    r"基本条件|申报范围|支持范围|培育对象)[^。；;\n]{0,140}")


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


def norm_date(v):
    if not v:
        return ""
    m = re.match(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", str(v))
    return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}" if m else ""


def valid_docno(r):
    dt = (r.get("docType") or "").strip()
    dy = (r.get("docYear") or "").strip()
    dn = (r.get("docNo") or "").strip()
    if not dt or dt.lower() == "null" or not dn or dn.lower() == "null":
        return ""
    if "〔" in dn or "[" in dn:
        return dn
    if not re.match(r"^[0-9]+$", dn):
        return ""
    return f"{dt}〔{dy or ''}〕{dn}号"


def is_relevant(title):
    if any(k in title for k in EXCLUDE):
        if not any(k in title for k in ["企业技术中心", "专利", "知识产权", "攻关",
                                        "揭榜", "单项冠军", "高新技术企业",
                                        "专精特新", "科技型中小企业", "科技小巨人",
                                        "科技创新券", "科技奖励", "科技专项",
                                        "技术改造", "智能工厂", "首台套"]):
            return False
    return any(k in title for k in TECH_KW) or bool(classify_cat(title))


# ---------------------------------------------------------------- 详情
def fetch_detail(key):
    sid, bid = key.split("|", 1)
    d = post_json("https://www.shanghai.gov.cn/gwk/policy/detail",
                  {"siteId": sid, "businessId": bid})
    return key, (d.get("data") or {})


def build_sweep():
    path = os.path.join(RAW, "e3_hits.json")
    if not os.path.exists(path):
        return []
    hits = json.load(open(path))
    keys = list(hits.keys())
    out = []
    done = {}
    cache_p = os.path.join(RAW, "e5_details.json")
    if os.path.exists(cache_p):
        done = json.load(open(cache_p))
    todo = [k for k in keys if k not in done]
    print(f"sweep detail todo {len(todo)} / {len(keys)}")
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(fetch_detail, k): k for k in todo}
        for i, f in enumerate(as_completed(futs), 1):
            try:
                k, d = f.result()
            except Exception:
                continue
            done[k] = d
            if i % 40 == 0:
                print("  detail", i, "/", len(todo), flush=True)
                json.dump(done, open(cache_p, "w"), ensure_ascii=False)
    json.dump(done, open(cache_p, "w"), ensure_ascii=False)
    for k, d in done.items():
        url = (d.get("originUrl") or "").strip()
        if not url.startswith("http"):
            continue
        sid = k.split("|", 1)[0]
        title = (d.get("title") or "").strip()
        if not is_relevant(title):
            continue
        txt = strip_html(d.get("txt") or "")
        attrs = d.get("attrs") or {}
        out.append({
            "title": title,
            "publishDate": norm_date(d.get("publishDate")),
            "url": url,
            "docNo": valid_docno(d),
            "issuer": (attrs.get("agency") or d.get("agency") or "").strip(),
            "district": NAME_BY_ID.get(sid, ""),
            "category": classify_cat(title, txt),
            "noticeType": classify_notice(title),
            "conditions": extract(COND_RE, txt),
            "benefits": extract(MONEY_RE, txt),
            "pdfUrls": [],
            "_src": "city-index",
            "_text": txt[:3000],
        })
    print("sweep records", len(out))
    return out


def load(path):
    p = os.path.join(RAW, path)
    if not os.path.exists(p):
        return []
    return json.load(open(p))


MANUAL = os.path.join(RAW, "e_manual.json")


def main():
    recs = []
    recs += build_sweep()
    for f in ("e4_jinshan.json", "e4_qingpu.json"):
        for r in load(f):
            r.setdefault("_src", f)
            recs.append(r)
    # 手工核实条目
    for r in load("e_manual.json"):
        r.setdefault("_src", "manual")
        recs.append(r)

    # 规整
    fixed = []
    for r in recs:
        t = (r.get("title") or "").strip()
        if not t or not r.get("url"):
            continue
        r["title"] = t
        if not r.get("category"):
            r["category"] = classify_cat(t, r.get("_text", ""))
        if not r["category"]:
            if any(k in t for k in ["专项资金", "奖励", "补贴", "资助", "资金",
                                    "兑现", "拨付", "扶持", "基金"]):
                r["category"] = "专项资金与补贴"
            else:
                r["category"] = "其他科技政策"
        if not r.get("noticeType"):
            r["noticeType"] = classify_notice(t)
        r.setdefault("docNo", "")
        r.setdefault("issuer", "")
        r.setdefault("conditions", [])
        r.setdefault("benefits", [])
        r.setdefault("pdfUrls", [])
        r.setdefault("publishDate", "")
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", r.get("publishDate", "")):
            r["publishDate"] = ""
        # 去重键
        r["_key"] = re.sub(r"\s+", "", t)[:60]
        fixed.append(r)

    # 每区去重（同标题或同 URL 保留信息最全的）
    by_district = {}
    for r in fixed:
        by_district.setdefault(r["district"], []).append(r)
    final = []
    for d, rows in by_district.items():
        seen_t, seen_u, picked = set(), set(), []
        # 排序：目标年份优先 + 目标类别优先
        def score(r):
            y = r["publishDate"][:4]
            s = 0
            if y in TARGET_YEARS:
                s -= 100
            if r["category"] in CAT_PRIORITY:
                s -= 50 - CAT_PRIORITY.index(r["category"])
            if r["publishDate"]:
                s -= int(r["publishDate"][:4]) * 0.01
            if r.get("_src", "").startswith(("jinshan", "qingpu")):
                s -= 5
            return s
        for r in sorted(rows, key=score):
            if r["_key"] in seen_t or r["url"] in seen_u:
                continue
            seen_t.add(r["_key"])
            seen_u.add(r["url"])
            picked.append(r)
        final += picked
        print(d, len(rows), "->", len(picked))

    # 输出全部候选（含验证）
    json.dump(final, open(os.path.join(RAW, "e5_all.json"), "w"),
              ensure_ascii=False, indent=1)
    print("total candidates", len(final))


if __name__ == "__main__":
    main()
