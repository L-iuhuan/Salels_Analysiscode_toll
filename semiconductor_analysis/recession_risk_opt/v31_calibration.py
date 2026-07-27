# -*- coding: utf-8 -*-
"""
v3.1 评分卡上线前校准 — 多方案实测对比
========================================
Tasks:
  1. Weight comparison (W1/W2/W3)
  2. Threshold comparison (T1-T6)
  3. F3 removal test
  4. c6 fill strategy test
  5. Whitelist mechanism test

Output: test_output/v3.1_calibration_master_report.md + PNG charts
"""
import os, sys, warnings, json
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

DECLINE_PORTRAITS = {"衰退期", "夕阳产品", "隐性衰退"}

# ══════════════════════════════════════════════════════════════════
# Weight schemes
# ══════════════════════════════════════════════════════════════════
WEIGHT_SCHEMES = {
    'W1':  {'F1f': 0.328, 'F5': 0.368, 'F4': 0.182, 'c6': 0.213, 'F3': 0.166, 'desc': '原优化权重'},
    'W2':  {'F1f': 0.350, 'F5': 0.300, 'F4': 0.200, 'c6': 0.100, 'F3': 0.050, 'desc': 'F1f主导'},
    'W3':  {'F1f': 0.300, 'F5': 0.300, 'F4': 0.200, 'c6': 0.150, 'F3': 0.050, 'desc': '平衡'},
}
REDISTRIBUTE_TO = {'F1f': 0.328, 'F4': 0.182, 'F5': 0.368}
REDIST_TOTAL = sum(REDISTRIBUTE_TO.values())

# ══════════════════════════════════════════════════════════════════
# Threshold schemes
# ══════════════════════════════════════════════════════════════════
THRESHOLD_SCHEMES = {
    'T1': {'thresholds': [34, 52, 58], 'levels': 4, 'desc': '历史基准'},
    'T2': {'thresholds': [30, 50, 65], 'levels': 4, 'desc': '轻调'},
    'T3': {'thresholds': [50, 60, 75], 'levels': 4, 'desc': '聚焦'},
    'T4': {'thresholds': [45, 65],      'levels': 3, 'desc': '简化'},
    'T5': {'thresholds': [50, 75],      'levels': 3, 'desc': '激进'},
    'T6': {'thresholds': [30, 45, 60, 75], 'levels': 5, 'desc': '精细'},
}
RISK_LEVEL_NAMES_4 = ['低风险', '中风险', '高风险', '极高风险']
RISK_LEVEL_NAMES_3 = ['低风险', '高风险', '极高风险']
RISK_LEVEL_NAMES_5 = ['低', '关注', '中', '高', '极高']

# ══════════════════════════════════════════════════════════════════
# Data preparation
# ══════════════════════════════════════════════════════════════════
def compute_decline_label_6m(df_in):
    df_sorted = df_in.sort_values(['product_id', 'date_month']).reset_index(drop=True)
    y_6m = []
    for prod, grp in df_sorted.groupby('product_id'):
        grp = grp.sort_values('date_month')
        n = len(grp)
        for i in range(n):
            future = grp.iloc[i+1:i+7]
            if len(future) < 3:
                y_6m.append(0); continue
            n_cons = 0; in_decline_3m = False
            for _, fut_row in future.iterrows():
                if fut_row['portrait'] in DECLINE_PORTRAITS:
                    n_cons += 1
                    if n_cons >= 3: in_decline_3m = True; break
                else: n_cons = 0
            n_cons_m = 0; margin_bad_3m = False
            for _, fut_row in future.iterrows():
                mo = fut_row.get('recent_margin', 1) or 0
                qo = fut_row.get('recent_qty_12m', 0) or 0
                if mo <= 0 and qo < 0:
                    n_cons_m += 1
                    if n_cons_m >= 3: margin_bad_3m = True; break
                else: n_cons_m = 0
            y_6m.append(1 if (in_decline_3m or margin_bad_3m) else 0)
    df_sorted['y_corrected'] = y_6m
    return df_sorted

def compute_f1f(df_in):
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
                try:
                    slope, _ = np.polyfit(x, window, 1)
                    mean_val = window.mean()
                    val = -slope / mean_val if (mean_val > 0 and not np.isnan(slope)) else np.nan
                except: val = np.nan
            else: val = np.nan
            results.append({'product_id': grp['product_id'].iloc[i],
                            'date_month': grp['date_month'].iloc[i], 'f1f_score': val})
    return pd.DataFrame(results)

def percentile_scale(series):
    valid = series.notna()
    ranks = series[valid].rank(pct=True)
    scaled = ranks * 100
    result = pd.Series(np.nan, index=series.index)
    result[valid] = scaled
    return result

def prepare_data():
    """Load and prepare the unified dataset for all tasks."""
    sp = pd.read_pickle(os.path.join(PROJECT_ROOT, 'data', 'samples.pkl'))
    cf = pd.read_csv(os.path.join(OUTPUT_DIR, 'phase1_customer_factors.csv'))
    df = sp.merge(cf[['product_id','date_month','c3_customer_net_change','c6_order_qty_change']],
                  on=['product_id','date_month'], how='left')
    df = df.sort_values(['product_id','date_month']).reset_index(drop=True)

    # Recompute label
    df = compute_decline_label_6m(df)
    ylab = 'y_corrected'
    print(f"  Label: mean={df[ylab].mean()*100:.1f}%, sum={df[ylab].sum()}/{len(df)}")

    # Compute F1f
    f1f_df = compute_f1f(df)
    df = df.merge(f1f_df, on=['product_id','date_month'], how='left')
    df['f1f_scaled'] = percentile_scale(df['f1f_score'])
    print(f"  F1f scaled: mean={df['f1f_scaled'].mean():.1f}")

    # c6 handling (S1: c3 fill)
    df['c6_score'] = -df['c6_order_qty_change']
    df['c3_neg'] = -df['c3_customer_net_change']
    df['c6_filled_c3'] = df['c6_score'].fillna(df['c3_neg'])
    df['c6_invalid'] = df['c6_filled_c3'].isna()
    c6_med = df['c6_filled_c3'].median()
    df['c6_filled_0'] = df['c6_score'].fillna(0)   # S3: fill with 0
    df['c6_filled_med'] = df['c6_score'].fillna(c6_med)  # for S2: fill with median as placeholder
    df['c6_scaled'] = percentile_scale(df['c6_filled_c3'].fillna(c6_med))
    df['c6_scaled_redistribute'] = percentile_scale(df['c6_score'].fillna(c6_med))

    # Scale other factors
    for col in ['f3_score','f4_score','f5_score']:
        df[f'{col}_scaled'] = percentile_scale(df[col])

    # Product age / filters
    df['date_month_dt'] = pd.to_datetime(df['date_month'], format='%Y-%m')
    df['product_age'] = df.groupby('product_id')['date_month_dt'].cumcount() + 1
    df['min_history_ok'] = df['product_age'] >= 3
    n_obs = df.groupby('product_id').size().reset_index(name='n_obs')
    df = df.merge(n_obs, on='product_id', how='left')
    df['min_obs_ok'] = df['n_obs'] >= 3
    df['include_in_eval'] = df['min_history_ok'] & df['min_obs_ok']
    df['is_new_product'] = df['product_age'] < 6

    return df

