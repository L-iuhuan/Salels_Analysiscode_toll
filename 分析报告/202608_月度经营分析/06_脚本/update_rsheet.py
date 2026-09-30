# -*- coding: utf-8 -*-
r"""R-报告补充: R1/R2重算修正 + R6数据块 + 隐藏未引用sheet + 0-说明追加 (v2修COM用法)"""
import json
import time
import pythoncom
import pywintypes
import win32com.client as win32

BK = r"E:\3-其他资料\数据分析\月度分析模板_8月报告副本.xlsx"
RC = json.load(open(r"C:\Users\910373\AppData\Local\Temp\opencode\build\recompute.json", encoding="utf-8"))
RD = json.load(open(r"C:\Users\910373\AppData\Local\Temp\opencode\build\report_data.json", encoding="utf-8"))

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
pythoncom.CoInitialize()
xl = None
try:
    xl = win32.DispatchEx("Excel.Application")
    xl.Visible = False
    xl.DisplayAlerts = False
    wb = with_retry(lambda: xl.Workbooks.Open(BK))

    def cell(ws, r, c):
        return with_retry(lambda: ws.Cells(r, c))

    def sv(ws, r, c, v):
        rg = cell(ws, r, c)
        with_retry(lambda: rg.__setattr__("Value", v if v is not None else ""))

    ws = with_retry(lambda: xl.Worksheets("R-报告补充"))

    by = RC["桥_同比_2026_08_vs_2025_08"]
    bm = RC["桥_环比_2026_08_vs_2026_07"]
    sv(ws, 1, 1, "R1 四因子毛利桥(万) —— 2026-09-09重算修正版。恒等式: 量4+结构4=三因子量效应(10-毛利桥); 量+结构+价+成本=可比ΔGP。量=ΔQ×基准平均单位毛利; 结构=Σq1×基准UM−Q1×基准平均UM; 可比=两期均有销售")
    for col, val in [(2, round(by["量4"])), (3, round(by["结构4"])), (4, round(by["价"])), (5, round(by["成本"])), (6, round(by["dGP"]))]:
        sv(ws, 3, col, val)
    sv(ws, 3, 7, "36.43%→30.48%")
    for col, val in [(2, round(bm["量4"])), (3, round(bm["结构4"])), (4, round(bm["价"])), (5, round(bm["成本"])), (6, round(bm["dGP"]))]:
        sv(ws, 4, col, val)
    sv(ws, 4, 7, "30.20%→30.99%")
    sv(ws, 5, 1, "可比SKU数: 同比{}个(可比收入占8月收入89%), 环比{}个(占96%)。锚点验证: 同比量3={:.0f}(底表383一致), 环比量3={:.0f}(底表-291一致); 价/成本/ΔGP与10-毛利桥逐位一致。原R1/R2量/结构拆分存在计算错误已废弃。".format(by["可比SKU数"], bm["可比SKU数"], by["量3验证"], bm["量3验证"]))
    LOG.append("R1 corrected")

    sv(ws, 6, 1, "R2 月度序列(万) —— 2026-09-09重算; 1月为vs2025-12; 每月量+结构+价+成本=该月dGP")
    sv(ws, 7, 8, "dGP")
    for i, s in enumerate(RC["月度序列_重算"]):
        r = 8 + i
        sv(ws, r, 1, s["月"])
        sv(ws, r, 2, s["收入万"])
        sv(ws, r, 3, s["毛利率"])
        sv(ws, r, 4, s["量"])
        sv(ws, r, 5, s["结构"])
        sv(ws, r, 6, s["价"])
        sv(ws, r, 7, s["成本"])
        sv(ws, r, 8, s["dGP"])
    LOG.append("R2 corrected")

    r0 = 59
    sv(ws, r0, 1, "R6 报告引用数据补算(2026-09-09, 计算源=D-镜像全量, Python复核)")
    sv(ws, r0 + 1, 1, "R6a 表14完整口径(11-SKU变化 + 净影响推导=新增-流失)")
    for c, h in enumerate(["客户群", "客户数", "新增SKU", "流失SKU", "净增减", "新增收入(万)", "新增利润(万)", "流失收入(万)", "流失利润(万)", "净收入影响(万)", "净利润影响(万)"], 1):
        sv(ws, r0 + 2, c, h)
    rows14 = [
        ["KA+AA合计", 39, 151, 66, 85, 2162, 845, 167, 83, 1995, 762],
        ["KA", 18, 82, 35, 47, 1783, 713, 71, 31, 1712, 682],
        ["AA", 21, 69, 31, 38, 379, 132, 96, 52, 283, 80],
    ]
    for ri, row in enumerate(rows14):
        for c, v in enumerate(row, 1):
            sv(ws, r0 + 3 + ri, c, v)

    sv(ws, r0 + 7, 1, "R6b 客户YTD对比(2026年1-8月 vs 2025年1-8月)")
    for c, h in enumerate(["客户", "YTD26收入(万)", "YTD26利润(万)", "YTD26毛利率", "去年收入(万)", "去年利润(万)", "去年毛利率", "收入同比", "利润同比(万)"], 1):
        sv(ws, r0 + 8, c, h)
    rr = r0 + 9
    for name, d in RC["目标客户YTD对比"].items():
        vals = [name, d["YTD26收入万"], d["YTD26利润万"], d["YTD26毛利率"], d["去年YTD收入万"], d["去年YTD利润万"], d["去年YTD毛利率"], d["收入同比"], d["利润同比万"]]
        for c, v in enumerate(vals, 1):
            sv(ws, rr, c, v)
        rr += 1

    sv(ws, rr, 1, "R6c 追觅/兆驰/共进 品类TOP3(2026年1-8月)")
    rr += 1
    for c, h in enumerate(["客户", "品类", "收入(万)", "利润(万)", "占比", "毛利率"], 1):
        sv(ws, rr, c, h)
    rr += 1
    for cust, items in RC["客户品类TOP3_2026YTD"].items():
        for it in items:
            for c, v in enumerate([cust, it["品类"], it["收入万"], it["利润万"], it["占比"], it["毛利率"]], 1):
                sv(ws, rr, c, v)
            rr += 1

    sv(ws, rr, 1, "R6d 8月小品类毛利率核实(正文'音频功放/电脑&计算'出处)")
    rr += 1
    for c, h in enumerate(["品类(产品线)", "8月收入(万)", "8月毛利率"], 1):
        sv(ws, rr, c, h)
    rr += 1
    for k, v in RC["音频电脑充电_8月_品类‖产品线"].items():
        nm = k.split("‖")[0] + "(" + k.split("‖")[1] + ")"
        for c, vv in enumerate([nm, v["收入万"], v["毛利率"]], 1):
            sv(ws, rr, c, vv)
        rr += 1

    sv(ws, rr, 1, "R6e 应用领域新品占新品收入比重算(表13修正)")
    rr += 1
    for c, h in enumerate(["领域", "新品收入(万)", "占新品收入%", "新品毛利率", "渗透度(占该领域收入)"], 1):
        sv(ws, rr, c, h)
    rr += 1
    total_new = RD["newp"]["rev_y"]
    for d in RD["dom_new_top"]:
        for c, vv in enumerate([d["name"], round(d["newrev"] / 1e4, 1), round(d["newrev"] / 1e4 / total_new, 4), d["newm"], d["pen"]], 1):
            sv(ws, rr, c, vv)
        rr += 1

    sv(ws, rr, 1, "R6f KA新增SKU其他品类推导(R4合计38个/1671万/694万 vs 11-SKU变化KA行82个/1783万/713万)")
    rr += 1
    for c, vv in enumerate(["KA其他品类合计", "SKU数=82-38=44", "收入=1783-1671=112(万)", "利润=713-694=19(万)"], 1):
        sv(ws, rr, c, vv)
    LOG.append("R6 written")

    try:
        w0 = with_retry(lambda: xl.Worksheets("0-说明"))
        lastr = with_retry(lambda: w0.UsedRange.Rows.Count)
        sv(w0, lastr + 1, 1, "2026-09-09: R-报告补充R1/R2按D-镜像全量重算修正(原量/结构拆分有计算错误,现满足量4+结构4=三因子量恒等式); 新增R6报告引用数据块; 隐藏未引用sheet(1b/21/22/23/24/27/28/D-镜像/C-维度)。")
        LOG.append("0-说明 appended")
    except Exception as e:
        LOG.append("0-说明 ERR {}".format(e))

    for sname in ["1b-H1任务项", "21-限量出货名单", "22-产品升级清单", "23-低毛利SKU明细", "24-整改项目清单", "27-追觅分型号", "28-长库龄存货明细", "D-镜像", "C-维度"]:
        try:
            s = with_retry(lambda: xl.Worksheets(sname))
            with_retry(lambda: s.__setattr__("Visible", 0))
            LOG.append("hidden: " + sname)
        except Exception as e:
            LOG.append("hide ERR {}: {}".format(sname, e))

    with_retry(lambda: wb.Save())
    with_retry(lambda: wb.Close(False))
finally:
    if xl is not None:
        try:
            xl.Quit()
        except Exception:
            pass
    pythoncom.CoUninitialize()

open(r"C:\Users\910373\AppData\Local\Temp\opencode\build\rsheet_log.txt", "w", encoding="utf-8").write("\n".join(LOG))
print("RSHEET_DONE")
