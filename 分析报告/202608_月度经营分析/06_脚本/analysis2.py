# -*- coding: utf-8 -*-
r"""扩展分析: 中兴月度/新品×客户/同类对冲/四因子长周期/量效应解剖/MM引擎/新典范"""
import json
import time
import pythoncom
import pywintypes
import win32com.client as win32
from datetime import datetime

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

COLS = {"发货日期": 1, "客户简称": 2, "客户类别全称": 3, "细分市场": 5, "产品线": 6, "品类": 8,
        "存货名称": 10, "是否新品": 11, "数量": 12, "收入": 13, "利润": 14}
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

res = {}
pythoncom.CoInitialize()
xl = None
try:
    xl = win32.DispatchEx("Excel.Application")
    xl.Visible = False
    xl.DisplayAlerts = False
    with_retry(lambda: xl.Workbooks.Open(BK, ReadOnly=True))
    ws = with_retry(lambda: xl.Worksheets("D-镜像"))
    nr = with_retry(lambda: ws.UsedRange.Rows.Count)
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
dates, custs, cats, skus, qtys, revs, pfts, ccls = (
    cols[COLS["发货日期"]], cols[COLS["客户简称"]], cols[COLS["品类"]], cols[COLS["存货名称"]],
    cols[COLS["数量"]], cols[COLS["收入"]], cols[COLS["利润"]], cols[COLS["客户类别全称"]])
yms = [ym_of(d) for d in dates]

def W(x):
    return (x or 0.0) / 1e4

# ---- A. 中兴康讯月度损益 2025-01..2026-08 ----
zx = {}
for i in range(n):
    if "中兴康讯" in str(custs[i] or ""):
        ym = yms[i]
        if ym >= "2025-01":
            d = zx.setdefault(ym, [0.0, 0.0])
            d[0] += W(revs[i]); d[1] += W(pfts[i])
res["A_中兴康讯月度"] = {k: {"收入万": round(v[0], 1), "利润万": round(v[1], 1)} for k, v in sorted(zx.items())}

# ---- B. 新品案例 × 客户 (2026YTD) ----
case_skus = ["TMI8180I", "TMI7604R", "TMI8116-Q1", "TME7352"]
skc = {s: {} for s in case_skus}
for i in range(n):
    nm = str(skus[i] or "")
    for s in case_skus:
        if nm == s and yms[i].startswith("2026") and yms[i] <= "2026-08":
            cu = str(custs[i] or "?")
            d = skc[s].setdefault(cu, [0.0, 0.0])
            d[0] += W(revs[i]); d[1] += W(pfts[i])
resB = {}
for s in case_skus:
    top = sorted(skc[s].items(), key=lambda kv: -kv[1][0])[:5]
    resB[s] = [{"客户": k, "收入万": round(v[0], 1), "利润万": round(v[1], 1)} for k, v in top]
res["B_新品案例客户"] = resB

# ---- C. 同类对冲矩阵: 重点客户 × 品类 利润增量(26YTD - 25YTD) ----
keys = ["追觅", "中兴康讯", "小米集团", "石头", "海康威视", "大华集团", "TPLINK", "创维数字", "共进", "兆驰"]
mat = {}  # cust -> cat -> [p26, p25]
for i in range(n):
    cu = str(custs[i] or "")
    hit = None
    for k in keys:
        if k in cu:
            hit = k
            break
    if not hit:
        continue
    ym = yms[i]
    if not (ym.startswith("2026") and ym <= "2026-08" or (ym.startswith("2025") and ym <= "2025-08")):
        continue
    cat = str(cats[i] or "?")
    d = mat.setdefault(hit, {}).setdefault(cat, [0.0, 0.0])
    if ym.startswith("2026"):
        d[0] += W(pfts[i])
    else:
        d[1] += W(pfts[i])
resC = {}
for cu, cats_d in mat.items():
    rows = []
    for cat, (p26, p25) in cats_d.items():
        rows.append({"品类": cat, "利润26": round(p26, 1), "利润25": round(p25, 1), "增量": round(p26 - p25, 1)})
    rows.sort(key=lambda r: r["增量"])
    resC[cu] = rows[:4] + rows[-3:] if len(rows) > 7 else rows