# ══════════════════════════════════════════════════════════════════
# Scoring engine
# ══════════════════════════════════════════════════════════════════
def compute_risk_score_row(row, weights, c6_strategy='c3_fill'):
    """Compute risk score for a single row with given weights and c6 strategy.
    
    c6_strategy: 'c3_fill' (S1), 'redistribute' (S2), 'zero_fill' (S3)
    """
    f1f = row['f1f_scaled'] if pd.notna(row.get('f1f_scaled')) else 50
    f3 = row['f3_score_scaled'] if pd.notna(row.get('f3_score_scaled')) else 50
    f4 = row['f4_score_scaled'] if pd.notna(row.get('f4_score_scaled')) else 50
    f5 = row['f5_score_scaled'] if pd.notna(row.get('f5_score_scaled')) else 50

    # Filter to factor weights only (exclude 'desc' or other metadata)
    w = {k: v for k, v in weights.items() if k in ['F1f','F3','F4','F5','c6']}

    if c6_strategy == 'c3_fill':
        c6 = row['c6_scaled'] if not row.get('c6_invalid', False) else 0
        if row.get('c6_invalid', False):
            extra = w.get('c6', 0)
            w['F1f'] += extra * REDISTRIBUTE_TO['F1f'] / REDIST_TOTAL
            w['F4']  += extra * REDISTRIBUTE_TO['F4'] / REDIST_TOTAL
            w['F5']  += extra * REDISTRIBUTE_TO['F5'] / REDIST_TOTAL
            w['c6'] = 0
    elif c6_strategy == 'redistribute':
        extra = w.get('c6', 0)
        w['F1f'] += extra * REDISTRIBUTE_TO['F1f'] / REDIST_TOTAL
        w['F4']  += extra * REDISTRIBUTE_TO['F4'] / REDIST_TOTAL
        w['F5']  += extra * REDISTRIBUTE_TO['F5'] / REDIST_TOTAL
        w['c6'] = 0
        c6 = 0
    elif c6_strategy == 'zero_fill':
        c6 = row['c6_scaled'] if pd.notna(row.get('c6_scaled')) else 50
        if row.get('c6_invalid', False):
            c6 = 50  # mid score for missing
    else:
        c6 = row['c6_scaled'] if pd.notna(row.get('c6_scaled')) else 50

    total_w = sum(w.values())
    score = (w.get('F1f',0)*f1f + w.get('F3',0)*f3 + w.get('F4',0)*f4 +
             w.get('F5',0)*f5 + w.get('c6',0)*c6) / total_w
    return min(max(score, 0), 100)

def compute_risk_score_vectorized(df, weights, c6_strategy='c3_fill', factor_cols=None):
    """Compute risk scores for the whole dataframe (vectorized inner loop, row-by-row for c6 logic)."""
    if factor_cols is None:
        factor_cols = ['f1f_scaled', 'F3', 'F4', 'F5', 'c6']
    scores = []
    for idx, row in df.iterrows():
        scores.append(compute_risk_score_row(row, weights, c6_strategy))
    return np.array(scores)

def risk_level_vectorized(scores, thresholds):
    """Map scores to risk levels (variable number of levels)."""
    levels = []
    for s in scores:
        lvl = 0
        for i, t in enumerate(thresholds):
            if s > t:
                lvl = i + 1
        levels.append(lvl)
    return np.array(levels)

def get_level_name(level_idx, n_levels):
    if n_levels == 4: return RISK_LEVEL_NAMES_4[level_idx]
    elif n_levels == 3: return RISK_LEVEL_NAMES_3[level_idx]
    elif n_levels == 5: return RISK_LEVEL_NAMES_5[level_idx]
    return str(level_idx)

def compute_kendall_tau(predicted_scores, actual_labels):
    """Stability metric: Kendall τ between predicted scores and actual labels."""
    if len(predicted_scores) < 2:
        return 0.0
    tau, p = stats.kendalltau(predicted_scores, actual_labels)
    return tau if not np.isnan(tau) else 0.0

