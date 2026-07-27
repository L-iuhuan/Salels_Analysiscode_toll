# -*- coding: utf-8 -*-
"""
Unified Forecast System - v2 Rewrite
All fixes applied:
  Fix 1: Column name indexing (not numeric positions)
  Fix 2: Predict 销售额, derive 销售量/成本额/毛利额/毛利率 via weighted ASP
  Fix 3: Full output columns for both tables
  Fix 4: Float precision (2dp for money/qty, 4dp for rates)
  Fix 5: SKU as string
  Fix 6: History rows with full computed values
  Fix 7: Zero-forecast customer handling
  Fix 8: WAPE=0 -> 置信度="样本不足"
"""

import numpy as np
import pandas as pd
from python_calamine import CalamineWorkbook
from scipy import stats
from collections import defaultdict
import warnings
import os
import re
import sys

warnings.filterwarnings('ignore')

# ============================================================
# CONFIGURATION (重组修改#1-3: 绝对路径 → 相对/CLI, 2026-07-27)
# ============================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))            # forecasting\unified
ROOT_DIR = os.path.dirname(os.path.dirname(BASE_DIR))            # 数据分析根

# DATA_FILE: CLI 第1参数优先; 默认取 sales_analytics_platform\data\ 下最新 xlsx
def _default_data_file():
    data_dir = os.path.join(ROOT_DIR, "sales_analytics_platform", "data")
    xs = [os.path.join(data_dir, f) for f in os.listdir(data_dir)
          if f.endswith(".xlsx") and not f.startswith("~$")]
    return max(xs, key=os.path.getmtime) if xs else None

DATA_FILE = sys.argv[1] if len(sys.argv) > 1 else _default_data_file()
SHEET_NAME = "24-26"  # 修改#2(定版确认): "总表"已停止更新(5月/6月文件内容逐行相同,冻结于2026-05);
                      # "24-26"为月度刷新的活跃主表(与平台 DATA_SHEET_NAME 一致),历史窗口2024-01起
RANKING_FILE = os.path.join(BASE_DIR, "..", "quarterly", "output",
                            "quarterly_forecast_customer", "预测方法排行榜.csv")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)
print(f"  [配置] DATA_FILE = {DATA_FILE}")
print(f"  [配置] RANKING_FILE = {RANKING_FILE}")
print(f"  [配置] OUTPUT_DIR = {OUTPUT_DIR}")

# ============================================================
# STEP 1: DATA LOADING (Fix 1: use column NAMES)
# ============================================================
print("=" * 60)
print("STEP 1: Loading data...")
print("=" * 60)

wb = CalamineWorkbook.from_path(DATA_FILE)
sheet = wb.get_sheet_by_name(SHEET_NAME)
rows = list(sheet.to_python())
headers = rows[0]

data = {}
for i, h in enumerate(headers):
    col_name = str(h) if h else f"col_{i}"
    data[col_name] = [r[i] for r in rows[1:]]
df = pd.DataFrame(data)
print(f"  Loaded {len(df):,} rows, {len(df.columns)} columns")

# ---- Fix 1: Use actual column names directly ----
print("\n  Mapping fields by column name...")

# Date
df['发货日期'] = pd.to_datetime(df['发货日期'], errors='coerce')

# Product line
df['产品线'] = df['型号_产品线（新）'].fillna('未分类')
df.loc[df['产品线'] == 'PMIC', '产品线'] = '未分类'
df.loc[df['产品线'] == '', '产品线'] = '未分类'
df.loc[df['产品线'].isna(), '产品线'] = '未分类'

# Category
df['品类'] = df['型号_产品品类'].fillna('未知品类')
df.loc[df['品类'] == '', '品类'] = '未知品类'
df.loc[df['品类'].isna(), '品类'] = '未知品类'

# SKU (Fix 5: ensure string)
df['存货名称'] = df['存货名称'].fillna('未知')
df['SKU'] = df['存货编码'].fillna(df['存货名称']).fillna('未知SKU')
df['SKU'] = df['SKU'].astype(str)
df.loc[df['SKU'] == '', 'SKU'] = '未知SKU'
df.loc[df['SKU'].isna(), 'SKU'] = '未知SKU'
df.loc[df['SKU'] == 'nan', 'SKU'] = '未知SKU'

# Customer
df['客户'] = df['终端客户简称'].fillna(df['代理商/直供名称']).fillna(df['实际终端客户']).fillna('未知客户')
df.loc[df['客户'] == '', '客户'] = '未知客户'
df.loc[df['客户'].isna(), '客户'] = '未知客户'

# Customer category
df['客户类别'] = df['终端客户名称_客户类别'].fillna('MM<1000万')
df.loc[df['客户类别'] == '', '客户类别'] = 'MM<1000万'
df.loc[df['客户类别'].isna(), '客户类别'] = 'MM<1000万'

# Sales amount
df['销售额'] = pd.to_numeric(df['RMB 未税金额小计'], errors='coerce').fillna(0)

# Quantity (for ASP derivation)
df['发货数量'] = pd.to_numeric(df['发货数量'], errors='coerce').fillna(0)

# Cost (for cost price derivation)
df['总成本'] = pd.to_numeric(df['总成本'], errors='coerce').fillna(0)

# Clean: drop invalid dates and zero-sales rows
df = df.dropna(subset=['发货日期'])
df = df[df['销售额'] > 0].copy()

print(f"  Clean: {len(df):,} rows, PL:{df['产品线'].nunique()}, Cat:{df['品类'].nunique()}, SKU:{df['SKU'].nunique()}, Cust:{df['客户'].nunique()}")

# ============================================================
# STEP 2: BUCKET BUILDING
# ============================================================
print("\nSTEP 2: Building 3-month sliding buckets...")

df['_月'] = df['发货日期'].dt.to_period('M')
latest_month = df['_月'].max()
print(f"  Latest month in data: {latest_month}")


def build_buckets(latest_month):
    buckets = []
    for idx in range(12):
        end = latest_month - (11 - idx) * 3
        start = end - 2
        buckets.append({
            '数据类型': '历史', '桶序号': idx + 1, '桶编号': f'H{idx+1:02d}',
            '开始月': start, '结束月': end
        })
    for idx in range(4):
        start = latest_month + idx * 3 + 1
        end = start + 2
        buckets.append({
            '数据类型': '预测', '桶序号': idx + 1, '桶编号': f'F{idx+1:02d}',
            '开始月': start, '结束月': end
        })
    return buckets


buckets = build_buckets(latest_month)
for b in buckets:
    print(f"  {b['桶编号']}: {b['开始月']} -> {b['结束月']} ({b['数据类型']})")

H_BUCKETS = [f'H{i+1:02d}' for i in range(12)]
F_BUCKETS = [f'F{i+1:02d}' for i in range(4)]


def get_bucket_mask(df, b):
    start_date = pd.Timestamp(b['开始月'].start_time.date())
    end_date = pd.Timestamp(b['结束月'].end_time.date())
    return (df['发货日期'] >= start_date) & (df['发货日期'] <= end_date)


# Pre-assign bucket to each row
df['_bucket'] = None
for b in buckets:
    mask = get_bucket_mask(df, b)
    df.loc[mask, '_bucket'] = b['桶编号']
    df.loc[mask, '_bucket_type'] = b['数据类型']
    df.loc[mask, '_bucket_start'] = str(b['开始月'])
    df.loc[mask, '_bucket_end'] = str(b['结束月'])

df_with_buckets = df[df['_bucket'].notna()].copy()
print(f"  Rows with bucket assignment: {len(df_with_buckets):,}")

# ============================================================
# STEP 3: MULTI-METRIC AGGREGATION
# ============================================================
print("\nSTEP 3: Multi-metric aggregation...")

BUCKET_NAMES = H_BUCKETS + F_BUCKETS


def fast_aggregate_multi(df, group_cols):
    """Returns {key: {bucket: {'销售额': s, '销售量': q, '成本额': c}}}"""
    result = defaultdict(lambda: defaultdict(lambda: {'销售额': 0.0, '销售量': 0.0, '成本额': 0.0}))

    grouped = df.groupby(group_cols + ['_bucket']).agg(
        销售额=('销售额', 'sum'),
        销售量=('发货数量', 'sum'),
        成本额=('总成本', 'sum')
    ).reset_index()

    n_gc = len(group_cols)
    for _, row in grouped.iterrows():
        if n_gc == 1:
            key = row[group_cols[0]]
        else:
            key = tuple(row[gc] for gc in group_cols)
        bucket = row['_bucket']
        result[key][bucket] = {
            '销售额': float(row['销售额']),
            '销售量': float(row['销售量']),
            '成本额': float(row['成本额'])
        }
    return result


# Aggregate at all levels
pl_agg = fast_aggregate_multi(df_with_buckets, ['产品线'])
cat_agg = fast_aggregate_multi(df_with_buckets, ['产品线', '品类'])
sku_agg = fast_aggregate_multi(df_with_buckets, ['产品线', '品类', 'SKU'])
cust_agg = fast_aggregate_multi(df_with_buckets, ['客户'])
cp_agg = fast_aggregate_multi(df_with_buckets, ['客户', '产品线', 'SKU'])

