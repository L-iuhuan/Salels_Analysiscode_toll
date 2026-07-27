# -*- coding: utf-8 -*-
"""M3 残留差异解剖: 交叉销售建议 9 格 + 看板 5 变量"""
import json, os, re, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import pandas as pd

PLAT = r"E:\3-其他资料\数据分析\sales_analytics_platform\output\gold"
BASE = r"E:\3-其他资料\数据分析\工作文件\semiconductor_analysis\output\gold"

a = pd.read_csv(os.path.join(PLAT, "交叉销售建议.csv"), dtype=str, encoding="utf-8-sig").fillna("<NA>")
b = pd.read_csv(os.path.join(BASE, "交叉销售建议.csv"), dtype=str, encoding="utf-8-sig").fillna("<NA>")
print("列:", list(a.columns))
key = list(a.columns[:2])
a = a.set_index(key); b = b.set_index(key)
common = a.index.intersection(b.index)
neq = (a.loc[common] != b.loc[common])
for idx in common[neq.any(axis=1)]:
    for c in a.columns:
        if neq.loc[idx, c]:
            print(f"  {idx} | {c}:\n    平台: {a.loc[idx,c][:120]}\n    ②  : {b.loc[idx,c][:120]}")

# 看板变量对比
VAR_RE = re.compile(r"var\s+([A-Z_0-9]+)\s*=\s*(.*);\s*$")
def extract(path):
    vs = {}
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if line.startswith("var "):
                m = VAR_RE.match(line.rstrip("\n"))
                if m: vs[m.group(1)] = m.group(2)
    return vs

pa = extract(r"E:\3-其他资料\数据分析\sales_analytics_platform\dashboard\dashboard_a.html")
ba = extract(r"E:\3-其他资料\数据分析\工作文件\semiconductor_analysis\dashboard\dashboard_a.html")
for v in ["ALL", "D_DEPT_LIST", "E_SEL_MONTHS", "F_PRODUCT_LIST", "PROD_CHANGE"]:
    x, y = pa.get(v, ""), ba.get(v, "")
    print(f"\n== {v}: 平台 {len(x)} 字符, ② {len(y)} 字符")
    try:
        jx, jy = json.loads(x), json.loads(y)
        tx, ty = type(jx).__name__, type(jy).__name__
        lx = len(jx) if hasattr(jx, "__len__") else "-"
        ly = len(jy) if hasattr(jy, "__len__") else "-"
        print(f"   类型 {tx}({lx}) vs {ty}({ly})")
        if isinstance(jx, dict) and isinstance(jy, dict):
            kx, ky = set(jx), set(jy)
            print(f"   键: 共有 {len(kx&ky)}, 仅平台 {sorted(kx-ky)[:6]}, 仅② {sorted(ky-kx)[:6]}")
            dk = [k for k in kx & ky if jx[k] != jy[k]]
            print(f"   值不同键数: {len(dk)}, 示例: {dk[:6]}")
        elif isinstance(jx, list) and isinstance(jy, list):
            nd = sum(1 for i in range(min(len(jx), len(jy))) if jx[i] != jy[i])
            print(f"   位置不同元素数: {nd}/{min(len(jx),len(jy))}")
            for i in range(min(len(jx), len(jy))):
                if jx[i] != jy[i]:
                    print(f"   首个差异[{i}]: 平台={str(jx[i])[:100]} ②={str(jy[i])[:100]}")
                    break
    except Exception as e:
        print(f"   解析失败: {e!r}")
