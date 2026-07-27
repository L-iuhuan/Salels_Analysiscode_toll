# run_0.0.py — 实验 0.0: 平凡基线建立
# 创建: 2026-06-12
# 数据: quarterly_forecast_package/output/quarterly_forecast/产品线季度历史与预测.csv
# 种子: 42

import numpy as np
import pandas as pd
import os
import warnings
warnings.filterwarnings('ignore')

np.random.seed(42)

BASE = r"C:\Users\45091\Desktop\工作文件\semiconductor_analysis"
FORECAST_DIR = os.path.join(BASE, "quarterly_forecast_package", "output", "quarterly_forecast")
OUTPUT_DIR = os.path.join(BASE, "output", "test")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ── 1. Load data ────────────────────────────────────────────
history_df = pd.read_csv(os.path.join(FORECAST_DIR, "产品线季度历史与预测.csv"))
history_df = history_df[history_df['数据类型'] == '历史'].copy()

# Pivot to get product_line x bucket matrix
sales_pivot = history_df.pivot_table(
    values='销售额', index='产品线', columns='桶编号', aggfunc='sum'
)
# Ensure column order H01..H12
buckets = [f'H{i:02d}' for i in range(1, 13)]
sales_pivot = sales_pivot.reindex(columns=buckets)

print(f"Loaded {len(sales_pivot)} product lines x {len(buckets)} buckets")
print(f"Columns: {list(sales_pivot.columns)}")
print()

# ── 2. Backtest setup: train on H01-H08, test on H09-H12 ────
train_buckets = buckets[:8]   # H01-H08
test_buckets = buckets[8:12]  # H09-H12
print(f"Train: {train_buckets}")
print(f"Test:  {test_buckets}")

# ── 3. Compute baselines per product line ──────────────────
results = []

for pline in sales_pivot.index:
    train = sales_pivot.loc[pline, train_buckets].values.astype(float)
    actual = sales_pivot.loc[pline, test_buckets].values.astype(float)
    all_12 = sales_pivot.loc[pline, buckets].values.astype(float)

    # Skip if all NaN
    if np.all(np.isnan(train)):
        continue

    # BL-01: Seasonal Naive (4-quarter lag)
    # H09_pred = H05, H10_pred = H06, H11_pred = H07, H12_pred = H08
    seasonal_naive_pred = train[4:8]  # H05-H08 map to H09-H12

    # BL-02: Global Mean (mean of all 12 history buckets)
    global_mean_pred = np.full(4, np.nanmean(all_12))

    # BL-03: Naive Drift
    # drift = (H08 - H01) / 7
    drift = (train[7] - train[0]) / 7.0 if not np.isnan(train[7]) and not np.isnan(train[0]) else 0.0
    naive_drift_pred = np.array([train[7] + drift * (i+1) for i in range(4)])

    # BL-04: SES with simple alpha optimization
    # Optimize alpha by minimizing 1-step-ahead error on training data
    best_alpha = 0.5
    best_mse = float('inf')
    for alpha in np.arange(0.05, 1.0, 0.05):
        # Simple exponential smoothing forecast (1-step ahead)
        level = train[0]
        sse = 0.0
        n_valid = 0
        for t in range(1, len(train)):
            forecast = level
            if not np.isnan(train[t]):
                sse += (forecast - train[t]) ** 2
                n_valid += 1
            level = alpha * train[t] + (1 - alpha) * level
        if n_valid > 0:
            mse = sse / n_valid
            if mse < best_mse:
                best_mse = mse
                best_alpha = alpha

    # SES prediction: forecast next 4 steps
    ses_level = train[7]  # start from last training value
    # Re-fit with best alpha on full training data
    for t in range(1, len(train)):
        ses_level = best_alpha * train[t] + (1 - best_alpha) * ses_level
    ses_pred = np.full(4, ses_level)  # SES flat forecast

    # ── 4. Compute WAPE ──────────────────────────────────────
    def wape(pred, actual):
        mask = ~np.isnan(actual) & ~np.isnan(pred)
        if mask.sum() == 0:
            return np.nan
        return np.sum(np.abs(pred[mask] - actual[mask])) / np.sum(np.abs(actual[mask]))

    bl01_wape = wape(seasonal_naive_pred, actual)
    bl02_wape = wape(global_mean_pred, actual)
    bl03_wape = wape(naive_drift_pred, actual)
    bl04_wape = wape(ses_pred, actual)

    results.append({
        '产品线': pline,
        'BL-01_SeasonalNaive_WAPE': round(bl01_wape, 6) if not np.isnan(bl01_wape) else None,
        'BL-02_GlobalMean_WAPE': round(bl02_wape, 6) if not np.isnan(bl02_wape) else None,
        'BL-03_NaiveDrift_WAPE': round(bl03_wape, 6) if not np.isnan(bl03_wape) else None,
        'BL-04_SESOptimized_WAPE': round(bl04_wape, 6) if not np.isnan(bl04_wape) else None,
        'SES_BestAlpha': round(best_alpha, 3),
        'TrainNonNaN': int(np.sum(~np.isnan(train))),
        'TestNonNaN': int(np.sum(~np.isnan(actual))),
    })

