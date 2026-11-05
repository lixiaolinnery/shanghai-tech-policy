#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""合并 候选条目 + 详情页 + 抽取字段 + 深度解读 -> data/policies.json & data/policies.js"""
import json, os, re, sys, glob, hashlib, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_candidates import classify_category, CATEGORY_RULES  # noqa

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
DET = os.path.join(DATA, "details")
GUIDES = os.path.join(DATA, "guides")

_KW = dict(CATEGORY_RULES)


def resolve_category(title, hinted):
    """确定政策类型。

    以标题为准统一分类；当自研规则判为「其他科技政策」时，才考虑外部采集者给的
    分类，且**要求标题里确实出现该类的关键词**，否则回退为「其他科技政策」。
    这样可以避免把「数字广告产业创新」之类硬塞进「揭榜挂帅」。
    """
    mine = classify_category(title)
    if mine != "其他科技政策":
        return mine
    if not hinted or hinted == "其他科技政策":
        return "其他科技政策"
    kws = _KW.get(hinted)
    if kws and any(k in title for k in kws):
        return hinted
    return "其他科技政策"

SOURCE_NAME = {
    "stcsm": "上海市科学技术委员会（上海科技）",
    "sheitc": "上海市经济和信息化委员会",
    "ssme": "上海市企业服务云",
    "sipa": "上海市知识产权局",
    "wenchuang": "上海市文化创意产业推进领导小组办公室",
    "shgov": "上海市人民政府",
    "district": "区级政府",
}
SOURCE_SHORT = {
    "stcsm": "市科委", "sheitc": "市经信委", "ssme": "企业服务云",
    "shgov": "市政府", "sipa": "市知识产权局", "wenchuang": "市文创办", "district": "区级",
}

FUNDING_KW = ["资金", "经费", "补贴", "资助", "奖励", "拨付", "下达", "兑现", "贴息",
              "保费", "后补助", "补助", "减税", "税收", "加计扣除"]
DISTRICT_NAMES = ["浦东新区", "黄浦区", "徐汇区", "长宁区", "静安区", "普陀区", "虹口区",
                  "杨浦区", "闵行区", "宝山区", "嘉定区", "金山区", "松江区", "青浦区",
                  "奉贤区", "崇明区", "临港新片区"]

# 详情页标题抽取失败时常见的侧栏/导航文字
GENERIC_TITLES = {"相关文章", "正文", "通知公告", "首页", "信息公开", "相关附件",
                  "相关信息", "打印", "关闭", "分享"}


def page_id(url):
    return hashlib.md5(url.encode()).hexdigest()[:16]


def load_details():
    out = {}
    for p in glob.glob(os.path.join(DET, "*.json")):
        if os.path.basename(p).startswith("_"):
            continue
        try:
            d = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
        out[d["url"]] = d
    return out


def load_json(path, default):
    if os.path.exists(path):
        try:
            return json.load(open(path, encoding="utf-8"))
        except Exception:
            return default
    return default


def keywords_for(title, category):
    kws = set()
    for k in ["高新技术企业", "专精特新", "创新型中小企业", "科技型中小企业", "科技小巨人",
              "创新资金", "科技创新券", "研发费用", "加计扣除", "科技金融", "孵化器",
              "众创空间", "重点实验室", "成果转化", "知识产权", "科学技术奖", "科普",
              "科技计划", "专项资金", "人才", "贴息", "后补助", "数字化转型", "技术改造"]:
        if k in title:
            kws.add(k)
    if category and category != "其他科技政策":
        kws.add(category)
    return sorted(kws)


URL_DATE = re.compile(r'/(20\d{2})(\d{2})(\d{2})/')
DATE_OK = re.compile(r'^\d{4}-\d{2}-\d{2}$')
TODAY = datetime.date.today().isoformat()
# 允许的"未来"余量：0 天。发布日期不可能晚于今天。
# （采集时常把"申报截止日期/有效期至"误当成发布日期，如 2026年12月31日。）


