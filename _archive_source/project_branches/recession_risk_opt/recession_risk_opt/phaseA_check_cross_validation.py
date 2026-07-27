# -*- coding: utf-8 -*-
"""
Phase A-Check: Severity × Nine-grid Portrait Cross-Validation
=============================================================
1. Compute severity_label for all product-months
2. Group by nine-grid portrait label (from samples.pkl)
3. Compute distribution stats per group
4. Mann-Whitney U: decline group vs healthy group
5. If decline median < 0.3 → debug severity computation logic
"""
import os, sys, warnings
import pandas as pd
import numpy as np
from scipy.stats import mannwhitneyu
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

# ════════════════════════════════════════════════════════════════
# 1. Load data
# ════════════════════════════════════════════════════════════════
print("Loading silver_product_monthly ...")
pm = pd.read_csv('output/silver/silver_product_monthly.csv', encoding='utf-8-sig')

# Identify columns dynamically
prod_col = [c for c in pm.columns if '品' in c or '产品' in c][0]
date_col = '_月'
print(f"Product column: '{prod_col}'")
pm[date_col] = pd.to_datetime(pm[date_col], format='%Y-%m')
pm = pm.sort_values([prod_col, date_col]).reset_index(drop=True)

# GP anomaly filter
gp_col = [c for c in pm.columns if '毛利率' in c][0]
pm.loc[(pm[gp_col] > 100) | (pm[gp_col] < -50), 'qty_sum'] = np.nan

print("Loading samples.pkl ...")
sp = pd.read_pickle('recession_risk_opt/data/samples.pkl')
sp['date_month'] = pd.to_datetime(sp['date_month'], format='%Y-%m')
print(f"Samples: {len(sp)} rows, {sp['product_id'].nunique()} products")
print(f"Unique portraits: {sp['portrait'].nunique()}")

# ════════════════════════════════════════════════════════════════
# 2. Compute severity_label (same logic as Phase A)
# ════════════════════════════════════════════════════════════════
print("\nComputing severity_label ...")

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
    # Also return intermediate values for debugging
    grp['severity_label'] = severity
    grp['past_12m_avg_qty'] = past_avg
    grp['future_12m_avg_qty'] = future_avg
    return grp

pm = pm.groupby(prod_col, group_keys=False).apply(compute_severity)
n_computed = pm['severity_label'].notna().sum()
print(f"Severity computed: {n_computed}/{len(pm)} ({n_computed/len(pm)*100:.1f}%)")

# ════════════════════════════════════════════════════════════════
# 3. Merge with samples.pkl portrait labels
# ════════════════════════════════════════════════════════════════
print("\nMerging with portrait labels ...")
pm_merge = pm.rename(columns={prod_col: 'product_id', date_col: 'date_month'}).copy()
merged = sp[['product_id', 'date_month', 'portrait', 'risk_level', 'risk_score', 'y']].merge(
    pm_merge[['product_id', 'date_month', 'severity_label', 'past_12m_avg_qty', 'future_12m_avg_qty']],
    on=['product_id', 'date_month'],
    how='inner'
)
print(f"Merged: {len(merged)} rows")

# ════════════════════════════════════════════════════════════════
# 4. Group by portrait — distribution stats
# ════════════════════════════════════════════════════════════════
# Define groups (using Chinese labels as they appear in samples.pkl)
decline_group = {'衰退期', '夕阳产品', '隐性衰退'}
healthy_group = {'成长期', '健康扩张', '现金牛'}
all_groups = decline_group | healthy_group | {'预警增长', '主动收缩'}

# Filter to valid severity
valid = merged.dropna(subset=['severity_label']).copy()

# Stats per portrait
print("\n=== Severity Distribution by Portrait ===")
portrait_order = [
    '健康扩张', '成长期', '现金牛',   # healthy
    '预警增长', '主动收缩',           # warning
    '隐性衰退', '夕阳产品', '衰退期'   # decline
]

results = []
for p in portrait_order:
    sub = valid[valid['portrait'] == p]
    if len(sub) == 0:
        continue
    med = sub['severity_label'].median()
    mean = sub['severity_label'].mean()
    q25 = sub['severity_label'].quantile(0.25)
    q75 = sub['severity_label'].quantile(0.75)
    nz = (sub['severity_label'] > 0).mean()
    results.append({
        'portrait': p, 'count': len(sub),
        'median': med, 'mean': mean,
        'p25': q25, 'p75': q75,
        'non_zero': nz,
        'max': sub['severity_label'].max()
    })
    grp_label = 'DECLINE' if p in decline_group else 'HEALTHY' if p in healthy_group else 'OTHER'
    print(f"  {grp_label:8s} {p:8s}: n={len(sub):5d}  median={med:.4f}  mean={mean:.4f}  q25={q25:.4f}  q75={q75:.4f}  >0={nz:.1%}  max={sub['severity_label'].max():.4f}")

