# -*- coding: utf-8 -*-
"""
Phase B1a: v5 RF Regression — Predict severity_label
=====================================================
1. Compute all 9 v5 features from silver data (no look-ahead)
2. Walk-forward RF with TimeSeriesSplit(n_splits=5)
3. OOF evaluation: R², MAE, Spearman ρ, feature importance
4. severity_pred distribution + calibration curve

Pass criteria: OOF R² > 0.30 and Spearman ρ > 0.50
"""
import os, sys, warnings, json
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import r2_score, mean_absolute_error
from scipy.stats import spearmanr
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
os.chdir(PROJECT_ROOT)
warnings.filterwarnings('ignore')

OUT_DIR = 'recession_risk_opt/output'
os.makedirs(OUT_DIR, exist_ok=True)
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DengXian', 'Noto Sans SC']
plt.rcParams['axes.unicode_minus'] = False
np.random.seed(42)

# ═════════════════════════════════════════════════════════════════════
# 1. Load silver data
# ═════════════════════════════════════════════════════════════════════
print("Loading data ...")
pm = pd.read_csv('output/silver/silver_product_monthly.csv', encoding='utf-8-sig')
cp = pd.read_csv('output/silver/silver_customer_x_product.csv', encoding='utf-8-sig')

# Column names (verified from CSV headers)
prod_col = '产品品种'
date_col = '_月'
cust_col = '客户编号'
gp_col = '毛利率%'

pm[date_col] = pd.to_datetime(pm[date_col], format='%Y-%m')
cp[date_col] = pd.to_datetime(cp[date_col], format='%Y-%m')
pm = pm.sort_values([prod_col, date_col]).reset_index(drop=True)

# GP anomaly filter → NaN
pm.loc[(pm[gp_col] > 100) | (pm[gp_col] < -50), 'qty_sum'] = np.nan

print(f"  PM: {len(pm)} rows, {pm[prod_col].nunique()} products, {pm[date_col].min().strftime('%Y-%m')}~{pm[date_col].max().strftime('%Y-%m')}")
print(f"  CP: {len(cp)} rows, {cp[prod_col].nunique()} products, {cp[cust_col].nunique()} customers")

# ═════════════════════════════════════════════════════════════════════
# 2. Compute Product-Level Features (rolling, no look-ahead)
# ═════════════════════════════════════════════════════════════════════
print("\nComputing product-level features ...")

def compute_product_features(group):
    grp = group.copy().sort_values(date_col)
    qty = grp['qty_sum'].values
    margin = grp[gp_col].values
    
    # Helper: rolling 12-month avg, shift(1) so only uses <= T-1
    roll12 = pd.Series(qty).rolling(window=12, min_periods=6)
    roll12_mean = roll12.mean().shift(1).values  # avg[T-12:T-1] at T
    roll12_prior_mean = roll12.mean().shift(13).values  # avg[T-24:T-13] at T
    
    # 2a. growth_rate: (recent - prior) / prior
    with np.errstate(divide='ignore', invalid='ignore'):
        gr = np.where(
            (roll12_prior_mean > 0) & (~np.isnan(roll12_mean)) & (~np.isnan(roll12_prior_mean)),
            (roll12_mean - roll12_prior_mean) / roll12_prior_mean,
            np.nan
        )
    grp['growth_rate'] = gr
    
    # 2b. decline_depth: 1 - (current_12m_avg / peak_12m_avg)
    # Rolling cumulative max of the 12-month averages
    cum_peak = np.maximum.accumulate(np.where(np.isnan(roll12_mean), -np.inf, roll12_mean))
    cum_peak = np.where(np.isneginf(cum_peak), np.nan, cum_peak)
    with np.errstate(divide='ignore', invalid='ignore'):
        dd = np.where(
            (cum_peak > 0) & (~np.isnan(roll12_mean)) & (~np.isnan(cum_peak)),
            1 - roll12_mean / cum_peak,
            np.nan
        )
    grp['decline_depth'] = dd
    
    # 2c. self_health: recent_12m_margin / hist_ref_margin (capped at 1.0)
    # hist_ref_margin = overall average margin (before T)
    exp_avg_margin = pd.Series(margin).expanding(min_periods=6).mean().shift(1).values
    roll12_margin_avg = pd.Series(margin).rolling(window=12, min_periods=6).mean().shift(1).values
    with np.errstate(divide='ignore', invalid='ignore'):
        sh = np.where(
            (exp_avg_margin > 0) & (~np.isnan(roll12_margin_avg)) & (~np.isnan(exp_avg_margin)),
            np.minimum(roll12_margin_avg / exp_avg_margin, 1.0),
            np.nan
        )
    grp['self_health'] = sh
    
    return grp

