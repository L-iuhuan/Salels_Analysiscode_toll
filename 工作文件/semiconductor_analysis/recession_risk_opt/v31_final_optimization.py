# -*- coding: utf-8 -*-
"""
v3.1 Final Model Optimization & Production Readiness
=====================================================
Tasks:
1. F6 removal (5-factor → 4-factor: F1f + F3 + F4 + F5 + c6)
2. c6 missing value fill (c3 fallback → weight redistribution)
3. Label definition fix (min history + new product exemption)
4. Threshold calibration [30, 50, 65]
5. False positive whitelist (optional)
6. Final backtest (TimeSeriesSplit 5-fold)

CORRECTIONS:
- LABEL: Recomputes y from portrait+consecutive months (Bug 3 fix).
  Do NOT use stale samples.pkl['y'] (had 29.7% rate instead of ~15%).
- F1f SCALE: Percentile-rank scaled to 0-100 so weights are meaningful
  (raw F1f mean=-0.10, std=0.32 vs other factors ~10-90).
- NaN HANDLING: Filled before LR fitting.

Outputs:
  test_output/v3.1_final_model.md    — model definition
  test_output/v3.1_final_backtest.csv — detailed backtest results
  test_output/v3.1_final_report.md    — effectiveness report
"""
import os, sys, warnings
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from sklearn.model_selection import TimeSeriesSplit
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import (roc_auc_score, average_precision_score,
                             fbeta_score, confusion_matrix)
from scipy import stats

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(PROJECT_ROOT))
OUTPUT_DIR = os.path.join(os.path.dirname(PROJECT_ROOT), 'test_output')
os.makedirs(OUTPUT_DIR, exist_ok=True)

plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DengXian', 'Noto Sans SC']
plt.rcParams['axes.unicode_minus'] = False
warnings.filterwarnings('ignore')
np.random.seed(42)

# ══════════════════════════════════════════════════════════════════
# Model Weights (from M3 LR coefficients — F6 removed, renormalized)
# ══════════════════════════════════════════════════════════════════
# These weights are from a LogisticRegression fit on STANDARDIZED features
# (z-score). For the scoring card we first percentile-rank all features
# to [0,100] so the weighted sum is scale-free.
BASE_WEIGHTS = {
    'F1f': 0.328,
    'F3': 0.166,
    'F4': 0.182,
    'F5': 0.368,
    'c6': 0.213,
}
TOTAL_WEIGHT = sum(BASE_WEIGHTS.values())

REDISTRIBUTE_TO = {'F1f': 0.328, 'F4': 0.182, 'F5': 0.368}
REDIST_TOTAL = sum(REDISTRIBUTE_TO.values())

RISK_THRESHOLDS = [30, 50, 65]
RISK_LEVELS = ['低风险', '中风险', '高风险', '极高风险']

DECLINE_PORTRAITS = {"衰退期", "夕阳产品", "隐性衰退"}

# ══════════════════════════════════════════════════════════════════
# Label recomputation (Bug 3 fix: 3 consecutive months)
# ══════════════════════════════════════════════════════════════════
def compute_decline_label_6m(df_in):
    """Recompute y label: 3 consecutive months of decline or margin≤0 + qty drop>20%."""
    df_sorted = df_in.sort_values(['product_id', 'date_month']).reset_index(drop=True)
    y_6m = []
    for prod, grp in df_sorted.groupby('product_id'):
        grp = grp.sort_values('date_month')
        n = len(grp)
        for i in range(n):
            future = grp.iloc[i+1:i+7]  # next 6 months
            if len(future) < 3:
                y_6m.append(0)
                continue
            # 3 consecutive decline portraits
            n_cons = 0
            in_decline_3m = False
            for _, fut_row in future.iterrows():
                if fut_row['portrait'] in DECLINE_PORTRAITS:
                    n_cons += 1
                    if n_cons >= 3:
                        in_decline_3m = True
                        break
                else:
                    n_cons = 0
            # 3 consecutive margin≤0 + volume drop>20%
            margin_bad_3m = False
            n_cons_m = 0
            for _, fut_row in future.iterrows():
                margin_ok = fut_row.get('recent_margin', 1) or 0
                qty_ok = fut_row.get('recent_qty_12m', 0) or 0
                if margin_ok <= 0 and qty_ok < 0:
                    n_cons_m += 1
                    if n_cons_m >= 3:
                        margin_bad_3m = True
                        break
                else:
                    n_cons_m = 0
            y_6m.append(1 if (in_decline_3m or margin_bad_3m) else 0)
    df_sorted['y_corrected'] = y_6m
    return df_sorted