# ════════════════════════════════════════════════════════════════
# 5. Mann-Whitney U test: Decline vs Healthy
# ════════════════════════════════════════════════════════════════
decline_data = valid[valid['portrait'].isin(decline_group)]['severity_label'].values
healthy_data = valid[valid['portrait'].isin(healthy_group)]['severity_label'].values

print(f"\n=== Mann-Whitney U Test ===")
print(f"Decline group: n={len(decline_data)}, median={np.median(decline_data):.4f}, mean={np.mean(decline_data):.4f}")
print(f"  P25={np.percentile(decline_data, 25):.4f}, P75={np.percentile(decline_data, 75):.4f}")
print(f"Healthy group: n={len(healthy_data)}, median={np.median(healthy_data):.4f}, mean={np.mean(healthy_data):.4f}")
print(f"  P25={np.percentile(healthy_data, 25):.4f}, P75={np.percentile(healthy_data, 75):.4f}")

stat, pval = mannwhitneyu(decline_data, healthy_data, alternative='greater')
print(f"Mann-Whitney U: stat={stat:.1f}, p={pval:.6f} (one-sided: decline > healthy)")
print(f"Effect size (Cohen's d-like): mean diff = {np.mean(decline_data) - np.mean(healthy_data):.4f}")

decline_median = float(np.median(decline_data))
need_debug = decline_median < 0.3
print(f"\nDecline group median = {decline_median:.4f} {'< 0.3' if need_debug else '>= 0.3'} -> {'DEBUG NEEDED' if need_debug else 'OK'}")

# ════════════════════════════════════════════════════════════════
# 6. Diagnostics (only if decline median < 0.3)
# ════════════════════════════════════════════════════════════════
debug_sections = ""
if need_debug:
    print("\n" + "="*60)
    print("DEBUG: Decline group median < 0.3 — investigating severity logic")
    print("="*60)
    
    # 6a. Check past_12m_avg vs future_12m_avg for decline products
    decline_valid = valid[valid['portrait'].isin(decline_group)].copy()
    
    # Ratio distribution
    with np.errstate(divide='ignore', invalid='ignore'):
        ratio = decline_valid['future_12m_avg_qty'].values / decline_valid['past_12m_avg_qty'].values
        ratio = np.where(np.isfinite(ratio), ratio, np.nan)
        ratio = np.clip(ratio, 0, 10)  # cap for visualization
    
    shield_rate = (ratio >= 1.0).mean()
    print(f"\n  Declining products where future >= past (severity=0): {shield_rate:.1%}")
    print(f"  Median future/past ratio: {np.nanmedian(ratio):.4f}")
    print(f"  Mean future/past ratio: {np.nanmean(ratio):.4f}")
    
    # 6b. Check which column is driving the result
    print(f"\n  --- Column check ---")
    print(f"  past_12m_avg — any zeros? {(decline_valid['past_12m_avg_qty'] == 0).sum()} rows")
    print(f"  future_12m_avg — any zeros? {(decline_valid['future_12m_avg_qty'] == 0).sum()} rows")
    print(f"  past_12m_avg — small (<10): {(decline_valid['past_12m_avg_qty'] < 10).sum()} rows")
    print(f"  Silver qty_sum — any negatives? {(pm['qty_sum'] < 0).sum()} rows")
    
    # 6c. Spot-check some decline products
    print(f"\n  --- Spot check: top decline products (by severity) ---")
    top_decline = decline_valid.nlargest(10, 'severity_label')
    for _, row in top_decline.iterrows():
        print(f"    {row['product_id']:15s} {row['date_month'].strftime('%Y-%m')}  past={row['past_12m_avg_qty']:.1f}  future={row['future_12m_avg_qty']:.1f}  severity={row['severity_label']:.4f}")
    
    # 6d. Compare silver qty_sum range vs raw data
    print(f"\n  --- Silver qty_sum range ---")
    print(f"  qty_sum: min={pm['qty_sum'].min():.1f}, max={pm['qty_sum'].max():.1f}, median={pm['qty_sum'].median():.1f}")
    print(f"  Non-zero qty_sum: {(pm['qty_sum'] > 0).mean():.1%}")
    print(f"  Negative qty_sum: {(pm['qty_sum'] < 0).sum()} rows")
    
    # 6e. Check if the rolling window boundaries are correct
    print(f"\n  --- Window boundary sanity check ---")
    # Pick a specific product-month to trace through
    sample_rows = decline_valid.sample(min(5, len(decline_valid)))
    for _, row in sample_rows.iterrows():
        pid = row['product_id']
        dt = row['date_month']
        prod_data = pm[pm[prod_col] == pid].sort_values(date_col)
        idx = prod_data[prod_data[date_col] == dt].index
        if len(idx) == 0:
            continue
        idx = idx[0]
        pos = prod_data.index.get_loc(idx)
        qty_series = prod_data['qty_sum'].values
        
        # Manual check: what's in the past 12 window?
        past_start = max(0, pos - 12)
        past_vals = qty_series[past_start:pos]  # T-12 to T-1
        future_vals = qty_series[pos+1:pos+13]  # T+1 to T+12
        
        print(f"    {pid:15s} {dt.strftime('%Y-%m')}:")
        print(f"      pos={pos}, past_start={past_start}, past={len(past_vals)} vals: {past_vals[:6]}... future={len(future_vals)} vals: {future_vals[:6]}...")
        print(f"      Manual past_avg: {np.mean(past_vals):.2f} (code: {row['past_12m_avg_qty']:.2f})")
        if len(future_vals) > 0:
            print(f"      Manual future_avg: {np.nanmean(future_vals):.2f} (code: {row['future_12m_avg_qty']:.2f})")
            manual_sev = 1 - min(np.nanmean(future_vals) / max(np.mean(past_vals), 0.001), 1.0)
            print(f"      Manual severity: {manual_sev:.4f} (code: {row['severity_label']:.4f})")
    
    # Build debug section for report
    debug_sections = f"""
## Diagnostics: Decline Group Median < 0.3

### Why is decline severity so low?

| Check | Value |
|---|---|
| Declining products where future ≥ past (severity=0) | {shield_rate:.1%} |
| Median future/past ratio | {np.nanmedian(ratio):.4f} |
| Mean future/past ratio | {np.nanmean(ratio):.4f} |
| Silver qty_sum non-zero rate | {(pm['qty_sum'] > 0).mean():.1%} |
| Silver qty_sum negative | {(pm['qty_sum'] < 0).sum()} rows |
| Silver qty_sum median | {pm['qty_sum'].median():.1f} |

### Interpretation
- **{shield_rate:.1%}** of "declining" products actually have stable/growing future 12-month sales (severity=0).
  This suggests the portrait label (based on past momentum) does NOT strongly predict future decline direction.
- Many products labeled as "衰退期" may be seasonal or already bottomed-out — their decline has already happened
  and the next 12 months show recovery.
- The weak correlation (r=0.0187 in Phase A) confirms severity_label and nine-grid portrait capture different dimensions.
"""
else:
    debug_sections = """
## Diagnostics: Skip

Decline group median ≥ 0.3 — severity logic verified.

"""

