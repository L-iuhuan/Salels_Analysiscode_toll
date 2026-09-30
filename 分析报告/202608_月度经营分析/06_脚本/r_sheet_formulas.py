# -*- coding: utf-8 -*-
r"""R-报告补充公式化: 聚合块转SUMIFS活公式(源=D-镜像), 写后重算与旧值对拍; 增加及流失/主模板VBA核查"""
import re
import time
import pythoncom
import pywintypes
import win32com.client as win32

BK = r"E:\3-其他资料\数据分析\月度分析模板_8月报告副本.xlsx"
MASTER = r"E:\3-其他资料\数据分析\月度分析模板.xlsm"
LAST = 206900

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

MIR = "'D-镜像'!"
def C(col):
    return f"{MIR}${col}$2:${col}${LAST}"

def dt_lo(y, m):
    return f'">="&DATE({y},{m},1)'

def dt_hi(y, m):
    m2, y2 = (m + 1, y) if m < 12 else (1, y + 1)
    return f'"<"&DATE({y2},{m2},1)'

def win(y1, m1, y2, m2):
    return [( "A", dt_lo(y1, m1)), ("A", dt_hi(y2, m2))]

def sumifs(tcol, conds):
    parts = [C(tcol)]
    for col, crit in conds:
        parts.append(C(col))
        parts.append(crit)
    return "SUMIFS(" + ",".join(parts) + ")"

REV = lambda conds: f"ROUND({sumifs('M', conds)}/10000,{{dp}})"
PFT = lambda conds: f"ROUND({sumifs('N', conds)}/10000,{{dp}})"
QTY = lambda conds: f"ROUND({sumifs('L', conds)},0)"

def custcrit(cell):
    return f'"*"&{cell}&"*"'

