# -*- coding: utf-8 -*-
r"""R块拆分独立sheet: R-报告补充保留R1-R5(清59+), R6-R12各建独立sheet(公式+静态带注+验证)"""
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
RC = json.load(open(r"C:\Users\910373\AppData\Local\Temp\opencode\build\recompute.json", encoding="utf-8"))

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
YES = chr(34) + "是" + chr(34)
MMSTAR = chr(34) + "MM*" + chr(34)
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
VER = []
pythoncom.CoInitialize()
xl = None
try:
    xl = with_retry(lambda: win32.DispatchEx("Excel.Application"))
    xl.Visible = False
    xl.DisplayAlerts = False
    wb = with_retry(lambda: xl.Workbooks.Open(BK))

    def get_sheet(name):
        for i in range(1, with_retry(lambda: xl.Worksheets.Count) + 1):
            if str(with_retry(lambda: xl.Worksheets(i).Name)) == name:
                return with_retry(lambda: xl.Worksheets(i))
        ws = with_retry(lambda: xl.Worksheets.Add(with_retry(lambda: xl.Worksheets(1))))
        with_retry(lambda: ws.__setattr__("Name", name))
        LOG.append(f"created sheet {name}")
        return ws

    class Ctx:
        def __init__(self, ws):
            self.ws = ws
            self.r = 1
        def sv(self, c, v):
            rg = with_retry(lambda: self.ws.Cells(self.r, c))
            prop = "Formula" if isinstance(v, str) and v.startswith("=") else "Value"
            with_retry(lambda: rg.__setattr__(prop, v))
        def rv(self, c):
            return with_retry(lambda: self.ws.Cells(self.r, c).Value)
        def title(self, t):
            self.sv(1, t); self.r += 1
        def header(self, hs):
            for c, h in enumerate(hs, 1):
                self.sv(c, h)
            self.r += 1
        def gap(self):
            self.r += 1

    def ver(blk, ws, row, colletter, expect, tol=None):
        VER.append((blk, ws, row, colletter, expect, tol))

    # ---- 0) R-报告补充清理: 只留R1-R5 ----
    wr5 = with_retry(lambda: xl.Worksheets("R-报告补充"))
    with_retry(lambda: wr5.Range("A59:AZ260").Clear)
    LOG.append("R-报告补充 cleared below 58 (keep R1-R5)")

    # ---- 1) R6-SKU与客户 ----
    x = Ctx(get_sheet("R6-SKU与客户"))
    with_retry(lambda: x.ws.Cells.Clear)
    x.title("R6a 表14完整口径(11-SKU变化数据 + 净影响=新增-流失公式)")
    x.header(["客户群", "客户数", "新增SKU", "流失SKU", "净增减", "新增收入(万)", "新增利润(万)", "流失收入(万)", "流失利润(万)", "净收入影响(万)", "净利润影响(万)"])
    for row in [["KA+AA合计", 39, 151, 66, 85, 2162, 845, 167, 83], ["KA", 18, 82, 35, 47, 1783, 713, 71, 31], ["AA", 21, 69, 31, 38, 379, 132, 96, 52]]:
        for c, v in enumerate(row, 1):
            x.sv(c, v)
        x.sv(10, f"=F{x.r}-H{x.r}")
        x.sv(11, f"=G{x.r}-I{x.r}")
        ver("R6a", x.ws, x.r, "J", row[5] - row[7])
        x.r += 1
    x.gap()
    x.title("R6b 客户YTD对比(2026年1-8月 vs 2025年1-8月)——SUMIFS活算")
    x.header(["客户", "YTD26收入(万)", "YTD26利润(万)", "YTD26毛利率", "去年收入(万)", "去年利润(万)", "去年毛利率", "收入同比", "利润同比(万)"])
    for cust in ["石头", "海康威视", "追觅", "兆驰", "共进", "安克创新", "中兴康讯"]:
        x.sv(1, cust)
        rr = x.r
        c26 = [("B", cc(f"A{rr}"))] + W26
        c25 = [("B", cc(f"A{rr}"))] + W25
        x.sv(2, rev(c26)); x.sv(3, pft(c26))
        x.sv(4, f"=IF(B{rr}=0,\"\",ROUND(C{rr}/B{rr},4))")
        x.sv(5, rev(c25)); x.sv(6, pft(c25))
        x.sv(7, f"=IF(E{rr}=0,\"\",ROUND(F{rr}/E{rr},4))")
        x.sv(8, f"=IF(E{rr}=0,\"\",ROUND(B{rr}/E{rr}-1,4))")
        x.sv(9, f"=ROUND(C{rr}-F{rr},1)")
        ver("R6b", x.ws, rr, "B", RC["目标客户YTD对比"][cust]["YTD26收入万"])
        ver("R6b", x.ws, rr, "C", RC["目标客户YTD对比"][cust]["YTD26利润万"])
        x.r += 1
    x.gap()
    x.title("R6c 追觅/兆驰/共进 品类TOP3(2026年1-8月)——SUMIFS活算,占比=该品类收入/客户总收入(全品类)")
    x.header(["客户", "品类", "收入(万)", "利润(万)", "毛利率"])
    for cust in ("追觅", "兆驰", "共进"):
        for it in RC["客户品类TOP3_2026YTD"][cust]:
            x.sv(1, cust); x.sv(2, it["品类"])
            rr = x.r
            conds = [("B", cc(f"A{rr}")), ("H", f"B{rr}")] + W26
            ctot = [("B", cc(f"A{rr}"))] + W26
            x.sv(3, rev(conds))
            x.sv(4, pft(conds))
            x.sv(5, f"=IF(C{rr}=0,\"\",ROUND(D{rr}/C{rr},4))")
            x.sv(6, f"=ROUND(C{rr}/({sumifs('M', ctot)}/10000),3)")
            ver("R6c", x.ws, rr, "C", it["收入万"])
            x.r += 1
    x.gap()
    x.title("R6d 8月小品类毛利率核实——SUMIFS活算")
    x.header(["品类(产品线)", "8月收入(万)", "8月毛利率"])
    for nm, col, crit in [("音频功放(产品线)", "F", '"音频功放"'), ("电脑&计算(品类通配)", "H", '"电脑&计算*"')]:
        x.sv(1, nm)
        rr = x.r
        conds = [(col, crit)] + W8
        x.sv(2, rev(conds))
        x.sv(3, f"=IF(B{rr}=0,\"\",ROUND({sumifs('N', conds)}/{sumifs('M', conds)},4))")
        x.r += 1
    ver("R6d", x.ws, x.r - 2, "B", 52.9)
    x.gap()
    x.title("R6e 应用领域新品结构(表13)——SUMIFS活算")
    x.header(["领域", "新品收入(万)", "占新品收入%", "新品毛利率", "渗透度"])
    tot_f = f"({sumifs('M', [('K', YES)] + W26)}/10000)"
    for d in ["安防", "网通", "智能清洁", "汽车电子", "充电头"]:
        x.sv(1, d)
        rr = x.r
        cn = [("E", cc(f"A{rr}")), ("K", YES)] + W26
        ca = [("E", cc(f"A{rr}"))] + W26
        x.sv(2, rev(cn))
        x.sv(3, f"=ROUND(B{rr}/{tot_f},3)")
        x.sv(4, f"=IF(B{rr}=0,\"\",ROUND({sumifs('N', cn)}/{sumifs('M', cn)},4))")
        x.sv(5, f"=ROUND(B{rr}/({sumifs('M', ca)}/10000),3)")
        x.r += 1
    x.gap()
    x.title("R6f KA其他品类推导: SKU数=82-38=44, 收入=1783-1671=112(万), 利润=713-694=19(万) (R4合计 vs 11-SKU变化KA行)")

    # ---- 2) R7-中兴月度 ----
    x = Ctx(get_sheet("R7-中兴月度"))
    with_retry(lambda: x.ws.Cells.Clear)
    x.title("R7 中兴康讯月度损益(万)——SUMIFS活算")
    x.header(["年月", "收入(万)", "利润(万)", "毛利率"])
    for ym in sorted(AN2["A_中兴康讯月度"]):
        y, m = int(ym[:4]), int(ym[5:7])
        x.sv(1, ym)
        rr = x.r
        conds = [("B", '"*中兴康讯*"')] + winp(y, m, y, m)
        x.sv(2, rev(conds)); x.sv(3, pft(conds))
        x.sv(4, f"=IF(B{rr}=0,\"\",ROUND(C{rr}/B{rr},4))")
        ver("R7", x.ws, rr, "B", AN2["A_中兴康讯月度"][ym]["收入万"])
        x.r += 1

    # ---- 3) R8-品类增量 ----
    x = Ctx(get_sheet("R8-品类增量"))
    with_retry(lambda: x.ws.Cells.Clear)
    x.title("R8 重点客户×品类利润增量(2026YTD vs 2025YTD,万)——SUMIFS活算")
    x.header(["客户", "品类", "利润26", "利润25", "增量"])
    for cust in ["石头", "海康威视", "TPLINK", "大华集团", "共进", "兆驰", "创维数字", "小米集团", "追觅", "中兴康讯"]:
        for it in AN2["C_同类对冲矩阵"][cust]:
            x.sv(1, cust); x.sv(2, it["品类"])
            rr = x.r
            c26 = [("B", cc(f"A{rr}")), ("H", f"B{rr}")] + W26
            c25 = [("B", cc(f"A{rr}")), ("H", f"B{rr}")] + W25
            x.sv(3, pft(c26)); x.sv(4, pft(c25))
            x.sv(5, f"=ROUND(C{rr}-D{rr},1)")
            x.r += 1
    x.gap()
    x.title("R8b 新品案例代表客户(2026YTD)——SUMIFS活算")
    x.header(["SKU", "客户", "收入(万)", "利润(万)"])
    for sku, custs in AN2["B_新品案例客户"].items():
        for it in custs:
            if it["收入万"] <= 0:
                continue
            x.sv(1, sku); x.sv(2, it["客户"])
            rr = x.r
            conds = [("J", f'"*{sku}*"'), ("B", cc(f"B{rr}"))] + W26
            x.sv(3, rev(conds)); x.sv(4, pft(conds))
            ver("R8b", x.ws, rr, "C", it["收入万"])
            x.r += 1
    x.gap()
    x.title("R8c TMI6011客户(2026YTD)——SUMIFS活算")
    x.header(["型号", "客户", "收入(万)", "利润(万)"])
    for cust, v in AN2["G_TMI6011_客户"].items():
        x.sv(1, "TMI6011"); x.sv(2, cust)
        rr = x.r
        conds = [("J", '"*TMI6011*"'), ("B", cc(f"B{rr}"))] + W26
        x.sv(3, rev(conds)); x.sv(4, pft(conds))
        ver("R8c", x.ws, rr, "C", v[0])
        x.r += 1

    # ---- 4) R9-长周期 ----
    x = Ctx(get_sheet("R9-长周期"))
    with_retry(lambda: x.ws.Cells.Clear)
    x.title("R9 四因子长周期序列(2024-02至2026-08,万)——收入/毛利率SUMIFS活算;量/结构/价/成本/dGP为主模板VBA重算机制产物(静态快照,锚点=10-毛利桥)")
    x.header(["年月", "可比SKU数", "量", "结构", "价", "成本", "dGP", "收入(万)", "毛利率"])
    for s in AN2["D_四因子长周期"]:
        y, m = int(s["月"][:4]), int(s["月"][5:7])
        x.sv(1, s["月"])
        for c, k in [(2, "SKU"), (3, "量"), (4, "结构"), (5, "价"), (6, "成本"), (7, "dGP")]:
            x.sv(c, s[k])
        rr = x.r
        conds = winp(y, m, y, m)
        x.sv(8, rev(conds, 0))
        x.sv(9, f"=IF(H{rr}=0,\"\",ROUND({sumifs('N', conds)}/10000/H{rr},4))")
        ver("R9", x.ws, rr, "H", s["收入"], tol=1.1)
        x.r += 1

    # ---- 5) R10-量效应 ----
    x = Ctx(get_sheet("R10-量效应"))
    with_retry(lambda: x.ws.Cells.Clear)
    x.title("R10 量效应解剖(8月vs7月全口径)——SUMIFS活算")
    x.header(["方向", "维度", "品类/客户", "收入变动(万)", "8月收入(万)", "7月收入(万)"])
    for d in AN2["E_量效应解剖_品类"]["降幅TOP"] + AN2["E_量效应解剖_品类"]["增幅TOP"]:
        x.sv(1, "降幅" if d["收入变动万"] < 0 else "增幅")
        x.sv(2, "品类"); x.sv(3, d["品类"])
        rr = x.r
        c8 = [("H", cc(f"C{rr}"))] + W8
        c7 = [("H", cc(f"C{rr}"))] + W7
        x.sv(4, f"=ROUND(({sumifs('M', c8)}-{sumifs('M', c7)})/10000,1)")
        x.sv(5, rev(c8)); x.sv(6, rev(c7))
        ver("R10", x.ws, rr, "D", d["收入变动万"])
        x.r += 1
    for d in AN2["E_量效应解剖_客户"]["降幅TOP"] + AN2["E_量效应解剖_客户"]["增幅TOP"]:
        if d["客户"] == "?":
            x.sv(1, "降幅"); x.sv(2, "客户(未署名)"); x.sv(3, "(CRM客户名空,静态)")
            x.sv(4, d["收入变动万"]); x.sv(5, d["8月收入万"]); x.sv(6, d["7月收入万"])
            x.r += 1
            continue
        x.sv(1, "降幅" if d["收入变动万"] < 0 else "增幅")
        x.sv(2, "客户"); x.sv(3, d["客户"])
        rr = x.r
        c8 = [("B", cc(f"C{rr}"))] + W8
        c7 = [("B", cc(f"C{rr}"))] + W7
        x.sv(4, f"=ROUND(({sumifs('M', c8)}-{sumifs('M', c7)})/10000,1)")
        x.sv(5, rev(c8)); x.sv(6, rev(c7))
        ver("R10", x.ws, rr, "D", d["收入变动万"])
        x.r += 1
    x.gap()
    x.title("R10b MM引擎(2026YTD vs 2025YTD)——收入/利润SUMIFS活算,客户数静态(逐客户去重)")
    x.header(["指标", "值"])
    r_n26 = x.r; x.sv(1, "客户数26(静态)"); x.sv(2, 1437); x.r += 1
    r_n25 = x.r; x.sv(1, "客户数25(静态)"); x.sv(2, 1547); x.r += 1
    r_r26 = x.r; x.sv(1, "收入26(万)"); x.sv(2, f"=ROUND({sumifs('M', [('C', MMSTAR)] + W26)}/10000,0)"); x.r += 1
    r_r25 = x.r; x.sv(1, "收入25(万)"); x.sv(2, f"=ROUND({sumifs('M', [('C', MMSTAR)] + W25)}/10000,0)"); x.r += 1
    r_p26 = x.r; x.sv(1, "利润26(万)"); x.sv(2, f"=ROUND({sumifs('N', [('C', MMSTAR)] + W26)}/10000,0)"); x.r += 1
    r_p25 = x.r; x.sv(1, "利润25(万)"); x.sv(2, f"=ROUND({sumifs('N', [('C', MMSTAR)] + W25)}/10000,0)"); x.r += 1
    x.sv(1, "户均26(万)"); x.sv(2, f"=ROUND(B{r_r26}/B{r_n26},1)"); x.r += 1
    x.sv(1, "户均25(万)"); x.sv(2, f"=ROUND(B{r_r25}/B{r_n25},1)"); x.r += 1
    r_d = x.r; x.sv(1, "利润增量(万)"); x.sv(2, f"=B{r_p26}-B{r_p25}"); x.r += 1
    ver("R10b", x.ws, r_d, "B", 3145, tol=1.1)
    ver("R10b", x.ws, r_r26, "B", 25257, tol=1.1)

    # ---- 6) R11-音频与渗透 ----
    x = Ctx(get_sheet("R11-音频与渗透"))
    with_retry(lambda: x.ws.Cells.Clear)
    x.title("R11a 音频功放分产品月度收入(万)——SUMIFS活算;毛利率=利润/收入")
    x.header(["SKU", "1月", "2月", "3月", "4月", "5月", "6月", "7月", "8月", "YTD(万)", "毛利率1-5月", "毛利率6-8月", "TOP客户(静态)"])
    for it in AN4["音频功放_分产品"]:
        sku = it["产品"]
        x.sv(1, sku)
        rr = x.r
        for m in range(1, 9):
            conds = [("F", '"音频功放"'), ("J", f'"*{sku}*"')] + winp(2026, m, 2026, m)
            x.sv(m + 1, rev(conds, 0))
        cy = [("F", '"音频功放"'), ("J", f'"*{sku}*"')] + W26
        c15 = [("F", '"音频功放"'), ("J", f'"*{sku}*"')] + winp(2026, 1, 2026, 5)
        c68 = [("F", '"音频功放"'), ("J", f'"*{sku}*"')] + winp(2026, 6, 2026, 8)
        x.sv(10, rev(cy))
        x.sv(11, f"=ROUND({sumifs('N', c15)}/{sumifs('M', c15)},4)")
        x.sv(12, f"=ROUND({sumifs('N', c68)}/{sumifs('M', c68)},4)")
        x.sv(13, it["TOP客户"])
        ver("R11a", x.ws, rr, "J", it["YTD收入万"])
        ver("R11a", x.ws, rr, "K", it["毛利率_1至5月"], tol=0.02)
        x.r += 1
    x.gap()
    x.title("R11b 品类×客户渗透矩阵(2026YTD,静态;计算方式=SUMIFS(品类,客户,2026窗口),源=D-镜像)")
    x.header(["品类", "总YTD收入(万)", "已渗透客户(领域/收入万)TOP8", "TOP30客户中未渗透"])
    for cat, d in AN3["D_渗透矩阵"].items():
        buyers = "; ".join(f"{b['客户']}({b['领域']}/{b['收入万']}万)" for b in d["已渗透TOP客户"])
        x.sv(1, cat); x.sv(2, d["总YTD收入万"]); x.sv(3, buyers); x.sv(4, "、".join(d["TOP30客户中未渗透"][:12]))
        x.r += 1
    x.gap()
    x.title("R11c 音频功放2025年月度(表8'去年8月毛利率26.5%'出处)——SUMIFS活算")
    x.header(["年月", "收入(万)", "利润(万)", "毛利率"])
    for ym in ("2025-06", "2025-07", "2025-08"):
        y, m = int(ym[:4]), int(ym[5:7])
        x.sv(1, ym)
        rr = x.r
        conds = [("F", '"音频功放"')] + winp(y, m, y, m)
        x.sv(2, rev(conds)); x.sv(3, pft(conds))
        x.sv(4, f"=IF(B{rr}=0,\"\",ROUND(C{rr}/B{rr},4))")
        ver("R11c", x.ws, rr, "B", AN3["A_音频功放月度"][ym]["收入万"])
        x.r += 1

    # ---- 7) R12-新品与快照 ----
    x = Ctx(get_sheet("R12-新品与快照"))
    with_retry(lambda: x.ws.Cells.Clear)
    x.title("R12a 新品案例SKU汇总(2026YTD)——收入SUMIFS活算;客户数静态(去重计数)")
    x.header(["SKU", "YTD收入(万)", "8月收入(万)", "客户数(静态)"])
    for sku, ry, r8, cn in [("TMI8180I", 314.1, 108.9, 5), ("TMI7604R", 417.1, 57.4, 42), ("TMI8116-Q1", 163.5, 23.7, 13), ("TME7352", 274.1, 22.7, 2)]:
        x.sv(1, sku)
        rr = x.r
        x.sv(2, rev([("J", f'"*{sku}*"')] + W26))
        x.sv(3, rev([("J", f'"*{sku}*"')] + W8))
        x.sv(4, cn)
        ver("R12a", x.ws, rr, "B", ry)
        x.r += 1
    x.gap()
    x.title("R12b 7月快照值(来源:2026年7月销售经营分析报告,静态): STI7月亏损-98万; DCDC-18V 7月成本效应-58万/毛利率2.8%; 中兴康讯7月毛利率-3.0%; 追觅7月收入14万; 新品占比15.7%")

    # ---- 0-说明追加 ----
    w0 = with_retry(lambda: xl.Worksheets("0-说明"))
    lr = with_retry(lambda: w0.UsedRange.Rows.Count)
    rg = with_retry(lambda: w0.Cells(lr + 1, 1))
    with_retry(lambda: rg.__setattr__("Value", "2026-09-09(二): R-报告补充仅保留R1-R5;R6-R12拆分为独立sheet(R6-SKU与客户/R7-中兴月度/R8-品类增量/R9-长周期/R10-量效应/R11-音频与渗透/R12-新品与快照),聚合数据均为SUMIFS活公式(源=D-镜像),量/结构拆分与SKU增减对比由主模板VBA重算(同10-毛利桥/11-SKU变化)。"))

    # ---- 重算+验证 ----
    with_retry(lambda: xl.CalculateFull())
    time.sleep(5)
    fails = 0
    res = []
    for blk, ws, row, colletter, expect, tol in VER:
        v = with_retry(lambda: ws.Cells(row, colletter).Value)
        try:
            vf = float(v)
        except (TypeError, ValueError):
            fails += 1
            res.append(f"FAIL {blk} {ws.Name}!{colletter}{row} expect={expect} actual=非数值({v})")
            continue
        t = tol if tol else (1.1 if abs(expect) >= 20 else 0.16)
        if abs(vf - expect) > t:
            fails += 1
            res.append(f"FAIL {blk} {ws.Name}!{colletter}{row} expect={expect} actual={round(vf, 2)}")
    LOG.append(f"verify total={len(VER)} fails={fails}")
    LOG.extend(res[:25])

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

open(r"C:\Users\910373\AppData\Local\Temp\opencode\build\split_r_log.txt", "w", encoding="utf-8").write("\n".join(str(x) for x in LOG))
print("SPLIT_R_DONE")