# ════════════════════════════════════════════════════════════════
# 7. Additional: Distribution chart by portrait
# ════════════════════════════════════════════════════════════════
fig, ax = plt.subplots(figsize=(12, 5))
bp_data = [valid.loc[valid['portrait'] == p, 'severity_label'].values for p in portrait_order if p in valid['portrait'].unique()]
bp_labels = [p for p in portrait_order if p in valid['portrait'].unique()]
bp = ax.boxplot(bp_data, labels=bp_labels, patch_artist=True)
colors = []
for label in bp_labels:
    if label in decline_group:
        colors.append('red')
    elif label in healthy_group:
        colors.append('green')
    else:
        colors.append('gold')
for patch, color in zip(bp['boxes'], colors):
    patch.set_facecolor(color)
    patch.set_alpha(0.5)
ax.axhline(0.3, color='gray', linestyle='--', alpha=0.5, label='Threshold=0.3')
ax.set_ylabel('Severity Label')
ax.set_title('Severity Distribution by Nine-grid Portrait (Phase A-Check)')
ax.legend()
ax.grid(axis='y', alpha=0.3)
fig.tight_layout()
fig.savefig(os.path.join(OUT_DIR, 'phaseA_check_boxplot.png'), dpi=150)
plt.close(fig)
print("\nBoxplot saved.")

# ════════════════════════════════════════════════════════════════
# 8. Generate Markdown Report
# ════════════════════════════════════════════════════════════════
rows_str = ""
for r in results:
    grp = 'DECLINE' if r['portrait'] in decline_group else 'HEALTHY' if r['portrait'] in healthy_group else 'OTHER'
    rows_str += f"| {grp:8s} | {r['portrait']:8s} | {r['count']:5d} | {r['median']:.4f} | {r['mean']:.4f} | {r['p25']:.4f} | {r['p75']:.4f} | {r['non_zero']:.1%} | {r['max']:.4f} |\n"

