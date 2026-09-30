# -*- coding: utf-8 -*-
r"""审计C+D轻量版：
C=镜像维度通配符/类别覆盖扫描；D=换月(6)与换源(7月8.27)实测，用附件常数做独立锚点"""
import collections
import os
import shutil
import time
import datetime as dt
import pythoncom
import pywintypes
import win32com.client as win32

BASE_JUL = r"\\192.168.8.3\财务部\财务电子档案备份\D1经营分析\财务分析-7月（8.27) .xlsx"
TPL = r"C:\Users\910373\AppData\Local\Temp\opencode\build\月度分析模板.xlsm"
SCRATCH = r"C:\Users\910373\AppData\Local\Temp\opencode\build\audit_scratch.xlsm"
REPORT = r"C:\Users\910373\AppData\Local\Temp\opencode\build\audit_cd_report.txt"

ATT_JUN_REV = 73694545.62      # 7月附件 2026年6月行(收入)
ATT_JUN_PFT = 24045539.615
ATT_JUN_QTY = 430785579.0
ATT_JUL_REV = 77596625.91      # 附件 2026年7月行
ATT_JUL_PFT = 23470687.09

out = []
def log(s=""):
    out.append(str(s))
    print(str(s).encode("ascii", "replace").decode("ascii"), flush=True)

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

OK = BAD = 0
def chk(tag, exp, got, tol=0.02):
    global OK, BAD
    try:
        d = abs(float(exp) - float(got))
    except (TypeError, ValueError):
        BAD += 1
        log(f"  [DIFF] {tag}: 期望={exp!r} 实测={got!r}")
        return
    if d <= tol:
        OK += 1
    else:
        BAD += 1
        log(f"  [DIFF] {tag}: 期望={exp!r} 实测={got!r} 差={d:.6g}")

pythoncom.CoInitialize()
xl = None
try:
    xl = win32.DispatchEx("Excel.Application")
    xl.Visible = False
    xl.DisplayAlerts = False
    xl.AutomationSecurity = 1
    xl.AutoRecover.Enabled = False

    # ============ C：镜像维度扫描 ============
    log("[C] 镜像维度脆弱点扫描")
    wt = with_retry(lambda: xl.Workbooks.Open(TPL))
    wsM = wt.Worksheets("D-镜像")
    lo = with_retry(lambda: wsM.ListObjects("镜像表"))
    n = with_retry(lambda: lo.ListRows.Count)
    hdrs = {}
    for i in range(1, with_retry(lambda: lo.ListColumns.Count) + 1):
        hdrs[with_retry(lambda: lo.HeaderRowRange.Cells(1, i).Value)] = i
    def mcol(nm):
        ci = hdrs[nm]
        v = with_retry(lambda c=ci: wsM.Range(wsM.Cells(2, c), wsM.Cells(1 + n, c)).Value)
        return [x[0] if isinstance(x, tuple) else x for x in v]
    wild = set()
    for nm in ["品类", "产品线新", "细分市场", "客户简称", "存货名称"]:
        for v in mcol(nm):
            if isinstance(v, str) and any(ch in v for ch in "*?~"):
                wild.add(f"{nm}:{v[:30]}")
    log(f"  通配符字符维度值: {len(wild)} 个" + ((" | " + "; ".join(sorted(wild)[:8])) if wild else "(无)"))
    pref = collections.Counter()
    Dm = mcol("发货日期")
    CATm = mcol("客户类别全称")
    for j in range(n):
        if Dm[j]:
            pref[(CATm[j] or "?")[:2]] += 1
    tot_dated = sum(pref.values())
    unknown = pref.get("?", 0)
    log(f"  有效日期行类别前缀: {dict((k, v) for k, v in pref.items() if k != '?')}; 未知前缀行={unknown}/{tot_dated}")
    # 客户YTD并列(用镜像算)
    agg = collections.defaultdict(float)
    y_s = dt.datetime(2026, 1, 1)
    Rm = mcol("收入")
    Cm = mcol("客户简称")
    for j in range(n):
        if Dm[j] and y_s <= Dm[j].replace(tzinfo=None) <= dt.datetime(2026, 8, 31, 23, 59, 59):
            agg[Cm[j]] += Rm[j] if isinstance(Rm[j], (int, float)) else 0
    cnt = collections.Counter(round(v, 2) for v in agg.values())
    dup_big = [(k, v) for k, v in cnt.items() if v > 1 and k > 100000]
    log(f"  客户YTD收入并列组(>10万): {len(dup_big)} 组 —— LARGE/MATCH并列风险" + (f" 示例:{dup_big[:3]}" if dup_big else "(无)"))
    wt.Close(SaveChanges=False)

    # ============ D：换月/换源实测 ============
    log("\n[D] 换月/换源实测 (scratch)")
    shutil.copyfile(TPL, SCRATCH)
    wsc = with_retry(lambda: xl.Workbooks.Open(SCRATCH))
    p = wsc.Worksheets("0-参数")
    p.Range("B5").Value = 6
    log("  报表月=6, 计算…")
    with_retry(lambda: xl.Calculate())
    ov = wsc.Worksheets("1-整体概览")
    chk("D1!换月→6月收入", ATT_JUN_REV, ov.Range("B6").Value)
    chk("D1!换月→6月利润", ATT_JUN_PFT, ov.Range("C6").Value)
    chk("D1!换月→6月数量", ATT_JUN_QTY, ov.Range("D6").Value)
    log(f"  6月自检: B6={ov.Range('B6').Value} B5(5月)={ov.Range('B5').Value}")
    log("  换源→刷7月(8.27)…")
    with_retry(lambda: xl.Run("'audit_scratch.xlsm'!刷新镜像", BASE_JUL, True))
    p.Range("B5").Value = 7
    with_retry(lambda: xl.Calculate())
    chk("D2!换源+月=7→7月收入", ATT_JUL_REV, ov.Range("B6").Value)
    chk("D2!7月利润", ATT_JUL_PFT, ov.Range("C6").Value)
    b13 = p.Range("B13").Value
    b14 = p.Range("B14").Value
    log(f"  版本戳: 行数={b13} 最大日期={b14}")
    wsc.Close(SaveChanges=False)
    if os.path.exists(SCRATCH):
        os.remove(SCRATCH)
    log("  scratch 已清理")
    log(f"\n审计C+D: OK={OK} DIFF={BAD}")
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