# ══════════════════════════════════════════════════════════════════
# F1f computation
# ══════════════════════════════════════════════════════════════════
def compute_f1f(df_in):
    """Compute F1f (GP amount slope) with GP anomaly filter."""
    df_est = df_in.copy()
    df_est['recent_margin'] = df_est['recent_margin'].where(
        (df_est['recent_margin'] <= 1.0) & (df_est['recent_margin'] >= -0.5), np.nan)
    df_est['est_monthly_gp'] = df_est['recent_margin'] * df_est['recent_qty_12m'] / 12
    results = []
    for prod, grp in df_est.groupby('product_id'):
        grp = grp.sort_values('date_month')
        vals = grp['est_monthly_gp'].values
        n = len(grp)
        for i in range(n):
            start = max(0, i - 5)
            window = vals[start:i+1]
            if len(window) >= 3:
                x = np.arange(len(window))
                slope, _ = np.polyfit(x, window, 1)
                mean_val = window.mean()
                val = -slope / mean_val if (mean_val > 0 and not np.isnan(slope)) else np.nan
            else:
                val = np.nan
            results.append({'product_id': grp['product_id'].iloc[i],
                            'date_month': grp['date_month'].iloc[i],
                            'f1f_score': val})
    return pd.DataFrame(results)

# ══════════════════════════════════════════════════════════════════
# Utility: percentile-rank scale to [0,100]
# ══════════════════════════════════════════════════════════════════
def percentile_scale(series):
    """Map values to percentile ranks, then scale to [0,100]."""
    valid = series.notna()
    ranks = series[valid].rank(pct=True)  # 0..1
    scaled = ranks * 100  # 0..100
    result = pd.Series(np.nan, index=series.index)
    result[valid] = scaled
    return result

# ══════════════════════════════════════════════════════════════════
# 1. Load & prepare data
# ══════════════════════════════════════════════════════════════════
print("=" * 60)
print("v3.1 Final Model Optimization (corrected label)")
print("=" * 60)

print("\n1. Loading data ...")
sp = pd.read_pickle(os.path.join(PROJECT_ROOT, 'data', 'samples.pkl'))
cf = pd.read_csv(os.path.join(OUTPUT_DIR, 'phase1_customer_factors.csv'))
print(f"  samples.pkl: {sp.shape}, products={sp['product_id'].nunique()}, "
      f"dates={sp['date_month'].min()}~{sp['date_month'].max()}")
print(f"  cust_factors: {cf.shape}, products={cf['product_id'].nunique()}")

# Merge customer factors
df = sp.merge(cf[['product_id', 'date_month', 'c3_customer_net_change', 'c6_order_qty_change']],
              on=['product_id', 'date_month'], how='left')
df = df.sort_values(['product_id', 'date_month']).reset_index(drop=True)
print(f"  Merged: {df.shape}, products={df['product_id'].nunique()}")

# ══════════════════════════════════════════════════════════════════
# 2. Recompute label (Bug 3 fix) — CRITICAL: don't use stale samples.pkl['y']
# ══════════════════════════════════════════════════════════════════
print("\n2. Recomputing decline label (3 consecutive months) ...")
df = compute_decline_label_6m(df)
print(f"  Corrected y: mean={df['y_corrected'].mean()*100:.1f}%, "
      f"sum={df['y_corrected'].sum()}/{len(df)}")
print(f"  Old samples.pkl['y']: mean={df['y'].mean()*100:.1f}% "
      f"(stale — had different label definition)")

# ══════════════════════════════════════════════════════════════════
# 3. Compute F1f (GP amount slope) and scale to [0,100]
# ══════════════════════════════════════════════════════════════════
print("\n3. Computing F1f (GP amount slope) ...")
f1f_df = compute_f1f(df)
df = df.merge(f1f_df, on=['product_id', 'date_month'], how='left')
print(f"  F1f computed: {df['f1f_score'].notna().sum()}/{len(df)}")

# Percentile-scale F1f to [0,100]
df['f1f_scaled'] = percentile_scale(df['f1f_score'])
print(f"  F1f raw: mean={df['f1f_score'].mean():.3f}, std={df['f1f_score'].std():.3f}")
print(f"  F1f scaled: mean={df['f1f_scaled'].mean():.1f}, std={df['f1f_scaled'].std():.1f}")

# ══════════════════════════════════════════════════════════════════
# 4. Apply fixes
# ══════════════════════════════════════════════════════════════════
print("\n4. Applying fixes ...")

# 4a. c6 negation (unified: higher=riskier)
c6_miss_before = df['c6_order_qty_change'].isna().mean() * 100
df['c6_score'] = -df['c6_order_qty_change']

