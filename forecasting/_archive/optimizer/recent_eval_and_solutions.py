"""
Re-evaluate model on 2023+/2024+ data and propose blind spot solutions.
"""
import os, sys, warnings, json
warnings.filterwarnings("ignore")
import pandas as pd
import numpy as np

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

OUT_DIR = os.path.join(_PROJECT_ROOT, "output", "optimization", "comprehensive_eval")

LABEL_COL = "decline_label_6m"
OPTIMAL_WEIGHTS_4F = {"F1f": 0.100, "F4": 0.600, "F5": 0.200, "c6": 0.100}
OPTIMAL_THRESHOLDS = [55, 65, 71]
CURRENT_WEIGHTS_3F = {"F1f": 0.411, "F4": 0.236, "F5": 0.353}
CURRENT_THRESHOLDS = [50, 60, 75]

from optimizer.data_loader import load_optimization_data
from optimizer.scoring_v2 import score_panel_v2
from optimizer.metrics import compute_classification_metrics

def classify_risk(score, thr):
    if score <= thr[0]: return "low"
    elif score <= thr[1]: return "mid"
    elif score <= thr[2]: return "high"
    else: return "extreme"

print("Loading & scoring...")
df = load_optimization_data()
labeled = df[df[LABEL_COL].notna()].copy()

df_v4 = score_panel_v2(labeled, OPTIMAL_WEIGHTS_4F, use_c6=True)
df_v4["risk_level_v4"] = df_v4["score_v2"].apply(lambda s: classify_risk(s, OPTIMAL_THRESHOLDS))
df_current = score_panel_v2(labeled, CURRENT_WEIGHTS_3F, use_c6=False)
df_v4["risk_level_current"] = df_current["score_v2"].apply(
    lambda s: classify_risk(s, CURRENT_THRESHOLDS))

y_true_all = df_v4[LABEL_COL].values

# ════════════════════════════════════════════════════════════════
# PART 1: PERFORMANCE BY TIME PERIOD
# ════════════════════════════════════════════════════════════════
print("\n" + "="*70)
print("PART 1: PERFORMANCE BY START YEAR")
print("="*70)

from sklearn.metrics import roc_auc_score, precision_score, recall_score, f1_score

print(f"\n  {'Period':10s} {'n':>6s} {'BaseRate':>10s} {'AUC':>7s} {'Prec':>7s} {'Rec':>7s} {'F1':>7s} {'FP/1000':>9s}")
print(f"  {'-'*10} {'-'*6} {'-'*10} {'-'*7} {'-'*7} {'-'*7} {'-'*7} {'-'*9}")

for start_year in [2020, 2021, 2022, 2023, 2024]:
    sub = df_v4[df_v4["date_month"].astype(str).str[:4].astype(int) >= start_year].copy()
    if len(sub) < 100: continue
    y = sub[LABEL_COL].values
    pred = sub["score_v2"].values > OPTIMAL_THRESHOLDS[2]
    auc = roc_auc_score(y, sub["score_v2"].values)
    prec = precision_score(y, pred, zero_division=0)
    rec = recall_score(y, pred, zero_division=0)
    f1 = f1_score(y, pred, zero_division=0)
    fp_rate = ((~y.astype(bool)) & pred).sum() / len(sub) * 1000
    print(f"  {start_year}+{'':>7s} {len(sub):6d} {y.mean():10.3f} {auc:7.4f} {prec:7.1%} {rec:7.1%} {f1:7.3f} {fp_rate:8.1f}")

# Also show 2023-2025 specifically (full window)
print(f"\n  2023-2025 full window:")
for yr_str, label in [("2023","2023-2025"), ("2024","2024-2025")]:
    sub = df_v4[(df_v4["date_month"].astype(str).str[:4].astype(int) >= int(yr_str))].copy()
    if len(sub) < 100: continue
    y = sub[LABEL_COL].values
    pred = sub["score_v2"].values > OPTIMAL_THRESHOLDS[2]
    auc = roc_auc_score(y, sub["score_v2"].values)
    prec = precision_score(y, pred, zero_division=0)
    rec = recall_score(y, pred, zero_division=0)
    f1 = f1_score(y, pred, zero_division=0)
    
    # Product-level coverage
    prod = sub.groupby("product_id").agg(
        extreme=("risk_level_v4", lambda x: (x=="extreme").any()),
        declined=(LABEL_COL, "max"),
    )
    n_declined = (prod["declined"]==1).sum()
    n_caught = ((prod["declined"]==1) & prod["extreme"]).sum()
    coverage = n_caught / max(n_declined,1) * 100
    
    fp_ct = ((~y.astype(bool)) & pred).sum()
    fp_per_1000 = fp_ct / len(sub) * 1000
    
    print(f"    {label:12s}: AUC={auc:.4f}, Prec={prec:.1%}, Rec={rec:.1%}, "
          f"F1={f1:.3f}, Coverage={coverage:.1f}%, FP/1k={fp_per_1000:.0f}")

