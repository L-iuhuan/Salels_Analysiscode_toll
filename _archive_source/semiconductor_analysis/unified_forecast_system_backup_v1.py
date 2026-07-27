# -*- coding: utf-8 -*-
"""
Unified Forecast System - Optimized Rebuild
3-month sliding buckets (NOT natural quarters)
"""

import numpy as np
import pandas as pd
from python_calamine import CalamineWorkbook
from scipy import stats
from collections import defaultdict
import warnings
import os
import re
from datetime import datetime

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
# 1. DATA LOADING
# ============================================================
print("=" * 60)
print("STEP 1: Loading data...")
print("=" * 60)

wb = CalamineWorkbook.from_path(DATA_FILE)
sheet = wb.get_sheet_by_name(SHEET_NAME)
rows = list(sheet.to_python())
headers = rows[0]

data = {str(h) if h else f"col_{i}": [r[i] for r in rows[1:]] for i, h in enumerate(headers)}
df = pd.DataFrame(data)
print(f"  Loaded {len(df):,} rows, {len(df.columns)} columns")

# ============================================================
# 2. FIELD MAPPING
# ============================================================
print("\nSTEP 2: Field mapping...")

col_names = list(df.columns)
ship_date_col = col_names[0]
product_line_col = col_names[24]
category_col = col_names[26]
material_code_col = col_names[57]
model_col = col_names[9]
end_customer_short_col = col_names[7]
distributor_col = col_names[5]
actual_end_customer_col = col_names[6]
customer_col = col_names[36]
customer_category_col = col_names[63]
sales_amount_col = col_names[15]

df['发货日期'] = pd.to_datetime(df[ship_date_col], errors='coerce')
df['产品线'] = df[product_line_col].fillna('未分类')
df.loc[df['产品线'] == 'PMIC', '产品线'] = '未分类'
df.loc[df['产品线'] == '', '产品线'] = '未分类'
df.loc[df['产品线'].isna(), '产品线'] = '未分类'
df['品类'] = df[category_col].fillna('未知品类')
df.loc[df['品类'] == '', '品类'] = '未知品类'
df.loc[df['品类'].isna(), '品类'] = '未知品类'
df['SKU'] = df[material_code_col].fillna(df[model_col]).fillna('未知SKU')
df.loc[df['SKU'] == '', 'SKU'] = '未知SKU'
df.loc[df['SKU'].isna(), 'SKU'] = '未知SKU'
df['客户'] = df[end_customer_short_col].fillna(df[distributor_col]).fillna(df[actual_end_customer_col]).fillna('未知客户')
df.loc[df['客户'] == '', '客户'] = '未知客户'
df.loc[df['客户'].isna(), '客户'] = '未知客户'
df['客户类别'] = df[customer_category_col].fillna('MM<1000万')
df.loc[df['客户类别'] == '', '客户类别'] = 'MM<1000万'
df.loc[df['客户类别'].isna(), '客户类别'] = 'MM<1000万'
df['销售额'] = pd.to_numeric(df[sales_amount_col], errors='coerce').fillna(0)

df = df.dropna(subset=['发货日期'])
df = df[df['销售额'] > 0].copy()

print(f"  Clean: {len(df):,} rows, PL:{df['产品线'].nunique()}, Cust:{df['客户'].nunique()}")

# ============================================================
# 3. BUCKET BUILDING
# ============================================================
print("\nSTEP 3: Building 3-month sliding buckets...")

df['_月'] = df['发货日期'].dt.to_period('M')
latest_month = df['_月'].max()


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


# Pre-compute bucket masks for fast aggregation
def get_bucket_mask(df, b):
    start_date = pd.Timestamp(b['开始月'].start_time.date())
    end_date = pd.Timestamp(b['结束月'].end_time.date())
    return (df['发货日期'] >= start_date) & (df['发货日期'] <= end_date)


# ============================================================
# 4. FAST AGGREGATION
# ============================================================
print("\nSTEP 4: Aggregating data into buckets...")

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


def fast_aggregate(df, group_cols):
    """Fast groupby aggregation returning dict of {(group_key): {bucket: value}}."""
    groups = df.groupby(group_cols + ['_bucket'])['销售额'].sum()
    result = defaultdict(lambda: defaultdict(float))
    for idx, val in groups.items():
        if len(group_cols) == 1:
            key = idx[0]
            bucket = idx[1]
        else:
            key = tuple(idx[:len(group_cols)])
            bucket = idx[len(group_cols)]
        result[key][bucket] = val
    return result


