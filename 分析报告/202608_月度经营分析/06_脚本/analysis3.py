# -*- coding: utf-8 -*-
r"""分析3: 音频/电脑历史毛利率 + DCDC-18V分产品7vs8月 + 量结构相关性 + 品类×客户渗透"""
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

COLS = {"发货日期": 1, "客户简称": 2, "细分市场": 5, "产品线": 6, "品类": 8,
        "存货名称": 10, "数量": 12, "收入": 13, "利润": 14}
NEED = sorted(set(COLS.values()))

def ym_of(v):
    if isinstance(v, datetime):
        return f"{v.year}-{v.month:02d}"
    parts = str(v)[:10].split("-")
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
        for start in range(2, nr + 1, 60000):
            end = min(start + 59999, nr)
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
dates, custs, mkts, pls, cats, skus, qtys, revs, pfts = (
    cols[COLS["发货日期"]], cols[COLS["客户简称"]], cols[COLS["细分市场"]], cols[COLS["产品线"]],
    cols[COLS["品类"]], cols[COLS["存货名称"]], cols[COLS["数量"]], cols[COLS["收入"]], cols[COLS["利润"]])
yms = [ym_of(d) for d in dates]

def W(x):
    return (x or 0.0) / 1e4

# ---- A. 音频功放(产品线)/电脑&计算(品类) 月度毛利率 2025-01..2026-08 ----
aud, cmp_ = {}, {}
for i in range(n):
    ym = yms[i]
    if ym < "2025-01":
        continue
    pl = str(pls[i] or "")
    cat = str(cats[i] or "")
    if pl == "音频功放":
        d = aud.setdefault(ym, [0.0, 0.0]); d[0] += W(revs[i]); d[1] += W(pfts[i])
    elif cat.startswith("电脑&计算"):
        d = cmp_.setdefault(ym, [0.0, 0.0]); d[0] += W(revs[i]); d[1] += W(pfts[i])
res["A_音频功放月度"] = {k: {"收入万": round(v[0], 1), "利润万": round(v[1], 1),
                        "毛利率": round(v[1] / v[0], 4) if v[0] else None} for k, v in sorted(aud.items())}
res["A_电脑计算月度"] = {k: {"收入万": round(v[0], 1), "利润万": round(v[1], 1),
                        "毛利率": round(v[1] / v[0], 4) if v[0] else None} for k, v in sorted(cmp_.items())}

# ---- B. DCDC-18V-降压2~4A 分产品 7月vs8月 ----
prod = {}
for i in range(n):
    if str(cats[i] or "") == "DCDC-18V-降压2~4A" and yms[i] in ("2026-07", "2026-08"):
        k = str(skus[i] or "?")
        d = prod.setdefault(k, {"rev7": 0.0, "rev8": 0.0, "pft7": 0.0, "pft8": 0.0, "q7": 0.0, "q8": 0.0})
        if yms[i] == "2026-07":
            d["rev7"] += W(revs[i]); d["pft7"] += W(pfts[i]); d["q7"] += qtys[i] or 0
        else:
            d["rev8"] += W(revs[i]); d["pft8"] += W(pfts[i]); d["q8"] += qtys[i] or 0
rows = []
for k, d in prod.items():
    dp = d["pft8"] - d["pft7"]
    rows.append({"产品": k, "rev7": round(d["rev7"], 1), "rev8": round(d["rev8"], 1),
                 "pft7": round(d["pft7"], 1), "pft8": round(d["pft8"], 1),
                 "m7": round(d["pft7"] / d["rev7"], 4) if d["rev7"] else None,
                 "m8": round(d["pft8"] / d["rev8"], 4) if d["rev8"] else None,
                 "dpft": round(dp, 1), "drev": round(d["rev8"] - d["rev7"], 1)})
