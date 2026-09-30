# -*- coding: utf-8 -*-
r"""静态'7月'文本全部参数化：表头/规则文字改为跟随报表月的公式"""
import time
import pythoncom
import pywintypes
import win32com.client as win32

STAGE = r"C:\Users\910373\AppData\Local\Temp\opencode\build\月度分析模板.xlsm"
REPORT = r"C:\Users\910373\AppData\Local\Temp\opencode\build\title_fix.txt"

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

def setf(ws, addr, formula):
    with_retry(lambda: ws.Range(addr).__setattr__("Formula", formula))

pythoncom.CoInitialize()
xl = None
try:
    xl = win32.DispatchEx("Excel.Application")
    xl.Visible = False
    xl.DisplayAlerts = False
    xl.AutomationSecurity = 1
    xl.AutoRecover.Enabled = False
    wb = xl.Workbooks.Open(STAGE)
    if wb.ReadOnly:
        raise RuntimeError("staging locked")

    W = lambda nm: wb.Worksheets(nm)

    # ---- 表头参数化 ----
    ws2 = W("2-产品线")
    setf(ws2, "B3", '=报表月&"月收入"')
    setf(ws2, "C3", '=报表月&"月利润"')
    setf(ws2, "D3", '=报表月&"月毛利率"')
    setf(ws2, "E3", '="去年"&报表月&"月毛利率"')

    ws3 = W("3-客户分类")
    setf(ws3, "B3", '=报表月&"月收入"')
    setf(ws3, "C3", '=报表月&"月利润"')
    setf(ws3, "D3", '=报表月&"月毛利率"')

    ws4 = W("4-前20大客户")
    setf(ws4, "F3", '=报表月&"月收入"')

    ws5 = W("5-应用领域")
    setf(ws5, "F3", '=报表月&"月毛利率"')

    ws6 = W("6-全品类")
    setf(ws6, "B3", '=报表月&"月收入"')
    setf(ws6, "C3", '=报表月&"月利润"')
    setf(ws6, "D3", '=报表月&"月毛利率"')

    ws21 = W("21-限量出货名单")
    setf(ws21, "F4", '=报表月&"月收入(万)"')
    setf(ws21, "G4", '=报表月&"月利润(万)"')
    setf(ws21, "H4", '=报表月&"月毛利率"')

    ws24 = W("24-整改项目清单")
    setf(ws24, "E3", '=报表月&"月利润(万)"')
    for r in range(5, 17):
        with_retry(lambda r=r: ws24.Cells(r, 1).__setattr__("Formula", '=报表月&"月负毛利"'))
        with_retry(lambda r=r: ws24.Cells(r, 7).__setattr__("Formula", f'=报表月&"月亏损"&$E{r}&"万"'))

    ws26 = W("26-成本上升品类")
    setf(ws26, "B4", '=报表月&"月收入(万)"')

    ws27 = W("27-追觅分型号")
    setf(ws27, "F3", '=报表月&"月销量(万颗)"')
    setf(ws27, "G3", '=报表月&"月销售额(万)"')

    # ---- 规则文字参数化 ----
    # 21 建议列: "7月亏损,..." -> 动态
    for r in range(5, 85):
        with_retry(lambda r=r: ws21.Cells(r, 9).__setattr__("Formula",
            f'=IF($A{r}="","",IF($G{r}<0,报表月&"月亏损,优先整改/停售",IF($E{r}<0.15,"限月度出货量,超量提价审批","限期提价")))'))
    # 27 诊断列: "7月归零" -> 动态
    for r in range(5, 30):
        with_retry(lambda r=r: ws27.Cells(r, 8).__setattr__("Formula",
            f'=IF($A{r}="","",IF(INDEX($O$2:$O$6001,MATCH($A{r},$K$2:$K$6001,0))=0,报表月&"月归零","仅存,量减"))'))

    # ---- 10-毛利桥/11 注释中"原7月附件"字样保留(历史说明) ----
    with_retry(lambda: xl.Calculate())
    log("改写完成，抽样验证：")
    for nm, cells in [("2-产品线", ["B3", "E3"]), ("3-客户分类", ["B3"]), ("21-限量出货名单", ["F4"]),
                      ("24-整改项目清单", ["A5", "G5"]), ("27-追觅分型号", ["F3"])]:
        ws = W(nm)
        for c in cells:
            log(f"  {nm}!{c} => {ws.Range(c).Value}")
    # 残留扫描：可见sheet中仍含"7月"的静态单元格（排除手工区和历史说明）
    log("\n残留'7月'扫描（前30项，手工区/说明除外）：")
    cnt = 0
    manual = {"1b-H1任务项", "28-长库龄存货明细", "0-说明"}
    for sh in wb.Worksheets:
        if sh.Name in manual or sh.Name.startswith("C-") or sh.Name in ("D-镜像",):
            continue
        ur = sh.UsedRange
        vals = None
        try:
            vals = with_retry(lambda: sh.Range(sh.Cells(1, 1), sh.Cells(ur.Rows.Count, min(ur.Columns.Count, 30))).Value)
        except Exception:
            continue
        def grid(v):
            if isinstance(v, (str, int, float)):
                return ((v,),)
            if v is None:
                return ()
            if isinstance(v, tuple):
                if len(v) == 0:
                    return ()
                if not isinstance(v[0], tuple):
                    return (v,)
                return v
            return ((v,),)
        for ri, row in enumerate(grid(vals)):
            for ci, v in enumerate(row):
                if isinstance(v, str) and "7月" in v and cnt < 30:
                    cnt += 1
                    log(f"  [{sh.Name}] R{ri+1}C{ci+1}: {v[:50]}")
    log(f"共扫描到 {cnt} 项残留(未截断总数可能更多)")

    wb.Save()
    log("SAVED")
    wb.Close(SaveChanges=False)
finally:
    if xl is not None:
        try:
            xl.Quit()
        except Exception:
            pass
    pythoncom.CoUninitialize()

with open(REPORT, "w", encoding="utf-8") as fh:
    fh.write("\n".join(out))
print("TITLE_FIX_DONE")
