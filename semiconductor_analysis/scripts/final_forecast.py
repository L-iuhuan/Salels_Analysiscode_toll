# -*- coding: utf-8 -*-
"""
产品线季度销量/收入/利润预测 — 最终版
========================================
数据源: silver_cleaned_rows.csv
方法: 每条产品线独立选择最优方法（基于回测效果）
预测: 未来4个季度（销量 → 收入 → 利润）
输出: Excel报告
"""

import warnings
warnings.filterwarnings('ignore')

import pandas as pd
import numpy as np
import os, sys
from datetime import datetime
from copy import deepcopy

# ============================================================
# 滚动季度划分工具：以最新数据月份为锚点，每3个月为一桶
# ============================================================
LATEST_YEAR = 2026
LATEST_MONTH = 5  # 最新数据月份（2026-05）

def _rolling_qtr_start_ep(dt):
    """返回该日期所属滚动季度的起始月份epoch值（year*12+month）"""
    ep = dt.year * 12 + dt.month
    latest_ep = LATEST_YEAR * 12 + LATEST_MONTH
    qid = (latest_ep - ep) // 3  # 0=最新季度, 1=上一季度, ...
    return latest_ep - qid * 3 - 2  # 该季度的起始月份

def _format_qtr_label(start_ep):
    """从起始月份epoch值生成季度标签 'YYYY-MM~YYYY-MM'"""
    end_ep = start_ep + 2
    sy, sm = (start_ep - 1) // 12, (start_ep - 1) % 12 + 1
    ey, em = (end_ep - 1) // 12, (end_ep - 1) % 12 + 1
    return f"{sy}-{sm:02d}~{ey}-{em:02d}"

def next_rolling_quarters(last_qtr_start_ep, n=4):
    """计算未来n个滚动季度的标签"""
    return [_format_qtr_label(last_qtr_start_ep + 3 * i) for i in range(1, n + 1)]

# ============================================================
# 0. 配置
# ============================================================
SILVER_PATH = r'E:\3-其他资料\数据分析\semiconductor_analysis\output\silver\silver_cleaned_rows.csv'
OUTPUT_DIR  = r'E:\3-其他资料\数据分析\semiconductor_analysis\output\report'
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 列索引
COL_DATE  = 0   # 发货日期
COL_QTY   = 10  # 数量
COL_PRICE = 11  # 原币含税单价
COL_PLINE = 24  # 型号_产品线（新）
COL_MARGIN = 67 # _毛利率

# ============================================================
# 1. 加载数据
# ============================================================
print("=" * 60)
print("加载数据...")
print("=" * 60)

df = pd.read_csv(SILVER_PATH, encoding='utf-8-sig',
                 usecols=[COL_DATE, COL_QTY, COL_PRICE, COL_PLINE, COL_MARGIN])
df.columns = ['date', 'qty', 'price', 'pline', 'margin']
df['date'] = pd.to_datetime(df['date'], errors='coerce')
df = df.dropna(subset=['date'])
df['qty'] = pd.to_numeric(df['qty'], errors='coerce').fillna(0)
df['price'] = pd.to_numeric(df['price'], errors='coerce').fillna(0)
df['margin'] = pd.to_numeric(df['margin'], errors='coerce')
df['qtr_start_ep'] = df['date'].apply(_rolling_qtr_start_ep)
df['quarter'] = df['qtr_start_ep'].apply(_format_qtr_label)
df['quarter_sort'] = df['qtr_start_ep']

print(f"  总行数: {len(df):,}")
print(f"  日期范围: {df['date'].min().date()} ~ {df['date'].max().date()}")
print(f"  产品线数: {df['pline'].nunique()}")

# ============================================================
# 2. 聚合：产品线 × 季度
# ============================================================
print("\n" + "=" * 60)
print("聚合数据...")
print("=" * 60)

pline_qtr = df.groupby(['pline', 'quarter', 'quarter_sort']).agg(
    qty    = ('qty', 'sum'),
    price  = ('price', 'mean'),
    margin = ('margin', 'mean'),
    rows   = ('qty', 'count'),
).reset_index()

all_qtrs = sorted(pline_qtr['quarter'].unique(),
                  key=lambda q: pline_qtr[pline_qtr['quarter'] == q]['quarter_sort'].iloc[0])