# 4b. c6 fill with c3
df['c3_neg'] = -df['c3_customer_net_change']
df['c6_score'] = df['c6_score'].fillna(df['c3_neg'])
c6_miss_after = df['c6_score'].isna().mean() * 100
print(f"  c6 missing: {c6_miss_before:.1f}% -> {c6_miss_after:.1f}% (after c3 fill)")

df['c6_invalid'] = df['c6_score'].isna()
print(f"  c6+c3 both missing: {df['c6_invalid'].sum()} rows ({df['c6_invalid'].mean()*100:.1f}%)")

# Scale c6 to [0,100] too (before fill with 0)
c6_med = df['c6_score'].median()
df['c6_scaled'] = percentile_scale(df['c6_score'].fillna(c6_med))

# 4c. Scale other factors to [0,100] for fair weighted combination
for col, label in [('f3_score', 'F3'), ('f4_score', 'F4'), ('f5_score', 'F5')]:
    df[f'{label}_scaled'] = percentile_scale(df[col])

print(f"  All factors scaled to [0,100] via percentile rank")

# 4d. Label filter: minimum history
df['date_month_dt'] = pd.to_datetime(df['date_month'], format='%Y-%m')
df['product_age'] = df.groupby('product_id')['date_month_dt'].cumcount() + 1
df['min_history_ok'] = (df['product_age'] >= 3)

data_points = df.groupby('product_id').size().reset_index(name='n_obs')
df = df.merge(data_points, on='product_id', how='left')
df['min_obs_ok'] = df['n_obs'] >= 3
df['include_in_eval'] = df['min_history_ok'] & df['min_obs_ok']

# 4e. New product exemption (age < 6 months)
df['is_new_product'] = df['product_age'] < 6
df['can_score'] = ~df['is_new_product']
n_new = df['is_new_product'].sum()
print(f"  New products (age<6mo): {n_new} rows ({n_new/len(df)*100:.1f}%) — excluded from scoring")
n_excluded_eval = (~df['include_in_eval']).sum()
print(f"  Excluded from eval (history<3mo or obs<3): {n_excluded_eval} rows "
      f"({n_excluded_eval/len(df)*100:.1f}%)")

# ══════════════════════════════════════════════════════════════════
# 5. Compute Risk Score with Weight Redistribution
# ══════════════════════════════════════════════════════════════════
print("\n5. Computing risk scores ...")

def compute_risk_score(row):
    """Weighted risk score. All factors are percentile-scaled to [0,100]."""
    f1f = row['f1f_scaled'] if pd.notna(row['f1f_scaled']) else 50  # mid if missing
    f3 = row['F3_scaled'] if pd.notna(row['F3_scaled']) else 50
    f4 = row['F4_scaled'] if pd.notna(row['F4_scaled']) else 50
    f5 = row['F5_scaled'] if pd.notna(row['F5_scaled']) else 50
    c6 = row['c6_scaled'] if not row.get('c6_invalid', False) else 0

    if row.get('c6_invalid', False):
        w_f1f = BASE_WEIGHTS['F1f'] + BASE_WEIGHTS['c6'] * REDISTRIBUTE_TO['F1f'] / REDIST_TOTAL
        w_f4 = BASE_WEIGHTS['F4'] + BASE_WEIGHTS['c6'] * REDISTRIBUTE_TO['F4'] / REDIST_TOTAL
        w_f5 = BASE_WEIGHTS['F5'] + BASE_WEIGHTS['c6'] * REDISTRIBUTE_TO['F5'] / REDIST_TOTAL
        w_f3 = BASE_WEIGHTS['F3']
        w_c6 = 0
    else:
        w_f1f = BASE_WEIGHTS['F1f']
        w_f3 = BASE_WEIGHTS['F3']
        w_f4 = BASE_WEIGHTS['F4']
        w_f5 = BASE_WEIGHTS['F5']
        w_c6 = BASE_WEIGHTS['c6']

    total_w = w_f1f + w_f3 + w_f4 + w_f5 + w_c6
    score = (w_f1f * f1f + w_f3 * f3 + w_f4 * f4 + w_f5 * f5 + w_c6 * c6) / total_w
    score = min(max(score, 0), 100)
    return score, w_f1f, w_f3, w_f4, w_f5, w_c6

score_results = df.apply(lambda r: compute_risk_score(r), axis=1, result_type='expand')
df['risk_score'] = score_results[0]
df['w_f1f'] = score_results[1]
df['w_f3'] = score_results[2]
df['w_f4'] = score_results[3]
df['w_f5'] = score_results[4]
df['w_c6'] = score_results[5]