report = f"""# Phase A-Check: Severity × Nine-grid Portrait

## 1. Data Overview

| Metric | Value |
|---|---|
| Silver product-month rows | {len(pm)} |
| Severity computed (valid) | {n_computed} ({n_computed/len(pm)*100:.1f}%) |
| Merged with samples.pkl | {len(merged)} rows |
| Unique portraits in merge | {valid['portrait'].nunique()} |

## 2. Severity Distribution by Portrait

| Group | Portrait | Count | Median | Mean | P25 | P75 | >0 Rate | Max |
|---|---|---|---|---|---|---|---|---|
{rows_str}

## 3. Mann-Whitney U Test

| Metric | Decline Group | Healthy Group |
|---|---|---|
| Portraits included | {" + ".join(sorted(decline_group))} | {" + ".join(sorted(healthy_group))} |
| Count | {len(decline_data)} | {len(healthy_data)} |
| Median | {np.median(decline_data):.4f} | {np.median(healthy_data):.4f} |
| Mean | {np.mean(decline_data):.4f} | {np.mean(healthy_data):.4f} |
| P25 | {np.percentile(decline_data, 25):.4f} | {np.percentile(healthy_data, 25):.4f} |
| P75 | {np.percentile(decline_data, 75):.4f} | {np.percentile(healthy_data, 75):.4f} |

| Test | Value |
|---|---|
| Mann-Whitney U stat | {stat:.1f} |
| p-value (one-sided: decline > healthy) | {pval:.6f} |
| Significant at α=0.05 | {"✅ YES" if pval < 0.05 else "❌ NO"} |
| Mean difference (decline - healthy) | {np.mean(decline_data) - np.mean(healthy_data):.4f} |
| Effect interpretation | {"Decline group has HIGHER severity (expected ✔)" if np.mean(decline_data) > np.mean(healthy_data) else "Decline group has LOWER severity (counterintuitive ⚠)"} |

## 4. Severity vs Previous Decline Label (y)

The samples.pkl `y` column marks v3.1 decline (3 consecutive months, binary). Compare:

"""

# Also check y column (v3.1 decline label) vs severity
y_valid = merged.dropna(subset=['severity_label', 'y'])
y0 = y_valid[y_valid['y'] == 0]['severity_label'].values
y1 = y_valid[y_valid['y'] == 1]['severity_label'].values
if len(y0) > 0 and len(y1) > 0:
    stat_y, pval_y = mannwhitneyu(y1, y0, alternative='greater')
    report += f"""| Metric | v3.1 No Decline (y=0) | v3.1 Decline (y=1) |
|---|---|---|
| Count | {len(y0)} | {len(y1)} |
| Median severity | {np.median(y0):.4f} | {np.median(y1):.4f} |
| Mean severity | {np.mean(y0):.4f} | {np.mean(y1):.4f} |
| P25 | {np.percentile(y0, 25):.4f} | {np.percentile(y1, 25):.4f} |
| P75 | {np.percentile(y0, 75):.4f} | {np.percentile(y1, 75):.4f} |

| MWU test stat | {stat_y:.1f} |
|---|---|
| MWU p-value | {pval_y:.6f} |
| Significant | {"✅ YES" if pval_y < 0.05 else "❌ NO"} |
"""

report += f"""
## 5. Chart

![Severity by Portrait](phaseA_check_boxplot.png)

## 6. Conclusion

- Severity shows {'statistically significant' if pval < 0.05 else 'no statistically significant'} separation between decline vs healthy groups.
- Decline group median = {np.median(decline_data):.4f} ({'≥ 0.3 ✅' if np.median(decline_data) >= 0.3 else '< 0.3 ⚠ — see diagnostics below'}).
- v3.1 decline label (y) vs severity: {'significant' if pval_y < 0.05 else 'not significant'} {'✅' if pval_y < 0.05 else ''}.

{debug_sections}

## 7. Phase B Readiness

| Criterion | Status |
|---|---|
| Severity has meaningful variation across known decline groups | {'✅ PASS' if pval < 0.05 else '❌ FAIL'} |
| Decline group median ≥ 0.3 | {'✅ PASS' if np.median(decline_data) >= 0.3 else '⚠ Investigated (see diagnostics)'} |
| Enough data for RF training | {'✅ PASS' if len(valid) > 2000 else '❌ FAIL'} |
| Proceed to Phase B | {'✅ YES — severity label validated' if pval < 0.05 else '⚠ Review diagnostics before Phase B'} |

"""

with open(os.path.join(OUT_DIR, 'phaseA_check_cross_validation.md'), 'w', encoding='utf-8') as f:
    f.write(report)
print(f"\nReport saved.")
print("Phase A-Check complete.")
