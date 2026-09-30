# -*- coding: utf-8 -*-
r"""重算8月成本上升单品TOP: 侵蚀=8月量×(7月加权UC-8月加权UC), 与表7对照"""
import json
import time
import pythoncom
import pywintypes
import win32com.client as win32
from datetime import datetime

BK = r"E:\3-其他资料\数据分析\月度分析模板_8月报告副本.xlsx"

def with_retry(fn, *a, **k):
    last = None
    for i in range(15):
        try:
            return fn(*a, **k)
        except pywintypes.com_error as e:
            if e.hresult in (-2147418111, -2147417846) and i < 14:
                last = e
                time.sleep(2)
                continue
            raise
    raise last

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

pythoncom.CoInitialize()
xl = None
sk = {}
try:
    xl = with_retry(lambda: win32.DispatchEx("Excel.Application"))
    xl.Visible = False
    xl.DisplayAlerts = False
    with_retry(lambda: xl.Workbooks.Open(BK, ReadOnly=True))
    ws = with_retry(lambda: xl.Worksheets("D-镜像"))
    nr = with_retry(lambda: ws.UsedRange.Rows.Count)
    cols = {}
    for c, nm in ((1, "dt"), (10, "sku"), (12, "q"), (13, "rev"), (14, "pft")):
        vals = []
        for start in range(2, nr + 1, 60000):
            end = min(start + 59999, nr)
            v = with_retry(lambda: ws.Range(ws.Cells(start, c), ws.Cells(end, c)).Value)
            vals.extend([x[0] if isinstance(x, tuple) else x for x in v])
        cols[nm] = vals
    with_retry(lambda: xl.Workbooks.Close())
finally:
    if xl is not None:
        try:
            xl.Quit()
        except Exception:
            pass
    pythoncom.CoUninitialize()

for i in range(len(cols["dt"])):
    ym = ym_of(cols["dt"][i])
    if ym not in ("2026-07", "2026-08"):
        continue
    k = str(cols["sku"][i] or "")
    if not k:
        continue
    d = sk.setdefault(k, {mm: [0.0, 0.0, 0.0] for mm in ("2026-07", "2026-08")})[ym]
    d[0] += cols["q"][i] or 0.0
    d[1] += cols["rev"][i] or 0.0
    d[2] += cols["pft"][i] or 0.0

# 品类对照(用于表内"所在品类"列): 略, 用已知三行品类
rows = []
for k, m in sk.items():
    q7, r7, p7 = m["2026-07"]
    q8, r8, p8 = m["2026-08"]
    if q7 > 0 and q8 > 0 and r7 > 0 and r8 > 0:
        uc0 = (r7 - p7) / q7
        uc1 = (r8 - p8) / q8
        cost_eff = q8 * (uc0 - uc1)  # 正=改善
        erosion = -cost_eff / 1e4     # 正=成本上升侵蚀(万)
        rows.append({
            "sku": k, "rev8万": round(r8 / 1e4, 1), "rev7万": round(r7 / 1e4, 1),
            "uc变化%": round((uc1 / uc0 - 1) * 100, 1),
            "侵蚀万": round(erosion, 1),
            "pft8万": round(p8 / 1e4, 1),
        })

rows.sort(key=lambda r: -r["侵蚀万"])
out = []
out.append("== 8月成本上升侵蚀TOP8 (口径: 8月量×(7月加权UC-8月加权UC), 侵蚀为正=成本上升伤利润) ==")
for r in rows[:8]:
    out.append(f"{r['sku']}: 侵蚀{r['侵蚀万']}万, UC变化{r['uc变化%']:+.1f}%, 8月收入{r['rev8万']}万, 8月利润{r['pft8万']}万")
out.append("")
focus = ["STI3452HFI", "TMI7608S", "TMI3252SN"]
out.append("== 原表7三个产品的8月真实值 ==")
for f in focus:
    r = next((x for x in rows if x["sku"] == f), None)
    if r:
        out.append(f"{f}: 侵蚀{r['侵蚀万']}万, UC变化{r['uc变化%']:+.1f}%, 8月收入{r['rev8万']}万, 8月利润{r['pft8万']}万")
    else:
        out.append(f"{f}: 不在7/8月双月在售集合(或无有效量/收入)")
out.append("")
out.append(f"(共{len(rows)}个双月在售SKU参与排序; 收入门槛未设,展示TOP8)")
json.dump(rows[:30], open(r"C:\Users\910373\AppData\Local\Temp\opencode\build\cost_sku.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
open(r"C:\Users\910373\AppData\Local\Temp\opencode\build\cost_sku.txt", "w", encoding="utf-8").write("\n".join(out))
print("COSTSKU_DONE")