# Aggregate at different levels
pl_agg = fast_aggregate(df_with_buckets, ['产品线'])
cat_agg = fast_aggregate(df_with_buckets, ['产品线', '品类'])
sku_agg = fast_aggregate(df_with_buckets, ['产品线', '品类', 'SKU'])
cust_agg = fast_aggregate(df_with_buckets, ['客户'])
cp_agg = fast_aggregate(df_with_buckets, ['客户', '产品线', 'SKU'])

print(f"  Product line aggregates: {len(pl_agg)}")
print(f"  Category aggregates: {len(cat_agg)}")
print(f"  SKU aggregates: {len(sku_agg)}")
print(f"  Customer aggregates: {len(cust_agg)}")
print(f"  Customer-Product aggregates: {len(cp_agg)}")


def agg_to_series(agg_dict, key):
    """Convert aggregate dict key to pandas Series of H01-H12 buckets."""
    bucket_vals = agg_dict.get(key, {})
    all_h = [f'H{i+1:02d}' for i in range(12)]
    return pd.Series([bucket_vals.get(h, 0.0) for h in all_h], index=all_h)


# ============================================================
# 5. METHOD POOL (Reduced for performance)
# ============================================================
print("\nSTEP 5: Building method pool...")


def forecast_single(data_array, algo_name, params):
    """Compute a single forecast given array of historical values."""
    window = min(params.get('window', len(data_array)), len(data_array))
    if window == 0:
        return np.nan
    vals = data_array[-window:].astype(float)

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
        return max(0.0, float(intercept + slope * len(vals)))
    elif algo_name == '对数线性趋势':
        if len(vals) < 2:
            return float(vals[-1])
        x = np.arange(len(vals), dtype=float)
        pos = np.maximum(vals, 1e-10)
        slope, intercept, _, _, _ = stats.linregress(x, np.log(pos))
        return max(0.0, float(np.exp(intercept + slope * len(vals))))
    elif algo_name == '漂移':
        if len(vals) < 2:
            return float(vals[-1])
        drift_val = np.mean(np.diff(vals))
        return max(0.0, float(vals[-1] + drift_val))
    elif algo_name == '同比季节':
        lag = params.get('season_lag', 4)
        gw = params.get('growth_window', 4)
        full_data = data_array
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
        return max(0.0, sv * gf)
    elif algo_name == '衰减趋势':
        dr = params.get('decay_rate', 0.7)
        if len(vals) < 2:
            return float(vals[-1])
        trend = np.mean(np.diff(vals))
        if trend > 0:
            return float(vals[-1] + trend * dr)
        return max(0.0, float(vals[-1] * dr))
    elif algo_name == '保守增长':
        gr = params.get('growth_rate', 0.05)
        return float(np.mean(vals) * (1 + gr))
    elif algo_name == '保守衰减':
        dr = params.get('decay_rate', 0.05)
        return max(0.0, float(np.mean(vals) * (1 - dr)))
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


def build_method_candidates():
    """Build method candidates with reduced parameter sweeps for performance."""
    candidates = []
    windows = [1, 2, 3, 4, 6, 8, 12]  # 7 windows (removed 10)

    simple = ['最近值', '均值', '中位数', '线性加权均值', '线性趋势', '对数线性趋势', '漂移', '组合中位数']
    for m in simple:
        for w in windows:
            candidates.append({'name': f'{m}(窗口={w})', 'algorithm': m, 'params': {'window': w}})

    # 指数加权均值: reduce to 7 windows x 3 alphas = 21
    for w in windows:
        for alpha in [0.2, 0.5, 0.85]:
            candidates.append({'name': f'指数加权均值(窗口={w},alpha={alpha})', 'algorithm': '指数加权均值',
                              'params': {'window': w, 'alpha': alpha}})

    # Croston: 7 windows x 3 alphas = 21
    for w in windows:
        for alpha in [0.2, 0.5, 0.85]:
            candidates.append({'name': f'Croston(窗口={w},alpha={alpha})', 'algorithm': 'Croston',
                              'params': {'window': w, 'alpha': alpha}})

    # 衰减趋势: 7 windows x 2 decays = 14
    for w in windows:
        for d in [0.4, 0.9]:
            candidates.append({'name': f'衰减趋势(窗口={w},衰减={d})', 'algorithm': '衰减趋势',
                              'params': {'window': w, 'decay_rate': d}})

    # 保守增长: 7 windows x 2 rates = 14
    for w in windows:
        for r in [0.02, 0.10]:
            candidates.append({'name': f'保守增长(窗口={w},增长率={r})', 'algorithm': '保守增长',
                              'params': {'window': w, 'growth_rate': r}})

    # 保守衰减: 7 windows x 2 rates = 14
    for w in windows:
        for r in [0.02, 0.10]:
            candidates.append({'name': f'保守衰减(窗口={w},衰减率={r})', 'algorithm': '保守衰减',
                              'params': {'window': w, 'decay_rate': r}})

    # 同比季节
    for gw in [2, 4, 6]:
        candidates.append({'name': f'同比季节(窗口=12,季节滞后=4,增长窗口={gw})', 'algorithm': '同比季节',
                          'params': {'window': 12, 'season_lag': 4, 'growth_window': gw}})

    # 月度季节指数
    for sw in [24, 36]:
        candidates.append({'name': f'月度季节指数(窗口=12,季节窗口={sw})', 'algorithm': '月度季节指数',
                          'params': {'window': 12, 'seasonal_window': sw}})

    return candidates


