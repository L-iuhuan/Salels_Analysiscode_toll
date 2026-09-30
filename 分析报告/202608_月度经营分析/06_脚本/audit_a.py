# -*- coding: utf-8 -*-
r"""审计A+B：独立路径重算 —— 直接从基础数据(8月9.5的24-26原表)用Python聚合，
与模板计算值逐项比对；并做跨维度守恒校验。不经镜像、不经模板公式。"""
import pickle
import collections
import datetime as dt
import time
import pythoncom
import pywintypes
import win32com.client as win32

BASE = r"\\192.168.8.3\财务部\财务电子档案备份\D1经营分析\财务分析-8月（9.5) .xlsx"
TPL = r"C:\Users\910373\AppData\Local\Temp\opencode\build\月度分析模板.xlsm"
CACHE = r"C:\Users\910373\AppData\Local\Temp\opencode\build\audit_base.pkl"
REPORT = r"C:\Users\910373\AppData\Local\Temp\opencode\build\audit_a_report.txt"

out = []
def log(s=""):
    out.append(str(s))
    print(str(s).encode("ascii", "replace").decode("ascii"))

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

NEED = ["发货日期", "终端客户简称", "终端客户名称_客户类别", "细分市场（新）", "型号_产品线（新）",
        "产品品类（新）", "存货名称", "是否新品", "发货数量", "RMB 未税金额小计", "利润"]

