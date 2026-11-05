#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从详情页正文中规则化抽取：申报条件 / 政策好处 / 时间窗口 / 材料清单 / 摘要。"""
import json, os, re, sys, glob, hashlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DET = os.path.join(ROOT, "data", "details")
RAW = os.path.join(ROOT, "data", "raw")

HEAD_RE = re.compile(r'^\s*(?:[（(]?[一二三四五六七八九十]{1,3}[）)、.]|[0-9]{1,2}[、.])\s*(.{2,40})$')

COND_KEYS = ["申报条件", "申请条件", "条件标准", "认定条件", "基本条件", "申报要求", "申报对象",
             "支持对象", "申报范围", "申请对象", "资格条件", "评价标准", "认定标准", "条件"]
BEN_KEYS = ["政策好处", "支持方式", "支持标准", "扶持", "资助", "奖励", "补助", "补贴", "优惠",
            "税收", "减免", "经费支持", "资金支持", "支持内容", "兑付", "拨付标准", "资助标准"]
TIME_KEYS = ["申报时间", "申请时间", "受理时间", "时间安排", "截止", "受理期限", "申报期限",
             "办理时间", "报送时间", "填报时间", "进度安排", "工作安排"]
MAT_KEYS = ["申报材料", "申请材料", "需提交", "提交材料", "材料清单", "报送材料", "申报材料清单",
            "佐证材料", "附件材料", "应提交"]

MONEY_RE = re.compile(r'(?:不超过|最高|不超过人民币|给予|一次性|按)?[^，。；\n]{0,24}?'
                      r'([0-9]+(?:\.[0-9]+)?)\s*(万元|亿元|元)')
TAX_RE = re.compile(r'(减按\s*[0-9]+\s*%|按\s*[0-9]+\s*%|加计扣除|免征|减征|税前扣除|税率)')
DATE_RE = re.compile(r'(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日')
DATE_CN = re.compile(r'(20\d{2})\s*年\s*(\d{1,2})\s*月(?![0-9])')
HALF_YEAR = re.compile(r'(20\d{2})\s*年\s*(上半年|下半年|年底|全年)')
QUARTER = re.compile(r'(20\d{2})\s*年\s*第([一二三四1234])季度')
CUTOFF = re.compile(r'[，,。；;]?\s*(?:于|在)?\s*([^，。；;\n]{0,24}?前)')


def norm_date(y, m, d):
    return f"{y}-{int(m):02d}-{int(d):02d}"


def split_sections(text):
    """按「一、xxx」这类小标题切段，返回 [(heading, body), ...]"""
    lines = text.split('\n')
    secs, cur_h, cur_b = [], "", []
    for l in lines:
        m = HEAD_RE.match(l)
        if m and len(l) <= 46:
            if cur_h or cur_b:
                secs.append((cur_h, '\n'.join(cur_b).strip()))
            cur_h, cur_b = m.group(1).strip(), []
        else:
            cur_b.append(l)
    if cur_h or cur_b:
        secs.append((cur_h, '\n'.join(cur_b).strip()))
    return secs


def sents(body):
    parts = re.split(r'[\n。；;]', body)
    return [p.strip(' 　•·-—') for p in parts if len(p.strip()) >= 6]


BEN_RE = re.compile(
    r'给予|支持|资助|奖励|补助|补贴|减免|免征|减征|减按|税率|加计扣除|拨付|贴息|后补助|'
    r'经费|最高|不超过|万元|亿元|免费|优惠|扣除|落户|优先|加分|一次性')
COND_RE = re.compile(
    r'应当|应|须|需|具有|不低于|不少于|成立|注册|满\s*\d|以上|符合|属于|具备|原则上|'
    r'条件|范围|对象|资格|要求|标准|年限|占比|人员|职工|收入|资产|未|遵守|从事')


