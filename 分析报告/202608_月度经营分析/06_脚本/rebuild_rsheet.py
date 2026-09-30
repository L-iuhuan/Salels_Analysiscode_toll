# -*- coding: utf-8 -*-
r"""R-报告补充整体重建: 清空59行以下→游标顺序重写R6-R12(公式+静态带注)→重算→全块验证"""
import json
import re
import time
import pythoncom
import pywintypes
import win32com.client as win32

BK = r"E:\3-其他资料\数据分析\月度分析模板_8月报告副本.xlsx"
AN2 = json.load(open(r"C:\Users\910373\AppData\Local\Temp\opencode\build\analysis2.json", encoding="utf-8"))
AN3 = json.load(open(r"C:\Users\910373\AppData\Local\Temp\opencode\build\analysis3.json", encoding="utf-8"))
AN4 = json.load(open(r"C:\Users\910373\AppData\Local\Temp\opencode\build\analysis4.json", encoding="utf-8"))

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
def sumifs(tcol, conds):
    parts = [C(tcol)]
    for col, crit in conds:
        parts.append(C(col))
        parts.append(crit)
    return "SUMIFS(" + ",".join(parts) + ")"
def rev(conds, dp=1):
    return f"=ROUND({sumifs('M', conds)}/10000,{dp})"
def pft(conds, dp=1):
    return f"=ROUND({sumifs('N', conds)}/10000,{dp})"
def qty(conds):
    return f"=ROUND({sumifs('L', conds)},0)"
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

