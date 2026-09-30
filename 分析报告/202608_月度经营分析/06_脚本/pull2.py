# -*- coding: utf-8 -*-
r"""数据补拉v2:正确sheet名+鲁棒列映射"""
import json
import time
import pythoncom
import pywintypes
import win32com.client as win32

BK = r"E:\3-其他资料\数据分析\月度分析模板_8月报告副本.xlsx"

def with_retry(fn, *a, **k):
    last = None
    for i in range(12):
        try:
            return fn(*a, **k)
        except pywintypes.com_error as e:
            if e.hresult in (-2147418111, -2147417846) and i < 11:
                last = e
                time.sleep(1.5)
                continue
            raise
    raise last

def J(v):
    return json.dumps(v, ensure_ascii=False, default=str)

res = {}
pythoncom.CoInitialize()
xl = None
try:
    xl = win32.DispatchEx("Excel.Application")
    xl.Visible = False
    xl.DisplayAlerts = False
    with_retry(lambda: xl.Workbooks.Open(BK, ReadOnly=True))

    # ---- D-镜像 ----
    ws = with_retry(lambda: xl.Worksheets("D-镜像"))
    nr = with_retry(lambda: ws.UsedRange.Rows.Count)
    nc = with_retry(lambda: ws.UsedRange.Columns.Count)
    hdr_raw = with_retry(lambda: ws.Range(ws.Cells(1, 1), ws.Cells(1, nc)).Value)[0]
    hdr = [str(h) if h is not None else "" for h in hdr_raw]
    res["镜像列头"] = hdr
    res["镜像行数"] = nr

    def find_col(*kws):
        for i, h in enumerate(hdr):
            if all(k in h for k in kws):
                return i
        return None

    ci = {
        "年月": find_col("年月") or find_col("月"),
        "客户": find_col("客户"),
        "品类": find_col("品类"),
        "产品线": find_col("产品线"),
        "收入": find_col("收入"),
        "利润": find_col("利润"),
        "新品": find_col("新品"),
    }
    res["列定位"] = {k: (hdr[v] if v is not None else None) for k, v in ci.items()}
    missing = [k for k, v in ci.items() if v is None]
    if missing:
        res["ERROR"] = f"缺列: {missing}, 列头={hdr}"
    else:
        need = sorted(set(ci.values()))
        # 分块读取
        cols = {}
        for c in need:
            vals = []
            CH = 60000
            for start in range(2, nr + 1, CH):
                end = min(start + CH - 1, nr)
                v = with_retry(lambda: ws.Range(ws.Cells(start, c + 1), ws.Cells(end, c + 1)).Value)
                vals.extend([x[0] if isinstance(x, tuple) else x for x in v])
            cols[c] = vals
        res["读取行数"] = len(cols[need[0]])

        def col(k):
            return cols[ci[k]]

        ym = col("年月"); cust = col("客户"); cat = col("品类"); pl = col("产品线")
        rev = col("收入"); pft = col("利润"); newp = col("新品")
        ym_s = [str(x) if x is not None else "" for x in ym]

        def ytd26(i):
            return ym_s[i].startswith("2026") and ym_s[i][5:7] in ("01","02","03","04","05","06","07","08")

        def y25(i):
            return ym_s[i].startswith("2025")

        def m08_26(i):
            return ym_s[i].startswith("2026-08")

        targets = ["石头", "海康威视", "追觅", "兆驰", "共进", "安克创新", "中兴康讯"]
        stat = {t: {"r26": 0.0, "p26": 0.0, "r25": 0.0, "p25": 0.0, "cats": {}} for t in targets}
        dim08 = {}
        for i in range(len(ym_s)):
            c = str(cust[i] or "")
            r_ = rev[i] or 0.0
            p = pft[i] or 0.0
            hit = None
            for t in targets:
                if t in c:
                    hit = t
                    break
            if hit:
                if ytd26(i):
                    stat[hit]["r26"] += r_; stat[hit]["p26"] += p
                    if hit in ("追觅", "兆驰", "共进"):
                        cc = str(cat[i] or "?")
                        d = stat[hit]["cats"].setdefault(cc, [0.0, 0.0])
                        d[0] += r_; d[1] += p
                elif y25(i):
                    stat[hit]["r25"] += r_; stat[hit]["p25"] += p
            if m08_26(i):
                nm = str(cat[i] or "") + "|" + str(pl[i] or "")
                if ("音频" in nm) or ("电脑" in nm) or ("计算" in nm) or ("充电与控制" in nm) or ("通用电源" in nm):
                    d = dim08.setdefault(nm, [0.0, 0.0])
                    d[0] += r_; d[1] += p
        cust_out = {}
        for t in targets:
            s = stat[t]
            cust_out[t] = {
                "YTD26收入万": round(s["r26"] / 1e4, 1), "YTD26利润万": round(s["p26"] / 1e4, 1),
                "YTD26毛利率": round(s["p26"] / s["r26"], 4) if s["r26"] else None,
                "去年YTD收入万": round(s["r25"] / 1e4, 1), "去年YTD利润万": round(s["p25"] / 1e4, 1),
                "去年YTD毛利率": round(s["p25"] / s["r25"], 4) if s["r25"] else None,
                "收入同比": round(s["r26"] / s["r25"] - 1, 4) if s["r25"] else None,
                "利润同比万": round((s["p26"] - s["p25"]) / 1e4, 1),
            }
        res["目标客户YTD对比"] = cust_out
        cat_out = {}
        for t in ("追觅", "兆驰", "共进"):
            d = stat[t]["cats"]
            tot = sum(v[0] for v in d.values())
            top = sorted(d.items(), key=lambda kv: -kv[1][0])[:3]
            cat_out[t] = [{"品类": k, "收入万": round(v[0] / 1e4, 1), "利润万": round(v[1] / 1e4, 1),
                           "占比": round(v[0] / tot, 3) if tot else None,
                           "毛利率": round(v[1] / v[0], 4) if v[0] else None} for k, v in top]
        res["客户品类TOP3_2026YTD"] = cat_out
        res["音频电脑充电_8月品类|产品线"] = {k: {"收入万": round(v[0] / 1e4, 1),
                                              "毛利率": round(v[1] / v[0], 4) if v[0] else None}
                                         for k, v in dim08.items()}

    # ---- 其他sheet原文 ----
    for sname in ("10-毛利桥", "增加及流失", "R-报告补充", "11-SKU变化"):
        try:
            w2 = with_retry(lambda: xl.Worksheets(sname))
            n2r = with_retry(lambda: w2.UsedRange.Rows.Count)
            n2c = min(with_retry(lambda: w2.UsedRange.Columns.Count), 14)
            lim = min(n2r, 45 if sname == "10-毛利桥" else (30 if sname == "增加及流失" else (140 if sname == "R-报告补充" else 30)))
            body = with_retry(lambda: w2.Range(w2.Cells(1, 1), w2.Cells(lim, n2c)).Value)
            res[sname] = [[("" if c is None else str(c)) for c in r] for r in body]
            res[sname + "_行数"] = n2r
        except Exception as e:
            res[sname] = f"ERR {e}"

    with_retry(lambda: xl.Workbooks.Close())
finally:
    if xl is not None:
        try:
            xl.Quit()
        except Exception:
            pass
    pythoncom.CoUninitialize()

json.dump(res, open(r"C:\Users\910373\AppData\Local\Temp\opencode\build\pull2.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("PULL2_DONE")