def pick(sections, keys, limit=8, valid=None):
    out = []
    for h, b in sections:
        if any(k in h for k in keys):
            for s in sents(b):
                if valid and not valid(s):
                    continue
                if len(s) <= 300:
                    out.append(s)
                else:
                    out.append(s[:300] + '…')
                if len(out) >= limit * 2:
                    break
    # 去重、截断
    seen, res = set(), []
    for x in out:
        k = x[:24]
        if k in seen:
            continue
        seen.add(k)
        res.append(x)
        if len(res) >= limit:
            break
    return res


def valid_benefit(s):
    if not BEN_RE.search(s):
        return False
    # 纯门槛句（"不低于/不少于 X 万元"且无扶持动作）判为条件，不算好处
    if re.search(r'不低于|不少于', s) and not re.search(
            r'给予|支持|资助|奖励|补助|补贴|减免|免征|减按|税率|加计扣除|拨付|贴息|后补助|最高|不超过', s):
        return False
    return True


def valid_condition(s):
    return bool(COND_RE.search(s))


def time_hints(text, title):
    res = []
    for m in DATE_RE.finditer(text):
        res.append(norm_date(*m.groups()))
    for m in DATE_CN.finditer(text):
        res.append(f"{m.group(1)}-{int(m.group(2)):02d}")
    for m in HALF_YEAR.finditer(text):
        res.append(f"{m.group(1)} {m.group(2)}")
    for m in QUARTER.finditer(text):
        res.append(f"{m.group(1)} 第{m.group(2)}季度")
    ym = re.search(r'(20\d{2})\s*年\s*(\d{1,2})\s*月(?![\d])', title)
    return list(dict.fromkeys(res))[:10]


def money_hints(text):
    out = []
    for m in MONEY_RE.finditer(text):
        s = m.group(0).strip('，,。；; ')
        out.append(s)
    seen, res = set(), []
    for x in out:
        if x in seen:
            continue
        seen.add(x)
        res.append(x)
        if len(res) >= 8:
            break
    return res


def summarize(title, sections, text, n=110):
    for h, b in sections:
        if any(k in h for k in ["支持方式", "支持标准", "资助", "补助", "补贴", "政策", "背景", "依据", "总体"]):
            for s in sents(b):
                if len(s) >= 12:
                    return s[:n] + ('…' if len(s) > n else '')
    for l in text.split('\n'):
        if len(l) >= 20:
            return l[:n] + ('…' if len(l) > n else '')
    return title[:n]


def extract(d):
    text = d.get("text", "")
    title = d.get("title", "")
    sections = split_sections(text)
    conds = pick(sections, COND_KEYS, 8, valid_condition)
    if not conds:
        conds = []
    bens = pick(sections, BEN_KEYS, 8, valid_benefit)
    mats = pick(sections, MAT_KEYS, 10)
    tl = pick(sections, TIME_KEYS, 6)
    hints = time_hints(text, title)
    money = money_hints(text)
    if not bens and money:
        bens = [f"涉及金额：{'；'.join(money[:3])}"]
    if not bens:
        tax = TAX_RE.findall(text)
        if tax:
            bens = [f"税收优惠相关表述：{'、'.join(sorted(set(tax))[:5])}"]
    return {
        "conditions": conds,
        "benefits": bens,
        "materials": mats,
        "timeline": tl,
        "timeHints": hints,
        "moneyHints": money,
        "summary": summarize(title, sections, text),
        "sections": [h for h, _ in sections if h][:20],
        "hasRichInfo": bool(conds or bens or mats),
    }


def main():
    out = {}
    files = sorted(p for p in glob.glob(os.path.join(DET, "*.json"))
                   if not os.path.basename(p).startswith("_"))
    for p in files:
        try:
            d = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
        ex = extract(d)
        out[d["url"]] = ex
    dst = os.path.join(ROOT, "data", "extracted.json")
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    rich = sum(1 for v in out.values() if v["hasRichInfo"])
    print(f"extracted {len(out)} pages, rich={rich} -> {dst}")


if __name__ == "__main__":
    main()