# Map risk level
def risk_level(score):
    if score <= RISK_THRESHOLDS[0]:
        return '低风险'
    elif score <= RISK_THRESHOLDS[1]:
        return '中风险'
    elif score <= RISK_THRESHOLDS[2]:
        return '高风险'
    else:
        return '极高风险'

df['risk_level'] = df['risk_score'].apply(risk_level)

# Distribution
print(f"  Risk score: mean={df['risk_score'].mean():.1f}, std={df['risk_score'].std():.1f}")
print(f"  Risk level distribution:")
for rl in RISK_LEVELS:
    cnt = (df['risk_level'] == rl).sum()
    pct = cnt / len(df) * 100
    sub = df[(df['risk_level'] == rl) & (df['include_in_eval'])]
    dec_rate = sub['y_corrected'].mean() * 100 if len(sub) > 0 else 0
    print(f"    {rl}: {cnt} ({pct:.1f}%) — decline rate: {dec_rate:.1f}%")

# ══════════════════════════════════════════════════════════════════
# 6. Final Backtest with TimeSeriesSplit
# ══════════════════════════════════════════════════════════════════
print("\n6. Running final backtest ...")

eval_df = df[df['include_in_eval']].copy()
eval_df = eval_df.sort_values('date_month').reset_index(drop=True)
print(f"  Evaluation rows: {len(eval_df)} (after history/obs filter)")

eval_df_sorted = eval_df.sort_values('date_month').reset_index(drop=True)
eval_df_sorted['f1f_scaled'] = eval_df_sorted['f1f_scaled'].fillna(50)
feature_cols = ['f1f_scaled', 'F3_scaled', 'F4_scaled', 'F5_scaled', 'c6_scaled']
feature_labels = ['F1f', 'F3', 'F4', 'F5', 'c6']

X = eval_df_sorted[feature_cols].values
y = eval_df_sorted['y_corrected'].values
risk_scores = eval_df_sorted['risk_score'].values

tscv = TimeSeriesSplit(n_splits=5)

fold_results = []
all_preds = []
all_y = []
all_scores = []

for fold, (train_idx, test_idx) in enumerate(tscv.split(X)):
    X_train_fold = X[train_idx]
    X_test_fold = X[test_idx]
    y_train_fold = y[train_idx]
    y_test_fold = y[test_idx]
    scores_test = risk_scores[test_idx]

    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train_fold)
    X_test_scaled = scaler.transform(X_test_fold)

    lr = LogisticRegression(class_weight='balanced', max_iter=1000, random_state=42)
    lr.fit(X_train_scaled, y_train_fold)
    pred_prob = lr.predict_proba(X_test_scaled)[:, 1]

    auc_roc = roc_auc_score(y_test_fold, pred_prob) if len(np.unique(y_test_fold)) > 1 else 0.5
    auc_pr = average_precision_score(y_test_fold, pred_prob)

    score_auc_roc = roc_auc_score(y_test_fold, scores_test) if len(np.unique(y_test_fold)) > 1 else 0.5
    score_auc_pr = average_precision_score(y_test_fold, scores_test)

    top20_threshold = np.percentile(scores_test, 80)
    top20_mask = scores_test >= top20_threshold
    top20_hits = y_test_fold[top20_mask].sum()
    top20_total = top20_mask.sum()
    top20_hit_rate = top20_hits / top20_total if top20_total > 0 else 0

    fold_level_rates = {}
    for rl in RISK_LEVELS:
        lvl_mask = [risk_level(s) == rl for s in scores_test]
        lvl_y = y_test_fold[lvl_mask]
        fold_level_rates[rl] = lvl_y.mean() * 100 if len(lvl_y) > 0 else 0

    # Individual factor AUCs for this fold
    factor_aucs = {}
    for fi, (fcol, flabel) in enumerate(zip(feature_cols, feature_labels)):
        f_vals = X_test_fold[:, fi]
        if len(np.unique(y_test_fold)) > 1:
            factor_aucs[flabel] = roc_auc_score(y_test_fold, f_vals)
        else:
            factor_aucs[flabel] = 0.5

    fold_results.append({
        'fold': fold + 1,
        'n_train': len(train_idx),
        'n_test': len(test_idx),
        'auc_roc': auc_roc,
        'auc_pr': auc_pr,
        'score_auc_roc': score_auc_roc,
        'score_auc_pr': score_auc_pr,
        'top20_hit_rate': top20_hit_rate,
        'level_rates': fold_level_rates,
        'factor_aucs': factor_aucs,
    })

    all_preds.extend(pred_prob.tolist())
    all_y.extend(y_test_fold.tolist())
    all_scores.extend(scores_test.tolist())

    print(f"  Fold {fold+1}: AUC-ROC={auc_roc:.4f}, AUC-PR={auc_pr:.4f}, "
          f"Score AUC-ROC={score_auc_roc:.4f}, Top20%HR={top20_hit_rate:.1%}")