print(f"  Product line aggregates: {len(pl_agg)}")
print(f"  Category aggregates: {len(cat_agg)}")
print(f"  SKU aggregates: {len(sku_agg)}")
print(f"  Customer aggregates: {len(cust_agg)}")
print(f"  Customer-Product aggregates: {len(cp_agg)}")

# Build SKU name map for product name lookup
sku_name_map = {}
for _, r in df_with_buckets[['存货编码','存货名称']].drop_duplicates().iterrows():
    sku_name_map[str(r['存货编码'])] = str(r['存货名称'])

# ---- Helper functions for extracting metrics from agg dict ----
def entity_metrics(agg_dict, key, bucket):
    """Get the 3-metric dict for a specific entity+bucket."""
    return agg_dict.get(key, {}).get(bucket, {'销售额': 0.0, '销售量': 0.0, '成本额': 0.0})


def entity_sales_series(agg_dict, key):
    """Get sales-only pd.Series for forecasting (H01-H12)."""
    bv = agg_dict.get(key, {})
    all_h = [f'H{i+1:02d}' for i in range(12)]
    return pd.Series([bv.get(h, {}).get('销售额', 0.0) for h in all_h], index=all_h)


def compute_entity_asp(agg_dict, key, bucket_list):
    """Compute weighted ASP with trend factor from given buckets."""
    bv = agg_dict.get(key, {})
    all_buckets = list(bucket_list)
    
    # Recent 3 buckets
    recent_buckets = all_buckets[-3:] if len(all_buckets) >= 3 else all_buckets
    recent_sales = sum(bv.get(b, {}).get('销售额', 0.0) for b in recent_buckets)
    recent_qty = sum(bv.get(b, {}).get('销售量', 0.0) for b in recent_buckets)
    asp_recent = recent_sales / recent_qty if recent_qty > 0 else 0.0
    
    # Earlier 3 buckets (for trend)
    if len(all_buckets) >= 6:
        earlier_buckets = all_buckets[-6:-3]
        earlier_sales = sum(bv.get(b, {}).get('销售额', 0.0) for b in earlier_buckets)
        earlier_qty = sum(bv.get(b, {}).get('销售量', 0.0) for b in earlier_buckets)
        asp_earlier = earlier_sales / earlier_qty if earlier_qty > 0 else asp_recent
    else:
        asp_earlier = asp_recent
    
    # Trend factor: half the change, clamped ±10%
    if asp_earlier > 0 and asp_recent > 0:
        trend = (asp_recent / asp_earlier - 1.0) * 0.5
        trend = max(min(trend, 0.10), -0.10)
    else:
        trend = 0.0
    
    return asp_recent * (1.0 + trend)


def compute_entity_cost_price(agg_dict, key, bucket_list):
    """Compute weighted cost price with trend factor from given buckets."""
    bv = agg_dict.get(key, {})
    all_buckets = list(bucket_list)
    
    # Recent 3 buckets
    recent_buckets = all_buckets[-3:] if len(all_buckets) >= 3 else all_buckets
    recent_cost = sum(bv.get(b, {}).get('成本额', 0.0) for b in recent_buckets)
    recent_qty = sum(bv.get(b, {}).get('销售量', 0.0) for b in recent_buckets)
    cp_recent = recent_cost / recent_qty if recent_qty > 0 else 0.0
    
    # Earlier 3 buckets (for trend)
    if len(all_buckets) >= 6:
        earlier_buckets = all_buckets[-6:-3]
        earlier_cost = sum(bv.get(b, {}).get('成本额', 0.0) for b in earlier_buckets)
        earlier_qty = sum(bv.get(b, {}).get('销售量', 0.0) for b in earlier_buckets)
        cp_earlier = earlier_cost / earlier_qty if earlier_qty > 0 else cp_recent
    else:
        cp_earlier = cp_recent
    
    # Trend factor: half the change, clamped ±10%
    if cp_earlier > 0 and cp_recent > 0:
        trend = (cp_recent / cp_earlier - 1.0) * 0.5
        trend = max(min(trend, 0.10), -0.10)
    else:
        trend = 0.0
    
    return cp_recent * (1.0 + trend)


def get_asp_fallback(primary_agg, primary_key, fallback_agg, fallback_key, global_key, buckets):
    """Get ASP with 3-level fallback: SKU->Category->ProductLine."""
    asp = compute_entity_asp(primary_agg, primary_key, buckets)
    if asp <= 0 and fallback_agg is not None:
        asp = compute_entity_asp(fallback_agg, fallback_key, buckets)
    if asp <= 0:
        asp = compute_entity_asp(pl_agg, global_key, buckets)
    return asp if asp > 0 else 0.0


def get_cost_fallback(primary_agg, primary_key, fallback_agg, fallback_key, global_key, buckets):
    """Get cost price with 3-level fallback: SKU->Category->ProductLine."""
    cp = compute_entity_cost_price(primary_agg, primary_key, buckets)
    if cp <= 0 and fallback_agg is not None:
        cp = compute_entity_cost_price(fallback_agg, fallback_key, buckets)
    if cp <= 0:
        cp = compute_entity_cost_price(pl_agg, global_key, buckets)
    return cp if cp > 0 else 0.0


def compute_customer_sku_asp(cp_agg, cust, sku, bucket_list):
    """Compute customer-specific ASP for a given customer+SKU combination."""
    best_asp = 0.0
    best_qty = 0
    for (c, pl_cp, sku_cp), bv in cp_agg.items():
        if c == cust and str(sku_cp) == str(sku):
            total_sales = sum(bv.get(b, {}).get('销售额', 0.0) for b in bucket_list[-3:])
            total_qty = sum(bv.get(b, {}).get('销售量', 0.0) for b in bucket_list[-3:])
            if total_qty > best_qty:
                best_qty = total_qty
                best_asp = total_sales / total_qty
    if best_asp > 0:
        return best_asp
    # Fallback: return 0 to signal "use regular ASP"
    return 0.0


# ============================================================
# STEP 4: METHOD POOL
# ============================================================
print("\nSTEP 4: Building method pool...")


def forecast_single(data_array, algo_name, params):
    """Compute a single forecast given array of historical values."""
    window = min(params.get('window', len(data_array)), len(data_array))
    if window == 0:
        return np.nan
    vals = data_array[-window:].astype(float)
    return _forecast_single_impl(vals, algo_name, params, step=0)

def forecast_multi(data_array, algo_name, params, horizon=4):
    """Compute horizon-step forecast. Returns array of length horizon."""
    window = min(params.get('window', len(data_array)), len(data_array))
    if window == 0:
        return np.full(horizon, np.nan)
    vals = data_array[-window:].astype(float)
    
    # Generate horizon-step forecast by iterating
    results = []
    for h in range(horizon):
        f = _forecast_single_impl(vals, algo_name, params, step=h)
        results.append(max(0.0, f))
    return np.array(results)

def _forecast_single_impl(vals, algo_name, params, step=0):
    """Internal: single-step forecast with optional step offset for multi-horizon."""
    if algo_name == '最近值':
        return float(vals[-1])
    elif algo_name == '均值':
        return float(np.mean(vals))
    elif algo_name == '中位数':
        return float(np.median(vals))
    elif algo_name == '线性加权均值':
        w = np.arange(1, len(vals) + 1)
        return float(np.average(vals, weights=w))
    elif algo_name == '指数加权均值':
        alpha = params.get('alpha', 0.5)
        if len(vals) == 1:
            return float(vals[0])
        result = float(vals[0])
        for i in range(1, len(vals)):
            result = alpha * vals[i] + (1 - alpha) * result
        return result
    elif algo_name == '线性趋势':
        if len(vals) < 2:
            return float(vals[-1])
        x = np.arange(len(vals), dtype=float)
        slope, intercept, _, _, _ = stats.linregress(x, vals)
        return max(0.0, float(intercept + slope * (len(vals) + step)))
    elif algo_name == '对数线性趋势':
        if len(vals) < 2:
            return float(vals[-1])
        x = np.arange(len(vals), dtype=float)
        pos = np.maximum(vals, 1e-10)
        slope, intercept, _, _, _ = stats.linregress(x, np.log(pos))
        return max(0.0, float(np.exp(intercept + slope * (len(vals) + step))))
    elif algo_name == '漂移':
        if len(vals) < 2:
            return float(vals[-1])
        drift_val = np.mean(np.diff(vals))
        return max(0.0, float(vals[-1] + drift_val * (1 + step)))
    elif algo_name == '同比季节':
        lag = params.get('season_lag', 4)
        gw = params.get('growth_window', 4)
        full_data = vals
        if len(full_data) >= lag:
            sv = float(full_data[-lag])
        else:
            sv = float(vals[-1])
        if len(full_data) >= gw * 2:
            recent = np.sum(full_data[-gw:])
            earlier = np.sum(full_data[-2*gw:-gw])
            gf = recent / earlier if earlier > 0 else 1.0
        else:
            gf = 1.0
        return max(0.0, sv * (gf ** (1 + step)))
    elif algo_name == '衰减趋势':
        dr = params.get('decay_rate', 0.7)
        if len(vals) < 2:
            return float(vals[-1])
        trend = np.mean(np.diff(vals))
        if trend > 0:
            return float(vals[-1] + trend * dr * (1 + step))
        return max(0.0, float(vals[-1] * (dr ** (1 + step))))
    elif algo_name == '保守增长':
        gr = params.get('growth_rate', 0.05)
        return float(np.mean(vals) * ((1 + gr) ** (1 + step)))
    elif algo_name == '保守衰减':
        dr = params.get('decay_rate', 0.05)
        return max(0.0, float(np.mean(vals) * ((1 - dr) ** (1 + step))))
    elif algo_name == 'Croston':
        alpha = params.get('alpha', 0.5)
        nonzero = vals[vals > 0]
        if len(nonzero) == 0:
            return 0.0
        sizes, intervals = [], []
        last_nz = -1
        for i, v in enumerate(vals):
            if v > 0:
                sizes.append(v)
                if last_nz >= 0:
                    intervals.append(i - last_nz)
                last_nz = i
        if not sizes:
            return 0.0
        s = float(sizes[0])
        for sz in sizes[1:]:
            s = alpha * sz + (1 - alpha) * s
        if intervals:
            iv = float(intervals[0])
            for it in intervals[1:]:
                iv = alpha * it + (1 - alpha) * iv
        else:
            iv = 1.0
        return s / max(iv, 1.0)
    elif algo_name == '月度季节指数':
        return float(np.mean(vals))
    elif algo_name == '组合中位数':
        ws = [min(w, len(vals)) for w in [2, 3, 4, 6] if w <= len(vals)]
        if not ws:
            return float(vals[-1])
        return float(np.median([np.median(vals[-w:]) for w in ws]))
    return np.nan

    return _forecast_single_impl(vals, algo_name, params, step=0)


