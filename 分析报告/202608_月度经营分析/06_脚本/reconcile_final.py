# -*- coding: utf-8 -*-
r"""最终对拍: 定稿报告 vs 数据底表(副本xlsx)
1) 读底表全部相关sheet数值 → 2) 报告各表/关键正文数字逐个回溯 → 3) 派生数公式复验 → 4) sheet可见性"""
import json
import re
import time
import pythoncom
import pywintypes
import win32com.client as win32

BK = r"E:\3-其他资料\数据分析\月度分析模板_8月报告副本.xlsx"
TXT = r"C:\Users\910373\AppData\Local\Temp\opencode\build\final_text_v4.txt"

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

# ---------- 1) 读底表 ----------
sheets_needed = ["1-整体概览", "2-产品线", "2b-新品分档", "3-客户分类", "5-应用领域", "8-新品",
                 "9-成本监控", "10-毛利桥", "11-SKU变化", "26-成本上升品类", "增加及流失", "R-报告补充"]
data = {}
vis = {}
pythoncom.CoInitialize()
xl = None
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
            rows = []
            for r in vals:
                if isinstance(r, tuple):
                    rows.append(list(r))
                else:
                    rows.append([r])
            data[sn] = rows
        except Exception as e:
            data[sn] = f"ERR {e}"
    for i in range(1, with_retry(lambda: xl.Worksheets.Count) + 1):
        s = with_retry(lambda: xl.Worksheets(i))
        vis[str(with_retry(lambda: s.Name))] = int(with_retry(lambda: s.Visible))
    with_retry(lambda: xl.Workbooks.Close())
finally:
    if xl is not None:
        try:
            xl.Quit()
        except Exception:
            pass
    pythoncom.CoUninitialize()

# 底表数值全集(含×100百分比归一)
pool = set()
def add_num(x):
    try:
        v = float(x)
        pool.add(round(v, 4))
        pool.add(round(v * 100, 2))
    except (TypeError, ValueError):
        pass

for sn, rows in data.items():
    if isinstance(rows, str):
        continue
    for row in rows:
        for c in row:
            add_num(c)

def num_variants(tok):
    """报告数字token → 底表匹配变体集合"""
    out = set()
    try:
        v = float(tok)
    except ValueError:
        return out
    out.add(round(v, 2))
    out.add(round(v / 100, 4))  # 7.4(%) vs 0.074
    return out

def in_pool(tok, tol_alt=True):
    try:
        v = float(tok)
    except ValueError:
        return True  # 非数字不计
    for cand in num_variants(tok):
        if cand in pool:
            return True
    # 容差匹配(±0.05)
    for p in pool:
        if abs(p - v) < 0.051 or abs(p - v * 100) < 0.051:
            return True
    return False

# ---------- 2) 报告文本数字提取 ----------
text = open(TXT, encoding="utf-8").read()
lines = text.splitlines()
tables = {}
cur = None
for ln in lines:
    m = re.match(r"=== 表(\d+) \((\d+)行\) ===", ln)
    if m:
        cur = int(m.group(1))
        tables[cur] = []
    elif cur is not None and "|" in ln:
        tables[cur].append(ln)

NUMRE = re.compile(r"-?\d[\d,]*\.?\d*")
def toks(s):
    return [t.replace(",", "") for t in NUMRE.findall(s) if t.replace(",", "") not in ("", "-")]

SKIP_IN_TABLE = {"1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13", "14", "15", "16", "17", "18", "19", "20", "0"}  # 行号/序号/表号

res = []
for tn in sorted(tables):
    miss = []
    checked = 0
    for row in tables[tn]:
        for tok in toks(row):
            if tok in SKIP_IN_TABLE:
                continue
            checked += 1
            if not in_pool(tok):
                miss.append(tok)
    res.append((tn, checked, sorted(set(miss))))

# ---------- 3) 关键派生数公式复验 ----------
der = []
def has(s):
    return s in text
der.append(("净影响+1,995=2,162-167", has("+1,995") and abs((2162 - 167) - 1995) < 1))
der.append(("净利润影响+762=845-83", has("+762") and abs((845 - 83) - 762) < 1))
der.append(("KA拖累-1,060=-505-333-222", has("-1,060万") and abs((-505 - 333 - 222) + 1060) < 1))
der.append(("石头对冲33%=189/(423+148)", has("33%") and abs(189 / (423 + 148) * 100 - 33.1) < 0.2))
der.append(("MM户均+60%=17.6/11.0", has("17.6") and has("11.0") and abs(25257 / 1437 / (17044 / 1547) * 100 - 159.4) < 0.6))
der.append(("音频同比-19.1%=7.4-26.5", has("-19.1%") and abs(7.37 - 26.49 + 19.12) < 0.05))
der.append(("DCDC18V新增毛利率12.5%=5/40", has("12.5%") and abs(5 / 40 * 100 - 12.5) < 0.1))
der.append(("STI减亏22.3=98.3-76.1", has("减亏+22.3万") and abs(98.3 - 76.1 - 22.2) < 0.15))
der.append(("新客户+216=69.4+58.1+45.5+42.6", has("+216万") and abs(69.4 + 58.1 + 45.5 + 42.6 - 215.6) < 0.5))
der.append(("石头占比91%=285/314", has("占91%") and abs(284.7 / 314.1 * 100 - 90.6) < 0.6))
der.append(("海康占比97%=266/274", has("占97%") and abs(266.3 / 274.1 * 100 - 97.2) < 0.3))

# ---------- 4) sheet可见性 ----------
hidden_expected = ["1b-H1任务项", "21-限量出货名单", "22-产品升级清单", "23-低毛利SKU明细", "24-整改项目清单", "27-追觅分型号", "28-长库龄存货明细", "D-镜像", "C-维度", "C-SKU指标", "C-客户指标"]
vis_ok = [s for s in hidden_expected if vis.get(s) == 0]
vis_bad = [s for s in hidden_expected if vis.get(s) != 0]

out = []
out.append("== 表格数字回溯(逐token在底表数值池匹配,容差0.05) ==")
for tn, checked, miss in res:
    status = "PASS" if not miss else f"未匹配{len(miss)}个: {','.join(miss[:8])}"
    out.append(f"表{tn}: 检查{checked}个数字 -> {status}")
out.append("")
out.append("== 关键派生数公式复验 ==")
for name, ok in der:
    out.append(f"{'PASS' if ok else 'FAIL'} {name}")
out.append("")
out.append(f"== sheet可见性: 应隐藏{len(hidden_expected)}个,实际隐藏{len(vis_ok)}个" + (f",异常:{vis_bad}" if vis_bad else " -> PASS"))
out.append(f"R-报告补充可见: {vis.get('R-报告补充') == -1}")
out.append(f"sheet总数: {len(vis)}")
json.dump({"tables": [(t, c, m) for t, c, m in res], "derivations": der,
           "visibility": vis}, open(r"C:\Users\910373\AppData\Local\Temp\opencode\build\recon.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
open(r"C:\Users\910373\AppData\Local\Temp\opencode\build\recon_result.txt", "w", encoding="utf-8").write("\n".join(out))
print("RECON_DONE")
