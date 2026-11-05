#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""汇总 district_c：合并各来源候选 -> 逐条验活(HTTP 200) -> 分类 -> 写 district_c.json"""
import json, os, re, sys, time, html as ihtml
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw_district_c")
OUT = os.path.join(ROOT, "data", "district")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from district_c_fetch import analyze, strip_html  # noqa

DISTRICTS = ["浦东新区", "徐汇区", "闵行区", "嘉定区", "松江区", "宝山区"]

TARGET = re.compile(
    r"企业技术中心|技术中心|专利.{0,6}(试点|示范)|知识产权.{0,8}(试点|示范|优势)|"
    r"试点示范|攻关|揭榜|挂帅|发榜|单项冠军|制造业冠军|冠军企业|"
    r"先进制造业.{0,8}冠军|创新联合体")

# 明显不属于本次 5 类的噪声
NOISE = re.compile(
    r"环境影响|环评|规划|十五五|招聘|网站普查|停播|事业单位|社区工作者|"
    r"听证|送达|仲裁|资金决算|预算|采购|招标|中标|校服|职业教育|绿化市容|"
    r"疾病|公共卫生应急|党校|书法|摩托艇|水上摩托|融媒体|特殊津贴|"
    r"预备役|清淤|道路|桥梁|水务|消防|应急演练|房屋|修缮")


def classify_cat(t):
    if re.search(r"揭榜|挂帅|发榜", t):
        return "揭榜挂帅"
    if re.search(r"企业技术中心", t) or re.search(r"技术中心", t):
        return "企业技术中心"
    if re.search(r"单项冠军|制造业冠军|冠军企业|先进制造业.{0,8}冠军", t):
        return "制造业单项冠军"
    if re.search(r"攻关", t):
        return "重大产业攻关"
    if re.search(r"专利.{0,6}(试点|示范)|知识产权.{0,8}(试点|示范|优势)|试点示范", t):
        return "专利试点示范"
    if re.search(r"知识产权|专利", t):
        return "专利试点示范"
    if re.search(r"创新联合体", t):
        return "重大产业攻关"
    return "其他科技政策"


def classify_type(t):
    if re.search(r"公示|拟认定|拟支持|拟立项|征求意见", t):
        return "公示通知"
    if re.search(r"名单", t) and re.search(r"认定|公布|下达|备案|结果", t):
        return "名单公布"
    if re.search(r"立项|验收|评价结果|结题|评估结果", t):
        return "立项与评价通知"
    if re.search(r"管理办法|实施细则|操作细则|若干措施|工作指引|实施办法|"
                 r"奖励办法|管理办法（|规定|方案", t):
        return "政策红头文件"
    if re.search(r"奖励|资助|经费|拨付|兑现|补贴|下达.{0,12}资金|资金.{0,6}申报",
                 t):
        return "领补贴通知"
    if re.search(r"申报|征集|组织|开展|指南|通知|榜单", t):
        return "申报通知"
    return "政策红头文件"


def load_candidates():
    cands = {}

    def add(url, dist, title="", date="", extra=None):
        if not url or not url.startswith("http"):
            return
        key = url.split("#")[0]
        rec = cands.setdefault(key, {"url": key, "district": dist, "title": title,
                                     "publishDate": date, "docNo": "", "issuer": "",
                                     "pdfUrls": [], "text": ""})
        if title and not rec["title"]:
            rec["title"] = title
        if date and not rec["publishDate"]:
            rec["publishDate"] = date
        if extra:
            for k, v in extra.items():
                if v and not rec.get(k):
                    rec[k] = v

    # 1) 浦东/徐汇 接口清扫
    p = os.path.join(RAW, "sweep_both.json")
    if os.path.exists(p):
        d = json.load(open(p, encoding="utf-8"))
        for r in d.get("pudong", []):
            add(r["url"], "浦东新区", r["title"], r["publishDate"],
                {"docNo": r.get("docNo", ""), "issuer": r.get("issuer", ""),
                 "pdfUrls": r.get("pdfUrls", [])})
        for r in d.get("xuhui", []):
            add(r["url"], "徐汇区", r["title"], r.get("publishDate", ""))

    # 2) 列表页抓取
    p = os.path.join(RAW, "lists_all.json")
    if os.path.exists(p):
        d = json.load(open(p, encoding="utf-8"))
        for k, v in d.items():
            for r in v:
                add(r["url"], r["district"], r["title"], r.get("publishDate", ""),
                    {"issuer": r.get("issuer", "")})

    # 3) Manda 站内搜索（宝山 / 松江）
    for fn in os.listdir(RAW):
        if fn.startswith("manda_") and fn.endswith(".json"):
            for r in json.load(open(os.path.join(RAW, fn), encoding="utf-8")):
                add(r["url"], r["district"], r["title"], r.get("publishDate", ""),
                    {"docNo": r.get("docNo", "")})

    # 4) 市统一检索 detail
    p = os.path.join(RAW, "city_detail.json")
    if os.path.exists(p):
        for r in json.load(open(p, encoding="utf-8")):
            add(r["url"], r["district"], r["title"], r.get("publishDate", ""),
                {"docNo": r.get("docNo", ""), "issuer": r.get("issuer", ""),
                 "pdfUrls": r.get("pdfUrls", []), "text": r.get("text", "")})

    # 5) 手工线索
    p = os.path.join(RAW, "leads_manual.json")
    if os.path.exists(p):
        for r in json.load(open(p, encoding="utf-8")):
            add(r["url"], r["district"])

    return list(cands.values())