def build_method_candidates():
    """Build method candidates (~145 total)."""
    candidates = []
    windows = [4, 6, 8, 12]  # minimum window = 4 (stability constraint)

    simple = ['最近值', '均值', '中位数', '线性加权均值', '线性趋势', '对数线性趋势', '漂移', '组合中位数']
    for m in simple:
        for w in windows:
            candidates.append({'name': f'{m}(窗口={w})', 'algorithm': m, 'params': {'window': w}})

    for w in windows:
        for alpha in [0.2, 0.35, 0.5, 0.85]:
            candidates.append({'name': f'指数加权均值(窗口={w},alpha={alpha})', 'algorithm': '指数加权均值',
                               'params': {'window': w, 'alpha': alpha}})

    for w in windows:
        for alpha in [0.2, 0.35, 0.5, 0.85]:
            candidates.append({'name': f'Croston(窗口={w},alpha={alpha})', 'algorithm': 'Croston',
                               'params': {'window': w, 'alpha': alpha}})

    for w in windows:
        for d in [0.4, 0.9]:
            candidates.append({'name': f'衰减趋势(窗口={w},衰减={d})', 'algorithm': '衰减趋势',
                               'params': {'window': w, 'decay_rate': d}})

    for w in windows:
        for r in [0.02, 0.10]:
            candidates.append({'name': f'保守增长(窗口={w},增长率={r})', 'algorithm': '保守增长',
                               'params': {'window': w, 'growth_rate': r}})

    for w in windows:
        for r in [0.02, 0.10]:
            candidates.append({'name': f'保守衰减(窗口={w},衰减率={r})', 'algorithm': '保守衰减',
                               'params': {'window': w, 'decay_rate': r}})

    for gw in [2, 4, 6]:
        candidates.append({'name': f'同比季节(窗口=12,季节滞后=4,增长窗口={gw})', 'algorithm': '同比季节',
                           'params': {'window': 12, 'season_lag': 4, 'growth_window': gw}})

    for sw in [24, 36]:
        candidates.append({'name': f'月度季节指数(窗口=12,季节窗口={sw})', 'algorithm': '月度季节指数',
                           'params': {'window': 12, 'seasonal_window': sw}})

    return candidates


method_candidates = build_method_candidates()
print(f"  Total method candidates: {len(method_candidates)}")


# ============================================================
# STEP 5: BACKTEST ENGINE
# ============================================================
print("\nSTEP 5: Backtest engine...")


def calc_wape(actuals, forecasts):
    a = np.array(actuals, dtype=float)
    f = np.array(forecasts, dtype=float)
    mask = a > 0
    if mask.sum() == 0:
        return np.nan
    return float(np.sum(np.abs(a[mask] - f[mask])) / np.sum(a[mask]))


def fast_backtest(series_values, candidates, min_train=3):
    """Fast backtest using pre-computed series values."""
    vals = np.array(series_values, dtype=float)
    n = len(vals)
    if n < min_train + 1:
        return []

    results = []
    for ci, mc in enumerate(candidates):
        wape_folds = []
        params = mc['params']

        for fold_n in range(min_train, min(n, 12)):
            train_vals = vals[:fold_n]
            actual = vals[fold_n]
            if actual <= 0 or len(train_vals) == 0:
                continue

            adj_params = params.copy()
            adj_params['window'] = min(params.get('window', fold_n), len(train_vals))

            try:
                fcast = forecast_single(train_vals, mc['algorithm'], adj_params)
            except Exception:
                continue

            if not np.isnan(fcast) and fcast >= 0:
                wape_folds.append((actual, fcast))

        if len(wape_folds) >= 1:
            act, fct = zip(*wape_folds)
            wape = calc_wape(act, fct)
            if not np.isnan(wape):
                results.append((ci, wape, mc['name']))

    results.sort(key=lambda x: x[1])
    return results


# ============================================================
# STEP 6: PRODUCT PATH (Fix 2: predict 销售额, derive rest via ASP)
# ============================================================
print("\nSTEP 6: Product Path - forecasting product lines...")

product_lines = sorted(df['产品线'].unique())
print(f"  Processing {len(product_lines)} product lines...")

pl_forecasts = {}  # {pl: (method_name, wape, confidence, fcast_sales_list, asp, cost_price)}
pl_all_results = []

for idx, pl in enumerate(product_lines):
    series = entity_sales_series(pl_agg, pl)
    nonzero = series[series > 0]
    if len(nonzero) < 4:
        print(f"  [{idx+1}/{len(product_lines)}] {pl}: <4 non-zero buckets ({len(nonzero)}), skipping")
        continue

    vals = series.values
    first_nz = np.argmax(vals > 0) if any(vals > 0) else 0
    trimmed = vals[first_nz:]

    bt = fast_backtest(trimmed, method_candidates, min_train=3)
    if not bt:
        print(f"  [{idx+1}/{len(product_lines)}] {pl}: backtest failed, skipping")
        continue

    best_idx, best_wape, best_name = bt[0]
    best_mc = method_candidates[best_idx]
    
    # ---- Method overrides (validated via monthly sliding backtest) ----
    method_overrides = {
        '通用电源管理': ('指数加权均值', {'window': 4, 'alpha': 0.50}),
        '有刷直流电机驱动': ('指数加权均值', {'window': 6, 'alpha': 0.50}),
        '充电与控制电源管理': ('指数加权均值', {'window': 6, 'alpha': 0.35}),
        'POE电源管理': ('指数加权均值', {'window': 6, 'alpha': 0.35}),
    }
    if pl in method_overrides:
        ov_algo, ov_params = method_overrides[pl]
        # Find matching method in candidate pool
        for ci, mc in enumerate(method_candidates):
            if mc['algorithm'] == ov_algo and all(mc['params'].get(k) == v for k, v in ov_params.items()):
                best_idx, best_wape, best_name = ci, best_wape, mc['name']
                best_mc = mc
                print(f"  [{idx+1}/{len(product_lines)}] {pl}: OVERRIDE -> {best_name}")
                break

    # ---- Forecast 销售额 (multi-horizon: 4 quarters) ----
    params = best_mc['params'].copy()
    params['window'] = min(params.get('window', len(trimmed)), len(trimmed))
    fcast_sales_arr = forecast_multi(trimmed, best_mc['algorithm'], params, horizon=4)
    if np.any(np.isnan(fcast_sales_arr)) or np.all(fcast_sales_arr < 0):
        fallback = float(np.mean(trimmed[-4:])) if len(trimmed) >= 4 else float(np.mean(trimmed))
        fcast_sales_arr = np.full(4, fallback)
    fcast_sales_arr = np.maximum(fcast_sales_arr, 0.0)
    
    # ---- Derive ASP and cost price from full history (12 buckets, more stable) ----
    train_buckets = H_BUCKETS
    asp = compute_entity_asp(pl_agg, pl, train_buckets)
    cost_price = compute_entity_cost_price(pl_agg, pl, train_buckets)
    if np.isnan(asp) or asp <= 0:
        asp = 0.0
    if np.isnan(cost_price) or cost_price < 0:
        cost_price = 0.0
    
    # ---- Fix 8: WAPE=0 -> 样本不足 ----
    if best_wape == 0.0:
        confidence = "样本不足"
    else:
        confidence = '高' if best_wape <= 0.20 else ('中' if best_wape <= 0.45 else '低')

    # ---- Prediction intervals based on WAPE ----
    wape_band = max(best_wape, 0.05)  # minimum 5% band
    fcast_lo = np.maximum(fcast_sales_arr * (1 - wape_band), 0)
    fcast_hi = fcast_sales_arr * (1 + wape_band)

    # Method stability assessment
    win_size = params.get('window', 0)
    if win_size <= 2:
        stability = '不稳定(窗口过短)'
    elif win_size <= 4:
        stability = '一般'
    else:
        stability = '稳定'
    
    pl_forecasts[pl] = (best_name, best_wape, confidence, fcast_sales_arr, fcast_lo, fcast_hi, asp, cost_price, stability)
    
    # Trend sanity check
    hist_avg = np.mean(trimmed[-4:]) if len(trimmed) >= 4 else np.mean(trimmed)
    fcst_avg = np.mean(fcast_sales_arr)
    trend_change = (fcst_avg - hist_avg) / hist_avg * 100 if hist_avg > 0 else 0
    trend_flag = ''
    if abs(trend_change) > 30:
        trend_flag = ' [TREND ALERT: {:+d}%]'.format(int(trend_change))
    
    print(f"  [{idx+1}/{len(product_lines)}] {pl}: {best_name}, WAPE={best_wape:.4f}, "
          f"F01={fcast_sales_arr[0]:.0f} [{fcast_lo[0]:.0f}-{fcast_hi[0]:.0f}], stable={stability}{trend_flag}")

