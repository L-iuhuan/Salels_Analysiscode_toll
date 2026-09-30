# -*- coding: utf-8 -*-
r"""8月数据摘要：报告差异清单用（读网络模板，只读）"""
import time
import pythoncom
import pywintypes
import win32com.client as win32

TPL = r"\\192.168.8.3\财务部\财务电子档案备份\D1经营分析\分析报告\分析报告-202608\月度分析模板.xlsm"
OUT = r"C:\Users\910373\AppData\Local\Temp\opencode\build\aug_digest.txt"

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

lines = []
def log(s):
    lines.append(str(s))

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
    def block(sh, a1, a2):
        v = with_retry(lambda: wb.Worksheets(sh).Range(a1 + ":" + a2).Value)
        return v

    log("== 1-整体概览 A4:K8 ==")
    v = block("1-整体概览", "A4", "K8")
    for row in v:
        log(" | ".join("" if c is None else (f"{c:,.4g}" if isinstance(c, float) else str(c))[:16] for c in row))
    log("\n== 3-客户分类 A4:I7 ==")
    for row in block("3-客户分类", "A4", "I7"):
        log(" | ".join("" if c is None else (f"{c:,.6g}" if isinstance(c, float) else str(c))[:14] for c in row))
    log("\n== 2-产品线 A4:F22 (8月) ==")
    for row in block("2-产品线", "A4", "F22"):
        log(" | ".join("" if c is None else (f"{c:,.6g}" if isinstance(c, float) else str(c))[:18] for c in row))
    log("\n== 5-应用领域 A4:J10 ==")
    for row in block("5-应用领域", "A4", "J10"):
        log(" | ".join("" if c is None else (f"{c:,.6g}" if isinstance(c, float) else str(c))[:16] for c in row))
    log("\n== 4-前20大客户 前10 ==")
    for row in block("4-前20大客户", "A4", "I13"):
        log(" | ".join("" if c is None else (f"{c:,.6g}" if isinstance(c, float) else str(c))[:16] for c in row))
    log("\n== 7-追觅 A4:E6 + A10:D17 ==")
    for row in block("7-追觅", "A4", "E6"):
        log(" | ".join("" if c is None else (f"{c:,.6g}" if isinstance(c, float) else str(c))[:16] for c in row))
    for row in block("7-追觅", "A10", "D17"):
        log(" | ".join("" if c is None else (f"{c:,.6g}" if isinstance(c, float) else str(c))[:16] for c in row))
    log("\n== 8-新品 A4:G5 ==")
    for row in block("8-新品", "A4", "G5"):
        log(" | ".join("" if c is None else (f"{c:,.6g}" if isinstance(c, float) else str(c))[:16] for c in row))
    log("\n== 10-毛利桥 A5:F6 ==")
    for row in block("10-毛利桥", "A5", "F6"):
        log(" | ".join("" if c is None else str(c)[:60] for c in row))
    log("\n== 9-成本监控 A11:H12 (8月STI3452HFI) ==")
    for row in block("9-成本监控", "A11", "H12"):
        log(" | ".join("" if c is None else (f"{c:,.6g}" if isinstance(c, float) else str(c))[:16] for c in row))
    log("\n== 26-成本上升 A5:C10 ==")
    for row in block("26-成本上升品类", "A5", "C10"):
        log(" | ".join("" if c is None else (f"{c:,.6g}" if isinstance(c, float) else str(c))[:22] for c in row))
    log("\n== 11-SKU变化 A5:I7 ==")
    for row in block("11-SKU变化", "A5", "I7"):
        log(" | ".join("" if c is None else (f"{c:,.6g}" if isinstance(c, float) else str(c))[:14] for c in row))
    log("\n== 2b-新品分档 A4:F9 ==")
    for row in block("2b-新品分档", "A4", "F9"):
        log(" | ".join("" if c is None else (f"{c:,.6g}" if isinstance(c, float) else str(c))[:14] for c in row))
    log("\n== 0-参数 版本戳 ==")
    log(f"源={tv('0-参数','B12')} 行数={tv('0-参数','B13')} 最大日期={tv('0-参数','B14')}")
    wb.Close(SaveChanges=False)
finally:
    if xl is not None:
        try:
            xl.Quit()
        except Exception:
            pass
    pythoncom.CoUninitialize()

with open(OUT, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
print("DIGEST_DONE")