method_candidates = build_method_candidates()
print(f"  Total method candidates: {len(method_candidates)}")

# ============================================================
# 6. VECTORIZED BACKTEST
# ============================================================
print("\nSTEP 6: Backtest engine...")


def calc_wape(actuals, forecasts):
    a = np.array(actuals, dtype=float)
    f = np.array(forecasts, dtype=float)
    mask = a > 0
    if mask.sum() == 0:
        return np.nan
    return float(np.sum(np.abs(a[mask] - f[mask])) / np.sum(a[mask]))


def fast_backtest(series_values, candidates, min_train=3):
    """
    Fast backtest using pre-computed series values.
    series_values: 1D numpy array of length <= 12
    Returns: list of (candidate_idx, wape) sorted by WAPE.
    """
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

            # Adjust window
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
# 7. PRODUCT PATH
# ============================================================
print("\nSTEP 7: Product Path forecasting...")

product_lines = sorted(df['产品线'].unique())
print(f"  Processing {len(product_lines)} product lines...")

pl_forecasts = {}  # {pl: (method_name, wape, [f01..f04 values])}
pl_all_results = []  # For output

for idx, pl in enumerate(product_lines):
    series = agg_to_series(pl_agg, pl)
    # Trim leading zeros
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

    # Forecast
    params = best_mc['params'].copy()
    params['window'] = min(params.get('window', len(trimmed)), len(trimmed))
    fcast_val = forecast_single(trimmed, best_mc['algorithm'], params)
    if np.isnan(fcast_val) or fcast_val < 0:
        fcast_val = float(np.mean(trimmed[-4:])) if len(trimmed) >= 4 else float(np.mean(trimmed))

    # Split to 4 buckets
    recent4 = trimmed[-4:] if len(trimmed) >= 4 else trimmed
    if recent4.sum() > 0:
        w = recent4 / recent4.sum()
    else:
        w = np.ones(len(recent4)) / len(recent4)
    if len(w) < 4:
        w = np.full(4, 0.25)

    f01_f04 = [max(0.0, float(fcast_val * w[i])) for i in range(4)]
    pl_forecasts[pl] = (best_name, best_wape, f01_f04)
    print(f"  [{idx+1}/{len(product_lines)}] {pl}: {best_name}, WAPE={best_wape:.4f}, F01={f01_f04[0]:.0f}")

# ============================================================
# 7b. SHRINKAGE: PL -> Category -> SKU
# ============================================================
print("\nSTEP 7b: Shrinkage allocation PL->Category->SKU...")


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


# Build PL->Category shares from historical H01-H12
# First compute PL totals
pl_totals = {}
for (pl, cat), bv in cat_agg.items():
    for i in range(12):
        pl_totals[pl] = pl_totals.get(pl, 0.0) + bv.get(f'H{i+1:02d}', 0.0)

pl_cat_raw = defaultdict(dict)
pl_cat_nobs = defaultdict(dict)
for (pl, cat), bv in cat_agg.items():
    hist_vals = [bv.get(f'H{i+1:02d}', 0.0) for i in range(12)]
    total_cat = sum(hist_vals)
    if total_cat <= 0:
        continue
    all_pl_hist = pl_totals.get(pl, 0.0)
    if all_pl_hist > 0:
        pl_cat_raw[pl][cat] = total_cat / all_pl_hist
    nz_buckets = sum(1 for i in range(12) if bv.get(f'H{i+1:02d}', 0.0) > 0)
    pl_cat_nobs[pl][cat] = nz_buckets