# ============================================================
# STEP 6b: SHRINKAGE ALLOCATION PL -> Category -> SKU
# ============================================================
print("\nSTEP 6b: Shrinkage allocation PL->Category->SKU...")


def shrinkage_share(raw_shares, n_obs_dict, lambda_val=4):
    n = len(raw_shares)
    if n == 0:
        return {}
    if n == 1:
        return {list(raw_shares.keys())[0]: 1.0}
    prior = 1.0 / n
    shrunk = {}
    for ent, rs in raw_shares.items():
        nobs = n_obs_dict.get(ent, 0)
        shrunk[ent] = (nobs * rs + lambda_val * prior) / (nobs + lambda_val)
    total = sum(shrunk.values())
    if total > 0:
        return {k: v / total for k, v in shrunk.items()}
    return shrunk


# Build PL->Category shares
pl_totals = defaultdict(float)
for (pl_cat, cat), bv in cat_agg.items():
    for hb in H_BUCKETS:
        pl_totals[pl_cat] += bv.get(hb, {}).get('销售额', 0.0)

pl_cat_raw = defaultdict(dict)
pl_cat_nobs = defaultdict(dict)
for (pl_cat, cat), bv in cat_agg.items():
    hist_sales = [bv.get(hb, {}).get('销售额', 0.0) for hb in H_BUCKETS]
    total = sum(hist_sales)
    if total <= 0:
        continue
    all_pl = pl_totals.get(pl_cat, 0.0)
    if all_pl > 0:
        pl_cat_raw[pl_cat][cat] = total / all_pl
    nz_buckets = sum(1 for hb in H_BUCKETS if bv.get(hb, {}).get('销售额', 0.0) > 0)
    pl_cat_nobs[pl_cat][cat] = nz_buckets

# Build Category->SKU shares
cat_totals = defaultdict(float)
for (pl_cat2, cat2, sku), bv in sku_agg.items():
    for hb in H_BUCKETS:
        cat_totals[(pl_cat2, cat2)] += bv.get(hb, {}).get('销售额', 0.0)

cat_sku_raw = defaultdict(dict)
cat_sku_nobs = defaultdict(dict)
for (pl_cat2, cat2, sku), bv in sku_agg.items():
    hist_sales = [bv.get(hb, {}).get('销售额', 0.0) for hb in H_BUCKETS]
    total = sum(hist_sales)
    if total <= 0:
        continue
    all_cat = cat_totals.get((pl_cat2, cat2), 0.0)
    if all_cat > 0:
        cat_sku_raw[(pl_cat2, cat2)][sku] = total / all_cat
    nz_buckets = sum(1 for hb in H_BUCKETS if bv.get(hb, {}).get('销售额', 0.0) > 0)
    cat_sku_nobs[(pl_cat2, cat2)][sku] = nz_buckets

product_output_rows = []

# ---- HISTORY ROWS (Fix 6: full computed values) ----
print("  Building history rows...")
for (pl_hist, cat_hist, sku_hist), bv in sku_agg.items():
    # Compute SKU-level ASP from its own history
    sku_asp = compute_entity_asp(sku_agg, (pl_hist, cat_hist, sku_hist), H_BUCKETS)
    sku_cp = compute_entity_cost_price(sku_agg, (pl_hist, cat_hist, sku_hist), H_BUCKETS)

    for i, hb in enumerate(H_BUCKETS):
        m = bv.get(hb, {})
        sales_val = m.get('销售额', 0.0)
        if sales_val <= 0:
            continue
        qty_val = m.get('销售量', 0.0)
        cost_val = m.get('成本额', 0.0)
        gp_val = sales_val - cost_val
        gm_val = gp_val / sales_val if sales_val > 0 else 0.0
        bucket_asp = sales_val / qty_val if qty_val > 0 else sku_asp

        bk = buckets[i]
        sku_name = sku_name_map.get(str(sku_hist), '未知')
        product_output_rows.append({
            '产品线': pl_hist, '品类': cat_hist, 'SKU': str(sku_hist), '产品名称': sku_name,
            '数据类型': '历史', '桶编号': hb,
            '桶开始月': str(bk['开始月']), '桶结束月': str(bk['结束月']),
            '销售额': float(round(sales_val, 2)),
            '销售额下限': '',
            '销售额上限': '',
            '销售量': float(round(qty_val, 2)),
            '毛利额': float(round(gp_val, 2)),
            '毛利率': float(round(gm_val, 4)),
            '成本额': float(round(cost_val, 2)),
            '加权ASP': float(round(bucket_asp, 4)),
            '预测方法': '历史实际', '方法WAPE': '', '方法稳定性': '', '置信度': '历史实际'
        })

print(f"  History rows: {len(product_output_rows)}")

# ---- FORECAST ROWS with shrinkage + prediction intervals ----
print("  Building forecast rows...")
for pl, (method_name, wape, confidence, fcast_arr, fcast_lo, fcast_hi, pl_asp, pl_cost_price, stability) in pl_forecasts.items():
    cat_shares = pl_cat_raw.get(pl, {})
    cat_nobs_dict = pl_cat_nobs.get(pl, {})

    if not cat_shares:
        for fi in range(4):
            fb = F_BUCKETS[fi]
            bk = buckets[12 + fi]
            sales = float(fcast_arr[fi])
            sales_lo = float(fcast_lo[fi])
            sales_hi = float(fcast_hi[fi])
            qty = sales / pl_asp if pl_asp > 0 else 0.0
            cost = qty * pl_cost_price if pl_cost_price > 0 else 0.0
            gp = sales - cost
            gm = gp / sales if sales > 0 else 0.0
            if qty == 0: gm = 0.0
            product_output_rows.append({
                '产品线': pl, '品类': '未知品类', 'SKU': '未知SKU', '产品名称': '未知',
                '数据类型': '预测', '桶编号': fb,
                '桶开始月': str(bk['开始月']), '桶结束月': str(bk['结束月']),
                '销售额': float(round(sales, 2)),
                '销售额下限': float(round(sales_lo, 2)),
                '销售额上限': float(round(sales_hi, 2)),
                '销售量': float(round(qty, 2)),
                '毛利额': float(round(gp, 2)),
                '毛利率': float(round(gm, 4)),
                '成本额': float(round(cost, 2)),
                '加权ASP': float(round(pl_asp, 4)),
                '预测方法': method_name, '方法WAPE': float(round(wape, 4)) if wape > 0 else '',
                '置信度': confidence, '方法稳定性': stability
            })
        continue

    shrunk_cat = shrinkage_share(cat_shares, cat_nobs_dict)
    for cat, cat_pct in shrunk_cat.items():
        sku_key = (pl, cat)
        sku_shares = cat_sku_raw.get(sku_key, {})
        sku_nobs = cat_sku_nobs.get(sku_key, {})

        cat_asp = get_asp_fallback(cat_agg, (pl, cat), None, None, pl, H_BUCKETS)
        cat_cp = get_cost_fallback(cat_agg, (pl, cat), None, None, pl, H_BUCKETS)

        if not sku_shares:
            for fi in range(4):
                fb = F_BUCKETS[fi]
                bk = buckets[12 + fi]
                sales = float(fcast_arr[fi] * cat_pct)
                sales_lo = float(fcast_lo[fi] * cat_pct)
                sales_hi = float(fcast_hi[fi] * cat_pct)
                qty = sales / cat_asp if cat_asp > 0 else 0.0
                cost = qty * cat_cp if cat_cp > 0 else 0.0
                gp = sales - cost
                gm = gp / sales if sales > 0 else 0.0
                if qty == 0: gm = 0.0
                product_output_rows.append({
                    '产品线': pl, '品类': cat, 'SKU': '未知SKU', '产品名称': '未知',
                    '数据类型': '预测', '桶编号': fb,
                    '桶开始月': str(bk['开始月']), '桶结束月': str(bk['结束月']),
                    '销售额': float(round(sales, 2)),
                    '销售额下限': float(round(sales_lo, 2)),
                    '销售额上限': float(round(sales_hi, 2)),
                    '销售量': float(round(qty, 2)),
                    '毛利额': float(round(gp, 2)),
                    '毛利率': float(round(gm, 4)),
                    '成本额': float(round(cost, 2)),
                    '加权ASP': float(round(cat_asp, 4)),
                    '预测方法': method_name, '方法WAPE': float(round(wape, 4)) if wape > 0 else '',
                    '置信度': confidence, '方法稳定性': stability
                })
            continue

        shrunk_sku = shrinkage_share(sku_shares, sku_nobs)
        for sku, sku_pct in shrunk_sku.items():
            sku_asp_v = get_asp_fallback(sku_agg, (pl, cat, sku), cat_agg, (pl, cat), pl, H_BUCKETS)
            sku_cp_v = get_cost_fallback(sku_agg, (pl, cat, sku), cat_agg, (pl, cat), pl, H_BUCKETS)

            for fi in range(4):
                fb = F_BUCKETS[fi]
                bk = buckets[12 + fi]
                sales = float(fcast_arr[fi] * cat_pct * sku_pct)
                sales_lo = float(fcast_lo[fi] * cat_pct * sku_pct)
                sales_hi = float(fcast_hi[fi] * cat_pct * sku_pct)
                qty = sales / sku_asp_v if sku_asp_v > 0 else 0.0
                cost = qty * sku_cp_v if sku_cp_v > 0 else 0.0
                gp = sales - cost
                gm = gp / sales if sales > 0 else 0.0
                if qty == 0: gm = 0.0
                product_output_rows.append({
                    '产品线': pl, '品类': cat, 'SKU': str(sku),
                    '产品名称': sku_name_map.get(str(sku), '未知'),
                    '数据类型': '预测', '桶编号': fb,
                    '桶开始月': str(bk['开始月']), '桶结束月': str(bk['结束月']),
                    '销售额': float(round(sales, 2)),
                    '销售额下限': float(round(sales_lo, 2)),
                    '销售额上限': float(round(sales_hi, 2)),
                    '销售量': float(round(qty, 2)),
                    '毛利额': float(round(gp, 2)),
                    '毛利率': float(round(gm, 4)),
                    '成本额': float(round(cost, 2)),
                    '加权ASP': float(round(sku_asp_v, 4)),
                    '预测方法': method_name, '方法WAPE': float(round(wape, 4)) if wape > 0 else '',
                    '置信度': confidence, '方法稳定性': stability
                })

