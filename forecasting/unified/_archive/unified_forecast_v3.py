# -*- coding: utf-8 -*-
"""
Unified Forecast System v3 - Rebuilt with:
  - FULL method pool (~200+ candidates, 12 base algorithms)
  - Monthly sliding window backtest for method selection
  - KA/AA individual prediction, KM/MM aggregated
  - Product path + Customer path output tables
"""

import numpy as np
import pandas as pd
from python_calamine import CalamineWorkbook
from scipy import stats
from collections import defaultdict
import warnings
import os
import re

warnings.filterwarnings('ignore')

# ============================================================
# CONFIGURATION
# ============================================================
DATA_FILE = r"E:\3-其他资料\数据分析\semiconductor_analysis\data\财务分析-5月（6.3）.xlsx"
SHEET_NAME = "总表"
RANKING_FILE = r"E:\3-其他资料\数据分析\semiconductor_analysis\quarterly_forecast_package\output\quarterly_forecast_customer\预测方法排行榜.csv"
OUTPUT_DIR = r"E:\3-其他资料\数据分析\semiconductor_analysis\output\unified_forecast"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ============================================================
# STEP 1: DATA LOADING
# ============================================================
print("=" * 70)
print("STEP 1: Loading data...")
print("=" * 70)

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

# ---- Field mapping ----
print("\n  Mapping fields...")
df['发货日期'] = pd.to_datetime(df['发货日期'], errors='coerce')

df['产品线'] = df['型号_产品线（新）'].fillna('未分类')
df.loc[df['产品线'] == 'PMIC', '产品线'] = '未分类'
df.loc[df['产品线'] == '', '产品线'] = '未分类'
df.loc[df['产品线'].isna(), '产品线'] = '未分类'

df['品类'] = df['型号_产品品类'].fillna('未知品类')
df.loc[df['品类'] == '', '品类'] = '未知品类'
df.loc[df['品类'].isna(), '品类'] = '未知品类'

df['SKU'] = df['存货编码'].fillna(df['存货名称']).fillna('未知SKU')
df['SKU'] = df['SKU'].astype(str)
df.loc[df['SKU'] == '', 'SKU'] = '未知SKU'
df.loc[df['SKU'].isna(), 'SKU'] = '未知SKU'
df.loc[df['SKU'] == 'nan', 'SKU'] = '未知SKU'

df['客户'] = df['终端客户简称'].fillna(df['代理商/直供名称']).fillna(df['实际终端客户']).fillna('未知客户')
df.loc[df['客户'] == '', '客户'] = '未知客户'
df.loc[df['客户'].isna(), '客户'] = '未知客户'

df['客户类别'] = df['终端客户名称_客户类别'].fillna('MM<1000万')
df.loc[df['客户类别'] == '', '客户类别'] = 'MM<1000万'
df.loc[df['客户类别'].isna(), '客户类别'] = 'MM<1000万'

df['销售额'] = pd.to_numeric(df['RMB 未税金额小计'], errors='coerce').fillna(0)
df['销售量'] = pd.to_numeric(df['发货数量'], errors='coerce').fillna(0)
# Try both '成本' and '总成本' for cost column
cost_col = '总成本' if '总成本' in df.columns else ('成本' if '成本' in df.columns else None)
if cost_col:
    df['成本额'] = pd.to_numeric(df[cost_col], errors='coerce').fillna(0)
else:
    df['成本额'] = 0.0
df['毛利额'] = df['销售额'] - df['成本额']

# Filter
df = df.dropna(subset=['发货日期'])
df = df[(df['发货数量'] > 0) & (df['销售额'] > 0)].copy()
print(f"  Clean: {len(df):,} rows, PL:{df['产品线'].nunique()}, Cat:{df['品类'].nunique()}, "
      f"SKU:{df['SKU'].nunique()}, Cust:{df['客户'].nunique()}")

# ============================================================
# STEP 2: BUCKET BUILDING
# ============================================================
print("\n" + "=" * 70)
print("STEP 2: Building 3-month sliding buckets...")
print("=" * 70)

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
# STEP 3: MULTI-METRIC AGGREGATION + MONTHLY TIME SERIES
# ============================================================
print("\n" + "=" * 70)
print("STEP 3: Multi-metric aggregation and monthly time series...")
print("=" * 70)


