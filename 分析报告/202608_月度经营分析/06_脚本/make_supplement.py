# -*- coding: utf-8 -*-
r"""生成数据底表更新副本：
- 副本=网络模板复制(不改原文件)
- 新增 R-报告补充 sheet：四因子毛利桥(同比/环比)、月度毛利率与环比四因子序列、
  中兴康讯×品类、KA新增SKU品类TOP、KA利润同比归因
全部写入值+口径注，供报告脚注引用"""
import collections
import datetime as dt
import json
import shutil
import time
import pythoncom
import pywintypes
import win32com.client as win32

TPL = r"\\192.168.8.3\财务部\财务电子档案备份\D1经营分析\分析报告\分析报告-202608\月度分析模板.xlsm"
COPY = r"E:\3-其他资料\数据分析\月度分析模板_8月报告副本.xlsx"
OUTJ = r"C:\Users\910373\AppData\Local\Temp\opencode\build\supplement.json"

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

sup = {}
pythoncom.CoInitialize()
xl = None
try:
    xl = win32.DispatchEx("Excel.Application")
    xl.Visible = False
    xl.DisplayAlerts = False
    xl.AutomationSecurity = 1
    xl.AutoRecover.Enabled = False
    # 临时副本：xlsm→xlsx 剥宏(报告用，不动原文件)
    shutil.copyfile(TPL, COPY + "m")
    wb = with_retry(lambda: xl.Workbooks.Open(COPY + "m"))
    wsM = wb.Worksheets("D-镜像")
    lo = with_retry(lambda: wsM.ListObjects("镜像表"))
    n = with_retry(lambda: lo.ListRows.Count)
    hdrs = {}
    for i in range(1, with_retry(lambda: lo.ListColumns.Count) + 1):
        hdrs[with_retry(lambda: lo.HeaderRowRange.Cells(1, i).Value)] = i
    def mcol(nm):
        ci = hdrs[nm]
        v = with_retry(lambda c=ci: wsM.Range(wsM.Cells(2, c), wsM.Cells(1 + n, c)).Value)
        return [x[0] if isinstance(x, tuple) else x for x in v]
    D = [d.replace(tzinfo=None) if isinstance(d, (dt.datetime, dt.date)) else None for d in mcol("发货日期")]
    Q = [float(v) if isinstance(v, (int, float)) else 0.0 for v in mcol("数量")]
    R = [float(v) if isinstance(v, (int, float)) else 0.0 for v in mcol("收入")]
    P = [float(v) if isinstance(v, (int, float)) else 0.0 for v in mcol("利润")]
    SKU = mcol("存货名称"); CAT = mcol("客户类别全称"); CUST = mcol("客户简称"); PIN = mcol("品类")
    N = n

    def periods(d0s, d0e, d1s=dt.datetime(2026, 8, 1), d1e=dt.datetime(2026, 8, 31, 23, 59, 59)):
        cur = collections.defaultdict(lambda: [0.0, 0.0, 0.0])
        old = collections.defaultdict(lambda: [0.0, 0.0, 0.0])
        for j in range(N):
            dv = D[j]
            if not dv:
                continue
            if d1s <= dv <= d1e:
                a = cur[SKU[j]]; a[0] += Q[j]; a[1] += R[j]; a[2] += P[j]
            elif d0s <= dv <= d0e:
                a = old[SKU[j]]; a[0] += Q[j]; a[1] += R[j]; a[2] += P[j]
        return cur, old

    def four_factor(cur, old):
        Q1 = sum(v[0] for v in cur.values()); Q0 = sum(v[0] for v in old.values())
        G0 = sum(v[2] for v in old.values()); R0 = sum(v[1] for v in old.values())
        e_vol = (Q1 - Q0) * (G0 / Q0 if Q0 else 0)
        e_struct = 0.0
        q1_um0 = 0.0
        e_price = 0.0
        e_cost = 0.0
        g1 = g0 = r1 = r0 = 0.0
        for s in cur:
            if s in old:
                q1, rv1, gp1 = cur[s]
                q0, rv0, gp0 = old[s]
                if q1 > 0 and q0 > 0 and rv1 > 0 and rv0 > 0:
                    um0 = (rv0 - gp0) / q0
                    q1_um0 += q1 * um0
                    e_price += q1 * (rv1 / q1 - rv0 / q0)
                    e_cost += q1 * ((rv0 - gp0) / q0 - (rv1 - gp1) / q1)
                    g1 += gp1; g0 += gp0; r1 += rv1; r0 += rv0
        e_struct = q1_um0 - Q1 * (G0 / Q0 if Q0 else 0)
        return dict(量=round(e_vol / 1e4), 结构=round(e_struct / 1e4), 价=round(e_price / 1e4),
                    成本=round(e_cost / 1e4), dGP=round((g1 - g0) / 1e4),
                    m0=g0 / r0 if r0 else 0, m1=g1 / r1 if r1 else 0)

    # 同比(8月 vs 去年8月) 与 环比(8月 vs 7月)
    cur, oldL = periods(dt.datetime(2025, 8, 1), dt.datetime(2025, 8, 31, 23, 59, 59))
    sup["桥_同比"] = four_factor(cur, oldL)
    cur, oldP = periods(dt.datetime(2026, 7, 1), dt.datetime(2026, 7, 31, 23, 59, 59))
    sup["桥_环比"] = four_factor(cur, oldP)

    # 月度序列: 2026-02..08 每月 vs 上月 四因子 + 月毛利率
    sup["月度序列"] = []
    tot_m = {}
    for mi in range(1, 9):
        import calendar as _cal
        s = dt.datetime(2026, mi, 1)
        e = dt.datetime(2026, mi, _cal.monthrange(2026, mi)[1], 23, 59, 59)
        q = r_ = p_ = 0.0
        for j in range(N):
            if D[j] and s <= D[j] <= e:
                q += Q[j]; r_ += R[j]; p_ += P[j]
        tot_m[mi] = (q, r_, p_)
    for mi in range(1, 9):
        q, r_, p_ = tot_m[mi]
        row = {"月": f"{mi}月", "收入万": round(r_ / 1e4), "毛利率": round(p_ / r_, 4) if r_ else None}
        if mi >= 2:
            import calendar as _cal
            ps = dt.datetime(2026, mi - 1, 1)
            pe = dt.datetime(2026, mi - 1, _cal.monthrange(2026, mi - 1)[1], 23, 59, 59)
            cs = dt.datetime(2026, mi, 1)
            ce = dt.datetime(2026, mi, _cal.monthrange(2026, mi)[1], 23, 59, 59)
            curm, oldm = periods(ps, pe, cs, ce)
            f = four_factor(curm, oldm)
            row.update({k: f[k] for k in ("量", "结构", "价", "成本")})
        sup["月度序列"].append(row)

    # 中兴康讯 × 品类 (YTD 1-8 + 8月)
    z_cat_y = collections.defaultdict(lambda: [0.0, 0.0])
    z_cat_m = collections.defaultdict(lambda: [0.0, 0.0])
    z_tot_y = [0.0, 0.0]
    for j in range(N):
        if D[j] and CUST[j] == "中兴康讯":
            if D[j] >= dt.datetime(2026, 1, 1):
                a = z_cat_y[PIN[j]]; a[0] += R[j]; a[1] += P[j]
                z_tot_y[0] += R[j]; z_tot_y[1] += P[j]
                if D[j] >= dt.datetime(2026, 8, 1):
                    b = z_cat_m[PIN[j]]; b[0] += R[j]; b[1] += P[j]
    sup["中兴康讯_品类YTD"] = sorted(
        [{"品类": k, "收入万": round(v[0] / 1e4), "利润万": round(v[1] / 1e4),
          "毛利率": round(v[1] / v[0], 4) if v[0] else None, "占比": round(v[0] / z_tot_y[0], 4)}
         for k, v in z_cat_y.items() if v[0] > 1e4], key=lambda x: -x["收入万"])[:8]
    sup["中兴康讯_合计"] = {"YTD收入万": round(z_tot_y[0] / 1e4), "YTD利润万": round(z_tot_y[1] / 1e4)}

    # 去年同期中兴康讯 (1-8月2025)
    z_last = [0.0, 0.0]
    for j in range(N):
        if D[j] and CUST[j] == "中兴康讯" and dt.datetime(2025, 1, 1) <= D[j] <= dt.datetime(2025, 8, 31, 23, 59, 59):
            z_last[0] += R[j]; z_last[1] += P[j]
    sup["中兴康讯_去年YTD"] = {"收入万": round(z_last[0] / 1e4), "利润万": round(z_last[1] / 1e4)}

    # KA新增SKU品类TOP (近12月 vs 前12月, KA群)
    r12s = dt.datetime(2025, 9, 1); r12e = dt.datetime(2026, 8, 31, 23, 59, 59)
    p12s = dt.datetime(2024, 9, 1); p12e = dt.datetime(2025, 8, 31, 23, 59, 59)
    grp_cur = {}; grp_pre = {}
    for j in range(N):
        dv = D[j]
        if not dv:
            continue
        cg = (CAT[j] or "")[:2]
        if cg != "KA":
            continue
        if r12s <= dv <= r12e:
            k = SKU[j]
            grp_cur.setdefault(k, [0.0, 0.0])
            grp_cur[k][0] += R[j]; grp_cur[k][1] += P[j]
        elif p12s <= dv <= p12e:
            grp_pre.setdefault(SKU[j], 1)
    pin_first = {}
    for j in range(N):
        s = SKU[j]
        if s and s not in pin_first:
            pin_first[s] = PIN[j]
    ka_new_cat = collections.defaultdict(lambda: [0, 0.0, 0.0])
    for k, v in grp_cur.items():
        if k not in grp_pre and v[0] > 0:
            c = pin_first.get(k)
            if c:
                a = ka_new_cat[c]
                a[0] += 1; a[1] += v[0]; a[2] += v[1]
    sup["KA新增SKU品类TOP"] = sorted(
        [{"品类": k, "SKU数": v[0], "收入万": round(v[1] / 1e4), "利润万": round(v[2] / 1e4)}
         for k, v in ka_new_cat.items()], key=lambda x: -x["收入万"])[:10]

    # KA利润同比归因 (top拖累客户)
    ka_cust_y = collections.defaultdict(lambda: [0.0, 0.0])
    ka_cust_l = collections.defaultdict(lambda: [0.0, 0.0])
    for j in range(N):
        dv = D[j]
        if not dv or (CAT[j] or "")[:2] != "KA":
            continue
        if dt.datetime(2026, 1, 1) <= dv <= dt.datetime(2026, 8, 31, 23, 59, 59):
            a = ka_cust_y[CUST[j]]; a[0] += R[j]; a[1] += P[j]
        elif dt.datetime(2025, 1, 1) <= dv <= dt.datetime(2025, 8, 31, 23, 59, 59):
            a = ka_cust_l[CUST[j]]; a[0] += R[j]; a[1] += P[j]
    deltas = []
    for c in ka_cust_y:
        d = ka_cust_y[c][1] - ka_cust_l.get(c, [0, 0])[1]
        deltas.append({"客户": c, "YTD利润万": round(ka_cust_y[c][1] / 1e4), "利润同比万": round(d / 1e4)})
    sup["KA利润拖累TOP"] = sorted(deltas, key=lambda x: x["利润同比万"])[:8]
    sup["KA利润提升TOP"] = sorted(deltas, key=lambda x: -x["利润同比万"])[:5]

    # ===== 写入副本 R-报告补充 =====
    for sh in with_retry(lambda: list(wb.Worksheets)):
        if sh.Name == "R-报告补充":
            sh.Delete()
    wsS = wb.Worksheets.Add(After=wb.Worksheets(wb.Worksheets.Count))
    wsS.Name = "R-报告补充"
    RR = [1]
    def wrow(vals, bold=False):
        r = RR[0]
        for ci, v in enumerate(vals, 1):
            wsS.Cells(r, ci).Value = v
            if bold:
                wsS.Cells(r, ci).Font.Bold = True
        RR[0] = r + 1
    def wtitle(t):
        r = RR[0]
        wsS.Cells(r, 1).Value = t
        wsS.Cells(r, 1).Font.Bold = True
        RR[0] = r + 1
    wtitle("R1 四因子毛利桥(万) —— 量=ΔQ×基准单位毛利; 结构=Σq1×基准UM−Q1×基准平均UM; 价=Σq1×Δp; 成本=Σq1×(基准UC−本期UC); 可比集合=两期均有销售")
    wrow(["口径", "量效应", "结构效应", "价效应", "成本效应", "可比ΔGP", "可比毛利率变化"], True)
    b = sup["桥_同比"]
    wrow([f"同比(8月vs去年8月)", b["量"], b["结构"], b["价"], b["成本"], b["dGP"], f"{b['m0']:.2%}→{b['m1']:.2%}%"])
    b = sup["桥_环比"]
    wrow([f"环比(8月vs7月)", b["量"], b["结构"], b["价"], b["成本"], b["dGP"], f"{b['m0']:.2%}→{b['m1']:.2%}%"])
    RR[0] += 1
    wtitle("R2 月度序列(万) —— 2月起为环比四因子")
    wrow(["月份", "收入", "毛利率", "量", "结构", "价", "成本"], True)
    for row in sup["月度序列"]:
        wrow([row["月"], row["收入万"], row["毛利率"], row.get("量", ""), row.get("结构", ""), row.get("价", ""), row.get("成本", "")])
    wsS.Range(wsS.Cells(4, 3), wsS.Cells(3 + len(sup["月度序列"]), 3)).NumberFormat = "0.00%"
    RR[0] += 1
    wtitle("R3 中兴康讯×品类 (2026年1-8月YTD)")
    wrow(["品类", "收入(万)", "利润(万)", "毛利率", "占比"], True)
    for row in sup["中兴康讯_品类YTD"]:
        wrow([row["品类"], row["收入万"], row["利润万"], row["毛利率"], row["占比"]])
    t = sup["中兴康讯_合计"]; l = sup["中兴康讯_去年YTD"]
    wrow(["合计", t["YTD收入万"], t["YTD利润万"], round(t["YTD利润万"] / t["YTD收入万"], 4), 1.0])
    wrow(["去年同期", l["收入万"], l["利润万"], "", ""])
    RR[0] += 1
    wtitle("R4 KA新增SKU品类TOP (近12月vs前12月)")
    wrow(["品类", "SKU数", "收入(万)", "利润(万)"], True)
    for row in sup["KA新增SKU品类TOP"]:
        wrow([row["品类"], row["SKU数"], row["收入万"], row["利润万"]])
    RR[0] += 1
    wtitle("R5 KA客户利润同比(2026YTD vs 2025YTD) 拖累TOP/提升TOP")
    wrow(["客户", "YTD利润(万)", "利润同比(万)"], True)
    for row in sup["KA利润拖累TOP"] + sup["KA利润提升TOP"]:
        wrow([row["客户"], row["YTD利润万"], row["利润同比万"]])
    wsS.Columns("A:G").ColumnWidth = 22
    # 另存为 xlsx 副本(剥宏,报告引用版)
    with_retry(lambda: wb.SaveAs(COPY, FileFormat=51))
    with_retry(lambda: wb.Close(SaveChanges=False))
    import os
    if os.path.exists(COPY + "m"):
        os.remove(COPY + "m")
finally:
    if xl is not None:
        try:
            xl.Quit()
        except Exception:
            pass
    pythoncom.CoUninitialize()

with open(OUTJ, "w", encoding="utf-8") as f:
    json.dump(sup, f, ensure_ascii=False, indent=1)
print("SUPPLEMENT_DONE")
