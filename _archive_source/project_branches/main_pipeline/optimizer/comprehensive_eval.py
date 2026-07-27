"""
Comprehensive Multi-Perspective Evaluation of Risk Decline Model v4.0

CORRECTED: Uses decline_label_6m (official label, 17% rate) as primary target.
Validates from 8 independent perspectives including ground truth, calibration,
segmentation, lead time, post-warning trajectory, FP profile, interpretability,
and business impact comparison.

Usage: python optimizer/comprehensive_eval.py
"""
import os, sys, json, warnings
warnings.filterwarnings("ignore")

import pandas as pd
import numpy as np

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

OUT_DIR = os.path.join(_PROJECT_ROOT, "output", "optimization", "comprehensive_eval")
os.makedirs(OUT_DIR, exist_ok=True)

# ── Model Config ──────────────────────────────────────────────
OPTIMAL_WEIGHTS_4F = {"F1f": 0.100, "F4": 0.600, "F5": 0.200, "c6": 0.100}
OPTIMAL_THRESHOLDS = [55, 65, 71]   # [low_max, mid_max, high_max]

CURRENT_WEIGHTS_3F = {"F1f": 0.411, "F4": 0.236, "F5": 0.353}
CURRENT_THRESHOLDS = [50, 60, 75]

LABEL_COL = "decline_label_6m"  # official training label

# ── Load data & score ─────────────────────────────────────────
from optimizer.data_loader import load_optimization_data
from optimizer.scoring_v2 import score_panel_v2, score_self_health_v2
from optimizer.metrics import compute_classification_metrics

print("Loading data...")
df = load_optimization_data()
# Filter to labeled subset (same as optimizer)
labeled = df[df[LABEL_COL].notna()].copy()
y_true = labeled[LABEL_COL].values

print(f"Labeled rows: {len(labeled)}")
print(f"Label positive rate: {y_true.mean():.4f} (= {int(y_true.sum())}/{len(y_true)})")
print(f"Products: {labeled['product_id'].nunique()}")
print(f"Date range: {labeled['date_month'].min()} ~ {labeled['date_month'].max()}")

# --- Score with v4.0 ---
print("\nScoring v4.0 (optimized)...")
df_v4 = score_panel_v2(labeled, OPTIMAL_WEIGHTS_4F, use_c6=True)

def classify_risk(score, thr):
    if score <= thr[0]: return "low"
    elif score <= thr[1]: return "mid"
    elif score <= thr[2]: return "high"
    else: return "extreme"

df_v4["risk_level_v4"] = df_v4["score_v2"].apply(lambda s: classify_risk(s, OPTIMAL_THRESHOLDS))

# --- Score with v2.9 current ---
print("Scoring v2.9 (current production)...")
df_current = score_panel_v2(labeled, CURRENT_WEIGHTS_3F, use_c6=False)
df_current["risk_level_current"] = df_current["score_v2"].apply(
    lambda s: classify_risk(s, CURRENT_THRESHOLDS))

df_v4["score_current"] = df_current["score_v2"]
df_v4["risk_level_current"] = df_current["risk_level_current"]

all_results = {}
key_findings = []

# ════════════════════════════════════════════════════════════════
# PERSPECTIVE 1: GROUND TRUTH VERIFICATION
# ════════════════════════════════════════════════════════════════
print("\n" + "="*70)
print("PERSPECTIVE 1: GROUND TRUTH — Do high-risk products REALLY decline?")
print("="*70)

# 1A: Compare actual business metrics by label status
print("\n--- 1A: Actual margin/revenue by label ---")
for m in ["recent_margin", "margin_yoy_change_pp", "decay_pp", "self_health"]:
    if m in df_v4.columns:
        y0 = df_v4[df_v4[LABEL_COL]==0][m].dropna()
        y1 = df_v4[df_v4[LABEL_COL]==1][m].dropna()
        if len(y0) > 0 and len(y1) > 0:
            diff = y1.mean() - y0.mean()
            print(f"  {m:25s}: label=0 mean={y0.mean():.4f}, label=1 mean={y1.mean():.4f}, diff={diff:+.4f} ({diff/abs(y0.mean())*100:+.1f}%)")