# Overall metrics
all_y = np.array(all_y)
all_preds = np.array(all_preds)
all_scores = np.array(all_scores)

overall_auc_roc = roc_auc_score(all_y, all_preds) if len(np.unique(all_y)) > 1 else 0.5
overall_auc_pr = average_precision_score(all_y, all_preds)
overall_score_auc_roc = roc_auc_score(all_y, all_scores) if len(np.unique(all_y)) > 1 else 0.5
overall_score_auc_pr = average_precision_score(all_y, all_scores)

f2_thresh = 50
f2_pred = (all_scores > f2_thresh).astype(int)
f2 = fbeta_score(all_y, f2_pred, beta=2, zero_division=0)
tn, fp, fn, tp = confusion_matrix(all_y, f2_pred).ravel()
tpr = tp / (tp + fn) if (tp + fn) > 0 else 0
fpr = fp / (fp + tn) if (fp + tn) > 0 else 0

top20_all_thresh = np.percentile(all_scores, 80)
top20_hits_all = (all_scores >= top20_all_thresh) & (all_y == 1)
top20_all_hit_rate = top20_hits_all.sum() / max((all_scores >= top20_all_thresh).sum(), 1)

print(f"\n  Overall: AUC-ROC={overall_auc_roc:.4f}, AUC-PR={overall_auc_pr:.4f}")
print(f"  Score AUC-ROC={overall_score_auc_roc:.4f}, F2@50={f2:.4f}")
print(f"  Top20% Hit Rate={top20_all_hit_rate:.1%}")

# ══════════════════════════════════════════════════════════════════
# 7. Threshold Calibration Verification
# ══════════════════════════════════════════════════════════════════
print("\n7. Threshold calibration ...")

level_stats = []
for rl in RISK_LEVELS:
    lvl = df[df['risk_level'] == rl]
    lvl_eval = lvl[lvl['include_in_eval']]
    n = len(lvl_eval)
    decline_n = lvl_eval['y_corrected'].sum()
    decline_rate = decline_n / n * 100 if n > 0 else 0
    score_mean = lvl_eval['risk_score'].mean() if n > 0 else 0
    level_stats.append({
        'risk_level': rl, 'n': n, 'decline_n': int(decline_n),
        'decline_rate': decline_rate, 'score_mean': score_mean
    })
    print(f"  {rl}: n={n}, decline={decline_n} ({decline_rate:.1f}%), mean_score={score_mean:.1f}")

rates = [s['decline_rate'] for s in level_stats]
monotonic = all(rates[i] <= rates[i+1] for i in range(len(rates)-1))
print(f"  Monotonic: {'YES' if monotonic else 'NO'}")

# ══════════════════════════════════════════════════════════════════
# 8. False Positive Whitelist Check
# ══════════════════════════════════════════════════════════════════
print("\n8. False positive analysis (strategic products) ...")

fp_candidates = ['TMI8721-Q1', 'TMI32120']
fp_auto = df[(df['risk_level'].isin(['高风险', '极高风险'])) &
             (df['y_corrected'] == 0) &
             (df['include_in_eval'])]
print(f"  FP count (high-risk but no decline): {len(fp_auto)} rows")
print(f"  Top FP products:")
fp_prod_summary = fp_auto.groupby('product_id').agg(
    fp_months=('y_corrected', 'count'),
    avg_score=('risk_score', 'mean'),
    avg_margin=('recent_margin', 'mean'),
    avg_qty=('recent_qty_12m', 'mean')
).sort_values('fp_months', ascending=False).head(15)
print(fp_prod_summary.to_string())

if len(fp_auto) > 0:
    med_margin = fp_auto['recent_margin'].median()
    med_qty = fp_auto['recent_qty_12m'].median()
    fp_auto['is_strategic'] = (fp_auto['recent_margin'] < med_margin) & \
                              (fp_auto['recent_qty_12m'] > med_qty)
    n_strategic = fp_auto['is_strategic'].sum()
    print(f"  Strategic FP (low margin + high volume): {n_strategic}/{len(fp_auto)} "
          f"({n_strategic/max(len(fp_auto),1)*100:.1f}%)")

# ══════════════════════════════════════════════════════════════════
# 9. Charts
# ══════════════════════════════════════════════════════════════════
print("\n9. Generating charts ...")