pm = pm.groupby(prod_col, group_keys=False).apply(compute_product_features)
print(f"  growth_rate computed: {pm['growth_rate'].notna().sum()}/{len(pm)}")
print(f"  decline_depth computed: {pm['decline_depth'].notna().sum()}/{len(pm)}")
print(f"  self_health computed: {pm['self_health'].notna().sum()}/{len(pm)}")

# ═════════════════════════════════════════════════════════════════════
# 3. Compute Customer-Level Features (rolling window, <= T)
# ═════════════════════════════════════════════════════════════════════
print("\nComputing customer-level features ...")

# Pre-process customer data: add derived columns
cp_sorted = cp.sort_values([prod_col, cust_col, date_col]).copy()
cp_sorted['month_num'] = cp_sorted[date_col].dt.to_period('M').astype(int)

# For each product, compute monthly customer stats
def compute_customer_features_for_product(prod_data, all_cp):
    """Compute all 6 customer-level features for a single product."""
    pid = prod_data[prod_col].iloc[0]
    
    # Get all customer data for this product
    prod_cust = all_cp[all_cp[prod_col] == pid].copy()
    if len(prod_cust) == 0:
        for col in ['cust_rev_hhi', 'cust_top1_share', 'cust_churn_rate', 
                     'avg_cust_tenure', 'n_customers_log', 'is_single_customer']:
            prod_data[col] = np.nan
        return prod_data
    
    # Pre-compute first purchase date per customer
    first_purchase = prod_cust.groupby(cust_col)[date_col].min().to_dict()
    
    # Get sorted months for this product
    months = sorted(prod_cust[date_col].unique())
    month_to_idx = {m: i for i, m in enumerate(months)}
    
    results = {}
    for _, row in prod_data.iterrows():
        t = row[date_col]
        t_idx = month_to_idx.get(t)
        if t_idx is None:
            for col in ['cust_rev_hhi', 'cust_top1_share', 'cust_churn_rate',
                         'avg_cust_tenure', 'n_customers_log', 'is_single_customer']:
                results.setdefault(col, []).append(np.nan)
            continue
        
        # Window: [T-11, T] for current customer data
        win_start = max(0, t_idx - 11)
        win_months = months[win_start:t_idx + 1]  # includes T
        window = prod_cust[prod_cust[date_col].isin(win_months)]
        
        if len(window) == 0:
            for col in ['cust_rev_hhi', 'cust_top1_share', 'cust_churn_rate',
                         'avg_cust_tenure', 'n_customers_log', 'is_single_customer']:
                results.setdefault(col, []).append(np.nan)
            continue
        
        # Revenue per customer in window
        cust_rev = window.groupby(cust_col)['rev_sum'].sum()
        total_rev = cust_rev.sum()
        
        if total_rev <= 0:
            for col in ['cust_rev_hhi', 'cust_top1_share', 'cust_churn_rate',
                         'avg_cust_tenure', 'n_customers_log', 'is_single_customer']:
                results.setdefault(col, []).append(np.nan)
            continue
        
        n_cust = len(cust_rev)
        shares = cust_rev / total_rev
        
        # 3a. cust_rev_hhi
        results.setdefault('cust_rev_hhi', []).append((shares ** 2).sum())
        
        # 3b. cust_top1_share
        results.setdefault('cust_top1_share', []).append(shares.max())
        
        # 3c. cust_churn_rate: customers in prior 6 months but NOT in current window
        if t_idx >= 12:
            prior_start = max(0, t_idx - 17)
            prior_months = months[prior_start:t_idx - 11 + 1]
            if len(prior_months) >= 6:
                prior_window = prod_cust[prod_cust[date_col].isin(prior_months)]
                prior_custs = set(prior_window[cust_col].unique())
                current_custs = set(window[cust_col].unique())
                churned = prior_custs - current_custs
                if len(prior_custs) > 0:
                    churn_rate = len(churned) / len(prior_custs)
                else:
                    churn_rate = np.nan
            else:
                churn_rate = np.nan
        else:
            churn_rate = np.nan
        results.setdefault('cust_churn_rate', []).append(churn_rate)
        
        # 3d. avg_cust_tenure
        tenures = []
        for c in window[cust_col].unique():
            first = first_purchase.get(c, t)
            tenure = (t.year - first.year) * 12 + (t.month - first.month)
            tenures.append(max(1, tenure))
        results.setdefault('avg_cust_tenure', []).append(np.mean(tenures))
        
        # 3e. n_customers_log
        results.setdefault('n_customers_log', []).append(np.log1p(n_cust))
        
        # 3f. is_single_customer
        results.setdefault('is_single_customer', []).append(1 if n_cust == 1 else 0)
    
    for col, vals in results.items():
        prod_data[col] = vals
    return prod_data

