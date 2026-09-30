# -*- coding: utf-8 -*-
r"""底稿全量审计: 实际读取所有R相关sheet + 跨表一致性/过期内容自动检测"""
import time
import pythoncom
import pywintypes
import win32com.client as win32

BK = r"E:\3-其他资料\数据分析\月度分析模板_8月报告副本.xlsx"
OUT = r"C:\Users\910373\AppData\Local\Temp\opencode\build\audit_full.txt"

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

lines = []
pythoncom.CoInitialize()
xl = None
try:
    xl = with_retry(lambda: win32.DispatchEx("Excel.Application"))
    xl.Visible = False
    xl.DisplayAlerts = False
    wb = with_retry(lambda: xl.Workbooks.Open(BK, ReadOnly=True))

    def dump(name, r1, r2, nc=10):
        try:
            ws = with_retry(lambda: xl.Worksheets(name))
        except Exception as e:
            lines.append(f"### {name}: ERR {e}")
            return {}
        rows = {}
        lines.append(f"\n### {name} (rows {r1}-{r2}) ###")
        for r in range(r1, r2 + 1):
            vals = []
            for c in range(1, nc + 1):
                v = with_retry(lambda: ws.Cells(r, c).Value)
                if v is None:
                    vals.append("")
                elif isinstance(v, float):
                    vals.append(round(v, 4))
                else:
                    vals.append(str(v))
            if any(str(v) != "" for v in vals):
                rows[r] = vals
                lines.append(f"r{r}: " + " | ".join(str(v) for v in vals))
        return rows

    R = dump("R-报告补充", 1, 58, 12)
    R6 = dump("R6-SKU与客户", 1, 70, 12)
    R7 = dump("R7-中兴月度", 1, 30, 6)
    R8 = dump("R8-品类增量", 1, 90, 6)
    R9 = dump("R9-长周期", 1, 40, 10)
    R10 = dump("R10-量效应", 1, 60, 7)
    R11 = dump("R11-音频与渗透", 1, 60, 13)
    R12 = dump("R12-新品与快照", 1, 15, 5)
    SK = dump("11-SKU变化", 1, 10, 10)
    W0 = dump("0-说明", 1, 60, 2)

    # ---- 自动交叉检测 ----
    lines.append("\n===== 交叉检测 =====")

    def g(rows, r, c):
        try:
            return rows[r][c - 1]
        except Exception:
            return None

    # 1) R2(报告补充 rows8-15) vs R9 2026行: 量/结构/价/成本
    r9map = {}
    for r, vals in R9.items():
        m = str(g(R9, r, 1))
        if m.startswith("2026-"):
            r9map[m] = r
    mism = 0
    for i, r in enumerate(range(8, 16)):
        mon = f"2026-{i + 1:02d}"
        r9r = r9map.get(mon)
        if not r9r:
            continue
        for c_off, (c2, c9) in enumerate([(4, 3), (5, 4), (6, 5), (7, 6)]):
            v2, v9 = g(R, r, c2), g(R9, r9r, c9)
            try:
                if abs(float(v2) - float(v9)) > 0.6:
                    lines.append(f"[R2过期?] {mon} col{c2}: R2={v2} vs R9={v9}")
                    mism += 1
            except (TypeError, ValueError):
                pass
    lines.append(f"1) R2 vs R9 2026四因子: mismatch={mism} " + ("-> R2与R9一致(重复维护)" if mism == 0 else "-> R2存在过期值!"))

    # 2) R3 vs R8中兴康讯行(利润26)
    zx8 = {}
    for r, vals in R8.items():
        if g(R8, r, 1) == "中兴康讯":
            cat = str(g(R8, r, 2))
            try:
                zx8[cat] = float(g(R8, r, 3))
            except (TypeError, ValueError):
                pass
    mism = 0
    for r in range(19, 27):
        cat = g(R, r, 1)
        if cat and str(cat) in zx8:
            v3 = g(R, r, 3)
            try:
                if abs(float(v3) - zx8[str(cat)]) > 0.6:
                    lines.append(f"[R3vsR8] {cat}: R3利润={v3} vs R8={zx8[str(cat)]}")
                    mism += 1
            except (TypeError, ValueError):
                pass
    lines.append(f"2) R3 vs R8 中兴康讯利润26: overlap={len(zx8)} mismatch={mism}")

    # 3) R5 vs R6b 利润同比(重叠客户)
    r6b = {}
    for r, vals in R6.items():
        cu = g(R6, r, 1)
        if cu in ("石头", "海康威视", "追觅", "兆驰", "共进", "安克创新", "中兴康讯") and g(R6, r, 2) is not None and g(R6, r, 3) is not None:
            try:
                r6b[str(cu)] = (float(g(R6, r, 3)), float(g(R6, r, 9)))
            except (TypeError, ValueError):
                pass
    r5 = {}
    for r, vals in R.items():
        if 44 <= r <= 58:
            cu = g(R, r, 1)
            try:
                r5[str(cu)] = (float(g(R, r, 2)), float(g(R, r, 3)))
            except (TypeError, ValueError):
                pass
    mism = 0
    for cu, (p26, dp) in r5.items():
        if cu in r6b:
            p6, d6 = r6b[cu]
            if abs(p26 - p6) > 1.1 or abs(dp - d6) > 1.1:
                lines.append(f"[R5vsR6b] {cu}: R5=({p26},{dp}) vs R6b=({p6},{d6})")
                mism += 1
    lines.append(f"3) R5 vs R6b 重叠客户: {len([c for c in r5 if c in r6b])}家 mismatch={mism}")

    # 4) R6a vs 11-SKU变化
    mism = 0
    sk = [(g(SK, r, c)) for r in range(5, 8) for c in range(2, 10)]
    for i, r in enumerate(range(3, 6)):
        for c in range(2, 10):
            v6, v11 = g(R6, r, c), g(SK, 5 + i, c)
            try:
                if abs(float(v6) - float(v11)) > 0.01:
                    lines.append(f"[R6avs11SKU] r{r}c{c}: {v6} vs {v11}")
                    mism += 1
            except (TypeError, ValueError):
                pass
    lines.append(f"4) R6a vs 11-SKU变化: mismatch={mism}")

    # 5) R9 2026-08 vs R1 环比行
    r9_8 = r9map.get("2026-08")
    if r9_8:
        for (c9, c1, nm) in [(3, 2, "量"), (4, 3, "结构"), (5, 4, "价"), (6, 5, "成本")]:
            v9, v1 = g(R9, r9_8, c9), g(R, 4, c1)
            try:
                ok = abs(float(v9) - float(v1)) <= 0.6
                lines.append(f"5) R9(2026-08){nm}={v9} vs R1环比{nm}={v1} -> {'一致' if ok else '不一致!'}")
            except (TypeError, ValueError):
                lines.append(f"5) R9/R1 {nm}: 值异常 {v9}/{v1}")

    # 6) R7 2026-01..08合计 vs R3合计(收入2260/利润-126)
    tot_r, tot_p = 0.0, 0.0
    for r, vals in R7.items():
        m = str(g(R7, r, 1))
        if m.startswith("2026-"):
            try:
                tot_r += float(g(R7, r, 2))
                tot_p += float(g(R7, r, 3))
            except (TypeError, ValueError):
                pass
    lines.append(f"6) R7 2026合计: 收入={round(tot_r, 1)} 利润={round(tot_p, 1)} (应≈2260/-126)")

    # 7) 全簿sheet清单+可见性
    lines.append("7) sheet清单: " + ", ".join(
        f"{with_retry(lambda: xl.Worksheets(i).Name)}(v={with_retry(lambda: xl.Worksheets(i).Visible)})"
        for i in range(1, with_retry(lambda: xl.Worksheets.Count) + 1)))

    with_retry(lambda: wb.Close(False))
finally:
    if xl is not None:
        try:
            xl.Quit()
        except Exception:
            pass
    pythoncom.CoUninitialize()

open(OUT, "w", encoding="utf-8").write("\n".join(str(x) for x in lines))
print("AUDIT_DONE")