# ════════════════════════════════════════════════════════════════
# PART 2: 2024+ DEEP BLIND SPOT ANALYSIS
# ════════════════════════════════════════════════════════════════
print("\n" + "="*70)
print("PART 2: 2024+ BLIND SPOT DEEP DIVE")
print("="*70)

recent = df_v4[df_v4["date_month"].astype(str).str[:4].astype(int) >= 2024].copy()
print(f"\n  2024+ data: {len(recent)} rows, {recent['product_id'].nunique()} products")
print(f"  Label rate: {recent[LABEL_COL].mean():.3f}")

# Product-level in 2024+
prod_recent = recent.groupby("product_id").agg(
    ever_extreme=("risk_level_v4", lambda x: (x=="extreme").any()),
    ever_high=("risk_level_v4", lambda x: (x=="high").any()),
    ever_mid=("risk_level_v4", lambda x: (x=="mid").any()),
    ever_declined=(LABEL_COL, "max"),
    max_score=("score_v2", "max"),
    n_extreme=("risk_level_v4", lambda x: (x=="extreme").sum()),
    n_rows=(LABEL_COL, "count"),
).reset_index()

r_declined = prod_recent[prod_recent["ever_declined"]==1]
r_missed = r_declined[~r_declined["ever_extreme"]]
r_caught = r_declined[r_declined["ever_extreme"]]
print(f"\n  2024+ declined products: {len(r_declined)}")
print(f"  2024+ caught at extreme: {len(r_caught)} ({len(r_caught)/max(len(r_declined),1)*100:.1f}%)")
print(f"  2024+ missed at extreme: {len(r_missed)} ({len(r_missed)/max(len(r_declined),1)*100:.1f}%)")

# Missed products - what level did they reach?
r_flagged_high = r_missed[r_missed["ever_high"]]
r_flagged_mid = r_missed[r_missed["ever_mid"]]
r_never_any = r_missed[~r_missed["ever_mid"]]
print(f"    Reached high (but not extreme): {len(r_flagged_high)}")
print(f"    Reached mid (but not high+): {len(r_flagged_mid)}")
print(f"    Never exceeded low: {len(r_never_any)}")

# Missed products' max score distribution
print(f"\n  Missed products max score distribution (2024+):")
for lo, hi, label in [(0,30,"0-30"),(30,50,"30-50"),(50,55,"50-55"),
                       (55,60,"55-60"),(60,65,"60-65"),(65,70,"65-70"),
                       (70,71,"70(just below 71)")]:
    cnt = ((r_missed["max_score"]>lo)&(r_missed["max_score"]<=hi)).sum()
    if cnt > 0: print(f"    {label:18s}: {cnt}")

# Missed vs caught factor comparison (2024+)
r_missed_rows = recent[recent["product_id"].isin(r_missed["product_id"]) & (recent[LABEL_COL]==1)]
r_caught_rows = recent[recent["product_id"].isin(r_caught["product_id"]) & (recent[LABEL_COL]==1)]

if len(r_missed_rows) > 0 and len(r_caught_rows) > 0:
    print(f"\n  Factor comparison at decline time (2024+):")
    for f in ["score_v2","f4_v2","f5_v2","f1f_v2","recent_margin","decay_pp",
              "self_health","consecutive_months","margin_yoy_change_pp","c6_available"]:
        if f not in r_missed_rows.columns: continue
        m = r_missed_rows[f].mean()
        c = r_caught_rows[f].mean()
        print(f"    {f:25s}: missed={m:.3f}, caught={c:.3f}, diff={c-m:+.3f}")