# 1B: Actual metrics by v4.0 risk level
print("\n--- 1B: Actual metrics by v4.0 risk level ---")
print(f"  {'Level':8s} {'n':>6s} {'Margin':>10s} {'Rev_12m':>12s} {'Decay_pp':>10s} {'DeclineRate':>12s}")
for level in ["low", "mid", "high", "extreme"]:
    sub = df_v4[df_v4["risk_level_v4"]==level]
    if len(sub) < 5: continue
    print(f"  {level:8s} {len(sub):6d} {sub['recent_margin'].mean():10.4f} "
          f"{sub['recent_rev_12m'].mean():12.0f} {sub['decay_pp'].mean():10.2f} "
          f"{sub[LABEL_COL].mean():12.3f}")

# 1C: Forward consistency (does label=1 predict future margin drop?)
print("\n--- 1C: Label forward consistency check ---")
consistent_fwd, total_fwd = 0, 0
for pid in df_v4["product_id"].unique()[:200]:
    prod = df_v4[df_v4["product_id"]==pid].sort_values("date_month")
    for i in range(len(prod)-1):
        if prod.iloc[i][LABEL_COL] == 1:
            total_fwd += 1
            if prod.iloc[i+1]["recent_margin"] < prod.iloc[i]["recent_margin"]:
                consistent_fwd += 1
if total_fwd > 0:
    pct = consistent_fwd/total_fwd*100
    print(f"  Sampled {total_fwd} label=1 cases: {consistent_fwd} ({pct:.1f}%) had margin drop next month")
    key_findings.append(("Ground Truth (margin drop consistency)", f"{pct:.1f}%", "Forward", f"Sampled {total_fwd} cases"))
else:
    print("  [WARN] No forward data available for label=1 cases")

all_results["ground_truth"] = {
    "margin_drop_consistency_pct": round(consistent_fwd/max(total_fwd,1)*100, 1),
    "samples_checked": total_fwd,
}

# ════════════════════════════════════════════════════════════════
# PERSPECTIVE 2: SCORE CALIBRATION
# ════════════════════════════════════════════════════════════════
print("\n" + "="*70)
print("PERSPECTIVE 2: CALIBRATION — Does the score MEAN what it claims?")
print("="*70)

# 2A: 10-point bucket calibration
print("\n--- 2A: Observed decline rate by 10-point score bucket ---")
df_v4["score_bucket"] = pd.cut(df_v4["score_v2"], bins=list(range(0, 111, 10)),
                                 right=True, include_lowest=True)
bucket_stats = df_v4.groupby("score_bucket", observed=False).agg(
    n=(LABEL_COL, "count"),
    decline_rate=(LABEL_COL, "mean"),
    pct_of_total=(LABEL_COL, lambda x: len(x)/len(df_v4)*100),
).round(4)
print(bucket_stats.to_string())

# 2B: Monotonicity check
rates = bucket_stats["decline_rate"].values
violations = sum(1 for i in range(1, len(rates)) if rates[i] < rates[i-1] - 0.005)
print(f"\n  Monotonicity violations (rate decrease >0.5pp): {violations}/{len(rates)-1}")
if violations > 0:
    for i in range(1, len(rates)):
        if rates[i] < rates[i-1] - 0.005:
            print(f"    {bucket_stats.index[i-1]} ({rates[i-1]:.3f}) -> {bucket_stats.index[i]} ({rates[i]:.3f})")

# 2C: Risk level calibration
print("\n--- 2C: Risk level calibration ---")
print(f"  {'Level':8s} {'n':>6s} {'%tot':>6s} {'DeclineRate':>12s} {'FP_within':>10s} {'%ofDeclines':>12s}")
total_declines = y_true.sum()
for level in ["low", "mid", "high", "extreme"]:
    sub = df_v4[df_v4["risk_level_v4"]==level]
    if len(sub) < 3: continue
    rate = sub[LABEL_COL].mean()
    n_declines_in_level = int(sub[LABEL_COL].sum())
    pct_of_all_declines = n_declines_in_level / total_declines * 100
    print(f"  {level:8s} {len(sub):6d} {len(sub)/len(df_v4)*100:5.1f}% {rate:12.3f} "
          f"{(1-rate)*100:9.1f}% {pct_of_all_declines:11.1f}%")