print(f"  覆盖季度数: {len(all_qtrs)}")
print(f"  季度范围: {all_qtrs[0]} ~ {all_qtrs[-1]}")

# ============================================================
# 2b. 计算数量等级（Tier）
# ============================================================
print("\n" + "=" * 60)
print("计算数量等级(Tier)...")
print("=" * 60)

avg_qty_per_pline = pline_qtr.groupby('pline')['qty'].mean().reset_index()
avg_qty_per_pline.columns = ['pline', 'avg_quarterly_qty']

def assign_tier(avg_qty):
    if avg_qty >= 100_000:
        return 'High (>100K)'
    elif avg_qty >= 10_000:
        return 'Med (10K~100K)'
    else:
        return 'Low (<10K)'

avg_qty_per_pline['tier'] = avg_qty_per_pline['avg_quarterly_qty'].apply(assign_tier)

tier_counts = avg_qty_per_pline['tier'].value_counts()
for tier, cnt in tier_counts.items():
    print(f"  {tier}: {cnt}条产品线")

# 合并回主数据
pline_qtr = pline_qtr.merge(avg_qty_per_pline[['pline', 'tier', 'avg_quarterly_qty']], on='pline', how='left')

# Tier级最优策略（参考，不用于强制选择）
tier_strategy = """
Tier级参考策略（基于回测）:
  High (>100K/季): 推荐 Naive   (平均MAPE 29.2%)
  Med (10K~100K):  推荐 MA3     (平均MAPE 33.0%)
  Low (<10K):      推荐 Median4 (平均MAPE 20.0%)
注: 当前系统实际使用逐产品线最优方法，比统一Tier策略更精准
"""
print(tier_strategy)

# ============================================================
# 3. 预测方法集
# ============================================================
print("\n" + "=" * 60)
print("定义预测方法...")
print("=" * 60)

def m_naive(y, sp=4):
    """Naive: last quarter's value"""
    return y[-1] if len(y) > 0 else 0

def m_ma3(y, sp=4):
    """MA3: average of last 3 quarters"""
    if len(y) < 1: return 0
    return np.mean(y[-min(3, len(y)):])

def m_median4(y, sp=4):
    """Median of last 4 quarters"""
    if len(y) < 1: return 0
    return np.median(y[-min(4, len(y)):])

def m_holt(y, sp=4):
    """Holt's linear trend with parameter optimization"""
    if len(y) < 3: return y[-1] if len(y) > 0 else 0
    best_a, best_b, best_sse = 0.5, 0.1, np.inf
    for a in np.arange(0.05, 0.95, 0.05):
        for b in np.arange(0.05, 0.50, 0.05):
            s, bt = y[0], max(0, y[1]-y[0]) if len(y) > 1 else 0
            sse = 0
            for i in range(1, len(y)):
                sn = a * y[i] + (1 - a) * (s + bt)
                bn = b * (sn - s) + (1 - b) * bt
                sse += (y[i] - (s + bt)) ** 2
                s, bt = sn, bn
            if sse < best_sse:
                best_a, best_b, best_sse = a, b, sse
    s, bt = y[0], max(0, y[1]-y[0]) if len(y) > 1 else 0
    for i in range(1, len(y)):
        sn = best_a * y[i] + (1 - best_a) * (s + bt)
        bn = best_b * (sn - s) + (1 - best_b) * bt
        s, bt = sn, bn
    return max(0, s + bt)

def m_ensemble_median(y, sp=4):
    """Ensemble: median of Naive, MA3, Median4, Holt"""
    preds = []
    for fn in [m_naive, m_ma3, m_median4, m_holt]:
        try:
            p = fn(y, sp)
            if p > 0: preds.append(p)
        except:
            pass
    return np.median(preds) if preds else m_naive(y)

METHODS = {
    'Naive':        m_naive,
    'MA3':          m_ma3,
    'Median4':      m_median4,
    'Holt':         m_holt,
    'Ensemble_median': m_ensemble_median,
}

# ============================================================
# 4. 每条产品线选择最优方法
# ============================================================
print("\n" + "=" * 60)
print("每条产品线选择最优方法...")
print("=" * 60)