# Process products in batches to manage progress
products = pm[prod_col].unique()
n_prod = len(products)
cust_features_list = []

for i, pid in enumerate(products):
    if (i + 1) % 100 == 0 or i == 0:
        print(f"  [{i+1}/{n_prod}] Processing customer features for {pid} ...")
    prod_mask = pm[prod_col] == pid
    prod_data = pm[prod_mask].copy()
    prod_data = compute_customer_features_for_product(prod_data, cp_sorted)
    cust_features_list.append(prod_data)

pm = pd.concat(cust_features_list).sort_values([prod_col, date_col]).reset_index(drop=True)

# Check customer feature coverage
for col in ['cust_rev_hhi', 'cust_top1_share', 'cust_churn_rate',
             'avg_cust_tenure', 'n_customers_log', 'is_single_customer']:
    n_valid = pm[col].notna().sum()
    print(f"  {col}: {n_valid}/{len(pm)} ({n_valid/len(pm)*100:.1f}%)")

# ═════════════════════════════════════════════════════════════════════
# 4. Compute severity_label + Build Final Training Dataset
# ═════════════════════════════════════════════════════════════════════
print("\nComputing severity_label and building training dataset ...")

def compute_severity(group):
    grp = group.copy()
    qty = grp['qty_sum'].values
    past_avg = pd.Series(qty).rolling(window=12, min_periods=6).mean().shift(1).values
    future_avg = pd.Series(qty).rolling(window=12, min_periods=6).mean().shift(-12).values
    severity = np.where(
        (past_avg > 0) & (~np.isnan(past_avg)) & (~np.isnan(future_avg)),
        1 - np.minimum(future_avg / past_avg, 1.0),
        np.nan
    )
    grp['severity_label'] = severity
    return grp

pm = pm.groupby(prod_col, group_keys=False).apply(compute_severity)

# Build training dataset
feature_cols = ['growth_rate', 'decline_depth', 'self_health',
                'cust_rev_hhi', 'cust_top1_share', 'cust_churn_rate',
                'avg_cust_tenure', 'n_customers_log', 'is_single_customer']

train = pm.dropna(subset=feature_cols + ['severity_label']).copy()
train = train.reset_index(drop=True)

print(f"Training dataset: {len(train)} rows")
for f in feature_cols:
    print(f"  {f}: {train[f].notna().sum()}/{len(train)}")

# ═════════════════════════════════════════════════════════════════════
# 5. Walk-forward RF with TimeSeriesSplit
# ═════════════════════════════════════════════════════════════════════
print("\nWalk-forward RF training ...")

# Sort by date globally
train = train.sort_values(date_col).reset_index(drop=True)
X = train[feature_cols].values
y = train['severity_label'].values
dates_series = train[date_col]
dates = dates_series.values

tscv = TimeSeriesSplit(n_splits=5)
rf = RandomForestRegressor(n_estimators=500, max_depth=8, min_samples_leaf=10,
                           random_state=42, n_jobs=-1, verbose=0)

oof_pred = np.full(len(train), np.nan)
fi_list = []

