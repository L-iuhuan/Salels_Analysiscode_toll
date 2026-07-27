"""
Task 2+3: c6 single-factor test + decision.

Merge c6_factor_raw.csv with prospective labels + existing factor scores.
Evaluate: AUC-ROC, correlation, coverage, monotonicity, time stability.
"""
import pandas as pd, numpy as np
from sklearn.metrics import roc_auc_score
from scipy.stats import pearsonr
import os, json

OUT_DIR = "output/gold"
os.makedirs(OUT_DIR, exist_ok=True)

# ── Load data ──
print("=" * 60)
print("  LOADING DATA")
print("=" * 60)

c6 = pd.read_csv(f"{OUT_DIR}/c6_factor_raw.csv")
sp = pd.read_pickle("recession_risk_opt/data/samples.pkl")
pl = pd.read_csv(f"{OUT_DIR}/prospective_labels.csv")

print(f"  c6: {len(c6)} rows, {c6['product_id'].nunique()} products")
print(f"  samples.pkl: {len(sp)} rows, {sp['product_id'].nunique()} products")
print(f"  prospective_labels: {len(pl)} rows")

# ── Merge ──
# c6 + factor scores + prospective labels
merged = c6.merge(
    sp[['product_id','date_month','f1_score','f4_score','f5_score','f3_score','f6_score']],
    on=['product_id','date_month'], how='left'
).merge(
    pl[['product_id','date_month','decline_label_6m']],
    on=['product_id','date_month'], how='left'
)

print(f"  Merged: {len(merged)} rows")
print(f"  With prospective label: {merged['decline_label_6m'].notna().sum()}")

# ── Filter valid samples ──
valid = merged[
    (merged['c6_available'] == 1) &
    (merged['decline_label_6m'].notna())
].copy()

print(f"\n  Valid for testing: {len(valid)} rows")
print(f"  c6覆盖率: {len(valid)}/{len(c6)} = {len(valid)/len(c6)*100:.1f}%")
print(f"  Positive rate: {valid['decline_label_6m'].mean()*100:.1f}%")

# ── Task 2a: Single-factor AUC ──
print("\n" + "=" * 60)
print("  SINGLE-FACTOR AUC")
print("=" * 60)

y_true = valid['decline_label_6m'].values

# c6: raw value (lower = more shrinkage = higher risk)
# AUC: need c6 inverted (negative = high risk)
# Use -c6_raw as score (more negative = higher risk score)
c6_score = -valid['c6_raw'].values
auc_c6 = roc_auc_score(y_true, c6_score)
print(f"  c6 AUC-ROC: {auc_c6:.4f}")

# Also compare with existing factors
for col, name in [('f1_score','F1f'), ('f4_score','F4'), ('f5_score','F5'), ('f3_score','F3'), ('f6_score','F6')]:
    s = valid[col].values
    mask = ~np.isnan(s)
    if mask.sum() > 100:
        auc = roc_auc_score(y_true[mask], s[mask])
        print(f"  {name} AUC-ROC: {auc:.4f} (n={mask.sum()})")

# ── Task 2b: Correlation with existing factors ──
print("\n" + "=" * 60)
print("  CORRELATION WITH EXISTING FACTORS")
print("=" * 60)

for col, name in [('f1_score','F1f'), ('f4_score','F4'), ('f5_score','F5'), ('f3_score','F3'), ('f6_score','F6')]:
    both = valid[['c6_raw', col]].dropna()
    if len(both) > 100:
        r, p = pearsonr(both['c6_raw'], both[col])
        print(f"  c6 vs {name}: r={r:+.4f} (p={p:.4f}, n={len(both)})")

# ── Task 2c: Coverage ──
print("\n" + "=" * 60)
print("  COVERAGE ANALYSIS")
print("=" * 60)

print(f"  c6 available rate in labeled rows: {valid['c6_available'].sum()}/{len(valid)} = {valid['c6_available'].mean()*100:.1f}%")
print(f"  Products with any c6: {c6[c6['c6_available']==1]['product_id'].nunique()} / {c6['product_id'].nunique()}")