pythoncom.CoInitialize()
xl = None
try:
    xl = win32.DispatchEx("Excel.Application")
    xl.Visible = False
    xl.DisplayAlerts = False
    xl.AutomationSecurity = 1
    xl.AutoRecover.Enabled = False

    # ============ 抽取基础数据（独立路径） ============
    if True:
        wb = with_retry(lambda: xl.Workbooks.Open(BASE, ReadOnly=True, UpdateLinks=0))
        ws = wb.Worksheets("24-26")
        last_col = with_retry(lambda: ws.Cells(1, ws.Columns.Count).End(-4159).Column)
        hdr = with_retry(lambda: ws.Range(ws.Cells(1, 1), ws.Cells(1, last_col)).Value)
        if isinstance(hdr, tuple) and hdr and isinstance(hdr[0], tuple):
            headers = list(hdr[0])
        elif isinstance(hdr, tuple):
            headers = list(hdr)
        else:
            headers = [hdr]
        # 尾部垃圾防御（同VBA逻辑：三列交叉最小）
        def endup(cidx):
            return with_retry(lambda: ws.Cells(ws.Rows.Count, cidx).End(-4159).Row)
        last_row = min(endup(headers.index("发货日期") + 1), endup(headers.index("存货名称") + 1), endup(headers.index("RMB 未税金额小计") + 1))
        log(f"基础数据: {last_row - 1} 行")
        cols = {}
        for nm in NEED:
            cidx = headers.index(nm) + 1
            vals = with_retry(lambda c=cidx: ws.Range(ws.Cells(2, c), ws.Cells(last_row, c)).Value)
            cols[nm] = [v[0] if isinstance(v, tuple) else v for v in vals]
        wb.Close(SaveChanges=False)
        N = last_row - 1
        D = [d.replace(tzinfo=None) if isinstance(d, (dt.datetime, dt.date)) else None for d in cols["发货日期"]]
        def num(arr):
            return [float(v) if isinstance(v, (int, float)) else 0.0 for v in arr]
        Q, R, P = num(cols["发货数量"]), num(cols["RMB 未税金额小计"]), num(cols["利润"])
        CUST, CAT, SEG, PL, PIN, SKU, NEW = (cols["终端客户简称"], cols["终端客户名称_客户类别"],
                                             cols["细分市场（新）"], cols["型号_产品线（新）"],
                                             cols["产品品类（新）"], cols["存货名称"], cols["是否新品"])

    # ============ 打开模板读值 ============
    wt = with_retry(lambda: xl.Workbooks.Open(TPL))
    def tv(sheet, addr):
        return with_retry(lambda: wt.Worksheets(sheet).Range(addr).Value)
    def tcells(sheet, r1, c1, r2, c2):
        v = with_retry(lambda: wt.Worksheets(sheet).Range(wt.Worksheets(sheet).Cells(r1, c1), wt.Worksheets(sheet).Cells(r2, c2)).Value)
        if isinstance(v, (str, int, float)) or v is None:
            return ((v,),)
        if isinstance(v, tuple) and v and not isinstance(v[0], tuple):
            return (v,)
        return v

    # ============ Python 独立聚合 ============
    def agg(dim_fn, d1, d2):
        a = collections.defaultdict(lambda: [0.0, 0.0, 0.0])
        tot = [0.0, 0.0, 0.0]
        for j in range(N):
            dv = D[j]
            if dv and d1 <= dv <= d2:
                k = dim_fn(j)
                a[k][0] += Q[j]; a[k][1] += R[j]; a[k][2] += P[j]
                tot[0] += Q[j]; tot[1] += R[j]; tot[2] += P[j]
        return a, tot

    Y, M = 2026, 8
    m_start = dt.datetime(Y, M, 1); m_end = dt.datetime(Y, M, 31, 23, 59, 59)
    lm_start = dt.datetime(Y, 7, 1); lm_end = dt.datetime(Y, 7, 31, 23, 59, 59)
    ly_start = dt.datetime(Y - 1, 8, 1); ly_end = dt.datetime(Y - 1, 8, 31, 23, 59, 59)
    ytd_s = dt.datetime(Y, 1, 1)
    lytd_s = dt.datetime(Y - 1, 1, 1); lytd_e = dt.datetime(Y - 1, 8, 31, 23, 59, 59)

    OK = BAD = 0
    def chk(tag, exp, got, tol=0.01):
        global OK, BAD
        if exp is None or got is None or got == "":
            return
        try:
            d = abs(float(exp) - float(got))
        except (TypeError, ValueError):
            return
        if d <= tol:
            OK += 1
        else:
            BAD += 1
            log(f"  [DIFF] {tag}: 独立={exp!r} 模板={got!r} 差={d:.6g}")

    # ---- 1-整体概览 ----
    log("== 1-整体概览 ==")
    for label, d1, d2, row in [("去年同月", ly_start, ly_end, 4), ("上月", lm_start, lm_end, 5),
                               ("本月", m_start, m_end, 6), ("YTD", ytd_s, m_end, 7), ("去年YTD", lytd_s, lytd_e, 8)]:
        _, tot = agg(lambda j: "T", d1, d2)
        cells = tcells("1-整体概览", row, 2, row, 4)
        chk(f"1!{label}收入", tot[1], cells[0][0])
        chk(f"1!{label}利润", tot[2], cells[0][1])
        chk(f"1!{label}数量", tot[0], cells[0][2])

    # ---- 3-客户分类 ----
    log("== 3-客户分类 ==")
    a3, _ = agg(lambda j: (CAT[j] or "None")[:2], m_start, m_end)
    for r, cat in [(4, "KA"), (5, "AA"), (6, "KM"), (7, "MM")]:
        e = a3.get(cat, [0, 0, 0])
        chk(f"3!{cat}月收入", e[1], tv("3-客户分类", f"B{r}"))
        chk(f"3!{cat}月利润", e[2], tv("3-客户分类", f"C{r}"))
    a3y, _ = agg(lambda j: (CAT[j] or "None")[:2], ytd_s, m_end)
    chk("3!KA_YTD收入", a3y["KA"][1], tv("3-客户分类", "E4"))
    a3l, _ = agg(lambda j: (CAT[j] or "None")[:2], lytd_s, lytd_e)
    chk("3!KA_去年YTD利润", a3l["KA"][2], tv("3-客户分类", "H4"))

    # ---- 2/5/6 维度表 ----
    for sheet, dimfn, cols_n in [("2-产品线", lambda j: PL[j], 5), ("5-应用领域", lambda j: SEG[j], 9), ("6-全品类", lambda j: PIN[j], 6)]:
        log(f"== {sheet} ==")
        am, _ = agg(dimfn, m_start, m_end)
        ay, _ = agg(dimfn, ytd_s, m_end)
        # 读模板全部行
        rows = tcells(sheet, 4, 1, 90, cols_n)
        nchecked = 0
        for ri, row in enumerate(rows):
            key = row[0]
            if not key:
                continue
            vals_m = am.get(key)
            if vals_m is None:
                continue  # 模板行在基础数据无记录(0值行)
            chk(f"{sheet}[{key[:12]}]月收入", vals_m[1], row[1])
            chk(f"{sheet}[{key[:12]}]月利润", vals_m[2], row[2])
            if cols_n >= 5:
                chk(f"{sheet}[{key[:12]}]YTD收入", ay[key][1], row[4 - (9 - cols_n)] if cols_n == 9 else row[4])
            nchecked += 1
        log(f"  独立比对 {nchecked} 行")

    # ---- 4-前20 ----
    log("== 4-前20大客户 ==")
    a4, _ = agg(lambda j: CUST[j], ytd_s, m_end)
    a4m, _ = agg(lambda j: CUST[j], m_start, m_end)
    a4l, _ = agg(lambda j: CUST[j], lytd_s, lytd_e)
    a4p, _ = agg(lambda j: (CUST[j], 1), lytd_s, lytd_e)
    lastY = collections.defaultdict(lambda: [0.0, 0.0])
    for j in range(N):
        dv = D[j]
        if dv and lytd_s <= dv <= lytd_e:
            k = CUST[j]
            lastY[k][0] += R[j]; lastY[k][1] += P[j]
    top = sorted(a4.items(), key=lambda kv: -kv[1][1])[:20]
    for i, (cust, v) in enumerate(top):
        r = 4 + i
        got = tcells("4-前20大客户", r, 2, r, 7)
        if got[0][0] != cust:
            BAD += 1
            log(f"  [DIFF] 4!第{i+1}名客户: 独立={cust} 模板={got[0][0]}")
            continue
        chk(f"4!{cust}YTD收入", v[1], got[0][1])
        chk(f"4!{cust}YTD利润", v[2], got[0][2])
        chk(f"4!{cust}月收入", a4m[cust][1], got[0][4])
        chk(f"4!{cust}去年YTD收入", lastY[cust][0], got[0][5])

    # ---- 8-新品 ----
    log("== 8-新品 ==")
    for label, d1, d2, r in [("月", m_start, m_end, 4), ("YTD", ytd_s, m_end, 5)]:
        tot_new = [0.0, 0.0]
        tot_all = [0.0, 0.0]
        for j in range(N):
            dv = D[j]
            if dv and d1 <= dv <= d2:
                tot_all[0] += R[j]; tot_all[1] += P[j]
                if NEW[j] == "是":
                    tot_new[0] += R[j]; tot_new[1] += P[j]
        chk(f"8!{label}新品收入", tot_new[0], tv("8-新品", f"B{r}"))
        chk(f"8!{label}新品利润", tot_new[1], tv("8-新品", f"C{r}"))
        chk(f"8!{label}整体收入", tot_all[0], tv("8-新品", f"E{r}"))

    # ---- 9-成本监控 (STI3452HFI 月度序列) ----
    log("== 9-成本监控 ==")
    for mi in range(1, 9):
        s = dt.datetime(Y, mi, 1)
        e = dt.datetime(Y, mi, [31, 29 if Y % 4 == 0 else 28, 31, 30, 31, 30, 31, 31][mi - 1], 23, 59, 59)
        q = r_ = p_ = 0.0
        for j in range(N):
            dv = D[j]
            if dv and s <= dv <= e and SKU[j] == "STI3452HFI":
                q += Q[j]; r_ += R[j]; p_ += P[j]
        got = tcells("9-成本监控", 3 + mi, 2, 3 + mi, 5)
        chk(f"9!{Y}-{mi:02d}收入", r_, got[0][0])
        chk(f"9!{Y}-{mi:02d}利润", p_, got[0][1])
        chk(f"9!{Y}-{mi:02d}数量", q, got[0][3])

    # ---- 2b 分档 ----
    log("== 2b-新品分档 ==")
    sku_y = collections.defaultdict(lambda: [0.0, 0.0])
    for j in range(N):
        dv = D[j]
        if dv and ytd_s <= dv <= m_end and NEW[j] == "是":
            k = SKU[j]
            sku_y[k][0] += R[j]; sku_y[k][1] += P[j]
    bands = [(0.45, 1.01), (0.39, 0.45), (0.25, 0.39), (0.0, 0.25), (-99, 0.0)]
    for bi, (lo, hi) in enumerate(bands):
        cnt = rev = 0
        for k, (rv, pf) in sku_y.items():
            if rv > 0 and lo <= pf / rv < hi:
                cnt += 1; rev += rv
        r = 4 + bi
        chk(f"2b!band{bi}SKU数", cnt, tv("2b-新品分档", f"B{r}"), tol=0)
        chk(f"2b!band{bi}收入万", round(rev / 10000), tv("2b-新品分档", f"D{r}"), tol=1.0)

    # ---- 25 SKU数口径抽查 ----
    log("== 25-品类四档(抽查SKU数/收入) ==")
    pin_first = {}
    for j in range(N):
        s = SKU[j]
        if s and s not in pin_first:
            pin_first[s] = PIN[j]
    sku_cat_y = collections.defaultdict(lambda: [0.0, 0.0])
    for j in range(N):
        dv = D[j]
        if dv and ytd_s <= dv <= m_end:
            k = SKU[j]
            sku_cat_y[k][0] += R[j]; sku_cat_y[k][1] += P[j]
    cat_sku_cnt = collections.Counter()
    cat_rev = collections.defaultdict(float)
    cat_pft = collections.defaultdict(float)
    for s, (rv, pf) in sku_cat_y.items():
        c = pin_first.get(s)
        if c:
            if rv > 0:
                cat_sku_cnt[c] += 1
            cat_rev[c] += rv
            cat_pft[c] += pf
    rows25 = tcells("25-品类四档分类", 5, 2, 81, 6)
    for row in rows25:
        key = row[0]
        if not key:
            continue
        if key in cat_sku_cnt:
            chk(f"25!{str(key)[:10]}SKU数", cat_sku_cnt[key], row[3], tol=0)
            chk(f"25!{str(key)[:10]}YTD万", round(cat_rev[key] / 10000), row[1], tol=1.0)

    # ---- 26 成本效应 ----
    log("== 26-成本上升(成本效应) ==")
    sku_uc = collections.defaultdict(lambda: [0.0] * 6)  # q7,r7,p7,q6,r6,p6
    for j in range(N):
        dv = D[j]
        if not dv:
            continue
        s = SKU[j]
        if m_start <= dv <= m_end:
            sku_uc[s][0] += Q[j]; sku_uc[s][1] += R[j]; sku_uc[s][2] += P[j]
        elif lm_start <= dv <= lm_end:
            sku_uc[s][3] += Q[j]; sku_uc[s][4] += R[j]; sku_uc[s][5] += P[j]
    cat_eff = collections.defaultdict(float)
    for s, (q7, r7, p7, q6, r6, p6) in sku_uc.items():
        if q7 > 0 and q6 > 0:
            uc6 = (r6 - p6) / q6
            uc7 = (r7 - p7) / q7
            c = pin_first.get(s)
            if c:
                cat_eff[c] += (uc6 - uc7) * q7
    rows26 = tcells("26-成本上升品类", 5, 1, 30, 3)
    for row in rows26:
        key = row[0]
        if not key:
            continue
        if key in cat_eff:
            chk(f"26!{str(key)[:10]}成本效应万", round(cat_eff[key] / 10000), row[2], tol=1.0)

    # ---- 10-毛利桥 ----
    log("== 10-毛利桥 ==")
    def bridge_py(d0s, d0e):
        cur = collections.defaultdict(lambda: [0.0, 0.0, 0.0])
        old = collections.defaultdict(lambda: [0.0, 0.0, 0.0])
        for j in range(N):
            dv = D[j]
            if not dv:
                continue
            if m_start <= dv <= m_end:
                a = cur[SKU[j]]; a[0] += Q[j]; a[1] += R[j]; a[2] += P[j]
            elif d0s <= dv <= d0e:
                a = old[SKU[j]]; a[0] += Q[j]; a[1] += R[j]; a[2] += P[j]
        eV = eP = eC = 0.0
        g0 = g1 = r0 = r1 = 0.0
        for s in cur:
            if s in old:
                q1, rv1, gp1 = cur[s]
                q0, rv0, gp0 = old[s]
                if q1 > 0 and q0 > 0 and rv1 > 0 and rv0 > 0:
                    p1 = rv1 / q1; p0 = rv0 / q0
                    c1 = (rv1 - gp1) / q1; c0 = (rv0 - gp0) / q0
                    eV += (q1 - q0) * (p0 - c0)
                    eP += q1 * (p1 - p0)
                    eC += q1 * (c0 - c1)
                    g0 += gp0; g1 += gp1; r0 += rv0; r1 += rv1
        return eV, eP, eC, g1 - g0
    eV, eP, eC, dgp = bridge_py(ly_start, ly_end)
    for cidx, ev in [(2, eV), (3, eP), (4, eC), (5, dgp)]:
        chk(f"10!同比c{cidx}", round(ev / 10000), tv("10-毛利桥", f"{chr(64+cidx)}5"), tol=1.0)
    eV, eP, eC, dgp = bridge_py(lm_start, lm_end)
    for cidx, ev in [(2, eV), (3, eP), (4, eC), (5, dgp)]:
        chk(f"10!环比c{cidx}", round(ev / 10000), tv("10-毛利桥", f"{chr(64+cidx)}6"), tol=1.0)

    # ---- 11-SKU变化 ----
    log("== 11-SKU变化 ==")
    r12s = dt.datetime(Y - 1, 9, 1); r12e = m_end
    p12s = dt.datetime(Y - 2, 9, 1); p12e = dt.datetime(Y - 1, 8, 31, 23, 59, 59)
    grp_cur = {}; grp_pre = {}
    cust_set = set()
    for j in range(N):
        dv = D[j]
        if not dv:
            continue
        cg = (CAT[j] or "")[:2]
        if cg not in ("KA", "AA"):
            continue
        if r12s <= dv <= r12e:
            grp_cur.setdefault((cg, SKU[j]), [0.0, 0.0])
            grp_cur[(cg, SKU[j])][0] += R[j]; grp_cur[(cg, SKU[j])][1] += P[j]
            cust_set.add((cg, CUST[j]))
        elif p12s <= dv <= p12e:
            grp_pre.setdefault((cg, SKU[j]), [0.0, 0.0])
            grp_pre[(cg, SKU[j])][0] += R[j]; grp_pre[(cg, SKU[j])][1] += P[j]
    for r, label, grps in [(5, "ALL", ("KA", "AA")), (6, "KA", ("KA",)), (7, "AA", ("AA",))]:
        cc = sum(1 for (g, _) in cust_set if g in grps)
        newN = sum(1 for k in grp_cur if k[0] in grps and k not in grp_pre)
        lostN = sum(1 for k in grp_pre if k[0] in grps and k not in grp_cur)
        rvn = sum(v[0] for k, v in grp_cur.items() if k[0] in grps and k not in grp_pre)
        chk(f"11!{label}客户数", cc, tv("11-SKU变化", f"B{r}"), tol=0)
        chk(f"11!{label}新增SKU", newN, tv("11-SKU变化", f"C{r}"), tol=0)
        chk(f"11!{label}流失SKU", lostN, tv("11-SKU变化", f"D{r}"), tol=0)
        chk(f"11!{label}新增收入万", round(rvn / 10000), tv("11-SKU变化", f"F{r}"), tol=1.0)

    # ---- B. 跨维度守恒 ----
    log("== 守恒校验 ==")
    _, tot_m = agg(lambda j: "T", m_start, m_end)
    b1 = tv("1-整体概览", "B6")
    s3 = sum(tv("3-客户分类", f"B{r}") or 0 for r in range(4, 8))
    am2, _ = agg(lambda j: PL[j], m_start, m_end)
    s2py = sum(v[1] for v in am2.values())
    log(f"  总收入(Python)={tot_m[1]:.2f} | 1!B6={b1:.2f} | Σ3-客户分类={s3:.2f} | Σ2-产品线(Python)={s2py:.2f}")
    chk("守恒:1!B6 vs Python", tot_m[1], b1)
    chk("守恒:Σ3 vs 1!B6", b1, s3)

    # ---- 类别前缀覆盖 ----
    prefixes = collections.Counter((CAT[j] or "∅")[:2] for j in range(N))
    log("  类别前缀分布: " + str(dict(prefixes)))

    log(f"\n审计A+B合计: OK={OK} DIFF={BAD}")
    wt.Close(SaveChanges=False)
finally:
    if xl is not None:
        try:
            xl.Quit()
        except Exception:
            pass
    pythoncom.CoUninitialize()

with open(REPORT, "w", encoding="utf-8") as fh:
    fh.write("\n".join(out))
print("AUDIT_A_DONE")