# ════════════════════════════════════════════════════════════════
# PART 3: SOLUTIONS FOR EACH BLIND SPOT
# ════════════════════════════════════════════════════════════════
print("\n" + "="*70)
print("PART 3: BLIND SPOT SOLUTIONS — QUANTITATIVE EVALUATION")
print("="*70)

# --- Solution A: Threshold tuning ---
print("\n--- Solution A: Optimal threshold selection for 2024+ ---")
print(f"  {'Threshold':>12s} {'Coverage':>10s} {'FP/1000':>9s} {'Prec':>7s} {'Rec':>7s} {'F1':>7s}")
best_f1 = 0; best_config = None
for thr in range(55, 80):
    pred = recent["score_v2"].values > thr
    y = recent[LABEL_COL].values
    prod_flag = recent.groupby("product_id")["score_v2"].agg(lambda x: (x>thr).any())
    prod_dec = recent.groupby("product_id")[LABEL_COL].max()
    n_dec = (prod_dec==1).sum()
    n_caught = ((prod_dec==1) & prod_flag).sum()
    cov = n_caught/max(n_dec,1)*100
    
    fp = ((~y.astype(bool)) & pred).sum()
    fp1k = fp/len(y)*1000
    prec = precision_score(y, pred, zero_division=0)
    rec = recall_score(y, pred, zero_division=0)
    f1 = f1_score(y, pred, zero_division=0)
    
    if f1 > best_f1:
        best_f1 = f1
        best_config = (thr, cov, fp1k, prec, rec, f1)
    
    if thr in [55,60,63,65,67,68,69,70,71,75]:
        print(f"  thr>{thr:3d}      {cov:8.1f}% {fp1k:8.0f} {prec:6.1%} {rec:6.1%} {f1:6.3f}")

print(f"\n  Best threshold (F1-max): >{best_config[0]} — "
      f"Coverage={best_config[1]:.1f}%, FP/1k={best_config[2]:.0f}, "
      f"Prec={best_config[3]:.1%}, Rec={best_config[4]:.1%}, F1={best_config[5]:.3f}")

# --- Solution B: Segment-specific thresholds ---
print("\n--- Solution B: Segment-specific thresholds ---")
print(f"  Testing per-portrait optimal thresholds on 2024+ data:")
for portrait in recent["portrait"].unique():
    sub = recent[recent["portrait"]==portrait]
    if len(sub) < 50: continue
    y = sub[LABEL_COL].values
    
    # Find best threshold for this segment
    best = None
    for thr in range(45, 80):
        pred = sub["score_v2"].values > thr
        f1 = f1_score(y, pred, zero_division=0) if pred.sum()>0 else 0
        if best is None or f1 > best[1]:
            best = (thr, f1, precision_score(y, pred, zero_division=0) if pred.sum()>0 else 0,
                    recall_score(y, pred, zero_division=0) if pred.sum()>0 else 0)
    
    pname = str(portrait)[:12]
    print(f"    {pname:12s}: best thr>{best[0]:2d} F1={best[1]:.3f} Prec={best[2]:.1%} Rec={best[3]:.1%}")

# --- Solution C: F5 override rule ---
print("\n--- Solution C: F5 override rule simulation ---")
print("  Idea: If F4>=80 and F1f>=70, give extreme even if composite score < threshold")
override_caught = 0
for idx, row in recent.iterrows():
    if row["risk_level_v4"] != "extreme" and row["f4_v2"] >= 80 and row["f1f_v2"] >= 70:
        if row[LABEL_COL] == 1:
            override_caught += 1
override_fp = 0
for idx, row in recent.iterrows():
    if row["risk_level_v4"] != "extreme" and row["f4_v2"] >= 80 and row["f1f_v2"] >= 70:
        if row[LABEL_COL] == 0:
            override_fp += 1
print(f"    Additional caught (TP) with override: {override_caught}")
print(f"    Additional false alarms (FP): {override_fp}")
if override_caught + override_fp > 0:
    print(f"    Override precision: {override_caught/max(override_caught+override_fp,1)*100:.1f}%")

