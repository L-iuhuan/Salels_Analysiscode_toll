# -*- coding: utf-8 -*-
r"""R11写入(音频分产品+渗透矩阵) + Word清残留修订"""
import json
import time
import pythoncom
import pywintypes
import win32com.client as win32

BK = r"E:\3-其他资料\数据分析\月度分析模板_8月报告副本.xlsx"
DST = r"E:\3-其他资料\数据分析\2026年8月销售经营分析报告(定稿).docx"
A3 = json.load(open(r"C:\Users\910373\AppData\Local\Temp\opencode\build\analysis3.json", encoding="utf-8"))
A4 = json.load(open(r"C:\Users\910373\AppData\Local\Temp\opencode\build\analysis4.json", encoding="utf-8"))

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

LOG = []
pythoncom.CoInitialize()
word = None
try:
    word = with_retry(lambda: win32.DispatchEx("Word.Application"))
    word.Visible = False
    word.DisplayAlerts = 0
    doc = with_retry(lambda: word.Documents.Open(DST))
    n = with_retry(lambda: doc.Revisions.Count)
    for i in range(n, 0, -1):
        rv = with_retry(lambda: doc.Revisions(i))
        with_retry(lambda: rv.Accept())
    LOG.append(f"word revisions: {n}->{with_retry(lambda: doc.Revisions.Count)}")
    with_retry(lambda: doc.Save())
    with_retry(lambda: doc.Close(False))
finally:
    if word is not None:
        try:
            word.Quit()
        except Exception:
            pass

xl = None
try:
    xl = with_retry(lambda: win32.DispatchEx("Excel.Application"))
    xl.Visible = False
    xl.DisplayAlerts = False
    wb = with_retry(lambda: xl.Workbooks.Open(BK))

    def sv(ws, r, c, v):
        rg = with_retry(lambda: ws.Cells(r, c))
        with_retry(lambda: rg.__setattr__("Value", v if v is not None else ""))

    ws = with_retry(lambda: xl.Worksheets("R-报告补充"))
    r0 = 118
    sv(ws, r0, 1, "R11 音频功放分产品(2026年,月=收入万/利润万/毛利率) + 品类×客户渗透矩阵(2026YTD) —— 计算源=D-镜像,2026-09-09")
    hdr = ["产品", "YTD收入(万)", "1月", "2月", "3月", "4月", "5月", "6月", "7月", "8月", "毛利率1-5月", "毛利率6-8月", "TOP客户"]
    for c, h in enumerate(hdr, 1):
        sv(ws, r0 + 1, c, h)
    rr = r0 + 2
    for it in A4["音频功放_分产品"]:
        vals = [it["产品"], it["YTD收入万"], it["01"], it["02"], it["03"], it["04"], it["05"], it["06"], it["07"], it["08"], it["毛利率_1至5月"], it["毛利率_6至8月"], it["TOP客户"]]
        for c, v in enumerate(vals, 1):
            sv(ws, rr, c, v)
        rr += 1
    LOG.append("R11a written")

    sv(ws, rr + 1, 1, "-- 品类×客户渗透矩阵(2026YTD收入万) --")
    rr += 2
    for c, h in enumerate(["品类", "总YTD收入(万)", "已渗透客户(领域/收入万)TOP8", "TOP30客户中未渗透"], 1):
        sv(ws, rr, c, h)
    rr += 1
    for cat, d in A3["D_渗透矩阵"].items():
        buyers = "; ".join(f"{b['客户']}({b['领域']}/{b['收入万']}万)" for b in d["已渗透TOP客户"])
        miss = "、".join(d["TOP30客户中未渗透"][:12])
        for c, v in enumerate([cat, d["总YTD收入万"], buyers, miss], 1):
            sv(ws, rr, c, v)
        rr += 1
    LOG.append("R11b written")

    with_retry(lambda: wb.Save())
    with_retry(lambda: wb.Close(False))
finally:
    if xl is not None:
        try:
            xl.Quit()
        except Exception:
            pass
    pythoncom.CoUninitialize()

open(r"C:\Users\910373\AppData\Local\Temp\opencode\build\r11_log.txt", "w", encoding="utf-8").write("\n".join(str(x) for x in LOG))
print("R11_DONE")
