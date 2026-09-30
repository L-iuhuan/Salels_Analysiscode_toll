# -*- coding: utf-8 -*-
r"""报告数据准备：从模板(网络)读取/计算全部展示值 → report_data.json"""
import collections
import datetime as dt
import json
import time
import pythoncom
import pywintypes
import win32com.client as win32

TPL = r"\\192.168.8.3\财务部\财务电子档案备份\D1经营分析\分析报告\分析报告-202608\月度分析模板.xlsm"
OUT = r"C:\Users\910373\AppData\Local\Temp\opencode\build\report_data.json"

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

def wan(x):
    return round(x / 1e4, 1)

def pct(x, nd=1):
    return f"{x * 100:.{nd}f}%"

D = {}
pythoncom.CoInitialize()
xl = None
try:
    xl = win32.DispatchEx("Excel.Application")
    xl.Visible = False
    xl.DisplayAlerts = False
    xl.AutomationSecurity = 1
    xl.AutoRecover.Enabled = False
    wb = with_retry(lambda: xl.Workbooks.Open(TPL, ReadOnly=True))

    def tv(sh, addr):
        return with_retry(lambda: wb.Worksheets(sh).Range(addr).Value)
    def rows(sh, r1, c1, r2, c2):
        v = with_retry(lambda: wb.Worksheets(sh).Range(wb.Worksheets(sh).Cells(r1, c1), wb.Worksheets(sh).Cells(r2, c2)).Value)
        return v

    # 镜像列
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
    Md = [d.replace(tzinfo=None) if isinstance(d, (dt.datetime, dt.date)) else None for d in mcol("发货日期")]
    MQ = [float(v) if isinstance(v, (int, float)) else 0.0 for v in mcol("数量")]
    MR = [float(v) if isinstance(v, (int, float)) else 0.0 for v in mcol("收入")]
    MP = [float(v) if isinstance(v, (int, float)) else 0.0 for v in mcol("利润")]
    MSKU = mcol("存货名称"); MCAT = mcol("客户类别全称"); MCUST = mcol("客户简称"); MPIN = mcol("品类"); MNEW = mcol("是否新品")
    N = n

    def win_agg(dimfn, d1, d2):
        a = collections.defaultdict(lambda: [0.0, 0.0, 0.0])
        for j in range(N):
            if Md[j] and d1 <= Md[j] <= d2:
                k = dimfn(j)
                a[k][0] += MR[j]; a[k][1] += MP[j]; a[k][2] += MQ[j]
        return a

    Y = 2026
    m1, m2, m3 = dt.datetime(Y, 8, 1), dt.datetime(Y, 7, 1), dt.datetime(Y - 1, 8, 1)
    m1e = dt.datetime(Y, 8, 31, 23, 59, 59); m2e = dt.datetime(Y, 7, 31, 23, 59, 59); m3e = dt.datetime(Y - 1, 8, 31, 23, 59, 59)
    ytd_s = dt.datetime(Y, 1, 1); lytd_s = dt.datetime(Y - 1, 1, 1)

    # 1 总览
    D["ov"] = {}
    for tag, d1, d2 in [("lastyear", m3, m3e), ("prev", m2, m2e), ("cur", m1, m1e), ("ytd", ytd_s, m1e), ("lytd", lytd_s, m3e)]:
        a, = [win_agg(lambda j: "T", d1, d2)]
        t = a["T"]
        D["ov"][tag] = {"rev": t[0], "pft": t[1], "qty": t[2], "m": t[1] / t[0]}
    cur, prev, ly = D["ov"]["cur"], D["ov"]["prev"], D["ov"]["lastyear"]
    D["ov"]["yoy"] = {"rev": cur["rev"] / ly["rev"] - 1, "pft": cur["pft"] / ly["pft"] - 1, "qty": cur["qty"] / ly["qty"] - 1, "m": cur["m"] - ly["m"]}
    D["ov"]["mom"] = {"rev": cur["rev"] / prev["rev"] - 1, "pft": cur["pft"] / prev["pft"] - 1, "qty": cur["qty"] / prev["qty"] - 1, "m": cur["m"] - prev["m"]}
    yt, lyt = D["ov"]["ytd"], D["ov"]["lytd"]
    D["ov"]["ytdd"] = {"rev": yt["rev"] / lyt["rev"] - 1, "pft": yt["pft"] / lyt["pft"] - 1, "m": yt["m"] - lyt["m"]}

    # 2 可比SKU数(同比/环比)
    def comp_counts(d0s, d0e):
        cur_set = collections.defaultdict(float); old_set = collections.defaultdict(float)
        for j in range(N):
            if Md[j] and MR[j] > 0:
                if m1 <= Md[j] <= m1e:
                    cur_set[MSKU[j]] += MR[j]
                elif d0s <= Md[j] <= d0e:
                    old_set[MSKU[j]] += MR[j]
        both = sum(1 for s in cur_set if s in old_set and old_set[s] > 0)
        return both, len(cur_set)
    D["comp_yoy"] = comp_counts(m3, m3e)
    D["comp_mom"] = comp_counts(m2, m2e)

    # 3 产品线 top4 (8月收入降序)
    pl = win_agg(lambda j: MPIN and j or j, m1, m1e)  # placeholder
    plm = win_agg(lambda j: None or None, m1, m1e)  # skip; 用2-sheet直接读
    pl_rows = []
    for r in range(4, 29):
        k = tv("2-产品线", f"A{r}")
        if not k:
            continue
        pl_rows.append({"name": k, "rev": tv("2-产品线", f"B{r}"), "pft": tv("2-产品线", f"C{r}"),
                        "m": tv("2-产品线", f"D{r}"), "m_ly": tv("2-产品线", f"E{r}"), "dm": tv("2-产品线", f"F{r}")})
    tot_rev = D["ov"]["cur"]["rev"]
    D["pl_top"] = [{"name": p["name"], "rev万": wan(p["rev"]), "share": p["rev"] / tot_rev,
                    "m": p["m"], "m_ly": p["m_ly"], "dm": p["dm"]} for p in pl_rows if p["rev"] and p["rev"] > 0][:6]

    # 4 客户分类 (含去年YTD毛利率)
    cls = {}
    for r in range(4, 8):
        c = tv("3-客户分类", f"A{r}")
        cls[c] = {"rev_m": tv("3-客户分类", f"B{r}"), "m_m": tv("3-客户分类", f"D{r}"),
                  "rev_y": tv("3-客户分类", f"E{r}"), "pft_y": tv("3-客户分类", f"F{r}"), "m_y": tv("3-客户分类", f"G{r}"),
                  "pft_ly": tv("3-客户分类", f"H{r}"), "dpft": tv("3-客户分类", f"I{r}")}
    a_y = win_agg(lambda j: (MCAT[j] or "?")[:2], ytd_s, m1e)
    a_l = win_agg(lambda j: (MCAT[j] or "?")[:2], lytd_s, m3e)
    D["cls"] = {c: {**v, "rev_ly_y": a_l[c][0] if c in a_l else 0, "m_ly_y": (a_l[c][1] / a_l[c][0]) if c in a_l and a_l[c][0] else None} for c, v in cls.items()}

    # 5 应用领域 top5 (YTD收入) + 新品列
    doms = []
    for r in range(4, 26):
        k = tv("5-应用领域", f"A{r}")
        if not k:
            continue
        doms.append({"name": k, "m_jan": tv("5-应用领域", f"E{r}"), "m_cur": tv("5-应用领域", f"F{r}"),
                     "dm": tv("5-应用领域", f"G{r}"), "rev_y": tv("5-应用领域", f"B{r}"), "m_y": tv("5-应用领域", f"D{r}"),
                     "newrev": tv("5-应用领域", f"H{r}"), "newm": tv("5-应用领域", f"I{r}"), "pen": tv("5-应用领域", f"J{r}")})
    D["dom_top"] = sorted([d for d in doms if d["rev_y"]], key=lambda x: -x["rev_y"])[:5]
    D["dom_new_top"] = sorted([d for d in doms if d["newrev"]], key=lambda x: -x["newrev"])[:5]

    # 6 案例SKU (表4)
    case_skus = ["TMI8180I", "TMI7604R", "TMI8116-Q1", "TME7352"]
    sku_y = win_agg(lambda j: MSKU[j], ytd_s, m1e)
    sku_m = win_agg(lambda j: MSKU[j], m1, m1e)
    sku_cust = collections.defaultdict(set)
    for j in range(N):
        if Md[j] and ytd_s <= Md[j] <= m1e and MNEW[j] == "是":
            sku_cust[MSKU[j]].add(MCUST[j])
    sku_cust_all = collections.defaultdict(set)
    for j in range(N):
        if Md[j] and ytd_s <= Md[j] <= m1e:
            sku_cust_all[MSKU[j]].add(MCUST[j])
    D["case"] = []
    for s in case_skus:
        y = sku_y.get(s, [0, 0, 0]); mth = sku_m.get(s, [0, 0, 0])
        D["case"].append({"sku": s, "rev_y": wan(y[0]), "rev_m": wan(mth[0]),
                          "m": (y[1] / y[0]) if y[0] else None, "cust": len(sku_cust_all.get(s, set()))})

    # 7 安克/CVTE (3.6案例)
    for nm in ["安克创新", "CVTE"]:
        a1 = win_agg(lambda j: MCUST[j] if MCUST[j] == nm else None, ytd_s, m1e)
        a0 = win_agg(lambda j: MCUST[j] if MCUST[j] == nm else None, lytd_s, m3e)
        v1 = a1.get(nm, [0, 0, 0]); v0 = a0.get(nm, [0, 0, 0])
        D.setdefault("cases36", {})[nm] = {"rev_y": wan(v1[0]), "m_y": v1[1] / v1[0] if v1[0] else None,
                                           "rev_l": wan(v0[0]), "m_l": v0[1] / v0[0] if v0[0] else None}

    # 8 SKU变化 (11表)
    D["sku_var"] = []
    for r in range(5, 8):
        D["sku_var"].append([tv("11-SKU变化", f"{c}{r}") for c in "ABCDEFGHI"])

    # 9 增加及流失 top6 (客户/类别/新增/流失/净/新增收入万/新增利润万/流失收入万/流失利润万)
    zrows = []
    for r in range(3, 55):
        nm = tv("增加及流失", f"B{r}")
        if not nm or nm == "合计":
            continue
        zrows.append([nm, tv("增加及流失", f"C{r}"), tv("增加及流失", f"D{r}"), tv("增加及流失", f"E{r}"),
                      tv("增加及流失", f"F{r}"), tv("增加及流失", f"G{r}"), tv("增加及流失", f"H{r}"),
                      tv("增加及流失", f"I{r}"), tv("增加及流失", f"J{r}")])
        if len(zrows) >= 8:
            break
    D["zengliu"] = zrows

    # 10 DCDC-18V 品类 8月 + YTD
    for r in range(4, 83):
        k = tv("6-全品类", f"A{r}")
        if k == "DCDC-18V-降压2~4A":
            D["dcdc18"] = {"rev_m": wan(tv("6-全品类", f"B{r}")), "m_m": tv("6-全品类", f"D{r}"),
                           "rev_y": wan(tv("6-全品类", f"E{r}")), "m_y": tv("6-全品类", f"G{r}")}
            break

    # 11 STI3452HFI
    D["sti"] = {"rev_m": wan(tv("9-成本监控", "B11")), "pft_m": wan(tv("9-成本监控", "C11")),
                "qty_m": tv("9-成本监控", "E11"), "uc_m": tv("9-成本监控", "F11"),
                "uc_prev": tv("9-成本监控", "F10"), "m_m": tv("9-成本监控", "G11")}

    # 12 新品 (8表+2b表)
    D["newp"] = {"rev_m": wan(tv("8-新品", "B4")), "m_m": tv("8-新品", "D4"), "share_m": tv("8-新品", "G4"),
                 "rev_y": wan(tv("8-新品", "B5")), "m_y": tv("8-新品", "D5"), "share_y": tv("8-新品", "G5")}
    D["bands"] = []
    for r in range(4, 10):
        D["bands"].append([tv("2b-新品分档", f"A{r}"), tv("2b-新品分档", f"B{r}"), tv("2b-新品分档", f"E{r}"), tv("2b-新品分档", f"F{r}")])

    # 13 26-成本上升
    D["cost_up"] = []
    for r in range(5, 12):
        k = tv("26-成本上升品类", f"A{r}")
        if k:
            D["cost_up"].append([k, tv("26-成本上升品类", f"B{r}"), tv("26-成本上升品类", f"C{r}")])

    # 14 前20 (用于叙事: 排名变动)
    D["top20"] = []
    for r in range(4, 14):
        D["top20"].append([tv("4-前20大客户", f"A{r}"), tv("4-前20大客户", f"B{r}"), wan(tv("4-前20大客户", f"C{r}")),
                           tv("4-前20大客户", f"E{r}"), wan(tv("4-前20大客户", f"F{r}"))])

    # 15 21-限量出货 top4 (行动建议用)
    D["act21"] = []
    for r in range(5, 10):
        k = tv("21-限量出货名单", f"A{r}")
        if k:
            D["act21"].append([k, tv("21-限量出货名单", f"B{r}"), tv("21-限量出货名单", f"C{r}"),
                               tv("21-限量出货名单", f"D{r}"), tv("21-限量出货名单", f"E{r}"), tv("21-限量出货名单", f"G{r}")])

    # 16 1月四因子 (Dec2025 vs Jan2026)
    def four(d0s, d0e, d1s, d1e):
        curd = collections.defaultdict(lambda: [0.0, 0.0, 0.0]); oldd = collections.defaultdict(lambda: [0.0, 0.0, 0.0])
        for j in range(N):
            if not Md[j]:
                continue
            if d1s <= Md[j] <= d1e:
                a = curd[MSKU[j]]; a[0] += MR[j]; a[1] += MP[j]; a[2] += MQ[j]
            elif d0s <= Md[j] <= d0e:
                a = oldd[MSKU[j]]; a[0] += MR[j]; a[1] += MP[j]; a[2] += MQ[j]
        Q1 = sum(v[2] for v in curd.values()); Q0 = sum(v[2] for v in oldd.values())
        G0 = sum(v[1] for v in oldd.values())
        e_vol = (Q1 - Q0) * (G0 / Q0 if Q0 else 0)
        q1_um0 = 0.0; e_price = 0.0; e_cost = 0.0
        for s in curd:
            if s in oldd:
                q1, rv1, gp1 = curd[s]
                q0, rv0, gp0 = oldd[s]
                if q1 > 0 and q0 > 0 and rv1 > 0 and rv0 > 0:
                    um0 = (rv0 - gp0) / q0
                    q1_um0 += q1 * um0
                    e_price += q1 * (rv1 / q1 - rv0 / q0)
                    e_cost += q1 * (um0 - (rv1 - gp1) / q1)
        e_struct = q1_um0 - Q1 * (G0 / Q0 if Q0 else 0)
        return round(e_vol / 1e4), round(e_struct / 1e4), round(e_price / 1e4), round(e_cost / 1e4)
    D["jan_bridge"] = four(dt.datetime(2025, 12, 1), dt.datetime(2025, 12, 31, 23, 59, 59),
                           dt.datetime(2026, 1, 1), dt.datetime(2026, 1, 31, 23, 59, 59))

    wb.Close(SaveChanges=False)
finally:
    if xl is not None:
        try:
            xl.Quit()
        except Exception:
            pass
    pythoncom.CoUninitialize()

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(D, f, ensure_ascii=False, indent=1, default=str)
print("REPORT_DATA_DONE")