# Build Category->SKU shares
# First compute category totals
cat_totals = {}
for (pl, cat, sku), bv in sku_agg.items():
    key = (pl, cat)
    for i in range(12):
        cat_totals[key] = cat_totals.get(key, 0.0) + bv.get(f'H{i+1:02d}', 0.0)

cat_sku_raw = defaultdict(dict)
cat_sku_nobs = defaultdict(dict)
for (pl, cat, sku), bv in sku_agg.items():
    hist_vals = [bv.get(f'H{i+1:02d}', 0.0) for i in range(12)]
    total_sku = sum(hist_vals)
    if total_sku <= 0:
        continue
    all_cat_hist = cat_totals.get((pl, cat), 0.0)
    if all_cat_hist > 0:
        cat_sku_raw[(pl, cat)][sku] = total_sku / all_cat_hist
    nz_buckets = sum(1 for i in range(12) if bv.get(f'H{i+1:02d}', 0.0) > 0)
    cat_sku_nobs[(pl, cat)][sku] = nz_buckets

# Generate output rows
product_output_rows = []

# Add historical SKU rows
for (pl, cat, sku), bv in sku_agg.items():
    for i in range(12):
        hb = f'H{i+1:02d}'
        val = bv.get(hb, 0.0)
        if val > 0:
            bk = buckets[i]
            product_output_rows.append({
                '产品线': pl, '品类': cat, 'SKU': sku,
                '数据类型': '历史', '桶编号': hb,
                '桶开始月': str(bk['开始月']), '桶结束月': str(bk['结束月']),
                '销售额': float(val), '预测方法': '', '方法WAPE': '', '置信度': ''
            })

# Generate forecast rows with shrinkage
for pl, (method_name, wape, f01_f04) in pl_forecasts.items():
    confidence = '高' if wape <= 0.20 else ('中' if wape <= 0.45 else '低')
    cat_shares = pl_cat_raw.get(pl, {})
    cat_nobs_dict = pl_cat_nobs.get(pl, {})

    if not cat_shares:
        for fi in range(4):
            fb = f'F{fi+1:02d}'
            bk = buckets[12 + fi]
            product_output_rows.append({
                '产品线': pl, '品类': '未知品类', 'SKU': '未知SKU',
                '数据类型': '预测', '桶编号': fb,
                '桶开始月': str(bk['开始月']), '桶结束月': str(bk['结束月']),
                '销售额': round(f01_f04[fi], 2),
                '预测方法': method_name, '方法WAPE': float(wape), '置信度': confidence
            })
        continue

    shrunk_cat = shrinkage_share(cat_shares, cat_nobs_dict)
    for cat, cat_pct in shrunk_cat.items():
        cat_fcast = f01_f04[0] * cat_pct  # Use first bucket as base allocation
        sku_key = (pl, cat)
        sku_shares = cat_sku_raw.get(sku_key, {})
        sku_nobs = cat_sku_nobs.get(sku_key, {})

        if not sku_shares:
            for fi in range(4):
                fb = f'F{fi+1:02d}'
                bk = buckets[12 + fi]
                product_output_rows.append({
                    '产品线': pl, '品类': cat, 'SKU': '未知SKU',
                    '数据类型': '预测', '桶编号': fb,
                    '桶开始月': str(bk['开始月']), '桶结束月': str(bk['结束月']),
                    '销售额': round(f01_f04[fi] * cat_pct, 2),
                    '预测方法': method_name, '方法WAPE': float(wape), '置信度': confidence
                })
            continue

        shrunk_sku = shrinkage_share(sku_shares, sku_nobs)
        for sku, sku_pct in shrunk_sku.items():
            for fi in range(4):
                fb = f'F{fi+1:02d}'
                bk = buckets[12 + fi]
                product_output_rows.append({
                    '产品线': pl, '品类': cat, 'SKU': sku,
                    '数据类型': '预测', '桶编号': fb,
                    '桶开始月': str(bk['开始月']), '桶结束月': str(bk['结束月']),
                    '销售额': round(f01_f04[fi] * cat_pct * sku_pct, 2),
                    '预测方法': method_name, '方法WAPE': float(wape), '置信度': confidence
                })