product_output_df = pd.DataFrame(product_output_rows)
hist_count = len(product_output_df[product_output_df['数据类型'] == '历史'])
fcst_count = len(product_output_df[product_output_df['数据类型'] == '预测'])
print(f"  Product output: {len(product_output_df)} rows (hist={hist_count}, fcst={fcst_count})")

# ============================================================
# STEP 7: CUSTOMER PATH
# ============================================================
print("\nSTEP 7: Customer Path...")

# Load ranking
ranking_df = pd.read_csv(RANKING_FILE, encoding='utf-8-sig')
ka_aa_best = ranking_df[ranking_df['排名'] == 1].copy()
ka_aa_categories = ['AA>5000万', 'KA>1亿']


def parse_method_name(method_name_str):
    """Parse method name from ranking CSV into algo+params."""
    if '-' in method_name_str:
        parts = method_name_str.rsplit('-', 1)
        algo_part = parts[-1]
    else:
        algo_part = method_name_str
    match = re.match(r'(.+?)\((.*)\)', algo_part)
    if not match:
        return None
    algo_name = match.group(1)
    params_str = match.group(2)
    params = {}
    for param in params_str.split(','):
        param = param.strip()
        if '=' in param:
            k, v = param.split('=', 1)
            k, v = k.strip(), v.strip()
            try:
                params[k] = float(v) if '.' in v else int(v)
            except ValueError:
                params[k] = v
    algo_map = {
        '保守增长': '保守增长', '漂移': '漂移', '同比季节': '同比季节',
        '组合中位数': '组合中位数', '中位数': '中位数', '均值': '均值',
        '指数加权均值': '指数加权均值', 'Croston': 'Croston',
        '月度季节指数': '月度季节指数', '线性加权均值': '线性加权均值',
        '最近值': '最近值', '线性趋势': '线性趋势', '对数线性趋势': '对数线性趋势',
        '衰减趋势': '衰减趋势', '保守衰减': '保守衰减',
    }
    our_algo = algo_map.get(algo_name)
    if not our_algo:
        return None
    param_map = {
        '窗口': 'window', '增长窗口': 'growth_window', '增长率': 'growth_rate',
        '衰减率': 'decay_rate', 'alpha': 'alpha', '季节滞后': 'season_lag',
        '季节窗口': 'seasonal_window', '衰减': 'decay_rate',
    }
    mapped = {}
    for k, v in params.items():
        mapped[param_map.get(k, k)] = v
    return {
        'algorithm': our_algo, 'params': mapped,
        'window': mapped.get('window', 4), 'raw_name': method_name_str
    }


ka_aa_methods = {}
for _, row in ka_aa_best.iterrows():
    cust = row['客户']
    parsed = parse_method_name(row['方法名称'])
    if parsed:
        parsed['wape'] = row['销售额WAPE']
        ka_aa_methods[cust] = parsed

print(f"  KA/AA parsed methods: {len(ka_aa_methods)}")

# Customer-category map
print("  Building customer-category map...")
cust_cat_map = df.groupby('客户')['客户类别'].first().to_dict()
print(f"  Mapped {len(cust_cat_map)} customers to categories")

# Identify active KM/MM (近12月 > 500万)
km_mm_12m = df_with_buckets[~df_with_buckets['客户类别'].isin(['KA>1亿','AA>5000万'])].groupby('客户')['销售额'].sum()
active_km_mm = set(km_mm_12m[km_mm_12m > 5000000].index)
print(f"  Active KM/MM for individual prediction: {len(active_km_mm)}")

# Process all customers
all_customers = sorted(df['客户'].unique())
customer_output_rows = []
ka_aa_count = 0
km_mm_forecasted = 0
skipped_data = 0
skipped_aggregate = 0

print(f"  Processing {len(all_customers)} customers...")

