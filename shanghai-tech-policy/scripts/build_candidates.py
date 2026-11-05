#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把多源列表合并、去重、分类，筛出科技类政策候选集。"""
import json, glob, re, os, sys, collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw")

# ---------- 政策类型（category）----------
CATEGORY_RULES = [
    # 「专精特新小巨人」必须排在「专精特新中小企业」和「科技小巨人」之前，
    # 否则会被前两者先命中（两者是完全不同的资质：小巨人是工信部国家级）。
    ("专精特新小巨人", ["专精特新“小巨人”", '专精特新"小巨人"', "专精特新小巨人",
                        "小巨人”企业", '小巨人"企业']),
    ("高新技术企业", ["高新技术企业", "高企认定", "高企更名", "高企"]),
    ("专精特新中小企业", ["专精特新"]),
    ("创新型中小企业", ["创新型中小企业"]),
    ("科技型中小企业", ["科技型中小企业", "科技中小企业", "科技型中小"]),
    ("科技小巨人", ["科技小巨人"]),
    ("制造业单项冠军", ["单项冠军", "制造业冠军", "冠军企业", "制造业单项"]),
    ("企业技术中心", ["企业技术中心", "技术中心认定", "市级技术中心", "区级技术中心"]),
    ("张江科学城", ["张江科学城", "科学城"]),
    ("张江示范区", ["张江国家自主创新示范区", "张江高新技术产业开发区", "张江高新区",
                    "张江示范区", "张江园", "张江专项资金", "张江"]),
    ("服务业引导资金", ["服务业引导资金", "服务业发展引导资金", "服务业发展引导", "引导资金"]),
    ("文化创意资金", ["文化创意", "文创", "文创产业"]),
    ("技术改造", ["技术先进性改造", "技术改造", "设备更新", "智能化改造", "生产线改造",
                  "技改", "工业投资"]),
    ("创·在上海", ["创·在上海", "创•在上海", "创在上海", "Startup in Shanghai",
                   "创在上海国际创新创业大赛"]),
    ("创新创业大赛", ["创新创业大赛", "创业大赛", "创客中国", "创客上海", "大赛", "赛事"]),
    ("产学研合作", ["产学研", "协同创新", "联合创新"]),
    ("技术创新资金", ["创新资金", "技术创新资金"]),
    ("科技创新券", ["科技创新券"]),
    ("专利试点示范", ["专利试点", "知识产权试点", "专利示范", "知识产权示范",
                      "试点示范单位", "专利工作试点", "知识产权示范企业"]),
    ("揭榜挂帅", ["揭榜挂帅", "揭榜", "发榜", "英雄帖"]),
    ("重大产业攻关", ["产业攻关", "重大攻关", "关键核心技术攻关", "攻关项目", "攻关任务",
                      "技术攻关", "联合攻关", "攻关计划", "攻关专项"]),
    ("研发费用与加计扣除", ["研发费用", "加计扣除", "研发准备金", "基础研究合同登记"]),
    ("科技金融", ["科技金融", "保费补贴", "沪科积分贷", "科技信贷", "融资担保", "投贷联动", "科技保险"]),
    ("科技人才", ["浦江人才", "启明星", "学术带头人", "科技人才", "青年科技", "人才计划", "外国专家"]),
    ("创新载体与孵化器", ["孵化器", "众创空间", "创新创业载体", "科技园区", "高新区", "中试基地", "概念验证"]),
    ("研发机构与实验室", ["重点实验室", "工程技术研究中心", "技术创新中心", "新型研发机构", "研发机构", "技术创新平台", "联合实验室"]),
    ("科技成果转化", ["成果转化", "技术转移", "技术交易", "产学研"]),
    ("知识产权", ["知识产权", "专利", "商标", "著作权"]),
    ("科技奖励", ["科学技术奖", "科技奖", "科技进步奖", "科技创新奖"]),
    ("科技计划项目", ["科技计划", "颠覆性技术", "软科学", "自然科学基金", "重点项目", "专项项目"]),
    ("专项资金与补贴", ["专项资金", "资金", "补贴", "资助", "奖励", "经费", "后补助", "配套"]),
    ("科普与科学传播", ["科普", "科学传播", "科普基地"]),
    ("外国专家与国际化", ["国际科技合作", "外资研发中心", "外籍", "国际联合"]),
]

# ---------- 通知类型（noticeType）----------
def classify_notice(title):
    t = title
    # 1) 红头文件/规范性文件
    if any(k in t for k in ["管理办法", "实施细则", "若干措施", "工作指引", "暂行办法", "实施意见",
                            "规范性文件", "印发《", "关于印发", "操作指引", "认定办法", "奖励办法",
                            "补助办法", "资助办法", "管理规定", "办法（试行）"]):
        return "政策红头文件"
    # 2) 资金下达/补贴兑现（"领补贴"）
    if any(k in t for k in ["下达", "拨付", "兑现", "发放", "资金安排", "经费安排", "拨付经费",
                            "奖励资金", "补贴经费", "补助经费", "资助经费", "贴息", "保费补贴",
                            "财政奖励", "给予", "资金支持", "后补助"]):
        if not any(k in t for k in ["公示", "申报", "征集", "公布名单"]):
            return "领补贴通知"
    # 3) 公示
    if any(k in t for k in ["公示", "拟认定", "拟入库", "拟支持", "拟立项", "拟更名", "拟通过", "拟公布", "拟推荐"]):
        return "公示通知"
    # 4) 立项与评价
    if any(k in t for k in ["立项", "综合绩效评价", "绩效评价", "评估结果", "评价结果", "验收"]):
        return "立项与评价通知"
    # 5) 政策解读
    if any(k in t for k in ["解读", "一图读懂", "政策问答", "图解"]):
        return "政策解读"
    # 6) 申报
    if any(k in t for k in ["申报", "组织开展", "征集", "遴选", "推荐", "评价工作", "认定管理",
                            "认定工作", "培育工作", "复核工作", "报送", "摸底", "备案工作",
                            "申请", "自评"]):
        return "申报通知"
    # 7) 公告/名单
    if any(k in t for k in ["公告", "公布", "名单", "结果"]):
        return "名单公布"
    if "通知" in t:
        return "申报通知"
    return "其他"