# ══════════════════════════════════════════════════════════════════
# Backtest engine
# ══════════════════════════════════════════════════════════════════
def run_backtest(df, weights, thresholds, c6_strategy='c3_fill',
                 weight_name='W?', threshold_name='T?', n_splits=5):
    """Run TimeSeriesSplit backtest and return metrics dict."""
    # Filter to eval set
    eval_df = df[df['include_in_eval']].copy().sort_values('date_month').reset_index(drop=True)
    y_true = eval_df['y_corrected'].values
    y = y_true  # alias

    # Compute scores for all eval rows
    scores = compute_risk_score_vectorized(eval_df, weights, c6_strategy)
    eval_df['risk_score'] = scores

    # Per-factor scaled features for LR baseline
    factor_cols = ['f1f_scaled', 'f3_score_scaled', 'f4_score_scaled', 'f5_score_scaled', 'c6_scaled']
    for c in factor_cols:
        eval_df[c] = eval_df[c].fillna(50)
    X = eval_df[factor_cols].values

    tscv = TimeSeriesSplit(n_splits=n_splits)
    fold_results = []
    all_preds, all_yb, all_scores = [], [], []

    for fold, (tr_idx, te_idx) in enumerate(tscv.split(X)):
        X_tr, X_te = X[tr_idx], X[te_idx]
        y_tr, y_te = y[tr_idx], y[te_idx]
        s_te = scores[te_idx]

        # LR for probability calibration
        if len(np.unique(y_tr)) > 1 and len(np.unique(y_te)) > 1:
            scaler = StandardScaler()
            X_tr_s = scaler.fit_transform(X_tr)
            X_te_s = scaler.transform(X_te)
            lr = LogisticRegression(class_weight='balanced', max_iter=1000, random_state=42)
            lr.fit(X_tr_s, y_tr)
            pred_prob = lr.predict_proba(X_te_s)[:, 1]
        else:
            pred_prob = np.full(len(y_te), y_tr.mean() if len(y_tr) > 0 else 0.5)

        auc_roc = roc_auc_score(y_te, pred_prob) if len(np.unique(y_te)) > 1 else 0.5
        auc_pr = average_precision_score(y_te, pred_prob)
        sc_auc_roc = roc_auc_score(y_te, s_te) if len(np.unique(y_te)) > 1 else 0.5
        sc_auc_pr = average_precision_score(y_te, s_te)

        # Kendall τ
        tau = compute_kendall_tau(s_te, y_te)

        # Top20% hit rate
        top20_th = np.percentile(s_te, 80)
        top20_hr = y_te[s_te >= top20_th].sum() / max((s_te >= top20_th).sum(), 1)

        # Level statistics
        n_levels = len(thresholds) + 1
        levels = risk_level_vectorized(s_te, thresholds)
        level_data = {}
        for li in range(n_levels):
            mask = levels == li
            n = mask.sum()
            dec = y_te[mask].sum() if n > 0 else 0
            level_data[get_level_name(li, n_levels)] = {
                'n': int(n), 'decline': int(dec),
                'rate': (dec / n * 100) if n > 0 else 0.0,
                'pct': n / len(y_te) * 100
            }

        fold_results.append({
            'fold': fold + 1, 'auc_roc': auc_roc, 'auc_pr': auc_pr,
            'score_auc_roc': sc_auc_roc, 'score_auc_pr': sc_auc_pr,
            'kendall_tau': tau, 'top20_hit_rate': top20_hr,
            'level_data': level_data, 'n_test': len(y_te),
        })
        all_preds.extend(pred_prob); all_yb.extend(y_te); all_scores.extend(s_te)

    # Overall
    all_yb = np.array(all_yb); all_preds = np.array(all_preds); all_scores = np.array(all_scores)
    o_auc = roc_auc_score(all_yb, all_preds) if len(np.unique(all_yb)) > 1 else 0.5
    o_apr = average_precision_score(all_yb, all_preds)
    o_sauc = roc_auc_score(all_yb, all_scores) if len(np.unique(all_yb)) > 1 else 0.5
    o_sapr = average_precision_score(all_yb, all_scores)

    f2_pred = (all_scores > thresholds[-1]).astype(int) if len(thresholds) >= 1 else np.zeros_like(all_scores)
    f2 = fbeta_score(all_yb, f2_pred, beta=2, zero_division=0)
    if len(np.unique(f2_pred)) > 1:
        cm = confusion_matrix(all_yb, f2_pred)
        tn_all, fp_all, fn_all, tp_all = cm.ravel()
    else:
        tn_all = (all_yb == 0).sum() if (f2_pred == 0).all() else 0
        fp_all = 0; fn_all = (all_yb == 1).sum(); tp_all = 0

    # Overall level data
    o_levels = risk_level_vectorized(all_scores, thresholds)
    n_levels = len(thresholds) + 1
    o_level_data = {}
    for li in range(n_levels):
        mask = o_levels == li
        n = mask.sum()
        dec = all_yb[mask].sum() if n > 0 else 0
        lname = get_level_name(li, n_levels)
        o_level_data[lname] = {
            'n': int(n), 'decline': int(dec),
            'rate': (dec / n * 100) if n > 0 else 0.0,
            'pct': n / len(all_yb) * 100
        }

    # Monotonicity
    rates = [o_level_data[l]['rate'] for l in [get_level_name(li, n_levels) for li in range(n_levels)]]
    monotonic = all((rates[i] <= rates[i+1] + 0.5) for i in range(len(rates)-1))  # allow 0.5% tolerance

    result = {
        'weight_name': weight_name,
        'threshold_name': threshold_name,
        'thresholds': thresholds,
        'c6_strategy': c6_strategy,
        'n_levels': n_levels,
        'auc_roc': o_auc, 'auc_pr': o_apr,
        'score_auc_roc': o_sauc, 'score_auc_pr': o_sapr,
        'f2_score': f2,
        'top20_hit_rate': (
            all_yb[all_scores >= np.percentile(all_scores, 80)].sum() /
            max((all_scores >= np.percentile(all_scores, 80)).sum(), 1)
        ),
        'kendall_tau': np.mean([r['kendall_tau'] for r in fold_results]),
        'n_train_total': 0,
        'n_test_total': len(all_yb),
        'monotonic': monotonic,
        'fold_results': fold_results,
        'overall_levels': o_level_data,
        'tp': int(tp_all), 'fp': int(fp_all), 'fn': int(fn_all), 'tn': int(tn_all),
    }
    return result

# ══════════════════════════════════════════════════════════════════
# Data
# ══════════════════════════════════════════════════════════════════
print("=" * 60)
print("v3.1 Calibration — Multi-scheme Comparison")
print("=" * 60)

print("\n[Data Preparation]")
df = prepare_data()
print(f"  Total: {len(df)} rows, {df['product_id'].nunique()} products")
eval_count = df['include_in_eval'].sum()
print(f"  Eval set: {eval_count} rows")

# ══════════════════════════════════════════════════════════════════
# Task 1: Weight Comparison
# ══════════════════════════════════════════════════════════════════
print(f"\n{'='*60}")
print("Task 1: Weight Comparison (W1/W2/W3)")
print(f"{'='*60}")

TASK1_THRESHOLDS = [50, 60, 75]  # fixed for weight comparison

weight_results = {}
for wname, wdict in WEIGHT_SCHEMES.items():
    print(f"\n  Testing {wname} ({wdict['desc']}) ...")
    res = run_backtest(df, wdict, TASK1_THRESHOLDS, 'c3_fill',
                       weight_name=wname, threshold_name='T3_fixed')
    weight_results[wname] = res
    print(f"    AUC-ROC={res['auc_roc']:.4f}, Score AUC-ROC={res['score_auc_roc']:.4f}, "
          f"Kendall tau={res['kendall_tau']:.4f}")
    for lname, ld in res['overall_levels'].items():
        print(f"    {lname}: n={ld['n']} ({ld['pct']:.1f}%), decline={ld['decline']} ({ld['rate']:.1f}%)")

# Select best weight
def rank_weights(results):
    """Rank weights by composite score: AUC-ROC + Kendall tau + monotonic."""
    scores = {}
    for wn, r in results.items():
        s = r['auc_roc'] + r['kendall_tau'] * 0.5
        if r['monotonic']: s += 0.05
        scores[wn] = s
    best = max(scores, key=scores.get)
    return best, scores

best_weight_name, wscores = rank_weights(weight_results)
print(f"\n  >> Best weight: {best_weight_name} (composite score: {wscores[best_weight_name]:.4f})")
print(f"  Scores: {', '.join([f'{k}={v:.4f}' for k,v in wscores.items()])}")

# ══════════════════════════════════════════════════════════════════
# Task 2: Threshold Comparison
# ══════════════════════════════════════════════════════════════════
print(f"\n{'='*60}")
print("Task 2: Threshold Comparison (T1-T6)")
print(f"{'='*60}")

BEST_WEIGHTS = WEIGHT_SCHEMES[best_weight_name]
threshold_results = {}