def enrich(rec):
    try:
        a = analyze(rec["url"], rec["district"])
        if a["http"] != 200:
            time.sleep(2.0)
            a = analyze(rec["url"], rec["district"])
    except Exception as e:  # noqa
        rec["_http"] = "ERR"
        rec["_err"] = str(e)[:120]
        return rec
    rec["_http"] = a["http"]
    rec["_final"] = a["final"]
    rec["_soft404"] = bool(a.get("soft404"))
    if a["http"] == "200":
        pt = a["title"]
        # 页面 <title> 常带站名后缀，保留但我们优先用列表标题
        rec["_pageTitle"] = pt
        heading = a.get("heading") or ""
        generic = (not pt) or len(pt) < 8 or re.search(
            r"科创服务平台|人民政府门户网站|加载中|首页|政务公开$", pt)
        if not rec["title"] or (generic and heading):
            if heading and (not rec["title"] or len(heading) > len(rec["title"]) - 5):
                rec["title"] = heading
            elif not rec["title"]:
                rec["title"] = re.split(r"[_|]", pt)[0].strip()
        if not rec["publishDate"] and a["date"]:
            rec["publishDate"] = a["date"]
        if not rec["text"]:
            rec["text"] = a["text"]
        if not rec["pdfUrls"]:
            rec["pdfUrls"] = a["pdfs"]
        if not rec.get("docNo") and a.get("docNo"):
            rec["docNo"] = a["docNo"]
        if not rec.get("issuer") and a.get("issuer"):
            rec["issuer"] = a["issuer"]
    return rec


def extract_conds(text):
    out = []
    for sent in re.split(r"(?<=[。；;])", text or ""):
        s = sent.strip()
        if 12 <= len(s) <= 220 and re.search(
                r"应当具备|应具备|申报条件|申请条件|基本条件|须同时满足|"
                r"符合以下条件|具备以下", s):
            out.append(s)
        if len(out) >= 3:
            break
    return out


def extract_benefits(text):
    out = []
    for sent in re.split(r"(?<=[。；;])", text or ""):
        s = sent.strip()
        if 8 <= len(s) <= 220 and re.search(r"给予|奖励|资助|补贴|支持", s) \
                and re.search(r"万元|亿元|%|比例", s):
            out.append(s)
        if len(out) >= 3:
            break
    return out


POLICY_MARK = re.compile(
    r"通知|公告|公示|名单|办法|细则|方案|意见|指南|规定|申报|认定|立项|评价|"
    r"征集|奖励|批复|解读|标准|措施|指引|榜单|备案|验收|资金|经费|资助|补贴")

GOOD_DOMAINS = re.compile(
    r"^https?://(www\.pudong\.gov\.cn|www\.xuhui\.gov\.cn|zwgk\.shmh\.gov\.cn|"
    r"kc\.shmh\.gov\.cn|keji\.jiading\.cn|jingwei\.jiading\.cn|"
    r"www\.jiading\.gov\.cn|www\.songjiang\.gov\.cn|www\.shbsq\.gov\.cn|"
    r"xxgk\.shbsq\.gov\.cn|www\.shanghai\.gov\.cn)/")


def is_notice(rec):
    """剔除新闻动态 / 办事指南，仅保留政策类通知。"""
    t = rec["title"]
    if not POLICY_MARK.search(t):
        return False
    if re.search(r"^视频|澎湃|上观|来源：|转发", t):
        return False
    if not GOOD_DOMAINS.match(rec["url"]):
        return False
    if rec["url"].startswith("http://zwdt."):
        return False
    return True


