import json,os,re,subprocess,time,sys
UA=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36")
def curl(url,timeout=45,retries=5):
    for i in range(retries):
        try:
            p=subprocess.run(["curl","-sS","-L","--compressed","-m",str(timeout),"-H",f"User-Agent: {UA}",url],capture_output=True,timeout=timeout+15)
            if p.stdout:
                for enc in ("utf-8","gb18030"):
                    try: return p.stdout.decode(enc)
                    except UnicodeDecodeError: continue
                return p.stdout.decode("utf-8","replace")
        except Exception: pass
        time.sleep(2.0*(i+1))
    return ""
A_RE=re.compile(r'<a\s[^>]*href="([^"]+)"[^>]*>(.*?)</a>',re.S|re.I)
def strip_tags(s):
    s=re.sub(r"<[^>]+>","",s).replace("&nbsp;"," ").replace("&amp;","&")
    return re.sub(r"\s+"," ",s).strip()
pat=re.compile(r"/kw/tzgg/\d{8}/[0-9a-zA-Z\-]+\.html")
res=[]
for i in range(1,63):
    u="https://www.fengxian.gov.cn/kw/tzgg/index.html" if i==1 else f"https://www.fengxian.gov.cn/kw/tzgg/index_{i}.html"
    h=curl(u)
    n=0
    if h:
        for m in A_RE.finditer(h):
            href,inner=m.group(1),m.group(2)
            if not pat.search(href): continue
            t=strip_tags(inner)
            if len(t)<6:
                tm=re.search(r'title="([^"]+)"',m.group(0))
                if tm: t=tm.group(1).strip()
            if len(t)<6: continue
            res.append({"title":t,"url":"https://www.fengxian.gov.cn"+href,"district":"奉贤区","source":"奉贤科委-通知公告","page":i})
            n+=1
    print(f"p{i}: {n}",file=sys.stderr)
    time.sleep(0.5)
seen=set();out=[]
for x in res:
    if x["url"] in seen: continue
    seen.add(x["url"]);out.append(x)
json.dump(out,open("data/raw_district/fx_lists.json","w"),ensure_ascii=False,indent=1)
print("FX total",len(out),file=sys.stderr)