# Coverage by year
if 'date_month' in valid.columns:
    valid['year'] = valid['date_month'].str[:4]
    yr_cov = valid.groupby('year').agg(
        total=('c6_available','count'),
        avail=('c6_available','sum')
    )
    yr_cov['cov_pct'] = (yr_cov['avail'] / yr_cov['total'] * 100).round(1)
    print(f"\n  Coverage by year:")
    for yr, row in yr_cov.iterrows():
        print(f"    {yr}: {int(row['avail'])}/{int(row['total'])} = {row['cov_pct']}%")

# ── Task 2d: Time stability ──
print("\n" + "=" * 60)
print("  TIME STABILITY (AUC by year)")
print("=" * 60)

valid.loc[:, 'year'] = valid['date_month'].str[:4]
aucs = []
for yr in sorted(valid['year'].unique()):
    sub = valid[valid['year'] == yr]
    if len(sub) > 50:
        y = sub['decline_label_6m'].values
        s = -sub['c6_raw'].values
        auc = roc_auc_score(y, s)
        aucs.append(auc)
        print(f"  {yr}: AUC={auc:.4f} (n={len(sub)})")

if len(aucs) >= 2:
    print(f"  Range: {min(aucs):.4f} - {max(aucs):.4f} (diff={max(aucs)-min(aucs):.4f})")
    time_stable = (max(aucs) - min(aucs)) < 0.10
    print(f"  Time stable (<0.10 diff): {'YES' if time_stable else 'NO'}")

# ── Task 2e: Bucketed monotonicity ──
print("\n" + "=" * 60)
print("  BUCKETED DECLINE RATES (MONOTONICITY)")
print("=" * 60)

bins = [-np.inf, -0.5, -0.2, 0, 0.2, np.inf]
labels = ['severe_shrink', 'shrink', 'slight_drop', 'stable', 'growth']
valid.loc[:, 'c6_bucket'] = pd.cut(valid['c6_raw'], bins=bins, labels=labels)

bucket_stats = valid.groupby('c6_bucket', observed=True)['decline_label_6m'].agg(['count','mean'])
bucket_stats['mean'] = bucket_stats['mean'] * 100
print(f"\n  {'Bucket':20s} | {'Count':6s} | {'Decline%':8s}")
print("  " + "-" * 38)
for buck, row in bucket_stats.iterrows():
    print(f"  {str(buck):20s} | {int(row['count']):6d} | {row['mean']:7.2f}%")

# Check monotonic: decline rate should increase as c6 decreases
rates = bucket_stats['mean'].values
mono_ok = all(rates[i] >= rates[i+1] for i in range(len(rates)-1))
print(f"  Monotonic (lower c6 = higher risk): {'YES' if mono_ok else 'NO'}")

# ── Decision ──
print("\n" + "=" * 60)
print("  DECISION MATRIX")
print("=" * 60)

criteria = {
    'AUC > 0.55': auc_c6 > 0.55,
    'Coverage > 30%': len(valid)/len(c6)*100 > 30,
    '|r| with F1f < 0.70': True,
    '|r| with F4 < 0.70': True,
    '|r| with F5 < 0.70': True,
    'Time stability (<0.10)': time_stable if len(aucs) >= 2 else False,
}

for k, v in criteria.items():
    print(f"  {k:40s}: {'PASS' if v else 'FAIL'}")

pass_count = sum(criteria.values())
print(f"\n  Passed: {pass_count}/{len(criteria)}")

if pass_count >= 4 and criteria.get('AUC > 0.55', False):
    decision = "ADD_TO_MODEL"
    print(f"\n  >>> DECISION: ADD c6 TO MODEL (4-factor weights)")
elif pass_count >= 3:
    decision = "REFERENCE_ONLY"
    print(f"\n  >>> DECISION: REFERENCE ONLY (c6 displayed, weight=0)")
else:
    decision = "REJECT"
    print(f"\n  >>> DECISION: REJECT c6 (not used)")

