# -*- coding: utf-8 -*-
r"""四因子毛利桥重算+数据缺口补算(从D-镜像全量)
锚点验证: 量4+结构4 == 底表三因子量(同比383/环比-291); 价/成本/ΔGP 与底表一致
"""
import json
import time
import pythoncom
import pywintypes
import win32com.client as win32
from datetime import datetime, date

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

# 列号(1-based): 发货日期1 存货名称10 数量12 收入13 利润14 客户简称2 品类8 产品线6
COLS = {"发货日期": 1, "客户简称": 2, "产品线": 6, "品类": 8, "存货名称": 10, "数量": 12, "收入": 13, "利润": 14}
NEED = sorted(set(COLS.values()))

def ym_of(v):
    if isinstance(v, datetime):
        return f"{v.year}-{v.month:02d}"
    s = str(v)[:10]
    parts = s.split("-")
    if len(parts) >= 2:
        try:
            return f"{int(parts[0])}-{int(parts[1]):02d}"
        except ValueError:
            return ""
    return ""

res = {"锚点_底表三因子": {"同比": {"量": 383.0, "价": -470.0, "成本": -33.0, "dGP": -120.0},
                       "环比": {"量": -291.0, "价": 62.0, "成本": 8.0, "dGP": -220.0}}}
pythoncom.CoInitialize()
xl = None
try:
    xl = win32.DispatchEx("Excel.Application")
    xl.Visible = False
    xl.DisplayAlerts = False
    with_retry(lambda: xl.Workbooks.Open(BK, ReadOnly=True))
    ws = with_retry(lambda: xl.Worksheets("D-镜像"))
    nr = with_retry(lambda: ws.UsedRange.Rows.Count)
    res["行数"] = nr
    cols = {}
    for c in NEED:
        vals = []
        CH = 60000
        for start in range(2, nr + 1, CH):
            end = min(start + CH - 1, nr)
            v = with_retry(lambda: ws.Range(ws.Cells(start, c), ws.Cells(end, c)).Value)
            vals.extend([x[0] if isinstance(x, tuple) else x for x in v])
        cols[c] = vals
    with_retry(lambda: xl.Workbooks.Close())
finally:
    if xl is not None:
        try:
            xl.Quit()
        except Exception:
            pass
    pythoncom.CoUninitialize()

n = len(cols[NEED[0]])
dates = cols[COLS["发货日期"]]
skus = cols[COLS["存货名称"]]
qtys = cols[COLS["数量"]]
revs = cols[COLS["收入"]]
pfts = cols[COLS["利润"]]
custs = cols[COLS["客户简称"]]
cats = cols[COLS["品类"]]
pls = cols[COLS["产品线"]]

yms = [ym_of(d) for d in dates]

# ---- SKU×月度 聚合 ----
agg = {}  # (sku, ym) -> [q, rev, pft]
for i in range(n):
    ym = yms[i]
    if not ym:
        continue
    k = (str(skus[i] or "?"), ym)
    d = agg.setdefault(k, [0.0, 0.0, 0.0])
    d[0] += qtys[i] or 0.0
    d[1] += revs[i] or 0.0
    d[2] += pfts[i] or 0.0

def bridge(m1, m0):
    """四因子桥: m1当月 m0基准月, 返回万"""
    sk1 = {k[0]: v for k, v in agg.items() if k[1] == m1 and v[0] > 0}
    sk0 = {k[0]: v for k, v in agg.items() if k[1] == m0 and v[0] > 0}
    comp = set(sk1) & set(sk0)
    GP0 = GP1 = Q0 = Q1 = 0.0
    sumq1um0 = 0.0
    val = 0.0
    cst = 0.0
    for s in comp:
        q0, r0, p0 = sk0[s]
        q1, r1, p1 = sk1[s]
        um0 = p0 / q0
        um1 = p1 / q1
        pr0 = r0 / q0
        pr1 = r1 / q1
        GP0 += p0; GP1 += p1; Q0 += q0; Q1 += q1
        sumq1um0 += q1 * um0
        val += q1 * (pr1 - pr0)
        cst += q1 * ((pr0 - um0) - (pr1 - um1))
    UM0bar = GP0 / Q0
    q4 = (Q1 - Q0) * UM0bar
    st4 = sumq1um0 - Q1 * UM0bar
    dGP = GP1 - GP0
    return {"可比SKU数": len(comp), "量4": q4 / 1e4, "结构4": st4 / 1e4, "价": val / 1e4, "成本": cst / 1e4,
            "dGP": dGP / 1e4, "GP0万": GP0 / 1e4, "GP1万": GP1 / 1e4,
            "m0": GP0 / (sum(v[1] for k, v in agg.items() if k[1] == m0 and v[0] > 0 and k[0] in comp)),
            "m1": GP1 / (sum(v[1] for k, v in agg.items() if k[1] == m1 and v[0] > 0 and k[0] in comp)),
            "量3验证": (q4 + st4) / 1e4,
            "求和验证": (q4 + st4 + val + cst - dGP) / 1e4}

