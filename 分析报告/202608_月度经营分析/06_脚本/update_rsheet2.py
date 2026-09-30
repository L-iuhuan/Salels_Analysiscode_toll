# -*- coding: utf-8 -*-
r"""R-sheet新增R7-R10(中兴月度/对冲矩阵/长周期序列/量效应解剖+MM引擎) + Word清除残留修订"""
import json
import time
import pythoncom
import pywintypes
import win32com.client as win32

BK = r"E:\3-其他资料\数据分析\月度分析模板_8月报告副本.xlsx"
DST = r"E:\3-其他资料\数据分析\2026年8月销售经营分析报告(定稿).docx"
AN = json.load(open(r"C:\Users\910373\AppData\Local\Temp\opencode\build\analysis2.json", encoding="utf-8"))

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

LOG = []

# ---------- 1) Word 清残留修订 ----------
pythoncom.CoInitialize()
word = None
try:
    word = win32.DispatchEx("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0
    doc = with_retry(lambda: word.Documents.Open(DST))
    n = with_retry(lambda: doc.Revisions.Count)
    for i in range(n, 0, -1):
        rv = with_retry(lambda: doc.Revisions(i))
        with_retry(lambda: rv.Accept())
    n2 = with_retry(lambda: doc.Revisions.Count)
    LOG.append(f"word revisions: {n}->{n2}")
    with_retry(lambda: doc.Save())
    with_retry(lambda: doc.Close(False))
finally:
    if word is not None:
        try:
            word.Quit()
        except Exception:
            pass

# ---------- 2) Excel R7-R10 ----------
xl = None
try:
    xl = win32.DispatchEx("Excel.Application")
    xl.Visible = False
    xl.DisplayAlerts = False
    wb = with_retry(lambda: xl.Workbooks.Open(BK))

    def sv(ws, r, c, v):
        rg = with_retry(lambda: ws.Cells(r, c))
        with_retry(lambda: rg.__setattr__("Value", v if v is not None else ""))

    ws = with_retry(lambda: xl.Worksheets("R-报告补充"))
    r0 = 62
    sv(ws, r0, 1, "R7 中兴康讯月度损益(万) —— 2025-01至2026-08(计算源=D-镜像,2026-09-09)")
    for c, h in enumerate(["年月", "收入(万)", "利润(万)"], 1):
        sv(ws, r0 + 1, c, h)
    rr = r0 + 2
    for ym, d in sorted(AN["A_中兴康讯月度"].items()):
        sv(ws, rr, 1, ym); sv(ws, rr, 2, d["收入万"]); sv(ws, rr, 3, d["利润万"])
        rr += 1
    LOG.append("R7 written")

    sv(ws, rr + 1, 1, "R8 重点客户×品类利润增量矩阵(2026YTD vs 2025YTD,万) + 新品案例客户 + TMI6011客户")
    rr += 2
    for c, h in enumerate(["客户", "品类", "利润26", "利润25", "增量"], 1):
        sv(ws, rr, c, h)
    rr += 1
    for cust, rows in AN["C_同类对冲矩阵"].items():
        for it in rows:
            for c, v in enumerate([cust, it["品类"], it["利润26"], it["利润25"], it["增量"]], 1):
                sv(ws, rr, c, v)
            rr += 1
    sv(ws, rr, 1, "-- 新品案例代表客户(2026YTD,收入万/利润万) --")
    rr += 1
    for sku, custs in AN["B_新品案例客户"].items():
        for it in custs:
            if it["收入万"] > 0:
                for c, v in enumerate([f"新品:{sku}", it["客户"], it["收入万"], "", it["利润万"]], 1):
                    sv(ws, rr, c, v)
                rr += 1
    sv(ws, rr, 1, "-- TMI6011客户(2026YTD,收入万/利润万) --")
    rr += 1
    for cust, v in AN["G_TMI6011_客户"].items():
        for c, vv in enumerate(["TMI6011", cust, v[0], "", v[1]], 1):
            sv(ws, rr, c, vv)
        rr += 1
    LOG.append("R8 written")

    sv(ws, rr + 1, 1, "R9 四因子长周期序列(2024-02至2026-08,万) —— 每月vs上月,量+结构+价+成本=该月dGP")
    rr += 2
    for c, h in enumerate(["年月", "可比SKU数", "量", "结构", "价", "成本", "dGP", "收入(万)", "毛利率"], 1):
        sv(ws, rr, c, h)
    rr += 1
    for s in AN["D_四因子长周期"]:
        vals = [s["月"], s["SKU"], s["量"], s["结构"], s["价"], s["成本"], s["dGP"], s["收入"], s["毛利率"]]
        for c, v in enumerate(vals, 1):
            sv(ws, rr, c, v)
        rr += 1
    LOG.append("R9 written")

    sv(ws, rr + 1, 1, "R10 量效应解剖(8月vs7月全口径) + MM引擎")
    rr += 2
    sv(ws, rr, 1, "-- 品类环比变动(万) --")
    rr += 1
    for c, h in enumerate(["方向", "品类", "收入变动(万)", "销量变动(颗)", "8月收入(万)", "7月收入(万)"], 1):
        sv(ws, rr, c, h)
    rr += 1
    for d in AN["E_量效应解剖_品类"]["降幅TOP"]:
        vals = ["降幅", d["品类"], d["收入变动万"], d["数量变动颗"], d["8月收入万"], d["7月收入万"]]
        for c, v in enumerate(vals, 1):
            sv(ws, rr, c, v)
        rr += 1
    for d in AN["E_量效应解剖_品类"]["增幅TOP"]:
        vals = ["增幅", d["品类"], d["收入变动万"], d["数量变动颗"], d["8月收入万"], d["7月收入万"]]
        for c, v in enumerate(vals, 1):
            sv(ws, rr, c, v)
        rr += 1
    sv(ws, rr, 1, "-- 客户环比变动(万) --")
    rr += 1
    for d in AN["E_量效应解剖_客户"]["降幅TOP"]:
        vals = ["降幅", d["客户"], d["收入变动万"], d["数量变动颗"], d["8月收入万"], d["7月收入万"]]
        for c, v in enumerate(vals, 1):
            sv(ws, rr, c, v)
        rr += 1
    for d in AN["E_量效应解剖_客户"]["增幅TOP"]:
        vals = ["增幅", d["客户"], d["收入变动万"], d["数量变动颗"], d["8月收入万"], d["7月收入万"]]
        for c, v in enumerate(vals, 1):
            sv(ws, rr, c, v)
        rr += 1
    sv(ws, rr, 1, "-- MM引擎(2026YTD vs 2025YTD) --")
    rr += 1
    mm = AN["F_MM引擎"]
    for k, v in [("客户数26", mm["客户数26"]), ("客户数25", mm["客户数25"]), ("新增客户", mm["新增客户数"]),
                 ("流失客户", mm["流失客户数"]), ("收入26(万)", mm["收入26万"]), ("收入25(万)", mm["收入25万"]),
                 ("利润26(万)", mm["利润26万"]), ("利润25(万)", mm["利润25万"]), ("收入同比", mm["收入同比"]),
                 ("利润增量(万)", mm["利润同比万"]), ("毛利率26", mm["毛利率26"]), ("毛利率25", mm["毛利率25"]),
                 ("户均收入26(万)", round(mm["收入26万"] / mm["客户数26"], 1)),
                 ("户均收入25(万)", round(mm["收入25万"] / mm["客户数25"], 1))]:
        sv(ws, rr, 1, k); sv(ws, rr, 2, v)
        rr += 1
    LOG.append("R10 written")

    with_retry(lambda: wb.Save())
    with_retry(lambda: wb.Close(False))
finally:
    if xl is not None:
        try:
            xl.Quit()
        except Exception:
            pass
    pythoncom.CoUninitialize()

open(r"C:\Users\910373\AppData\Local\Temp\opencode\build\r710_log.txt", "w", encoding="utf-8").write("\n".join(str(x) for x in LOG))
print("R710_DONE")
