# -*- coding: utf-8 -*-
r"""主模板(xlsm) vs 副本(xlsx) 一致性核查: sheet清单/可见性/关键sheet抽样值/毛利桥双口径"""
import time
import pythoncom
import pywintypes
import win32com.client as win32

MASTER = r"E:\3-其他资料\数据分析\月度分析模板.xlsm"
COPY = r"E:\3-其他资料\数据分析\月度分析模板_8月报告副本.xlsx"
OUT = r"C:\Users\910373\AppData\Local\Temp\opencode\build\mc_consistency.txt"

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

out = []
pythoncom.CoInitialize()
xl = None
try:
    xl = with_retry(lambda: win32.DispatchEx("Excel.Application"))
    xl.Visible = False
    xl.DisplayAlerts = False
    try:
        with_retry(lambda: xl.__setattr__("AutomationSecurity", 1))
    except Exception:
        pass
    wbm = with_retry(lambda: xl.Workbooks.Open(MASTER, ReadOnly=True))
    wbc = with_retry(lambda: xl.Workbooks.Open(COPY, ReadOnly=True))

    def sheetmap(wb):
        m = {}
        for i in range(1, with_retry(lambda: wb.Worksheets.Count) + 1):
            s = with_retry(lambda: wb.Worksheets(i))
            m[str(with_retry(lambda: s.Name))] = int(with_retry(lambda: s.Visible))
        return m

    sm = sheetmap(wbm)
    sc = sheetmap(wbc)
    out.append(f"master sheets({len(sm)}): {sorted(sm.keys())}")
    out.append(f"copy sheets({len(sc)}): {sorted(sc.keys())}")
    only_m = sorted(set(sm) - set(sc))
    only_c = sorted(set(sc) - set(sm))
    out.append(f"仅master有: {only_m}")
    out.append(f"仅copy有: {only_c}")
    visdiff = [n for n in set(sm) & set(sc) if sm[n] != sc[n]]
    out.append(f"共有sheet可见性差异: {visdiff if visdiff else '无'}")

    def read_cell(wb, sn, r, c):
        try:
            ws = with_retry(lambda: wb.Worksheets(sn))
            return with_retry(lambda: ws.Cells(r, c).Value)
        except Exception:
            return "<无此sheet>"

    # 毛利桥双口径 (行4-6三因子, 行11-13四因子)
    out.append("")
    out.append("== 10-毛利桥 双口径对比 ==")
    for r in list(range(4, 7)) + list(range(11, 14)):
        vm = [read_cell(wbm, "10-毛利桥", r, c) for c in range(1, 7)]
        vc = [read_cell(wbc, "10-毛利桥", r, c) for c in range(1, 7)]
        same = all(str(a) == str(b) for a, b in zip(vm, vc))
        out.append(f"r{r} {'一致' if same else '差异'}: master={vm} | copy={vc}" if not same else f"r{r} 一致: {vm[:6]}")

    # 核心sheet抽样: 关键汇总单元格
    out.append("")
    out.append("== 核心sheet抽样对比 ==")
    samples = [("1-整体概览", [(3, 2), (4, 2), (5, 2)]),
               ("3-客户分类", [(4, 2), (4, 3), (5, 2)]),
               ("11-SKU变化", [(5, 2), (5, 6)]),
               ("26-成本上升品类", [(3, 1), (3, 3)]),
               ("9-成本监控", [(3, 1), (3, 3)])]
    diffn = 0
    for sn, cells in samples:
        for (r, c) in cells:
            vm = read_cell(wbm, sn, r, c)
            vc = read_cell(wbc, sn, r, c)
            if str(vm) != str(vc):
                diffn += 1
                out.append(f"[差异] {sn} r{r}c{c}: master={vm} copy={vc}")
    out.append(f"抽样差异合计: {diffn}" + (" -> 共有sheet数值一致" if diffn == 0 else ""))

    # 0-说明 尾部注记对比(信息性)
    out.append("")
    out.append("== 0-说明 尾部注记(信息性) ==")
    for label, wb in (("master", wbm), ("copy", wbc)):
        w0 = with_retry(lambda: wb.Worksheets("0-说明"))
        lr = with_retry(lambda: w0.UsedRange.Rows.Count)
        tail = []
        for r in range(max(1, lr - 3), lr + 1):
            v = with_retry(lambda: w0.Cells(r, 1).Value)
            if v:
                tail.append(str(v)[:60])
        out.append(f"{label} 末{len(tail)}条: {tail}")

    with_retry(lambda: wbm.Close(False))
    with_retry(lambda: wbc.Close(False))
finally:
    if xl is not None:
        try:
            xl.Quit()
        except Exception:
            pass
    pythoncom.CoUninitialize()

open(OUT, "w", encoding="utf-8").write("\n".join(str(x) for x in out))
print("MCCHECK_DONE")
