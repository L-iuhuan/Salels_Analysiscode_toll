# -*- coding: utf-8 -*-
r"""底稿系统整理: R3全块公式重写(真实总计+裸字面量)/R2并入R9指针/R5公式化/0-说明合并 + 全量验证"""
import time
import pythoncom
import pywintypes
import win32com.client as win32

BK = r"E:\3-其他资料\数据分析\月度分析模板_8月报告副本.xlsx"
LOGF = r"C:\Users\910373\AppData\Local\Temp\opencode\build\reorg_log.txt"

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
W26 = [("A", dt_lo(2026, 1)), ("A", dt_hi(2026, 8))]
W25 = [("A", dt_lo(2025, 1)), ("A", dt_hi(2025, 8))]
def lit(s):
    return '"' + s + '"'
def sumifs(tcol, conds):
    parts = [C(tcol)]
    for col, crit in conds:
        parts.append(C(col))
        parts.append(crit)
    return "SUMIFS(" + ",".join(parts) + ")"
ZX = lit("*中兴康讯*")

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
    ws = with_retry(lambda: xl.Worksheets("R-报告补充"))

    def sv(r, c, v):
        rg = with_retry(lambda: ws.Cells(r, c))
        prop = "Formula" if isinstance(v, str) and v.startswith("=") else "Value"
        with_retry(lambda: rg.__setattr__(prop, v))

    def rv(r, c):
        return with_retry(lambda: ws.Cells(r, c).Value)

    # ---- 1) R2 → 指针 ----
    with_retry(lambda: ws.Range("A7:H15").Clear)
    sv(6, 1, "R2 月度序列已并入 R9-长周期(单一数据源,2026年各月四因子与R9逐位一致已验证;避免双处维护)")
    log("R2 -> pointer")

    # ---- 2) R3 全块公式重写(真实总计+裸字面量) ----
    sv(17, 1, "R3 中兴康讯×品类(2026年1-8月YTD)——SUMIFS活算;利润列与R8-品类增量'中兴康讯'行同源")
    for c, h in enumerate(["品类", "收入(万)", "利润(万)", "毛利率", "占中兴收入比"], 1):
        sv(18, c, h)
    cats = ["DCDC-18V-降压2~4A", "LDO通用/双通道", "PSE", "DCDC-18V-降压5~12A",
            "USB单通道/多通道2.4A/3A", "DCDC-5V-降压4~10A", "DCDC-5V-降压1~3A", "步进驱动细分/微细分"]
    exp = {"DCDC-18V-降压2~4A": (1939, -225.3), "LDO通用/双通道": (96, 26.7), "PSE": (93.1, 32.5),
           "DCDC-18V-降压5~12A": (88.3, 22.5), "USB单通道/多通道2.4A/3A": (27.9, 12.4),
           "DCDC-5V-降压4~10A": (6.2, 1.2), "DCDC-5V-降压1~3A": (1.3, 0.5), "步进驱动细分/微细分": (1.1, 0.6)}
    r = 19
    for cat in cats:
        sv(r, 1, cat)
        conds = [("B", ZX), ("H", lit(cat))] + W26
        sv(r, 2, f"=ROUND({sumifs('M', conds)}/10000,1)")
        sv(r, 3, f"=ROUND({sumifs('N', conds)}/10000,1)")
        sv(r, 4, f"=IF(B{r}=0,\"\",ROUND(C{r}/B{r},4))")
        sv(r, 5, f"=ROUND(B{r}/$B$27,3)")
        if cat in exp:
            VER.append(("R3", r, "B", exp[cat][0]))
            VER.append(("R3", r, "C", exp[cat][1]))
        r += 1
    sv(27, 1, "合计(真实总计,含未列小品类)")
    sv(27, 2, f"=ROUND({sumifs('M', [('B', ZX)] + W26)}/10000,1)")
    sv(27, 3, f"=ROUND({sumifs('N', [('B', ZX)] + W26)}/10000,1)")
    sv(27, 4, "=ROUND(C27/B27,4)")
    sv(27, 5, "=1")
    VER.append(("R3合计", 27, "B", 2259.8, 1.1))
    VER.append(("R3合计", 27, "C", -126.2, 1.1))
    sv(28, 1, "去年同期")
    sv(28, 2, f"=ROUND({sumifs('M', [('B', ZX)] + W25)}/10000,1)")
    sv(28, 3, f"=ROUND({sumifs('N', [('B', ZX)] + W25)}/10000,1)")
    VER.append(("R3去年", 28, "B", 1315.3, 1.1))
    log("R3 rewritten")

    # ---- 3) R5 公式化 ----
    sv(43, 1, "R5 KA客户利润同比(2026YTD vs 2025YTD)——SUMIFS活算;与R6-SKU与客户!R6b同源")
    for c, h in enumerate(["客户", "YTD利润(万)", "利润同比(万)"], 1):
        sv(44, c, h)
    r5c = ["追觅", "中兴康讯", "小米集团", "长虹集团", "海信集团", "烽火", "富士康集团", "TCL集团",
           "石头", "海康威视", "大华集团", "TPLINK", "创维数字"]
    exp5 = {"追觅": (657, -504.5), "中兴康讯": (-126, -333.0), "小米集团": (303, -221.4), "长虹集团": (200, -63.4),
            "海信集团": (215, -37.4), "烽火": (2, -9.3), "富士康集团": (25, -8.7), "TCL集团": (156, 13.8),
            "石头": (999, 330.5), "海康威视": (627, 322.6), "大华集团": (334, 86.7), "TPLINK": (375, 83.7),
            "创维数字": (310, 81.6)}
    r = 45
    for cust in r5c:
        sv(r, 1, cust)
        c26 = [("B", lit(cust))] + W26
        c25 = [("B", lit(cust))] + W25
        sv(r, 2, f"=ROUND({sumifs('N', c26)}/10000,0)")
        sv(r, 3, f"=ROUND(({sumifs('N', c26)}-{sumifs('N', c25)})/10000,1)")
        VER.append(("R5", r, "B", exp5[cust][0], 1.1))
        VER.append(("R5", r, "C", exp5[cust][1], 1.1))
        r += 1
    log("R5 formula-ized")

    # ---- 4) 0-说明合并 ----
    w0 = with_retry(lambda: xl.Worksheets("0-说明"))
    lr = with_retry(lambda: w0.UsedRange.Rows.Count)

    def sv0(r, c, v):
        rg = with_retry(lambda: w0.Cells(r, c))
        with_retry(lambda: rg.__setattr__("Value", v))

    sv0(54, 1, "2026-09-09 底稿重构: R-报告补充保留R1(四因子桥)/R3(中兴品类,真实总计口径)/R4(KA新增SKU)/R5(KA利润TOP,已公式化);R2月度序列并入R9-长周期(单一数据源);R6-R12为独立sheet(R6-SKU与客户/R7-中兴月度/R8-品类增量/R9-长周期/R10-量效应/R11-音频与渗透/R12-新品与快照)。聚合数据均为SUMIFS活公式(源=D-镜像);量/结构拆分与SKU增减对比由主模板VBA重算(同10-毛利桥/11-SKU变化);品类条件须用裸字面量(名称含~时勿加*通配,Excel会将~作转义符)。")
    with_retry(lambda: w0.Cells(55, 1).Clear)
    log("0-说明 consolidated")

    # ---- 验证 ----
    with_retry(lambda: ws.Calculate())
    time.sleep(2)
    fails = 0
    for item in VER:
        blk, row, col, expect = item[0], item[1], item[2], item[3]
        tol = item[4] if len(item) > 4 else (1.1 if abs(expect) >= 20 else 0.16)
        v = rv(row, col)
        try:
            vf = float(v)
        except (TypeError, ValueError):
            fails += 1
            log(f"FAIL {blk} r{row}c{col} expect={expect} actual=非数值({v})")
            continue
        if abs(vf - expect) > tol:
            fails += 1
            log(f"FAIL {blk} r{row}c{col} expect={expect} actual={round(vf, 2)}")
    log(f"R-报告补充 verify total={len(VER)} fails={fails}")

    # R5 vs R6b 同源精确对比(4家重叠)
    w6 = with_retry(lambda: xl.Worksheets("R6-SKU与客户"))
    r6b = {}
    for r in range(9, 16):
        cu = with_retry(lambda: w6.Cells(r, 1).Value)
        r6b[str(cu)] = (round(float(with_retry(lambda: w6.Cells(r, 3).Value)), 1),
                        round(float(with_retry(lambda: w6.Cells(r, 9).Value)), 1))
    mism = 0
    for r in range(45, 58):
        cu = str(rv(r, 1))
        if cu in r6b:
            b = round(float(rv(r, 2)), 0)
            c = round(float(rv(r, 3)), 1)
            p6, d6 = r6b[cu]
            if abs(b - round(p6, 0)) > 1.0 or abs(c - d6) > 1.0:
                mism += 1
                log(f"FAIL R5vsR6b {cu}: R5=({b},{c}) R6b=({p6},{d6})")
    log(f"R5 vs R6b 同源对比: mismatch={mism}")

    # R3 vs R8 中兴行
    w8 = with_retry(lambda: xl.Worksheets("R8-品类增量"))
    zx8 = {}
    for r in range(3, 80):
        cu = with_retry(lambda: w8.Cells(r, 1).Value)
        if cu == "中兴康讯":
            cat = str(with_retry(lambda: w8.Cells(r, 2).Value))
            zx8[cat] = round(float(with_retry(lambda: w8.Cells(r, 3).Value)), 1)
    mism = 0
    for r in range(19, 27):
        cat = str(rv(r, 1))
        v3 = rv(r, 3)
        try:
            v3f = round(float(v3), 1)
        except (TypeError, ValueError):
            continue
        if cat in zx8 and abs(v3f - zx8[cat]) > 0.6:
            mism += 1
            log(f"FAIL R3vsR8 {cat}: R3={v3f} R8={zx8[cat]}")
    log(f"R3 vs R8 中兴品类利润: overlap={len(zx8)} mismatch={mism}")

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
print("REORG_DONE")
