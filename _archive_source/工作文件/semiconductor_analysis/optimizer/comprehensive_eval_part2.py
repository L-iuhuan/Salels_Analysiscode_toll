"""
Continue comprehensive evaluation from Perspective 7 onwards.
Uses saved df_v4 data to avoid re-running everything.
"""
import os, sys, json, warnings
warnings.filterwarnings("ignore")
import pandas as pd
import numpy as np

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

OUT_DIR = os.path.join(_PROJECT_ROOT, "output", "optimization", "comprehensive_eval")
print("OUT_DIR:", OUT_DIR)
print("Exists:", os.path.isdir(OUT_DIR))
os.makedirs(OUT_DIR, exist_ok=True)

LABEL_COL = "decline_label_6m"

# Reload data
from optimizer.data_loader import load_optimization_data
from optimizer.scoring_v2 import score_panel_v2
from optimizer.metrics import compute_classification_metrics

print("Loading data...")
df = load_optimization_data()
labeled = df[df[LABEL_COL].notna()].copy()
y_true = labeled[LABEL_COL].values

OPTIMAL_WEIGHTS_4F = {"F1f": 0.100, "F4": 0.600, "F5": 0.200, "c6": 0.100}
OPTIMAL_THRESHOLDS = [55, 65, 71]
CURRENT_WEIGHTS_3F = {"F1f": 0.411, "F4": 0.236, "F5": 0.353}
CURRENT_THRESHOLDS = [50, 60, 75]

def classify_risk(score, thr):
    if score <= thr[0]: return "low"
    elif score <= thr[1]: return "mid"
    elif score <= thr[2]: return "high"
    else: return "extreme"

print("Scoring v4.0...")
df_v4 = score_panel_v2(labeled, OPTIMAL_WEIGHTS_4F, use_c6=True)
df_v4["risk_level_v4"] = df_v4["score_v2"].apply(lambda s: classify_risk(s, OPTIMAL_THRESHOLDS))

print("Scoring v2.9...")
df_current = score_panel_v2(labeled, CURRENT_WEIGHTS_3F, use_c6=False)
df_current["risk_level_current"] = df_current["score_v2"].apply(
    lambda s: classify_risk(s, CURRENT_THRESHOLDS))

df_v4["score_current"] = df_current["score_v2"]
df_v4["risk_level_current"] = df_current["risk_level_current"]

all_results = {}

# ════════════════════════════════════════════════════════════════
# PERSPECTIVE 7: INTERPRETABILITY
# ════════════════════════════════════════════════════════════════
print("\n" + "="*70)
print("PERSPECTIVE 7: INTERPRETABILITY — Score decomposition")
print("="*70)

# 7A: Factor driving extreme
print("\n--- 7A: Which factor drives extreme risk? ---")
for f in ["f4_v2", "f5_v2", "f1f_v2"]:
    high_f = df_v4[df_v4[f] >= 70]
    ext_among_high = high_f[high_f["risk_level_v4"]=="extreme"]
    if len(high_f) > 0:
        pct = len(ext_among_high)/len(high_f)*100
        print(f"  {f}: {len(high_f)} rows with >=70 -> {len(ext_among_high)} extreme ({pct:.1f}%)")

# 7B: Average factor profile by risk level
print("\n--- 7B: Average factor scores by risk level ---")
prof_cols = ["score_v2", "f1f_v2", "f4_v2", "f5_v2"]
if "c6_v2" in df_v4.columns: prof_cols.append("c6_v2")
profile = df_v4.groupby("risk_level_v4")[prof_cols].mean().round(2)
print(profile.to_string())

# 7C: Case studies
print("\n--- 7C: Case studies ---")
case_cols = ["product_id", "date_month", "risk_level_v4", "score_v2",
             "f1f_v2", "f4_v2", "f5_v2", "recent_margin", "decay_pp",
             "self_health", "portrait", "momentum"]

extreme_subset = df_v4[df_v4["risk_level_v4"]=="extreme"]
for label_val, label_name in [(1, "TRUE POSITIVES"), (0, "FALSE POSITIVES")]:
    subset = extreme_subset[extreme_subset[LABEL_COL]==label_val]
    if len(subset) == 0: continue
    cases = subset.nlargest(min(3, len(subset)), "score_v2")
    print(f"\n  Top {min(3,len(subset))} {label_name} (extreme risk, highest scores):")
    for _, row in cases.iterrows():
        print(f"    {str(row['product_id']):12s} | {row['date_month']} | "
              f"score={row['score_v2']:.0f} | F1f={row['f1f_v2']} F4={row['f4_v2']} "
              f"F5={row['f5_v2']} | margin={row['recent_margin']:.3f} | "
              f"decay={row['decay_pp']:.1f} | sh={row['self_health']:.2f}")

# 7D: Score distribution by factor
print("\n--- 7D: Score distribution by factor ---")
for f in ["f1f_v2", "f4_v2", "f5_v2"]:
    dist = df_v4[f].value_counts().sort_index()
    print(f"  {f}: {dict(dist)}")

