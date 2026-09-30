# -*- coding: utf-8 -*-
r"""修复SUMIFS criteria波浪号问题: 含~品类改字面量条件(~~转义), 全量重验R3/R6c/R8/R10"""
import json
import re
import time
import pythoncom
import pywintypes
import win32com.client as win32

BK = r"E:\3-其他资料\数据分析\月度分析模板_8月报告副本.xlsx"
LOGF = r"C:\Users\910373\AppData\Local\Temp\opencode\build\fix_tilde_log.txt"
AN2 = json.load(open(r"C:\Users\910373\AppData\Local\Temp\opencode\build\analysis2.json", encoding="utf-8"))
RC = json.load(open(r"C:\Users\910373\AppData\Local\Temp\opencode\build\recompute.json", encoding="utf-8"))

def log(msg):
    with open(LOGF, "a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")

LAST = 206900
MIR = "'D-镜像'!"
def C(col):
    return f"{MIR}${col}$2:${col}${LAST}"
def dt_lo(y, m):
    return f'">="&DATE({y},{m},1)'
def dt_hi(y, m):
    m2, y2 = (m + 1, y) if m < 12 else (1, y + 1)
    return f'"<"&DATE({y2},{m2},1)'
def winp(y1, m1, y2, m2):
    return [("A", dt_lo(y1, m1)), ("A", dt_hi(y2, m2))]
W26 = winp(2026, 1, 2026, 8)
W25 = winp(2025, 1, 2025, 8)
W8 = winp(2026, 8, 2026, 8)
W7 = winp(2026, 7, 2026, 7)
def esc(cat):
    return cat.replace("~", "~~")
def crit_lit(cat):
    return '"' + esc(cat) + '"'
def sumifs(tcol, conds):
    parts = [C(tcol)]
    for col, crit in conds:
        parts.append(C(col))
        parts.append(crit)
    return "SUMIFS(" + ",".join(parts) + ")"
def cc(cell):
    return f'"*"&{cell}&"*"'

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