# 2D: Extreme risk reliability
extreme = df_v4[df_v4["risk_level_v4"]=="extreme"]
all_extreme_count = len(extreme)
if all_extreme_count > 0:
    extreme_dec_rate = extreme[LABEL_COL].mean()
    extreme_tp = int(extreme[LABEL_COL].sum())
    extreme_fp = all_extreme_count - extreme_tp
    print(f"\n  Extreme risk:")
    print(f"    Precision (TP/(TP+FP)): {extreme_tp}/{all_extreme_count} = {extreme_dec_rate:.3f}")
    print(f"    False alarms (FP): {extreme_fp} ({extreme_fp/all_extreme_count*100:.1f}% of extreme)")
    print(f"    Coverage: {extreme_tp}/{total_declines} = {extreme_tp/total_declines*100:.1f}% of all declines")

all_results["calibration"] = {
    "monotonicity_violations": int(violations),
    "extreme_precision": float(extreme_dec_rate) if all_extreme_count > 0 else None,
    "extreme_fp_count": int(extreme_fp) if all_extreme_count > 0 else None,
    "extreme_fp_rate": float(extreme_fp/max(all_extreme_count,1)) if all_extreme_count > 0 else None,
    "n_extreme": all_extreme_count,
}

# ════════════════════════════════════════════════════════════════
# PERSPECTIVE 3: SEGMENTATION — Is performance universal?
# ════════════════════════════════════════════════════════════════
print("\n" + "="*70)
print("PERSPECTIVE 3: SEGMENTATION — Does it work for ALL product types?")
print("="*70)

for seg_col in ["portrait", "momentum", "health"]:
    if seg_col not in df_v4.columns: continue
    print(f"\n--- 3A: Performance by {seg_col} ---")
    seg_data = []
    for name, grp in df_v4.groupby(seg_col):
        if len(grp) < 20: continue
        ext = grp[grp["risk_level_v4"]=="extreme"]
        seg_data.append({
            seg_col: name,
            "n": len(grp),
            "base_rate": grp[LABEL_COL].mean(),
            "score_mean": grp["score_v2"].mean(),
            "extreme_n": len(ext),
            "extreme_pct": len(ext)/len(grp)*100,
            "extreme_prec": ext[LABEL_COL].mean() if len(ext)>=5 else float("nan"),
            "extreme_recall": ext[LABEL_COL].sum()/max(grp[LABEL_COL].sum(),1) if len(ext)>=5 else float("nan"),
        })
    seg_df = pd.DataFrame(seg_data).sort_values("n", ascending=False)
    seg_df[seg_col] = seg_df[seg_col].astype(str).str[:12]
    print(seg_df.to_string(index=False))

# 3B: By time period
print("\n--- 3B: Performance by year ---")
df_v4["year"] = df_v4["date_month"].astype(str).str[:4]
yearly = df_v4.groupby("year").agg(
    n=(LABEL_COL, "count"),
    base_rate=(LABEL_COL, "mean"),
    score_mean=("score_v2", "mean"),
).round(4)
print(yearly.to_string())

# 3C: By product size (revenue quartile)
print("\n--- 3C: Performance by revenue size ---")
df_v4["rev_quartile"] = pd.qcut(df_v4["recent_rev_12m"].clip(lower=1),
                                  q=4, labels=["Q1_small", "Q2", "Q3", "Q4_large"])
rev_seg = df_v4.groupby("rev_quartile", observed=False).agg(
    n=(LABEL_COL, "count"),
    base_rate=(LABEL_COL, "mean"),
    score_mean=("score_v2", "mean"),
).round(4)
print(rev_seg.to_string())

# ════════════════════════════════════════════════════════════════
# PERSPECTIVE 4: LEAD TIME — How early does the model warn?
# ════════════════════════════════════════════════════════════════
print("\n" + "="*70)
print("PERSPECTIVE 4: LEAD TIME — How many months of advance warning?")
print("="*70)

# For each product, find first extreme flag, then first label=1 after it
# lead_time = months from first flag to first label=1
lead_data = []
for pid, grp in df_v4.groupby("product_id"):
    grp = grp.sort_values("date_month").reset_index(drop=True)
    ext_idx = grp.index[grp["risk_level_v4"]=="extreme"].tolist()
    if len(ext_idx) == 0: continue

    first_ext = ext_idx[0]
    # Look forward for label=1
    for j in range(first_ext, len(grp)):
        if grp.loc[j, LABEL_COL] == 1:
            lead_months = j - first_ext
            if lead_months > 0:
                lead_data.append({
                    "product_id": pid,
                    "first_flag_date": grp.loc[first_ext, "date_month"],
                    "decline_date": grp.loc[j, "date_month"],
                    "lead_months": lead_months,
                    "score_at_flag": grp.loc[first_ext, "score_v2"],
                    "margin_at_flag": grp.loc[first_ext, "recent_margin"],
                    "margin_at_decline": grp.loc[j, "recent_margin"],
                })
            break