res["C_同类对冲矩阵"] = resC

# ---- D. 四因子长周期 2024-02..2026-08 ----
agg = {}
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
    sk1 = {k[0]: v for k, v in agg.items() if k[1] == m1 and v[0] > 0}
    sk0 = {k[0]: v for k, v in agg.items() if k[1] == m0 and v[0] > 0}
    comp = set(sk1) & set(sk0)
    GP0 = GP1 = Q0 = Q1 = sq1u0 = val = cst = 0.0
    for s in comp:
        q0, r0, p0 = sk0[s]
        q1, r1, p1 = sk1[s]
        um0 = p0 / q0; um1 = p1 / q1
        pr0 = r0 / q0; pr1 = r1 / q1
        GP0 += p0; GP1 += p1; Q0 += q0; Q1 += q1
        sq1u0 += q1 * um0
        val += q1 * (pr1 - pr0)
        cst += q1 * ((pr0 - um0) - (pr1 - um1))
    UM0 = GP0 / Q0
    return {"SKU": len(comp), "量": round((Q1 - Q0) * UM0 / 1e4, 0), "结构": round((sq1u0 - Q1 * UM0) / 1e4, 0),
            "价": round(val / 1e4, 0), "成本": round(cst / 1e4, 0), "dGP": round((GP1 - GP0) / 1e4, 0)}

series = []
for y in (2024, 2025, 2026):
    for m in range(1, 13):
        m1 = f"{y}-{m:02d}"
        m0 = f"{y}-{m-1:02d}" if m > 1 else f"{y-1}-12"
        if m1 < "2024-02" or m1 > "2026-08":
            continue
        if not any(k[1] == m1 for k in agg) or not any(k[1] == m0 for k in agg):
            continue
        b = bridge(m1, m0)
        rev1 = sum(v[1] for k, v in agg.items() if k[1] == m1) / 1e4
        pft1 = sum(v[2] for k, v in agg.items() if k[1] == m1) / 1e4
        b["月"] = m1
        b["收入"] = round(rev1, 0)
        b["毛利率"] = round(pft1 / rev1, 4) if rev1 else None
        series.append(b)
res["D_四因子长周期"] = series

# ---- E. 量效应解剖: 8月vs7月 收入/数量变动 by 品类 & 客户 ----
def delta_dim(idx_name, col_map, topn=10):
    d = {}
    for i in range(n):
        if yms[i] in ("2026-08", "2026-07"):
            key = str(col_map[i] or "?")
            e = d.setdefault(key, {"rev8": 0.0, "rev7": 0.0, "q8": 0.0, "q7": 0.0})
            if yms[i] == "2026-08":
                e["rev8"] += W(revs[i]); e["q8"] += qtys[i] or 0.0
            else:
                e["rev7"] += W(revs[i]); e["q7"] += qtys[i] or 0.0
    rows = []
    for k, e in d.items():
        dr = e["rev8"] - e["rev7"]
        dq = e["q8"] - e["q7"]
        if abs(dr) < 10:
            continue
        rows.append({idx_name: k, "收入变动万": round(dr, 1), "数量变动颗": round(dq, 0),
                     "8月收入万": round(e["rev8"], 1), "7月收入万": round(e["rev7"], 1)})
    rows.sort(key=lambda r: r["收入变动万"])
    return {"降幅TOP": rows[:topn], "增幅TOP": sorted(rows, key=lambda r: -r["收入变动万"])[:5]}

res["E_量效应解剖_品类"] = delta_dim("品类", cats)
res["E_量效应解剖_客户"] = delta_dim("客户", custs)

