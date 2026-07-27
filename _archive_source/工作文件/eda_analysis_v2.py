# -*- coding: utf-8 -*-
"""
智数分析专家团 - 数据科学工程师赛奇（Sage）
Excel总表探索性数据分析（EDA）- Phase 2
输出到文件以避免编码问题
"""

import pandas as pd
import numpy as np
from scipy import stats
import warnings
import json
import sys
import io

warnings.filterwarnings('ignore')

# 写入UTF-8文件
output_path = r"C:/Users/45091/Desktop/工作文件/eda_results.txt"

with open(output_path, 'w', encoding='utf-8') as f:
    
    file_path = r"C:/Users/45091/Desktop/工作文件/财务分析-5月（6.3）(1).xlsx"
    
    # ============================================================
    # 1. 数据加载
    # ============================================================
    f.write("=" * 80 + "\n")
    f.write("【1】数据加载\n")
    f.write("=" * 80 + "\n")
    
    xls = pd.ExcelFile(file_path)
    f.write(f"所有Sheet名称: {xls.sheet_names}\n")
    
    df = pd.read_excel(file_path, sheet_name='总表', engine='openpyxl')
    f.write(f"数据加载成功！\n")
    f.write(f"数据维度: {df.shape[0]} 行 × {df.shape[1]} 列\n")
    
    # ============================================================
    # 2. 数据结构
    # ============================================================
    f.write("\n" + "=" * 80 + "\n")
    f.write("【2】数据结构概览\n")
    f.write("=" * 80 + "\n")
    
    f.write(f"\n所有列名 ({len(df.columns)} 列):\n")
    for i, col in enumerate(df.columns):
        f.write(f"  [{i}] {col} (dtype: {df[col].dtype})\n")
    
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', 300)
    pd.set_option('display.max_colwidth', 40)
    f.write("\n前5行数据预览:\n")
    f.write(df.head(5).to_string() + "\n")
    
    f.write("\n数据类型统计:\n")
    dtype_counts = df.dtypes.value_counts()
    for dtype, count in dtype_counts.items():
        f.write(f"  {dtype}: {count} 列\n")
    
    # ============================================================
    # 3. 客户分类字段 - 重点！
    # ============================================================
    f.write("\n" + "=" * 80 + "\n")
    f.write("【3】客户分类字段识别 ★关键\n")
    f.write("=" * 80 + "\n")
    
    # 发现 终端客户名称_客户分类 是关键列
    key_class_col = '终端客户名称_客户分类'
    if key_class_col in df.columns:
        f.write(f"\n★★★ 关键列: '{key_class_col}' ★★★\n")
        unique_vals = df[key_class_col].dropna().unique()
        f.write(f"  唯一值: {list(unique_vals)}\n")
        f.write(f"  各类型统计:\n")
        for val in unique_vals:
            count = (df[key_class_col] == val).sum()
            pct = count / len(df) * 100
            f.write(f"    '{val}': {count} 条 ({pct:.2f}%)\n")
        
        # 计算含缺失值的情况
        na_count = df[key_class_col].isna().sum()
        f.write(f"    缺失值: {na_count} 条 ({na_count/len(df)*100:.2f}%)\n")
    
    # 其他可能的分类列
    f.write(f"\n其他可能相关列:\n")
    f.write(f"  '销售部门' 唯一值: {list(df['销售部门'].dropna().unique())}\n")
    f.write(f"  '事业部或直客标识' 唯一值: {list(df['事业部或直客标识'].dropna().unique())}\n")
    
    # ============================================================
    # 4. 销售数据字段
    # ============================================================
    f.write("\n" + "=" * 80 + "\n")
    f.write("【4】销售数据字段\n")
    f.write("=" * 80 + "\n")
    
    sales_cols_detail = [
        '销售数量', '原始含税单价', '销售总金额', '单位成本', '总成本',
        'RMB 未税金额（小）', '毛利', '未税单价', '原始税额'
    ]
    for col in sales_cols_detail:
        if col in df.columns:
            f.write(f"\n  '{col}':\n")
            f.write(f"    类型: {df[col].dtype}\n")
            f.write(f"    非空: {df[col].notna().sum()} ({df[col].notna().sum()/len(df)*100:.1f}%)\n")
            if df[col].dtype in ['int64', 'float64']:
                valid = df[col].dropna()
                f.write(f"    均值: {valid.mean():.4f}\n")
                f.write(f"    中位数: {valid.median():.4f}\n")
                f.write(f"    标准差: {valid.std():.4f}\n")
                f.write(f"    最小值: {valid.min():.4f}\n")
                f.write(f"    最大值: {valid.max():.4f}\n")
                f.write(f"    偏度: {valid.skew():.4f}\n")
                f.write(f"    峰度: {valid.kurt():.4f}\n")
                # 分位数
                for q in [0.1, 0.25, 0.5, 0.75, 0.9, 0.95, 0.99]:
                    f.write(f"    P{int(q*100)}: {valid.quantile(q):.4f}\n")
    
    # ============================================================
    # 5. 时间维度
    # ============================================================
    f.write("\n" + "=" * 80 + "\n")
    f.write("【5】时间维度分析\n")
    f.write("=" * 80 + "\n")
    
    date_col = '交易日期'
    if date_col in df.columns:
        dates = pd.to_datetime(df[date_col], errors='coerce').dropna()
        f.write(f"\n  日期列: '{date_col}'\n")
        f.write(f"  日期范围: {dates.min()} ~ {dates.max()}\n")
        f.write(f"  非空记录: {len(dates)}\n")
        
        # 按年月统计
        df['年月'] = dates.dt.to_period('M')
        monthly = df.groupby('年月').size()
        f.write(f"\n  按月记录数:\n")
        for period, count in monthly.items():
            f.write(f"    {period}: {count} 条\n")
    
    f.write(f"\n  结款期限列: {list(df['结款期限'].dropna().unique())}\n")
    
    # ============================================================
    # 6. 缺失值分析
    # ============================================================
    f.write("\n" + "=" * 80 + "\n")
    f.write("【6】缺失值分析\n")
    f.write("=" * 80 + "\n")
    
    missing = df.isnull().sum()
    missing_pct = (missing / len(df) * 100).round(2)
    missing_df = pd.DataFrame({'缺失数': missing, '缺失率(%)': missing_pct})
    missing_df = missing_df.sort_values('缺失率(%)', ascending=False)
    
    for col_name, row in missing_df.iterrows():
        if row['缺失数'] > 0:
            f.write(f"  '{col_name}': 缺失 {int(row['缺失数'])} 条 ({row['缺失率(%)']:.2f}%)\n")
    
    zero_missing = missing_df[missing_df['缺失数'] == 0]
    f.write(f"\n  无缺失的字段 ({len(zero_missing)} 个): {list(zero_missing.index)}\n")
    
    # ============================================================
    # 7. 长尾分布特征 ★★★ 核心分析
    # ============================================================
    f.write("\n" + "=" * 80 + "\n")
    f.write("【7】长尾分布特征分析 ★★★ 核心\n")
    f.write("=" * 80 + "\n")
    
    # 用关键分类列进行分析
    class_col = '终端客户名称_客户分类'
    # 销售金额列使用 'RMB 未税金额（小）' 或 '销售总金额'
    amount_col = 'RMB 未税金额（小）'
    qty_col = '销售数量'
    profit_col = '毛利'
    
    # 过滤有分类标签的记录
    df_classified = df[df[class_col].notna()].copy()
    f.write(f"\n有客户分类标签的记录: {len(df_classified)} / {len(df)} ({len(df_classified)/len(df)*100:.1f}%)\n")
    
    # 提取客户类型标签（KA/AA/MM/KM）
    df_classified['客户类型'] = df_classified[class_col].str.extract(r'^(KA|AA|MM|KM)', expand=False)
    f.write(f"客户类型提取结果: {list(df_classified['客户类型'].dropna().unique())}\n")
    
    # ---- 7.1 各客户类型的销售额分布 ----
    f.write(f"\n--- 7.1 各客户类型销售金额分布 ({amount_col}) ---\n")
    
    for ctype in ['KA', 'AA', 'MM', 'KM']:
        subset = df_classified[df_classified['客户类型'] == ctype][amount_col].dropna()
        if len(subset) > 0:
            f.write(f"\n  【{ctype}】 记录数: {len(subset)}\n")
            f.write(f"    均值: {subset.mean():.2f}\n")
            f.write(f"    中位数: {subset.median():.2f}\n")
            f.write(f"    标准差: {subset.std():.2f}\n")
            f.write(f"    偏度: {subset.skew():.4f}\n")
            f.write(f"    峰度: {subset.kurt():.4f}\n")
            f.write(f"    最小值: {subset.min():.2f}\n")
            f.write(f"    最大值: {subset.max():.2f}\n")
            f.write(f"    P10: {subset.quantile(0.1):.2f}\n")
            f.write(f"    P25: {subset.quantile(0.25):.2f}\n")
            f.write(f"    P50: {subset.quantile(0.5):.2f}\n")
            f.write(f"    P75: {subset.quantile(0.75):.2f}\n")
            f.write(f"    P90: {subset.quantile(0.9):.2f}\n")
            f.write(f"    P95: {subset.quantile(0.95):.2f}\n")
            f.write(f"    P99: {subset.quantile(0.99):.2f}\n")
            # 正态性检验
            if len(subset) > 5000:
                sample = subset.sample(5000, random_state=42)
            else:
                sample = subset
            stat_sw, p_sw = stats.shapiro(sample)
            f.write(f"    Shapiro-Wilk正态性检验: stat={stat_sw:.6f}, p={p_sw:.6e}\n")
    
    # ---- 7.2 MM/KM客户数量占比 vs 销售额占比 ----
    f.write(f"\n--- 7.2 各客户类型数量占比 vs 销售额占比 ---\n")
    
    # 按客户维度聚合（终端客户名称）
    customer_col = '终端客户名称'
    
    # 先按分类统计记录数
    total_records = len(df_classified)
    total_amount = df_classified[amount_col].sum()
    
    f.write(f"\n  总记录数（有分类）: {total_records}\n")
    f.write(f"  总销售额（有分类）: {total_amount:,.2f}\n\n")
    
    f.write(f"  {'客户类型':<10} {'记录数':>10} {'记录占比':>10} {'销售额':>18} {'销售额占比':>12}\n")
    f.write(f"  {'-'*60}\n")
    for ctype in ['KA', 'AA', 'MM', 'KM']:
        subset = df_classified[df_classified['客户类型'] == ctype]
        rec_count = len(subset)
        rec_pct = rec_count / total_records * 100
        amt = subset[amount_col].sum()
        amt_pct = amt / total_amount * 100
        f.write(f"  {ctype:<10} {rec_count:>10} {rec_pct:>9.2f}% {amt:>18,.2f} {amt_pct:>11.2f}%\n")
    
    # 按独立客户数统计
    f.write(f"\n  按独立客户数统计（'{customer_col}'）:\n")
    for ctype in ['KA', 'AA', 'MM', 'KM']:
        subset = df_classified[df_classified['客户类型'] == ctype]
        unique_customers = subset[customer_col].nunique()
        unique_all = df_classified[customer_col].nunique()
        f.write(f"    {ctype} 独立客户数: {unique_customers} ({unique_customers/unique_all*100:.2f}%)\n")
    
    # ---- 7.3 客户销售金额分布特征 ----
    f.write(f"\n--- 7.3 客户级别销售金额分布特征（长尾/幂律分析）---\n")
    
    # 按客户聚合销售总额
    customer_agg = df_classified.groupby([customer_col, '客户类型']).agg(
        总销售额=(amount_col, 'sum'),
        交易次数=(amount_col, 'count'),
        平均客单价=(amount_col, 'mean'),
        总数量=(qty_col, 'sum')
    ).reset_index()
    
    f.write(f"\n  独立客户总数: {len(customer_agg)}\n")
    
    # 总体分布
    all_amounts = customer_agg['总销售额']
    f.write(f"\n  全部客户销售额分布:\n")
    f.write(f"    均值: {all_amounts.mean():,.2f}\n")
    f.write(f"    中位数: {all_amounts.median():,.2f}\n")
    f.write(f"    标准差: {all_amounts.std():,.2f}\n")
    f.write(f"    偏度: {all_amounts.skew():.4f}\n")
    f.write(f"    峰度: {all_amounts.kurt():.4f}\n")
    f.write(f"    变异系数(CV): {all_amounts.std()/all_amounts.mean():.4f}\n")
    f.write(f"    P10: {all_amounts.quantile(0.1):,.2f}\n")
    f.write(f"    P25: {all_amounts.quantile(0.25):,.2f}\n")
    f.write(f"    P50: {all_amounts.quantile(0.5):,.2f}\n")
    f.write(f"    P75: {all_amounts.quantile(0.75):,.2f}\n")
    f.write(f"    P90: {all_amounts.quantile(0.9):,.2f}\n")
    f.write(f"    P95: {all_amounts.quantile(0.95):,.2f}\n")
    f.write(f"    P99: {all_amounts.quantile(0.99):,.2f}\n")
    
    # Top客户集中度
    sorted_amounts = all_amounts.sort_values(ascending=False)
    total = sorted_amounts.sum()
    top_n_list = [10, 20, 50, 100, 200]
    f.write(f"\n  Top客户集中度:\n")
    for n in top_n_list:
        top_n_sum = sorted_amounts.head(n).sum()
        f.write(f"    Top {n}: {top_n_sum:,.2f} ({top_n_sum/total*100:.2f}%)\n")
    
    # 各客户类型分别的长尾分析
    for ctype in ['KA', 'AA', 'MM', 'KM']:
        subset = customer_agg[customer_agg['客户类型'] == ctype]['总销售额']
        if len(subset) > 0:
            f.write(f"\n  【{ctype}】客户销售额分布 ({len(subset)} 个客户):\n")
            f.write(f"    均值: {subset.mean():,.2f}\n")
            f.write(f"    中位数: {subset.median():,.2f}\n")
            f.write(f"    标准差: {subset.std():,.2f}\n")
            f.write(f"    偏度: {subset.skew():.4f}\n")
            f.write(f"    变异系数(CV): {subset.std()/subset.mean() if subset.mean() != 0 else 'N/A'}\n")
            f.write(f"    P10~P90: {subset.quantile(0.1):,.2f} ~ {subset.quantile(0.9):,.2f}\n")
            f.write(f"    P95: {subset.quantile(0.95):,.2f}\n")
            f.write(f"    P99: {subset.quantile(0.99):,.2f}\n")
            
            # Top集中度
            sorted_sub = subset.sort_values(ascending=False)
            sub_total = sorted_sub.sum()
            f.write(f"    Top 10客户占比: {sorted_sub.head(10).sum()/sub_total*100:.2f}%\n")
            f.write(f"    Top 20客户占比: {sorted_sub.head(20).sum()/sub_total*100:.2f}%\n")
    
    # ---- 7.4 长尾分布判定 ----
    f.write(f"\n--- 7.4 长尾分布统计判定 ---\n")
    
    # 对MM和KM客户进行幂律/对数正态拟合
    for ctype in ['MM', 'KM']:
        subset = customer_agg[customer_agg['客户类型'] == ctype]['总销售额'].dropna()
        subset_pos = subset[subset > 0]
        if len(subset_pos) > 10:
            f.write(f"\n  【{ctype}】正值销售额分布拟合:\n")
            
            # 对数正态拟合
            log_data = np.log(subset_pos)
            mu, sigma = log_data.mean(), log_data.std()
            f.write(f"    对数正态参数: mu={mu:.4f}, sigma={sigma:.4f}\n")
            
            # KS检验（对数正态）
            ks_stat, ks_p = stats.kstest(log_data, 'norm', args=(mu, sigma))
            f.write(f"    KS检验(对数正态): stat={ks_stat:.6f}, p={ks_p:.6e}\n")
            
            # 幂律指数估计（使用极大似然法）
            xmin = subset_pos.min()
            alpha = 1 + len(subset_pos) / np.sum(np.log(subset_pos / xmin))
            f.write(f"    幂律指数估计: alpha={alpha:.4f} (xmin={xmin:.2f})\n")
            
            # Gini系数
            sorted_vals = np.sort(subset_pos.values)
            n = len(sorted_vals)
            gini = (2 * np.sum((np.arange(1, n+1) * sorted_vals)) / (n * np.sum(sorted_vals)) - (n+1)/n)
            f.write(f"    Gini系数: {gini:.4f}\n")
    
    # ============================================================
    # 8. 客户活跃度分析
    # ============================================================
    f.write("\n" + "=" * 80 + "\n")
    f.write("【8】客户活跃度分析（MM/KM重点）\n")
    f.write("=" * 80 + "\n")
    
    # 按客户+类型聚合
    date_col = '交易日期'
    df_classified[date_col] = pd.to_datetime(df_classified[date_col], errors='coerce')
    
    customer_activity = df_classified.groupby([customer_col, '客户类型']).agg(
        交易次数=(amount_col, 'count'),
        首次交易=(date_col, 'min'),
        最近交易=(date_col, 'max'),
        总销售额=(amount_col, 'sum'),
        平均客单价=(amount_col, 'mean'),
        独立月份数=('年月', 'nunique')
    ).reset_index()
    
    customer_activity['活跃天数'] = (customer_activity['最近交易'] - customer_activity['首次交易']).dt.days + 1
    customer_activity['交易频率_次每月'] = customer_activity['交易次数'] / customer_activity['独立月份数'].clip(lower=1)
    
    for ctype in ['KA', 'AA', 'MM', 'KM']:
        subset = customer_activity[customer_activity['客户类型'] == ctype]
        f.write(f"\n--- 【{ctype}】客户活跃度 ({len(subset)} 个客户) ---\n")
        
        f.write(f"  交易次数分布:\n")
        f.write(f"    均值: {subset['交易次数'].mean():.2f}\n")
        f.write(f"    中位数: {subset['交易次数'].median():.2f}\n")
        f.write(f"    P25~P75: {subset['交易次数'].quantile(0.25):.0f} ~ {subset['交易次数'].quantile(0.75):.0f}\n")
        f.write(f"    P90: {subset['交易次数'].quantile(0.9):.0f}\n")
        f.write(f"    P95: {subset['交易次数'].quantile(0.95):.0f}\n")
        
        f.write(f"  交易频率（次/月）:\n")
        f.write(f"    均值: {subset['交易频率_次每月'].mean():.2f}\n")
        f.write(f"    中位数: {subset['交易频率_次每月'].median():.2f}\n")
        
        f.write(f"  活跃天数:\n")
        f.write(f"    均值: {subset['活跃天数'].mean():.1f}\n")
        f.write(f"    中位数: {subset['活跃天数'].median():.1f}\n")
        
        # 最近交易时间分布
        f.write(f"  最近交易时间分布:\n")
        latest = subset['最近交易'].dropna()
        if len(latest) > 0:
            f.write(f"    最早: {latest.min()}\n")
            f.write(f"    最晚: {latest.max()}\n")
            # 按月分布
            latest_month = latest.dt.to_period('M')
            month_dist = latest_month.value_counts().sort_index()
            for period, count in month_dist.items():
                f.write(f"      {period}: {count} 个客户\n")
    
    # ============================================================
    # 9. 补充分析
    # ============================================================
    f.write("\n" + "=" * 80 + "\n")
    f.write("【9】补充分析\n")
    f.write("=" * 80 + "\n")
    
    # 销售部门分布
    f.write(f"\n  销售部门分布:\n")
    dept_counts = df['销售部门'].value_counts()
    for dept, count in dept_counts.items():
        f.write(f"    {dept}: {count} 条 ({count/len(df)*100:.2f}%)\n")
    
    # 事业部或直客标识
    f.write(f"\n  事业部或直客标识:\n")
    biz_counts = df['事业部或直客标识'].value_counts()
    for biz, count in biz_counts.items():
        f.write(f"    {biz}: {count} 条 ({count/len(df)*100:.2f}%)\n")
    
    # 产品类型分布
    f.write(f"\n  产品系列分布 (前20):\n")
    prod_counts = df['产品系列'].value_counts().head(20)
    for prod, count in prod_counts.items():
        f.write(f"    {prod}: {count} 条 ({count/len(df)*100:.2f}%)\n")
    
    # 交易模式
    f.write(f"\n  交易模式分布:\n")
    mode_counts = df['交易模式'].value_counts()
    for mode, count in mode_counts.items():
        f.write(f"    {mode}: {count} 条 ({count/len(df)*100:.2f}%)\n")
    
    # MM/KM客户的产品偏好
    f.write(f"\n  MM/KM客户的产品系列偏好:\n")
    for ctype in ['MM', 'KM']:
        subset = df_classified[df_classified['客户类型'] == ctype]
        prod_prefs = subset['产品系列'].value_counts().head(10)
        f.write(f"    {ctype} Top10产品:\n")
        for prod, count in prod_prefs.items():
            f.write(f"      {prod}: {count} 条\n")
    
    # 保存客户聚合数据供后续使用
    customer_agg.to_csv(r"C:/Users/45091/Desktop/工作文件/customer_agg.csv", index=False, encoding='utf-8-sig')
    customer_activity.to_csv(r"C:/Users/45091/Desktop/工作文件/customer_activity.csv", index=False, encoding='utf-8-sig')
    f.write(f"\n  已保存聚合数据到 customer_agg.csv 和 customer_activity.csv\n")

print(f"分析完成！结果已写入: {output_path}")