for fold, (train_idx, test_idx) in enumerate(tscv.split(X)):
    print(f"\n  Fold {fold+1}:")
    print(f"    Train: {dates_series.iloc[train_idx].min().strftime('%Y-%m')} ~ {dates_series.iloc[train_idx].max().strftime('%Y-%m')} ({len(train_idx)} rows)")
    print(f"    Test:  {dates_series.iloc[test_idx].min().strftime('%Y-%m')} ~ {dates_series.iloc[test_idx].max().strftime('%Y-%m')} ({len(test_idx)} rows)")
    
    X_train, X_test = X[train_idx], X[test_idx]
    y_train, y_test = y[train_idx], y[test_idx]
    
    rf.fit(X_train, y_train)
    y_pred = rf.predict(X_test)
    oof_pred[test_idx] = y_pred
    
    fold_r2 = r2_score(y_test, y_pred)
    fold_mae = mean_absolute_error(y_test, y_pred)
    fold_rho, _ = spearmanr(y_test, y_pred)
    print(f"    R2={fold_r2:.4f}  MAE={fold_mae:.4f}  Spearman rho={fold_rho:.4f}")
    
    fi_list.append(rf.feature_importances_)

# ═════════════════════════════════════════════════════════════════════
# 6. OOF Evaluation
# ═════════════════════════════════════════════════════════════════════
valid_mask = ~np.isnan(oof_pred)
y_true = y[valid_mask]
y_pred = oof_pred[valid_mask]

oof_r2 = r2_score(y_true, y_pred)
oof_mae = mean_absolute_error(y_true, y_pred)
oof_rho, oof_pval = spearmanr(y_true, y_pred)

print(f"\n{'='*60}")
print(f"OOF Results:")
print(f"  R2         = {oof_r2:.4f}")
print(f"  MAE        = {oof_mae:.4f}")
print(f"  Spearman rho = {oof_rho:.4f}")
print(f"  p-value    = {oof_pval:.2e}")
print(f"  Valid OOF  = {len(y_true)} / {len(train)}")
print(f"  R2>0.30: {'PASS' if oof_r2 > 0.30 else 'FAIL'}")
print(f"  Spearman>0.50: {'PASS' if oof_rho > 0.50 else 'FAIL'}")

# Feature importance
fi_mean = np.mean(fi_list, axis=0)
fi_std = np.std(fi_list, axis=0)
fi_df = pd.DataFrame({'feature': feature_cols, 'importance_mean': fi_mean, 'importance_std': fi_std})
fi_df = fi_df.sort_values('importance_mean', ascending=False)
print(f"\nFeature Importance:")
for _, row in fi_df.iterrows():
    bar = '█' * int(row['importance_mean'] * 100)
    print(f"  {row['feature']:25s} {row['importance_mean']:.4f} ± {row['importance_std']:.4f}  {bar}")

decline_depth_share = fi_df.loc[fi_df['feature'] == 'decline_depth', 'importance_mean'].values[0]
print(f"\n  decline_depth share = {decline_depth_share:.1%} (target around 75%)")

# ═════════════════════════════════════════════════════════════════════
# 7. Charts
# ═════════════════════════════════════════════════════════════════════

# 7a: Calibration curve: predicted vs actual (binned)
fig1, axes = plt.subplots(1, 2, figsize=(14, 5))

# Scatter
ax = axes[0]
ax.scatter(y_pred, y_true, alpha=0.08, s=3, c='steelblue')
ax.plot([0, 1], [0, 1], 'r--', alpha=0.5, label='Perfect calibration')
ax.set_xlabel('Predicted severity')
ax.set_ylabel('Actual severity')
ax.set_title(f'OOF: Predicted vs Actual (R²={oof_r2:.3f}, ρ={oof_rho:.3f})')
ax.legend()
ax.grid(alpha=0.3)

# Calibration curve (binned)
ax = axes[1]
bins = np.linspace(0, 1, 21)
bin_centers = (bins[:-1] + bins[1:]) / 2
bin_indices = np.digitize(y_pred, bins) - 1
actual_mean = np.array([y_true[bin_indices == i].mean() if (bin_indices == i).sum() > 5 else np.nan for i in range(len(bins)-1)])
ax.plot(bin_centers, actual_mean, 'o-', color='steelblue', linewidth=2, markersize=5, label='Actual mean')
ax.plot([0, 1], [0, 1], 'r--', alpha=0.5, label='Perfect')
n_per_bin = np.array([(bin_indices == i).sum() for i in range(len(bins)-1)])
for i, n in enumerate(n_per_bin):
    if n > 5:
        ax.annotate(str(n), (bin_centers[i], actual_mean[i]), fontsize=6, ha='center', va='bottom')
