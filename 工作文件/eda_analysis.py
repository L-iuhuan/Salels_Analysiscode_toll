# -*- coding: utf-8 -*-
"""
智数分析专家团 - 数据科学工程师赛奇（Sage）
Excel总表探索性数据分析（EDA）
"""

import pandas as pd
import numpy as np
from scipy import stats
import warnings
import json

warnings.filterwarnings('ignore')

# ============================================================
# 1. 数据加载
# ============================================================
print("=" * 80)
print("【1】数据加载")
print("=" * 80)

file_path = r"C:/Users/45091/Desktop/工作文件/财务分析-5月（6.3）(1).xlsx"

# 先读取sheet名称
xls = pd.ExcelFile(file_path)
print(f"所有Sheet名称: {xls.sheet_names}")

# 读取总表
df = pd.read_excel(file_path, sheet_name='总表', engine='openpyxl')
print(f"\n数据加载成功！")
print(f"数据维度: {df.shape[0]} 行 × {df.shape[1]} 列")

# ============================================================
# 2. 数据结构
# ============================================================
print("\n" + "=" * 80)
print("【2】数据结构概览")
print("=" * 80)

# 列名
print(f"\n所有列名 ({len(df.columns)} 列):")
for i, col in enumerate(df.columns):
    print(f"  [{i}] {col} (dtype: {df[col].dtype})")

# 前10行
print("\n前10行数据预览:")
pd.set_option('display.max_columns', None)
pd.set_option('display.width', 200)
pd.set_option('display.max_colwidth', 30)
print(df.head(10).to_string())

# 数据类型统计
print("\n数据类型统计:")
dtype_counts = df.dtypes.value_counts()
for dtype, count in dtype_counts.items():
    print(f"  {dtype}: {count} 列")

# ============================================================
# 3. 客户分类字段识别
# ============================================================
print("\n" + "=" * 80)
print("【3】客户分类字段识别")
print("=" * 80)

# 搜索可能包含客户分类的列
keywords_customer = ['客户', '分类', '类型', '等级', 'KA', 'AA', 'MM', 'KM', '级别', '类别', 'type', 'category', 'class', 'level']
customer_cols = []
for col in df.columns:
    col_str = str(col).lower()
    for kw in keywords_customer:
        if kw.lower() in col_str:
            customer_cols.append(col)
            break

print(f"\n可能与客户分类相关的列: {customer_cols}")

# 检查这些列的唯一值
for col in customer_cols:
    unique_vals = df[col].dropna().unique()
    print(f"\n  列 '{col}' 的唯一值 ({len(unique_vals)} 个):")
    if len(unique_vals) <= 30:
        for val in unique_vals:
            count = (df[col] == val).sum()
            print(f"    '{val}': {count} 条 ({count/len(df)*100:.1f}%)")
    else:
        print(f"    前20个: {unique_vals[:20]}")
        # 也检查是否包含KA/AA/MM/KM
        for pattern in ['KA', 'AA', 'MM', 'KM']:
            matches = [v for v in unique_vals if pattern in str(v).upper()]
            if matches:
                print(f"    包含'{pattern}'的值: {matches}")

# 额外搜索：检查所有字符串列中是否包含KA/AA/MM/KM值
print("\n在所有字符串列中搜索KA/AA/MM/KM值:")
for col in df.select_dtypes(include=['object', 'category']).columns:
    unique_vals = df[col].dropna().unique()
    for pattern in ['KA', 'AA', 'MM', 'KM']:
        matches = [v for v in unique_vals if str(v).strip().upper() == pattern or pattern in str(v)]
        if matches and len(matches) <= 5:
            print(f"  列 '{col}' 包含'{pattern}': {matches}")

# ============================================================
# 4. 销售数据字段识别
# ============================================================
print("\n" + "=" * 80)
print("【4】销售数据字段识别")
print("=" * 80)

sales_keywords = ['销售', '金额', '数量', '收入', '营收', '营业', '利润', '成本', '费用', 
                   '增长', '毛利', '净利', '回款', '应收', '订单', '交易', 'sale', 'revenue',
                   'amount', 'price', 'quantity', 'profit', 'cost']
sales_cols = []
for col in df.columns:
    col_str = str(col).lower()
    for kw in sales_keywords:
        if kw in col_str:
            sales_cols.append(col)
            break