for ci, cust in enumerate(all_customers):
    series = entity_sales_series(cust_agg, cust)
    vals = series.values
    first_nz = np.argmax(vals > 0) if any(vals > 0) else 0
    trimmed = vals[first_nz:]
    n_nonzero = int(np.sum(trimmed > 0))

    cust_cat = cust_cat_map.get(cust, 'MM<1000万')
    is_ka_aa = cust_cat in ka_aa_categories

    # ---- HISTORY ROWS (Fix 6) ----
    cust_bv = cust_agg.get(cust, {})
    cust_asp_hist = compute_entity_asp(cust_agg, cust, H_BUCKETS)
    for i, hb in enumerate(H_BUCKETS):
        m = cust_bv.get(hb, {})
        sales_val = m.get('销售额', 0.0)
        if sales_val <= 0:
            continue
        qty_val = m.get('销售量', 0.0)
        cost_val = m.get('成本额', 0.0)
        gp_val = sales_val - cost_val
        gm_val = gp_val / sales_val if sales_val > 0 else 0.0
        bucket_asp = sales_val / qty_val if qty_val > 0 else cust_asp_hist

        bk = buckets[i]
        customer_output_rows.append({
            '客户': cust, '客户类别': cust_cat,
            '产品线': '', '产品(SKU)': '',
            '数据类型': '历史', '桶编号': hb,
            '桶开始月': str(bk['开始月']), '桶结束月': str(bk['结束月']),
            '销售额': float(round(sales_val, 2)),
            '销售额下限': '',
            '销售额上限': '',
            '销售量': float(round(qty_val, 2)),
            '毛利额': float(round(gp_val, 2)),
            '毛利率': float(round(gm_val, 4)),
            '成本额': float(round(cost_val, 2)),
            '加权ASP': float(round(bucket_asp, 4)),
            '预测方法': '历史实际', '方法WAPE': '', '置信度': '历史实际'
        })

    # ---- Fix 7: Zero-forecast customers ----
    # Check data sufficiency - only predict individually for KA/AA and active KM/MM
    is_individual = is_ka_aa or cust in active_km_mm
    if not is_individual:
        # Skip individual prediction, will be aggregated later
        skipped_aggregate += 1
        if (ci + 1) % 100 == 0:
            print(f"  [{ci+1}/{len(all_customers)}] KA/AA:{ka_aa_count} KM/MM:{km_mm_forecasted} skip_agg:{skipped_aggregate}")
        continue

    # Determine best method
    if is_ka_aa and cust in ka_aa_methods:
        parsed = ka_aa_methods[cust]
        best_algo = parsed['algorithm']
        best_params = parsed['params'].copy()
        best_wape = parsed['wape']
        method_name = parsed['raw_name']
        ka_aa_count += 1
    elif is_ka_aa:
        best_algo = '均值'
        best_params = {'window': min(6, len(trimmed))}
        best_wape = 0.5
        method_name = '均值(窗口=6)-fallback'
        ka_aa_count += 1
    else:
        # KM/MM - run backtest
        bt = fast_backtest(trimmed, method_candidates, min_train=3)
        if not bt:
            skipped_data += 1
            if (ci + 1) % 100 == 0:
                print(f"  [{ci+1}/{len(all_customers)}] KA/AA:{ka_aa_count} KM/MM:{km_mm_forecasted} skip:{skipped_data}")
            continue
        best_idx, best_wape, best_name = bt[0]
        best_mc = method_candidates[best_idx]
        best_algo = best_mc['algorithm']
        best_params = best_mc['params'].copy()
        method_name = best_name
        km_mm_forecasted += 1

    # ---- Forecast 销售额 (multi-horizon) ----
    best_params['window'] = min(best_params.get('window', len(trimmed)), len(trimmed))
    try:
        fcast_sales_arr = forecast_multi(trimmed, best_algo, best_params, horizon=4)
    except Exception:
        fcast_sales_arr = np.full(4, np.nan)
    if np.any(np.isnan(fcast_sales_arr)) or np.all(fcast_sales_arr < 0):
        fallback = float(np.mean(trimmed[-4:])) if len(trimmed) >= 4 else float(np.mean(trimmed))
        fcast_sales_arr = np.full(4, fallback)
    fcast_sales_arr = np.maximum(fcast_sales_arr, 0.0)

    # ---- Fix 7: Check for zero forecast ----
    if np.all(fcast_sales_arr <= 0) and n_nonzero >= 5:
        fallback = float(np.mean(trimmed[-4:])) if len(trimmed) >= 4 else float(np.mean(trimmed))
        fcast_sales_arr = np.full(4, fallback)

    # ---- Derive ASP and cost price using full history ----
    cust_asp = compute_entity_asp(cust_agg, cust, H_BUCKETS)
    cust_cp = compute_entity_cost_price(cust_agg, cust, H_BUCKETS)
    if np.isnan(cust_asp) or cust_asp <= 0:
        cust_asp = 0.0
    if np.isnan(cust_cp) or cust_cp < 0:
        cust_cp = 0.0

    # ---- Fix 8: WAPE=0 -> 样本不足 ----
    if best_wape == 0.0 or np.isnan(best_wape):
        confidence = "样本不足"
    elif np.all(fcast_sales_arr <= 0) and n_nonzero < 5:
        confidence = "数据不足"
    else:
        confidence = '高' if best_wape <= 0.20 else ('中' if best_wape <= 0.45 else '低')

    # ---- Prediction intervals ----
    wape_band = max(best_wape, 0.05) if not np.isnan(best_wape) else 0.5
    fcast_lo = np.maximum(fcast_sales_arr * (1 - wape_band), 0)
    fcast_hi = fcast_sales_arr * (1 + wape_band)

    for fi in range(4):
        fb = F_BUCKETS[fi]
        bk = buckets[12 + fi]
        sales = float(fcast_sales_arr[fi])
        sales_lo = float(fcast_lo[fi])
        sales_hi = float(fcast_hi[fi])
        qty = sales / cust_asp if cust_asp > 0 else 0.0
        cost = qty * cust_cp if cust_cp > 0 else 0.0
        gp = sales - cost
        gm = gp / sales if sales > 0 else 0.0
        if qty == 0: gm = 0.0

        customer_output_rows.append({
            '客户': cust, '客户类别': cust_cat,
            '产品线': '', '产品(SKU)': '',
            '数据类型': '预测', '桶编号': fb,
            '桶开始月': str(bk['开始月']), '桶结束月': str(bk['结束月']),
            '销售额': float(round(sales, 2)),
            '销售额下限': float(round(sales_lo, 2)),
            '销售额上限': float(round(sales_hi, 2)),
            '销售量': float(round(qty, 2)),
            '毛利额': float(round(gp, 2)),
            '毛利率': float(round(gm, 4)),
            '成本额': float(round(cost, 2)),
            '加权ASP': float(round(cust_asp, 4)),
            '预测方法': method_name, '方法WAPE': float(round(best_wape, 4)) if (isinstance(best_wape, (int, float)) and best_wape > 0) else '',
            '置信度': confidence
        })

    if (ci + 1) % 100 == 0:
        print(f"  [{ci+1}/{len(all_customers)}] KA/AA:{ka_aa_count} KM/MM:{km_mm_forecasted} skip_agg:{skipped_aggregate}")

print(f"  Final: KA/AA:{ka_aa_count} KM/MM:{km_mm_forecasted} skip_agg:{skipped_aggregate} (will be aggregated)")

cust_df = pd.DataFrame(customer_output_rows)
print(f"  Customer output (pre-split): {len(cust_df)} rows")

# ============================================================
# STEP 7b: PRODUCT SPLIT for customers
# ============================================================
print("\nSTEP 7b: Product split for customers...")

# Build customer->product shares from cp_agg
cust_prod_shares = defaultdict(dict)
cust_prod_nobs = defaultdict(dict)

for (cust_cp, pl_cp, sku_cp), bv in cp_agg.items():
    hist_sales = [bv.get(hb, {}).get('销售额', 0.0) for hb in H_BUCKETS]
    total = sum(hist_sales)
    if total <= 0:
        continue
    cust_total = sum(
        bv2.get(hb, {}).get('销售额', 0.0)
        for hb in H_BUCKETS
        for (c2, p2, s2), bv2 in cp_agg.items()
        if c2 == cust_cp
    )
    if cust_total <= 0:
        continue
    prod_id = f'{pl_cp}|||{sku_cp}'
    cust_prod_shares[cust_cp][prod_id] = total / cust_total
    nz = sum(1 for hb in H_BUCKETS if bv.get(hb, {}).get('销售额', 0.0) > 0)
    cust_prod_nobs[cust_cp][prod_id] = nz

# Expand forecast rows with product split
final_customer_rows = []
cust_forecast = cust_df[cust_df['数据类型'] == '预测']

for _, frow in cust_forecast.iterrows():
    cust = frow['客户']
    fb = frow['桶编号']
    total_fcast = frow['销售额']
    total_lo = frow.get('销售额下限', total_fcast)
    total_hi = frow.get('销售额上限', total_fcast)
    method_name = frow['预测方法']
    wape = frow['方法WAPE']
    confidence = frow['置信度']
    cust_cat = frow['客户类别']

    shares = cust_prod_shares.get(cust, {})
    nobs_dict = cust_prod_nobs.get(cust, {})

    if not shares:
        final_customer_rows.append(dict(frow))
        continue

    shrunk = shrinkage_share(shares, nobs_dict)
    for prod_id, share in shrunk.items():
        parts = prod_id.split('|||', 1)
        pl_name = parts[0] if len(parts) > 0 else '未知'
        sku_name = parts[1] if len(parts) > 1 else '未知'

        cp_key = (cust, pl_name, sku_name)
        # Try customer-specific ASP first, fallback to general
        cust_specific_asp = compute_customer_sku_asp(cp_agg, cust, sku_name, H_BUCKETS)
        if cust_specific_asp > 0:
            prod_asp = cust_specific_asp
        else:
            prod_asp = get_asp_fallback(cp_agg, cp_key, cust_agg, cust, pl_name, H_BUCKETS)
        prod_cp = get_cost_fallback(cp_agg, cp_key, cust_agg, cust, pl_name, H_BUCKETS)

        allocated_sales = total_fcast * share
        allocated_lo = total_lo * share
        allocated_hi = total_hi * share
        qty = allocated_sales / prod_asp if prod_asp > 0 else 0.0
        cost = qty * prod_cp if prod_cp > 0 else 0.0
        gp = allocated_sales - cost
        gm = gp / allocated_sales if allocated_sales > 0 else 0.0
        if qty == 0: gm = 0.0

        final_customer_rows.append({
            '客户': cust, '客户类别': cust_cat,
            '产品线': pl_name, '产品(SKU)': str(sku_name),
            '产品名称': sku_name_map.get(str(sku_name), '未知'),
            '数据类型': '预测', '桶编号': fb,
            '桶开始月': frow['桶开始月'], '桶结束月': frow['桶结束月'],
            '销售额': float(round(allocated_sales, 2)),
            '销售额下限': float(round(allocated_lo, 2)),
            '销售额上限': float(round(allocated_hi, 2)),
            '销售量': float(round(qty, 2)),
            '毛利额': float(round(gp, 2)),
            '毛利率': float(round(gm, 4)),
            '成本额': float(round(cost, 2)),
            '加权ASP': float(round(prod_asp, 4)),
            '预测方法': method_name, '方法WAPE': float(round(wape, 4)) if (isinstance(wape, (int, float)) and wape > 0) else '',
            '置信度': confidence
        })

# ---- Add historical rows at product level ----
for (cust_hist, pl_hist, sku_hist), bv in cp_agg.items():
    cust_cat = cust_cat_map.get(cust_hist, 'MM<1000万')
    cp_asp_hist = compute_entity_asp(cp_agg, (cust_hist, pl_hist, sku_hist), H_BUCKETS)
    for i, hb in enumerate(H_BUCKETS):
        m = bv.get(hb, {})
        sales_val = m.get('销售额', 0.0)
        if sales_val <= 0:
            continue
        qty_val = m.get('销售量', 0.0)
        cost_val = m.get('成本额', 0.0)
        gp_val = sales_val - cost_val
        gm_val = gp_val / sales_val if sales_val > 0 else 0.0
        bucket_asp = sales_val / qty_val if qty_val > 0 else cp_asp_hist

        bk = buckets[i]
        final_customer_rows.append({
            '客户': cust_hist, '客户类别': cust_cat,
            '产品线': pl_hist, '产品(SKU)': str(sku_hist),
            '产品名称': sku_name_map.get(str(sku_hist), '未知'),
            '数据类型': '历史', '桶编号': hb,
            '桶开始月': str(bk['开始月']), '桶结束月': str(bk['结束月']),
            '销售额': float(round(sales_val, 2)),
            '销售额下限': '',
            '销售额上限': '',
            '销售量': float(round(qty_val, 2)),
            '毛利额': float(round(gp_val, 2)),
            '毛利率': float(round(gm_val, 4)),
            '成本额': float(round(cost_val, 2)),
            '加权ASP': float(round(bucket_asp, 4)),
            '预测方法': '历史实际', '方法WAPE': '', '置信度': '历史实际'
        })