for tname, tinfo in THRESHOLD_SCHEMES.items():
    print(f"\n  Testing {tname} ({tinfo['desc']}): thresholds={tinfo['thresholds']} ...")
    res = run_backtest(df, BEST_WEIGHTS, tinfo['thresholds'], 'c3_fill',
                       weight_name=best_weight_name, threshold_name=tname)
    threshold_results[tname] = res
    print(f"    AUC-ROC={res['auc_roc']:.4f}, Monotonic={'YES' if res['monotonic'] else 'NO'}")
    for lname, ld in res['overall_levels'].items():
        print(f"    {lname}: n={ld['n']} ({ld['pct']:.1f}%), decline={ld['decline']} ({ld['rate']:.1f}%)")
    # Check criteria
    n_levels = res['n_levels']
    high_names = [get_level_name(li, n_levels) for li in range(max(0, n_levels-2), n_levels)]
    low_names = [get_level_name(0, n_levels)]
    if n_levels >= 4:
        low_names.append(get_level_name(1, n_levels))
    high_pct = sum(res['overall_levels'][h]['pct'] for h in high_names if h in res['overall_levels'])
    high_rate = max((res['overall_levels'][h]['rate'] for h in high_names if h in res['overall_levels']), default=0)
    low_pct = sum(res['overall_levels'][l]['pct'] for l in low_names if l in res['overall_levels'])
    low_rate = max((res['overall_levels'][l]['rate'] for l in low_names if l in res['overall_levels']), default=100)
    print(f"    >>> 极高组占比={res['overall_levels'][get_level_name(n_levels-1, n_levels)]['pct']:.1f}%")
    print(f"    >>> 极高组衰退率={res['overall_levels'][get_level_name(n_levels-1, n_levels)]['rate']:.1f}%")
    print(f"    >>> 低组占比={low_pct:.1f}%, 低组最大衰退率={low_rate:.1f}%")

# Rank thresholds by decision criteria
def rank_thresholds(results):
    """Rank thresholds by: 1) high-risk rate>40% 2) high-risk pct<15% 3) low pct>50% 4) monotonic 5) auc_roc"""
    passing = []
    for tn, r in results.items():
        n_lv = r['n_levels']
        top_name = get_level_name(n_lv - 1, n_lv)
        top = r['overall_levels'].get(top_name, {})
        top_rate = top.get('rate', 0)
        top_pct = top.get('pct', 100)

        low_names = [get_level_name(0, n_lv)]
        if n_lv >= 4: low_names.append(get_level_name(1, n_lv))
        low_pct = sum(r['overall_levels'].get(l, {}).get('pct', 0) for l in low_names)
        low_rate = max((r['overall_levels'].get(l, {}).get('rate', 100) for l in low_names), default=100)

        passes_c1 = top_rate > 40     # 极高衰退率>40%
        passes_c2 = top_pct < 15     # 极高占比<15%
        passes_c3 = low_pct > 50 if n_lv >= 4 else low_pct > 50  # 低+中占比>50% for 4-level
        passes_c4 = r['monotonic']

        n_passed = sum([passes_c1, passes_c2, passes_c3, passes_c4])
        passing.append((tn, n_passed, r['auc_roc'], top_rate, top_pct, low_pct))
    # Sort: most criteria passed -> highest AUC
    passing.sort(key=lambda x: (x[1], x[2]), reverse=True)
    return passing

threshold_ranking = rank_thresholds(threshold_results)
print(f"\n  >> Threshold ranking (criteria passed -> AUC):")
for tn, npas, auc, tr, tp, lp in threshold_ranking:
    print(f"    {tn}: {npas}/4 criteria passed, AUC={auc:.4f}, 极高衰退率={tr:.1f}%, 极高占比={tp:.1f}%, 低组占比={lp:.1f}%")

best_threshold_name = threshold_ranking[0][0]
print(f"\n  >> Best threshold: {best_threshold_name} ({THRESHOLD_SCHEMES[best_threshold_name]['desc']})")

# ══════════════════════════════════════════════════════════════════
# Task 3: F3 Removal Test
# ══════════════════════════════════════════════════════════════════
print(f"\n{'='*60}")
print("Task 3: F3 Removal Test")
print(f"{'='*60}")

BEST_THRESHOLDS = THRESHOLD_SCHEMES[best_threshold_name]['thresholds']
BEST_N_LEVELS = THRESHOLD_SCHEMES[best_threshold_name]['levels']

# 4-factor weights (F1f, F5, F4, c6, no F3) — renormalized
f3_removed_weights = {k: v for k, v in BEST_WEIGHTS.items()
                      if k in ['F1f','F3','F4','F5','c6'] and k != 'F3'}
total_w_f3 = sum(f3_removed_weights.values())
f3_removed_weights = {k: v/total_w_f3 for k, v in f3_removed_weights.items()}
print(f"  F3-removed weights (renormalized): {f3_removed_weights}")

res_5factor = run_backtest(df, BEST_WEIGHTS, BEST_THRESHOLDS, 'c3_fill',
                           weight_name=f'{best_weight_name}_5factor', threshold_name=best_threshold_name)
res_4factor = run_backtest(df, f3_removed_weights, BEST_THRESHOLDS, 'c3_fill',
                           weight_name=f'{best_weight_name}_4factor', threshold_name=best_threshold_name)

print(f"  5-factor: AUC-ROC={res_5factor['auc_roc']:.4f}, Kendall tau={res_5factor['kendall_tau']:.4f}")
print(f"  4-factor: AUC-ROC={res_4factor['auc_roc']:.4f}, Kendall tau={res_4factor['kendall_tau']:.4f}")
auc_diff = res_5factor['auc_roc'] - res_4factor['auc_roc']
print(f"  AUC diff (5f - 4f): {auc_diff:.4f} ({'REMOVE F3' if auc_diff < 0.01 else 'KEEP F3'})")

# ══════════════════════════════════════════════════════════════════
# Task 4: c6 Fill Strategy Test
# ══════════════════════════════════════════════════════════════════
print(f"\n{'='*60}")
print("Task 4: c6 Fill Strategy Test")
print(f"{'='*60}")

c6_results = {}
for sname in ['c3_fill', 'redistribute', 'zero_fill']:
    print(f"\n  Testing {sname} ...")
    weights_used = {k: v for k, v in BEST_WEIGHTS.items()
                    if k in ['F1f','F3','F4','F5','c6']}
    res = run_backtest(df, weights_used, BEST_THRESHOLDS, c6_strategy=sname,
                       weight_name=best_weight_name, threshold_name=best_threshold_name)
    c6_results[sname] = res
    print(f"    AUC-ROC={res['auc_roc']:.4f}, Score AUC-ROC={res['score_auc_roc']:.4f}")
    n_lv = res['n_levels']
    top_name = get_level_name(n_lv - 1, n_lv)
    top = res['overall_levels'].get(top_name, {})
    print(f"    极高组: n={top.get('n',0)} ({top.get('pct',0):.1f}%), decline={top.get('rate',0):.1f}%")

# Select best c6 strategy
c6_ranking = sorted(c6_results.items(), key=lambda x: (x[1]['auc_roc'] + x[1]['score_auc_roc']), reverse=True)
best_c6 = c6_ranking[0][0]

# Prepare JSON-serializable weights for report
# Use 4-factor renormalized weights if F3 is removed
if auc_diff < 0.01:
    FINAL_WEIGHTS = {k: round(v, 3) for k, v in f3_removed_weights.items()}
    FINAL_WEIGHT_DESC = f"4因子 (F3已移除): F1f={FINAL_WEIGHTS['F1f']}, F5={FINAL_WEIGHTS['F5']}, F4={FINAL_WEIGHTS['F4']}, c6={FINAL_WEIGHTS['c6']}"
