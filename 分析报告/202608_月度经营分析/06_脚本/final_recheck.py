# -*- coding: utf-8 -*-
r"""最终只读复验: 整理后底稿数字池覆盖报告全部数字 + 结构整洁检查(无叠写残留)"""
import re
import time
import pythoncom
import pywintypes
import win32com.client as win32

BK = r"E:\3-其他资料\数据分析\月度分析模板_8月报告副本.xlsx"
TXT = r"C:\Users\910373\AppData\Local\Temp\opencode\build\final_text_v4.txt"

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

sheets = ["1-整体概览", "2-产品线", "2b-新品分档", "3-客户分类", "4-前20大客户", "5-应用领域",
          "8-新品", "9-成本监控", "10-毛利桥", "11-SKU变化", "26-成本上升品类", "增加及流失",
          "R-报告补充", "R6-SKU与客户", "R7-中兴月度", "R8-品类增量", "R9-长周期", "R10-量效应",
          "R11-音频与渗透", "R12-新品与快照"]
pool = set()
NUMS_IN_STR = re.compile(r"-?\d+\.?\d*")
pythoncom.CoInitialize()
xl = None
try:
    xl = with_retry(lambda: win32.DispatchEx("Excel.Application"))
    xl.Visible = False
    xl.DisplayAlerts = False
    wb = with_retry(lambda: xl.Workbooks.Open(BK, ReadOnly=True))

    def add(x):
        try:
            v = float(x)
        except (TypeError, ValueError):
            return
        for f in (1, 100, 1e4, 1e8):
            pool.add(round(v * f, 2))

    for sn in sheets:
        try:
            ws = with_retry(lambda: xl.Worksheets(sn))
            used = with_retry(lambda: ws.UsedRange)
            nr = min(with_retry(lambda: used.Rows.Count), 200)
            nc = min(with_retry(lambda: used.Columns.Count), 14)
            vals = with_retry(lambda: ws.Range(ws.Cells(1, 1), ws.Cells(nr, nc)).Value)
            for row in vals:
                if not isinstance(row, tuple):
                    row = (row,)
                for c in row:
                    if isinstance(c, (int, float)):
                        add(c)
                    elif isinstance(c, str):
                        for m in NUMS_IN_STR.findall(c):
                            add(m)
        except Exception:
            pass
    # 结构检查
    wr = with_retry(lambda: xl.Worksheets("R-报告补充"))
    below = []
    for r in range(60, 200):
        v = with_retry(lambda: wr.Cells(r, 1).Value)
        if v:
            below.append((r, str(v)[:30]))
    r2p = with_retry(lambda: wr.Cells(6, 1).Value)
    r5t = with_retry(lambda: wr.Cells(43, 1).Value)
    r3t = with_retry(lambda: wr.Cells(17, 1).Value)
    r27 = with_retry(lambda: wr.Cells(27, 2).Value)
    r27p = with_retry(lambda: wr.Cells(27, 3).Value)
    with_retry(lambda: wb.Close(False))
finally:
    if xl is not None:
        try:
            xl.Quit()
        except Exception:
            pass
    pythoncom.CoUninitialize()

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

WORDNUM = re.compile(r"[A-Za-z][A-Za-z0-9\-]*\d|\d[A-Za-z]")
NUMRE = re.compile(r"-?\d[\d,]*\.?\d*")

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

SKIP = {str(i) for i in range(0, 21)}
res = []
total_miss = 0
for tn in sorted(tables):
    miss = []
    checked = 0
    for row in tables[tn]:
        clean = WORDNUM.sub(" ", row)
        for tok in NUMRE.findall(clean):
            tok = tok.replace(",", "")
            if tok in ("", "-") or tok in SKIP:
                continue
            checked += 1
            if not in_pool(tok):
                miss.append(tok)
    total_miss += len(miss)
    res.append(f"表{tn}: 检查{checked} -> {'PASS' if not miss else '未匹配:' + ','.join(sorted(set(miss))[:8])}")

out = ["== 报告20表数字池复验(整理后底稿) =="] + res + [f"合计未匹配: {total_miss}",
       "",
       "== 结构整洁检查 ==",
       f"R2指针: {str(r2p)[:40]}",
       f"R3标题(同源注): {str(r3t)[:50]}",
       f"R3真实总计: 收入={r27} 利润={r27p} (应2259.8/-126.2)",
       f"R5标题(同源注): {str(r5t)[:50]}",
       f"60行以下残留: {len(below)}处 {below[:5]} -> {'PASS' if not below else 'FAIL'}"]
open(r"C:\Users\910373\AppData\Local\Temp\opencode\build\final_recheck.txt", "w", encoding="utf-8").write("\n".join(out))
print("FINALRECHECK_DONE")
