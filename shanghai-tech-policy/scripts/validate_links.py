#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""链接验活：检查 policies.json 中所有原文/PDF 链接的可访问性。"""
import json, os, sys, subprocess, collections
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_JSON = os.path.join(ROOT, "data", "linkcheck.json")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36"


def check(url, timeout=20, retries=2):
    """返回 (url, code, err, ssl_unverified)。
    政府站常因本机 CA 证书链不全会报 SSL 错，此时用 -k 复测；
    只要内容能取到就判为可访问，仅标记 ssl_unverified，不算失效。"""
    last = ("000", "no-response", False)
    for attempt in range(retries + 1):
        code, err, _insecure = _check_once(url, timeout if attempt == 0 else max(timeout, 35))
        if not err:
            return url, code, "", False
        last = (code, err, False)
        if _is_ssl_err(err):
            code2, err2, _ = _check_once(url, max(timeout, 35), insecure=True)
            if not err2:
                return url, code2, "", True
            last = (code2, err2, True)
    return url, last[0], last[1], last[2]


def _is_ssl_err(err):
    e = (err or "").lower()
    return "ssl" in e or "certificate" in e or "cert" in e


def classify(code, err):
    """把失败分为「确认失效」与「本轮无法核实」两类。

    404/410 视为确认失效（会写进 dead，页面标红）；
    403（限流/反爬）与超时视为无法核实（写进 unverified，页面不标红），
    避免把政府站的临时限流误判成死链。
    """
    if not err:
        return "ok"
    if code in ("404", "410"):
        return "dead"
    if code == "403" or "timeout" in err or code == "000":
        return "unverified"
    return "other"

    e = (err or "").lower()
    return "ssl" in e or "certificate" in e or "cert" in e


def _check_once(url, timeout, insecure=False):
    try:
        cmd = ["curl", "-sS", "-o", "/dev/null", "-L", "--compressed"]
        if insecure:
            cmd.append("-k")
        cmd += ["-m", str(timeout), "-H", f"User-Agent: {UA}",
                "-w", "%{http_code}", url]
        p = subprocess.run(cmd, capture_output=True, timeout=timeout + 10)
        code = p.stdout.decode().strip()
        serr = p.stderr.decode(errors="replace").strip()
        if not code:
            return "000", (serr or "no-response")[:160], insecure
        try:
            ci = int(code)
        except ValueError:
            return code, ("bad-code " + serr)[:160], insecure
        if 200 <= ci < 400:
            return code, "", insecure
        # 非 2xx/3xx：把 curl 的 stderr（含 SSL 证书错误）一并带回，供上层判断
        return code, (serr or "http-error")[:160], insecure
    except subprocess.TimeoutExpired:
        return "000", "timeout", insecure
    except Exception as e:
        return "000", str(e)[:120], insecure


def main():
    incremental = "--incremental" in sys.argv
    positional = [a for a in sys.argv[1:] if not a.startswith("--")]
    src = positional[0] if positional else os.path.join(ROOT, "data", "policies.json")
    payload = json.load(open(src, encoding="utf-8"))
    policies = payload["policies"] if isinstance(payload, dict) else payload
    urls = []
    for p in policies:
        urls.append(("page", p["url"], p.get("id")))
        for u in p.get("pdfUrls", []):
            urls.append(("pdf", u, p.get("id")))
    uniq = {}
    for kind, u, pid in urls:
        uniq.setdefault(u, {"kind": kind, "ids": []})["ids"].append(pid)

    # 增量模式：沿用上次结果，只测没测过的链接（每日更新时避免重测全部几千条）
    results, cached = {}, {}
    if incremental and os.path.exists(OUT_JSON):
        try:
            old = json.load(open(OUT_JSON, encoding="utf-8"))
            # 旧报告里按 url 存了结果，直接沿用
            cached = old.get("results", {})
        except Exception:
            cached = {}
        for u in list(uniq):
            if u in cached:
                results[u] = cached[u]
        print(f"增量模式：沿用上次结果 {len(results)} 条，只需新测 {len(uniq) - len(results)} 条",
              flush=True)
    todo = [u for u in uniq if u not in results]
    print(f"待验链接 {len(urls)} 个（去重 {len(uniq)}，本轮实际请求 {len(todo)}）", flush=True)

    done = 0
    with ThreadPoolExecutor(max_workers=12) as ex:
        futs = {ex.submit(check, u): u for u in todo}
        for f in as_completed(futs):
            u, code, err, sslv = f.result()
            results[u] = {"code": code, "err": err, "kind": uniq[u]["kind"],
                          "sslUnverified": sslv}
            done += 1
            if done % 200 == 0:
                print(f"  {done}/{len(todo)}", flush=True)

    cnt = collections.Counter(v["code"] for v in results.values())
    for u, v in results.items():
        v["verdict"] = classify(v["code"], v["err"])
    bad = {u: v for u, v in results.items() if v["verdict"] == "dead"}
    other = {u: v for u, v in results.items() if v["verdict"] == "other"}
    unver = {u: v for u, v in results.items() if v["verdict"] == "unverified"}
    ssl_only = {u: v for u, v in results.items() if v.get("sslUnverified")}
    ok_pages = sum(1 for p in policies
                   if results.get(p["url"], {}).get("err", "x") == "")
    ok_pdf = sum(1 for p in policies
                 if p.get("pdfUrls") and
                 results.get(p["pdfUrls"][0], {}).get("err", "x") == "")
    n_pdf = sum(1 for p in policies if p.get("pdfUrls"))
    out = {
        "checked": len(uniq), "total": len(urls),
        "byCode": dict(cnt),
        "okPages": ok_pages, "okPdf": ok_pdf, "pdfPolicies": n_pdf,
        "sslUnverified": sorted(ssl_only.keys()),
        "unverified": [{"url": u, "code": v["code"], "err": v["err"], "kind": v["kind"]}
                       for u, v in unver.items()],
        "other": [{"url": u, "code": v["code"], "err": v["err"], "kind": v["kind"]}
                  for u, v in other.items()],
        "dead": [{"url": u, "code": v["code"], "err": v["err"], "kind": v["kind"]}
                 for u, v in bad.items()],
        # per-url 明细：下次 --incremental 直接复用，不必重测
        "results": results,
    }
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"\n正文页可访问 {ok_pages}/{len(policies)}")
    print(f"含 PDF 的政策中，首个 PDF 可访问 {ok_pdf}/{n_pdf}")
    print("状态码分布:", dict(cnt))
    print(f"确认失效链接 {len(bad)} 个（404/410）-> data/linkcheck.json")
    if unver:
        hosts = collections.Counter(u.split("/")[2] for u in unver)
        print(f"本轮无法核实 {len(unver)} 个（限流/超时，不当死链）：{dict(hosts)}")
    if other:
        print(f"其他异常 {len(other)} 个")
    if ssl_only:
        print(f"（另有 {len(ssl_only)} 个链接因本机 CA 证书链不全需 -k 跳过校验才能访问，"
              f"已判为可访问并记录在 sslUnverified）")
    if bad:
        for u, v in list(bad.items())[:10]:
            print("  ", v["code"], v["kind"], u[:110])


if __name__ == "__main__":
    main()