print(f"\n与销售相关的列 ({len(sales_cols)} 列):")
for col in sales_cols:
    dtype = df[col].dtype
    non_null = df[col].notna().sum()
    print(f"  '{col}' | 类型: {dtype} | 非空: {non_null} ({non_null/len(df)*100:.1f}%)")
    if df[col].dtype in ['int64', 'float64']:
        print(f"    统计: 均值={df[col].mean():.2f}, 中位数={df[col].median():.2f}, "
              f"最大={df[col].max():.2f}, 最小={df[col].min():.2f}")

# 所有数值列概览
print("\n所有数值列概览:")
numeric_df = df.select_dtypes(include=[np.number])
print(f"数值列数量: {len(numeric_df.columns)}")
for col in numeric_df.columns:
    print(f"  '{col}': mean={numeric_df[col].mean():.4f}, std={numeric_df[col].std():.4f}, "
          f"min={numeric_df[col].min():.4f}, max={numeric_df[col].max():.4f}")

# ============================================================
# 5. 时间维度
# ============================================================
print("\n" + "=" * 80)
print("【5】时间维度分析")
print("=" * 80)

date_keywords = ['日期', '时间', '年', '月', '日', 'date', 'time', 'year', 'month', 'period', '期间']
date_cols = []
for col in df.columns:
    col_str = str(col).lower()
    for kw in date_keywords:
        if kw in col_str:
            date_cols.append(col)
            break

print(f"\n时间相关列: {date_cols}")
for col in date_cols:
    print(f"\n  列 '{col}':")
    print(f"    数据类型: {df[col].dtype}")
    non_null = df[col].dropna()
    if len(non_null) > 0:
        print(f"    非空值: {len(non_null)}")
        unique_vals = non_null.unique()
        print(f"    唯一值数量: {len(unique_vals)}")
        if len(unique_vals) <= 30:
            print(f"    所有值: {sorted(unique_vals)}")
        else:
            # 尝试转为datetime
            try:
                dates = pd.to_datetime(non_null, errors='coerce')
                valid_dates = dates.dropna()
                if len(valid_dates) > 0:
                    print(f"    日期范围: {valid_dates.min()} ~ {valid_dates.max()}")
            except:
                print(f"    前20个值: {unique_vals[:20]}")

# 也检查datetime类型列
datetime_cols = df.select_dtypes(include=['datetime64', 'datetimetz']).columns
if len(datetime_cols) > 0:
    print(f"\nDatetime类型列: {list(datetime_cols)}")
    for col in datetime_cols:
        valid = df[col].dropna()
        if len(valid) > 0:
            print(f"  '{col}': {valid.min()} ~ {valid.max()}, 非空: {len(valid)}")

# ============================================================
# 6. 缺失值分析
# ============================================================
print("\n" + "=" * 80)
print("【6】缺失值分析")
print("=" * 80)

missing = df.isnull().sum()
missing_pct = (missing / len(df) * 100).round(2)
missing_df = pd.DataFrame({'缺失数': missing, '缺失率(%)': missing_pct})
missing_df = missing_df.sort_values('缺失率(%)', ascending=False)

print("\n各字段缺失情况（按缺失率降序）:")
for col_name, row in missing_df.iterrows():
    if row['缺失数'] > 0:
        print(f"  '{col_name}': 缺失 {int(row['缺失数'])} 条 ({row['缺失率(%)']:.2f}%)")

zero_missing = missing_df[missing_df['缺失数'] == 0]
print(f"\n无缺失的字段 ({len(zero_missing)} 个): {list(zero_missing.index)}")

# ============================================================
# 7. 长尾分布特征分析
# ============================================================
print("\n" + "=" * 80)
print("【7】长尾分布特征分析")
print("=" * 80)

# 先确定客户分类列和销售金额列
# 根据前面的分析结果动态识别
print("\n（需要先确认客户分类列和销售金额列）")

# 尝试找到客户名称列
name_keywords = ['客户名称', '客户名', '名称', 'name', '公司', 'company']
name_cols = []
for col in df.columns:
    col_str = str(col).lower()
    for kw in name_keywords:
        if kw in col_str:
            name_cols.append(col)
            break
print(f"\n客户名称相关列: {name_cols}")

# 输出所有列名供后续精确使用
print("\n完整列名列表（JSON格式）:")
print(json.dumps(list(df.columns), ensure_ascii=False, indent=2))

print("\n\n===== 第一阶段分析完成，请检查结果以进行第二阶段深入分析 =====")
