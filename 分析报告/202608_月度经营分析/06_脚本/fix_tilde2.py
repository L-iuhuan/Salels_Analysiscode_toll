# -*- coding: utf-8 -*-
r"""波浪号修复v2: 品类条件改裸字面量(无*包裹无转义,精确匹配), 覆盖R10/R8/R6c/R3全部品类行"""
import json
import time
import pythoncom
import pywintypes
import win32com.client as win32

BK = r"E:\3-其他资料\数据分析\月度分析模板_8月报告副本.xlsx"
LOGF = r"C:\Users\910373\AppData\Local\Temp\opencode\build\fix_tilde2_log.txt"
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
def lit(cat):
    return '"' + cat + '"'
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

    # ---- R10: 全部品类行(裸字面量) ----
    w = with_retry(lambda: xl.Worksheets("R10-量效应"))
    exp10 = AN2["E_量效应解剖_品类"]["降幅TOP"] + AN2["E_量效应解剖_品类"]["增幅TOP"]
    catrows = {}
    r = 3
    while r < 40:
        a = rd(w, r, 3)
        if rd(w, r, 2) == "品类" and a:
            catrows[str(a)] = r
        r += 1
    n = 0
    for d in exp10:
        cat = d["品类"]
        rr = catrows.get(cat)
        if not rr:
            log(f"WARN R10 miss {cat}")
            continue
        c8 = [("H", lit(cat))] + W8
        c7 = [("H", lit(cat))] + W7
        sf(w, rr, 4, f"=ROUND(({sumifs('M', c8)}-{sumifs('M', c7)})/10000,1)")
        sf(w, rr, 5, f"=ROUND({sumifs('M', c8)}/10000,1)")
        sf(w, rr, 6, f"=ROUND({sumifs('M', c7)}/10000,1)")
        VER.append(("R10", w, rr, "D", d["收入变动万"]))
        VER.append(("R10", w, rr, "E", d["8月收入万"], 1.1))
        n += 1
    log(f"R10 rewritten {n}")

    # ---- R8: 对冲矩阵全部行(品类裸字面量,客户保留通配) ----
    w = with_retry(lambda: xl.Worksheets("R8-品类增量"))
    exp8 = {}
    for cust in ["石头", "海康威视", "TPLINK", "大华集团", "共进", "兆驰", "创维数字", "小米集团", "追觅", "中兴康讯"]:
        for it in AN2["C_同类对冲矩阵"][cust]:
            exp8[(cust, it["品类"])] = it
    r = 3
    while r < 120:
        cust = rd(w, r, 1)
        cat = rd(w, r, 2)
        if cust and cat and str(cust) in exp8.__str__() or (cust and cat):
            key = (str(cust), str(cat))
            if key in exp8:
                rr = r
                c26 = [("B", cc(f"A{rr}")), ("H", lit(str(cat)))] + W26
                c25 = [("B", cc(f"A{rr}")), ("H", lit(str(cat)))] + W25
                sf(w, rr, 3, f"=ROUND({sumifs('N', c26)}/10000,1)")
                sf(w, rr, 4, f"=ROUND({sumifs('N', c25)}/10000,1)")
                VER.append(("R8", w, rr, "C", exp8[key]["利润26"]))
        r += 1
    log("R8 rewritten")

    # ---- R6c: 品类TOP3全部行 ----
    w = with_retry(lambda: xl.Worksheets("R6-SKU与客户"))
    exp6c = RC["客户品类TOP3_2026YTD"]
    r = 1
    while r < 60:
        cust = rd(w, r, 1)
        cat = rd(w, r, 2)
        if cust in ("追觅", "兆驰", "共进") and cat:
            found = next((it for it in exp6c[str(cust)] if it["品类"] == str(cat)), None)
            if found:
                rr = r
                c26 = [("B", cc(f"A{rr}")), ("H", lit(str(cat)))] + W26
                ctot = [("B", cc(f"A{rr}"))] + W26
                sf(w, rr, 3, f"=ROUND({sumifs('M', c26)}/10000,1)")
                sf(w, rr, 4, f"=ROUND({sumifs('N', c26)}/10000,1)")
                sf(w, rr, 6, f"=ROUND(C{rr}/({sumifs('M', ctot)}/10000),3)")
                VER.append(("R6c", w, rr, "C", found["收入万"]))
        r += 1
    log("R6c rewritten")

    # ---- R3(报告补充): 含~品类行 ----
    w = with_retry(lambda: xl.Worksheets("R-报告补充"))
    zx = {it["品类"]: it for it in AN2["C_同类对冲矩阵"]["中兴康讯"]}
    zx_rev = {"DCDC-18V-降压2~4A": (1939.0, -225.3), "LDO通用/双通道": (96.0, 26.7), "PSE": (93.0, 32.5),
              "DCDC-18V-降压5~12A": (88.0, 22.5), "USB单通道/多通道2.4A/3A": (28.0, 12.4)}
    r = 19
    while r <= 26:
        cat = rd(w, r, 1)
        if cat and str(cat) in zx_rev:
            rr = r
            c26 = [("B", '"*中兴康讯*"'), ("H", lit(str(cat)))] + W26
            sf(w, rr, 2, f"=ROUND({sumifs('M', c26)}/10000,1)")
            sf(w, rr, 3, f"=ROUND({sumifs('N', c26)}/10000,1)")
            VER.append(("R3", w, rr, "B", zx_rev[str(cat)][0]))
            VER.append(("R3", w, rr, "C", zx_rev[str(cat)][1]))
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
    for item in VER:
        blk, ws, row, colletter = item[0], item[1], item[2], item[3]
        expect = item[4]
        tol = item[5] if len(item) > 5 else None
        v = with_retry(lambda: ws.Cells(row, colletter).Value)
        try:
            vf = float(v)
        except (TypeError, ValueError):
            fails += 1
            log(f"FAIL {blk} {ws.Name}!{colletter}{row} expect={expect} actual=非数值({v})")
            continue
        t = tol if tol else (1.1 if abs(expect) >= 20 else 0.16)
        if abs(vf - expect) > t:
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
print("FIX_TILDE2_DONE")