# --- Solution D: C6 imputation / weight redistribution ---
print("\n--- Solution D: C6-aware weight redistribution ---")
print("  For products without c6 data: redistribute c6 weight to F4 + F5")
w_no_c6 = {"F1f": 0.100, "F4": 0.700, "F5": 0.200}  # c6=0.100 redistributed: 60% to F4, 40% to F5
df_no_c6 = score_panel_v2(labeled, w_no_c6, use_c6=False)
df_no_c6["rl"] = df_no_c6["score_v2"].apply(lambda s: classify_risk(s, OPTIMAL_THRESHOLDS))

# Apply only to no-c6 subset
recent_noc6 = recent[recent["c6_available"]==0].copy()
# Preserve original scores before dropping v2 columns
orig_score = recent_noc6["score_v2"].copy()
# Drop old v2 scoring columns to avoid concat duplication
drop_cols = [c for c in recent_noc6.columns
             if c.endswith("_v2") or c.startswith("score_v2")
             or c.startswith("c6_") or c == "factor_weights"
             or c.startswith("risk_level")]
recent_noc6 = recent_noc6.drop(columns=[c for c in drop_cols if c in recent_noc6.columns],
                                errors="ignore")
recent_noc6_scores = score_panel_v2(recent_noc6, w_no_c6, use_c6=False)

# Compare original vs new
y_noc6 = recent_noc6[LABEL_COL].values.ravel()
orig_pred = (orig_score.values > OPTIMAL_THRESHOLDS[2]).ravel()
new_score = recent_noc6_scores["score_v2"]
if isinstance(new_score, pd.DataFrame):
    new_score = new_score.iloc[:, -1]
new_pred = (new_score.values > OPTIMAL_THRESHOLDS[2]).ravel()

orig_prec = precision_score(y_noc6, orig_pred, zero_division=0)
orig_rec = recall_score(y_noc6, orig_pred, zero_division=0)
new_prec = precision_score(y_noc6, new_pred, zero_division=0)
new_rec = recall_score(y_noc6, new_pred, zero_division=0)

print(f"    No-c6 subset (2024+): {len(recent_noc6)} rows")
print(f"    Original: Prec={orig_prec:.1%}, Rec={orig_rec:.1%}")
print(f"    Redistributed: Prec={new_prec:.1%}, Rec={new_rec:.1%}")
print(f"    Change: Prec={new_prec-orig_prec:+.1%}, Rec={new_rec-orig_rec:+.1%}")

# ════════════════════════════════════════════════════════════════
# PART 4: COMPREHENSIVE SOLUTION PROPOSAL
# ════════════════════════════════════════════════════════════════
print("\n" + "="*70)
print("PART 4: COMPREHENSIVE SOLUTION SCORECARD")
print("="*70)

# How many of the 2024+ blind spots can each solution fix?
r_missed_2024 = recent[(recent["product_id"].isin(r_missed["product_id"])) & 
                        (recent[LABEL_COL]==1)]

# A: Threshold 68
thr68_fix = ((r_missed_2024["score_v2"] > 68)).sum()
# B: F5 override
f5_override_fix = ((r_missed_2024["f4_v2"]>=80) & (r_missed_2024["f1f_v2"]>=70)).sum()
# C: C6 redistribution (estimated impact)
c6_redist_fix = ((r_missed_2024["c6_available"]==0) & (r_missed_2024["score_v2"] <= OPTIMAL_THRESHOLDS[2])).sum()
# D: Combined
combined = ((r_missed_2024["score_v2"] > 68) | 
            ((r_missed_2024["f4_v2"]>=80) & (r_missed_2024["f1f_v2"]>=70)) |
            ((r_missed_2024["c6_available"]==0) & (r_missed_2024["score_v2"] <= OPTIMAL_THRESHOLDS[2]))).sum()

total_missed_rows = len(r_missed_2024)