ax.set_xlabel('Predicted severity bin')
ax.set_ylabel('Mean actual severity')
ax.set_title('Calibration Curve (binned)')
ax.legend()
ax.grid(alpha=0.3)

fig1.tight_layout()
fig1.savefig(os.path.join(OUT_DIR, 'phaseB1a_calibration.png'), dpi=150)
plt.close(fig1)
print("Calibration chart saved.")

# 7b: Feature importance
fig2, ax = plt.subplots(figsize=(10, 6))
fi_plot = fi_df.sort_values('importance_mean')
ax.barh(fi_plot['feature'], fi_plot['importance_mean'], xerr=fi_plot['importance_std'],
        color='steelblue', alpha=0.8, capsize=3)
ax.set_xlabel('Feature Importance')
ax.set_title('Random Forest Feature Importance (mean ± std across folds)')
ax.grid(axis='x', alpha=0.3)
fig2.tight_layout()
fig2.savefig(os.path.join(OUT_DIR, 'phaseB1a_feature_importance.png'), dpi=150)
plt.close(fig2)
print("Feature importance chart saved.")

# 7c: severity_pred distribution vs actual
fig3, ax = plt.subplots(figsize=(10, 5))
ax.hist(y_true, bins=50, alpha=0.6, label='Actual severity', color='steelblue', density=True)
ax.hist(y_pred, bins=50, alpha=0.6, label='Predicted severity', color='orange', density=True)
ax.set_xlabel('Severity')
ax.set_ylabel('Density')
ax.set_title('Severity Distribution: Actual vs Predicted (OOF)')
ax.legend()
ax.grid(alpha=0.3)
fig3.tight_layout()
fig3.savefig(os.path.join(OUT_DIR, 'phaseB1a_distribution.png'), dpi=150)
plt.close(fig3)
print("Distribution chart saved.")

# ═════════════════════════════════════════════════════════════════════
# 8. Save Results for B1b
# ═════════════════════════════════════════════════════════════════════
train['severity_pred'] = oof_pred
save_cols = ['product_id', 'date_month', 'severity_label', 'severity_pred'] + feature_cols
train_save = train.rename(columns={prod_col: 'product_id', date_col: 'date_month'})
train_save[save_cols].to_pickle(os.path.join(OUT_DIR, 'phaseB1a_results.pkl'))
print(f"\nResults saved: {OUT_DIR}/phaseB1a_results.pkl ({len(train_save)} rows)")

# ═════════════════════════════════════════════════════════════════════
# 9. Markdown Report
# ═════════════════════════════════════════════════════════════════════
b1a_pass = oof_r2 > 0.30 and oof_rho > 0.50

report = f"""# Phase B1a: v5 RF Severity Regression Results

## 1. Data Overview

| Metric | Value |
|---|---|
| Training rows (all features + target available) | {len(train)} |
| Products represented | {train[prod_col].nunique()} |
| Date range | {train[date_col].min().strftime('%Y-%m')} ~ {train[date_col].max().strftime('%Y-%m')} |
| Walk-forward folds | 5 (TimeSeriesSplit) |
| RF parameters | n_estimators=500, max_depth=8, min_samples_leaf=10 |

## 2. OOF Regression Performance

| Metric | Value | Pass (>{'0.30 / >0.50'}) |
|---|---|---|
| R² | {oof_r2:.4f} | {'✅' if oof_r2 > 0.30 else '❌'} |
| MAE | {oof_mae:.4f} | — |
| Spearman ρ | {oof_rho:.4f} | {'✅' if oof_rho > 0.50 else '❌'} |
| Spearman p-value | {oof_pval:.2e} | — |

**Overall: {'✅ PASS' if b1a_pass else '❌ FAIL'}**

## 3. Feature Importance

| Feature | Importance (mean) | Std |
|---|---|---|
"""

for _, row in fi_df.iterrows():
    report += f"| {row['feature']:25s} | {row['importance_mean']:.4f} | {row['importance_std']:.4f} |\n"