print(f"\n  Products with valid lead time: {len(lead_data)}")
if lead_data:
    lt = pd.DataFrame(lead_data)
    print(f"  Lead time distribution:")
    print(f"    Mean:   {lt['lead_months'].mean():.1f} months")
    print(f"    Median: {lt['lead_months'].median():.1f} months")
    print(f"    Q25:    {lt['lead_months'].quantile(0.25):.0f} months")
    print(f"    Q75:    {lt['lead_months'].quantile(0.75):.0f} months")
    print(f"    Min:    {lt['lead_months'].min():.0f} months")
    print(f"    Max:    {lt['lead_months'].max():.0f} months")
    print(f"\n  Lead months distribution:")
    for m in range(0, int(lt['lead_months'].max())+1):
        cnt = (lt['lead_months'] >= m).sum()
        print(f"    >= {m:2d}m: {cnt:3d} ({cnt/len(lt)*100:5.1f}%)")

    # What was the margin drop from flag to decline?
    lt["margin_drop_pct"] = (lt["margin_at_decline"] - lt["margin_at_flag"]) / lt["margin_at_flag"].replace(0, np.nan) * 100
    print(f"\n  Margin change from flag to decline: mean={lt['margin_drop_pct'].mean():.1f}%, median={lt['margin_drop_pct'].median():.1f}%")

    all_results["lead_time"] = {
        "n_products": len(lt),
        "mean_months": float(lt["lead_months"].mean()),
        "median_months": float(lt["lead_months"].median()),
        "pct_lead_ge3m": float((lt["lead_months"]>=3).mean() * 100),
        "pct_lead_ge6m": float((lt["lead_months"]>=6).mean() * 100),
    }
else:
    print("  [WARN] No lead time data")
    all_results["lead_time"] = None

# ════════════════════════════════════════════════════════════════
# PERSPECTIVE 5: POST-WARNING TRAJECTORY
# ════════════════════════════════════════════════════════════════
print("\n" + "="*70)
print("PERSPECTIVE 5: POST-WARNING — What happens AFTER extreme flag?")
print("="*70)

traj_data = []
for pid, grp in df_v4.groupby("product_id"):
    grp = grp.sort_values("date_month").reset_index(drop=True)
    ext_idx = grp.index[grp["risk_level_v4"]=="extreme"].tolist()
    if len(ext_idx) == 0: continue

    first_ext = ext_idx[0]
    # Need at least 6 months future data
    if first_ext + 6 >= len(grp): continue

    pre_margin = grp.loc[first_ext-1, "recent_margin"] if first_ext > 0 else grp.loc[0, "recent_margin"]
    flag_margin = grp.loc[first_ext, "recent_margin"]
    post3m = grp.loc[first_ext+3, "recent_margin"]
    post6m = grp.loc[first_ext+6, "recent_margin"]

    # Check future label within 6m
    future_window = grp.iloc[first_ext:first_ext+7]
    future_declined = future_window[LABEL_COL].max() == 1

    # What was the actual label outcome in the next 12 months?
    future_12 = grp.iloc[first_ext:min(first_ext+13, len(grp))]
    future_decline_count = future_12[LABEL_COL].sum()

    traj_data.append({
        "product_id": pid,
        "flag_margin": flag_margin,
        "pre_margin": pre_margin,
        "post3m_margin": post3m,
        "post6m_margin": post6m,
        "future_declined_6m": future_declined,
        "future_decline_count_12m": future_decline_count,
        "label_positive_6m_after_flag": future_window[LABEL_COL].values.tolist() if len(future_window) == 7 else None,
    })