customer_output_df = pd.DataFrame(final_customer_rows)
hist_cc = len(customer_output_df[customer_output_df['数据类型'] == '历史'])
fcst_cc = len(customer_output_df[customer_output_df['数据类型'] == '预测'])
print(f"  Final customer output (pre-filter): {len(customer_output_df)} rows (hist={hist_cc}, fcst={fcst_cc})")

# ============================================================
# STEP 7c: RECONCILE customer path to product path totals
# ============================================================
print("\nSTEP 7c: Reconciling customer path to product path...")

# Build product path totals per (product_line, bucket)
prod_totals = {}
for pl, (method_name, wape, confidence, fcast_arr, fcast_lo, fcast_hi, pl_asp, pl_cp, stability) in pl_forecasts.items():
    for fi in range(4):
        fb = F_BUCKETS[fi]
        prod_totals[(pl, fb)] = float(fcast_arr[fi])

# Scale customer forecasts to match product line totals
cust_fcst_mask = customer_output_df['数据类型'] == '预测'
cust_fcst = customer_output_df[cust_fcst_mask].copy()

# For each (product_line, bucket), compute customer sum and scale factor
reconciled_rows = []
scale_stats = []
for (pl, fb), pl_total in prod_totals.items():
    pl_cust = cust_fcst[(cust_fcst['产品线'] == pl) & (cust_fcst['桶编号'] == fb)]
    if len(pl_cust) == 0:
        continue
    cust_sum = pl_cust['销售额'].sum()
    if cust_sum > 0 and abs(pl_total - cust_sum) > 1:
        scale = pl_total / cust_sum
        scale_stats.append((pl, fb, pl_total, cust_sum, scale))
        # Scale all customer rows for this (product_line, bucket)
        for idx in pl_cust.index:
            customer_output_df.loc[idx, '销售额'] = float(round(customer_output_df.loc[idx, '销售额'] * scale, 2))
            if '销售额下限' in customer_output_df.columns:
                customer_output_df.loc[idx, '销售额下限'] = float(round(float(customer_output_df.loc[idx, '销售额下限'] or 0) * scale, 2))
            if '销售额上限' in customer_output_df.columns:
                customer_output_df.loc[idx, '销售额上限'] = float(round(float(customer_output_df.loc[idx, '销售额上限'] or 0) * scale, 2))

if scale_stats:
    print(f"  Reconciled {len(scale_stats)} (product_line, bucket) combinations")
    # Show top divergences
    scale_stats.sort(key=lambda x: abs(1 - x[4]), reverse=True)
    for pl, fb, pt, cs, sc in scale_stats[:5]:
        print(f"    {pl} {fb}: product={pt:,.0f}, customer_orig={cs:,.0f}, scale={sc:.3f}")
else:
    print("  No reconciliation needed")

# ---- Filter out forecast rows with zero sales ----
before_filter = len(product_output_df)
product_output_df = product_output_df[
    ~((product_output_df['数据类型'] == '预测') & (pd.to_numeric(product_output_df['销售额'], errors='coerce') <= 0))
]
print(f"  Product: filtered {before_filter - len(product_output_df)} zero-sales forecast rows, now {len(product_output_df)} rows")

before_filter_c = len(customer_output_df)
customer_output_df = customer_output_df[
    ~((customer_output_df['数据类型'] == '预测') & (pd.to_numeric(customer_output_df['销售额'], errors='coerce') <= 0))
]
print(f"  Customer: filtered {before_filter_c - len(customer_output_df)} zero-sales forecast rows, now {len(customer_output_df)} rows")

# ============================================================
# STEP 7d: AGGREGATE KM/MM customers to reduce noise
# ============================================================
print("\nSTEP 7d: Aggregating KM/MM customers...")

# Keep KA/AA and active KM/MM individual, aggregate remaining KM and MM by product line
ka_aa_active_km = customer_output_df['客户类别'].isin(['KA>1亿','AA>5000万']) | customer_output_df['客户'].isin(active_km_mm)
ka_aa_rows = customer_output_df[ka_aa_active_km].copy()

# Aggregate KM customers (excluding active ones) by (产品线, 桶编号, 数据类型)
km_mask = (customer_output_df['客户类别'] == 'KM>1000万') & (~customer_output_df['客户'].isin(active_km_mm))
km_rows = customer_output_df[km_mask]
if len(km_rows) > 0:
    km_agg = km_rows.groupby(['产品线', '桶编号', '桶开始月', '桶结束月', '数据类型']).agg(
        销售额=('销售额', 'sum'),
        销售额下限=('销售额下限', lambda x: pd.to_numeric(x, errors='coerce').sum()),
        销售额上限=('销售额上限', lambda x: pd.to_numeric(x, errors='coerce').sum()),
        销售量=('销售量', 'sum'),
        成本额=('成本额', 'sum'),
    ).reset_index()
    km_agg['客户'] = '中型客户(KM汇总)'
    km_agg['客户类别'] = '中型客户(KM汇总)'
    km_agg['产品(SKU)'] = '汇总'
    km_agg['毛利额'] = km_agg['销售额'] - km_agg['成本额']
    km_agg['毛利率'] = (km_agg['毛利额'] / km_agg['销售额'].replace(0, np.nan)).fillna(0)
    asp_safe = km_agg['销售量'].replace(0, np.nan)
    km_agg['加权ASP'] = (km_agg['销售额'] / asp_safe).fillna(0)
    km_agg['预测方法'] = 'KM聚合(均值)'
    km_agg['方法WAPE'] = 0.40  # estimated
    km_agg['置信度'] = '低'
    print(f"  KM aggregated: {len(km_rows)} -> {len(km_agg)} rows")
else:
    km_agg = pd.DataFrame()

# Aggregate MM customers (excluding active ones)
mm_mask = (customer_output_df['客户类别'] == 'MM<1000万') & (~customer_output_df['客户'].isin(active_km_mm))
mm_rows = customer_output_df[mm_mask]
if len(mm_rows) > 0:
    mm_agg = mm_rows.groupby(['产品线', '桶编号', '桶开始月', '桶结束月', '数据类型']).agg(
        销售额=('销售额', 'sum'),
        销售额下限=('销售额下限', lambda x: pd.to_numeric(x, errors='coerce').sum()),
        销售额上限=('销售额上限', lambda x: pd.to_numeric(x, errors='coerce').sum()),
        销售量=('销售量', 'sum'),
        成本额=('成本额', 'sum'),
    ).reset_index()
    mm_agg['客户'] = '长尾客户(MM汇总)'
    mm_agg['客户类别'] = '长尾客户(MM汇总)'
    mm_agg['产品(SKU)'] = '汇总'
    mm_agg['毛利额'] = mm_agg['销售额'] - mm_agg['成本额']
    mm_agg['毛利率'] = (mm_agg['毛利额'] / mm_agg['销售额'].replace(0, np.nan)).fillna(0)
    asp_safe = mm_agg['销售量'].replace(0, np.nan)
    mm_agg['加权ASP'] = (mm_agg['销售额'] / asp_safe).fillna(0)
    mm_agg['预测方法'] = 'MM聚合(均值)'
    mm_agg['方法WAPE'] = 0.50  # estimated
    mm_agg['置信度'] = '低'
    print(f"  MM aggregated: {len(mm_rows)} -> {len(mm_agg)} rows")
else:
    mm_agg = pd.DataFrame()

# Combine: KA/AA individual + KM aggregate + MM aggregate
customer_output_df = pd.concat([ka_aa_rows, km_agg, mm_agg], ignore_index=True)
print(f"  Final customer output: {len(customer_output_df)} rows (KA/AA={len(ka_aa_rows)}, KM={len(km_agg)}, MM={len(mm_agg)})")

hist_cc = len(customer_output_df[customer_output_df['数据类型'] == '历史'])
fcst_cc = len(customer_output_df[customer_output_df['数据类型'] == '预测'])

# ============================================================
# STEP 8: SAVE OUTPUTS
# ============================================================
print("\nSTEP 8: Saving outputs...")

product_output_path = os.path.join(OUTPUT_DIR, 'product_path_forecast.csv')
customer_output_path = os.path.join(OUTPUT_DIR, 'customer_path_forecast.csv')

# Ensure output columns are in correct order
PRODUCT_COLS = ['产品线', '品类', 'SKU', '产品名称', '数据类型', '桶编号', '桶开始月', '桶结束月',
                '销售额', '销售额下限', '销售额上限', '销售量', '毛利额', '毛利率', '成本额', '加权ASP',
                '预测方法', '方法WAPE', '方法稳定性', '置信度']
