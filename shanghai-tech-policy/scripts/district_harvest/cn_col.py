import json,re,subprocess,time,sys
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36"
def curl(u,timeout=35,retries=3):
    for i in range(retries):
        try:
            p=subprocess.run(["curl","-sS","-L","--compressed","-m",str(timeout),"-H",f"User-Agent: {UA}",u],capture_output=True,timeout=timeout+15)
            if p.stdout: return p.stdout.decode("utf-8","replace")
        except Exception: pass
        time.sleep(1.2)
    return ""
def strip(s):
    s=re.sub(r"<[^>]+>","",s).replace("&nbsp;"," ").replace("&amp;","&")
    return re.sub(r"\s+"," ",s).strip()
def crawl(col,district,src,maxp=60):
    out=[];tot=None
    for i in range(1,maxp+1):
        u=f"https://www.shcn.gov.cn/{col}/" if i==1 else f"https://www.shcn.gov.cn/{col}/index_{i}.html"
        h=curl(u)
        if not h or len(h)<400:
            if i==1: return out,0
            break
        if tot is None:
            m=re.search(r'totalPage:\s*(\d+)',h)
            tot=int(m.group(1)) if m else maxp
        pat=re.compile(rf'/{col}/\d{{8}}/\d+\.html')
        n=0
        for m in re.finditer(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>',h,re.S|re.I):
            hr,inn=m.group(1),m.group(2)
            if not pat.search(hr): continue
            t=strip(inn)
            if len(t)<6:
                tm=re.search(r'title="([^"]+)"',m.group(0))
                if tm: t=tm.group(1).strip()
            if len(t)<6: continue
            out.append({"district":district,"source":src,"title":t,"url":"https://www.shcn.gov.cn"+hr,"col":col})
            n+=1
        if i>=tot: break
        time.sleep(0.3)
    seen=set();r=[]
    for x in out:
        if x["url"] in seen: continue
        seen.add(x["url"]);r.append(x)
    return r,tot
if __name__=="__main__":
    res=[]
    for col,src in [("col7431","长宁市场监管局/知识产权"),("col8342","长宁揭榜挂帅"),("col11010","长宁科委通知公告")]:
        r,t=crawl(col,"长宁区",src)
        print(col,"pages",t,"items",len(r),file=sys.stderr)
        res+=r
    json.dump(res,open("data/raw_district/cn_cols2.json","w"),ensure_ascii=False,indent=1)
    import re as _re
    for x in res:
        if _re.search("知识产权|专利|技术中心|揭榜|攻关|单项冠军",x["title"]): print(x["title"][:80])
