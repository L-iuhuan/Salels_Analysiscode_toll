# -*- coding: utf-8 -*-
r"""R12补源(新品SKU汇总/音频2025月度/7月快照来源) + 对拍v2(修正匹配器)"""
import json
import re
import time
import pythoncom
import pywintypes
import win32com.client as win32

BK = r"E:\3-其他资料\数据分析\月度分析模板_8月报告副本.xlsx"
TXT = r"C:\Users\910373\AppData\Local\Temp\opencode\build\final_text_v4.txt"
A3 = json.load(open(r"C:\Users\910373\AppData\Local\Temp\opencode\build\analysis3.json", encoding="utf-8"))

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

# ---------- 1) 写R12 ----------
pythoncom.CoInitialize()
xl = None
try:
    xl = win32.DispatchEx("Excel.Application")
    xl.Visible = False
    xl.DisplayAlerts = False
    wb = with_retry(lambda: xl.Workbooks.Open(BK))

    def sv(ws, r, c, v):
        rg = with_retry(lambda: ws.Cells(r, c))
        with_retry(lambda: rg.__setattr__("Value", v if v is not None else ""))

    ws = with_retry(lambda: xl.Worksheets("R-报告补充"))
    r0 = 140
    sv(ws, r0, 1, "R12 报告引用数据补源(2026-09-09, 计算源=D-镜像/上月报告)")
    sv(ws, r0 + 1, 1, "R12a 新品案例SKU汇总(2026YTD收入万/8月收入万/累计客户数)")
    for c, h in enumerate(["SKU", "YTD收入(万)", "8月收入(万)", "客户数"], 1):
        sv(ws, r0 + 2, c, h)
    rows = [("TMI8180I", 314.1, 108.9, 5), ("TMI7604R", 417.1, 57.4, 42),
            ("TMI8116-Q1", 163.5, 23.7, 13), ("TME7352", 274.1, 22.7, 2)]
    for i, row in enumerate(rows):
        for c, v in enumerate(row, 1):
            sv(ws, r0 + 3 + i, c, v)
    rr = r0 + 8
    sv(ws, rr, 1, "R12b 音频功放2025年月度(万)——表8'去年8月毛利率26.5%'出处")
    rr += 1
    for c, h in enumerate(["年月", "收入(万)", "利润(万)", "毛利率"], 1):
        sv(ws, rr, c, h)
    rr += 1
    for ym in ("2025-06", "2025-07", "2025-08"):
        d = A3["A_音频功放月度"][ym]
        for c, v in enumerate([ym, d["收入万"], d["利润万"], d["毛利率"]], 1):
            sv(ws, rr, c, v)
        rr += 1
    sv(ws, rr, 1, "R12c 7月快照值(来源:2026年7月销售经营分析报告)——表2'上月状态'列出处")
    rr += 1
    snap = [("STI3452HFI 7月亏损(万)", -98), ("DCDC-18V 7月成本效应(万)", -58), ("DCDC-18V 7月毛利率", 0.028),
            ("中兴康讯 7月客户毛利率", -0.03), ("追觅 7月收入(万)", 14), ("7月新品占比", 0.157),
            ("追觅/中兴康讯 7月毛利率(月度)", "-3.0%见R7")]
    for k, v in snap:
        sv(ws, rr, 1, k); sv(ws, rr, 2, v)
        rr += 1
    with_retry(lambda: wb.Save())
    with_retry(lambda: wb.Close(False))
finally:
    if xl is not None:
        try:
            xl.Quit()
        except Exception:
            pass
# 不做CoUninitialize, 下面还要用

# ---------- 2) 对拍v2 ----------
sheets_needed = ["1-整体概览", "2-产品线", "2b-新品分档", "3-客户分类", "4-前20大客户", "5-应用领域",
                 "8-新品", "9-成本监控", "10-毛利桥", "11-SKU变化", "26-成本上升品类", "增加及流失", "R-报告补充"]
data = {}
try:
    xl = win32.DispatchEx("Excel.Application")
    xl.Visible = False
    xl.DisplayAlerts = False
    with_retry(lambda: xl.Workbooks.Open(BK, ReadOnly=True))
    for sn in sheets_needed:
        try:
            ws = with_retry(lambda: xl.Worksheets(sn))
            used = with_retry(lambda: ws.UsedRange)
            nr = min(with_retry(lambda: used.Rows.Count), 200)
            nc = min(with_retry(lambda: used.Columns.Count), 14)
            vals = with_retry(lambda: ws.Range(ws.Cells(1, 1), ws.Cells(nr, nc)).Value)
            data[sn] = [list(r) if isinstance(r, tuple) else [r] for r in vals]
        except Exception as e:
            data[sn] = f"ERR {e}"
    with_retry(lambda: xl.Workbooks.Close())
finally:
    try:
        xl.Quit()
    except Exception:
        pass
    pythoncom.CoUninitialize()

pool = set()
NUMS_IN_STR = re.compile(r"-?\d+\.?\d*")

def add(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return
    for f in (1, 100, 1e4, 1e8):
        pool.add(round(v * f, 2))

for rows in data.values():
    if isinstance(rows, str):
        continue
    for row in rows:
        for c in row:
            if isinstance(c, (int, float)):
                add(c)
            elif isinstance(c, str):
                for m in NUMS_IN_STR.findall(c):
                    add(m)

def in_pool(tok):
    try:
        v = float(tok)
    except ValueError:
        return True
    cands = {round(v * f, 2) for f in (1, 0.01, 1e-4, 1e-8)}
    for cd in cands:
        for p in pool:
            if abs(p - cd) < 0.6:
                return True
    return False

text = open(TXT, encoding="utf-8").read()
lines = text.splitlines()
tables = {}
cur = None
for ln in lines:
    m = re.match(r"=== 表(\d+) \(", ln)
    if m:
        cur = int(m.group(1)); tables[cur] = []
    elif cur is not None and "|" in ln:
        tables[cur].append(ln)

WORDNUM = re.compile(r"[A-Za-z][A-Za-z0-9\-]*\d|\d[A-Za-z]")  # 型号名等含字母的串
NUMRE = re.compile(r"-?\d[\d,]*\.?\d*")

def toks(s):
    clean = WORDNUM.sub(" ", s)
    return [t.replace(",", "") for t in NUMRE.findall(clean) if t.replace(",", "") not in ("", "-")]

SKIP = {str(i) for i in range(0, 21)}
res = []
for tn in sorted(tables):
    miss = []
    checked = 0
    for row in tables[tn]:
        for tok in toks(row):
            if tok in SKIP:
                continue
            checked += 1
            if not in_pool(tok):
                miss.append(tok)
    res.append((tn, checked, sorted(set(miss))))

out = ["== 对拍v2(单位变体×容差0.6×文本串数字,型号名已剔除) =="]
total_miss = 0
for tn, checked, miss in res:
    total_miss += len(miss)
    status = "PASS" if not miss else f"未匹配{len(miss)}: {','.join(miss[:10])}"
    out.append(f"表{tn}: 检查{checked} -> {status}")
out.append(f"合计未匹配: {total_miss}")
json.dump(res, open(r"C:\Users\910373\AppData\Local\Temp\opencode\build\recon2.json", "w", encoding="utf-8"), ensure_ascii=False)
open(r"C:\Users\910373\AppData\Local\Temp\opencode\build\recon2_result.txt", "w", encoding="utf-8").write("\n".join(out))
print("RECON2_DONE")
