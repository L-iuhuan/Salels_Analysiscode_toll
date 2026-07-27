# -*- coding: utf-8 -*-
"""
Phase A: Severity Label Distribution Analysis
==============================================
Goal: Compute severity_label for every product-month, analyze its distribution,
      and verify it has enough variation to support v5 RF modeling.

severity = 1 - min(future_12m_avg_qty / past_12m_avg_qty, 1.0)
- Higher = riskier (severe decline expected)
- Clamped to [0,1]; values near 0 = stable/growing, near 1 = steep decline

Output: phaseA_severity_distribution.md + 3 charts
"""
import os, sys, warnings
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
os.chdir(PROJECT_ROOT)
warnings.filterwarnings('ignore')

OUT_DIR = 'recession_risk_opt/output'
os.makedirs(OUT_DIR, exist_ok=True)

# ── Matplotlib Chinese font ──
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DengXian', 'Noto Sans SC']
plt.rcParams['axes.unicode_minus'] = False

# ════════════════════════════════════════════════
# 1. Load data
# ════════════════════════════════════════════════
print("Loading silver_product_monthly ...")
pm = pd.read_csv('output/silver/silver_product_monthly.csv', encoding='utf-8-sig')

# Identify column names dynamically
prod_col = [c for c in pm.columns if '品' in c or '产品' in c][0]
date_col = '_月'
print(f"Product column: '{prod_col}'")
print(f"Shape: {pm.shape}, Date range: {pm[date_col].min()} ~ {pm[date_col].max()}")

# Parse dates
pm[date_col] = pd.to_datetime(pm[date_col], format='%Y-%m')

# Sort
pm = pm.sort_values([prod_col, date_col]).reset_index(drop=True)

# GP anomaly filter: mark GP >100% or <-50% as NaN for qty
gp_col = [c for c in pm.columns if '毛利率' in c][0]
print(f"GP column: '{gp_col}'")

anomaly_mask = (pm[gp_col] > 100) | (pm[gp_col] < -50)
n_anomaly = anomaly_mask.sum()
print(f"GP anomalies (>100% or <-50%): {n_anomaly} ({n_anomaly/len(pm)*100:.1f}%)")
# Set qty to NaN for anomaly months (so rolling computation won't use them)
pm.loc[anomaly_mask, 'qty_sum'] = np.nan

# ════════════════════════════════════════════════
# 2. Compute severity_label per product-month
# ════════════════════════════════════════════════
print("\nComputing severity_label ...")

def compute_severity(group):
    """For a single product, compute severity_label at each month T."""
    grp = group.copy()
    qty = grp['qty_sum'].values
    # Past 12-month rolling average (trailing 12 months, T-12 to T-1)
    # We use rolling with min_periods=6 (need at least 6 months data)
    past_avg = pd.Series(qty).rolling(window=12, min_periods=6).mean().shift(1).values
    # Future 12-month rolling average (next 12 months, T+1 to T+12)
    # Reverse rolling: use .shift(-12) on rolling mean of reversed data
    future_avg = pd.Series(qty).rolling(window=12, min_periods=6).mean().shift(-12).values
    
    severity = np.where(
        (past_avg > 0) & (~np.isnan(past_avg)) & (~np.isnan(future_avg)),
        1 - np.minimum(future_avg / past_avg, 1.0),
        np.nan
    )
    grp['severity_label'] = severity
    grp['past_12m_avg_qty'] = past_avg
    grp['future_12m_avg_qty'] = future_avg
    return grp

pm = pm.groupby(prod_col, group_keys=False).apply(compute_severity)

n_computed = pm['severity_label'].notna().sum()
n_total = len(pm)
print(f"Severity computed: {n_computed}/{n_total} ({n_computed/n_total*100:.1f}%)")

# ════════════════════════════════════════════════
# 3. Distribution Analysis
# ════════════════════════════════════════════════
valid = pm.dropna(subset=['severity_label']).copy()

print(f"\n=== Severity Label Distribution ===")
print(f"Count: {len(valid)}")
print(f"Mean ± Std: {valid['severity_label'].mean():.4f} ± {valid['severity_label'].std():.4f}")
print(f"Min: {valid['severity_label'].min():.4f}")
print(f"Q1: {valid['severity_label'].quantile(0.25):.4f}")
print(f"Median: {valid['severity_label'].median():.4f}")
print(f"Q3: {valid['severity_label'].quantile(0.75):.4f}")
print(f"Max: {valid['severity_label'].max():.4f}")
print(f"Zero-severity (stable/growth) rate: {(valid['severity_label'] == 0).mean()*100:.1f}%")
print(f"Severity >0.3 (significant decline): {(valid['severity_label'] > 0.3).mean()*100:.1f}%")
print(f"Severity >0.5 (severe decline): {(valid['severity_label'] > 0.5).mean()*100:.1f}%")