if traj_data:
    td = pd.DataFrame(traj_data)
    n_total = len(td)

    # Trajectory: recovery vs stable vs worsened (6m post flag)
    td["margin_chg_6m"] = (td["post6m_margin"] - td["flag_margin"]) / td["flag_margin"].replace(0, np.nan) * 100
    recovered = (td["margin_chg_6m"] > 10).sum()
    stable = ((td["margin_chg_6m"] >= -10) & (td["margin_chg_6m"] <= 10)).sum()
    worsened = (td["margin_chg_6m"] < -10).sum()

    # How many had at least one decline event in 12 months post flag?
    n_with_any_decline = (td["future_decline_count_12m"] > 0).sum()

    print(f"\n  Products tracked (extreme flag + 6mo future data): {n_total}")
    print(f"  6-month margin trajectory from flag:")
    print(f"    Recovery (>+10%):     {recovered} ({recovered/n_total*100:.1f}%)")
    print(f"    Stable (+/-10%):      {stable} ({stable/n_total*100:.1f}%)")
    print(f"    Worsened (<-10%):     {worsened} ({worsened/n_total*100:.1f}%)")
    print(f"  Had >=1 decline event in 12mo post flag: {n_with_any_decline} ({n_with_any_decline/n_total*100:.1f}%)")
    print(f"  Decline event in 6mo post flag: {td['future_declined_6m'].sum()} ({td['future_declined_6m'].mean()*100:.1f}%)")
    print(f"  Mean margin change (flag -> 6m): {td['margin_chg_6m'].mean():.1f}%")

    # Compare pre-flag margin to post-6m margin (overall decline from before flag to after)
    td["overall_margin_chg"] = (td["post6m_margin"] - td["pre_margin"]) / td["pre_margin"].replace(0, np.nan) * 100
    print(f"  Mean margin change (pre-flag -> post-6m): {td['overall_margin_chg'].mean():.1f}%")

    all_results["post_warning"] = {
        "n_tracked": n_total,
        "recovered_pct": round(recovered/n_total*100, 1),
        "stable_pct": round(stable/n_total*100, 1),
        "worsened_pct": round(worsened/n_total*100, 1),
        "any_decline_12m_pct": round(n_with_any_decline/n_total*100, 1),
        "decline_6m_pct": round(td['future_declined_6m'].mean()*100, 1),
        "mean_margin_chg_6m_pct": round(td['margin_chg_6m'].mean(), 1),
        "mean_overall_chg_pct": round(td['overall_margin_chg'].mean(), 1),
    }
else:
    print("  [WARN] No post-warning data available")
    all_results["post_warning"] = None

# ════════════════════════════════════════════════════════════════
# PERSPECTIVE 6: FALSE POSITIVE DEEP DIVE
# ════════════════════════════════════════════════════════════════
print("\n" + "="*70)
print("PERSPECTIVE 6: FALSE POSITIVES — Who are the false alarms?")
print("="*70)

extreme_subset = df_v4[df_v4["risk_level_v4"]=="extreme"]
fp = extreme_subset[extreme_subset[LABEL_COL]==0]
tp = extreme_subset[extreme_subset[LABEL_COL]==1]
all_ex = extreme_subset

print(f"  Extreme total: {len(all_ex)}")
print(f"  TP (correct): {len(tp)} ({len(tp)/max(len(all_ex),1)*100:.1f}%)")
print(f"  FP (false alarm): {len(fp)} ({len(fp)/max(len(all_ex),1)*100:.1f}%)")

if len(fp) >= 5 and len(tp) >= 5:
    print("\n  FP vs TP feature comparison:")
    for col in ["score_v2", "recent_margin", "margin_yoy_change_pp", "decay_pp",
                "self_health", "consecutive_months", "recent_rev_12m"]:
        if col not in df_v4.columns: continue
        fpm = fp[col].mean()
        tpm = tp[col].mean()
        diff = tpm - fpm
        print(f"    {col:25s}: FP={fpm:10.4f}, TP={tpm:10.4f}, diff={diff:+.4f}")

    print("\n  Factor score comparison:")
    for f in ["f1f_v2", "f4_v2", "f5_v2"]:
        if f not in fp.columns: continue
        fpm = fp[f].mean()
        tpm = tp[f].mean()
        print(f"    {f:8s}: FP={fpm:6.2f}, TP={tpm:6.2f}, diff={tpm-fpm:+.2f}")

    print("\n  Segment distribution comparison:")
    for seg in ["portrait", "momentum", "health"]:
        if seg not in df_v4.columns: continue
        print(f"    {seg}:")
        fp_pct = fp[seg].value_counts(normalize=True).head(3) * 100
        tp_pct = tp[seg].value_counts(normalize=True).head(3) * 100
        for cat in fp_pct.index:
            print(f"      {str(cat)[:12]:12s}: FP={fp_pct.get(cat,0):.0f}%, TP={tp_pct.get(cat,0):.0f}%")

    # Are FPs "near misses" — products close to being actually declining?
    print("\n  Are FPs recovering or near-miss?")
    high_fp = fp[fp["score_v2"] >= 80]
    print(f"    FP with score>=80 (high confidence false alarm): {len(high_fp)}")
    # Check if FPs had recent margin volatility (use copy to avoid SettingWithCopyWarning)
    fp_temp = fp.copy()
    tp_temp = tp.copy()
    if len(fp_temp) > 0:
        fp_temp["margin_vol"] = fp_temp.groupby("product_id")["recent_margin"].transform(
            lambda x: x.diff().abs().mean())
        print(f"    Mean margin volatility: FP={fp_temp['margin_vol'].mean():.4f}", end="")
        if len(tp_temp) > 0:
            tp_temp["margin_vol"] = tp_temp.groupby("product_id")["recent_margin"].transform(
                lambda x: x.diff().abs().mean())
            print(f" vs TP={tp_temp['margin_vol'].mean():.4f}")
        else:
            print()