results_df = pd.DataFrame(results)

# ── 5. Compare with current best method WAPE ────────────────
ranking = pd.read_csv(os.path.join(FORECAST_DIR, "预测方法排行榜.csv"))
best_methods = ranking[ranking['是否最终选中'] == '是'][['产品线', '销售额WAPE', '方法名称']]
best_methods.columns = ['产品线', '当前最优WAPE', '当前最优方法']

results_df = results_df.merge(best_methods, on='产品线', how='left')

# ── 6. Save output ──────────────────────────────────────────
output_path = os.path.join(OUTPUT_DIR, "trivial_baselines_wape.csv")
results_df.to_csv(output_path, index=False, encoding='utf-8-sig')
print(f"\nOutput saved to: {output_path}")

# ── 7. Summary statistics ───────────────────────────────────
print("\n" + "="*80)
print("SUMMARY: Trivial Baselines WAPE")
print("="*80)
for col in ['BL-01_SeasonalNaive_WAPE', 'BL-02_GlobalMean_WAPE', 'BL-03_NaiveDrift_WAPE', 'BL-04_SESOptimized_WAPE', '当前最优WAPE']:
    vals = results_df[col].dropna()
    if len(vals) > 0:
        print(f"  {col}: mean={vals.mean():.4f}, median={vals.median():.4f}, min={vals.min():.4f}, max={vals.max():.4f}")

# Check success criteria
bl01_vals = results_df['BL-01_SeasonalNaive_WAPE'].dropna()
bl02_vals = results_df['BL-02_GlobalMean_WAPE'].dropna()
print(f"\nSuccess Criteria Check:")
print(f"  Seasonal Naive WAPE in [0.10, 0.50]: {bl01_vals.mean():.4f} → {'PASS' if 0.10 <= bl01_vals.mean() <= 0.50 else 'FAIL'}")
print(f"  Seasonal Naive vs Global Mean: SN={bl01_vals.mean():.4f}, GM={bl02_vals.mean():.4f} → {'SeasonalNaive BETTER' if bl01_vals.mean() < bl02_vals.mean() else 'GlobalMean BETTER'}")

# Per-product-line details
print(f"\n{'产品线':<20s} {'SN_WAPE':>8s} {'GM_WAPE':>8s} {'ND_WAPE':>8s} {'SES_WAPE':>8s} {'CurBest':>8s} {'SNvsGM':>8s}")
print("-"*75)
for _, row in results_df.iterrows():
    sn = row['BL-01_SeasonalNaive_WAPE']
    gm = row['BL-02_GlobalMean_WAPE']
    nd = row['BL-03_NaiveDrift_WAPE']
    ses = row['BL-04_SESOptimized_WAPE']
    cb = row['当前最优WAPE']
    comparison = 'SN_WINS' if (sn is not None and gm is not None and sn < gm) else 'GM_WINS'
    print(f"{row['产品线']:<20s} {str(sn)[:8]:>8s} {str(gm)[:8]:>8s} {str(nd)[:8]:>8s} {str(ses)[:8]:>8s} {str(cb)[:8]:>8s} {comparison:>8s}")
