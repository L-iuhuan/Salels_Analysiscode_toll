# -*- coding: utf-8 -*-
"""M3 根因验证: 读当前 xlsx 的客户信息表, 确认"未知客户"归属行是否存在"""
import sys, time
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import pandas as pd

X = r"E:\3-其他资料\数据分析\sales_analytics_platform\data\财务分析-6月（7.6）.xlsx"

t0 = time.time()
try:
    xl = pd.ExcelFile(X, engine="calamine")
    print(f"[calamine] 打开 {time.time()-t0:.1f}s")
except Exception as e:
    print(f"calamine 不可用({e!r}), 回退 openpyxl")
    xl = pd.ExcelFile(X, engine="openpyxl", read_only=True) if False else pd.ExcelFile(X)
    print(f"[openpyxl] 打开 {time.time()-t0:.1f}s")

print("sheets:", xl.sheet_names)

target = None
for cand in ("客户信息表", "客户信息", "CRM"):
    if cand in xl.sheet_names:
        target = cand; break
if target is None:
    print("!! 无客户信息表 sheet —— 基线归属来源已被整体移除?")
    sys.exit(0)

t0 = time.time()
ci = xl.parse(target)
print(f"读取[{target}] {time.time()-t0:.1f}s shape={ci.shape}")
print("列:", list(ci.columns))

# 找客户标识列
cust_col = next((c for c in ci.columns if "客户" in str(c)), ci.columns[0])
hit = ci[ci[cust_col].astype(str).str.contains("未知", na=False)]
print(f"\n'未知'客户行数: {len(hit)}")
if len(hit):
    print(hit.to_string(max_colwidth=40))

w = ci[ci.apply(lambda r: r.astype(str).str.contains("翁创伟").any(), axis=1)]
print(f"\n含'翁创伟'行数: {len(w)}")
if len(w):
    print(w.head(10).to_string(max_colwidth=40))

# 业务负责人列概况
own = next((c for c in ci.columns if "负责" in str(c) or "业务" in str(c)), None)
print(f"\n业务负责人列: {own!r}", f"非空 {ci[own].notna().sum()}/{len(ci)}" if own else "")