all_results["fp_analysis"] = {
    "n_fp": int(len(fp)),
    "n_tp": int(len(tp)),
    "fp_rate": float(len(fp)/max(len(all_ex),1)),
    "fp_high_conf": int((fp["score_v2"]>=80).sum()) if len(fp) > 0 else 0,
}

# ════════════════════════════════════════════════════════════════
# PERSPECTIVE 7: INTERPRETABILITY — Why did each product score high?
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

# 7C: Case studies — top 5 TP and top 5 FP
print("\n--- 7C: Case studies ---")
case_cols = ["product_id", "date_month", "risk_level_v4", "score_v2",
             "f1f_v2", "f4_v2", "f5_v2", "recent_margin", "decay_pp", "self_health",
             "portrait", "momentum"]

for label_val, label_name in [(1, "TRUE POSITIVES"), (0, "FALSE POSITIVES")]:
    subset = extreme_subset[extreme_subset[LABEL_COL]==label_val]
    if len(subset) == 0: continue
    # Pick top 3 by score
    cases = subset.nlargest(min(3, len(subset)), "score_v2")
    print(f"\n  Top {min(3,len(subset))} {label_name} (extreme risk, highest scores):")
    for _, row in cases.iterrows():
        print(f"    {str(row['product_id']):12s} | {row['date_month']} | "
              f"score={row['score_v2']:.0f} | F1f={row['f1f_v2']} F4={row['f4_v2']} "
              f"F5={row['f5_v2']} | margin={row['recent_margin']:.3f} | "
              f"decay={row['decay_pp']:.1f} | sh={row['self_health']:.2f}")

# 7D: Score distribution by factor (what scores do products actually get?)
print("\n--- 7D: Score distribution by factor ---")
for f in ["f1f_v2", "f4_v2", "f5_v2"]:
    dist = df_v4[f].value_counts().sort_index()
    print(f"  {f}:")
    print(f"    {dist.to_dict()}")

# ════════════════════════════════════════════════════════════════
# PERSPECTIVE 8: BUSINESS IMPACT COMPARISON
# ════════════════════════════════════════════════════════════════
print("\n" + "="*70)
print("PERSPECTIVE 8: BUSINESS IMPACT — v4.0 vs v2.9 side-by-side")
print("="*70)

def confusion_metrics(df_in, score_col, level_col, thr_high):
    y = df_in[LABEL_COL].values
    pred = (df_in[score_col].values > thr_high)
    tp = int((pred & (y==1)).sum())
    fp = int((pred & (y==0)).sum())
    fn = int((~pred & (y==1)).sum())
    tn = int((~pred & (y==0)).sum())
    prec = tp/max(tp+fp,1)
    rec = tp/max(tp+fn,1)
    f1 = 2*prec*rec/max(prec+rec,1e-10)
    return {"tp":tp,"fp":fp,"tn":tn,"fn":fn,
            "precision":round(prec,4),"recall":round(rec,4),"f1":round(f1,4),
            "n_extreme":tp+fp,"extreme_pct":(tp+fp)/len(df_in),
            "base_rate":y.mean()}

v4 = confusion_metrics(df_v4, "score_v2", "risk_level_v4", OPTIMAL_THRESHOLDS[2])
cur = confusion_metrics(df_current, "score_v2", "risk_level_current", CURRENT_THRESHOLDS[2])