# 使用全部历史数据做 leave-one-out 回测
# 对每条产品线，对每个可用季度做预测并计算MAPE

best_methods = {}  # pline -> best method name
best_methods_mape = {}  # pline -> {method: mape}
best_method_err = {}  # pline -> best MAPE value

plines = pline_qtr['pline'].unique()
for pline in plines:
    pdata = pline_qtr[pline_qtr['pline'] == pline].sort_values('quarter_sort')
    y = pdata['qty'].values
    
    if len(y) < 4:
        # 数据太少，用Naive
        best_methods[pline] = 'Naive'
        continue
    
    # 对每个方法，在所有可能的测试点上计算MAPE
    method_errors = {m: [] for m in METHODS}
    
    for test_idx in range(3, len(y)):  # 需要至少3个历史点
        train = y[:test_idx]
        actual = y[test_idx]
        if actual <= 0:
            continue
        
        for mname, mfn in METHODS.items():
            try:
                pred = mfn(train)
                if pred > 0:
                    mape = abs(pred - actual) / actual * 100
                    method_errors[mname].append(mape)
            except:
                pass
    
    # 选择平均MAPE最低的方法
    avg_mape = {}
    for mname, errs in method_errors.items():
        if len(errs) >= 2:
            avg_mape[mname] = np.mean(errs)
    
    if not avg_mape:
        best_methods[pline] = 'Naive'
        best_method_err[pline] = -1
    else:
        best = min(avg_mape, key=avg_mape.get)
        best_methods[pline] = best
        best_method_err[pline] = avg_mape.get(best, -1)
    
    best_methods_mape[pline] = avg_mape
    
    # 显示结果
    err_str = " | ".join([f"{m}={avg_mape.get(m, -1):.1f}%" for m in METHODS if m in avg_mape])
    print(f"  {pline}: best={best_methods[pline]} | {err_str}")

# ============================================================
# 5. 预测未来4个季度
# ============================================================
print("\n" + "=" * 60)
print("预测未来4个季度...")
print("=" * 60)

# 确定要预测的季度（基于滚动季度）
last_qtr_start = int(pline_qtr['quarter_sort'].max())
last_qtr_label = _format_qtr_label(last_qtr_start)
print(f"  最新数据季度: {last_qtr_label}")

# 未来4个滚动季度
future_qtrs = next_rolling_quarters(last_qtr_start, 4)
print(f"  预测季度: {future_qtrs}")

# 收集预测结果
forecast_rows = []

for pline in plines:
    pdata = pline_qtr[pline_qtr['pline'] == pline].sort_values('quarter_sort')
    y = pdata['qty'].values
    mname = best_methods.get(pline, 'Naive')
    mfn = METHODS[mname]
    
    # 最新完整季度的单价和毛利率
    last_row = pdata.iloc[-1]
    latest_price = last_row['price']
    latest_margin = last_row['margin']
    tier = last_row['tier']
    avg_q = last_row['avg_quarterly_qty']
    
    for fq in future_qtrs:
        pred_qty = mfn(y)
        pred_qty = max(0, pred_qty)  # 不能为负
        
        # 收入 = 销量 × 最新单价
        pred_revenue = pred_qty * latest_price
        
        # 利润 = 收入 × 最新毛利率
        pred_profit = pred_revenue * latest_margin if pd.notna(latest_margin) else 0
        
        forecast_rows.append({
            'product_line': pline,
            'tier': tier,
            'avg_quarterly_qty': round(avg_q, 0),
            'forecast_quarter': fq,
            'method': mname,
            'latest_avg_price': round(latest_price, 4),
            'latest_margin_rate': round(latest_margin, 4) if pd.notna(latest_margin) else None,
            'forecast_qty': round(pred_qty, 0),
            'forecast_revenue': round(pred_revenue, 2),
            'forecast_profit': round(pred_profit, 2),
        })
        
        # 滚动预测：把预测值加入历史，用于下一期预测
        y = np.append(y, pred_qty)

forecast_df = pd.DataFrame(forecast_rows)
print(f"  生成预测记录数: {len(forecast_df)}")

# ============================================================
# 6. 汇总表
# ============================================================
print("\n" + "=" * 60)
print("生成汇总...")
print("=" * 60)