# ════════════════════════════════════════════════════════════════
# PERSPECTIVE 8: BUSINESS IMPACT
# ════════════════════════════════════════════════════════════════
print("\n" + "="*70)
print("PERSPECTIVE 8: BUSINESS IMPACT — v4.0 vs v2.9")
print("="*70)

def confusion_metrics(df_in, score_col, thr_high):
    y = df_in[LABEL_COL].values
    pred = (df_in[score_col].values > thr_high)
    tp = int((pred & (y==1)).sum())
    fp = int((pred & (y==0)).sum())
    fn = int((~pred & (y==1)).sum())
    tn = int((~pred & (y==0)).sum())
    prec = tp/max(tp+fp,1)
    rec = tp/max(tp+fn,1)
    f1 = 2*prec*rec/max(prec+rec,1e-10)
    return {"tp":tp,"fp":fp,"fn":fn,"tn":tn,
            "precision":round(prec,4),"recall":round(rec,4),"f1":round(f1,4),
            "n_extreme":tp+fp,"extreme_pct":(tp+fp)/len(df_in),
            "base_rate":y.mean()}

v4 = confusion_metrics(df_v4, "score_v2", OPTIMAL_THRESHOLDS[2])
cur = confusion_metrics(df_current, "score_v2", CURRENT_THRESHOLDS[2])

print(f"\n  {'Metric':25s} {'v2.9 Current':15s} {'v4.0 Optimized':15s} {'Delta':10s}")
print(f"  {'-'*25} {'-'*15} {'-'*15} {'-'*10}")
for k in ["n_extreme", "extreme_pct", "precision", "recall", "f1", "tp", "fp", "fn", "tn"]:
    v = cur.get(k, "?")
    v2 = v4.get(k, "?")
    if isinstance(v, (int, float)) and isinstance(v2, (int, float)):
        if isinstance(v, float) and k not in ["tp","fp","fn","tn"]:
            d = v2 - v
            print(f"  {k:25s} {v*100:>8.1f}%     {v2*100:>8.1f}%     {d*100:>+8.1f}%")
        else:
            d = v2 - v
            print(f"  {k:25s} {v:>8d}     {v2:>8d}     {d:+8d}")

# ROC AUC comparison
from sklearn.metrics import roc_auc_score
auc_v4 = roc_auc_score(y_true, df_v4["score_v2"].values)
auc_cur = roc_auc_score(y_true, df_current["score_v2"].values)
print(f"\n  ROC AUC: v2.9={auc_cur:.4f}, v4.0={auc_v4:.4f}, +{(auc_v4-auc_cur):.4f}")

# Top-k precision
print(f"\n  Top-k precision (v4.0):")
scores = df_v4["score_v2"].values
order = np.argsort(-scores)
sorted_y = y_true[order]
for k in [50, 100, 200, 500, 1000]:
    if k > len(sorted_y): continue
    pk = sorted_y[:k].mean()
    print(f"    Top {k:5d}: precision={pk:.3f} ({int(sorted_y[:k].sum())}/{k})")

# Cost-benefit estimation
print(f"\n  Estimated business impact (per 1000 products screened):")
print(f"    v2.9: ~{int(1000*cur['extreme_pct'])} flagged, "
      f"{int(1000*cur['extreme_pct']*cur['precision'])} correct, "
      f"{int(1000*cur['extreme_pct']*(1-cur['precision']))} false alarms")
print(f"    v4.0: ~{int(1000*v4['extreme_pct'])} flagged, "
      f"{int(1000*v4['extreme_pct']*v4['precision'])} correct, "
      f"{int(1000*v4['extreme_pct']*(1-v4['precision']))} false alarms")
fp_diff = int(1000*cur['extreme_pct']*(1-cur['precision'])) - int(1000*v4['extreme_pct']*(1-v4['precision']))
print(f"    FP reduction: {fp_diff} fewer false alarms per 1000")

# ════════════════════════════════════════════════════════════════
# PERSPECTIVE 9: ROBUSTNESS CHECKS (replacing cross-check in original)
# ════════════════════════════════════════════════════════════════
print("\n" + "="*70)
print("PERSPECTIVE 9: ROBUSTNESS & SANITY CHECKS")
print("="*70)

# 9A: Are extreme scores driven by actual factors?
extreme = df_v4[df_v4["risk_level_v4"]=="extreme"]
any_high = ((extreme["f4_v2"]>=70) | (extreme["f5_v2"]>=70) | (extreme["f1f_v2"]>=70)).sum()
print(f"  Extreme products with >=1 factor score >=70: {any_high}/{len(extreme)} ({any_high/len(extreme)*100:.1f}%)")

c6_only = ((extreme["c6_v2"]>=70) & (extreme["f4_v2"]<70) & (extreme["f5_v2"]<70) & (extreme["f1f_v2"]<70)).sum()
if "c6_v2" in df_v4.columns:
    print(f"  Extreme driven SOLELY by c6 (no other factor>=70): {c6_only}")