print(f"\n  {'Metric':25s} {'v2.9 Current':15s} {'v4.0 Optimized':15s} {'Delta':10s}")
print(f"  {'-'*25} {'-'*15} {'-'*15} {'-'*10}")
for k in ["n_extreme", "extreme_pct", "precision", "recall", "f1", "tp", "fp", "fn", "tn"]:
    v = cur.get(k, "?")
    v2 = v4.get(k, "?")
    if isinstance(v, (int, float)) and isinstance(v2, (int, float)):
        if isinstance(v, float) and k not in ["tp","fp","fn","tn"]:
            d = v2 - v
            print(f"  {k:25s} {v*100 if k!='n_extreme' else v:>8.1f}      {v2*100 if k!='n_extreme' else v2:>8.1f}      {d*100 if k!='n_extreme' else d:>+8.1f}")
        else:
            d = v2 - v
            print(f"  {k:25s} {v:>8d}      {v2:>8d}      {d:+8d}")

# 8B: ROC AUC comparison
from sklearn.metrics import roc_auc_score
auc_v4 = roc_auc_score(y_true, df_v4["score_v2"].values)
auc_cur = roc_auc_score(y_true, df_current["score_v2"].values)
print(f"\n  ROC AUC: v2.9={auc_cur:.4f}, v4.0={auc_v4:.4f}, +{(auc_v4-auc_cur):.4f}")

# 8C: Top-k precision
print(f"\n  Top-k precision (v4.0):")
scores = df_v4["score_v2"].values
order = np.argsort(-scores)
sorted_y = y_true[order]
for k in [50, 100, 200, 500, 1000]:
    if k > len(sorted_y): continue
    pk = sorted_y[:k].mean()
    print(f"    Top {k:5d}: precision={pk:.3f} ({int(sorted_y[:k].sum())}/{k})")

# 8D: Cost-benefit estimation
print(f"\n  Estimated business impact (per 1000 products screened):")
print(f"    Using v2.9: ~{int(1000*cur['extreme_pct'])} flagged as extreme, "
      f"of which ~{int(1000*cur['extreme_pct']*cur['precision'])} correct, "
      f"~{int(1000*cur['extreme_pct']*(1-cur['precision']))} false alarms")
print(f"    Using v4.0: ~{int(1000*v4['extreme_pct'])} flagged as extreme, "
      f"of which ~{int(1000*v4['extreme_pct']*v4['precision'])} correct, "
      f"~{int(1000*v4['extreme_pct']*(1-v4['precision']))} false alarms")
print(f"    FP reduction: {int(1000*cur['extreme_pct']*(1-cur['precision'])) - int(1000*v4['extreme_pct']*(1-v4['precision']))} fewer FPs per 1000")

all_results["business_impact"] = {
    "auc_v4": float(auc_v4), "auc_current": float(auc_cur),
    "v4_metrics": v4, "current_metrics": cur,
}

# ════════════════════════════════════════════════════════════════
# CROSS-CHECK: Robustness validation
# ════════════════════════════════════════════════════════════════
print("\n" + "="*70)
print("CROSS-CHECK: Robustness & Sanity Checks")
print("="*70)

# Check 1: Do all extreme-risk products have at least ONE high factor score?
extreme_any_high = ((df_v4["risk_level_v4"]=="extreme") &
    ((df_v4["f4_v2"]>=70) | (df_v4["f5_v2"]>=70) | (df_v4["f1f_v2"]>=70))).sum()
extreme_total = (df_v4["risk_level_v4"]=="extreme").sum()
print(f"  Extreme products with >=1 factor >=70: {extreme_any_high}/{extreme_total} "
      f"({extreme_any_high/max(extreme_total,1)*100:.1f}%)")

# Check 2: Scores not driven by c6 only (c6 has low weight)
if "c6_v2" in df_v4.columns:
    c6_only_high = ((df_v4["risk_level_v4"]=="extreme") &
                    (df_v4["c6_v2"]>=70) &
                    (df_v4["f4_v2"]<70) & (df_v4["f5_v2"]<70) & (df_v4["f1f_v2"]<70)).sum()
    print(f"  Extreme driven SOLELY by c6 (no other factor>=70): {c6_only_high}")