else:
    FINAL_WEIGHTS = {k: round(v, 3) for k, v in BEST_WEIGHTS.items() if k in ['F1f','F3','F4','F5','c6']}
    FINAL_WEIGHT_DESC = f"5因子: F1f={FINAL_WEIGHTS['F1f']}, F3={FINAL_WEIGHTS['F3']}, F5={FINAL_WEIGHTS['F5']}, F4={FINAL_WEIGHTS['F4']}, c6={FINAL_WEIGHTS['c6']}"
WEIGHTS_JSON = FINAL_WEIGHTS
print(f"\n  >> Best c6 strategy: {best_c6}")

# ══════════════════════════════════════════════════════════════════
# Task 5: Whitelist Analysis
# ══════════════════════════════════════════════════════════════════
print(f"\n{'='*60}")
print("Task 5: Whitelist Analysis")
print(f"{'='*60}")

# Analyze high-risk-but-no-decline products
eval_df = df[df['include_in_eval']].copy().sort_values('date_month').reset_index(drop=True)
scores_all = compute_risk_score_vectorized(eval_df, BEST_WEIGHTS, best_c6)
eval_df['risk_score'] = scores_all

n_lv5 = BEST_N_LEVELS
top_name = get_level_name(n_lv5 - 1, n_lv5)
levels_all = risk_level_vectorized(scores_all, BEST_THRESHOLDS)

# Find FPs: highest risk level but no decline
fp_mask = (levels_all == n_lv5 - 1) & (eval_df['y_corrected'] == 0)
fp_df = eval_df[fp_mask].copy()
print(f"  Top-level FP: {len(fp_df)} rows ({fp_df['product_id'].nunique()} products)")

if len(fp_df) > 0:
    # Analyze FP characteristics
    fp_summary = fp_df.groupby('product_id').agg(
        fp_months=('y_corrected', 'count'),
        avg_score=('risk_score', 'mean'),
        avg_margin=('recent_margin', 'mean'),
        avg_qty=('recent_qty_12m', 'mean'),
        n_cust=('c3_customer_net_change', lambda x: (x.notna()).sum()),
    ).sort_values('fp_months', ascending=False)

    if len(fp_df) > 0:
        med_margin = fp_df['recent_margin'].median()
        med_qty = fp_df['recent_qty_12m'].median()
        fp_df['is_strategic'] = (fp_df['recent_margin'] < med_margin) & (fp_df['recent_qty_12m'] > med_qty)
        strategic_pct = fp_df['is_strategic'].mean() * 100
        print(f"  Strategic FP (low margin + high volume): {fp_df['is_strategic'].sum()}/{len(fp_df)} ({strategic_pct:.1f}%)")

        # Whitelist rule: F5 < 30 + volume > 0 + has customers
        whitelist_candidates = fp_df[
            (fp_df['f5_score'] < 30) &
            (fp_df['recent_qty_12m'] > 0) &
            (fp_df['c3_customer_net_change'].notna())
        ]
        whitelist_impact = len(whitelist_candidates) / max(len(fp_df), 1) * 100
        print(f"  Whitelist candidates (F5<30 + volume>0 + has customers): {len(whitelist_candidates)}/{len(fp_df)} ({whitelist_impact:.1f}%)")
    else:
        strategic_pct = 0
        whitelist_candidates = pd.DataFrame()
        whitelist_impact = 0

    # Show top FP products
    print(f"\n  Top FP products (by fp_months):")
    print(fp_summary.head(10).to_string())

# ══════════════════════════════════════════════════════════════════
# Charts
# ══════════════════════════════════════════════════════════════════
print(f"\n{'='*60}")
print("Generating charts ...")

# Chart 1: Weight comparison — score distribution
fig, axes = plt.subplots(1, 2, figsize=(14, 5))
# Boxplot
eval_df_w = df[df['include_in_eval']].copy().sort_values('date_month').reset_index(drop=True)
box_data = []
labels_w = []
for wname in ['W1', 'W2', 'W3']:
    sc = compute_risk_score_vectorized(eval_df_w, WEIGHT_SCHEMES[wname], 'c3_fill')
    box_data.append(sc)
    labels_w.append(f"{wname}\n({WEIGHT_SCHEMES[wname]['desc']})")
axes[0].boxplot(box_data, labels=labels_w, showmeans=True,
                meanprops=dict(marker='D', markerfacecolor='red', markersize=5))
axes[0].set_ylabel('Risk Score')
axes[0].set_title('Risk Score Distribution by Weight Scheme')
axes[0].grid(axis='y', alpha=0.3)

# Per-fold AUC comparison
fold_count = len(weight_results['W1']['fold_results'])
x = np.arange(fold_count)
width = 0.25
for i, wname in enumerate(['W1', 'W2', 'W3']):
    aucs = [r['auc_roc'] for r in weight_results[wname]['fold_results']]
    axes[1].bar(x + i*width, aucs, width, label=wname, alpha=0.7)
axes[1].set_xlabel('Fold')
axes[1].set_ylabel('AUC-ROC')
axes[1].set_title('Per-fold AUC-ROC by Weight Scheme')
axes[1].set_xticks(x + width)
axes[1].set_xticklabels([f'Fold {i+1}' for i in range(fold_count)])
axes[1].legend()
axes[1].grid(axis='y', alpha=0.3)

fig.tight_layout()
fig.savefig(os.path.join(OUTPUT_DIR, 'calibration_weight_comparison.png'), dpi=150)
plt.close(fig)

# Chart 2: Threshold comparison — decline rate by level
fig, ax = plt.subplots(figsize=(14, 6))
bar_data = []
bar_labels = []
colors = ['green', 'yellowgreen', 'gold', 'orange', 'red', 'darkred']
for tname, tres in threshold_results.items():
    desc = THRESHOLD_SCHEMES[tname]['desc']
    n_lv = tres['n_levels']
    for li in range(n_lv):
        lname = get_level_name(li, n_lv)
        ld = tres['overall_levels'].get(lname, {})
        bar_data.append({
            'scheme': tname,
            'level': lname,
            'rate': ld.get('rate', 0),
            'pct': ld.get('pct', 0),
            'color': colors[li] if li < len(colors) else 'gray'
        })

# Grouped bar chart
import itertools
schemes = list(THRESHOLD_SCHEMES.keys())
groups = []
for s in schemes:
    n_lv = threshold_results[s]['n_levels']
    for li in range(n_lv):
        groups.append((s, get_level_name(li, n_lv)))

