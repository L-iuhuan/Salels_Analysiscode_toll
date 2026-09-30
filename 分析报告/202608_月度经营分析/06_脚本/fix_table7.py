# -*- coding: utf-8 -*-
r"""表7修正: Word引言句+3行表格重写 + 底稿R12c数据块"""
import time
import pythoncom
import pywintypes
import win32com.client as win32

DOC = r"E:\3-其他资料\数据分析\2026年8月销售经营分析报告(定稿).docx"
BK = r"E:\3-其他资料\数据分析\月度分析模板_8月报告副本.xlsx"

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
NEW_SENT = ("单个产品中,8月成本环比上升侵蚀最大的是STI3453FI(侵蚀10.9万,单位成本环比+24.2%,当月已转亏;"
            "与STI3452HFI同品类)。STI3452HFI本月单位成本环比已回落(-1.7%),成本效应转为改善(+6.1万),"
            "其-76.1万为负毛利总亏损而非成本侵蚀(数据底表:R-报告补充R12c)。")
NEW_ROWS = [
    ["STI3453FI", "DCDC-18V-降压2-4A", "-10.9", "+24.2%", "51.7"],
    ["TMI6050", "LDO通用/双通道", "-5.0", "+7.3%", "108.3"],
    ["TMI3255S", "DCDC-18V-降压5-12A", "-4.0", "+8.3%", "57.5"],
]

pythoncom.CoInitialize()
word = None
try:
    word = with_retry(lambda: win32.DispatchEx("Word.Application"))
    word.Visible = False
    word.DisplayAlerts = 0
    doc = with_retry(lambda: word.Documents.Open(DOC))
    with_retry(lambda: doc.__setattr__("TrackRevisions", False))

    # 1) 引言句
    rng = with_retry(lambda: doc.Content)
    f = with_retry(lambda: rng.Find)
    with_retry(lambda: f.ClearFormatting)
    with_retry(lambda: f.__setattr__("Text", "单个产品中,成本上升(按利润侵蚀额)最大的是STI3452HFI。"))
    with_retry(lambda: f.__setattr__("Forward", True))
    with_retry(lambda: f.__setattr__("Wrap", 0))
    ok = with_retry(lambda: f.Execute())
    if ok:
        found = with_retry(lambda: f.Parent)
        with_retry(lambda: found.__setattr__("Text", NEW_SENT))
        LOG.append("intro sentence OK")
    else:
        LOG.append("intro sentence MISS")

    # 2) 表7三行
    nt = with_retry(lambda: doc.Tables.Count)
    hit = None
    for ti in range(1, nt + 1):
        tb = with_retry(lambda: doc.Tables(ti))
        c1 = with_retry(lambda: tb.Cell(1, 1).Range.Text).replace("\r", "").replace("\x07", "").strip()
        c2 = with_retry(lambda: tb.Cell(1, 2).Range.Text).replace("\r", "").replace("\x07", "").strip()
        if c1 == "产品" and c2 == "所在品类":
            hit = tb
            break
    if hit:
        for ri, row in enumerate(NEW_ROWS, 2):
            for ci, v in enumerate(row, 1):
                rg = with_retry(lambda: hit.Cell(ri, ci).Range)
                with_retry(lambda: rg.__setattr__("Text", str(v)))
        LOG.append("table7 rows OK")
    else:
        LOG.append("table7 MISS")

    nrev = with_retry(lambda: doc.Revisions.Count)
    for i in range(nrev, 0, -1):
        rv = with_retry(lambda: doc.Revisions(i))
        with_retry(lambda: rv.Accept())
    with_retry(lambda: doc.Save())
    with_retry(lambda: doc.Close(False))
finally:
    if word is not None:
        try:
            word.Quit()
        except Exception:
            pass

# 3) 底稿R12c
xl = None
try:
    xl = with_retry(lambda: win32.DispatchEx("Excel.Application"))
    xl.Visible = False
    xl.DisplayAlerts = False
    wb = with_retry(lambda: xl.Workbooks.Open(BK))
    ws = with_retry(lambda: xl.Worksheets("R12-新品与快照"))
    lr = with_retry(lambda: ws.UsedRange.Rows.Count)
    r = lr + 2

    def sv(rr, c, v):
        rg = with_retry(lambda: ws.Cells(rr, c))
        with_retry(lambda: rg.__setattr__("Value", v))

    sv(r, 1, "R12c 8月成本上升单品TOP(环比口径: 侵蚀=8月量×(7月加权UC−8月加权UC), 源=D-镜像静态计算, 2026-09-10)——表7修正出处")
    r += 1
    for c, h in enumerate(["SKU", "所在品类", "成本侵蚀(万)", "单位成本环比", "8月收入(万)", "8月利润(万)"], 1):
        sv(r, c, h)
    r += 1
    for row in [["STI3453FI", "DCDC-18V-降压2~4A", -10.9, "+24.2%", 51.7, -4.4],
                ["TMI6050", "LDO通用/双通道", -5.0, "+7.3%", 108.3, 34.7],
                ["TMI3255S", "DCDC-18V-降压5~12A", -4.0, "+8.3%", 57.5, 5.1],
                ["TMI5302", "(TOP4)", -3.7, "+10.2%", 41.2, 0.8],
                ["TMI8152CA", "(TOP5)", -3.2, "+21.1%", 16.7, -1.5],
                ["TMI8180I", "(TOP6)", -2.8, "+5.1%", 108.9, 50.4],
                ["STI3454I", "(TOP7)", -2.7, "+9.2%", 39.0, 6.8],
                ["TMI6030-28", "(TOP8)", -2.5, "+10.5%", 39.6, 13.2]]:
        for c, v in enumerate(row, 1):
            sv(r, c, v)
        r += 1
    sv(r, 1, "原表7旧值更正记录: STI3452HFI成本效应实为+6.1万(改善,UC-1.7%),-76.1万为负毛利总亏损非成本侵蚀; TMI7608S旧行为7月残留(8月实值:侵蚀≈0,UC持平,收入48.5万); TMI3252SN旧行为7月残留(8月实值:侵蚀-1.8万即改善,UC-4.7%,收入40.7万)")
    with_retry(lambda: wb.Save())
    with_retry(lambda: wb.Close(False))
    LOG.append("R12c written")
finally:
    if xl is not None:
        try:
            xl.Quit()
        except Exception:
            pass
    pythoncom.CoUninitialize()

open(r"C:\Users\910373\AppData\Local\Temp\opencode\build\fix_t7_log.txt", "w", encoding="utf-8").write("\n".join(LOG))
print("FIX_T7_DONE")
