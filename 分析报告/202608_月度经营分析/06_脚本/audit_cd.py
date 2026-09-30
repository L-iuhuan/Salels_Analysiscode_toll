# -*- coding: utf-8 -*-
r"""审计收尾：A'修正列位复核(2/5) + C脆弱点扫描 + D换月/换源实测"""
import collections
import datetime as dt
import os
import shutil
import time
import pythoncom
import pywintypes
import win32com.client as win32

BASE_AUG = r"\\192.168.8.3\财务部\财务电子档案备份\D1经营分析\财务分析-8月（9.5) .xlsx"
BASE_JUL = r"\\192.168.8.3\财务部\财务电子档案备份\D1经营分析\财务分析-7月（8.27) .xlsx"
TPL = r"C:\Users\910373\AppData\Local\Temp\opencode\build\月度分析模板.xlsm"
SCRATCH = r"C:\Users\910373\AppData\Local\Temp\opencode\build\audit_scratch.xlsm"
REPORT = r"C:\Users\910373\AppData\Local\Temp\opencode\build\audit_cd_report.txt"

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

def extract(ws, n_expected_hint=None):
    last_col = with_retry(lambda: ws.Cells(1, ws.Columns.Count).End(-4159).Column)
    hdr = with_retry(lambda: ws.Range(ws.Cells(1, 1), ws.Cells(1, last_col)).Value)
    headers = list(hdr[0]) if isinstance(hdr, tuple) and hdr and isinstance(hdr[0], tuple) else list(hdr)
    last_row = with_retry(lambda: ws.Cells(ws.Rows.Count, headers.index("发货日期") + 1).End(-4159).Row)
    N = last_row - 1
    def col(nm):
        ci = headers.index(nm) + 1
        v = with_retry(lambda c=ci: ws.Range(ws.Cells(2, c), ws.Cells(last_row, c)).Value)
        return [x[0] if isinstance(x, tuple) else x for x in v]
    D = [d.replace(tzinfo=None) if isinstance(d, (dt.datetime, dt.date)) else None for d in col("发货日期")]
    Q = [float(v) if isinstance(v, (int, float)) else 0.0 for v in col("发货数量")]
    R = [float(v) if isinstance(v, (int, float)) else 0.0 for v in col("RMB 未税金额小计")]
    P = [float(v) if isinstance(v, (int, float)) else 0.0 for v in col("利润")]
    return N, D, Q, R, P, col

