# -*- coding: utf-8 -*-
r"""音频功放(产品线)分产品×月度 v2: 单次读取+Dispatch重试"""
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

res = {}
pythoncom.CoInitialize()
xl = None
try:
    xl = with_retry(lambda: win32.DispatchEx("Excel.Application"))
    xl.Visible = False
    xl.DisplayAlerts = False
    with_retry(lambda: xl.Workbooks.Open(BK, ReadOnly=True))
    ws = with_retry(lambda: xl.Worksheets("D-镜像"))
    nr = with_retry(lambda: ws.UsedRange.Rows.Count)
    cols = {}
    for c in (1, 2, 6, 10, 13, 14):  # 日期/客户/产品线/存货/收入/利润
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

dates, custs, pls, skus, revs, pfts = cols[1], cols[2], cols[6], cols[10], cols[13], cols[14]

prod = {}
pcust = {}
for i in range(len(dates)):
    if str(pls[i] or "") != "音频功放":
        continue
    ym = ym_of(dates[i])
    if ym < "2026-01" or ym > "2026-08":
        continue
    k = str(skus[i] or "?")
    r_ = (revs[i] or 0.0) / 1e4
    p_ = (pfts[i] or 0.0) / 1e4
    d = prod.setdefault(k, {}).setdefault(ym, [0.0, 0.0])
    d[0] += r_; d[1] += p_
    cu = str(custs[i] or "?")
    dd = pcust.setdefault(k, {}).setdefault(cu, [0.0, 0.0])
    dd[0] += r_; dd[1] += p_

MONTHS = [f"2026-{m:02d}" for m in range(1, 9)]
out = []
for sku, md in prod.items():
    tot = sum(v[0] for v in md.values())
    if tot < 5:
        continue
    row = {"产品": sku, "YTD收入万": round(tot, 1)}
    for ym in MONTHS:
        r_, p_ = md.get(ym, [0, 0])
        row[ym[5:]] = ("%.0f/%.0f(%.0f%%)" % (r_, p_, (p_ / r_ * 100) if r_ else 0))
    r15 = sum(md.get(ym, [0, 0])[0] for ym in MONTHS[:5])
    p15 = sum(md.get(ym, [0, 0])[1] for ym in MONTHS[:5])
    r68 = sum(md.get(ym, [0, 0])[0] for ym in MONTHS[5:])
    p68 = sum(md.get(ym, [0, 0])[1] for ym in MONTHS[5:])
    row["毛利率_1至5月"] = round(p15 / r15, 4) if r15 else None
    row["毛利率_6至8月"] = round(p68 / r68, 4) if r68 else None
    row["TOP客户"] = sorted(pcust[sku].items(), key=lambda kv: -kv[1][0])[0][0] if pcust.get(sku) else "?"
    out.append(row)
out.sort(key=lambda r: -r["YTD收入万"])
res["音频功放_分产品"] = out[:8]
res["音频功放_分产品_客户"] = {sku: {k: [round(v[0], 1), round(v[1], 1)] for k, v in sorted(pcust.get(sku, {}).items(), key=lambda kv: -kv[1][0])[:3]} for sku in [r["产品"] for r in out[:4]]}

json.dump(res, open(r"C:\Users\910373\AppData\Local\Temp\opencode\build\analysis4.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("AUDIO_DONE")