# Percentiles
bins = [0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
labels_bin = [f'{b:.1f}-{bins[i+1]:.1f}' for i, b in enumerate(bins[:-1])]
valid['severity_bin'] = pd.cut(valid['severity_label'], bins=bins, labels=labels_bin, include_lowest=True)
bin_counts = valid['severity_bin'].value_counts().sort_index()
print("\nSeverity distribution by decile:")
for k, v in bin_counts.items():
    print(f"  [{k}]: {v} ({v/len(valid)*100:.1f}%)")

# ════════════════════════════════════════════════
# 4. Generate 3 Charts
# ════════════════════════════════════════════════

# — Chart 1: Severity histogram —
fig1, ax1 = plt.subplots(figsize=(10, 5))
ax1.hist(valid['severity_label'], bins=50, color='steelblue', edgecolor='white', alpha=0.8)
ax1.axvline(valid['severity_label'].mean(), color='red', linestyle='--', label=f"Mean={valid['severity_label'].mean():.3f}")
ax1.axvline(valid['severity_label'].median(), color='orange', linestyle='--', label=f"Median={valid['severity_label'].median():.3f}")
ax1.set_xlabel('Severity Label (0=stable, 1=complete decline)')
ax1.set_ylabel('Frequency')
ax1.set_title('Phase A: Severity Label Distribution (all product-months)')
ax1.legend()
ax1.grid(axis='y', alpha=0.3)
fig1.tight_layout()
fig1.savefig(os.path.join(OUT_DIR, 'phaseA_chart1_severity_histogram.png'), dpi=150)
plt.close(fig1)
print("Chart 1 saved.")

# — Chart 2: Severity by time (average trend) —
fig2, ax2 = plt.subplots(figsize=(12, 5))
monthly_avg = valid.groupby(date_col)['severity_label'].agg(['mean', 'median', 'std']).reset_index()
ax2.plot(monthly_avg[date_col], monthly_avg['mean'], label='Mean severity', color='steelblue', linewidth=2)
ax2.fill_between(monthly_avg[date_col],
                 monthly_avg['mean'] - monthly_avg['std'],
                 monthly_avg['mean'] + monthly_avg['std'],
                 alpha=0.15, color='steelblue', label='Mean ± Std')
ax2.plot(monthly_avg[date_col], monthly_avg['median'], label='Median severity', color='orange', linestyle='--', linewidth=1.5)
ax2.set_xlabel('Date')
ax2.set_ylabel('Severity Label')
ax2.set_title('Phase A: Severity Label Trend Over Time')
ax2.legend()
ax2.grid(alpha=0.3)
fig2.tight_layout()
fig2.savefig(os.path.join(OUT_DIR, 'phaseA_chart2_severity_trend.png'), dpi=150)
plt.close(fig2)
print("Chart 2 saved.")

# — Chart 3: Severity vs v3.1 risk_score (from samples.pkl) —
# Load samples.pkl to compare
sp = pd.read_pickle('recession_risk_opt/data/samples.pkl')
sp_plot = sp[['product_id', 'date_month', 'risk_score', 'risk_level', 'y']].copy()
sp_plot['date_month'] = pd.to_datetime(sp_plot['date_month'], format='%Y-%m')

# Merge severity with samples
valid_merge = valid.rename(columns={prod_col: 'product_id'}).copy()
valid_merge['date_month'] = valid_merge[date_col]
merged = sp_plot.merge(valid_merge[['product_id', 'date_month', 'severity_label']], 
                       on=['product_id', 'date_month'], how='inner')

fig3, axes = plt.subplots(1, 2, figsize=(14, 5))

# 3a: Scatter severity vs risk_score
ax = axes[0]
ax.scatter(merged['risk_score'], merged['severity_label'], alpha=0.15, s=5, c='steelblue')
# Fit line
from numpy.polynomial import polynomial as P
mask = ~(merged['risk_score'].isna() | merged['severity_label'].isna())
x_fit = merged.loc[mask, 'risk_score'].values
y_fit = merged.loc[mask, 'severity_label'].values
if len(x_fit) > 10:
    coefs = P.polyfit(x_fit, y_fit, 1)
    x_line = np.linspace(x_fit.min(), x_fit.max(), 100)
    ax.plot(x_line, P.polyval(x_line, coefs), color='red', linestyle='--', 
            label=f'R²={np.corrcoef(x_fit, y_fit)[0,1]**2:.3f}')
ax.set_xlabel('v3.1 Risk Score')
ax.set_ylabel('v5 Severity Label')
ax.set_title('Phase A: Severity vs v3.1 Risk Score')
ax.legend()
ax.grid(alpha=0.3)

# 3b: Severity by risk_level
ax = axes[1]
rl_order = ['健康', '一般', '关注', '预警', '危险']
valid_rl = merged.dropna(subset=['risk_level', 'severity_label'])
avail_rl = [rl for rl in rl_order if rl in valid_rl['risk_level'].unique()]
bp_data = [valid_rl.loc[valid_rl['risk_level'] == rl, 'severity_label'].values for rl in avail_rl]
if len(bp_data) > 0:
    bp = ax.boxplot(bp_data, labels=avail_rl, patch_artist=True)
    colors = ['green', 'lime', 'gold', 'orange', 'red'][:len(bp_data)]
    for patch, color in zip(bp['boxes'], colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.4)
ax.set_xlabel('v3.1 Risk Level')
ax.set_ylabel('v5 Severity Label')
ax.set_title('Phase A: Severity by v3.1 Risk Level')
ax.grid(axis='y', alpha=0.3)

fig3.tight_layout()
fig3.savefig(os.path.join(OUT_DIR, 'phaseA_chart3_severity_vs_v31.png'), dpi=150)
plt.close(fig3)
print("Chart 3 saved.")

# ════════════════════════════════════════════════
# 5. Generate Markdown Report
# ════════════════════════════════════════════════
print("\nGenerating report ...")

report = f"""# Phase A: Severity Label Distribution Report

## 1. Data Overview

| Metric | Value |
|---|---|
| Silver product-month rows | {len(pm)} |
| Unique products | {pm[prod_col].nunique()} |
| Date range | {pm[date_col].min().strftime('%Y-%m')} ~ {pm[date_col].max().strftime('%Y-%m')} |
| GP anomalies (>100% or <-50%) | {n_anomaly} ({n_anomaly/len(pm)*100:.1f}%) |
| Severity computed (valid) | {n_computed} ({n_computed/n_total*100:.1f}%) |

## 2. Severity Label Distribution

| Statistic | Value |
|---|---|
| Count (product-months) | {len(valid)} |
| Mean | {valid['severity_label'].mean():.4f} |
| Std | {valid['severity_label'].std():.4f} |
| Min | {valid['severity_label'].min():.4f} |
| Q1 (25%) | {valid['severity_label'].quantile(0.25):.4f} |
| Median | {valid['severity_label'].median():.4f} |
| Q3 (75%) | {valid['severity_label'].quantile(0.75):.4f} |
| Max | {valid['severity_label'].max():.4f} |
| Zero-severity (stable/growth) | {(valid['severity_label'] == 0).mean()*100:.1f}% |
| Significant decline (>0.3) | {(valid['severity_label'] > 0.3).mean()*100:.1f}% |
| Severe decline (>0.5) | {(valid['severity_label'] > 0.5).mean()*100:.1f}% |

### Decile breakdown

| Range | Count | Percent |
|---|---|---|
"""

for k, v in bin_counts.items():
    report += f"| [{k}] | {v} | {v/len(valid)*100:.1f}% |\n"

report += f"""
## 3. Correlation with v3.1

| Comparison | Value |
|---|---|
| Pearson r (severity vs risk_score) | {np.corrcoef(x_fit, y_fit)[0,1]:.4f} |
| R² | {np.corrcoef(x_fit, y_fit)[0,1]**2:.4f} |
| Overlap (merged rows) | {len(merged)} |

## 4. Charts

### Chart 1: Severity Histogram
![Severity Histogram](phaseA_chart1_severity_histogram.png)

### Chart 2: Severity Trend Over Time
![Severity Trend](phaseA_chart2_severity_trend.png)

### Chart 3: Severity vs v3.1 Risk Score
![Severity vs v3.1](phaseA_chart3_severity_vs_v31.png)

## 5. Key Observations

### Label quality & variation
- Mean severity = **{valid['severity_label'].mean():.3f}** — moderate baseline
- Std = **{valid['severity_label'].std():.3f}** — substantial variation
- Zero-severity: **{(valid['severity_label'] == 0).mean()*100:.1f}%** — {'enough variation' if (valid['severity_label'] == 0).mean() < 0.5 else 'heavy zero-inflation, may need log-transform'}
- Severe (>0.5): **{(valid['severity_label'] > 0.5).mean()*100:.1f}%**

### Trend over time
_(see Chart 2)_ — check if severity is stable or drifting during the sample period.

### Alignment with v3.1
_(see Chart 3)_ — {'Severity shows moderate correlation with v3.1 risk scores (different but related constructs).' if abs(np.corrcoef(x_fit, y_fit)[0,1]) > 0.3 else 'Severity shows weak correlation with v3.1 risk scores (captures different information).'}

## 6. Readiness Assessment

| Criterion | Status | Notes |
|---|---|---|
| Enough variation (>10% non-zero) | {'✅ PASS' if (valid['severity_label'] > 0).mean() > 0.1 else '❌ FAIL'} | {(valid['severity_label'] > 0).mean()*100:.1f}% non-zero |
| Enough samples (>1000) | {'✅ PASS' if n_computed > 1000 else '❌ FAIL'} | {n_computed} valid observations |
| Temporal coverage (≥24 months) | {'✅ PASS' if (pm[date_col].max() - pm[date_col].min()).days / 365 > 2 else '❌ FAIL'} | {(pm[date_col].max() - pm[date_col].min()).days / 365:.1f} years |
| Severity correlates with risk_score (same direction) | {'✅ PASS' if np.corrcoef(x_fit, y_fit)[0,1] > 0 else '❌ FAIL'} | r = {np.corrcoef(x_fit, y_fit)[0,1]:.4f} |

"""

with open(os.path.join(OUT_DIR, 'phaseA_severity_distribution.md'), 'w', encoding='utf-8') as f:
    f.write(report)

print(f"Report saved to {OUT_DIR}/phaseA_severity_distribution.md")
print("\n=== Phase A complete ===")
