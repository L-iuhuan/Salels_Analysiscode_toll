# -*- coding: utf-8 -*-
"""Phase A: 数据摸底 — 检查 silver 数据与 samples.pkl 的映射关系"""
import os, sys
import pandas as pd
import numpy as np

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
os.chdir(PROJECT_ROOT)

# 1. 读取 samples.pkl
sp = pd.read_pickle('recession_risk_opt/data/samples.pkl')
print("=== samples.pkl ===")
print(f"Shape: {sp.shape}")
print(f"Products: {sp['product_id'].nunique()}")
print(f"Date range: {sp['date_month'].min()} ~ {sp['date_month'].max()}")
print(f"Sample product_ids: {sp['product_id'].unique()[:10].tolist()}")
print(f"Columns: {sp.columns.tolist()}")
print()

# 2. 读取 silver 数据 - 使用 repr 获取真实列名
pm = pd.read_csv('output/silver/silver_product_monthly.csv', encoding='utf-8-sig')
cp = pd.read_csv('output/silver/silver_customer_x_product.csv', encoding='utf-8-sig')

# 获取列名的 Unicode repr
print("=== silver_product_monthly ===")
print(f"Shape: {pm.shape}")
for c in pm.columns:
    print(f"  col: {c}  repr: {repr(c)}")
print()

# 动态访问: 用列名的 repr 重建字符串
pm_cols_py = {}
for c in pm.columns:
    pm_cols_py[eval(repr(c))] = c

print(f"Date min: {pm[pm_cols_py['_月']].min()}")
print(f"Date max: {pm[pm_cols_py['_月']].max()}")

prod_col_pm = [c for c in pm.columns if c not in ('_月', 'qty_sum', 'rev_sum', 'cost_sum', 
                                                   'profit_raw_sum', 'profit_clip_sum', 
                                                   'avg_price', '毛利率%')][0]
print(f"Product column (PM): {repr(prod_col_pm)}")
print(f"Sample products (PM): {pm[prod_col_pm].unique()[:10].tolist()}")
print()

# silver_customer_x_product
print("=== silver_customer_x_product ===")
print(f"Shape: {cp.shape}")
for c in cp.columns:
    print(f"  col: {c}  repr: {repr(c)}")
print()

# Find customer column
known = {'_月', 'qty_sum', 'rev_sum', 'profit_clip_sum', '毛利率%'}
remaining = [c for c in cp.columns if c not in known]
print(f"Remaining columns: {remaining}")
print(f"Shapes: CP={cp.shape}, Samples={sp.shape}")

# Check overlap
sp_prods = set(sp['product_id'].unique())
# Find prod col in CP
for c in remaining:
    vals = cp[c].unique()
    overlap = len(sp_prods & set(vals))
    print(f"  CP column {repr(c)}: overlap with product_id = {overlap}")