LOG = []
VER = []  # (block, cell, expect, actual, ok)
pythoncom.CoInitialize()
xl = None
try:
    xl = with_retry(lambda: win32.DispatchEx("Excel.Application"))
    xl.Visible = False
    xl.DisplayAlerts = False
    wb = with_retry(lambda: xl.Workbooks.Open(BK))
    ws = with_retry(lambda: xl.Worksheets("R-报告补充"))

    def sv(r, c, v):
        rg = with_retry(lambda: ws.Cells(r, c))
        with_retry(lambda: rg.__setattr__("Formula" if isinstance(v, str) and v.startswith("=") else "Value", v))

    def rv(r, c):
        return with_retry(lambda: ws.Cells(r, c).Value)

    # ---- 清空59行以下 ----
    with_retry(lambda: ws.Range("A59:AZ260").Clear)
    LOG.append("cleared A59:AZ260")

    r = 59
    def title(t):
        global r
        sv(r, 1, t)
        r += 1

    def header(hs):
        global r
        for c, h in enumerate(hs, 1):
            sv(r, c, h)
        r += 1

    def blk(name):
        LOG.append(f"{name} rows {r}")

    # R6a SKU汇总+净影响公式
    title("R6a 表14完整口径(11-SKU变化数据 + 净影响=新增-流失公式)")
    header(["客户群", "客户数", "新增SKU", "流失SKU", "净增减", "新增收入(万)", "新增利润(万)", "流失收入(万)", "流失利润(万)", "净收入影响(万)", "净利润影响(万)"])
    for row in [["KA+AA合计", 39, 151, 66, 85, 2162, 845, 167, 83], ["KA", 18, 82, 35, 47, 1783, 713, 71, 31], ["AA", 21, 69, 31, 38, 379, 132, 96, 52]]:
        for c, v in enumerate(row, 1):
            sv(r, c, v)
        sv(r, 10, f"=F{r}-H{r}")
        sv(r, 11, f"=G{r}-I{r}")
        VER.append(("R6a", f"J{r}", row[5] - row[7], None))
        r += 1
    r += 1

    # R6b 客户YTD对比(全公式)
    title("R6b 客户YTD对比(2026年1-8月 vs 2025年1-8月)——SUMIFS活算")
    header(["客户", "YTD26收入(万)", "YTD26利润(万)", "YTD26毛利率", "去年收入(万)", "去年利润(万)", "去年毛利率", "收入同比", "利润同比(万)"])
    exp6b = AN2["目标客户YTD对比"]
    for cust in ["石头", "海康威视", "追觅", "兆驰", "共进", "安克创新", "中兴康讯"]:
        sv(r, 1, cust)
        c26 = [("B", cc(f"A{r}"))] + W26
        c25 = [("B", cc(f"A{r}"))] + W25
        sv(r, 2, rev(c26, 1)); sv(r, 3, pft(c26, 1))
        sv(r, 4, f"=IF(B{r}=0,\"\",ROUND(C{r}/B{r},4))")
        sv(r, 5, rev(c25, 1)); sv(r, 6, pft(c25, 1))
        sv(r, 7, f"=IF(E{r}=0,\"\",ROUND(F{r}/E{r},4))")
        sv(r, 8, f"=IF(E{r}=0,\"\",ROUND(B{r}/E{r}-1,4))")
        sv(r, 9, f"=ROUND(C{r}-F{r},1)")
        e = exp6b[cust]
        VER.append(("R6b", f"B{r}", e["YTD26收入万"], None))
        VER.append(("R6b", f"C{r}", e["YTD26利润万"], None))
        r += 1
    r += 1

    # R6c 品类TOP3(公式)
    title("R6c 追觅/兆驰/共进 品类TOP3(2026年1-8月)——SUMIFS活算")
    header(["客户", "品类", "收入(万)", "利润(万)", "占比", "毛利率"])
    exp6c = AN2["客户品类TOP3_2026YTD"]
    totcell = {}
    first = {}
    for cust in ("追觅", "兆驰", "共进"):
        first[cust] = r
        for it in exp6c[cust]:
            sv(r, 1, cust)
            sv(r, 2, it["品类"])
            conds = [("B", cc(f"A{r}")), ("H", f"B{r}")] + W26
            sv(r, 3, rev(conds, 1))
            sv(r, 4, pft(conds, 1))
            VER.append(("R6c", f"C{r}", it["收入万"], None))
            r += 1
        totcell[cust] = r - 3  # 第一品类即最大,占比以三行合计近似注释
    # 占比公式(对该客户三行合计)
    for cust in ("追觅", "兆驰", "共进"):
        fr = first[cust]
        for rr2 in range(fr, fr + 3):
            sv(rr2, 5, f"=ROUND(C{rr2}/SUM(C{fr}:C{fr + 2}),3)")
            sv(rr2, 6, f"=IF(C{rr2}=0,\"\",ROUND(D{rr2}/C{rr2},4))")
    r += 1

    # R6d 8月小品类(公式)
    title("R6d 8月小品类毛利率核实(正文'音频功放/电脑&计算'出处)——SUMIFS活算")
    header(["品类(产品线)", "8月收入(万)", "8月毛利率"])
    for nm, col, crit in [("音频功放", "F", '"音频功放"'), ("电脑&计算(品类前缀)", "H", '"电脑&计算*"')]:
        sv(r, 1, nm)
        conds = [(col, crit)] + winp(2026, 8, 2026, 8)
        sv(r, 2, rev(conds, 1))
        sv(r, 3, f"=IF(B{r}=0,\"\",ROUND({sumifs('N', conds)}/{sumifs('M', conds)},4))")
        r += 1
    VER.append(("R6d", f"B{r - 2}", 52.9, None))
    r += 1

    # R6e 应用领域新品占比(公式)
    title("R6e 应用领域新品结构(表13)——SUMIFS活算,渗透度=新品收入/该领域收入")
    header(["领域", "新品收入(万)", "占新品收入%", "新品毛利率", "渗透度"])
    tot_f = f"({sumifs('M', [('K', '\"是\"'.replace(chr(92), ''))] + W26)}/10000)"
    tot_f = f"({sumifs('M', [('K', chr(34) + '是' + chr(34))] + W26)}/10000)"
    dn = AN3["D_渗透矩阵"]
    doms = ["安防", "网通", "智能清洁", "汽车电子", "充电头"]
    for d in doms:
        sv(r, 1, d)
        cn = [("E", cc(f"A{r}")), ("K", chr(34) + "是" + chr(34))] + W26
        ca = [("E", cc(f"A{r}"))] + W26
        sv(r, 2, rev(cn, 1))
        sv(r, 3, f"=ROUND(B{r}/{tot_f},3)")
        sv(r, 4, f"=IF(B{r}=0,\"\",ROUND({sumifs('N', cn)}/{sumifs('M', cn)},4))")
        sv(r, 5, f"=ROUND(B{r}/({sumifs('M', ca)}/10000),3)")
        r += 1
    r += 1

    sv(r, 1, "R6f KA其他品类推导: SKU数=82-38=44, 收入=1783-1671=112(万), 利润=713-694=19(万) (R4合计 vs 11-SKU变化KA行)")
    r += 2

    # R7 中兴月度(公式)
    title("R7 中兴康讯月度损益(万)——SUMIFS活算")
    header(["年月", "收入(万)", "利润(万)"])
    exp7 = AN2["A_中兴康讯月度"]
    for ym in sorted(exp7):
        y, m = int(ym[:4]), int(ym[5:7])
        sv(r, 1, ym)
        conds = [("B", '"*中兴康讯*"')] + winp(y, m, y, m)
        sv(r, 2, rev(conds, 1))
        sv(r, 3, pft(conds, 1))
        VER.append(("R7", f"B{r}", exp7[ym]["收入万"], None))
        r += 1
    r += 1

    # R8 对冲矩阵(公式)
    title("R8 重点客户×品类利润增量(2026YTD vs 2025YTD,万)——SUMIFS活算")
    header(["客户", "品类", "利润26", "利润25", "增量"])
    exp8 = AN2["C_同类对冲矩阵"]
    for cust in ["石头", "海康威视", "TPLINK", "大华集团", "共进", "兆驰", "创维数字", "小米集团", "追觅", "中兴康讯"]:
        for it in exp8[cust]:
            sv(r, 1, cust)
            sv(r, 2, it["品类"])
            c26 = [("B", cc(f"A{r}")), ("H", f"B{r}")] + W26
            c25 = [("B", cc(f"A{r}")), ("H", f"B{r}")] + W25
            sv(r, 3, pft(c26, 1))
            sv(r, 4, pft(c25, 1))
            sv(r, 5, f"=ROUND(C{r}-D{r},1)")
            r += 1
    r += 1

    # R8b 新品案例客户(公式)
    title("R8b 新品案例代表客户(2026YTD收入万)——SUMIFS活算")
    header(["SKU", "客户", "收入(万)", "利润(万)"])
    exp8b = AN4["音频功放_分产品_客户"] if False else AN2["B_新品案例客户"]
    for sku, custs in exp8b.items():
        for it in custs:
            if it["收入万"] <= 0:
                continue
            sv(r, 1, sku)
            sv(r, 2, it["客户"])
            conds = [("J", f'"*{sku}*"'), ("B", cc(f"B{r}"))] + W26
            sv(r, 3, rev(conds, 1))
            sv(r, 4, pft(conds, 1))
            VER.append(("R8b", f"C{r}", it["收入万"], None))
            r += 1
    r += 1

    # R8c TMI6011(公式)
    title("R8c TMI6011客户(2026YTD)——SUMIFS活算")
    header(["型号", "客户", "收入(万)", "利润(万)"])
    for cust, v in AN2["G_TMI6011_客户"].items():
        sv(r, 1, "TMI6011")
        sv(r, 2, cust)
        conds = [("J", f'"*TMI6011*"'), ("B", cc(f"B{r}"))] + W26
        sv(r, 3, rev(conds, 1))
        sv(r, 4, pft(conds, 1))
        VER.append(("R8c", f"C{r}", v[0], None))
        r += 1
    r += 1

    # R9 长周期(收入/毛利率公式 + 四因子静态带注)
    title("R9 四因子长周期序列(2024-02至2026-08,万)——收入/毛利率为SUMIFS活算;量/结构/价/成本/dGP为主模板VBA重算机制产物(静态快照,锚点=10-毛利桥)")
    header(["年月", "可比SKU数", "量", "结构", "价", "成本", "dGP", "收入(万)", "毛利率"])
    for s in AN2["D_四因子长周期"]:
        y, m = int(s["月"][:4]), int(s["月"][5:7])
        sv(r, 1, s["月"])
        for c, k in [(2, "SKU"), (3, "量"), (4, "结构"), (5, "价"), (6, "成本"), (7, "dGP")]:
            sv(r, c, s[k])
        conds = winp(y, m, y, m)
        sv(r, 8, rev(conds, 0))
        sv(r, 9, f"=IF(H{r}=0,\"\",ROUND({sumifs('N', conds)}/10000/H{r},4))")
        VER.append(("R9", f"H{r}", s["收入"], None))
        r += 1
    r += 1

    # R10 量效应解剖(公式) + MM(公式)
    title("R10 量效应解剖(8月vs7月全口径)——SUMIFS活算")
    W8 = winp(2026, 8, 2026, 8)
    W7 = winp(2026, 7, 2026, 7)
    header(["方向", "维度", "品类/客户", "收入变动(万)", "8月收入(万)", "7月收入(万)"])
    for d in AN3["E_量效应解剖_品类"]["降幅TOP"] + AN3["E_量效应解剖_品类"]["增幅TOP"]:
        sv(r, 1, "降幅" if d["收入变动万"] < 0 else "增幅")
        sv(r, 2, "品类")
        sv(r, 3, d["品类"])
        c8 = [("H", cc(f"C{r}"))] + W8
        c7 = [("H", cc(f"C{r}"))] + W7
        sv(r, 4, f"=ROUND(({sumifs('M', c8)}-{sumifs('M', c7)})/10000,1)")
        sv(r, 5, rev(c8, 1)); sv(r, 6, rev(c7, 1))
        VER.append(("R10", f"D{r}", d["收入变动万"], None))
        r += 1
    for d in AN3["E_量效应解剖_客户"]["降幅TOP"] + AN3["E_量效应解剖_客户"]["增幅TOP"]:
        if d["客户"] == "?":
            continue
        sv(r, 1, "降幅" if d["收入变动万"] < 0 else "增幅")
        sv(r, 2, "客户")
        sv(r, 3, d["客户"])
        c8 = [("B", cc(f"C{r}"))] + W8
        c7 = [("B", cc(f"C{r}"))] + W7
        sv(r, 4, f"=ROUND(({sumifs('M', c8)}-{sumifs('M', c7)})/10000,1)")
        sv(r, 5, rev(c8, 1)); sv(r, 6, rev(c7, 1))
        VER.append(("R10", f"D{r}", d["收入变动万"], None))
        r += 1
    r += 1
    mmstar = chr(34) + "MM*" + chr(34)
    title("R10b MM引擎(2026YTD vs 2025YTD)——SUMIFS活算")
    header(["指标", "值"])
    for lab, f in [("客户数26(静态,来自逐客户去重)", 1437), ("客户数25(静态)", 1547)]:
        sv(r, 1, lab); sv(r, 2, f); r += 1
    for lab, tcol, w in [("收入26(万)", "M", W26), ("收入25(万)", "M", W25), ("利润26(万)", "N", W26), ("利润25(万)", "N", W25)]:
        sv(r, 1, lab)
        sv(r, 2, f"=ROUND({sumifs(tcol, [('C', mmstar)] + w)}/10000,0)")
        r += 1
    sv(r, 1, "户均26(万)"); sv(r, 2, f"=ROUND(B{r - 4}/B{r - 6},1)"); r += 1
    sv(r, 1, "户均25(万)"); sv(r, 2, f"=ROUND(B{r - 4}/B{r - 6},1)"); r += 1
    sv(r, 1, "利润增量(万)"); sv(r, 2, f"=B{r - 4}-B{r - 3}"); r += 1
    VER.append(("R10b", f"B{r - 1}", 3145, None))
    r += 1

    # R11a 音频分产品(公式)
    title("R11a 音频功放分产品月度收入(万)——SUMIFS活算;毛利率=利润/收入")
    header(["SKU", "1月", "2月", "3月", "4月", "5月", "6月", "7月", "8月", "YTD(万)", "毛利率1-5月", "毛利率6-8月", "TOP客户(静态)"])
    exp11 = AN4["音频功放_分产品"]
    for it in exp11:
        sku = it["产品"]
        sv(r, 1, sku)
        for m in range(1, 9):
            conds = [("F", '"音频功放"'), ("J", f'"*{sku}*"')] + winp(2026, m, 2026, m)
            sv(r, m + 1, rev(conds, 0))
        cy = [("F", '"音频功放"'), ("J", f'"*{sku}*"')] + W26
        c15 = [("F", '"音频功放"'), ("J", f'"*{sku}*"')] + winp(2026, 1, 2026, 5)
        c68 = [("F", '"音频功放"'), ("J", f'"*{sku}*"')] + winp(2026, 6, 2026, 8)
        sv(r, 10, rev(cy, 1))
        sv(r, 11, f"=ROUND({sumifs('N', c15)}/{sumifs('M', c15)},4)")
        sv(r, 12, f"=ROUND({sumifs('N', c68)}/{sumifs('M', c68)},4)")
        sv(r, 13, it["TOP客户"])
        VER.append(("R11a", f"J{r}", it["YTD收入万"], None))
        VER.append(("R11a", f"K{r}", it["毛利率_1至5月"], None))
        r += 1
    r += 1

    # R11b 渗透矩阵(静态+注)
    title("R11b 品类×客户渗透矩阵(2026YTD,静态快照;计算方式=SUMIFS(品类,客户,2026窗口),源=D-镜像)")
    header(["品类", "总YTD收入(万)", "已渗透客户(领域/收入万)TOP8", "TOP30客户中未渗透"])
    for cat, d in AN3["D_渗透矩阵"].items():
        buyers = "; ".join(f"{b['客户']}({b['领域']}/{b['收入万']}万)" for b in d["已渗透TOP客户"])
        sv(r, 1, cat); sv(r, 2, d["总YTD收入万"]); sv(r, 3, buyers); sv(r, 4, "、".join(d["TOP30客户中未渗透"][:12]))
        r += 1
    r += 1

    # R11c 音频2025月度(公式)
    title("R11c 音频功放2025年月度(表8'去年8月毛利率26.5%'出处)——SUMIFS活算")
    header(["年月", "收入(万)", "利润(万)", "毛利率"])
    for ym in ("2025-06", "2025-07", "2025-08"):
        y, m = int(ym[:4]), int(ym[5:7])
        sv(r, 1, ym)
        conds = [("F", '"音频功放"')] + winp(y, m, y, m)
        sv(r, 2, rev(conds, 1)); sv(r, 3, pft(conds, 1))
        sv(r, 4, f"=IF(B{r}=0,\"\",ROUND(C{r}/B{r},4))")
        VER.append(("R11c", f"B{r}", AN3["A_音频功放月度"][ym]["收入万"], None))
        r += 1
    r += 1

    # R12 新品SKU汇总(公式)
    title("R12a 新品案例SKU汇总(2026YTD)——SUMIFS活算;客户数为静态(去重计数)")
    header(["SKU", "YTD收入(万)", "8月收入(万)", "客户数(静态)"])
    for sku, ry, r8, cn in [("TMI8180I", 314.1, 108.9, 5), ("TMI7604R", 417.1, 57.4, 42), ("TMI8116-Q1", 163.5, 23.7, 13), ("TME7352", 274.1, 22.7, 2)]:
        sv(r, 1, sku)
        sv(r, 2, rev([("J", f'"*{sku}*"')] + W26, 1))
        sv(r, 3, rev([("J", f'"*{sku}*"')] + W8, 1))
        sv(r, 4, cn)
        VER.append(("R12a", f"B{r}", ry, None))
        r += 1
    r += 1

    sv(r, 1, "R12b 7月快照值(来源:2026年7月销售经营分析报告): STI7月亏损-98万; DCDC-18V 7月成本效应-58万/毛利率2.8%; 中兴康讯7月毛利率-3.0%; 追觅7月收入14万; 新品占比15.7%")
    r += 1
    sv(r, 1, "注: 全表数值单元格除标注'静态'外均为SUMIFS活公式(源=D-镜像,单位万);量/结构拆分列与SKU增减对比由主模板VBA重算(同10-毛利桥/11-SKU变化),本副本(.xlsx)为快照。")
    r += 1
    sv(r, 1, "生成: 2026-09-09 整体重建(消除历史行号叠写)")

    # 顶部说明
    sv(1, 8, "注:数值单元格多为SUMIFS活公式(源=D-镜像,单位万);量/结构拆分与SKU增减对比由主模板VBA重算机制生成,详见0-说明与本表末注。")

    # ---- 重算并验证 ----
    with_retry(lambda: xl.CalculateFull())
    time.sleep(4)
    fails = 0
    for i, (blkname, cell, expect, _) in enumerate(VER):
        m = re.match(r"([A-Z]+)(\d+)", cell)
        col, row = m.group(1), int(m.group(2))
        v = rv(row, col)
        try:
            vf = float(v)
        except (TypeError, ValueError):
            VER[i] = (blkname, cell, expect, f"非数值:{v}")
            fails += 1
            continue
        tol = 1.1 if abs(expect) >= 20 else 0.16
        ok = abs(vf - expect) <= tol
        if not ok:
            fails += 1
        VER[i] = (blkname, cell, expect, round(vf, 2))
    LOG.append(f"verify total={len(VER)} fails={fails}")
    for blkname, cell, expect, actual in VER:
        if isinstance(actual, str) or abs((float(actual) if not isinstance(actual, str) else 0) - expect) > (1.1 if abs(expect) >= 20 else 0.16):
            LOG.append(f"  FAIL {blkname} {cell} expect={expect} actual={actual}")

    with_retry(lambda: wb.Save())
    with_retry(lambda: wb.Close(False))
    LOG.append("saved")
finally:
    if xl is not None:
        try:
            xl.Quit()
        except Exception:
            pass
    pythoncom.CoUninitialize()

open(r"C:\Users\910373\AppData\Local\Temp\opencode\build\rebuild_r_log.txt", "w", encoding="utf-8").write("\n".join(str(x) for x in LOG))
print("REBUILD_R_DONE")