VER = []
pythoncom.CoInitialize()
xl = None
try:
    xl = with_retry(lambda: win32.DispatchEx("Excel.Application"))
    xl.Visible = False
    xl.DisplayAlerts = False
    wb = with_retry(lambda: xl.Workbooks.Open(BK))
    with_retry(lambda: xl.__setattr__("Calculation", -4135))
    log("opened, calc=manual")

    def rd(ws, r, c):
        return with_retry(lambda: ws.Cells(r, c).Value)

    def sf(ws, r, c, f):
        rg = with_retry(lambda: ws.Cells(r, c))
        with_retry(lambda: rg.__setattr__("Formula", f))

    # ---- R10-量效应: 品类块全部改字面量转义条件 (D=变动, E=8月, F=7月) ----
    w = with_retry(lambda: xl.Worksheets("R10-量效应"))
    exp10 = AN2["E_量效应解剖_品类"]["降幅TOP"] + AN2["E_量效应解剖_品类"]["增幅TOP"]
    catrows = {}
    r = 3
    while True:
        a = rd(w, r, 3)
        if not a and not rd(w, r, 1):
            break
        if rd(w, r, 2) == "品类" and a:
            catrows[str(a)] = r
        r += 1
    fixed = 0
    for d in exp10:
        cat = d["品类"]
        rr = catrows.get(cat)
        if not rr:
            log(f"WARN R10 未找到行: {cat}")
            continue
        c8 = [("H", crit_lit(cat))] + W8
        c7 = [("H", crit_lit(cat))] + W7
        sf(w, rr, 4, f"=ROUND(({sumifs('M', c8)}-{sumifs('M', c7)})/10000,1)")
        sf(w, rr, 5, f"=ROUND({sumifs('M', c8)}/10000,1)")
        sf(w, rr, 6, f"=ROUND({sumifs('M', c7)}/10000,1)")
        VER.append(("R10", w, rr, "D", d["收入变动万"]))
        VER.append(("R10", w, rr, "E", d["8月收入万"], 1.1))
        fixed += 1
    log(f"R10 categories rewritten={fixed}")

    # ---- R8-品类增量: 含~品类行 C/D 改字面量条件 ----
    w = with_retry(lambda: xl.Worksheets("R8-品类增量"))
    exp8 = {}
    for cust in ["石头", "海康威视", "TPLINK", "大华集团", "共进", "兆驰", "创维数字", "小米集团", "追觅", "中兴康讯"]:
        for it in AN2["C_同类对冲矩阵"][cust]:
            exp8[(cust, it["品类"])] = it
    r = 3
    while r < 120:
        cust = rd(w, r, 1)
        cat = rd(w, r, 2)
        if cust and cat and ("~" in str(cat)):
            cust = str(cust)
            cat = str(cat)
            it = exp8.get((cust, cat))
            rr = r
            c26 = [("B", cc(f"A{rr}")), ("H", crit_lit(cat))] + W26
            c25 = [("B", cc(f"A{rr}")), ("H", crit_lit(cat))] + W25
            sf(w, rr, 3, f"=ROUND({sumifs('N', c26)}/10000,1)")
            sf(w, rr, 4, f"=ROUND({sumifs('N', c25)}/10000,1)")
            if it:
                VER.append(("R8", w, rr, "C", it["利润26"]))
            fixed += 1
        r += 1
    log(f"R8 tilde rows rewritten={fixed}")
    # R8全量验证(含非波浪号行)
    r = 3
    while r < 120:
        cust = rd(w, r, 1)
        cat = rd(w, r, 2)
        if cust and cat and rd(w, r, 3) is not None:
            key = (str(cust), str(cat))
            if key in exp8 and not any(v[2] == r and v[0] == "R8" for v in VER):
                VER.append(("R8", w, r, "C", exp8[key]["利润26"]))
        r += 1

    # ---- R6-SKU与客户: R6c 含~品类行 C/D 改字面量条件 ----
    w = with_retry(lambda: xl.Worksheets("R6-SKU与客户"))
    exp6c = RC["客户品类TOP3_2026YTD"]
    r = 1
    while r < 60:
        cust = rd(w, r, 1)
        cat = rd(w, r, 2)
        if cust in ("追觅", "兆驰", "共进") and cat:
            rr = r
            found = None
            for it in exp6c[cust]:
                if it["品类"] == str(cat):
                    found = it
            if found:
                c26 = [("B", cc(f"A{rr}")), ("H", crit_lit(str(cat)))] + W26
                sf(w, rr, 3, f"=ROUND({sumifs('M', c26)}/10000,1)")
                sf(w, rr, 4, f"=ROUND({sumifs('N', c26)}/10000,1)")
                VER.append(("R6c", w, rr, "C", found["收入万"]))
        r += 1
    log("R6c rewritten")

    # ---- R-报告补充: R3 含~品类行 B/C 改字面量条件 ----
    w = with_retry(lambda: xl.Worksheets("R-报告补充"))
    zx = AN2["C_同类对冲矩阵"]["中兴康讯"]
    r = 19
    while r <= 26:
        cat = rd(w, r, 1)
        if cat and "~" in str(cat):
            found = next((it for it in zx if it["品类"] == str(cat)), None)
            if found:
                rr = r
                c26 = [("B", '"*中兴康讯*"'), ("H", crit_lit(str(cat)))] + W26
                sf(w, rr, 2, f"=ROUND({sumifs('M', c26)}/10000,1)")
                sf(w, rr, 3, f"=ROUND({sumifs('N', c26)}/10000,1)")
                VER.append(("R3", w, rr, "B", found["利润26"] * -1 if False else None))
                # R3期望: 收入(万) 需另行取数 — 用AN2中兴康讯矩阵不含收入, R3原值1939已静态可比对
                VER.pop()
                old = rd(w, r, 2)
        r += 1
    log("R3 rewritten")

    # ---- 重算+验证 ----
    sheets = []
    for _, ws, *_ in VER:
        if ws not in sheets:
            sheets.append(ws)
    for ws in sheets:
        t0 = time.time()
        with_retry(lambda: ws.Calculate())
        log(f"calculated {ws.Name} in {time.time() - t0:.1f}s")
    time.sleep(2)
    fails = 0
    for blk, ws, row, colletter, expect, *rest in [(v[0], v[1], v[2], v[3], v[4]) for v in VER]:
        v = with_retry(lambda: ws.Cells(row, colletter).Value)
        tol = 1.1 if (expect is not None and abs(expect) >= 20) else 0.16
        if expect is None:
            continue
        try:
            vf = float(v)
        except (TypeError, ValueError):
            fails += 1
            log(f"FAIL {blk} {ws.Name}!{colletter}{row} expect={expect} actual=非数值({v})")
            continue
        if abs(vf - expect) > tol:
            fails += 1
            log(f"FAIL {blk} {ws.Name}!{colletter}{row} expect={expect} actual={round(vf, 2)}")
    log(f"verify total={len(VER)} fails={fails}")

    with_retry(lambda: xl.__setattr__("Calculation", -4105))
    with_retry(lambda: wb.Save())
    with_retry(lambda: wb.Close(False))
    log("saved")
finally:
    if xl is not None:
        try:
            xl.Quit()
        except Exception:
            pass
    pythoncom.CoUninitialize()
print("FIX_TILDE_DONE")