# 6a. 每条产品线 × 每季度
pivot_qty = forecast_df.pivot_table(
    index='product_line', columns='forecast_quarter',
    values='forecast_qty', aggfunc='sum'
).fillna(0).astype(int)

pivot_revenue = forecast_df.pivot_table(
    index='product_line', columns='forecast_quarter',
    values='forecast_revenue', aggfunc='sum'
).fillna(0)

pivot_profit = forecast_df.pivot_table(
    index='product_line', columns='forecast_quarter',
    values='forecast_profit', aggfunc='sum'
).fillna(0)

pivot_method = forecast_df.pivot_table(
    index='product_line', columns='forecast_quarter',
    values='method', aggfunc='first'
)

# 6b. 总量汇总
total_row = forecast_df.groupby('forecast_quarter').agg(
    total_qty=('forecast_qty', 'sum'),
    total_revenue=('forecast_revenue', 'sum'),
    total_profit=('forecast_profit', 'sum'),
).reset_index()

print(f"\n  未来4个季度预测总量:")
for _, r in total_row.iterrows():
    print(f"    {r['forecast_quarter']}: "
          f"销量={r['total_qty']:,.0f} | "
          f"收入={r['total_revenue']:,.2f} | "
          f"利润={r['total_profit']:,.2f}")

# ============================================================
# 7. 保存到Excel
# ============================================================
print("\n" + "=" * 60)
print("保存结果...")
print("=" * 60)

timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
output_path = os.path.join(OUTPUT_DIR, f'最终预测_{timestamp}.xlsx')

with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
    # Sheet 1: 详细预测（含Tier）
    forecast_df.to_excel(writer, sheet_name='预测明细', index=False)
    
    # Sheet 2: 销量透视
    pivot_qty.to_excel(writer, sheet_name='销量预测')
    
    # Sheet 3: 收入透视
    pivot_revenue.to_excel(writer, sheet_name='收入预测')
    
    # Sheet 4: 利润透视
    pivot_profit.to_excel(writer, sheet_name='利润预测')
    
    # Sheet 5: 最优方法与Tier矩阵（含MAPE）
    method_info = avg_qty_per_pline.copy()
    method_info['best_method'] = method_info['pline'].map(lambda x: best_methods.get(x, 'N/A'))
    method_info['best_MAPE'] = method_info['pline'].map(lambda x: best_method_err.get(x, -1))
    method_info['best_MAPE'] = method_info['best_MAPE'].apply(lambda x: f"{x:.1f}%" if x >= 0 else 'N/A')
    # 添加各方法MAPE列
    for m in METHODS:
        method_info[f'MAPE_{m}'] = method_info['pline'].map(
            lambda x: f"{best_methods_mape.get(x, {}).get(m, -1):.1f}%" 
            if best_methods_mape.get(x, {}).get(m, -1) >= 0 else '-')
    method_info.columns = ['产品线', '历史季度均销量', '数量等级', '最优预测方法', 
                           '最优MAPE'] + [f'MAPE_{m}' for m in METHODS]
    method_info = method_info.sort_values('历史季度均销量', ascending=False)
    method_info.to_excel(writer, sheet_name='方法与Tier', index=False)
    
    # Sheet 6: 总量汇总
    total_row.to_excel(writer, sheet_name='总量汇总', index=False)
    
    # Sheet 7: 历史数据
    pline_qtr_sorted = pline_qtr.sort_values(['pline', 'quarter_sort'])
    pline_qtr_sorted.to_excel(writer, sheet_name='历史数据', index=False)

print(f"\n=== 预测完成! ===")
print(f"   输出文件: {output_path}")
print(f"\n   文件包含以下工作表:")
print(f"     1. 预测明细 - 每条产品线每季度的预测详情 (含Tier分类)")
print(f"     2. 销量预测 - 销量透视表")
print(f"     3. 收入预测 - 收入透视表")
print(f"     4. 利润预测 - 利润透视表")
print(f"     5. 方法与Tier - 数量等级、历史均量、最优方法一览")
print(f"     6. 总量汇总 - 未来4季度的总销量/收入/利润")
print(f"     7. 历史数据 - 各产品线各季度的历史销量数据")
