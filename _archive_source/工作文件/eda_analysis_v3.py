# -*- coding: utf-8 -*-
"""
智数分析专家团 - 数据科学工程师赛奇（Sage）
Excel总表探索性分析（EDA）- Phase 3
使用正确的列名
"""

import pandas as pd
import numpy as np
from scipy import stats
import warnings
import json

warnings.filterwarnings('ignore')

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
    # 2. 数据结构概览
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
    for dtype, count in df.dtypes.value_counts().items():
        f.write(f"  {dtype}: {count} 列\n")
    
    # ============================================================
    # 3. 客户分类字段 ★★★
    # ============================================================
    f.write("\n" + "=" * 80 + "\n")
    f.write("【3】客户分类字段 ★★★\n")
    f.write("=" * 80 + "\n")
    
    # 关键列: 终端客户名称_客户类别
    class_col = '终端客户名称_客户类别'
    f.write(f"\n★★★ 关键分类列: '{class_col}' ★★★\n")
    unique_vals = df[class_col].dropna().unique()
    f.write(f"  唯一值 ({len(unique_vals)} 个): {list(unique_vals)}\n")
    for val in sorted(unique_vals, key=str):
        count = (df[class_col] == val).sum()
        pct = count / len(df) * 100
        f.write(f"    '{val}': {count:,} 条 ({pct:.2f}%)\n")
    na_count = df[class_col].isna().sum()
    f.write(f"    缺失值: {na_count:,} 条 ({na_count/len(df)*100:.2f}%)\n")
    
    # 销售部门
    f.write(f"\n  '销售部门' 分布:\n")
    for val, count in df['销售部门'].value_counts().items():
        f.write(f"    {val}: {count:,} 条 ({count/len(df)*100:.2f}%)\n")
    
    # 业务类型
    f.write(f"\n  '业务类型' 分布:\n")
    for val, count in df['业务类型'].value_counts().items():
        f.write(f"    {val}: {count:,} 条 ({count/len(df)*100:.2f}%)\n")
    
    # 销售模式
    f.write(f"\n  '销售模式' 分布:\n")
    for val, count in df['销售模式'].value_counts().items():
        f.write(f"    {val}: {count:,} 条 ({count/len(df)*100:.2f}%)\n")
    
    # ============================================================
    # 4. 销售数据字段
    # ============================================================
    f.write("\n" + "=" * 80 + "\n")
    f.write("【4】销售相关数值字段详情\n")
    f.write("=" * 80 + "\n")
    
    sales_cols = ['发货数量', '原币含税单价', '出货总金额', '单位成本', '总成本',
                  'RMB 未税金额小计', '利润', '汇率', '未税单价', '原币税额']
    for col in sales_cols:
        if col in df.columns:
            valid = df[col].dropna()
            f.write(f"\n  '{col}' (非空: {len(valid):,}, {len(valid)/len(df)*100:.1f}%):\n")
            if len(valid) > 0 and valid.dtype in ['int64', 'float64']:
                f.write(f"    均值={valid.mean():,.4f}  中位数={valid.median():,.4f}  "
                        f"标准差={valid.std():,.4f}\n")
                f.write(f"    最小值={valid.min():,.4f}  最大值={valid.max():,.4f}\n")
                f.write(f"    偏度={valid.skew():.4f}  峰度={valid.kurt():.4f}\n")
                f.write(f"    P10={valid.quantile(0.1):,.4f}  P25={valid.quantile(0.25):,.4f}  "
                        f"P50={valid.quantile(0.5):,.4f}  P75={valid.quantile(0.75):,.4f}  "
                        f"P90={valid.quantile(0.9):,.4f}  P95={valid.quantile(0.95):,.4f}  "
                        f"P99={valid.quantile(0.99):,.4f}\n")
                # 负值数量
                neg_count = (valid < 0).sum()
                if neg_count > 0:
                    f.write(f"    ⚠ 负值: {neg_count:,} 条 ({neg_count/len(valid)*100:.2f}%) - 可能是退货\n")
    
    # ============================================================
    # 5. 时间维度
    # ============================================================
    f.write("\n" + "=" * 80 + "\n")
    f.write("【5】时间维度分析\n")
    f.write("=" * 80 + "\n")
    
    df['发货日期_dt'] = pd.to_datetime(df['发货日期'], errors='coerce')
    valid_dates = df['发货日期_dt'].dropna()
    f.write(f"\n  '发货日期' 范围: {valid_dates.min()} ~ {valid_dates.max()}\n")
    f.write(f"  非空记录: {len(valid_dates):,}\n")
    
    df['年月'] = df['发货日期_dt'].dt.to_period('M')
    monthly = df.groupby('年月').size()
    f.write(f"\n  按月记录数:\n")
    for period, count in monthly.items():
        f.write(f"    {period}: {count:,} 条\n")
    
    f.write(f"\n  '月结条件' 分布:\n")
    for val, count in df['月结条件'].value_counts().items():
        f.write(f"    {val}: {count:,} 条 ({count/len(df)*100:.2f}%)\n")
    
    # ============================================================
    # 6. 缺失值分析
    # ============================================================
    f.write("\n" + "=" * 80 + "\n")
    f.write("【6】缺失值分析\n")
    f.write("=" * 80 + "\n")
    
    missing = df.isnull().sum()
    missing_pct = (missing / len(df) * 100).round(2)
    missing_df = pd.DataFrame({'缺失数': missing, '缺失率': missing_pct})
    missing_df = missing_df.sort_values('缺失率', ascending=False)
    
    for col_name, row in missing_df.iterrows():
        if row['缺失数'] > 0:
            f.write(f"  '{col_name}': {int(row['缺失数']):,} 条 ({row['缺失率']:.2f}%)\n")
    
    zero_missing = missing_df[missing_df['缺失数'] == 0]
    f.write(f"\n  无缺失的字段 ({len(zero_missing)} 个): {list(zero_missing.index)}\n")
    
    # ============================================================
    # 7. 长尾分布特征 ★★★ 核心
    # ============================================================
    f.write("\n" + "=" * 80 + "\n")
    f.write("【7】长尾分布特征分析 ★★★ 核心分析\n")
    f.write("=" * 80 + "\n")
    
    amount_col = 'RMB 未税金额小计'
    qty_col = '发货数量'
    profit_col = '利润'
    customer_col = '终端客户名称'
    
    # 提取客户类型标签
    df_classified = df[df[class_col].notna()].copy()
    df_classified['客户类型'] = df_classified[class_col].str.extract(r'^(KA|AA|MM|KM)', expand=False)
    f.write(f"\n有分类标签记录: {len(df_classified):,} / {len(df):,} ({len(df_classified)/len(df)*100:.1f}%)\n")
    f.write(f"提取到的客户类型: {sorted(df_classified['客户类型'].dropna().unique())}\n")
    
    # ---- 7.1 各客户类型的单笔交易销售额分布 ----
    f.write(f"\n--- 7.1 各客户类型单笔交易金额分布 ({amount_col}) ---\n")
    
    for ctype in ['KA', 'AA', 'MM', 'KM']:
        subset = df_classified[df_classified['客户类型'] == ctype][amount_col].dropna()
        if len(subset) > 0:
            f.write(f"\n  【{ctype}】 交易笔数: {len(subset):,}\n")
            f.write(f"    均值: {subset.mean():,.2f}\n")
            f.write(f"    中位数: {subset.median():,.2f}\n")
            f.write(f"    标准差: {subset.std():,.2f}\n")
            f.write(f"    偏度: {subset.skew():.4f}\n")
            f.write(f"    峰度: {subset.kurt():.4f}\n")
            f.write(f"    范围: [{subset.min():,.2f}, {subset.max():,.2f}]\n")
            f.write(f"    P10={subset.quantile(0.1):,.2f}  P25={subset.quantile(0.25):,.2f}  "
                    f"P50={subset.quantile(0.5):,.2f}  P75={subset.quantile(0.75):,.2f}\n")
            f.write(f"    P90={subset.quantile(0.9):,.2f}  P95={subset.quantile(0.95):,.2f}  "
                    f"P99={subset.quantile(0.99):,.2f}\n")
    
    # ---- 7.2 各客户类型数量占比 vs 销售额占比 ----
    f.write(f"\n--- 7.2 各客户类型 数量占比 vs 销售额占比 ---\n")
    
    total_records = len(df_classified)
    total_amount = df_classified[amount_col].sum()
    
    f.write(f"\n  总记录数（有分类）: {total_records:,}\n")
    f.write(f"  总销售额（有分类）: {total_amount:,.2f}\n\n")
    
    f.write(f"  {'类型':<8} {'记录数':>10} {'记录占比':>10} {'销售额(RMB)':>20} {'销售额占比':>12}\n")
    f.write(f"  {'-'*65}\n")
    for ctype in ['KA', 'AA', 'MM', 'KM']:
        subset = df_classified[df_classified['客户类型'] == ctype]
        rec_count = len(subset)
        rec_pct = rec_count / total_records * 100
        amt = subset[amount_col].sum()
        amt_pct = amt / total_amount * 100 if total_amount != 0 else 0
        f.write(f"  {ctype:<8} {rec_count:>10,} {rec_pct:>9.2f}% {amt:>20,.2f} {amt_pct:>11.2f}%\n")
    
    # 独立客户数
    f.write(f"\n  按独立客户数统计:\n")
    total_customers = df_classified[customer_col].nunique()
    for ctype in ['KA', 'AA', 'MM', 'KM']:
        unique_c = df_classified[df_classified['客户类型'] == ctype][customer_col].nunique()
        f.write(f"    {ctype}: {unique_c} 个独立客户 ({unique_c/total_customers*100:.2f}%)\n")
    
    # ---- 7.3 客户级别聚合分析 ----
    f.write(f"\n--- 7.3 客户级别销售分布（长尾/幂律分析）---\n")
    
    customer_agg = df_classified.groupby([customer_col, '客户类型']).agg(
        总销售额=(amount_col, 'sum'),
        交易次数=(amount_col, 'count'),
        平均客单价=(amount_col, 'mean'),
        总利润=(profit_col, 'sum'),
        总数量=(qty_col, 'sum')
    ).reset_index()
    
    f.write(f"\n  独立客户总数（有分类）: {len(customer_agg):,}\n")
    
    # 总体分布
    all_amounts = customer_agg['总销售额']
    f.write(f"\n  全部客户总销售额分布:\n")
    f.write(f"    均值: {all_amounts.mean():,.2f}\n")
    f.write(f"    中位数: {all_amounts.median():,.2f}\n")
    f.write(f"    标准差: {all_amounts.std():,.2f}\n")
    f.write(f"    偏度: {all_amounts.skew():.4f}\n")
    f.write(f"    峰度: {all_amounts.kurt():.4f}\n")
    f.write(f"    变异系数(CV): {all_amounts.std()/all_amounts.mean():.4f}\n")
    for q, label in [(0.1,'P10'),(0.25,'P25'),(0.5,'P50'),(0.75,'P75'),(0.9,'P90'),(0.95,'P95'),(0.99,'P99')]:
        f.write(f"    {label}: {all_amounts.quantile(q):,.2f}\n")
    
    # Top集中度
    sorted_amounts = all_amounts.sort_values(ascending=False)
    total = sorted_amounts.sum()
    f.write(f"\n  Top客户集中度:\n")
    for n in [5, 10, 20, 50, 100, 200, 500]:
        top_sum = sorted_amounts.head(n).sum()
        f.write(f"    Top {n}: {top_sum:,.2f} ({top_sum/total*100:.2f}%)\n")
    
    # 各客户类型的长尾分析
    for ctype in ['KA', 'AA', 'MM', 'KM']:
        subset = customer_agg[customer_agg['客户类型'] == ctype]['总销售额']
        if len(subset) > 0:
            f.write(f"\n  【{ctype}】客户销售额分布 ({len(subset):,} 个客户):\n")
            f.write(f"    均值: {subset.mean():,.2f}\n")
            f.write(f"    中位数: {subset.median():,.2f}\n")
            f.write(f"    标准差: {subset.std():,.2f}\n")
            f.write(f"    偏度: {subset.skew():.4f}\n")
            cv = subset.std()/subset.mean() if subset.mean() != 0 else float('nan')
            f.write(f"    变异系数(CV): {cv:.4f}\n")
            f.write(f"    P10={subset.quantile(0.1):,.2f}  P90={subset.quantile(0.9):,.2f}\n")
            f.write(f"    P95={subset.quantile(0.95):,.2f}  P99={subset.quantile(0.99):,.2f}\n")
            
            sorted_sub = subset.sort_values(ascending=False)
            sub_total = sorted_sub.sum()
            if sub_total > 0:
                for n in [5, 10, 20, 50]:
                    if len(sorted_sub) >= n:
                        f.write(f"    Top {n}客户占比: {sorted_sub.head(n).sum()/sub_total*100:.2f}%\n")
    
    # ---- 7.4 长尾分布统计判定 ----
    f.write(f"\n--- 7.4 长尾分布统计判定 ---\n")
    
    for ctype in ['KA', 'AA', 'MM', 'KM']:
        subset = customer_agg[customer_agg['客户类型'] == ctype]['总销售额'].dropna()
        subset_pos = subset[subset > 0]
        if len(subset_pos) > 10:
            f.write(f"\n  【{ctype}】正值销售额分布拟合 ({len(subset_pos)} 个客户):\n")
            
            # 对数正态拟合
            log_data = np.log(subset_pos)
            mu, sigma = log_data.mean(), log_data.std()
            f.write(f"    对数正态参数: mu={mu:.4f}, sigma={sigma:.4f}\n")
            
            # KS检验
            ks_stat, ks_p = stats.kstest(log_data, 'norm', args=(mu, sigma))
            f.write(f"    KS检验(对数正态): D={ks_stat:.6f}, p={ks_p:.6e}\n")
            if ks_p < 0.05:
                f.write(f"    → 拒绝正态假设 (p<0.05)，分布显著偏离对数正态\n")
            else:
                f.write(f"    → 不拒绝正态假设 (p≥0.05)，可近似对数正态\n")
            
            # 幂律指数估计
            xmin = subset_pos.min()
            if xmin > 0:
                alpha = 1 + len(subset_pos) / np.sum(np.log(subset_pos / xmin))
                f.write(f"    幂律指数估计: alpha={alpha:.4f} (xmin={xmin:,.2f})\n")
            
            # Gini系数
            sorted_vals = np.sort(subset_pos.values)
            n = len(sorted_vals)
            gini = (2 * np.sum((np.arange(1, n+1) * sorted_vals)) / (n * np.sum(sorted_vals)) - (n+1)/n)
            f.write(f"    Gini系数: {gini:.4f} (>0.6 高度不均衡)\n")
            
            # 20/80法则
            sorted_sub = subset_pos.sort_values(ascending=False)
            sub_total = sorted_sub.sum()
            n_20pct = max(1, int(len(sorted_sub) * 0.2))
            top_20pct_sum = sorted_sub.head(n_20pct).sum()
            f.write(f"    20/80法则: Top {n_20pct}({n_20pct/len(sorted_sub)*100:.0f}%)客户占销售额 {top_20pct_sum/sub_total*100:.1f}%\n")
    
    # ============================================================
    # 8. 客户活跃度分析
    # ============================================================
    f.write("\n" + "=" * 80 + "\n")
    f.write("【8】客户活跃度分析（MM/KM重点）\n")
    f.write("=" * 80 + "\n")
    
    customer_activity = df_classified.groupby([customer_col, '客户类型']).agg(
        交易次数=(amount_col, 'count'),
        首次发货=('发货日期_dt', 'min'),
        最近发货=('发货日期_dt', 'max'),
        总销售额=(amount_col, 'sum'),
        平均客单价=(amount_col, 'mean'),
        独立月份数=('年月', 'nunique')
    ).reset_index()
    
    customer_activity['活跃天数'] = (customer_activity['最近发货'] - customer_activity['首次发货']).dt.days + 1
    customer_activity['交易频率_次每月'] = customer_activity['交易次数'] / customer_activity['独立月份数'].clip(lower=1)
    
    for ctype in ['KA', 'AA', 'MM', 'KM']:
        subset = customer_activity[customer_activity['客户类型'] == ctype]
        f.write(f"\n--- 【{ctype}】客户活跃度 ({len(subset):,} 个客户) ---\n")
        
        f.write(f"  交易次数: 均值={subset['交易次数'].mean():.2f}  "
                f"中位数={subset['交易次数'].median():.0f}  "
                f"P75={subset['交易次数'].quantile(0.75):.0f}  "
                f"P90={subset['交易次数'].quantile(0.9):.0f}  "
                f"P95={subset['交易次数'].quantile(0.95):.0f}  "
                f"最大={subset['交易次数'].max()}\n")
        
        f.write(f"  交易频率(次/月): 均值={subset['交易频率_次每月'].mean():.2f}  "
                f"中位数={subset['交易频率_次每月'].median():.2f}\n")
        
        f.write(f"  活跃天数: 均值={subset['活跃天数'].mean():.1f}  "
                f"中位数={subset['活跃天数'].median():.0f}\n")
        
        # 单次交易客户占比
        single = (subset['交易次数'] == 1).sum()
        f.write(f"  仅1次交易客户: {single:,} ({single/len(subset)*100:.1f}%)\n")
        
        # 最近发货时间分布
        latest = subset['最近发货'].dropna()
        if len(latest) > 0:
            f.write(f"  最近发货时间范围: {latest.min()} ~ {latest.max()}\n")
            latest_month = latest.dt.to_period('M')
            month_dist = latest_month.value_counts().sort_index()
            f.write(f"  最近发货月份分布:\n")
            for period, count in month_dist.items():
                f.write(f"    {period}: {count} 个客户 ({count/len(subset)*100:.1f}%)\n")
    
    # ============================================================
    # 9. MM/KM客户深度特征
    # ============================================================
    f.write("\n" + "=" * 80 + "\n")
    f.write("【9】MM/KM客户深度特征分析\n")
    f.write("=" * 80 + "\n")
    
    # MM/KM的产品偏好
    for ctype in ['MM', 'KM']:
        subset = df_classified[df_classified['客户类型'] == ctype]
        f.write(f"\n  【{ctype}】Top 15 产品系列:\n")
        prod_prefs = subset['产品系列'].value_counts().head(15)
        for prod, count in prod_prefs.items():
            f.write(f"    {prod}: {count:,} 条 ({count/len(subset)*100:.1f}%)\n")
    
    # MM/KM的产品线偏好
    for ctype in ['MM', 'KM']:
        subset = df_classified[df_classified['客户类型'] == ctype]
        f.write(f"\n  【{ctype}】Top 15 产品线:\n")
        prod_prefs = subset['产品线'].value_counts().head(15)
        for prod, count in prod_prefs.items():
            f.write(f"    {prod}: {count:,} 条 ({count/len(subset)*100:.1f}%)\n")
    
    # MM/KM的细分市场
    for ctype in ['MM', 'KM']:
        subset = df_classified[df_classified['客户类型'] == ctype]
        f.write(f"\n  【{ctype}】细分市场分布:\n")
        seg = subset['细分市场'].value_counts().head(10)
        for s, count in seg.items():
            f.write(f"    {s}: {count:,} 条 ({count/len(subset)*100:.1f}%)\n")
    
    # 利润率分析
    f.write(f"\n  各客户类型利润率分析:\n")
    for ctype in ['KA', 'AA', 'MM', 'KM']:
        subset = df_classified[df_classified['客户类型'] == ctype].copy()
        valid = subset[(subset[amount_col] > 0)].copy()
        if len(valid) > 0:
            valid['利润率'] = valid[profit_col] / valid[amount_col]
            # 去除极端值
            valid['利润率_clipped'] = valid['利润率'].clip(-1, 2)
            f.write(f"    {ctype}: 平均利润率={valid['利润率_clipped'].mean()*100:.2f}%  "
                    f"中位数={valid['利润率_clipped'].median()*100:.2f}%  "
                    f"(基于{len(valid):,}条正金额记录)\n")
    
    # ============================================================
    # 10. 数据总结
    # ============================================================
    f.write("\n" + "=" * 80 + "\n")
    f.write("【10】数据总结与关键洞察\n")
    f.write("=" * 80 + "\n")
    
    f.write(f"""
数据概要:
  - 数据规模: {df.shape[0]:,} 行 × {df.shape[1]} 列
  - 时间跨度: {valid_dates.min().strftime('%Y-%m-%d')} ~ {valid_dates.max().strftime('%Y-%m-%d')}
  - 独立终端客户数: {df[customer_col].nunique():,}
  - 有分类标签记录: {len(df_classified):,} ({len(df_classified)/len(df)*100:.1f}%)
  
关键发现:
  1. 客户分类字段为'终端客户名称_客户类别'，包含 KA>1万/AA>5000万/MM<1000万/KM>1000万 四类
  2. MM客户（<1000万）数量最多，是典型的长尾客户群
  3. 数据存在退货（负金额记录），需要关注
  4. 部分字段缺失率较高（如关联订单明细、是否新品、细分市场（新）等）
""")
    
    # 保存聚合数据
    customer_agg.to_csv(r"C:/Users/45091/Desktop/工作文件/customer_agg.csv", index=False, encoding='utf-8-sig')
    customer_activity.to_csv(r"C:/Users/45091/Desktop/工作文件/customer_activity.csv", index=False, encoding='utf-8-sig')
    f.write("已保存聚合数据:\n")
    f.write("  - customer_agg.csv (客户级别销售聚合)\n")
    f.write("  - customer_activity.csv (客户活跃度聚合)\n")

print(f"分析完成！结果已写入: {output_path}")