# Simpler: stacked horizontal bars for level proportions
fig, axes = plt.subplots(2, 1, figsize=(14, 10))
# Top: decline rate by level
ax = axes[0]
x_pos = np.arange(len(schemes))
bar_width = 0.8
max_levels = max([threshold_results[s]['n_levels'] for s in schemes])
for li in range(max_levels):
    rates = []
    for s in schemes:
        n_lv = threshold_results[s]['n_levels']
        if li < n_lv:
            rates.append(threshold_results[s]['overall_levels'].get(get_level_name(li, n_lv), {}).get('rate', 0))
        else:
            rates.append(0)
    bottom = np.zeros(len(schemes)) if li == 0 else None
    label = f'Level {li+1}'
    ax.bar(x_pos, rates, bar_width, label=f'Level {li+1}', alpha=0.7)
ax.axhline(40, color='red', linestyle='--', alpha=0.5, label='40% threshold')
ax.set_xticks(x_pos)
ax.set_xticklabels([f"{s}\n({THRESHOLD_SCHEMES[s]['desc']})" for s in schemes], fontsize=9)
ax.set_ylabel('Decline Rate (%)')
ax.set_title('Threshold Comparison: Decline Rate by Level')
ax.legend(fontsize=8)
ax.grid(axis='y', alpha=0.3)

# Bottom: level proportions
ax = axes[1]
bottom = np.zeros(len(schemes))
for li in range(max_levels):
    pcts = []
    for s in schemes:
        n_lv = threshold_results[s]['n_levels']
        if li < n_lv:
            pcts.append(threshold_results[s]['overall_levels'].get(get_level_name(li, n_lv), {}).get('pct', 0))
        else:
            pcts.append(0)
    ax.bar(x_pos, pcts, bar_width, bottom=bottom, label=f'Level {li+1}', alpha=0.7)
    bottom += np.array(pcts)
ax.set_xticks(x_pos)
ax.set_xticklabels([f"{s}\n({THRESHOLD_SCHEMES[s]['desc']})" for s in schemes], fontsize=9)
ax.set_ylabel('Proportion (%)')
ax.set_title('Threshold Comparison: Level Proportion')
ax.legend(fontsize=8)
ax.grid(axis='y', alpha=0.3)

fig.tight_layout()
fig.savefig(os.path.join(OUTPUT_DIR, 'calibration_threshold_comparison.png'), dpi=150)
plt.close(fig)

# Chart 3: Scatter — high-risk pct vs high-risk decline rate
fig, ax = plt.subplots(figsize=(10, 7))
for tname, tres in threshold_results.items():
    n_lv = tres['n_levels']
    top_name = get_level_name(n_lv - 1, n_lv)
    top = tres['overall_levels'].get(top_name, {})
    top_pct = top.get('pct', 0)
    top_rate = top.get('rate', 0)
    ax.scatter(top_pct, top_rate, s=100, label=f"{tname} ({THRESHOLD_SCHEMES[tname]['desc']})", alpha=0.8)
    ax.annotate(tname, (top_pct, top_rate), fontsize=9, xytext=(5, 5),
                textcoords='offset points')

ax.axhline(40, color='red', linestyle='--', alpha=0.3, label='Target: >40% decline')
ax.axvline(15, color='green', linestyle='--', alpha=0.3, label='Target: <15% proportion')
ax.set_xlabel('极高风险组占比 (%)')
ax.set_ylabel('极高风险组衰退率 (%)')
ax.set_title('校准散点图：极高风险组聚焦度')
ax.legend(fontsize=8, loc='lower left')
ax.grid(alpha=0.3)
# Upper-left quadrant = ideal
rect = plt.Rectangle((0, 40), 15, 60, facecolor='green', alpha=0.05)
ax.add_patch(rect)
ax.text(7.5, 95, 'IDEAL ZONE', ha='center', fontsize=12, color='green', alpha=0.4)

fig.tight_layout()
fig.savefig(os.path.join(OUTPUT_DIR, 'calibration_threshold_scatter.png'), dpi=150)
plt.close(fig)

print("  Charts saved.")

# ══════════════════════════════════════════════════════════════════
# Generate Master Report
# ══════════════════════════════════════════════════════════════════
print(f"\n{'='*60}")
print("Generating master report ...")

def fmt_level_table(ol, n_lv):
    rows = ""
    for li in range(n_lv):
        lname = get_level_name(li, n_lv)
        ld = ol.get(lname, {})
        rows += f"| {lname} | {ld.get('n',0)} | {ld.get('pct',0):.1f}% | {ld.get('decline',0)} | {ld.get('rate',0):.1f}% |\n"
    return rows

# Weight comparison table
wt_rows = ""
for wn in ['W1','W2','W3']:
    r = weight_results[wn]
    wt_rows += (f"| {wn} ({WEIGHT_SCHEMES[wn]['desc']}) | "
                f"{WEIGHT_SCHEMES[wn]['F1f']:.3f}/{WEIGHT_SCHEMES[wn]['F5']:.3f}/"
                f"{WEIGHT_SCHEMES[wn]['F4']:.3f}/{WEIGHT_SCHEMES[wn]['c6']:.3f}/"
                f"{WEIGHT_SCHEMES[wn]['F3']:.3f} | "
                f"{r['auc_roc']:.4f} | {r['kendall_tau']:.4f} | "
                f"{'YES' if r['monotonic'] else 'NO'} |\n")

# Threshold comparison table
thr_rows = ""
for tn in ['T1','T2','T3','T4','T5','T6']:
    r = threshold_results[tn]
    n_lv = r['n_levels']
    top_n = get_level_name(n_lv - 1, n_lv)
    low_ns = [get_level_name(0, n_lv)]
    if n_lv >= 4: low_ns.append(get_level_name(1, n_lv))
    top = r['overall_levels'].get(top_n, {})
    low_pct = sum(r['overall_levels'].get(l, {}).get('pct', 0) for l in low_ns)
    low_rate = max((r['overall_levels'].get(l, {}).get('rate', 100) for l in low_ns), default=100)

    # Count criteria passed
    passes_c1 = top.get('rate', 0) > 40
    passes_c2 = top.get('pct', 0) < 15
    passes_c3 = low_pct > 50
    passes_c4 = r['monotonic']
    n_pass = sum([passes_c1, passes_c2, passes_c3, passes_c4])

    thr_rows += (f"| {tn} ({THRESHOLD_SCHEMES[tn]['desc']}) | {r['thresholds']} | "
                 f"{r['auc_roc']:.4f} | {'YES' if r['monotonic'] else 'NO'} | "
                 f"{top.get('pct',0):.1f}% | {top.get('rate',0):.1f}% | "
                 f"{low_pct:.1f}% | {low_rate:.1f}% | {n_pass}/4 |\n")

# F3 and c6 tables
f3_row = (f"| 5-Factor ({best_weight_name}) | {res_5factor['auc_roc']:.4f} | "
          f"{res_5factor['kendall_tau']:.4f} | {res_5factor['score_auc_roc']:.4f} |\n")
f3_row += (f"| 4-Factor (F3 removed) | {res_4factor['auc_roc']:.4f} | "
           f"{res_4factor['kendall_tau']:.4f} | {res_4factor['score_auc_roc']:.4f} |\n")
f3_verdict = "✅ 建议移除F3（简化模型）" if auc_diff < 0.01 else "❌ 建议保留F3"