product_output_df = pd.DataFrame(product_output_rows)
print(f"  Product output: {len(product_output_df)} rows (hist={len(product_output_df[product_output_df['数据类型']=='历史'])}, fcst={len(product_output_df[product_output_df['数据类型']=='预测'])})")

# ============================================================
# 8. CUSTOMER PATH
# ============================================================
print("\nSTEP 8: Customer Path...")

ranking_df = pd.read_csv(RANKING_FILE)
ka_aa_best = ranking_df[ranking_df['排名'] == 1].copy()
ka_aa_categories = ['AA>5000万', 'KA>1亿']

# Parse KA/AA method names
def parse_method_name(method_name_str):
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

# Pre-compute customer -> category mapping (avoid repeated DataFrame filtering)
print("  Building customer-category map...")
cust_cat_map = df.groupby('客户')['客户类别'].first().to_dict()
print(f"  Mapped {len(cust_cat_map)} customers to categories")

# Process all customers
all_customers = sorted(df['客户'].unique())
customer_output_rows = []
ka_aa_count = 0
km_mm_forecasted = 0
skipped_data = 0

print(f"  Processing {len(all_customers)} customers...")

for ci, cust in enumerate(all_customers):
    series = agg_to_series(cust_agg, cust)
    vals = series.values
    first_nz = np.argmax(vals > 0) if any(vals > 0) else 0
    trimmed = vals[first_nz:]
    n_nonzero = int(np.sum(trimmed > 0))

    cust_cat = cust_cat_map.get(cust, 'MM<1000万')
    is_ka_aa = cust_cat in ka_aa_categories

    # Add historical data
    for i in range(12):
        hb = f'H{i+1:02d}'
        val = series.get(hb, 0.0)
        if val > 0:
            bk = buckets[i]
            customer_output_rows.append({
                '客户': cust, '客户类别': cust_cat,
                '产品线': '', '产品(SKU)': '',
                '数据类型': '历史', '桶编号': hb,
                '桶开始月': str(bk['开始月']), '桶结束月': str(bk['结束月']),
                '销售额': float(val), '预测方法': '', '方法WAPE': '', '置信度': ''
            })

    # Check data sufficiency
    if not is_ka_aa and n_nonzero < 5:
        skipped_data += 1
        if (ci + 1) % 100 == 0:
            print(f"  [{ci+1}/{len(all_customers)}] KA/AA:{ka_aa_count} KM/MM:{km_mm_forecasted} skip:{skipped_data}")
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
        # KA/AA but no parsed method - fallback
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

    # Forecast
    best_params['window'] = min(best_params.get('window', len(trimmed)), len(trimmed))
    try:
        fcast_val = forecast_single(trimmed, best_algo, best_params)
    except Exception:
        fcast_val = np.nan
    if np.isnan(fcast_val) or fcast_val < 0:
        fcast_val = float(np.mean(trimmed[-4:])) if len(trimmed) >= 4 else float(np.mean(trimmed))

    # Split to 4 buckets
    recent4 = trimmed[-4:] if len(trimmed) >= 4 else trimmed
    if recent4.sum() > 0:
        w = recent4 / recent4.sum()
    else:
        w = np.ones(len(recent4)) / len(recent4)
    if len(w) < 4:
        w = np.full(4, 0.25)

    confidence = '高' if best_wape <= 0.20 else ('中' if best_wape <= 0.45 else '低')

    for fi in range(4):
        fb = f'F{fi+1:02d}'
        bk = buckets[12 + fi]
        customer_output_rows.append({
            '客户': cust, '客户类别': cust_cat,
            '产品线': '', '产品(SKU)': '',
            '数据类型': '预测', '桶编号': fb,
            '桶开始月': str(bk['开始月']), '桶结束月': str(bk['结束月']),
            '销售额': float(max(0, fcast_val * w[fi])),
            '预测方法': method_name, '方法WAPE': float(best_wape), '置信度': confidence
        })

    if (ci + 1) % 100 == 0:
        print(f"  [{ci+1}/{len(all_customers)}] KA/AA:{ka_aa_count} KM/MM:{km_mm_forecasted} skip:{skipped_data}")

print(f"  Final: KA/AA:{ka_aa_count} KM/MM:{km_mm_forecasted} skip:{skipped_data} (data insufficient)")

cust_df = pd.DataFrame(customer_output_rows)
print(f"  Customer output (pre-split): {len(cust_df)} rows")