def sane_date(pd, url=""):
    """发布日期兜底校正：晚于今天的一律不采信。

    优先用 URL 里的 /YYYYMMDD/；再不行就退回今天。返回 (日期, 是否被纠正)。
    """
    pd = (pd or "").strip()
    if DATE_OK.match(pd) and pd <= TODAY:
        return pd, False
    m = URL_DATE.search(url or "")
    if m:
        y, mo, d = m.groups()
        cand = f"{y}-{mo}-{d}"
        if DATE_OK.match(cand) and cand <= TODAY:
            return cand, True
    return TODAY, True
# 区级采集里混进来的非政策类内容
DIST_NOISE = ["视频｜", "视频|", "擂台赛", "活动举行", "文艺", "招聘"]


def clean_district_date(r):
    """补全缺失/异常的发布日期：优先用 URL 里的 /YYYYMMDD/。"""
    pd = (r.get("publishDate") or "").strip()
    if DATE_OK.match(pd):
        return pd
    m = URL_DATE.search(r.get("url", ""))
    if m:
        y, mo, d = m.groups()
        if 2015 <= int(y) <= 2030 and 1 <= int(mo) <= 12 and 1 <= int(d) <= 31:
            return f"{y}-{mo}-{d}"
    return ""


def load_district():
    """合并区级采集结果（data/district/district_*.json）。

    同时做三件清洗：
      1. 日期异常时从 URL 的 /YYYYMMDD/ 补全；
      2. 丢掉补不出日期的条目；
      3. 丢掉 2015 年前的老文与视频/活动类非政策内容。
    """
    out, dropped = [], {"noDate": 0, "tooOld": 0, "noise": 0, "future": 0}
    for p in sorted(glob.glob(os.path.join(DATA, "district", "district_*.json"))):
        try:
            arr = json.load(open(p, encoding="utf-8"))
        except Exception as e:
            print("  ! district parse fail", p, e)
            continue
        if isinstance(arr, dict):
            arr = arr.get("items", arr.get("records", []))
        for r in arr:
            if not isinstance(r, dict) or not r.get("url") or not r.get("title"):
                continue
            title = r["title"]
            if any(k in title for k in DIST_NOISE):
                dropped["noise"] += 1
                continue
            pd = clean_district_date(r)
            if not pd:
                dropped["noDate"] += 1
                continue
            pd2, fixed = sane_date(pd, r.get("url", ""))
            if fixed:
                dropped["future"] = dropped.get("future", 0) + 1
                print(f"    ! 日期越界已纠正：{pd} -> {pd2}  {title[:44]}")
                pd = pd2
            if int(pd[:4]) < 2015:
                dropped["tooOld"] += 1
                continue
            r = dict(r)
            r["publishDate"] = pd
            out.append(r)
    if any(dropped.values()):
        print(f"  区级清洗：丢弃 无日期 {dropped['noDate']} / 2015年前 {dropped['tooOld']} "
              f"/ 非政策 {dropped['noise']}；纠正未来日期 {dropped['future']}")
    return out