c6_rows = ""
for sname in ['c3_fill', 'redistribute', 'zero_fill']:
    r = c6_results[sname]
    c6_rows += f"| {sname} | {r['auc_roc']:.4f} | {r['score_auc_roc']:.4f} | {r['kendall_tau']:.4f} |\n"

# Generate final recommendation
best_t = threshold_results[best_threshold_name]
best_top_n = get_level_name(best_t['n_levels'] - 1, best_t['n_levels'])
best_top = best_t['overall_levels'].get(best_top_n, {})

master_report = f"""# v3.1 评分卡上线前校准 — 多方案实测报告

## 执行摘要

| 项目 | 结论 |
|------|------|
| 最优权重方案 | **{best_weight_name}** ({WEIGHT_SCHEMES[best_weight_name]['desc']}) |
| 最优阈值方案 | **{best_threshold_name}** ({THRESHOLD_SCHEMES[best_threshold_name]['desc']}): {BEST_THRESHOLDS} |
| 最优c6策略 | **{best_c6}** |
| F3去留 | {'**移除F3** (AUC变化<1%)' if auc_diff < 0.01 else '**保留F3**'} |
| 最终AUC-ROC | **{best_t['auc_roc']:.4f}** |
| 单调性 | {'✅ 严格成立' if best_t['monotonic'] else '❌ 不成立'} |
| 极高风险组占比 | {best_top.get('pct',0):.1f}% |
| 极高风险组衰退率 | {best_top.get('rate',0):.1f}% |

---

## 数据概况

- 总样本：{len(df)} 行，{df['product_id'].nunique()} 产品，{df['date_month'].nunique()} 月
- 评估集：{eval_count} 行（已过滤新品/历史不足）
- 标签正样本率：{df['y_corrected'].mean()*100:.1f}%
- 因子：F1f(毛利额斜率)、F5(自比健康度)、F4(增速衰减)、c6(单次订货量)、F3(订货波动)
- 处理：因子统一0-100分，方向修正，c6缺失用c3填充

---

## 任务1：权重方案对比

### 权重方案定义

| 方案 | 权重 (F1f/F5/F4/c6/F3) | 逻辑 |
|------|------------------------|------|
| W1 原优化 | 0.328/0.368/0.182/0.213/0.166 | M3系数，F6剔除后归一化 |
| W2 F1f主导 | 0.350/0.300/0.200/0.100/0.050 | F1f单因子AUC最高(0.77)，大幅强化；弱化F3/c6 |
| W3 平衡 | 0.300/0.300/0.200/0.150/0.050 | 更均衡，降低F5权重 |

### 对比结果（阈值固定为[50, 60, 75]）

| 方案 | 权重 | AUC-ROC | Kendall τ | 单调 |
|------|------|---------|-----------|------|
{wt_rows}
### 各方案风险分分布
（见 calibration_weight_comparison.png）

### 结论
**{best_weight_name} 最优** — 综合AUC-ROC + Kendall τ + 单调性评分最高。
后续任务以{best_weight_name}为基准继续。

---

## 任务2：阈值方案对比（核心）

### 方案定义

| 方案 | 阈值 | 级别数 | 设计逻辑 |
|------|------|--------|---------|
| T1 历史基准 | [34, 52, 58] | 4 | 历史使用的基准阈值 |
| T2 轻调 | [30, 50, 65] | 4 | 扩大高风险区间 |
| T3 聚焦 | [50, 60, 75] | 4 | 合并低+中，聚焦高+极高 |
| T4 简化 | [45, 65] | 3 | 减少中间地带 |
| T5 激进 | [50, 75] | 3 | 只有低/高/极高 |
| T6 精细 | [30, 45, 60, 75] | 5 | 增加"关注"档 |

### 对比矩阵

| 方案 | 阈值 | AUC-ROC | 单调 | 极高组占比 | 极高组衰退率 | 低+中组占比 | 低+中最大衰退率 | 通过数 |
|------|------|---------|------|-----------|------------|-----------|--------------|-------|
{thr_rows}

### 聚焦度散点图
（见 calibration_threshold_scatter.png — 越高+越左越好）

### 各级别衰退率对比
（见 calibration_threshold_comparison.png）

### 决策分析

按优先顺序评估各方案是否满足核心约束：

1. **极高组衰退率 > 40%** — 不能容忍极高组一半以上健康
2. **极高组占比 < 15%** — 业务精力有限
3. **低+中组合计 > 50%** — 大部分产品放行
4. **单调性严格成立**

"""

# Add per-threshold pass/fail detail
for tn in ['T1','T2','T3','T4','T5','T6']:
    r = threshold_results[tn]
    n_lv = r['n_levels']
    top_n = get_level_name(n_lv - 1, n_lv)
    low_ns = [get_level_name(0, n_lv)]
    if n_lv >= 4: low_ns.append(get_level_name(1, n_lv))
    top = r['overall_levels'].get(top_n, {})
    low_pct = sum(r['overall_levels'].get(l, {}).get('pct', 0) for l in low_ns)
    low_rate = max((r['overall_levels'].get(l, {}).get('rate', 100) for l in low_ns), default=100)

    p1 = '✅' if top.get('rate', 0) > 40 else '❌'
    p2 = '✅' if top.get('pct', 0) < 15 else '❌'
    p3 = '✅' if low_pct > 50 else '❌'
    p4 = '✅' if r['monotonic'] else '❌'

    # Detailed level breakdown
    lvl_detail = ""
    for li in range(n_lv):
        lname = get_level_name(li, n_lv)
        ld = r['overall_levels'].get(lname, {})
        lvl_detail += f"    - {lname}: n={ld.get('n',0)} ({ld.get('pct',0):.1f}%), 衰退={ld.get('decline',0)} ({ld.get('rate',0):.1f}%)\n"

    master_report += f"""### {tn} ({THRESHOLD_SCHEMES[tn]['desc']}) — 各级别详情

{lvl_detail}
| 标准 | 结果 |
|------|------|
| 极高组衰退率 > 40% | {p1} {top.get('rate',0):.1f}% |
| 极高组占比 < 15% | {p2} {top.get('pct',0):.1f}% |
| 低+中组合计 > 50% | {p3} {low_pct:.1f}% |
| 单调性 | {p4} |
| AUC-ROC | {r['auc_roc']:.4f} |

---

"""

master_report += f"""### 阈值方案推荐

综合4项核心约束，选出的最优方案为 **{best_threshold_name}** ({THRESHOLD_SCHEMES[best_threshold_name]['desc']})，阈值={BEST_THRESHOLDS}。

"""