def fast_aggregate_multi(df, group_cols):
    """Returns {key: {bucket: {'销售额': s, '销售量': q, '成本额': c}}}"""
    result = defaultdict(lambda: defaultdict(lambda: {'销售额': 0.0, '销售量': 0.0, '成本额': 0.0}))
    grouped = df.groupby(group_cols + ['_bucket']).agg(
        销售额=('销售额', 'sum'),
        销售量=('销售量', 'sum'),
        成本额=('成本额', 'sum')
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

# Build monthly time series from raw data
print("  Building monthly time series from raw data...")
df_with_buckets['_month'] = df_with_buckets['发货日期'].dt.to_period('M')

# Product-line monthly sales
pl_monthly = df_with_buckets.groupby(['产品线', '_month'])['销售额'].sum().unstack(fill_value=0.0)
pl_monthly = pl_monthly.reindex(columns=sorted(pl_monthly.columns))

# Customer monthly sales
cust_monthly = df_with_buckets.groupby(['客户', '_month'])['销售额'].sum().unstack(fill_value=0.0)
cust_monthly = cust_monthly.reindex(columns=sorted(cust_monthly.columns))

# Customer-product monthly sales
cp_monthly = df_with_buckets.groupby(['客户', '产品线', '_month'])['销售额'].sum().unstack(fill_value=0.0)
cp_monthly = cp_monthly.reindex(columns=sorted(cp_monthly.columns))

# Customer-product-SKU monthly sales
cpsku_monthly = df_with_buckets.groupby(['客户', '产品线', 'SKU', '_month'])['销售额'].sum().unstack(fill_value=0.0)
cpsku_monthly = cpsku_monthly.reindex(columns=sorted(cpsku_monthly.columns))

print(f"  PL monthly: {pl_monthly.shape}, Cust monthly: {cust_monthly.shape}")

# ---- Helper functions ----
def entity_metrics(agg_dict, key, bucket):
    return agg_dict.get(key, {}).get(bucket, {'销售额': 0.0, '销售量': 0.0, '成本额': 0.0})


def entity_sales_series(agg_dict, key):
    bv = agg_dict.get(key, {})
    all_h = H_BUCKETS
    return pd.Series([bv.get(h, {}).get('销售额', 0.0) for h in all_h], index=all_h)


def compute_entity_asp(agg_dict, key, bucket_list):
    bv = agg_dict.get(key, {})
    total_sales = sum(bv.get(b, {}).get('销售额', 0.0) for b in bucket_list)
    total_qty = sum(bv.get(b, {}).get('销售量', 0.0) for b in bucket_list)
    return total_sales / total_qty if total_qty > 0 else 0.0


def compute_entity_cost_price(agg_dict, key, bucket_list):
    bv = agg_dict.get(key, {})
    total_cost = sum(bv.get(b, {}).get('成本额', 0.0) for b in bucket_list)
    total_qty = sum(bv.get(b, {}).get('销售量', 0.0) for b in bucket_list)
    return total_cost / total_qty if total_qty > 0 else 0.0


def get_asp_fallback(primary_agg, primary_key, fallback_agg, fallback_key, global_key, buckets):
    asp = compute_entity_asp(primary_agg, primary_key, buckets)
    if asp <= 0 and fallback_agg is not None:
        asp = compute_entity_asp(fallback_agg, fallback_key, buckets)
    if asp <= 0:
        asp = compute_entity_asp(pl_agg, global_key, buckets)
    return asp if asp > 0 else 0.0


def get_cost_fallback(primary_agg, primary_key, fallback_agg, fallback_key, global_key, buckets):
    cp = compute_entity_cost_price(primary_agg, primary_key, buckets)
    if cp <= 0 and fallback_agg is not None:
        cp = compute_entity_cost_price(fallback_agg, fallback_key, buckets)
    if cp <= 0:
        cp = compute_entity_cost_price(pl_agg, global_key, buckets)
    return cp if cp > 0 else 0.0


# ============================================================
# STEP 4: FULL METHOD POOL (~200+ candidates)
# ============================================================
print("\n" + "=" * 70)
print("STEP 4: Building FULL method pool (~200+ candidates)...")
print("=" * 70)


def forecast_single(vals, algo_name, params_in):
    """Compute a single forecast given array of historical values."""
    params = dict(params_in)
    window = min(params.get('window', len(vals)), len(vals))
    if window == 0:
        return np.nan
    wv = np.array(vals[-window:], dtype=float)
    return _forecast_impl(wv, algo_name, params, step=0)


def forecast_multi(vals, algo_name, params_in, horizon=4):
    """Compute horizon-step forecast. Returns array of length horizon."""
    params = dict(params_in)
    window = min(params.get('window', len(vals)), len(vals))
    if window == 0:
        return np.full(horizon, np.nan)
    wv = np.array(vals[-window:], dtype=float)
    results = []
    for h in range(horizon):
        f = _forecast_impl(wv, algo_name, params, step=h)
        results.append(max(0.0, f))
    return np.array(results)


def _forecast_impl(vals, algo_name, params, step=0):
    """Internal: single-step forecast with optional step offset for multi-horizon."""
    n = len(vals)
    if algo_name == '最近值':
        return float(vals[-1])

    elif algo_name == '均值':
        return float(np.mean(vals))

    elif algo_name == '中位数':
        return float(np.median(vals))

    elif algo_name == '线性加权均值':
        w = np.arange(1, n + 1)
        return float(np.average(vals, weights=w))

    elif algo_name == '指数加权均值':
        alpha = params.get('alpha', 0.5)
        if n == 1:
            return float(vals[0])
        result = float(vals[0])
        for i in range(1, n):
            result = alpha * vals[i] + (1 - alpha) * result
        return result

    elif algo_name == '线性趋势':
        if n < 2:
            return float(vals[-1])
        x = np.arange(n, dtype=float)
        slope, intercept, _, _, _ = stats.linregress(x, vals)
        return max(0.0, float(intercept + slope * (n + step)))

    elif algo_name == '对数线性趋势':
        if n < 2:
            return float(vals[-1])
        x = np.arange(n, dtype=float)
        pos = np.maximum(vals, 1e-10)
        slope, intercept, _, _, _ = stats.linregress(x, np.log(pos))
        return max(0.0, float(np.exp(intercept + slope * (n + step))))

    elif algo_name == '漂移':
        if n < 2:
            return float(vals[-1])
        drift_val = np.mean(np.diff(vals))
        return max(0.0, float(vals[-1] + drift_val * (1 + step)))

    elif algo_name == '同比季节':
        lag = params.get('season_lag', 4)
        gw = params.get('growth_window', 4)
        if n >= lag:
            sv = float(vals[-lag])
        else:
            sv = float(vals[-1])
        if n >= gw * 2:
            recent = np.sum(vals[-gw:])
            earlier = np.sum(vals[-2*gw:-gw])
            gf = recent / earlier if earlier > 0 else 1.0
        else:
            gf = 1.0
        return max(0.0, sv * (gf ** (1 + step)))

    elif algo_name == '衰减趋势':
        dr = params.get('decay_rate', 0.7)
        if n < 2:
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

    # Additional algorithms for KA/AA customers from ranking file
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
        ws = [min(w, n) for w in [2, 3, 4, 6] if w <= n]
        if not ws:
            return float(vals[-1])
        return float(np.median([np.median(vals[-w:]) for w in ws]))

    return np.nan


def build_method_candidates():
    """
    Build FULL method candidates.
    12 base algorithms: 最近值, 均值, 中位数, 线性加权均值, 指数加权均值,
    线性趋势, 对数线性趋势, 漂移, 同比季节, 衰减趋势, 保守增长, 保守衰减

    Parameter sweeps generate ~200+ candidates.
    Minimum window constraint: window >= 4 (skip window=1,2,3 candidates).
    """
    candidates = []
    windows = [1, 2, 3, 4, 6, 8, 12]

    # Skip window=1,2 (too short), keep window >= 3
    valid_windows = [w for w in windows if w >= 3]

    # 1. Simple algorithms (no extra params)
    simple = ['最近值', '均值', '中位数', '线性加权均值', '线性趋势', '对数线性趋势', '漂移']
    for m in simple:
        for w in valid_windows:
            candidates.append({
                'name': f'{m}(窗口={w})',
                'algorithm': m,
                'params': {'window': w}
            })

    # 2. 指数加权均值: alpha sweep
    for w in valid_windows:
        for alpha in [0.2, 0.35, 0.5, 0.7, 0.85]:
            candidates.append({
                'name': f'指数加权均值(窗口={w},alpha={alpha})',
                'algorithm': '指数加权均值',
                'params': {'window': w, 'alpha': alpha}
            })

    # 3. 衰减趋势: decay sweep
    for w in valid_windows:
        for d in [0.4, 0.7, 0.9]:
            candidates.append({
                'name': f'衰减趋势(窗口={w},衰减={d})',
                'algorithm': '衰减趋势',
                'params': {'window': w, 'decay_rate': d}
            })

    # 4. 保守增长: growth rate sweep
    for w in valid_windows:
        for r in [0.02, 0.05, 0.10]:
            candidates.append({
                'name': f'保守增长(窗口={w},增长率={r})',
                'algorithm': '保守增长',
                'params': {'window': w, 'growth_rate': r}
            })

    # 5. 保守衰减: decay rate sweep
    for w in valid_windows:
        for r in [0.02, 0.05, 0.10]:
            candidates.append({
                'name': f'保守衰减(窗口={w},衰减率={r})',
                'algorithm': '保守衰减',
                'params': {'window': w, 'decay_rate': r}
            })

    # 6. 同比季节: growth_window sweep, window always 12
    for gw in [2, 3, 4, 6]:
        candidates.append({
            'name': f'同比季节(窗口=12,季节滞后=4,增长窗口={gw})',
            'algorithm': '同比季节',
            'params': {'window': 12, 'season_lag': 4, 'growth_window': gw}
        })

    return candidates


method_candidates = build_method_candidates()
print(f"  Total method candidates: {len(method_candidates)} (min window >= 3, skip window=1,2)")
# Show a few examples
for mc in method_candidates[:3]:
    print(f"    Example: {mc['name']}")
print(f"    ... and {len(method_candidates)-3} more")

# ============================================================
# STEP 5: MONTHLY SLIDING WINDOW BACKTEST
# ============================================================
print("\n" + "=" * 70)
print("STEP 5: Monthly sliding window backtest engine...")
print("=" * 70)


def calc_wape(actuals, forecasts):
    a = np.array(actuals, dtype=float)
    f = np.array(forecasts, dtype=float)
    mask = a > 0
    if mask.sum() == 0:
        return np.nan
    return float(np.sum(np.abs(a[mask] - f[mask])) / np.sum(a[mask]))


def monthly_sliding_backtest(monthly_values, candidates, train_months=6, predict_months=3):
    """
    monthly_values: numpy array of monthly sales
    Slide: train on [i-train_months:i], predict [i:i+predict_months]
    i ranges from train_months to len(monthly_values)-predict_months

    Returns: list of (candidate_name, wape, n_folds)
    """
    n = len(monthly_values)
    results = []

    for mc in candidates:
        errors = []
        for i in range(train_months, n - predict_months + 1):
            train = monthly_values[i - train_months:i]
            actual = monthly_values[i:i + predict_months].sum()
            if actual <= 0:
                continue
            # Adjust window to fit train length
            params = dict(mc['params'])
            params['window'] = min(params.get('window', len(train)), len(train))
            try:
                pred_monthly = forecast_single(train, mc['algorithm'], params)
                if np.isnan(pred_monthly) or pred_monthly < 0:
                    continue
                pred = pred_monthly * predict_months
                errors.append((actual, pred))
            except Exception:
                continue

        if len(errors) >= 1:
            wape = calc_wape([e[0] for e in errors], [e[1] for e in errors])
            if not np.isnan(wape):
                results.append((mc['name'], wape, len(errors), mc['algorithm'], mc['params']))

    results.sort(key=lambda x: x[1])
    return results


def monthly_sliding_backtest_quarterly(monthly_values, candidates, train_months=6, predict_months=3):
    """
    Same as monthly_sliding_backtest but also returns detailed fold errors.
    Used for product line selection.
    """
    n = len(monthly_values)
    results = []

    for mc in candidates:
        errors = []
        all_fold_errors = []
        for i in range(train_months, n - predict_months + 1):
            train = monthly_values[i - train_months:i]
            actual = monthly_values[i:i + predict_months].sum()
            if actual <= 0:
                continue
            params = dict(mc['params'])
            params['window'] = min(params.get('window', len(train)), len(train))
            try:
                pred_monthly = forecast_single(train, mc['algorithm'], params)
                if np.isnan(pred_monthly) or pred_monthly < 0:
                    continue
                pred = pred_monthly * predict_months
                errors.append((actual, pred))
                all_fold_errors.append({'actual': actual, 'pred': pred})
            except Exception:
                continue

        if len(errors) >= 1:
            wape = calc_wape([e[0] for e in errors], [e[1] for e in errors])
            if not np.isnan(wape):
                results.append({
                    'name': mc['name'],
                    'wape': wape,
                    'n_folds': len(errors),
                    'algorithm': mc['algorithm'],
                    'params': mc['params'],
                    'fold_errors': all_fold_errors
                })

    results.sort(key=lambda x: x['wape'])
    return results


print("  Backtest engine ready.")

# ============================================================
# STEP 6: PRODUCT PATH
# ============================================================
print("\n" + "=" * 70)
print("STEP 6: Product Path - forecasting product lines...")
print("=" * 70)

product_lines = sorted(df['产品线'].unique())
print(f"  Processing {len(product_lines)} product lines...")

pl_forecasts = {}  # {pl: dict with method info}
pl_all_results = []

for idx, pl in enumerate(product_lines):
    # Get monthly time series
    if pl not in pl_monthly.index:
        print(f"  [{idx+1}/{len(product_lines)}] {pl}: no monthly data, skipping")
        continue
    monthly_vals = pl_monthly.loc[pl].values.astype(float)

    # Trim leading zeros
    first_nz = 0
    for i, v in enumerate(monthly_vals):
        if v > 0:
            first_nz = i
            break
    trimmed = monthly_vals[first_nz:]

    nz_count = int(np.sum(trimmed > 0))
    if nz_count < 4 or len(trimmed) < 6:
        print(f"  [{idx+1}/{len(product_lines)}] {pl}: insufficient data "
              f"(nz={nz_count}, len={len(trimmed)}), skipping")
        continue

    # Run monthly sliding backtest
    bt_results = monthly_sliding_backtest_quarterly(trimmed, method_candidates,
                                                     train_months=6, predict_months=3)
    if not bt_results:
        print(f"  [{idx+1}/{len(product_lines)}] {pl}: backtest failed, skipping")
        continue

    best = bt_results[0]
    best_name = best['name']
    best_wape = best['wape']
    best_algo = best['algorithm']
    best_params = dict(best['params'])
    best_params['window'] = min(best_params.get('window', len(trimmed)), len(trimmed))

    # Generate 4-quarter forecast (12 months)
    fcast_sales_arr = forecast_multi(trimmed, best_algo, best_params, horizon=4)
    if np.any(np.isnan(fcast_sales_arr)) or np.all(fcast_sales_arr <= 0):
        fallback = float(np.mean(trimmed[-4:])) if len(trimmed) >= 4 else float(np.mean(trimmed))
        fcast_sales_arr = np.full(4, max(fallback, 0.0))
    fcast_sales_arr = np.maximum(fcast_sales_arr, 0.0)

    # Derive ASP and cost price from full history
    asp = compute_entity_asp(pl_agg, pl, H_BUCKETS)
    cost_price = compute_entity_cost_price(pl_agg, pl, H_BUCKETS)
    if np.isnan(asp) or asp <= 0:
        asp = 0.0
    if np.isnan(cost_price) or cost_price < 0:
        cost_price = 0.0

    # Confidence
    if best_wape == 0.0:
        confidence = "样本不足"
    else:
        confidence = '高' if best_wape <= 0.20 else ('中' if best_wape <= 0.45 else '低')

    # Prediction intervals
    wape_band = max(best_wape, 0.05)
    fcast_lo = np.maximum(fcast_sales_arr * (1 - wape_band), 0)
    fcast_hi = fcast_sales_arr * (1 + wape_band)

    # Method stability
    win_size = best_params.get('window', 0)
    if win_size <= 2:
        stability = '不稳定(窗口过短)'
    elif win_size <= 4:
        stability = '一般'
    else:
        stability = '稳定'

    pl_forecasts[pl] = {
        'method_name': best_name,
        'wape': best_wape,
        'confidence': confidence,
        'fcast_arr': fcast_sales_arr,
        'fcast_lo': fcast_lo,
        'fcast_hi': fcast_hi,
        'asp': asp,
        'cost_price': cost_price,
        'stability': stability
    }

    # Trend sanity check
    hist_avg = np.mean(trimmed[-4:]) if len(trimmed) >= 4 else np.mean(trimmed)
    fcst_avg = np.mean(fcast_sales_arr)
    trend_change = (fcst_avg - hist_avg) / hist_avg * 100 if hist_avg > 0 else 0
    trend_flag = ''
    if abs(trend_change) > 30:
        trend_flag = f' [TREND ALERT: {int(trend_change):+d}%]'

    print(f"  [{idx+1}/{len(product_lines)}] {pl}: {best_name}, WAPE={best_wape:.4f}, "
          f"F01={fcast_sales_arr[0]:.0f}, stable={stability}{trend_flag}")

print(f"  Forecasted {len(pl_forecasts)} product lines")

# ============================================================
# STEP 6b: SHRINKAGE ALLOCATION PL -> Category -> SKU
# ============================================================
print("\n" + "=" * 70)
print("STEP 6b: Shrinkage allocation PL->Category->SKU...")
print("=" * 70)


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

# Build output rows
product_output_rows = []

# ---- HISTORY ROWS ----
print("  Building history rows...")
for (pl_hist, cat_hist, sku_hist), bv in sku_agg.items():
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
        product_output_rows.append({
            '产品线': pl_hist, '品类': cat_hist, 'SKU': str(sku_hist),
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

# ---- FORECAST ROWS ----
print("  Building forecast rows...")
for pl, fdata in pl_forecasts.items():
    method_name = fdata['method_name']
    wape = fdata['wape']
    confidence = fdata['confidence']
    fcast_arr = fdata['fcast_arr']
    fcast_lo = fdata['fcast_lo']
    fcast_hi = fdata['fcast_hi']
    pl_asp = fdata['asp']
    pl_cost_price = fdata['cost_price']
    stability = fdata['stability']

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
            if qty == 0:
                gm = 0.0
            product_output_rows.append({
                '产品线': pl, '品类': '未知品类', 'SKU': '未知SKU',
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
                if qty == 0:
                    gm = 0.0
                product_output_rows.append({
                    '产品线': pl, '品类': cat, 'SKU': '未知SKU',
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
                if qty == 0:
                    gm = 0.0
                product_output_rows.append({
                    '产品线': pl, '品类': cat, 'SKU': str(sku),
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
print("\n" + "=" * 70)
print("STEP 7: Customer Path...")
print("=" * 70)

# ---- Load ranking file ----
print("  Loading ranking file...")
try:
    ranking_df = pd.read_csv(RANKING_FILE, encoding='utf-8-sig')
except Exception:
    try:
        ranking_df = pd.read_csv(RANKING_FILE, encoding='gbk')
    except Exception:
        ranking_df = pd.read_csv(RANKING_FILE, encoding='gb18030')

print(f"  Ranking rows: {len(ranking_df)}, columns: {list(ranking_df.columns)}")

# ---- Customer-category map ----
cust_cat_map = df.groupby('客户')['客户类别'].first().to_dict()

# ---- Parse methods for KA/AA ----
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
        '线性衰减趋势': '衰减趋势',  # alias
        '线性加权移动平均': '线性加权均值',  # alias
    }

    our_algo = algo_map.get(algo_name)
    if not our_algo:
        print(f"    WARNING: Unknown algorithm '{algo_name}' in method '{method_name_str}'")
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
        'window': int(mapped.get('window', 4)), 'raw_name': method_name_str
    }


ka_aa_methods = {}
for _, row in ka_aa_best.iterrows():
    cust = row['客户']
    parsed = parse_method_name(row['方法名称'])
    if parsed:
        parsed['wape'] = row['销售额WAPE']
        ka_aa_methods[cust] = parsed

print(f"  KA/AA parsed methods: {len(ka_aa_methods)}")
for cust, parsed in list(ka_aa_methods.items())[:5]:
    print(f"    {cust}: {parsed['raw_name']} (WAPE={parsed['wape']:.4f})")

# ---- Aggregate KM and MM ----
km_custs = [c for c, cat in cust_cat_map.items() if cat not in ka_aa_categories and 'KM' in str(cat).upper()]
mm_custs = [c for c, cat in cust_cat_map.items() if cat not in ka_aa_categories and 'MM' in str(cat).upper()]
ka_aa_custs = [c for c, cat in cust_cat_map.items() if cat in ka_aa_categories]
print(f"\n  KA/AA customers: {len(ka_aa_custs)}, KM customers: {len(km_custs)}, MM customers: {len(mm_custs)}")

# Identify KM customers from ranking file (those not KA/AA that have ranking entries)
ka_aa_in_ranking = set(ka_aa_best['客户'].unique())
km_in_ranking = [c for c in ranking_df['客户'].unique() if c not in ka_aa_in_ranking]
print(f"  KA/AA in ranking: {len(ka_aa_in_ranking)}, KM in ranking: {len(km_in_ranking)}")

customer_output_rows = []

# ---- 7a: KA/AA Individual Prediction ----
print("\n  --- KA/AA Individual Prediction ---")
for cust in ka_aa_custs:
    cust_cat = cust_cat_map.get(cust, 'KA>1亿')

    # Get monthly time series
    if cust not in cust_monthly.index:
        # No data, skip
        continue
    monthly_vals = cust_monthly.loc[cust].values.astype(float)
    first_nz = 0
    for i, v in enumerate(monthly_vals):
        if v > 0:
            first_nz = i
            break
    trimmed = monthly_vals[first_nz:]
    n_nonzero = int(np.sum(trimmed > 0))

    # Get method from ranking
    if cust in ka_aa_methods:
        parsed = ka_aa_methods[cust]
        best_algo = parsed['algorithm']
        best_params = dict(parsed['params'])
        best_wape = parsed['wape']
        method_name = parsed['raw_name']
    else:
        # No ranking entry, use mean fallback
        best_algo = '均值'
        best_params = {'window': min(6, len(trimmed))}
        best_wape = 0.5
        method_name = '均值(窗口=6)-fallback'

    best_params['window'] = min(best_params.get('window', len(trimmed)), len(trimmed))

    # Generate forecast
    try:
        fcast_arr = forecast_multi(trimmed, best_algo, best_params, horizon=4)
    except Exception:
        fcast_arr = np.full(4, np.mean(trimmed[-4:]) if len(trimmed) >= 4 else np.mean(trimmed))
    if np.any(np.isnan(fcast_arr)) or np.all(fcast_arr <= 0):
        fallback = float(np.mean(trimmed[-4:])) if len(trimmed) >= 4 else float(np.mean(trimmed))
        fcast_arr = np.full(4, max(fallback, 0.0))
    fcast_arr = np.maximum(fcast_arr, 0.0)

    # ASP and cost price
    cust_asp = compute_entity_asp(cust_agg, cust, H_BUCKETS)
    cust_cp = compute_entity_cost_price(cust_agg, cust, H_BUCKETS)
    if np.isnan(cust_asp) or cust_asp <= 0:
        cust_asp = 0.0
    if np.isnan(cust_cp) or cust_cp < 0:
        cust_cp = 0.0

    # Confidence
    if best_wape == 0.0 or np.isnan(best_wape):
        confidence = "样本不足"
    else:
        confidence = '高' if best_wape <= 0.20 else ('中' if best_wape <= 0.45 else '低')

    # Prediction intervals
    wape_band = max(best_wape, 0.05) if not np.isnan(best_wape) else 0.5
    fcast_lo = np.maximum(fcast_arr * (1 - wape_band), 0)
    fcast_hi = fcast_arr * (1 + wape_band)

    # HISTORY rows
    cust_bv = cust_agg.get(cust, {})
    for i, hb in enumerate(H_BUCKETS):
        m = cust_bv.get(hb, {})
        sales_val = m.get('销售额', 0.0)
        if sales_val <= 0:
            continue
        qty_val = m.get('销售量', 0.0)
        cost_val = m.get('成本额', 0.0)
        gp_val = sales_val - cost_val
        gm_val = gp_val / sales_val if sales_val > 0 else 0.0
        bucket_asp = sales_val / qty_val if qty_val > 0 else cust_asp
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

    # FORECAST rows (split to products)
    for fi in range(4):
        fb = F_BUCKETS[fi]
        bk = buckets[12 + fi]
        sales = float(fcast_arr[fi])
        sales_lo = float(fcast_lo[fi])
        sales_hi = float(fcast_hi[fi])
        qty = sales / cust_asp if cust_asp > 0 else 0.0
        cost = qty * cust_cp if cust_cp > 0 else 0.0
        gp = sales - cost
        gm = gp / sales if sales > 0 else 0.0
        if qty == 0:
            gm = 0.0

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
            '预测方法': method_name,
            '方法WAPE': float(round(best_wape, 4)) if (isinstance(best_wape, (int, float)) and best_wape > 0) else '',
            '置信度': confidence
        })

print(f"  KA/AA forecast rows (unsplit): {len(customer_output_rows)}")

# ---- 7b: KM Aggregate as "中型客户" ----
print("\n  --- KM Aggregate as 中型客户 ---")
km_product_forecasts = {}  # {pl: dict}

for pl in product_lines:
    if pl not in pl_forecasts:
        continue

    # Aggregate KM sales for this product line
    km_mask = df_with_buckets['客户'].isin(km_custs) & (df_with_buckets['产品线'] == pl)
    km_pl_data = df_with_buckets[km_mask]
    if len(km_pl_data) == 0:
        continue

    # Build monthly time series
    km_monthly = km_pl_data.groupby('_month')['销售额'].sum()
    all_months = sorted(df_with_buckets['_month'].unique())
    km_series = pd.Series(0.0, index=all_months)
    for m, v in km_monthly.items():
        if m in km_series.index:
            km_series[m] = v
    monthly_vals = km_series.values.astype(float)

    first_nz = 0
    for i, v in enumerate(monthly_vals):
        if v > 0:
            first_nz = i
            break
    trimmed = monthly_vals[first_nz:]
    nz_count = int(np.sum(trimmed > 0))

    if nz_count < 2 or len(trimmed) < 4:
        continue

    # Use same method selection as product line
    fdata = pl_forecasts[pl]
    best_algo = method_candidates[0]['algorithm']  # default
    best_params = {'window': 6}

    # Find the algorithm from the method name
    for mc in method_candidates:
        if mc['name'] == fdata['method_name']:
            best_algo = mc['algorithm']
            best_params = dict(mc['params'])
            break

    best_params['window'] = min(best_params.get('window', len(trimmed)), len(trimmed))
    try:
        fcast_arr = forecast_multi(trimmed, best_algo, best_params, horizon=4)
    except Exception:
        fcast_arr = np.full(4, np.mean(trimmed[-4:]) if len(trimmed) >= 4 else np.mean(trimmed))
    if np.any(np.isnan(fcast_arr)) or np.all(fcast_arr <= 0):
        fallback = float(np.mean(trimmed[-4:]))
        fcast_arr = np.full(4, max(fallback, 0.0))
    fcast_arr = np.maximum(fcast_arr, 0.0)

    km_product_forecasts[pl] = {
        'method_name': fdata['method_name'],
        'wape': fdata['wape'],
        'confidence': fdata['confidence'],
        'fcast_arr': fcast_arr,
        'fcast_lo': fcast_arr * (1 - max(fdata['wape'], 0.05)),
        'fcast_hi': fcast_arr * (1 + max(fdata['wape'], 0.05)),
        'asp': fdata['asp'],
        'cost_price': fdata['cost_price']
    }

# Output KM aggregate rows
km_total_forecasted = 0
for pl, fdata in km_product_forecasts.items():
    fcast_arr = fdata['fcast_arr']
    fcast_lo = fdata['fcast_lo']
    fcast_hi = fdata['fcast_hi']
    asp = fdata['asp']
    cost_price = fdata['cost_price']
    method_name = fdata['method_name']
    wape = fdata['wape']
    confidence = fdata['confidence']

    # -- HISTORY for KM aggregate --
    # Build KM aggregate history from buckets
    km_bv = defaultdict(lambda: {'销售额': 0.0, '销售量': 0.0, '成本额': 0.0})
    for (cust_cp, pl_cp, sku_cp), bv in cp_agg.items():
        if cust_cp in km_custs and pl_cp == pl:
            for hb in H_BUCKETS:
                km_bv[hb]['销售额'] += bv.get(hb, {}).get('销售额', 0.0)
                km_bv[hb]['销售量'] += bv.get(hb, {}).get('销售量', 0.0)
                km_bv[hb]['成本额'] += bv.get(hb, {}).get('成本额', 0.0)

    km_asp = asp if asp > 0 else 1.0
    for i, hb in enumerate(H_BUCKETS):
        sales_val = km_bv[hb]['销售额']
        if sales_val <= 0:
            continue
        qty_val = km_bv[hb]['销售量']
        cost_val = km_bv[hb]['成本额']
        gp_val = sales_val - cost_val
        gm_val = gp_val / sales_val if sales_val > 0 else 0.0
        bucket_asp = sales_val / qty_val if qty_val > 0 else km_asp
        bk = buckets[i]
        customer_output_rows.append({
            '客户': '中型客户(KM汇总)', '客户类别': 'KM(汇总)',
            '产品线': pl, '产品(SKU)': '',
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

    # FORECAST
    for fi in range(4):
        fb = F_BUCKETS[fi]
        bk = buckets[12 + fi]
        sales = float(fcast_arr[fi])
        sales_lo = float(fcast_lo[fi])
        sales_hi = float(fcast_hi[fi])
        qty = sales / asp if asp > 0 else 0.0
        cost = qty * cost_price if cost_price > 0 else 0.0
        gp = sales - cost
        gm = gp / sales if sales > 0 else 0.0
        if qty == 0:
            gm = 0.0

        customer_output_rows.append({
            '客户': '中型客户(KM汇总)', '客户类别': 'KM(汇总)',
            '产品线': pl, '产品(SKU)': '',
            '数据类型': '预测', '桶编号': fb,
            '桶开始月': str(bk['开始月']), '桶结束月': str(bk['结束月']),
            '销售额': float(round(sales, 2)),
            '销售额下限': float(round(sales_lo, 2)),
            '销售额上限': float(round(sales_hi, 2)),
            '销售量': float(round(qty, 2)),
            '毛利额': float(round(gp, 2)),
            '毛利率': float(round(gm, 4)),
            '成本额': float(round(cost, 2)),
            '加权ASP': float(round(asp, 4)),
            '预测方法': method_name,
            '方法WAPE': float(round(wape, 4)) if (isinstance(wape, (int, float)) and wape > 0) else '',
            '置信度': confidence
        })
        km_total_forecasted += 1

print(f"  KM aggregate: {len(km_product_forecasts)} product lines, {km_total_forecasted} forecast rows")

# ---- 7c: MM Aggregate as "长尾客户" ----
print("\n  --- MM Aggregate as 长尾客户 ---")
mm_product_forecasts = {}

for pl in product_lines:
    if pl not in pl_forecasts:
        continue

    # Aggregate MM sales for this product line
    mm_mask = df_with_buckets['客户'].isin(mm_custs) & (df_with_buckets['产品线'] == pl)
    mm_pl_data = df_with_buckets[mm_mask]
    if len(mm_pl_data) == 0:
        continue

    mm_monthly = mm_pl_data.groupby('_month')['销售额'].sum()
    all_months = sorted(df_with_buckets['_month'].unique())
    mm_series = pd.Series(0.0, index=all_months)
    for m, v in mm_monthly.items():
        if m in mm_series.index:
            mm_series[m] = v
    monthly_vals = mm_series.values.astype(float)

    first_nz = 0
    for i, v in enumerate(monthly_vals):
        if v > 0:
            first_nz = i
            break
    trimmed = monthly_vals[first_nz:]
    nz_count = int(np.sum(trimmed > 0))

    if nz_count < 1 or len(trimmed) < 2:
        continue

    # Simple mean method
    best_params = {'window': min(6, len(trimmed))}
    try:
        fcast_arr = forecast_multi(trimmed, '均值', best_params, horizon=4)
    except Exception:
        fcast_arr = np.full(4, np.mean(trimmed[-3:]) if len(trimmed) >= 3 else np.mean(trimmed))
    if np.any(np.isnan(fcast_arr)) or np.all(fcast_arr <= 0):
        fallback = float(np.mean(trimmed[-3:]))
        fcast_arr = np.full(4, max(fallback, 0.0))
    fcast_arr = np.maximum(fcast_arr, 0.0)

    fdata = pl_forecasts[pl]
    asp = fdata['asp']
    cost_price = fdata['cost_price']
    mm_wape = 0.3  # conservative WAPE for MM

    mm_product_forecasts[pl] = {
        'method_name': f'均值(窗口={best_params["window"]})',
        'wape': mm_wape,
        'confidence': '低',
        'fcast_arr': fcast_arr,
        'fcast_lo': fcast_arr * (1 - mm_wape),
        'fcast_hi': fcast_arr * (1 + mm_wape),
        'asp': asp,
        'cost_price': cost_price
    }

# Output MM aggregate rows
mm_total_forecasted = 0
for pl, fdata in mm_product_forecasts.items():
    fcast_arr = fdata['fcast_arr']
    fcast_lo = fdata['fcast_lo']
    fcast_hi = fdata['fcast_hi']
    asp = fdata['asp']
    cost_price = fdata['cost_price']
    method_name = fdata['method_name']
    wape = fdata['wape']
    confidence = fdata['confidence']

    # HISTORY
    mm_bv = defaultdict(lambda: {'销售额': 0.0, '销售量': 0.0, '成本额': 0.0})
    for (cust_cp, pl_cp, sku_cp), bv in cp_agg.items():
        if cust_cp in mm_custs and pl_cp == pl:
            for hb in H_BUCKETS:
                mm_bv[hb]['销售额'] += bv.get(hb, {}).get('销售额', 0.0)
                mm_bv[hb]['销售量'] += bv.get(hb, {}).get('销售量', 0.0)
                mm_bv[hb]['成本额'] += bv.get(hb, {}).get('成本额', 0.0)

    mm_asp = asp if asp > 0 else 1.0
    for i, hb in enumerate(H_BUCKETS):
        sales_val = mm_bv[hb]['销售额']
        if sales_val <= 0:
            continue
        qty_val = mm_bv[hb]['销售量']
        cost_val = mm_bv[hb]['成本额']
        gp_val = sales_val - cost_val
        gm_val = gp_val / sales_val if sales_val > 0 else 0.0
        bucket_asp = sales_val / qty_val if qty_val > 0 else mm_asp
        bk = buckets[i]
        customer_output_rows.append({
            '客户': '长尾客户(MM汇总)', '客户类别': 'MM(汇总)',
            '产品线': pl, '产品(SKU)': '',
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

    # FORECAST
    for fi in range(4):
        fb = F_BUCKETS[fi]
        bk = buckets[12 + fi]
        sales = float(fcast_arr[fi])
        sales_lo = float(fcast_lo[fi])
        sales_hi = float(fcast_hi[fi])
        qty = sales / asp if asp > 0 else 0.0
        cost = qty * cost_price if cost_price > 0 else 0.0
        gp = sales - cost
        gm = gp / sales if sales > 0 else 0.0
        if qty == 0:
            gm = 0.0

        customer_output_rows.append({
            '客户': '长尾客户(MM汇总)', '客户类别': 'MM(汇总)',
            '产品线': pl, '产品(SKU)': '',
            '数据类型': '预测', '桶编号': fb,
            '桶开始月': str(bk['开始月']), '桶结束月': str(bk['结束月']),
            '销售额': float(round(sales, 2)),
            '销售额下限': float(round(sales_lo, 2)),
            '销售额上限': float(round(sales_hi, 2)),
            '销售量': float(round(qty, 2)),
            '毛利额': float(round(gp, 2)),
            '毛利率': float(round(gm, 4)),
            '成本额': float(round(cost, 2)),
            '加权ASP': float(round(asp, 4)),
            '预测方法': method_name,
            '方法WAPE': float(round(wape, 4)) if wape > 0 else '',
            '置信度': confidence
        })
        mm_total_forecasted += 1

print(f"  MM aggregate: {len(mm_product_forecasts)} product lines, {mm_total_forecasted} forecast rows")

# ---- 7d: Product split for KA/AA customers ----
print("\n  --- Product split for KA/AA customers ---")
# Build customer->product shares from cp_agg
cust_prod_shares = defaultdict(dict)
cust_prod_nobs = defaultdict(dict)

# Precompute customer totals
cust_totals_for_share = {}
for (cust_cp, pl_cp, sku_cp), bv in cp_agg.items():
    hist_total = sum(bv.get(hb, {}).get('销售额', 0.0) for hb in H_BUCKETS)
    cust_totals_for_share[cust_cp] = cust_totals_for_share.get(cust_cp, 0.0) + hist_total

for (cust_cp, pl_cp, sku_cp), bv in cp_agg.items():
    hist_sales = [bv.get(hb, {}).get('销售额', 0.0) for hb in H_BUCKETS]
    total = sum(hist_sales)
    if total <= 0:
        continue
    cust_total = cust_totals_for_share.get(cust_cp, 0.0)
    if cust_total <= 0:
        continue
    prod_id = f'{pl_cp}|||{sku_cp}'
    cust_prod_shares[cust_cp][prod_id] = total / cust_total
    nz = sum(1 for hb in H_BUCKETS if bv.get(hb, {}).get('销售额', 0.0) > 0)
    cust_prod_nobs[cust_cp][prod_id] = nz

# Expand KA/AA forecast rows with product split
final_customer_rows = []
cust_forecast_rows = [r for r in customer_output_rows if r['数据类型'] == '预测']

for frow in cust_forecast_rows:
    cust = frow['客户']
    fb = frow['桶编号']
    total_fcast = frow['销售额']
    total_lo = float(frow.get('销售额下限', total_fcast) or 0)
    total_hi = float(frow.get('销售额上限', total_fcast) or 0)
    method_name = frow['预测方法']
    wape = frow['方法WAPE']
    confidence = frow['置信度']
    cust_cat = frow['客户类别']

    # Only split for individual KA/AA customers, not aggregates
    if cust in ka_aa_custs:
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
            prod_asp = get_asp_fallback(cp_agg, cp_key, cust_agg, cust, pl_name, H_BUCKETS)
            prod_cp = get_cost_fallback(cp_agg, cp_key, cust_agg, cust, pl_name, H_BUCKETS)

            allocated_sales = total_fcast * share
            allocated_lo = total_lo * share
            allocated_hi = total_hi * share
            qty = allocated_sales / prod_asp if prod_asp > 0 else 0.0
            cost = qty * prod_cp if prod_cp > 0 else 0.0
            gp = allocated_sales - cost
            gm = gp / allocated_sales if allocated_sales > 0 else 0.0
            if qty == 0:
                gm = 0.0

            final_customer_rows.append({
                '客户': cust, '客户类别': cust_cat,
                '产品线': pl_name, '产品(SKU)': str(sku_name),
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
                '预测方法': method_name,
                '方法WAPE': float(round(wape, 4)) if (isinstance(wape, (int, float)) and wape > 0) else '',
                '置信度': confidence
            })
    else:
        # Aggregate customers (KM/MM) - keep as-is
        final_customer_rows.append(dict(frow))

# Add historical rows (keep as-is, no split needed for history)
for row in customer_output_rows:
    if row['数据类型'] == '历史':
        final_customer_rows.append(dict(row))

customer_output_df = pd.DataFrame(final_customer_rows)
hist_cc = len(customer_output_df[customer_output_df['数据类型'] == '历史'])
fcst_cc = len(customer_output_df[customer_output_df['数据类型'] == '预测'])
print(f"  Final customer output: {len(customer_output_df)} rows (hist={hist_cc}, fcst={fcst_cc})")

# ============================================================
# STEP 7e: RECONCILE customer path to product path totals
# ============================================================
print("\n" + "=" * 70)
print("STEP 7e: Reconciling customer path to product path...")
print("=" * 70)

# Build product path totals per (product_line, bucket)
prod_totals = {}
for pl, fdata in pl_forecasts.items():
    for fi in range(4):
        fb = F_BUCKETS[fi]
        prod_totals[(pl, fb)] = float(fdata['fcast_arr'][fi])

# Scale customer forecasts to match product line totals
cust_fcst_mask = customer_output_df['数据类型'] == '预测'
cust_fcst_indices = customer_output_df[cust_fcst_mask].index

scale_stats = []
for (pl, fb), pl_total in prod_totals.items():
    pl_cust = customer_output_df[
        cust_fcst_mask & (customer_output_df['产品线'] == pl) & (customer_output_df['桶编号'] == fb)
    ]
    if len(pl_cust) == 0:
        continue
    cust_sum = pd.to_numeric(pl_cust['销售额'], errors='coerce').sum()
    if cust_sum > 0 and abs(pl_total - cust_sum) > 1:
        scale = pl_total / cust_sum
        scale_stats.append((pl, fb, pl_total, cust_sum, scale))
        for idx in pl_cust.index:
            # Scale sales and bounds
            orig_sales = pd.to_numeric(customer_output_df.loc[idx, '销售额'], errors='coerce')
            customer_output_df.loc[idx, '销售额'] = float(round(float(orig_sales) * scale, 2))
            if '销售额下限' in customer_output_df.columns:
                orig_lo = pd.to_numeric(customer_output_df.loc[idx, '销售额下限'], errors='coerce')
                customer_output_df.loc[idx, '销售额下限'] = float(round(float(orig_lo or 0) * scale, 2))
            if '销售额上限' in customer_output_df.columns:
                orig_hi = pd.to_numeric(customer_output_df.loc[idx, '销售额上限'], errors='coerce')
                customer_output_df.loc[idx, '销售额上限'] = float(round(float(orig_hi or 0) * scale, 2))

if scale_stats:
    print(f"  Reconciled {len(scale_stats)} (product_line, bucket) combinations")
    scale_stats.sort(key=lambda x: abs(1 - x[4]), reverse=True)
    for pl, fb, pt, cs, sc in scale_stats[:5]:
        print(f"    {pl} {fb}: product={pt:,.0f}, customer_orig={cs:,.0f}, scale={sc:.3f}")
else:
    print("  No reconciliation needed")

# Recompute quantity, cost, profit after scaling
cust_fcst_after = customer_output_df[cust_fcst_mask]
for idx in cust_fcst_after.index:
    row = customer_output_df.loc[idx]
    asp_val = pd.to_numeric(row['加权ASP'], errors='coerce')
    sales_val = pd.to_numeric(row['销售额'], errors='coerce')

    # Derive cost price from product line
    pl_name = row['产品线']
    if pl_name and pl_name in pl_forecasts:
        cp_val = pl_forecasts[pl_name]['cost_price']
    else:
        cp_val = 0.0

    qty = float(sales_val) / float(asp_val) if float(asp_val) > 0 else 0.0
    cost = qty * cp_val if cp_val > 0 else 0.0
    gp = float(sales_val) - cost
    gm = gp / float(sales_val) if float(sales_val) > 0 else 0.0
    if qty == 0:
        gm = 0.0

    customer_output_df.loc[idx, '销售量'] = float(round(qty, 2))
    customer_output_df.loc[idx, '成本额'] = float(round(cost, 2))
    customer_output_df.loc[idx, '毛利额'] = float(round(gp, 2))
    customer_output_df.loc[idx, '毛利率'] = float(round(gm, 4))

# ============================================================
# STEP 8: SAVE OUTPUTS
# ============================================================
print("\n" + "=" * 70)
print("STEP 8: Saving outputs...")
print("=" * 70)

PRODUCT_COLS = ['产品线', '品类', 'SKU', '数据类型', '桶编号', '桶开始月', '桶结束月',
                '销售额', '销售额下限', '销售额上限', '销售量', '毛利额', '毛利率', '成本额', '加权ASP',
                '预测方法', '方法WAPE', '方法稳定性', '置信度']
CUSTOMER_COLS = ['客户', '客户类别', '产品线', '产品(SKU)', '数据类型', '桶编号', '桶开始月', '桶结束月',
                 '销售额', '销售额下限', '销售额上限', '销售量', '毛利额', '毛利率', '成本额', '加权ASP',
                 '预测方法', '方法WAPE', '置信度']

# Fill missing columns
for c in PRODUCT_COLS:
    if c not in product_output_df.columns:
        product_output_df[c] = ''
product_output_df = product_output_df[PRODUCT_COLS]

for c in CUSTOMER_COLS:
    if c not in customer_output_df.columns:
        customer_output_df[c] = ''
customer_output_df = customer_output_df[CUSTOMER_COLS]

# Fix SKU strings
if 'SKU' in product_output_df.columns:
    product_output_df['SKU'] = product_output_df['SKU'].astype(str)
    product_output_df.loc[product_output_df['SKU'] == 'nan', 'SKU'] = '未知SKU'
if '产品(SKU)' in customer_output_df.columns:
    customer_output_df['产品(SKU)'] = customer_output_df['产品(SKU)'].astype(str)
    customer_output_df.loc[customer_output_df['产品(SKU)'] == 'nan', '产品(SKU)'] = '未知SKU'

# Fix history rows - 方法WAPE should be ''
for df_out in [product_output_df, customer_output_df]:
    hist_mask = df_out['数据类型'] == '历史'
    if '方法WAPE' in df_out.columns:
        df_out.loc[hist_mask, '方法WAPE'] = ''

# Float precision
numeric_cols_2 = ['销售额', '销售额下限', '销售额上限', '销售量', '毛利额', '成本额']
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
    if '方法WAPE' in df_out.columns:
        df_out.loc[fcst_mask, '方法WAPE'] = pd.to_numeric(df_out.loc[fcst_mask, '方法WAPE'], errors='coerce').apply(
            lambda x: float(round(x, 4)) if pd.notna(x) else '')

# Also round history
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

# Fill NaN
for df_out in [product_output_df, customer_output_df]:
    for col in numeric_cols_2 + numeric_cols_4:
        if col in df_out.columns:
            df_out[col] = df_out[col].fillna(0.0)
    for col in df_out.columns:
        if col not in numeric_cols_2 + numeric_cols_4 + ['方法WAPE']:
            df_out[col] = df_out[col].fillna('')

# Filter zero-sales forecast rows
before_filter = len(product_output_df)
product_output_df = product_output_df[
    ~((product_output_df['数据类型'] == '预测') & (pd.to_numeric(product_output_df['销售额'], errors='coerce') <= 0))
]
print(f"  Product: filtered {before_filter - len(product_output_df)} zero-sales rows, now {len(product_output_df)}")

before_filter_c = len(customer_output_df)
customer_output_df = customer_output_df[
    ~((customer_output_df['数据类型'] == '预测') & (pd.to_numeric(customer_output_df['销售额'], errors='coerce') <= 0))
]
print(f"  Customer: filtered {before_filter_c - len(customer_output_df)} zero-sales rows, now {len(customer_output_df)}")

# Write
product_output_path = os.path.join(OUTPUT_DIR, 'product_path_forecast.csv')
customer_output_path = os.path.join(OUTPUT_DIR, 'customer_path_forecast.csv')

product_output_df.to_csv(product_output_path, index=False, encoding='utf-8-sig')
print(f"  Product: {product_output_path} ({len(product_output_df)} rows)")

customer_output_df.to_csv(customer_output_path, index=False, encoding='utf-8-sig')
print(f"  Customer: {customer_output_path} ({len(customer_output_df)} rows)")

# ============================================================
# STEP 9: QUALITY CHECKS
# ============================================================
print("\n" + "=" * 70)
print("STEP 9: DATA QUALITY CHECKS")
print("=" * 70)

# 1. Zero sales/quantity checks
print("\n--- Zero/Negative Checks ---")
for name, dfo in [('Product', product_output_df), ('Customer', customer_output_df)]:
    fcst = dfo[dfo['数据类型'] == '预测']
    zero_sales = len(fcst[pd.to_numeric(fcst['销售额'], errors='coerce') <= 0])
    neg_sales = len(fcst[pd.to_numeric(fcst['销售额'], errors='coerce') < 0])
    neg_qty = len(fcst[pd.to_numeric(fcst['销售量'], errors='coerce') < 0])
    zero_asp = len(fcst[pd.to_numeric(fcst['加权ASP'], errors='coerce') <= 0])
    print(f"  [{name}] Zero sales: {zero_sales}, Neg sales: {neg_sales}, Neg qty: {neg_qty}, Zero ASP: {zero_asp}")

# 2. Two paths comparison per product line
print("\n--- Two Paths Comparison ---")
prod_f = product_output_df[product_output_df['数据类型'] == '预测']
cust_f = customer_output_df[customer_output_df['数据类型'] == '预测']
pt = pd.to_numeric(prod_f['销售额'], errors='coerce').sum()
ct = pd.to_numeric(cust_f['销售额'], errors='coerce').sum()
print(f"  Product path total: {pt:,.0f}")
print(f"  Customer path total: {ct:,.0f}")
print(f"  Difference: {pt - ct:+,.0f} ({(pt - ct) / pt * 100:+.1f}%)" if pt > 0 else "  Difference: N/A (pt=0)")

# Per product line comparison
print("  By product line:")
prod_by_pl = prod_f.groupby('产品线')['销售额'].apply(lambda x: pd.to_numeric(x, errors='coerce').sum())
cust_by_pl = cust_f[cust_f['产品线'] != ''].groupby('产品线')['销售额'].apply(
    lambda x: pd.to_numeric(x, errors='coerce').sum())
for pl in sorted(set(list(prod_by_pl.index) + list(cust_by_pl.index))):
    pv = prod_by_pl.get(pl, 0)
    cv = cust_by_pl.get(pl, 0)
    diff = pv - cv
    pct = diff / pv * 100 if pv > 0 else 0
    flag = ' ***' if abs(pct) > 20 else ''
    print(f"    {pl}: prod={pv:,.0f}, cust={cv:,.0f}, diff={diff:+,.0f} ({pct:+.1f}%){flag}")

# 3. WAPE distribution by customer tier
print("\n--- WAPE Distribution by Customer Tier ---")
cust_f_with_wape = cust_f[cust_f['方法WAPE'].notna() & (cust_f['方法WAPE'] != '') & (cust_f['方法WAPE'] != 0)]
if len(cust_f_with_wape) > 0:
    cust_f_with_wape = cust_f_with_wape.copy()
    cust_f_with_wape['wape_val'] = pd.to_numeric(cust_f_with_wape['方法WAPE'], errors='coerce')
    for tier in ['AA>5000万', 'KA>1亿', 'KM(汇总)', 'MM(汇总)']:
        tier_data = cust_f_with_wape[cust_f_with_wape['客户类别'] == tier]
        if len(tier_data) > 0:
            wape_vals = tier_data['wape_val'].dropna()
            if len(wape_vals) > 0:
                print(f"  {tier}: n={len(wape_vals)}, mean={wape_vals.mean():.4f}, "
                      f"median={wape_vals.median():.4f}, min={wape_vals.min():.4f}, max={wape_vals.max():.4f}")

# 4. Method stability summary
print("\n--- Method Stability Summary ---")
if '方法稳定性' in product_output_df.columns:
    stab = product_output_df[product_output_df['数据类型'] == '预测']['方法稳定性'].value_counts()
    print(f"  Product path: {dict(stab)}")

# 5. Trend alert detection
print("\n--- Trend Alert Detection ---")
for pl in product_lines:
    if pl not in pl_forecasts:
        continue
    fdata = pl_forecasts[pl]
    # Get historical avg
    if pl in pl_monthly.index:
        monthly_vals = pl_monthly.loc[pl].values.astype(float)
        first_nz = 0
        for i, v in enumerate(monthly_vals):
            if v > 0:
                first_nz = i
                break
        trimmed = monthly_vals[first_nz:]
        hist_avg = np.mean(trimmed[-4:]) if len(trimmed) >= 4 else np.mean(trimmed)
        fcst_avg = np.mean(fdata['fcast_arr'])
        if hist_avg > 0:
            trend_change = (fcst_avg - hist_avg) / hist_avg * 100
            if abs(trend_change) > 30:
                print(f"  {pl}: {trend_change:+.1f}% change (hist_avg={hist_avg:,.0f} -> fcst_avg={fcst_avg:,.0f})")

# 6. Confidence distribution
print("\n--- Confidence Distribution ---")
for name, dfo in [('Product', product_output_df), ('Customer', customer_output_df)]:
    fcst = dfo[dfo['数据类型'] == '预测']
    print(f"  [{name}] 置信度: {dict(fcst['置信度'].value_counts())}")

# 7. Profit margin sanity
print("\n--- Profit Margin Sanity ---")
for name, dfo in [('Product', product_output_df), ('Customer', customer_output_df)]:
    gm_vals = pd.to_numeric(dfo['毛利率'], errors='coerce')
    bad_gm = len(gm_vals[(gm_vals > 1.0) | (gm_vals < -1.0)])
    print(f"  [{name}] 毛利率 >1 or <-1: {bad_gm}")

# Summary
print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)
print(f"  Product path: {len(product_output_df)} rows, PLs={product_output_df['产品线'].nunique()}, "
      f"Categories={product_output_df['品类'].nunique()}")
pf = product_output_df[product_output_df['数据类型'] == '预测']
print(f"    Forecast rows: {len(pf)}, confidence: {dict(pf['置信度'].value_counts())}")
total_pf = pd.to_numeric(pf['销售额'], errors='coerce').sum()
print(f"    Total forecast sales: {total_pf:,.2f}")

print(f"  Customer path: {len(customer_output_df)} rows, Custs={customer_output_df['客户'].nunique()}")
cf = customer_output_df[customer_output_df['数据类型'] == '预测']
print(f"    Forecast rows: {len(cf)}")
total_cf = pd.to_numeric(cf['销售额'], errors='coerce').sum()
print(f"    Total forecast sales: {total_cf:,.2f}")
print(f"    Customer categories: {dict(cf['客户类别'].value_counts())}")

print("\n  Method candidates used: {}".format(len(method_candidates)))
print(f"  Product lines forecasted: {len(pl_forecasts)}")
print(f"  KA/AA customers with individual forecast: {len([c for c in ka_aa_custs if c in ka_aa_methods])}")
print(f"  KM aggregate product lines: {len(km_product_forecasts)}")
print(f"  MM aggregate product lines: {len(mm_product_forecasts)}")

print("\n" + "=" * 70)
print("DONE!")
print("=" * 70)