print(f"\n  Total 2024+ missed decline rows: {total_missed_rows}")
print(f"\n  Solution                Fixed rows   FixRate   Cumulative")
print(f"  {'-'*24} {'-'*12} {'-'*10} {'-'*12}")
print(f"  A: Threshold >68          {thr68_fix:8d}    {thr68_fix/max(total_missed_rows,1)*100:6.1f}%   {thr68_fix:8d}")
print(f"  B: F5 override            {f5_override_fix:8d}    {f5_override_fix/max(total_missed_rows,1)*100:6.1f}%   {thr68_fix+f5_override_fix:8d}")
print(f"  C: C6 redistribution      {c6_redist_fix:8d}    {c6_redist_fix/max(total_missed_rows,1)*100:6.1f}%   {thr68_fix+f5_override_fix+c6_redist_fix:8d}")
print(f"  D: All combined           {combined:8d}    {combined/max(total_missed_rows,1)*100:6.1f}%   {combined:8d}")

# ════════════════════════════════════════════════════════════════
# PART 5: FINAL RECOMMENDATION
# ════════════════════════════════════════════════════════════════
print("\n" + "="*70)
print("PART 5: FINAL RECOMMENDATION")
print("="*70)

# Get latest metrics for 2024+
y_recent = recent[LABEL_COL].values
pred_current = recent["score_v2"].values > OPTIMAL_THRESHOLDS[2]

# Try recommended combined approach
rec_threshold = 68
rec_pred = recent["score_v2"].values > rec_threshold
rec_f1 = f1_score(y_recent, rec_pred, zero_division=0)
rec_prec = precision_score(y_recent, rec_pred, zero_division=0)
rec_rec = recall_score(y_recent, rec_pred, zero_division=0)
rec_auc = roc_auc_score(y_recent, recent["score_v2"].values)
rec_fp = ((~y_recent.astype(bool)) & rec_pred).sum() / len(y_recent) * 1000

# Product level
prod_rec = recent.groupby("product_id").agg(
    flagged=("score_v2", lambda x: (x>rec_threshold).any()),
    declined=(LABEL_COL, "max"),
).reset_index()
rec_cov = ((prod_rec["declined"]==1) & prod_rec["flagged"]).sum() / max((prod_rec["declined"]==1).sum(),1) * 100

print(f"""
  RECOMMENDATION: Multi-strategy combined approach

  Current (2024+, threshold >71):
    AUC={roc_auc_score(y_recent, recent['score_v2'].values):.4f}
    Precision={precision_score(y_recent, pred_current, zero_division=0):.1%}
    Recall={recall_score(y_recent, pred_current, zero_division=0):.1%}
    F1={f1_score(y_recent, pred_current, zero_division=0):.3f}
    Coverage={0:.1f}%  (product-level)
    FP/1000={((~y_recent.astype(bool)) & pred_current).sum()/len(y_recent)*1000:.0f}

  Recommended (threshold >68 + F4/F1f override):
    AUC={rec_auc:.4f}
    Precision={rec_prec:.1%}
    Recall={rec_rec:.1%}
    F1={rec_f1:.3f}
    Coverage={rec_cov:.1f}%
    FP/1000={rec_fp:.0f}

  Key changes:
    1. Lower extreme threshold from 71 to 68
    2. Add F4+F1f override rule: if F4>=80 and F1f>=70, auto-extreme
    3. For no-c6 products, redistribute weight (F4=0.70, F5=0.20, F1f=0.10)
    4. Consider portrait-specific thresholds for 成长品/优化中品类 (thr >55)

  Trade-offs:
    - Precision drops {precision_score(y_recent, pred_current, zero_division=0)-rec_prec:+.1%}
    - Recall improves {rec_rec-recall_score(y_recent, pred_current, zero_division=0):+.1%}
    - FP increases by {rec_fp - ((~y_recent.astype(bool)) & pred_current).sum()/len(y_recent)*1000:.0f}/1000
""")

# Save results
results = {
    "2024_performance": {
        "auc": round(rec_auc, 4),
        "precision": round(rec_prec, 4),
        "recall": round(rec_rec, 4),
        "f1": round(rec_f1, 4),
        "coverage_pct": round(rec_cov, 1),
        "fp_per_1000": round(rec_fp, 0),
    },
    "recommended_threshold": rec_threshold,
    "solutions": {
        "threshold_68_fix": int(thr68_fix),
        "f5_override_fix": int(f5_override_fix),
        "c6_redist_fix": int(c6_redist_fix),
        "combined_fix": int(combined),
        "total_missed_rows": int(total_missed_rows),
    }
}
with open(os.path.join(OUT_DIR, "recent_eval_results.json"), "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

print("Done! Results saved.")