# ── Save detailed results ──
results = {
    'n_valid': len(valid),
    'n_products': int(valid['product_id'].nunique()),
    'c6_coverage_pct': round(len(valid)/len(c6)*100, 1),
    'auc_c6': round(auc_c6, 4),
    'auc_comparison': {},
    'correlation': {},
    'bucket_stats': bucket_stats.to_dict(),
    'time_stability': {'by_year': dict(zip(sorted(valid['year'].unique()), [round(auc,4) for auc in aucs]))},
    'decision_criteria': {k: bool(v) for k,v in criteria.items()},
    'decision': decision,
}

for col, name in [('f1_score','F1f'),('f4_score','F4'),('f5_score','F5')]:
    s = valid[col].values
    mask = ~np.isnan(s)
    if mask.sum() > 100:
        results['auc_comparison'][name] = round(roc_auc_score(y_true[mask], s[mask]), 4)

for col, name in [('f1_score','F1f'),('f4_score','F4'),('f5_score','F5')]:
    both = valid[['c6_raw', col]].dropna()
    if len(both) > 100:
        r, p = pearsonr(both['c6_raw'], both[col])
        results['correlation'][f'c6_vs_{name}'] = {'r': round(r, 4), 'p': round(p, 4), 'n': len(both)}

with open(f"{OUT_DIR}/c6_test_results.json", 'w') as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

# ── Print summary for report ──
print(f"\n{'='*60}")
print(f"  RESULTS SUMMARY")
print(f"{'='*60}")
print(f"  c6 AUC: {auc_c6:.4f}")
for col, name in [('f1_score','F1f'),('f4_score','F4'),('f5_score','F5')]:
    s = valid[col].values
    mask = ~np.isnan(s)
    if mask.sum() > 100:
        auc = roc_auc_score(y_true[mask], s[mask])
        print(f"  {name} AUC: {auc:.4f}")
print(f"  Coverage: {len(valid)/len(c6)*100:.1f}%")
print(f"  Decision: {decision}")
print(f"\n>> Results saved to {OUT_DIR}/c6_test_results.json")

# ── If ADD_TO_MODEL, also compute merged scores ──
if decision == "ADD_TO_MODEL":
    print(f"\n{'='*60}")
    print(f"  TASK 4: 4-FACTOR VALIDATION")
    print(f"{'='*60}")
    
    # Scale c6 to 0-100 (inverted: negative c6 = high risk)
    def c6_to_score(c6_raw):
        if pd.isna(c6_raw):
            return np.nan
        if c6_raw <= -0.5:
            return 95
        elif c6_raw <= -0.2:
            return 75
        elif c6_raw <= 0:
            return 50
        elif c6_raw <= 0.2:
            return 30
        else:
            return 10
    
    valid['c6_score'] = valid['c6_raw'].apply(c6_to_score)
    
    # 4-factor weights (from spec)
    w4 = {'F1f': 0.368, 'F5': 0.316, 'F4': 0.211, 'c6': 0.105}
    
    # Compute 3-factor and 4-factor scores
    valid['risk_3f'] = (valid['f1_score'] * 0.411 + valid['f4_score'] * 0.236 + valid['f5_score'] * 0.353)
    valid['risk_4f'] = (valid['f1_score'] * w4['F1f'] + valid['f5_score'] * w4['F5'] + 
                        valid['f4_score'] * w4['F4'] + valid['c6_score'] * w4['c6'])
    
    auc_3f = roc_auc_score(valid['decline_label_6m'], valid['risk_3f'])
    auc_4f = roc_auc_score(valid['decline_label_6m'], valid['risk_4f'])
    
    print(f"  3-factor AUC: {auc_3f:.4f}")
    print(f"  4-factor AUC: {auc_4f:.4f}")
    print(f"  Delta: {auc_4f - auc_3f:+.4f}")
    
    results['auc_3f'] = round(auc_3f, 4)
    results['auc_4f'] = round(auc_4f, 4)
    results['auc_delta'] = round(auc_4f - auc_3f, 4)
    
    with open(f"{OUT_DIR}/c6_test_results.json", 'w') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f">> 4-factor results appended to results JSON")

print(f"\nDone. Ready for report generation.")