LOG = []
pythoncom.CoInitialize()
xl = None
try:
    xl = with_retry(lambda: win32.DispatchEx("Excel.Application"))
    xl.Visible = False
    xl.DisplayAlerts = False
    wb = with_retry(lambda: xl.Workbooks.Open(BK))

    def rd(ws, r, c):
        return with_retry(lambda: ws.Cells(r, c).Value)

    def sv(ws, r, c, v):
        rg = with_retry(lambda: ws.Cells(r, c))
        with_retry(lambda: rg.__setattr__("Formula", v))

    ws = with_retry(lambda: xl.Worksheets("R-报告补充"))

    # ---- 定位锚点(扫A/B列 1..170) ----
    anchors = {}
    for r in range(1, 171):
        a = str(rd(ws, r, 1) or "")
        b = str(rd(ws, r, 2) or "")
        for key, pat in [("R2", "R2 月度序列"), ("R3", "R3 中兴康讯"), ("R5", "R5 KA客户"),
                         ("R6a", "R6a"), ("R6e", "R6e"), ("R7", "R7 中兴康讯月度"),
                         ("R8", "R8 重点客户"), ("R9", "R9 四因子"), ("R10", "R10 量效应"),
                         ("R11a", "R11 音频功放"), ("R12a", "R12a"), ("R12b", "R12b")]:
            if key not in anchors and pat in a:
                anchors[key] = r
    LOG.append(f"anchors: {anchors}")

    plan = []  # (row, col, formula, old, tol)

    def add(r, c, f, tol=0.6):
        old = rd(ws, r, c)
        plan.append((r, c, f, old, tol))

    W26 = [("A", dt_lo(2026, 1)), ("A", dt_hi(2026, 8))]
    W25 = [("A", dt_lo(2025, 1)), ("A", dt_hi(2025, 8))]
    W0807 = None

    # ---- R2 收入/毛利率 ----
    if "R2" in anchors:
        r = anchors["R2"] + 2  # header+1
        while True:
            a = rd(ws, r, 1)
            if not a:
                break
            m = re.match(r"(\d+)月", str(a))
            if m:
                mm = int(m.group(1))
                conds = win(2026, mm, 2026, mm)
                add(r, 2, REV(conds).format(dp=0), 0.6)
                add(r, 3, f"=IF(B{r}=0,\"\",ROUND({sumifs('N', conds)}/10000/B{r},4))", 0.006)
            r += 1

    # ---- R3 品类行 ----
    if "R3" in anchors:
        r = anchors["R3"] + 2
        first = r
        while True:
            a = rd(ws, r, 1)
            if not a or str(a) in ("合计", "去年同期"):
                break
            cat = str(a)
            conds26 = [("H", f'"{cat}"'), ("B", '"*中兴康讯*"')] + W26
            conds25 = [("H", f'"{cat}"'), ("B", '"*中兴康讯*"')] + W25
            add(r, 2, REV(conds26).format(dp=1), 0.6)
            add(r, 3, PFT(conds26).format(dp=1), 0.6)
            add(r, 4, f"=IF(B{r}=0,\"\",ROUND(C{r}/B{r},4))", 0.006)
            add(r, 5, f"=ROUND(B{r}/$B${first + 8},3)", 0.006)
            r += 1
        lastc = r - 1
        add(r, 2, f"=ROUND(SUM(B{first}:B{lastc}),1)", 0.6)
        add(r, 3, f"=ROUND(SUM(C{first}:C{lastc}),1)", 0.6)
        r += 1
        if str(rd(ws, r, 1) or "") == "去年同期":
            add(r, 2, REV([("B", '"*中兴康讯*"')] + W25).format(dp=1), 0.6)
            add(r, 3, PFT([("B", '"*中兴康讯*"')] + W25).format(dp=1), 0.6)

    # ---- R5 客户利润 ----
    if "R5" in anchors:
        r = anchors["R5"] + 2
        while True:
            a = rd(ws, r, 1)
            if not a:
                break
            c26 = [("B", f'"{a}"')] + W26
            c25 = [("B", f'"{a}"')] + W25
            add(r, 2, PFT(c26).format(dp=0), 0.6)
            add(r, 3, f"=ROUND(B{r}-({sumifs('N', c25)}/10000),1)", 0.6)
            r += 1

    # ---- R6a 净影响列 ----
    if "R6a" in anchors:
        r = anchors["R6a"] + 2
        while True:
            a = rd(ws, r, 1)
            if not a:
                break
            add(r, 10, f"=F{r}-H{r}", 0.01)
            add(r, 11, f"=G{r}-I{r}", 0.01)
            r += 1

    # ---- R6e 占新品收入% ----
    if "R6e" in anchors:
        r = anchors["R6e"] + 2
        tot = sumifs("M", [("K", '"是"')] + W26) + "/10000"
        while True:
            a = rd(ws, r, 1)
            if not a:
                break
            add(r, 3, f"=ROUND(B{r}/({tot}),3)", 0.006)
            r += 1

    # ---- R7 中兴月度 ----
    if "R7" in anchors:
        r = anchors["R7"] + 2
        while True:
            a = rd(ws, r, 1)
            m = re.match(r"(20\d\d)-(\d\d)", str(a or ""))
            if not m:
                if not a:
                    break
                r += 1
                continue
            y, mm = int(m.group(1)), int(m.group(2))
            conds = [("B", '"*中兴康讯*"')] + win(y, mm, y, mm)
            add(r, 2, REV(conds).format(dp=1), 0.6)
            add(r, 3, PFT(conds).format(dp=1), 0.6)
            r += 1

    # ---- R8 对冲矩阵 + 新品案例 + TMI6011 ----
    if "R8" in anchors:
        r = anchors["R8"] + 2
        while True:
            a = rd(ws, r, 1)
            if a is None or str(a).startswith("--") or str(a).startswith("R"):
                break
            cu, cat = str(a), str(rd(ws, r, 2) or "")
            if cat:
                c26 = [("B", custcrit(f"A{r}")), ("H", f"B{r}")] + W26
                c25 = [("B", custcrit(f"A{r}")), ("H", f"B{r}")] + W25
                add(r, 3, PFT(c26).format(dp=1), 0.6)
                add(r, 4, PFT(c25).format(dp=1), 0.6)
                add(r, 5, f"=ROUND(C{r}-D{r},1)", 0.01)
            r += 1
        # 新品案例/TMI6011: label col A like "新品:TMI8180I" / "TMI6011", col B=客户, col C=收入
        while r < anchors.get("R9", 170):
            a = str(rd(ws, r, 1) or "")
            m = re.search(r"(TMI\w+|TME\w+|STI\w+)", a)
            cust = rd(ws, r, 2)
            if m and cust:
                sku = m.group(1)
                conds = [("J", f'"{sku}"'), ("B", custcrit(f"B{r}"))] + W26
                add(r, 3, REV(conds).format(dp=1), 0.6)
            r += 1

    # ---- R9 收入/毛利率 ----
    if "R9" in anchors:
        r = anchors["R9"] + 2
        while True:
            a = rd(ws, r, 1)
            m = re.match(r"(20\d\d)-(\d\d)", str(a or ""))
            if not m:
                if not a:
                    break
                r += 1
                continue
            y, mm = int(m.group(1)), int(m.group(2))
            conds = win(y, mm, y, mm)
            add(r, 8, REV(conds).format(dp=0), 0.6)
            add(r, 9, f"=IF(H{r}=0,\"\",ROUND({sumifs('N', conds)}/10000/H{r},4))", 0.006)
            r += 1

    # ---- R10 品类/客户环比 + MM ----
    if "R10" in anchors:
        r = anchors["R10"] + 2
        W8 = [("A", dt_lo(2026, 8)), ("A", dt_hi(2026, 8))]
        W7 = [("A", dt_lo(2026, 7)), ("A", dt_hi(2026, 7))]
        while True:
            a = rd(ws, r, 2)
            if a is None or str(rd(ws, r, 1) or "").startswith("--"):
                break
            name = str(a)
            if name and name not in ("品类", "客户", "方向"):
                # 品类块: C收入变动 E 8月 F 7月 (col B=品类) ; 客户块同列但B=客户
                ismm = str(rd(ws, r, 1) or "")
                # 用品类列匹配(H), 客户块也尝试B列—通过上一行header判断
                hdr = str(rd(ws, r - 1 if r > 1 else r, 2) or "")
                # 简化: 品类块在前(检测row中col2值含'DCDC|POE|USB|车规|PSE|30V|H桥|LED|LDO'), 客户块在后
                if re.search(r"DCDC|POE|USB|车规|PSE|30V|H桥|LED|LDO", name):
                    c8 = [("H", f'B{r}')] + W8
                    c7 = [("H", f'B{r}')] + W7
                else:
                    c8 = [("B", custcrit(f'B{r}'))] + W8
                    c7 = [("B", custcrit(f'B{r}'))] + W7
                add(r, 3, f"=ROUND(({sumifs('M', c8)}-{sumifs('M', c7)})/10000,1)", 0.6)
                add(r, 5, REV(c8).format(dp=1), 0.6)
                add(r, 6, REV(c7).format(dp=1), 0.6)
            r += 1
        # MM块: 收入26/25/利润26/25 (col A标签 col B值)
        mmstar = '"MM*"'
        mr = r
        while mr < anchors.get("R11a", 170):
            lab = str(rd(ws, mr, 1) or "")
            if lab.startswith("收入26"):
                add(mr, 2, f"=ROUND({sumifs('M', [('C', mmstar)] + W26)}/10000,0)", 0.6)
            elif lab.startswith("收入25"):
                add(mr, 2, f"=ROUND({sumifs('M', [('C', mmstar)] + W25)}/10000,0)", 0.6)
            elif lab.startswith("利润26"):
                add(mr, 2, f"=ROUND({sumifs('N', [('C', mmstar)] + W26)}/10000,0)", 0.6)
            elif lab.startswith("利润25"):
                add(mr, 2, f"=ROUND({sumifs('N', [('C', mmstar)] + W25)}/10000,0)", 0.6)
            mr += 1

    # ---- R11a 音频分产品: 重构为公式数值块 ----
    if "R11a" in anchors:
        r0 = anchors["R11a"]  # 标题行, 下一行header, 再下一行起数据(旧: 13列字符串)
        hdr_r = r0 + 1
        skus = []
        rr = hdr_r + 1
        while True:
            a = rd(ws, rr, 1)
            if not a:
                break
            skus.append((rr, str(a)))
            rr += 1
        # 重写header
        heads = ["SKU", "1月", "2月", "3月", "4月", "5月", "6月", "7月", "8月", "YTD收入(万)", "毛利率1-5月", "毛利率6-8月", "TOP客户(静态)"]
        for c, h in enumerate(heads, 1):
            rg = with_retry(lambda: ws.Cells(hdr_r, c))
            with_retry(lambda: rg.__setattr__("Value", h))
        for rr, sku in skus:
            topc = rd(ws, rr, 13)
            for m in range(1, 9):
                conds = [("F", '"音频功放"'), ("J", f'"{sku}"')] + win(2026, m, 2026, m)
                rg = with_retry(lambda: ws.Cells(rr, m + 1))
                with_retry(lambda: rg.__setattr__("Formula", f"=ROUND({sumifs('M', conds)}/10000,0)"))
            cy = [("F", '"音频功放"'), ("J", f'"{sku}"')] + W26
            c15 = [("F", '"音频功放"'), ("J", f'"{sku}"'), ("A", dt_lo(2026, 1)), ("A", dt_hi(2026, 5))]
            c68 = [("F", '"音频功放"'), ("J", f'"{sku}"'), ("A", dt_lo(2026, 6)), ("A", dt_hi(2026, 8))]
            with_retry(lambda: ws.Cells(rr, 10).__setattr__("Formula", f"=ROUND({sumifs('M', cy)}/10000,1)"))
            with_retry(lambda: ws.Cells(rr, 11).__setattr__("Formula", f"=ROUND({sumifs('N', c15)}/{sumifs('M', c15)},4)"))
            with_retry(lambda: ws.Cells(rr, 12).__setattr__("Formula", f"=ROUND({sumifs('N', c68)}/{sumifs('M', c68)},4)"))
            rg = with_retry(lambda: ws.Cells(rr, 13))
            with_retry(lambda: rg.__setattr__("Value", topc if topc else ""))
        LOG.append(f"R11a rebuilt rows={len(skus)}")

    # ---- R12a/R12b ----
    for key, col_sku in (("R12a", 1),):
        if key in anchors:
            r = anchors[key] + 2
            while True:
                sku = rd(ws, r, 1)
                if not sku or str(sku).startswith("R1"):
                    break
                conds_y = [("J", f'A{r}')] + W26
                conds_8 = [("J", f'A{r}')] + [("A", dt_lo(2026, 8)), ("A", dt_hi(2026, 8))]
                add(r, 2, REV(conds_y).format(dp=1), 0.6)
                add(r, 3, REV(conds_8).format(dp=1), 0.6)
                r += 1
    if "R12b" in anchors:
        r = anchors["R12b"] + 2
        while True:
            a = rd(ws, r, 1)
            m = re.match(r"(20\d\d)-(\d\d)", str(a or ""))
            if not m:
                if not a:
                    break
                r += 1
                continue
            y, mm = int(m.group(1)), int(m.group(2))
            conds = [("F", '"音频功放"')] + win(y, mm, y, mm)
            add(r, 2, REV(conds).format(dp=1), 0.6)
            add(r, 3, PFT(conds).format(dp=1), 0.6)
            add(r, 4, f"=IF(B{r}=0,\"\",ROUND(C{r}/B{r},4))", 0.006)
            r += 1

    # ---- 顶部说明 ----
    rg = with_retry(lambda: ws.Cells(1, 8))
    with_retry(lambda: rg.__setattr__("Value", "注:本表数值单元格多为SUMIFS活公式(源=D-镜像,单位万);量/结构拆分与SKU增减对比由主模板VBA重算机制生成(同10-毛利桥/11-SKU变化),详见0-说明。"))

    # ---- 写公式 ----
    for r, c, f, old, tol in plan:
        sv(ws, r, c, "=" + f if not f.startswith("=") else f)
    LOG.append(f"formulas written: {len(plan)}")

    # ---- 重算并回读对拍 ----
    with_retry(lambda: xl.CalculateFull())
    time.sleep(3)
    mism = []
    checked = 0
    for r, c, f, old, tol in plan:
        if old is None:
            continue
        try:
            ov = float(old)
        except (TypeError, ValueError):
            continue
        nv = rd(ws, r, c)
        try:
            nvf = float(nv)
        except (TypeError, ValueError):
            mism.append((r, c, old, nv))
            continue
        checked += 1
        if abs(nvf - ov) > max(tol, abs(ov) * 0.02):
            mism.append((r, c, round(ov, 2), round(nvf, 2)))
    LOG.append(f"compare checked={checked} mismatch={len(mism)}")
    for mm in mism[:15]:
        LOG.append(f"  MISM r{mm[0]}c{mm[1]} old={mm[2]} new={mm[3]}")

    # ---- 增加及流失 注记 ----
    wz = with_retry(lambda: xl.Worksheets("增加及流失"))
    lr = with_retry(lambda: wz.UsedRange.Rows.Count)
    rg = with_retry(lambda: wz.Cells(lr + 2, 1))
    with_retry(lambda: rg.__setattr__("Value", "注:本表为主模板VBA重算表(与10-毛利桥/11-SKU变化同机制,窗口=近12月vs前12月);本副本(.xlsx)为2026-09-09快照,重算请在主模板(月度分析模板.xlsm)执行。"))
    LOG.append(f"增加及流失 note at row {lr + 2}")

    with_retry(lambda: wb.Save())
    with_retry(lambda: wb.Close(False))