def classify_category(title):
    for name, kws in CATEGORY_RULES:
        if any(k in title for k in kws):
            return name
    return "其他科技政策"


# 政策类型优先级：越靠前越"核心"，用于一条标题命中多类时定主类
CATEGORY_PRIORITY = [n for n, _ in CATEGORY_RULES]

TECH_STRONG = ["高新技术企业", "专精特新", "创新型中小企业", "科技型中小企业", "科技小巨人",
               "创新资金", "科技创新券", "研发费用", "加计扣除", "科技", "技术", "研发",
               "创新", "科研", "知识产权", "专利", "孵化器", "众创空间", "成果转化",
               "科技奖", "科普", "实验室", "中试", "概念验证", "科技金融", "沪科积分",
               # 用户点名补充的五类
               "企业技术中心", "技术中心", "专利试点", "知识产权试点", "专利示范",
               "揭榜挂帅", "揭榜", "发榜", "产业攻关", "重大攻关", "技术攻关",
               "联合攻关", "攻关", "单项冠军", "制造业冠军", "冠军企业",
               "制造业单项", "先进制造业",
               # 用户第二次点名补充的八类
               "小巨人", "技术改造", "技改", "设备更新", "服务业", "引导资金",
               "文创", "文化创意", "创新创业大赛", "创·在上海", "创在上海",
               "张江", "科学城", "产学研", "协同创新", "工业投资"]

NOISE = ["中心组", "党建", "党风廉政", "巡视", "干部", "人事任免", "招聘", "事业单位",
         "理论学习", "党组", "党史", "工会", "团委", "妇女", "老干部", "安全生产月",
         "保密", "节能宣传", "法制宣传", "垃圾分类", "无偿献血", "体育", "文艺"]

# 外省/外地区政策：标题出现这些地名且不含「上海」时排除
OTHER_REGIONS = ["北京", "天津", "河北", "山西", "内蒙古", "辽宁", "吉林", "黑龙江",
                 "江苏", "浙江", "安徽", "福建", "江西", "山东", "河南", "湖北", "湖南",
                 "广东", "广西", "海南", "重庆", "四川", "贵州", "云南", "西藏", "陕西",
                 "甘肃", "青海", "宁夏", "新疆", "香港", "澳门", "台湾",
                 "苏州", "杭州", "南京", "宁波", "深圳", "广州", "成都", "武汉", "合肥"]


def is_tech(title):
    if any(k in title for k in NOISE):
        return False
    if "上海" not in title and any(k in title for k in OTHER_REGIONS):
        return False
    return any(k in title for k in TECH_STRONG)


def norm_url(u):
    u = u.split("#")[0].rstrip("/")
    return u


def main():
    years = set(sys.argv[1].split(",")) if len(sys.argv) > 1 else set()
    records, seen = [], set()
    stats = collections.Counter()
    for path in sorted(glob.glob(os.path.join(RAW, "list_*.json"))):
        d = json.load(open(path, encoding="utf-8"))
        src = d.get("source", "?")
        for it in d.get("items", []):
            u = norm_url(it["url"])
            if u in seen:
                continue
            seen.add(u)
            stats[src] += 1
            title = it["title"]
            date = it["date"]
            y = date[:4]
            if years and y not in years:
                continue
            records.append({
                "title": title,
                "publishDate": date,
                "year": y,
                "url": it["url"],
                "source": src,
                "channel": it.get("channel", ""),
                "category": classify_category(title),
                "noticeType": classify_notice(title),
                "techRelevant": is_tech(title),
            })
    # 主类修正：命中多个类型时，取优先级最高者
    for r in records:
        hits = [n for n, kws in CATEGORY_RULES if any(k in r["title"] for k in kws)]
        if hits:
            hits.sort(key=lambda n: CATEGORY_PRIORITY.index(n))
            r["category"] = hits[0]
    out_all = os.path.join(ROOT, "data", "candidates_all.json")
    out_tech = os.path.join(ROOT, "data", "candidates_tech.json")
    with open(out_all, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=1)
    tech = [r for r in records if r["techRelevant"]]
    with open(out_tech, "w", encoding="utf-8") as f:
        json.dump(tech, f, ensure_ascii=False, indent=1)
    print("per-source raw counts:", dict(stats))
    print("all unique:", len(records), "-> tech:", len(tech), "-> file", out_tech)
    print("by year:", sorted(collections.Counter(r["year"] for r in tech).items(), reverse=True))
    print("by category:", collections.Counter(r["category"] for r in tech).most_common())
    print("by noticeType:", collections.Counter(r["noticeType"] for r in tech).most_common())


if __name__ == "__main__":
    main()