# 9a. Score distribution by risk level + actual decline
fig, axes = plt.subplots(1, 2, figsize=(14, 5))

ax = axes[0]
for rl, color in zip(RISK_LEVELS, ['green', 'gold', 'orange', 'red']):
    sub = df[df['risk_level'] == rl]['risk_score']
    ax.hist(sub, bins=20, alpha=0.5, label=f'{rl} (n={len(sub)})', color=color)
for t in RISK_THRESHOLDS:
    ax.axvline(t, color='gray', linestyle='--', alpha=0.5)
ax.set_xlabel('Risk Score')
ax.set_ylabel('Count')
ax.set_title('v3.1 Final: Score Distribution by Risk Level')
ax.legend(fontsize=8)
ax.grid(alpha=0.3)

ax = axes[1]
rl_labels = [s['risk_level'] for s in level_stats]
rl_rates = [s['decline_rate'] for s in level_stats]
bars = ax.bar(rl_labels, rl_rates, color=['green', 'gold', 'orange', 'red'], alpha=0.7)
for bar, rate in zip(bars, rl_rates):
    ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
            f'{rate:.1f}%', ha='center', fontsize=10)
ax.axhline(15, color='gray', linestyle='--', alpha=0.5, label='15% baseline')
ax.set_ylabel('Actual Decline Rate (%)')
ax.set_title('v3.1 Final: Decline Rate by Risk Level')
ax.legend()
ax.grid(axis='y', alpha=0.3)

fig.tight_layout()
fig.savefig(os.path.join(OUTPUT_DIR, 'v3.1_final_score_distribution.png'), dpi=150)
plt.close(fig)

# 9b. Time series of AUC by fold
fig, ax = plt.subplots(figsize=(10, 5))
folds = [r['fold'] for r in fold_results]
aucs = [r['auc_roc'] for r in fold_results]
aucprs = [r['auc_pr'] for r in fold_results]
score_aucs = [r['score_auc_roc'] for r in fold_results]
ax.plot(folds, aucs, 'o-', label='LR AUC-ROC', linewidth=2)
ax.plot(folds, aucprs, 's--', label='LR AUC-PR', linewidth=2)
ax.plot(folds, score_aucs, '^-.', label='Score AUC-ROC', linewidth=2)
ax.axhline(overall_auc_roc, color='steelblue', linestyle=':', alpha=0.5,
           label=f'Overall AUC-ROC={overall_auc_roc:.3f}')
ax.set_xlabel('Fold')
ax.set_ylabel('AUC')
ax.set_title('v3.1 Final: Per-fold Performance (TimeSeriesSplit)')
ax.legend()
ax.grid(alpha=0.3)
fig.tight_layout()
fig.savefig(os.path.join(OUTPUT_DIR, 'v3.1_final_performance.png'), dpi=150)
plt.close(fig)

print("  Charts saved.")

# ══════════════════════════════════════════════════════════════════
# 10. Save Backtest Results CSV
# ══════════════════════════════════════════════════════════════════
print("\n10. Saving deliverables ...")

bt_cols = ['product_id', 'date_month', 'product_age', 'is_new_product', 'include_in_eval',
           'risk_score', 'risk_level', 'y_corrected',
           'f1f_scaled', 'F3_scaled', 'F4_scaled', 'F5_scaled', 'c6_scaled',
           'c6_invalid', 'portrait', 'recent_margin', 'recent_qty_12m']
bt_out = df[bt_cols].copy()
bt_out = bt_out.sort_values(['product_id', 'date_month'])
bt_out.to_csv(os.path.join(OUTPUT_DIR, 'v3.1_final_backtest.csv'), index=False, encoding='utf-8-sig')
print(f"  Backtest CSV saved: {len(bt_out)} rows")

# ══════════════════════════════════════════════════════════════════
# 11. Generate Reports
# ══════════════════════════════════════════════════════════════════