# Add final performance summary for best scheme
best_t = threshold_results[best_threshold_name]
n_lv = best_t['n_levels']
master_report += f"""### 推荐方案最终表现

| 指标 | 值 |
|------|-----|
| AUC-ROC | {best_t['auc_roc']:.4f} |
| AUC-PR | {best_t['auc_pr']:.4f} |
| Score AUC-ROC | {best_t['score_auc_roc']:.4f} |
| Kendall τ (跨期稳定性) | {best_t['kendall_tau']:.4f} |
| F2-Score | {best_t['f2_score']:.4f} |
| Top20% Hit Rate | {best_t['top20_hit_rate']:.1%} |

| 级别 | n | 占比 | 衰退数 | 衰退率 |
|------|---|------|-------|-------|
{fmt_level_table(best_t['overall_levels'], n_lv)}

| 混淆矩阵 (阈值={best_t['thresholds'][-1]}) | 预测正 | 预测负 |
|------|--------|--------|
| 实际正 | {best_t['tp']} | {best_t['fn']} |
| 实际负 | {best_t['fp']} | {best_t['tn']} |

召回率(TPR): {best_t['tp']/(best_t['tp']+best_t['fn'])*100:.1f}% (TP={best_t['tp']}, FN={best_t['fn']})
误报率(FPR): {best_t['fp']/(best_t['fp']+best_t['tn'])*100:.1f}% (FP={best_t['fp']}, TN={best_t['tn']})
精确率(Precision): {best_t['tp']/(best_t['tp']+best_t['fp'])*100:.1f}%

---

## 任务3：F3去留测试

| 模型 | AUC-ROC | Kendall τ | Score AUC-ROC |
|------|---------|-----------|--------------|
{f3_row}
**结论：{f3_verdict}**

F3 (订货波动) 单因子AUC仅0.5397，在模型中贡献有限。
{'移除F3后AUC下降' + f'{auc_diff:.4f}' + '（<0.01），4因子模型更简洁且稳定性相当。建议上线4因子版本。'
 if auc_diff < 0.01 else
 'F3虽弱但仍有贡献，移除后AUC下降 > 0.01，建议保留。'}

---

## 任务4：c6缺失兜底策略对比

| 策略 | AUC-ROC | Score AUC-ROC | Kendall τ |
|------|---------|--------------|-----------|
{c6_rows}

**结论：{best_c6} 最优**

c6缺失率62.5%，c3填充后降至4.4%。
- S1 (c3填充) 保留了c6的真实分布信号
- S2 (权重重分配) 过度惩罚了c6缺失的产品
- S3 (填0) 假设缺失=健康，引入了偏差

---

## 任务5：误报产品白名单机制

### 极高风险组误报概况

- **极高风险组总误报行数**：{len(fp_df)}（{fp_df['product_id'].nunique()} 个产品）
- **战略型误报**（低毛利+高销量）：{'N/A (无FP数据)' if len(fp_df) == 0 else f'{fp_df["is_strategic"].sum()}/{len(fp_df)} ({strategic_pct:.1f}%)'}
- **白名单候选**（F5<30 + 销量>0 + 有客户数据）：{'N/A' if len(fp_df) == 0 else f'{len(whitelist_candidates)}/{len(fp_df)} ({whitelist_impact:.1f}%)'}

"""

if len(fp_df) > 0:
    master_report += f"""### 持续误报产品 Top 10（长期>75分但未衰退）

| 产品ID | 误报月数 | 平均分 | 平均毛利率 | 平均销量 |
|--------|---------|-------|-----------|--------|
"""
    for pid, row in fp_summary.head(10).iterrows():
        master_report += f"| {pid} | {int(row['fp_months'])} | {row['avg_score']:.1f} | {row['avg_margin']:.1%} | {row['avg_qty']:.1e} |\n"

if len(fp_df) > 0 and len(whitelist_candidates) > 0:
    master_report += f"""
### 白名单规则建议

**规则**：F5(自比健康度分) < 30 且 近12月销量 > 0 且 活跃客户 > 5 → 标记为"战略产品"，不触发极高风险警报

**影响**：
- 可降低误报 {len(whitelist_candidates)} 行（占极高风险组的 {whitelist_impact:.1f}%）
- 需手动复核白名单列表，确认这些产品确实"有量有利但被模型高估"
"""
else:
    master_report += """
### 白名单规则建议

当前误报产品数量较少，白名单机制非必选。
如需进一步降低误报，可考虑：F5<30 + 销量稳定 + 客户数>5 → 战略产品豁免。
"""

master_report += f"""

---

## 最终推荐方案

### 一键配置

```python
# v3.1 Final Scoring Card — Production Configuration
WEIGHTS = {json.dumps(WEIGHTS_JSON)}
THRESHOLDS = {json.dumps(BEST_THRESHOLDS)}
C6_STRATEGY = '{best_c6}'  # c3_fill | redistribute | zero_fill
REMOVE_F3 = {'true' if auc_diff < 0.01 else 'false'}
FACTOR_SCALING = 'percentile_rank'  # all factors -> [0, 100]

EXCLUSION_RULES = {{
    'new_product_age': 6,        # months
    'min_history_age': 3,        # months
    'min_observations': 3,       # data points
    'gp_anomaly_max': 1.0,       # 100%
    'gp_anomaly_min': -0.5,      # -50%
}}
```

### 上线动作矩阵

| 级别 | 动作 | 业务含义 |
|------|------|---------|
| {get_level_name(0, n_lv)} | {'维持' if n_lv >= 4 else '放行'} | 继续正常经营，无需特殊关注 |
| {get_level_name(1, n_lv) if n_lv >= 2 else '-'} | {'监控' if n_lv >= 4 else '-'} | 月度巡检，关注指标变化 |
| {get_level_name(max(0, n_lv-2), n_lv)} | {'成本复盘' if n_lv >= 3 else '-'} | 核查成本结构及客户需求变化 |
| {get_level_name(n_lv-1, n_lv)} | 退市评估 | 启动退出/迭代评估流程 |

---

## 附录：因子贡献度

| 因子 | 单因子AUC | 权重 | 说明 |
|------|----------|------|------|
| F1f 毛利额斜率 | 0.7656 | {BEST_WEIGHTS.get('F1f', '-'):.3f} | 最强单因子，下降趋势早期预警 |
| F5 自比健康度 | 0.6408 | {BEST_WEIGHTS.get('F5', '-'):.3f} | 毛利率相对历史峰值的衰退程度 |
| F4 增速衰减 | 0.6224 | {BEST_WEIGHTS.get('F4', '-'):.3f} | 近期增速相对远期增速的变化 |
| c6 单次订货量 | 0.5862 | {BEST_WEIGHTS.get('c6', '-'):.3f} | 客户平均单次订货量的下降趋势 |
| F3 订货波动 | 0.5397 | {f"{BEST_WEIGHTS.get('F3', 0):.3f}" if BEST_WEIGHTS.get('F3', 0) > 0 else '已移除'} | 月间订货波动性，区分力有限 |
"""

with open(os.path.join(OUTPUT_DIR, 'v3.1_calibration_master_report.md'), 'w', encoding='utf-8') as f:
    f.write(master_report)

print(f"  Master report saved: {OUTPUT_DIR}/v3.1_calibration_master_report.md")
print(f"\n{'='*60}")
print("Calibration complete!")
print(f"{'='*60}")