def main():
    cands = load_json(os.path.join(DATA, "candidates_tech.json"), [])
    details = load_details()
    extract = load_json(os.path.join(DATA, "extracted.json"), {})
    district = load_district()
    print(f"candidates={len(cands)} details={len(details)} extracted={len(extract)} district={len(district)}")

    policies = []
    miss_detail = 0
    for c in cands:
        url = c["url"]
        d = details.get(url)
        if not d:
            miss_detail += 1
        ex = extract.get(url, {})
        title = (d or {}).get("title") or c["title"]
        title = re.sub(r'\s+', ' ', title).strip()
        # 详情页标题抽取失败时（侧栏文字等），回退到列表页标题
        if len(title) < 8 or title in GENERIC_TITLES:
            title = re.sub(r'\s+', ' ', c["title"]).strip()
        docno = (d or {}).get("docNo", "") or ""
        issuer = (d or {}).get("issuer", "") or ""
        pdfs = (d or {}).get("pdfUrls", []) or []
        atts = (d or {}).get("attachments", []) or []
        # 层级只由数据来源决定：市科委/市经信委一律市级，避免把市级文件误标区级
        # 注意：不要复用 district 这个名字，它是区级记录列表
        pubdate, _fixed = sane_date(c["publishDate"], url)
        rec = {
            "id": page_id(url),
            "title": title,
            "docNo": docno,
            "issuer": issuer,
            "publishDate": pubdate,
            "year": pubdate[:4],
            "category": c["category"],
            "noticeType": c["noticeType"],
            "level": "市级",
            "district": "",
            "url": url,
            "pdfUrls": pdfs,
            "attachments": [a for a in atts if a["url"] not in pdfs][:20],
            "source": c["source"],
            "sourceName": SOURCE_NAME.get(c["source"], c["source"]),
            "sourceShort": SOURCE_SHORT.get(c["source"], c["source"]),
            "channel": c.get("channel", ""),
            "summary": ex.get("summary", ""),
            "conditions": ex.get("conditions", []),
            "benefits": ex.get("benefits", []),
            "materials": ex.get("materials", []),
            "timeline": ex.get("timeline", []),
            "timeHints": ex.get("timeHints", []),
            "moneyHints": ex.get("moneyHints", []),
            "keywords": keywords_for(title, c["category"]),
            "textChars": (d or {}).get("textLen", 0),
            "depth": "full" if ex.get("hasRichInfo") else "basic",
        }
        blob = title + " " + " ".join([docno, c["category"], c["noticeType"]])
        rec["isFunding"] = (c["noticeType"] == "领补贴通知") or any(k in blob for k in FUNDING_KW)
        policies.append(rec)

    policies.sort(key=lambda x: (x["publishDate"], x["title"]), reverse=True)

    # ---- 合并区级记录 ----
    seen_urls = {p["url"].split("#")[0].rstrip("/") for p in policies}
    added = 0
    for r in district:
        u = r["url"].split("#")[0].rstrip("/")
        if u in seen_urls:
            continue
        seen_urls.add(u)
        title = re.sub(r'\s+', ' ', r["title"]).strip()
        dist = r.get("district", "") or next(
            (x for x in DISTRICT_NAMES if x in title or x in (r.get("issuer") or "")), "")
        # 区级记录也尽量用抓到的详情页补全文号/单位/PDF/抽取字段
        dd = details.get(r["url"]) or {}
        dx = extract.get(r["url"]) or {}
        sub_docno = (r.get("docNo") or "").strip()
        sub_issuer = (r.get("issuer") or "").strip()
        sub_pdfs = list(r.get("pdfUrls") or [])
        det_pdfs = list(dd.get("pdfUrls") or [])
        pdfs = list(dict.fromkeys(sub_pdfs + det_pdfs))
        conds = list(r.get("conditions") or []) or list(dx.get("conditions") or [])
        bens = list(r.get("benefits") or []) or list(dx.get("benefits") or [])
        rec = {
            "id": page_id(r["url"]),
            "title": title,
            "docNo": sub_docno or (dd.get("docNo") or ""),
            "issuer": sub_issuer or (dd.get("issuer") or "")
                      or (dist + "科技/经济主管部门" if dist else "区级主管部门"),
            "publishDate": r.get("publishDate", "") or "",
            "year": (r.get("publishDate", "") or "0000")[:4],
            "category": resolve_category(title, r.get("category")),
            "noticeType": r.get("noticeType", "其他"),
            "level": "区级" if dist else "市级",
            "district": dist,
            "url": r["url"],
            "pdfUrls": pdfs,
            "attachments": [a for a in (dd.get("attachments") or [])
                            if a.get("url") not in pdfs][:20],
            "source": "district",
            "sourceName": (dist + "人民政府/科委" if dist
                           else (r.get("issuer") or "市级主管部门")),
            "sourceShort": dist or "市级",
            "channel": "区级政策",
            "summary": (bens[0][:180] if bens else (dd.get("title") and dx.get("summary") or "")),
            "conditions": conds,
            "benefits": bens,
            "materials": list(r.get("materials") or []) or list(dx.get("materials") or []),
            "timeline": list(dx.get("timeline") or []),
            "timeHints": list(dx.get("timeHints") or []),
            "moneyHints": re.findall(r'[0-9]+(?:\.[0-9]+)?\s*(?:万元|亿元|元)',
                                     " ".join(bens) + " ".join(dx.get("moneyHints") or []))[:8],
            "keywords": keywords_for(title, r.get("category", "")),
            "textChars": dd.get("textLen", 0),
            "depth": "full" if (conds or bens) else "basic",
        }
        blob = title + " " + rec["docNo"] + " " + rec["category"] + " " + rec["noticeType"]
        rec["isFunding"] = (rec["noticeType"] == "领补贴通知") or any(k in blob for k in FUNDING_KW)
        policies.append(rec)
        added += 1
    if added:
        policies.sort(key=lambda x: (x["publishDate"], x["title"]), reverse=True)
        print(f"并入区级记录 {added} 条")

    # ---- 合并链接验活结果 ----
    lc = load_json(os.path.join(DATA, "linkcheck.json"), {})
    dead = {d["url"] for d in lc.get("dead", [])}
    unver = {d["url"] for d in lc.get("unverified", [])}
    if dead:
        print(f"链接验活：{len(dead)} 个确认失效链接将标记")
    if unver:
        print(f"链接验活：{len(unver)} 个因限流/超时本轮无法核实（不标红）")
    for p in policies:
        p["linkOk"] = p["url"] not in dead
        p["linkNote"] = "unverified" if p["url"] in unver else ""
        p["pdfOk"] = (not p["pdfUrls"]) or (p["pdfUrls"][0] not in dead)

    guides = []
    for p in sorted(glob.glob(os.path.join(GUIDES, "*.json"))):
        try:
            g = json.load(open(p, encoding="utf-8"))
        except Exception as e:
            print("  ! guide parse fail", p, e)
            continue
        if isinstance(g, dict):
            g = g.get("guides", [g])
        guides.extend(g)
    # 去重（按 category）
    seen, g2 = set(), []
    for g in guides:
        if not isinstance(g, dict) or not g.get("category"):
            continue
        if g["category"] in seen:
            continue
        seen.add(g["category"])
        # 关联到本站政策记录的检索词：类别名 + 别名
        terms = [g["category"]] + [a for a in (g.get("alias") or []) if len(a) >= 3]
        g["matchTerms"] = list(dict.fromkeys(terms))
        g2.append(g)
    guides = g2

    meta = {
        "generatedAt": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "total": len(policies),
        "years": sorted({p["year"] for p in policies}),
        "categories": sorted({p["category"] for p in policies}),
        "noticeTypes": sorted({p["noticeType"] for p in policies}),
        "sources": sorted({p["sourceName"] for p in policies}),
        "deepCount": sum(1 for p in policies if p["depth"] == "full"),
        "pdfCount": sum(1 for p in policies if p["pdfUrls"]),
        "docNoCount": sum(1 for p in policies if p["docNo"]),
        "missingDetail": miss_detail,
    }
    payload = {"meta": meta, "policies": policies, "guides": guides}

    os.makedirs(DATA, exist_ok=True)
    with open(os.path.join(DATA, "policies.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    with open(os.path.join(DATA, "policies.js"), "w", encoding="utf-8") as f:
        f.write("/* 自动生成，请勿手改。源数据见 policies.json */\n")
        f.write("window.__POLICY_DATA__ = ")
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
        f.write(";\n")

    print("meta:", json.dumps(meta, ensure_ascii=False))
    print("guides:", len(guides), [g["category"] for g in guides])
    print("->", os.path.join(DATA, "policies.json"))


if __name__ == "__main__":
    main()