def dedup(rows):
    """同区同标题（去掉《》和空白）只保留一条，优先有日期、有文号的。"""
    def key(r):
        return (r["district"], re.sub(r"[《》\s（）()]|（.*?）", "", r["title"]))
    best = {}
    for r in rows:
        k = key(r)
        if k not in best:
            best[k] = r
            continue
        old = best[k]
        score = lambda x: (1 if x["publishDate"] else 0) + \
                          (1 if x["docNo"] else 0) + \
                          (1 if x["benefits"] else 0)
        if score(r) > score(old):
            best[k] = r
    return list(best.values())


def select_balanced(rows, per_dist=16, per_cat=6, per_cat_recent=4,
                    min_dist=10):
    """每区按类均衡取样：每类最多 per_cat 条，优先 2023–2026；
    不足 min_dist 条时按时间倒序补足。"""
    from collections import defaultdict
    by_d = defaultdict(list)
    for r in rows:
        by_d[r["district"]].append(r)
    picked = []
    for dist, items in by_d.items():
        by_c = defaultdict(list)
        for r in items:
            by_c[r["category"]].append(r)
        chosen, used = [], set()
        for cat, rs in by_c.items():
            rec = [r for r in rs if r["publishDate"][:4] >= "2023"]
            old = [r for r in rs if r["publishDate"][:4] < "2023"]
            rec.sort(key=lambda x: x["publishDate"], reverse=True)
            old.sort(key=lambda x: x["publishDate"], reverse=True)
            for r in rec[:per_cat_recent] + old[:per_cat - per_cat_recent]:
                chosen.append(r)
                used.add(r["url"])
        chosen.sort(key=lambda x: (x["publishDate"][:4] >= "2023",
                                   x["publishDate"]), reverse=True)
        chosen = chosen[:per_dist]
        # 补足下限
        if len(chosen) < min_dist:
            rest = [r for r in items if r["url"] not in used
                    and r["url"] not in {c["url"] for c in chosen}]
            rest.sort(key=lambda x: (x["publishDate"][:4] >= "2023",
                                     x["publishDate"]), reverse=True)
            chosen += rest[:min_dist - len(chosen)]
        picked += chosen
    return picked


def norm_date(s):
    m = re.search(r"(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})", s or "")
    if not m:
        return ""
    return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"


def main():
    cands = load_candidates()
    # 手工线索（无标题）先抓回来再判断，故此处不按标题预筛
    sel = [c for c in cands
           if (TARGET.search(c["title"]) if c["title"] else True)
           and not NOISE.search(c["title"] or "")]
    print(f"candidates {len(cands)} -> selected {len(sel)}", file=sys.stderr)
    # 预热 cookie（松江等站需要先访问首页拿 cookie）
    try:
        from district_c_fetch import curl as _c
        _c(["https://www.songjiang.gov.cn/"], timeout=35)
    except Exception:  # noqa
        pass
    with ThreadPoolExecutor(max_workers=4) as ex:
        recs = list(ex.map(enrich, sel))
    ok = [r for r in recs if r["_http"] == "200" and r["title"]
          and not r.get("_soft404") and is_notice(r)]
    print(f"http200 {len(ok)}", file=sys.stderr)
    # 保存富化后的候选池，便于后续只调分类/排序而无需重新抓取
    json.dump(ok, open(os.path.join(RAW, "pool.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    final = []
    for r in ok:
        cat = classify_cat(r["title"])
        nt = classify_type(r["title"])
        final.append({
            "title": r["title"],
            "publishDate": norm_date(r["publishDate"]) or norm_date(r["text"][:400]),
            "url": r["url"],
            "docNo": r.get("docNo", "") or "",
            "issuer": r.get("issuer", "") or "",
            "district": r["district"],
            "category": cat,
            "noticeType": nt,
            "conditions": extract_conds(r.get("text", "")),
            "benefits": extract_benefits(r.get("text", "")),
            "pdfUrls": r.get("pdfUrls", []) or [],
            "_http": 200,
        })
    final = dedup(final)
    final = select_balanced(final)
    final.sort(key=lambda x: (x["district"], x["category"], x["publishDate"]),
               reverse=False)
    os.makedirs(OUT, exist_ok=True)
    outp = os.path.join(OUT, "district_c.json")
    json.dump(final, open(outp, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("wrote", outp, len(final))
    # 统计
    from collections import Counter
    print("district:", dict(Counter(x["district"] for x in final)))
    print("category:", dict(Counter(x["category"] for x in final)))


if __name__ == "__main__":
    main()