rows.sort(key=lambda r: r["dpft"])
res["B_DCDC18V_分产品"] = {"利润改善TOP10": rows[:10], "利润恶化TOP5": rows[-5:],
                    "品类合计": {"rev7": round(sum(r["rev7"] for r in rows), 1), "rev8": round(sum(r["rev8"] for r in rows), 1),
                              "pft7": round(sum(r["pft7"] for r in rows), 1), "pft8": round(sum(r["pft8"] for r in rows), 1),
                              "dpft": round(sum(r["dpft"] for r in rows), 1)}}

# ---- C. 量-结构相关性 ----
AN = json.load(open(r"C:\Users\910373\AppData\Local\Temp\opencode\build\analysis2.json", encoding="utf-8"))
ser = AN["D_四因子长周期"]

def corr(xs, ys):
    nx = len(xs)
    mx, my = sum(xs) / nx, sum(ys) / nx
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = sum((x - mx) ** 2 for x in xs) ** 0.5
    vy = sum((y - my) ** 2 for y in ys) ** 0.5
    return cov / (vx * vy) if vx and vy else None

q = [s["量"] for s in ser]
st = [s["结构"] for s in ser]
p_ = [s["价"] for s in ser]
res["C_相关性"] = {"量vs结构_全期31月": round(corr(q, st), 3),
              "量vs结构_2026年8月": round(corr(q[-8:], st[-8:]), 3),
              "量vs价_全期": round(corr(q, p_), 3),
              "量dGP相关性": round(corr(q, [s["dGP"] for s in ser]), 3),
              "结构dGP相关性": round(corr(st, [s["dGP"] for s in ser]), 3)}
# 量周期性: 2月值与次月回补
res["C_量周期"] = {"2月量效应": {s["月"]: s["量"] for s in ser if s["月"].endswith("-02")},
              "3月量效应": {s["月"]: s["量"] for s in ser if s["月"].endswith("-03")}}

# ---- D. 品类×客户×细分市场 渗透矩阵(2026YTD) ----
target_cats = ["PSE", "POE-PD二合一/三合一", "LDO大电流超低压高性能", "H桥BDC-高压36V以上<3A",
               "DCDC-5V-降压1~3A", "车规有刷多路栅驱", "30V3~8A高精度CC转换器", "USB单通道/多通道2.4A/3A"]
cust_tot = {}
pen = {c: {} for c in target_cats}
for i in range(n):
    ym = yms[i]
    if not (ym.startswith("2026") and ym <= "2026-08"):
        continue
    cu = str(custs[i] or "?")
    cust_tot[cu] = cust_tot.get(cu, 0.0) + W(revs[i])
    cat = str(cats[i] or "")
    if cat in pen:
        d = pen[cat].setdefault(cu, [0.0, 0.0])
        d[0] += W(revs[i]); d[1] += W(pfts[i])
top_custs = sorted(cust_tot.items(), key=lambda kv: -kv[1])[:30]
# 客户→细分市场
cust_mkt = {}
for i in range(n):
    ym = yms[i]
    if ym.startswith("2026") and ym <= "2026-08":
        cu = str(custs[i] or "?")
        if cu not in cust_mkt:
            cust_mkt[cu] = str(mkts[i] or "?")
res["D_渗透矩阵"] = {}
for cat in target_cats:
    buyers = sorted(pen[cat].items(), key=lambda kv: -kv[1][0])
    res["D_渗透矩阵"][cat] = {
        "总YTD收入万": round(sum(v[0] for v in pen[cat].values()), 1),
        "已渗透TOP客户": [{"客户": k, "领域": cust_mkt.get(k, "?"), "收入万": round(v[0], 1)} for k, v in buyers[:8]],
        "TOP30客户中未渗透": [c for c, _ in top_custs if c not in pen[cat]][:12],
    }
res["D_TOP30客户"] = [{"客户": c, "领域": cust_mkt.get(c, "?"), "YTD收入万": round(r, 1)} for c, r in top_custs]

json.dump(res, open(r"C:\Users\910373\AppData\Local\Temp\opencode\build\analysis3.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("ANALYSIS3_DONE")