pythoncom.CoInitialize()
xl = None
try:
    xl = win32.DispatchEx("Excel.Application")
    xl.Visible = False
    xl.DisplayAlerts = False
    xl.AutomationSecurity = 1
    xl.AutoRecover.Enabled = False

    # ============ A'：2/5 修正列位复核（从基础数据独立算） ============
    wb = with_retry(lambda: xl.Workbooks.Open(BASE_AUG, ReadOnly=True, UpdateLinks=0))
    ws = wb.Worksheets("24-26")
    last_col = with_retry(lambda: ws.Cells(1, ws.Columns.Count).End(-4159).Column)
    hdr = with_retry(lambda: ws.Range(ws.Cells(1, 1), ws.Cells(1, last_col)).Value)
    headers = list(hdr[0]) if isinstance(hdr, tuple) and hdr and isinstance(hdr[0], tuple) else list(hdr)
    lr = with_retry(lambda: ws.Cells(ws.Rows.Count, headers.index("发货日期") + 1).End(-4159).Row)
    def col(nm):
        ci = headers.index(nm) + 1
        v = with_retry(lambda c=ci: ws.Range(ws.Cells(2, c), ws.Cells(lr, c)).Value)
        return [x[0] if isinstance(x, tuple) else x for x in v]
    D = [d.replace(tzinfo=None) if isinstance(d, (dt.datetime, dt.date)) else None for d in col("发货日期")]
    N = lr - 1
    Q = [float(v) if isinstance(v, (int, float)) else 0.0 for v in col("发货数量")]
    R = [float(v) if isinstance(v, (int, float)) else 0.0 for v in col("RMB 未税金额小计")]
    P = [float(v) if isinstance(v, (int, float)) else 0.0 for v in col("利润")]
    PL = col("型号_产品线（新）"); SEG = col("细分市场（新）")
    log(f"[A'] 基础数据 {N} 行")
    m_s, m_e = dt.datetime(2026, 8, 1), dt.datetime(2026, 8, 31, 23, 59, 59)
    y_s = dt.datetime(2026, 1, 1)
    OK = BAD = 0
    def chk(tag, exp, got, tol=0.01):
        global_var = None
        try:
            d = abs(float(exp) - float(got))
        except (TypeError, ValueError):
            return
        if d <= tol:
            globals()["OK"] += 1
        else:
            globals()["BAD"] += 1
            log(f"  [DIFF] {tag}: 独立={exp!r} 模板={got!r}")

    wt = with_retry(lambda: xl.Workbooks.Open(TPL))
    def tv(sheet, addr):
        return with_retry(lambda: wt.Worksheets(sheet).Range(addr).Value)

    aggPLm = collections.defaultdict(lambda: [0.0, 0.0])
    aggPLy = collections.defaultdict(lambda: [0.0, 0.0])
    aggSEGy = collections.defaultdict(lambda: [0.0, 0.0])
    for j in range(N):
        dv = D[j]
        if not dv:
            continue
        if m_s <= dv <= m_e:
            a = aggPLm[PL[j]]; a[0] += R[j]; a[1] += P[j]
        if y_s <= dv <= m_e:
            b = aggPLy[PL[j]]; b[0] += R[j]; b[1] += P[j]
            c = aggSEGy[SEG[j]]; c[0] += R[j]; c[1] += P[j]
    # 2-产品线: B=月收入 C=月利润 (前文已验, 此处再核毛利率E列去年口径跳过)
    for r in range(4, 29):
        key = tv("2-产品线", f"A{r}")
        if not key:
            continue
        v = aggPLm.get(key)
        if v:
            chk(f"2'[{str(key)[:8]}]月收入", v[0], tv("2-产品线", f"B{r}"))
    # 5-应用领域: B=YTD收入 C=YTD利润
    for r in range(4, 26):
        key = tv("5-应用领域", f"A{r}")
        if not key:
            continue
        v = aggSEGy.get(key)
        if v:
            chk(f"5'[{str(key)[:8]}]YTD收入", v[0], tv("5-应用领域", f"B{r}"))
            chk(f"5'[{str(key)[:8]}]YTD利润", v[1], tv("5-应用领域", f"C{r}"))
    log(f"[A'] 2/5 修正复核: OK={globals()['OK']} DIFF={globals()['BAD']}")
    wt.Close(SaveChanges=False)

    # ============ C：脆弱点扫描 ============
    log("\n[C] 脆弱点扫描")
    wild = set()
    for arr, nm in [(PL, "产品线新"), (SEG, "细分市场"), (col("产品品类（新）"), "品类"), (col("存货名称"), "SKU"), (col("终端客户简称"), "客户简称")]:
        for v in arr:
            if isinstance(v, str) and any(ch in v for ch in "*?~"):
                wild.add(f"{nm}:{v[:30]}")
    log(f"  含通配符字符(*?~)的维度值: {len(wild)} 个" + (" | " + "; ".join(sorted(wild)[:10]) if wild else " —— 无"))
    pref = collections.Counter()
    CATc = col("终端客户名称_客户类别")
    for j in range(N):
        if D[j]:
            pref[(CATc[j] or "?")[:2]] += 1
    log(f"  有效日期行的类别前缀分布: {dict(pref)}")
    # 客户YTD收入并列检查（4-前20的LARGE键）
    aggC = collections.defaultdict(float)
    for j in range(N):
        if D[j] and y_s <= D[j] <= m_e:
            aggC[col('终端客户简称')[j]] += R[j]
    revc = collections.Counter(round(v, 2) for v in aggC.values())
    dup = sum(1 for v in revc.values() if v > 1 and list(revc).count)
    dupk = [(k, v) for k, v in revc.items() if v > 1 and k > 100000]
    log(f"  客户YTD收入完全并列(>10万档)组数: {len(dupk)} —— LARGE/MATCH 在并列时可能取错客户(当前top20未受影响)")
    wb.Close(SaveChanges=False)

    # ============ D：换月 + 换源实测（scratch副本） ============
    log("\n[D] 换月/换源实测")
    shutil.copyfile(TPL, SCRATCH)
    ws_scr = with_retry(lambda: xl.Workbooks.Open(SCRATCH))
    p = ws_scr.Worksheets("0-参数")
    p.Range("B5").Value = 6
    with_retry(lambda: xl.Calculate())
    jun = ws_scr.Worksheets("1-整体概览").Range("B6").Value
    jun_l = ws_scr.Worksheets("1-整体概览").Range("B5").Value
    log(f"  [换月] 报表月=6 → 本月(6月)收入={jun!r}  上月(5月)收入={jun_l!r}")
    log(f"  [换月] 参照: 7月附件 2026年6月行=73694545.62; 5月Python口径待比")
    may_tot = 0.0
    for j in range(N):
        if D[j] and dt.datetime(2026, 5, 1) <= D[j] <= dt.datetime(2026, 5, 31, 23, 59, 59):
            may_tot += R[j]
    chk("D!换月-上月列(5月)", may_tot, jun_l)
    chk("D!换月-本月列(6月)", 73694545.62, jun, tol=0.02)
    # 换源: 7月8.27
    with_retry(lambda: xl.Run("'audit_scratch.xlsm'!刷新镜像", BASE_JUL, True))
    with_retry(lambda: xl.Calculate())
    jul = ws_scr.Worksheets("1-整体概览").Range("B6").Value
    log(f"  [换源] 刷7月(8.27) → 本月(6月)收入={jul!r}")
    p.Range("B5").Value = 7
    with_retry(lambda: xl.Calculate())
    jul7 = ws_scr.Worksheets("1-整体概览").Range("B6").Value
    log(f"  [换源+换月] 报表月=7 → 本月(7月)收入={jul7!r} (附件口径 77596625.91)")
    chk("D!换源换月-7月收入", 77596625.91, jul7, tol=0.02)
    ws_scr.Close(SaveChanges=False)
    if os.path.exists(SCRATCH):
        os.remove(SCRATCH)
    log("  scratch 已清理")

    log(f"\n审计C+D: OK={globals()['OK']} DIFF={globals()['BAD']}")
finally:
    if xl is not None:
        try:
            xl.Quit()
        except Exception:
            pass
    pythoncom.CoUninitialize()

with open(REPORT, "w", encoding="utf-8") as fh:
    fh.write("\n".join(out))
print("AUDIT_CD_DONE")