# ---- F. MM引擎: 客户数/收入/利润 26YTD vs 25YTD ----
mm = {"n26": set(), "n25": set(), "r26": 0.0, "r25": 0.0, "p26": 0.0, "p25": 0.0}
for i in range(n):
    cl = str(ccls[i] or "")
    ym = yms[i]
    if "MM" not in cl.upper():
        continue
    if ym.startswith("2026") and ym <= "2026-08":
        mm["n26"].add(str(custs[i])); mm["r26"] += W(revs[i]); mm["p26"] += W(pfts[i])
    elif ym.startswith("2025") and ym <= "2025-08":
        mm["n25"].add(str(custs[i])); mm["r25"] += W(revs[i]); mm["p25"] += W(pfts[i])
res["F_MM引擎"] = {"客户数26": len(mm["n26"]), "客户数25": len(mm["n25"]),
                   "新增客户数": len(mm["n26"] - mm["n25"]), "流失客户数": len(mm["n25"] - mm["n26"]),
                   "收入26万": round(mm["r26"], 0), "收入25万": round(mm["r25"], 0),
                   "利润26万": round(mm["p26"], 0), "利润25万": round(mm["p25"], 0),
                   "收入同比": round(mm["r26"] / mm["r25"] - 1, 4),
                   "利润同比万": round(mm["p26"] - mm["p25"], 0),
                   "毛利率26": round(mm["p26"] / mm["r26"], 4), "毛利率25": round(mm["p25"] / mm["r25"], 4)}

# ---- G. 新典范候选补充: 共进LDO/TMI6011, 大华/TPLINK/立讯 品类增量 ----
res["G_新典范补充"] = {k: v for k, v in resC.items() if k in ("大华集团", "TPLINK", "共进")}
tmi6011 = {}
for i in range(n):
    if "TMI6011" in str(skus[i] or "") and yms[i].startswith("2026"):
        cu = str(custs[i] or "?")
        d = tmi6011.setdefault(cu, [0.0, 0.0])
        d[0] += W(revs[i]); d[1] += W(pfts[i])
res["G_TMI6011_客户"] = {k: [round(v[0], 1), round(v[1], 1)] for k, v in sorted(tmi6011.items(), key=lambda kv: -kv[1][0])[:6]}

# ---- H. 可比毛利率复核(环比) ----
b = bridge("2026-08", "2026-07")
sk1 = {k[0]: v for k, v in agg.items() if k[1] == "2026-08" and v[0] > 0}
sk0 = {k[0]: v for k, v in agg.items() if k[1] == "2026-07" and v[0] > 0}
comp = set(sk1) & set(sk0)
r1c = sum(sk1[s][1] for s in comp) / 1e4
r0c = sum(sk0[s][1] for s in comp) / 1e4
p1c = sum(sk1[s][2] for s in comp) / 1e4
p0c = sum(sk0[s][2] for s in comp) / 1e4
res["H_可比毛利率复核"] = {"可比7月收入万": round(r0c, 0), "可比8月收入万": round(r1c, 0),
                       "可比7月毛利万": round(p0c, 0), "可比8月毛利万": round(p1c, 0),
                       "m0": round(p0c / r0c, 4), "m1": round(p1c / r1c, 4),
                       "全公司m0": 0.3025, "全公司m1": 0.3068,
                       "非可比7月毛利率": None, "非可比8月毛利率": None}
r7n = sum(v[1] for k, v in agg.items() if k[1] == "2026-07") / 1e4 - r0c
p7n = sum(v[2] for k, v in agg.items() if k[1] == "2026-07") / 1e4 - p0c
r8n = sum(v[1] for k, v in agg.items() if k[1] == "2026-08") / 1e4 - r1c
p8n = sum(v[2] for k, v in agg.items() if k[1] == "2026-08") / 1e4 - p1c
res["H_可比毛利率复核"]["非可比7月收入万"] = round(r7n, 0)
res["H_可比毛利率复核"]["非可比7月毛利率"] = round(p7n / r7n, 4) if r7n else None
res["H_可比毛利率复核"]["非可比8月收入万"] = round(r8n, 0)
res["H_可比毛利率复核"]["非可比8月毛利率"] = round(p8n / r8n, 4) if r8n else None

json.dump(res, open(r"C:\Users\910373\AppData\Local\Temp\opencode\build\analysis2.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("ANALYSIS2_DONE")