report += f"""
decline_depth share: **{decline_depth_share:.1%}**

## 4. Per-Fold Results

| Fold | Train Period | Test Period | Train Rows | Test Rows | R² | MAE | Spearman ρ |
|---|---|---|---|---|---|---|---|
"""

for fold, (train_idx, test_idx) in enumerate(tscv.split(X)):
    y_t = y[test_idx]
    y_p = oof_pred[test_idx]
    valid_f = ~np.isnan(y_p)
    y_t, y_p = y_t[valid_f], y_p[valid_f]
    fold_r2_val = r2_score(y_t, y_p)
    fold_mae_val = mean_absolute_error(y_t, y_p)
    fold_rho_val, _ = spearmanr(y_t, y_p)
    train_min = pd.Timestamp(dates[train_idx].min()).strftime('%Y-%m')
    train_max = pd.Timestamp(dates[train_idx].max()).strftime('%Y-%m')
    test_min = pd.Timestamp(dates[test_idx].min()).strftime('%Y-%m')
    test_max = pd.Timestamp(dates[test_idx].max()).strftime('%Y-%m')
    report += f"| {fold+1} | {train_min}~{train_max} | {test_min}~{test_max} | {len(train_idx)} | {len(test_idx)} | {fold_r2_val:.4f} | {fold_mae_val:.4f} | {fold_rho_val:.4f} |\n"

report += f"""
## 5. Diagnostics

### Feature engineering summary
- growth_rate: captures recent momentum direction (±)
- decline_depth: cumulative peak-to-current drop (0=at peak, 1=complete decline)
- self_health: margin relative to historical reference (0=worse, 1=at/above ref)
- cust_rev_hhi: 0=dispersed, 1=monocustomer
- cust_top1_share: 0-1 scale
- cust_churn_rate: 0-1 fraction lost
- avg_cust_tenure: months (log scale in model)
- n_customers_log: log(count+1)
- is_single_customer: 0/1 flag

### If failed: root cause analysis

"""

if not b1a_pass:
    issues = []
    if oof_r2 <= 0.30:
        issues.append(f"- **R²={oof_r2:.4f} ≤ 0.30**: Model explains too little variance.")
        issues.append(f"  - Feature quality: check if features are noisy or weakly correlated with future decline.")
        issues.append(f"  - Label noise: severity_label uses future 12-month avg; for products with high seasonality, this is inherently noisy.")
        issues.append(f"  - Data density: {len(train)} rows with 5-fold split may leave thin test folds.")
    
    if oof_rho <= 0.50:
        issues.append(f"- **Spearman ρ={oof_rho:.4f} ≤ 0.50**: Model fails to rank-order severity correctly.")
        issues.append(f"  - Check if extreme values are captured but mid-range is random.")
        issues.append(f"  - Calibration curve (chart) will show if systematic bias exists.")
    
    if decline_depth_share > 0.85:
        issues.append(f"- **decline_depth dominance ({decline_depth_share:.1%})**: Model relies almost entirely on one feature.")
        issues.append(f"  - This suggests customer features are uninformative or too noisy for this data.")
        issues.append(f"  - Check customer data coverage: are most products sold to 1-2 customers?")

    report += "\n".join(issues) if issues else ""
else:
    report += "All criteria passed. Model shows meaningful predictive power for severity_label."

report += f"""

## 6. Charts

### Calibration Curve & Scatter
![Calibration](phaseB1a_calibration.png)

### Feature Importance
![Feature Importance](phaseB1a_feature_importance.png)

### Distribution: Actual vs Predicted
![Distribution](phaseB1a_distribution.png)

## 7. B1b Readiness

severity_pred is {'✅ available' if b1a_pass else '⚠ still generated (may be weak)'} for Phase B1b classification evaluation.
"""

with open(os.path.join(OUT_DIR, 'phaseB1a_severity_regression.md'), 'w', encoding='utf-8') as f:
    f.write(report)

print(f"\nReport saved: {OUT_DIR}/phaseB1a_severity_regression.md")
print(f"B1a {'PASS' if b1a_pass else 'FAIL'} — {'proceeding to B1b' if b1a_pass else 'check diagnostics'}")
