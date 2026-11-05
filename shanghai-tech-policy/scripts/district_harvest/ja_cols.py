import json,re,subprocess,sys,time
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
cols=["jszx-gqwj3","kjcx-gqwj3","tsqygs-zjfcqj3"]
out=[]
for c in cols:
    for n in (1,2):
        u=f"https://www.shanghai.gov.cn/{c}/index.html" if n==1 else f"https://www.shanghai.gov.cn/{c}/index_{n}.html"
        h=curl(u)
        if not h or len(h)<1500: continue
        cnt=0
        for m in re.finditer(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>',h,re.S|re.I):
            hr,inn=m.group(1),m.group(2)
            if not re.search(rf'/{c}/\d{{8}}/[0-9a-f]+(_aaf)?\.html',hr): continue
            t=strip(inn)
            if len(t)<8:
                tm=re.search(r'title="([^"]+)"',m.group(0))
                if tm: t=tm.group(1).strip()
            if len(t)<8: continue
            url=hr if hr.startswith("http") else "https://www.shanghai.gov.cn"+hr
            out.append({"district":"静安区","source":"市政府-静安栏目","title":t,"url":url,"col":c})
            cnt+=1
        print(c,n,cnt,file=sys.stderr)
        time.sleep(0.3)
seen=set();r=[]
for x in out:
    if x["url"] in seen: continue
    seen.add(x["url"]);r.append(x)
json.dump(r,open("data/raw_district/ja_cols.json","w"),ensure_ascii=False,indent=1)
print("JA cols items",len(r),file=sys.stderr)
for x in r:
    if re.search("技术中心|专利|知识产权|攻关|揭榜|冠军|专项|奖励|申报",x["title"]):
        print(x["title"][:80])