res["桥_同比_2026_08_vs_2025_08"] = {k: (round(v, 4) if isinstance(v, float) else v) for k, v in bridge("2026-08", "2025-08").items()}
res["桥_环比_2026_08_vs_2026_07"] = {k: (round(v, 4) if isinstance(v, float) else v) for k, v in bridge("2026-08", "2026-07").items()}
res["桥_1月_vs_2025_12"] = {k: (round(v, 4) if isinstance(v, float) else v) for k, v in bridge("2026-01", "2025-12").items()}

# 月度序列 2-8月
series = []
for m in range(2, 9):
    m1 = f"2026-{m:02d}"
    m0 = f"2026-{m-1:02d}"
    b = bridge(m1, m0)
    rev1 = sum(v[1] for k, v in agg.items() if k[1] == m1) / 1e4
    pft1 = sum(v[2] for k, v in agg.items() if k[1] == m1) / 1e4
    series.append({"月": f"{m}月", "收入万": round(rev1, 0), "毛利率": round(pft1 / rev1, 4) if rev1 else None,
                   "量": round(b["量4"], 0), "结构": round(b["结构4"], 0),
                   "价": round(b["价"], 0), "成本": round(b["成本"], 0),
                   "dGP": round(b["dGP"], 0), "量3": round(b["量3验证"], 0),
                   "求和残差": round(b["求和验证"], 2)})
# 1月也纳入(vs 2025-12)
b1 = bridge("2026-01", "2025-12")
rev1 = sum(v[1] for k, v in agg.items() if k[1] == "2026-01") / 1e4
pft1 = sum(v[2] for k, v in agg.items() if k[1] == "2026-01") / 1e4
series.insert(0, {"月": "1月", "收入万": round(rev1, 0), "毛利率": round(pft1 / rev1, 4) if rev1 else None,
                  "量": round(b1["量4"], 0), "结构": round(b1["结构4"], 0),
                  "价": round(b1["价"], 0), "成本": round(b1["成本"], 0),
                  "dGP": round(b1["dGP"], 0), "量3": round(b1["量3验证"], 0),
                  "求和残差": round(b1["求和验证"], 2)})
res["月度序列_重算"] = series

# ---- 客户YTD ----
targets = ["石头", "海康威视", "追觅", "兆驰", "共进", "安克创新", "中兴康讯"]
stat = {t: {"r26": 0.0, "p26": 0.0, "r25": 0.0, "p25": 0.0, "cats": {}} for t in targets}
dim08 = {}
for i in range(n):
    ym = yms[i]
    if not ym:
        continue
    c = str(custs[i] or "")
    r_ = revs[i] or 0.0
    p = pfts[i] or 0.0
    hit = None
    for t in targets:
        if t in c:
            hit = t
            break
    if hit:
        if ym.startswith("2026") and ym <= "2026-08":
            stat[hit]["r26"] += r_; stat[hit]["p26"] += p
            if hit in ("追觅", "兆驰", "共进"):
                cc = str(cats[i] or "?")
                d = stat[hit]["cats"].setdefault(cc, [0.0, 0.0])
                d[0] += r_; d[1] += p
        elif ym.startswith("2025") and ym <= "2025-08":
            stat[hit]["r25"] += r_; stat[hit]["p25"] += p
    if ym == "2026-08":
        nm = str(cats[i] or "") + "‖" + str(pls[i] or "")
        if ("音频" in nm) or ("电脑" in nm) or ("计算" in nm) or ("充电与控制" in nm) or ("通用电源" in nm):
            d = dim08.setdefault(nm, [0.0, 0.0])
            d[0] += r_; d[1] += p

cust_out = {}
for t in targets:
    s = stat[t]
    cust_out[t] = {"YTD26收入万": round(s["r26"] / 1e4, 1), "YTD26利润万": round(s["p26"] / 1e4, 1),
                   "YTD26毛利率": round(s["p26"] / s["r26"], 4) if s["r26"] else None,
                   "去年YTD收入万": round(s["r25"] / 1e4, 1), "去年YTD利润万": round(s["p25"] / 1e4, 1),
                   "去年YTD毛利率": round(s["p25"] / s["r25"], 4) if s["r25"] else None,
                   "收入同比": round(s["r26"] / s["r25"] - 1, 4) if s["r25"] else None,
                   "利润同比万": round((s["p26"] - s["p25"]) / 1e4, 1)}
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
res["音频电脑充电_8月_品类‖产品线"] = {k: {"收入万": round(v[0] / 1e4, 1), "毛利率": round(v[1] / v[0], 4) if v[0] else None} for k, v in dim08.items()}

json.dump(res, open(r"C:\Users\910373\AppData\Local\Temp\opencode\build\recompute.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("RECOMPUTE_DONE")