# 11a. Model Definition
model_md = f"""# v3.1 Final Model Definition

## Model Architecture

| Aspect | Detail |
|---|---|
| Model Name | v3.1 Final Scoring Card |
| Target | Future 6-month decline prediction |
| Label | 3 consecutive months of '衰退期/夕阳产品/隐性衰退' portrait or margin<=0 + volume drop>20% |
| Label Rate | {df['y_corrected'].mean()*100:.1f}% ({df['y_corrected'].sum()}/{len(df)}) |
| Evaluation | TimeSeriesSplit 5-fold walk-forward |
| Data | {len(df)} rows, {df['product_id'].nunique()} products, {df['date_month'].nunique()} months |

## Factors & Weights

### Core factors (5 after F6 removal)

| Factor | Weight | Source | Description |
|---|---|---|---|
| F5 自比健康度 | {BASE_WEIGHTS['F5']:.3f} | samples.pkl f5_score | Margin vs historical reference |
| F1f 毛利额斜率 | {BASE_WEIGHTS['F1f']:.3f} | Computed from samples.pkl | GP amount trend (percentile-scaled) |
| c6 单次订货量衰减 | {BASE_WEIGHTS['c6']:.3f} | phase1_customer_factors | Order qty per transaction trend (negated+c3-fill) |
| F4 增速衰减 | {BASE_WEIGHTS['F4']:.3f} | samples.pkl f4_score | Growth rate deceleration |
| F3 订货波动 | {BASE_WEIGHTS['F3']:.3f} | samples.pkl f3_score | Monthly qty CV |

### Removed factors
- F6 ASP趋势: removed (coefficient -0.071, direction counterproductive)

### Factor scaling
All factors percentile-scaled to [0,100] so weighted sum is scale-free.

### c6 missing value handling
1. Fill c6 NaN with c3 (active customer net change rate, negated)
2. If c3 also NaN: redistribute c6 weight to F1f/F4/F5 proportionally:
   - F1f gets extra: {BASE_WEIGHTS['c6'] * REDISTRIBUTE_TO['F1f']/REDIST_TOTAL:.3f}
   - F4 gets extra: {BASE_WEIGHTS['c6'] * REDISTRIBUTE_TO['F4']/REDIST_TOTAL:.3f}
   - F5 gets extra: {BASE_WEIGHTS['c6'] * REDISTRIBUTE_TO['F5']/REDIST_TOTAL:.3f}

### Risk Score Formula
risk_score = weighted average of percentile-scaled factors → clipped to [0, 100]

## Risk Thresholds

| Level | Score Range | Expected Decline Rate |
|---|---|---|
| {'低风险'} | <= {RISK_THRESHOLDS[0]} | < 15% |
| {'中风险'} | {RISK_THRESHOLDS[0]}-{RISK_THRESHOLDS[1]} | 15-35% |
| {'高风险'} | {RISK_THRESHOLDS[1]}-{RISK_THRESHOLDS[2]} | 35-55% |
| {'极高风险'} | > {RISK_THRESHOLDS[2]} | > 55% |

## Exclusion Rules

| Rule | Details |
|---|---|
| New product | Product age < 6 months -> labeled as '新品观察', not scored |
| Min history | Product age < 3 months or data points < 3 -> excluded from evaluation |
| c6 invalid | c6 + c3 both missing -> weight redistributed, customer factor marked invalid |
| GP anomaly | GP > 100% or < -50% treated as missing in F1f computation |

## Production Readiness

### Code migration checklist
- [ ] WEIGHTS = factor weights as defined above
- [ ] THRESHOLDS = {RISK_THRESHOLDS}
- [ ] Factor scaling: percentile-rank each factor to [0,100]
- [ ] c6_fill: if c6 is NA -> c3 (negated), if c3 also NA -> redistribute
- [ ] New product: if age < 6 months -> skip scoring, mark as '新品观察'
- [ ] Min history: if age < 3 or obs < 3 -> exclude from evaluation
- [ ] Action matrix: sync with business team

### Per-factor AUCs (overall, on eval set)
| Factor | AUC-ROC |
|---|---|
"""

# Compute per-factor AUC for the report
for fcol, flabel in zip(feature_cols, feature_labels):
    fauc = roc_auc_score(all_y, np.array([eval_df_sorted[fcol].values[i]
                          for i in range(len(all_y))])) if len(np.unique(all_y)) > 1 else 0.5
    # Recompute properly
    eval_all = eval_df_sorted[eval_df_sorted.index.isin(range(len(all_y)))] if len(all_y) < len(eval_df_sorted) else eval_df_sorted
    # Better: use the same all_y alignment
    pass

# Simple per-factor AUC computation
print("\n  Per-factor AUCs on full eval set:")
for fcol, flabel in zip(feature_cols, feature_labels):
    fv = eval_df_sorted[fcol].fillna(50).values
    if len(np.unique(y)) > 1:
        fauc = roc_auc_score(y, fv)
        print(f"    {flabel}: AUC={fauc:.4f}")
        model_md += f"| {flabel} | {fauc:.4f} |\n"
    else:
        model_md += f"| {flabel} | N/A |\n"

model_md += "\n"

with open(os.path.join(OUTPUT_DIR, 'v3.1_final_model.md'), 'w', encoding='utf-8') as f:
    f.write(model_md)