finally:
    if xl is not None:
        try:
            xl.Quit()
        except Exception:
            pass
    pythoncom.CoUninitialize()

# ---- 主模板 VBA 核查(只读) ----
pythoncom.CoInitialize()
xl = None
try:
    xl = with_retry(lambda: win32.DispatchEx("Excel.Application"))
    xl.Visible = False
    xl.DisplayAlerts = False
    wb = with_retry(lambda: xl.Workbooks.Open(MASTER, ReadOnly=True))
    try:
        wz = with_retry(lambda: xl.Worksheets("增加及流失"))
        lr = with_retry(lambda: wz.UsedRange.Rows.Count)
        tail = []
        for r in range(max(1, lr - 2), lr + 1):
            tail.append(str(rd(wz, r, 1) if False else with_retry(lambda: wz.Cells(r, 1).Value)))
        LOG.append(f"master 增加及流失 rows={lr} tail={tail}")
    except Exception as e:
        LOG.append(f"master 增加及流失 ERR {e}")
    try:
        wbv = with_retry(lambda: xl.Workbooks.Count)
        hasvb = True
        try:
            _ = with_retry(lambda: wb.VBProject.Name)
        except Exception:
            hasvb = "no-access(受保护,通常代表有VBA)"
        LOG.append(f"master VBProject: {hasvb}")
    except Exception as e:
        LOG.append(f"master VB ERR {e}")
    with_retry(lambda: wb.Close(False))
finally:
    if xl is not None:
        try:
            xl.Quit()
        except Exception:
            pass
    pythoncom.CoUninitialize()

open(r"C:\Users\910373\AppData\Local\Temp\opencode\build\rformula_log.txt", "w", encoding="utf-8").write("\n".join(str(x) for x in LOG))
print("RFORMULA_DONE")