# 9B: Blind spots - products never flagged
flagged_products = df_v4[df_v4["risk_level_v4"]=="extreme"]["product_id"].nunique()
total_products = df_v4["product_id"].nunique()
print(f"  Products ever flagged extreme: {flagged_products}/{total_products} ({flagged_products/total_products*100:.1f}%)")

# 9C: Declined products never flagged
prod_stats = df_v4.groupby("product_id").agg(
    ever_extreme=("risk_level_v4", lambda x: (x=="extreme").any()),
    ever_declined=(LABEL_COL, "max"),
)
missed = ((prod_stats["ever_declined"]==1) & (~prod_stats["ever_extreme"])).sum()
total_declined = (prod_stats["ever_declined"]==1).sum()
print(f"  Declined products NEVER flagged extreme: {missed}/{total_declined} ({missed/max(total_declined,1)*100:.1f}%)")

# 9D: Low-risk but declined
low_declined = ((df_v4["risk_level_v4"]=="low") & (df_v4[LABEL_COL]==1)).sum()
low_total = (df_v4["risk_level_v4"]=="low").sum()
print(f"  Low-risk but declined: {low_declined}/{low_total} ({low_declined/max(low_total,1)*100:.1f}%)")

# 9E: Compare with alternative label (y) to test robustness
print(f"\n  Cross-label check (using y as alternative label):")
y_label = "y_y" if "y_y" in df_v4.columns else ("y" if "y" in df_v4.columns else None)
if y_label:
    alt_y = df_v4[y_label].values
    alt_auc = roc_auc_score(alt_y, df_v4["score_v2"].values)
    # Also compute precision/recall for y
    from sklearn.metrics import precision_score, recall_score
    pred_extreme = (df_v4["score_v2"].values > OPTIMAL_THRESHOLDS[2])
    alt_prec = precision_score(alt_y, pred_extreme, zero_division=0)
    alt_rec = recall_score(alt_y, pred_extreme, zero_division=0)
    print(f"    Using y as label (base rate={alt_y.mean():.3f}):")
    print(f"    AUC={alt_auc:.4f} (vs decline_label_6m AUC={auc_v4:.4f})")
    print(f"    Precision={alt_prec:.4f}, Recall={alt_rec:.4f}")
    print(f"    Note: y label has {alt_y.sum()} positives vs {y_true.sum()} for decline_label_6m")

# 9F: Null C6 check - do scores differ when c6 unavailable?
if "c6_available" in df_v4.columns:
    with_c6 = df_v4[df_v4["c6_available"]==1]
    without_c6 = df_v4[df_v4["c6_available"]==0]
    print(f"\n  C6 availability impact:")
    print(f"    With c6 (n={len(with_c6)}): mean score={with_c6['score_v2'].mean():.2f}")
    print(f"    Without c6 (n={len(without_c6)}): mean score={without_c6['score_v2'].mean():.2f}")
    if len(with_c6) > 0 and len(without_c6) > 0:
        w_auc = roc_auc_score(with_c6[LABEL_COL], with_c6["score_v2"])
        wo_auc = roc_auc_score(without_c6[LABEL_COL], without_c6["score_v2"])
        print(f"    AUC with c6: {w_auc:.4f}, without c6: {wo_auc:.4f}")

# PERSPECTIVE 10: CONFUSION MATRIX + RELIABILITY DIAGRAM DATA
print("\n" + "="*70)
print("PERSPECTIVE 10: FINAL CONFUSION MATRIX & SUMMARY")
print("="*70)

print(f"\n  {'':25s} {'v2.9':>10s} {'v4.0':>10s}")
print(f"  {'-'*25} {'-'*10} {'-'*10}")
print(f"  {'Extreme flag count':25s} {cur['n_extreme']:10d} {v4['n_extreme']:10d}")
print(f"  {'Precision (TP/flagged)':25s} {cur['precision']:10.1%} {v4['precision']:10.1%}")
print(f"  {'Recall (TP/total decline)':25s} {cur['recall']:10.1%} {v4['recall']:10.1%}")
print(f"  {'F1 score':25s} {cur['f1']:10.3f} {v4['f1']:10.3f}")
print(f"  {'False alarms per 1000':25s} {int(1000*cur['extreme_pct']*(1-cur['precision'])):10d} "
      f"{int(1000*v4['extreme_pct']*(1-v4['precision'])):10d}")

# Save updated results
all_results["v4_metrics"] = v4
all_results["current_metrics"] = cur
all_results["auc_v4"] = float(auc_v4)
all_results["auc_current"] = float(auc_cur)

with open(os.path.join(OUT_DIR, "eval_results.json"), "w", encoding="utf-8") as f:
    json.dump(all_results, f, ensure_ascii=False, indent=2, default=str)

print(f"\n[OK] Complete evaluation saved to {OUT_DIR}/")