# ============================================================
# 8b. PRODUCT SPLIT for customers
# ============================================================
print("\nSTEP 8b: Product split for customers...")

# Build customer->product shares from cp_agg
cust_prod_shares = defaultdict(dict)
cust_prod_nobs = defaultdict(dict)

for (cust, pl, sku), bv in cp_agg.items():
    hist_vals = [bv.get(f'H{i+1:02d}', 0.0) for i in range(12)]
    total = sum(hist_vals)
    if total <= 0:
        continue
    cust_total = sum([bv2.get(f'H{i+1:02d}', 0.0) for i in range(12) for (c2, p2, s2), bv2 in cp_agg.items() if c2 == cust])
    if cust_total <= 0:
        continue
    prod_id = f'{pl}|||{sku}'
    cust_prod_shares[cust][prod_id] = total / cust_total
    nz = sum(1 for i in range(12) if bv.get(f'H{i+1:02d}', 0.0) > 0)
    cust_prod_nobs[cust][prod_id] = nz

# Expand forecast rows with product split
final_customer_rows = []
cust_forecast = cust_df[cust_df['数据类型'] == '预测']

for _, frow in cust_forecast.iterrows():
    cust = frow['客户']
    fb = frow['桶编号']
    total_fcast = frow['销售额']
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
        final_customer_rows.append({
            '客户': cust, '客户类别': cust_cat,
            '产品线': pl_name, '产品(SKU)': sku_name,
            '数据类型': '预测', '桶编号': fb,
            '桶开始月': frow['桶开始月'], '桶结束月': frow['桶结束月'],
            '销售额': round(total_fcast * share, 2),
            '预测方法': method_name, '方法WAPE': wape, '置信度': confidence
        })

# Add historical rows at product level
for (cust, pl, sku), bv in cp_agg.items():
    cust_cat = cust_cat_map.get(cust, 'MM<1000万')
    for i in range(12):
        hb = f'H{i+1:02d}'
        val = bv.get(hb, 0.0)
        if val > 0:
            bk = buckets[i]
            final_customer_rows.append({
                '客户': cust, '客户类别': cust_cat,
                '产品线': pl, '产品(SKU)': sku,
                '数据类型': '历史', '桶编号': hb,
                '桶开始月': str(bk['开始月']), '桶结束月': str(bk['结束月']),
                '销售额': float(val), '预测方法': '', '方法WAPE': '', '置信度': ''
            })

customer_output_df = pd.DataFrame(final_customer_rows)
print(f"  Final customer output: {len(customer_output_df)} rows (hist={len(customer_output_df[customer_output_df['数据类型']=='历史'])}, fcst={len(customer_output_df[customer_output_df['数据类型']=='预测'])})")

# ============================================================
# 9. SAVE OUTPUTS
# ============================================================
print("\nSTEP 9: Saving outputs...")

product_output_path = os.path.join(OUTPUT_DIR, 'product_path_forecast.csv')
product_output_df.to_csv(product_output_path, index=False, encoding='utf-8-sig')
print(f"  Product: {product_output_path} ({len(product_output_df)} rows)")

customer_output_path = os.path.join(OUTPUT_DIR, 'customer_path_forecast.csv')
customer_output_df.to_csv(customer_output_path, index=False, encoding='utf-8-sig')
print(f"  Customer: {customer_output_path} ({len(customer_output_df)} rows)")

# Summary
print("\n" + "=" * 60)
print("SUMMARY")
print("=" * 60)
print(f"Product: {len(product_output_df)} rows, PLs={product_output_df[product_output_df['产品线'].str.len()>0]['产品线'].nunique()}")
if len(product_output_df[product_output_df['数据类型']=='预测']) > 0:
    fcst = product_output_df[product_output_df['数据类型']=='预测']
    print(f"  Forecast rows: {len(fcst)}, confidence: {dict(fcst['置信度'].value_counts())}")

print(f"Customer: {len(customer_output_df)} rows, Custs={customer_output_df['客户'].nunique()}")
if len(customer_output_df[customer_output_df['数据类型']=='预测']) > 0:
    cf = customer_output_df[customer_output_df['数据类型']=='预测']
    print(f"  Forecast rows: {len(cf)}, confidence: {dict(cf['置信度'].value_counts())}")
    print(f"  Categories: {dict(cf['客户类别'].value_counts())}")

print("\nDONE!")