# Check 3: How many products NEVER get flagged? (potential blind spots)
flagged_products = df_v4[df_v4["risk_level_v4"]=="extreme"]["product_id"].nunique()
total_products = df_v4["product_id"].nunique()
print(f"  Products ever flagged extreme: {flagged_products}/{total_products} "
      f"({flagged_products/total_products*100:.1f}%)")

# Check 4: What fraction of declined products are NEVER flagged?
declined_never_flagged = df_v4.groupby("product_id").agg(
    ever_extreme=(LABEL_COL, lambda x: ((df_v4.loc[x.index, "risk_level_v4"]=="extreme").any())),
    ever_declined=(LABEL_COL, "max"),
)
missed = ((declined_never_flagged["ever_declined"]==1) &
          (~declined_never_flagged["ever_extreme"])).sum()
total_declined_products = (declined_never_flagged["ever_declined"]==1).sum()
print(f"  Declined products NEVER flagged: {missed}/{total_declined_products} "
      f"({missed/max(total_declined_products,1)*100:.1f}%)")

# Check 5: Low-risk but still declined — how common?
low_risk_declined = ((df_v4["risk_level_v4"]=="low") & (df_v4[LABEL_COL]==1)).sum()
low_risk_total = (df_v4["risk_level_v4"]=="low").sum()
print(f"  Low-risk but declined: {low_risk_declined}/{low_risk_total} "
      f"({low_risk_declined/max(low_risk_total,1)*100:.1f}%)")

# ════════════════════════════════════════════════════════════════
# FINAL VERDICT
# ════════════════════════════════════════════════════════════════
print("\n" + "="*70)
print("FINAL VERDICT")
print("="*70)

verdict = {}
verdict["ground_truth"] = "PASS" if all_results["ground_truth"]["margin_drop_consistency_pct"] > 50 else "WARN"
verdict["calibration"] = "PASS" if all_results["calibration"]["monotonicity_violations"] == 0 else "WARN"
verdict["extreme_precision"] = "PASS" if all_results["calibration"]["extreme_precision"] and all_results["calibration"]["extreme_precision"] > 0.5 else "WARN"
verdict["lead_time"] = "PASS" if all_results.get("lead_time") and all_results["lead_time"]["median_months"] >= 2 else "WARN"
verdict["post_warning"] = "PASS" if all_results.get("post_warning") and all_results["post_warning"]["any_decline_12m_pct"] > 40 else "WARN"
verdict["fp_rate"] = "PASS" if all_results["calibration"]["extreme_fp_rate"] and all_results["calibration"]["extreme_fp_rate"] < 0.5 else "WARN"
verdict["improvement_over_v29"] = "PASS" if v4["precision"] > cur["precision"] else "FAIL"

overall_pass = sum(1 for v in verdict.values() if v == "PASS")
overall_warn = sum(1 for v in verdict.values() if v == "WARN")
overall_fail = sum(1 for v in verdict.values() if v == "FAIL")

print(f"\n  {'Check':30s} {'Result':10s}")
print(f"  {'-'*30} {'-'*10}")
for check, result in verdict.items():
    print(f"  {check:30s} {result:10s}")
print(f"\n  Overall: {overall_pass} PASS, {overall_warn} WARN, {overall_fail} FAIL "
      f"({overall_pass/max(overall_pass+overall_warn+overall_fail,1)*100:.0f}% pass rate)")

if all_results.get("lead_time"):
    print(f"\n  Decision: {'[OK] Model is usable for production' if v4['precision'] > 0.5 else '[REVIEW] Needs improvement'}")
    print(f"  Key strength: Precision {v4['precision']*100:.1f}% ({v4['tp']} correct out of {v4['n_extreme']} extreme)")
    print(f"  Key concern:  {all_results['calibration']['extreme_fp_count']} false alarms "
          f"({all_results['calibration']['extreme_fp_rate']*100:.1f}% of extreme)")
    if all_results.get("lead_time"):
        print(f"  Lead time:    {all_results['lead_time']['mean_months']:.1f}mo avg, "
              f"{all_results['lead_time']['pct_lead_ge3m']:.0f}% >= 3 months")

# Save all results
with open(os.path.join(OUT_DIR, "eval_results.json"), "w", encoding="utf-8") as f:
    json.dump(all_results, f, ensure_ascii=False, indent=2, default=str)
print(f"\nResults saved to {OUT_DIR}/")
print("Done!")