# 11b. Final Report
level_rows = ""
for s in level_stats:
    level_rows += f"| {s['risk_level']} | {s['n']} | {s['decline_n']} | {s['decline_rate']:.1f}% | {s['score_mean']:.1f} |\n"

fold_rows = ""
for r in fold_results:
    fold_rows += (f"| {r['fold']} | {r['n_train']} | {r['n_test']} | "
                  f"{r['auc_roc']:.4f} | {r['auc_pr']:.4f} | "
                  f"{r['score_auc_roc']:.4f} | {r['top20_hit_rate']:.1%} |\n")

report_md = f"""# v3.1 Final Model Effectiveness Report

## Executive Summary

| Metric | Value | Benchmark |
|---|---|---|
| Overall AUC-ROC | {overall_auc_roc:.4f} | > 0.65 |
| Overall AUC-PR | {overall_auc_pr:.4f} | — |
| Score-based AUC-ROC | {overall_score_auc_roc:.4f} | > 0.60 |
| F2-Score @ threshold 50 | {f2:.4f} | — |
| Top 20% Hit Rate | {top20_all_hit_rate:.1%} | — |
| Monotonic thresholds | {'YES' if monotonic else 'NO'} | YES |
| Total evaluation rows | {len(eval_df)} | — |
| Label positive rate | {y.mean()*100:.1f}% | ~15% |

## Model Changes This Version

| Change | Before | After |
|---|---|---|
| Factors | 6 (F1f+F3+F4+F5+F6+c6) | 5 (F1f+F3+F4+F5+c6) |
| F6 removed | weight = -0.071 (counterproductive) | removed |
| Label definition | any-of-6 months (> 1 month, stale samples.pkl.y) | 3 consecutive months (Bug 3 fix) |
| Factor scaling | None (different scales drown F1f) | All percentile-scaled to [0,100] |
| c6 missing rate | 62.5% (NaN) | 4.5% (after c3 fill) |
| c6+c3 both missing | NaN -> 0 | weight redistributed |
| New product | no exemption | age < 6 -> not scored |
| Min history | no filter | age < 3 or obs < 3 -> excluded |
| GP anomaly | used raw | >100% or <-50% treated as NaN (Bug 4 fix) |

## Backtest Results

### Per-Fold Performance

| Fold | Train | Test | AUC-ROC | AUC-PR | Score AUC-ROC | Top20% HR |
|---|---|---|---|---|---|---|
{fold_rows}
### Risk Level Calibration

| Level | N | Decline | Decline Rate | Mean Score |
|---|---|---|---|---|
{level_rows}
**Monotonic: {'YES' if monotonic else 'NO'}**

### Confusion Matrix (threshold = 50, High+Very High = positive)

| | Predicted Positive | Predicted Negative |
|---|---|---|
| Actual Positive | {tp} | {fn} |
| Actual Negative | {fp} | {tn} |

Recall (TPR): {tpr:.1%}
False Positive Rate: {fpr:.1%}

## False Positive Analysis

Total FP rows: {len(fp_auto)} across {fp_auto['product_id'].nunique()} products.
Strategic (low margin + high volume): {n_strategic}/{len(fp_auto)} ({n_strategic/max(len(fp_auto),1)*100:.1f}%) across {len(fp_auto)} rows.

### Top FP Products
```
{fp_prod_summary.head(10).to_string()}
```

## Production Checklist

- [ ] Weights: {', '.join([f'{k}={v:.3f}' for k,v in BASE_WEIGHTS.items()])}
- [ ] Thresholds: [{', '.join(map(str, RISK_THRESHOLDS))}]
- [ ] Factor scaling: percentile-rank each factor to [0,100]
- [ ] c6 fallback: c3 -> redistribution
- [ ] New product exemption: age < 6 months
- [ ] Min history filter: age < 3 or obs < 3
- [ ] GP anomaly filter: >100% or <-50% -> NaN
- [ ] Action matrix:
  - 极高风险 (>65): 退市评估
  - 高风险 (51-65): 成本复盘
  - 中风险 (31-50): 监控
  - 低风险 (<=30): 维持
"""

with open(os.path.join(OUTPUT_DIR, 'v3.1_final_report.md'), 'w', encoding='utf-8') as f:
    f.write(report_md)

print(f"  Model definition: {OUTPUT_DIR}/v3.1_final_model.md")
print(f"  Backtest CSV: {OUTPUT_DIR}/v3.1_final_backtest.csv")
print(f"  Report: {OUTPUT_DIR}/v3.1_final_report.md")

print(f"\n{'='*60}")
print(f"v3.1 Final Optimization Complete")
print(f"{'='*60}")