CUSTOMER_COLS = ['客户', '客户类别', '产品线', '产品(SKU)', '产品名称', '数据类型', '桶编号', '桶开始月', '桶结束月',
                 '销售额', '销售额下限', '销售额上限', '销售量', '毛利额', '毛利率', '成本额', '加权ASP',
                 '预测方法', '方法WAPE', '置信度']

# Fill any missing columns
for c in PRODUCT_COLS:
    if c not in product_output_df.columns:
        product_output_df[c] = ''
product_output_df = product_output_df[PRODUCT_COLS]

for c in CUSTOMER_COLS:
    if c not in customer_output_df.columns:
        customer_output_df[c] = ''
customer_output_df = customer_output_df[CUSTOMER_COLS]

# Fix 5: SKU must be string, not int64
if 'SKU' in product_output_df.columns:
    product_output_df['SKU'] = product_output_df['SKU'].astype(str)
    product_output_df.loc[product_output_df['SKU'] == 'nan', 'SKU'] = '未知SKU'
if '产品(SKU)' in customer_output_df.columns:
    customer_output_df['产品(SKU)'] = customer_output_df['产品(SKU)'].astype(str)
    customer_output_df.loc[customer_output_df['产品(SKU)'] == 'nan', '产品(SKU)'] = '未知SKU'

# Fix 6: History rows - 方法WAPE should be '' not 0.0
for df_out in [product_output_df, customer_output_df]:
    hist_mask = df_out['数据类型'] == '历史'
    if '方法WAPE' in df_out.columns:
        df_out.loc[hist_mask, '方法WAPE'] = ''

# Fix 4: ensure float precision across entire columns (forecast rows only)
numeric_cols_2 = ['销售额', '销售量', '毛利额', '成本额']
numeric_cols_4 = ['毛利率', '加权ASP']

for df_out, name in [(product_output_df, 'Product'), (customer_output_df, 'Customer')]:
    fcst_mask = df_out['数据类型'] == '预测'
    for col in numeric_cols_2:
        if col in df_out.columns:
            df_out.loc[fcst_mask, col] = pd.to_numeric(df_out.loc[fcst_mask, col], errors='coerce').apply(
                lambda x: float(round(x, 2)) if pd.notna(x) else 0.0)
    for col in numeric_cols_4:
        if col in df_out.columns:
            df_out.loc[fcst_mask, col] = pd.to_numeric(df_out.loc[fcst_mask, col], errors='coerce').apply(
                lambda x: float(round(x, 4)) if pd.notna(x) else 0.0)
    # 方法WAPE for forecast: round to 4dp
    if '方法WAPE' in df_out.columns:
        df_out.loc[fcst_mask, '方法WAPE'] = pd.to_numeric(df_out.loc[fcst_mask, '方法WAPE'], errors='coerce').apply(
            lambda x: float(round(x, 4)) if pd.notna(x) else '')

# Also round history numeric columns
for df_out, name in [(product_output_df, 'Product'), (customer_output_df, 'Customer')]:
    hist_mask = df_out['数据类型'] == '历史'
    for col in numeric_cols_2:
        if col in df_out.columns:
            df_out.loc[hist_mask, col] = pd.to_numeric(df_out.loc[hist_mask, col], errors='coerce').apply(
                lambda x: float(round(x, 2)) if pd.notna(x) else 0.0)
    for col in numeric_cols_4:
        if col in df_out.columns:
            df_out.loc[hist_mask, col] = pd.to_numeric(df_out.loc[hist_mask, col], errors='coerce').apply(
                lambda x: float(round(x, 4)) if pd.notna(x) else 0.0)

# Fill remaining NaN in numeric columns with 0
for df_out in [product_output_df, customer_output_df]:
    for col in numeric_cols_2 + numeric_cols_4:
        if col in df_out.columns:
            df_out[col] = df_out[col].fillna(0.0)
    # Fill NaN in string columns with empty string
    for col in df_out.columns:
        if col not in numeric_cols_2 + numeric_cols_4 + ['方法WAPE']:
            df_out[col] = df_out[col].fillna('')

# Write with UTF-8 BOM
product_output_df.to_csv(product_output_path, index=False, encoding='utf-8-sig')
print(f"  Product: {product_output_path} ({len(product_output_df)} rows)")

customer_output_df.to_csv(customer_output_path, index=False, encoding='utf-8-sig')
print(f"  Customer: {customer_output_path} ({len(customer_output_df)} rows)")

# ============================================================
# STEP 9: DATA QUALITY CHECKS
# ============================================================
print("\n" + "=" * 60)
print("DATA QUALITY CHECKS")
print("=" * 60)

# 1. Count of rows with 销售额=0 in forecast
for name, dfo in [('Product', product_output_df), ('Customer', customer_output_df)]:
    fcst = dfo[dfo['数据类型'] == '预测']
    zero_sales = len(fcst[fcst['销售额'] <= 0])
    print(f"  [{name}] Forecast rows with 销售额<=0: {zero_sales}")

# 2. Count of customers with WAPE=0 or WAPE=NaN
cust_fcst = customer_output_df[customer_output_df['数据类型'] == '预测']
cust_wape_zero = cust_fcst[cust_fcst['方法WAPE'] == 0.0]['客户'].nunique()
cust_wape_nan = cust_fcst[cust_fcst['方法WAPE'].isna() | (cust_fcst['方法WAPE'] == '')]['客户'].nunique()
print(f"  Customers with WAPE=0 (in forecast): {cust_wape_zero}")
print(f"  Customers with WAPE=NaN/empty (in forecast): {cust_wape_nan}")

# 3. Count of rows with 毛利率 > 1 or < -1
for name, dfo in [('Product', product_output_df), ('Customer', customer_output_df)]:
    gm_col = dfo['毛利率'] if '毛利率' in dfo.columns else None
    if gm_col is not None:
        gm_vals = pd.to_numeric(gm_col, errors='coerce')
        bad_gm = len(gm_vals[(gm_vals > 1.0) | (gm_vals < -1.0)])
        print(f"  [{name}] 毛利率 > 1 or < -1: {bad_gm}")

# 4. Count of rows with 加权ASP = 0 in forecast
for name, dfo in [('Product', product_output_df), ('Customer', customer_output_df)]:
    fcst = dfo[dfo['数据类型'] == '预测']
    asp_col = pd.to_numeric(fcst['加权ASP'], errors='coerce')
    zero_asp = len(asp_col[asp_col <= 0])
    print(f"  [{name}] Forecast rows with 加权ASP=0: {zero_asp}")

# 5. Distribution of 置信度 values
for name, dfo in [('Product', product_output_df), ('Customer', customer_output_df)]:
    fcst = dfo[dfo['数据类型'] == '预测']
    print(f"  [{name}] 置信度 distribution: {dict(fcst['置信度'].value_counts())}")

# 6. Any negative 销售额/销售量
for name, dfo in [('Product', product_output_df), ('Customer', customer_output_df)]:
    neg_sales = len(dfo[pd.to_numeric(dfo['销售额'], errors='coerce') < 0])
    neg_qty = len(dfo[pd.to_numeric(dfo['销售量'], errors='coerce') < 0])
    print(f"  [{name}] Negative 销售额: {neg_sales}, Negative 销售量: {neg_qty}")

# Summary stats
print("\n" + "=" * 60)
print("SUMMARY")
print("=" * 60)
print(f"Product: {len(product_output_df)} rows, PLs={product_output_df['产品线'].nunique()}")
if fcst_count > 0:
    pf = product_output_df[product_output_df['数据类型'] == '预测']
    print(f"  Forecast rows: {len(pf)}, confidence: {dict(pf['置信度'].value_counts())}")
    total_fcst_sales = pd.to_numeric(pf['销售额'], errors='coerce').sum()
    print(f"  Total forecast 销售额: {total_fcst_sales:,.2f}")
    # Method stability
    if '方法稳定性' in pf.columns:
        print(f"  Method stability: {dict(pf['方法稳定性'].value_counts())}")

print(f"Customer: {len(customer_output_df)} rows, Custs={customer_output_df['客户'].nunique()}")
if fcst_cc > 0:
    cf = customer_output_df[customer_output_df['数据类型'] == '预测']
    print(f"  Forecast rows: {len(cf)}, confidence: {dict(cf['置信度'].value_counts())}")
    print(f"  Categories: {dict(cf['客户类别'].value_counts())}")

# Two paths comparison
print()
print("--- Two Paths Reconciliation ---")
prod_f = product_output_df[product_output_df['数据类型'] == '预测']
cust_f = customer_output_df[customer_output_df['数据类型'] == '预测']
pt = pd.to_numeric(prod_f['销售额'], errors='coerce').sum()
ct = pd.to_numeric(cust_f['销售额'], errors='coerce').sum()
print(f"  Product path total: {pt:,.0f}")
print(f"  Customer path total: {ct:,.0f}")
print(f"  Difference: {pt - ct:+,.0f} ({(pt - ct)/pt*100:+.1f}%)")
print(f"  (Customer path reconciled to product path per product line)")

print("\nDONE!")
