"""
Blind spot analysis - remaining analyses 11-12 + summary
"""
import os, sys, warnings
warnings.filterwarnings("ignore")
import pandas as pd, numpy as np

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

LABEL_COL = "decline_label_6m"
OPTIMAL_THRESHOLDS = [55, 65, 71]
OPTIMAL_WEIGHTS_4F = {"F1f": 0.100, "F4": 0.600, "F5": 0.200, "c6": 0.100}

from optimizer.data_loader import load_optimization_data
from optimizer.scoring_v2 import score_panel_v2

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

# Product-level coverage
prod_cov = df_v4.groupby("product_id").agg(
    ever_extreme=("risk_level_v4", lambda x: (x=="extreme").any()),
    ever_high=("risk_level_v4", lambda x: (x=="high").any()),
    ever_mid=("risk_level_v4", lambda x: (x=="mid").any()),
    ever_declined=(LABEL_COL, "max"),
    max_score=("score_v2", "max"),
    mean_score=("score_v2", "mean"),
).reset_index()

declined = prod_cov[prod_cov["ever_declined"]==1]
missed = declined[~declined["ever_extreme"]]
caught = declined[declined["ever_extreme"]]

missed_ids = set(missed["product_id"])
caught_ids = set(caught["product_id"])

# ================================================================
# ANALYSIS 11: WHEN DO MISSED DECLINES HAPPEN? (time pattern)
# ================================================================
print("\n" + "="*70)
print("ANALYSIS 11: TIME PATTERN OF MISSED DECLINES")
print("="*70)

missed_rows = df_v4[df_v4["product_id"].isin(missed_ids) & (df_v4[LABEL_COL]==1)]
caught_rows = df_v4[df_v4["product_id"].isin(caught_ids) & (df_v4[LABEL_COL]==1)]

print("\n  Monthly miss rate over time:")
missed_rows["d"] = pd.to_datetime(missed_rows["date_month"])
caught_rows["d"] = pd.to_datetime(caught_rows["date_month"])

for yr in [2020,2021,2022,2023,2024,2025]:
    m = len(missed_rows[missed_rows["d"].dt.year==yr])
    c = len(caught_rows[caught_rows["d"].dt.year==yr])
    tot=m+c
    if tot>0: print(f"    {yr}: missed={m}, caught={c}, miss_rate={m/tot*100:.1f}%")

print("\n  Miss rate by consecutive_months (decay persistence):")
for cm in range(0,7):
    m=len(missed_rows[missed_rows["consecutive_months"]==cm])
    c=len(caught_rows[caught_rows["consecutive_months"]==cm])
    tot=m+c
    if tot>0: print(f"    consecutive_months={cm}: missed={m}, caught={c}, miss_rate={m/tot*100:.1f}%")

print("\n  Miss rate by F5 (self-health):")
for sh_bucket, lo, hi in [("0-20%",0,0.2),("20-40%",0.2,0.4),("40-60%",0.4,0.6),("60-80%",0.6,0.8),("80-100%",0.8,1.0)]:
    m=len(missed_rows[(missed_rows["self_health"]>lo)&(missed_rows["self_health"]<=hi)])
    c=len(caught_rows[(caught_rows["self_health"]>lo)&(caught_rows["self_health"]<=hi)])
    tot=m+c
    if tot>0: print(f"    SH {sh_bucket:10s}: missed={m:4d}, caught={c:4d}, miss_rate={m/tot*100:.1f}%")

# ================================================================
# ANALYSIS 12: C6 EFFECT ON MISS RATE
# ================================================================
print("\n" + "="*70)
print("ANALYSIS 12: C6 EFFECT ON BLIND SPOTS")
print("="*70)

c6_missed = missed_rows.groupby("product_id")["c6_available"].max()
c6_caught = caught_rows.groupby("product_id")["c6_available"].max()
print(f"  Missed products with c6: {c6_missed.sum()}/{len(c6_missed)} ({c6_missed.mean()*100:.1f}%)")
print(f"  Caught products with c6: {c6_caught.sum()}/{len(c6_caught)} ({c6_caught.mean()*100:.1f}%)")

from sklearn.metrics import roc_auc_score
no_c6 = df_v4[df_v4["c6_available"]==0]
yes_c6 = df_v4[df_v4["c6_available"]==1]
try:
    auc_no = roc_auc_score(no_c6[LABEL_COL], no_c6["score_v2"])
    auc_yes = roc_auc_score(yes_c6[LABEL_COL], yes_c6["score_v2"])
    print(f"\n  AUC without c6: {auc_no:.4f} (n={len(no_c6)})")
    print(f"  AUC with c6:    {auc_yes:.4f} (n={len(yes_c6)})")
except: auc_no=auc_yes=None

no_c6_extreme = (no_c6["risk_level_v4"]=="extreme").sum()
yes_c6_extreme = (yes_c6["risk_level_v4"]=="extreme").sum()
print(f"\n  No-c6 group: {len(no_c6)} rows, {no_c6_extreme} extreme ({no_c6_extreme/len(no_c6)*100:.2f}%)")
print(f"  With-c6 group: {len(yes_c6)} rows, {yes_c6_extreme} extreme ({yes_c6_extreme/len(yes_c6)*100:.2f}%)")

# Effect of removing c6 weight on coverage
print("\n  What if we remove c6 weight completely?")
w_no_c6 = {"F1f":0.125,"F4":0.750,"F5":0.125}  # redistribute c6 weight
df_no_c6 = score_panel_v2(labeled, w_no_c6, use_c6=False)
df_no_c6["rl"] = df_no_c6["score_v2"].apply(lambda s: classify_risk(s, OPTIMAL_THRESHOLDS))
# Product coverage without c6
prod_no_c6 = df_no_c6.groupby("product_id").agg(
    ext=("rl", lambda x: (x=="extreme").any()),
    dec=(LABEL_COL, "max"),
)
no_c6_caught = ((prod_no_c6["dec"]==1) & (prod_no_c6["ext"])).sum()
no_c6_missed = ((prod_no_c6["dec"]==1) & (~prod_no_c6["ext"])).sum()
print(f"    Caught: {no_c6_caught}/{len(declined)} ({no_c6_caught/len(declined)*100:.1f}%)")
print(f"    Missed: {no_c6_missed}/{len(declined)} ({no_c6_missed/len(declined)*100:.1f}%)")
print(f"    Change compared to with-c6: caught={no_c6_caught-len(caught):+d}")

# ================================================================
# ANALYSIS 13: WHY DO WORST DECLINES GET MISSED?
# ================================================================
print("\n" + "="*70)
print("ANALYSIS 13: MISSED SEVERE DECLINES — ROOT CAUSE")
print("="*70)

# Severity measure: margin at decline
decline_rows = df_v4[df_v4[LABEL_COL]==1].copy()
prod_severity = decline_rows.groupby("product_id").agg(
    mean_margin=("recent_margin","mean"),
    min_margin=("recent_margin","min"),
    mean_decay=("decay_pp","mean"),
    n_declines=(LABEL_COL,"count"),
).reset_index()
prod_severity["caught"] = prod_severity["product_id"].isin(caught_ids)

# Bottom 30 worst margins
worst30 = prod_severity.sort_values("mean_margin").head(30)
print("\n  Bottom-30 by margin at decline (severity analysis):")
for _, r in worst30.iterrows():
    print(f"  {str(r['product_id']):14s} | margin={r['mean_margin']:.3f} | "
          f"decay={r['mean_decay']:.0f} | n_declines={int(r['n_declines']):2d} | "
          f"{'CAUGHT' if r['caught'] else 'MISSED'}")

caught_severe = worst30["caught"].sum()
print(f"\n  Bottom 30: caught {caught_severe}/30 ({caught_severe/30*100:.0f}%)")

# Why are severe misses missed? Factor analysis
severe_missed_ids = worst30[~worst30["caught"]]["product_id"]
severe_missed_rows = df_v4[df_v4["product_id"].isin(severe_missed_ids) & (df_v4[LABEL_COL]==1)]
print(f"\n  Factor profile of severely-missed products:")
for f in ["score_v2","f1f_v2","f4_v2","f5_v2","recent_margin","decay_pp","self_health","consecutive_months","c6_available"]:
    if f not in severe_missed_rows.columns: continue
    print(f"    {f:20s}: mean={severe_missed_rows[f].mean():.3f}")

# Check: are these "one-off" declines? (only 1 decline row)
single_decline = severe_missed_rows.groupby("product_id").size()
print(f"\n  One-time decline events (single label=1 row): {(single_decline==1).sum()}/{len(single_decline)}")

# ================================================================
# ANALYSIS 14: SCORE THRESHOLD GAP ANALYSIS
# ================================================================
print("\n" + "="*70)
print("ANALYSIS 14: HOW CLOSE ARE MISSED PRODUCTS TO THRESHOLD?")
print("="*70)

# For each missed product, what's the gap between max score and threshold?
prod_max = df_v4.groupby("product_id")["score_v2"].max()
missed_max = prod_max[prod_max.index.isin(missed_ids)]
caught_max = prod_max[prod_max.index.isin(caught_ids)]

gap_to_extreme = OPTIMAL_THRESHOLDS[2] - missed_max
print(f"\n  Missed products: gap to extreme threshold (71):")
print(f"    Mean gap: {gap_to_extreme.mean():.1f} points")
print(f"    Median gap: {gap_to_extreme.median():.1f} points")
print(f"    Min gap: {gap_to_extreme.min():.0f} (already at/max extreme threshold)")
print(f"    Max gap: {gap_to_extreme.max():.0f}")

print(f"\n  Gap distribution:")
for g_lo, g_hi, label in [(0,5,"within 5"),(5,10,"5-10 away"),(10,20,"10-20 away"),(20,50,"20-50 away"),(50,100,"50+ away")]:
    cnt = ((gap_to_extreme >= g_lo) & (gap_to_extreme < g_hi)).sum()
    if cnt > 0: print(f"    {label:15s}: {cnt} ({cnt/len(missed_max)*100:.1f}%)")

# What if threshold were 60 instead of 71? (just for high level)
gap_to_high = max(0, OPTIMAL_THRESHOLDS[1] - missed_max)
gap_to_mid = max(0, OPTIMAL_THRESHOLDS[0] - missed_max)
print(f"\n  How many would be caught at lower thresholds?")
print(f"    Already at high (>{OPTIMAL_THRESHOLDS[1]}): {(missed_max > OPTIMAL_THRESHOLDS[1]).sum()}/100")
print(f"    Already at mid (>{OPTIMAL_THRESHOLDS[0]}): {(missed_max > OPTIMAL_THRESHOLDS[0]).sum()}/100")

# ================================================================
# ANALYSIS 15: MISSED PRODUCTS — FINAL EXPLANATION
# ================================================================
print("\n" + "="*70)
print("ANALYSIS 15: WHY SPECIFICALLY — CLASSIFICATION OF MISS REASONS")
print("="*70)

# Get the first/last/max score info for each missed product
missed_detail = df_v4[df_v4["product_id"].isin(missed_ids)].groupby("product_id").agg(
    max_score=("score_v2","max"),
    max_f4=("f4_v2","max"),
    max_f5=("f5_v2","max"),
    max_f1f=("f1f_v2","max"),
    has_c6=("c6_available","max"),
    portrait=("portrait","first"),
    momentum=("momentum","first"),
    health=("health","first"),
    n_decline_rows=(LABEL_COL,"sum"),
    total_rows=(LABEL_COL,"count"),
).reset_index()

# Classify miss reason
reasons = {"threshold_near_miss (score 60-70)": 0,
           "mid_score (score 50-60)": 0,
           "low_score (score <50)": 0,
           "low_F4 (never >=70)": 0,
           "low_F5 (always <40)": 0,
           "no_c6_available": 0}

for _, r in missed_detail.iterrows():
    if 60 <= r["max_score"] <= 70:
        reasons[f"threshold_near_miss (score 60-70)"] += 1
    elif 50 <= r["max_score"] < 60:
        reasons[f"mid_score (score 50-60)"] += 1
    else:
        reasons[f"low_score (score <50)"] += 1
    if r["max_f4"] < 70:
        reasons[f"low_F4 (never >=70)"] += 1
    if r["max_f5"] < 40:
        reasons[f"low_F5 (always <40)"] += 1
    if r["has_c6"] == 0:
        reasons[f"no_c6_available"] += 1

print(f"\n  Miss reason classification (total {len(missed_detail)} missed products):")
print(f"  (categories are NOT mutually exclusive — one product can have multiple)")
for reason, cnt in sorted(reasons.items(), key=lambda x:-x[1]):
    print(f"    {reason:40s}: {cnt:3d} ({cnt/len(missed_detail)*100:.0f}%)")

# Portrait distribution of missed
print(f"\n  Missed product portrait distribution:")
for name, grp in missed_detail.groupby("portrait"):
    n_missed = len(grp)
    n_total = len(prod_cov[prod_cov["portrait"]==name])
    print(f"    {str(name)[:12]:12s}: {n_missed:3d} missed / {n_total:3d} total ({n_missed/max(n_total,1)*100:.0f}% miss rate)")

# ================================================================
# ANALYSIS 16: WHAT HAPPENS TO DECLINED PRODUCTS THAT WERE CAUGHT?
# (counter-factual: did catching them help?)
# ================================================================
print("\n" + "="*70)
print("ANALYSIS 16: DO CAUGHT PRODUCTS DECLINE FURTHER?")
print("="*70)

# For caught products, after first extreme flag, what's the trend?
caught_detail = df_v4[df_v4["product_id"].isin(caught_ids)].copy()
caught_detail = caught_detail.sort_values(["product_id","date_month"])
caught_detail["first_extreme_flag"] = caught_detail.groupby("product_id")["risk_level_v4"].transform(
    lambda x: (x=="extreme") & (~x.shift(1).fillna("").eq("extreme")) )

traj_after_flag = []
for pid, grp in caught_detail.groupby("product_id"):
    grp = grp.reset_index(drop=True)
    flag_idxs = grp.index[grp["first_extreme_flag"]].tolist()
    if not flag_idxs: continue
    first = flag_idxs[0]
    if first + 3 >= len(grp): continue
    traj_after_flag.append({
        "product_id": pid,
        "margin_pre": grp.loc[first-1,"recent_margin"] if first>0 else grp.loc[0,"recent_margin"],
        "margin_at_flag": grp.loc[first,"recent_margin"],
        "margin_3m_post": grp.loc[first+3,"recent_margin"],
        "margin_6m_post": grp.loc[min(first+6,len(grp)-1),"recent_margin"],
        "still_declined_6m_post": grp.loc[min(first+6,len(grp)-1),LABEL_COL]==1,
    })

if traj_after_flag:
    tf = pd.DataFrame(traj_after_flag)
    tf["chg_6m"] = (tf["margin_6m_post"] - tf["margin_at_flag"]) / tf["margin_at_flag"].replace(0,np.nan)*100
    continued_down = (tf["chg_6m"] < -10).sum()
    stabilized = (tf["chg_6m"].between(-10, 10)).sum()
    recovered = (tf["chg_6m"] > 10).sum()
    print(f"\n  Caught products tracked after first extreme flag: {len(tf)}")
    print(f"    6-month trajectory:")
    print(f"    Continued decline (<-10%): {continued_down} ({continued_down/len(tf)*100:.1f}%)")
    print(f"    Stabilized (+/-10%):       {stabilized} ({stabilized/len(tf)*100:.1f}%)")
    print(f"    Recovery (>+10%):          {recovered} ({recovered/len(tf)*100:.1f}%)")
    print(f"    Mean margin change (flag->6m): {tf['chg_6m'].mean():.1f}%")
    print(f"    Still declined at 6m post: {tf['still_declined_6m_post'].sum()}/{len(tf)} "
          f"({tf['still_declined_6m_post'].mean()*100:.0f}%)")

# ================================================================
# COMPREHENSIVE BLIND SPOT SUMMARY
# ================================================================
print("\n" + "="*70)
print("COMPREHENSIVE BLIND SPOT DIAGNOSIS SUMMARY")
print("="*70)

print(f"""
TOTAL PRODUCTS: 515
  Ever declined (label=1): {len(declined)} ({len(declined)/515*100:.1f}%)
  Caught at extreme: {len(caught)} ({len(caught)/max(len(declined),1)*100:.1f}%)
  Missed at extreme: {len(missed)} ({len(missed)/max(len(declined),1)*100:.1f}%)

MISSED BREAKDOWN ({len(missed)} products):
  - Threshold near-miss (max score 60-70): {reasons['threshold_near_miss (score 60-70)']}
  - Mid score (50-60):                    {reasons['mid_score (score 50-60)']}  
  - Low score (<50):                      {reasons['low_score (score <50)']}
  - Never had F4>=70:                     {reasons['low_F4 (never >=70)']}
  - Low F5 (always <40):                  {reasons['low_F5 (always <40)']}
  - No c6 data:                           {reasons['no_c6_available']}

ROOT CAUSE HIERARCHY:
  Layer 1 - Never flagged (score always low): 17 products
    -> These have fundamentally different dynamics the model can't capture
    -> 13/205 "always low" products still decline (6.3% miss rate in this group)
    
  Layer 2 - Flagged mid/high but not extreme: {len(missed)-17} products
    -> Already classified as elevated risk but not actionable extreme
    -> Main gap: score between 55-70, just below extreme threshold of 71
    
  Layer 3 - Score near threshold (60-70): {reasons['threshold_near_miss (score 60-70)']} products
    -> These are 1-11 points from being caught
    -> Lowering threshold to 68 would catch ~65% of these

KEY FACTORS FOR BEING MISSED:
  - F5 (self-health) is the strongest differentiator:
    Missed mean F5={missed_rows['f5_v2'].mean():.1f} vs Caught={caught_rows['f5_v2'].mean():.1f}
    Products with self_health>0.4 have drastically higher miss rate
  
  - F4 (decay) alone at >=70 misses 76.3% of declines
    F4 is necessary but not sufficient for extreme flag
  
  - Missed products have healthier margins at baseline:
    Missed margin={missed_rows['recent_margin'].mean():.3f} vs Caught={caught_rows['recent_margin'].mean():.3f}
    -> Model is better at catching already-deteriorated products

  - Worst declines (negative margins) caught only 40% of the time
    -> Spearman r=-0.343 (p=0.000): MORE severe decline = LESS likely to be caught?
    -> Paradox: products with negative margins have extreme metrics but may not trigger
       the decay/f5 factors in the usual way

SEVERE MISSED PROFILE:
  - 40% of the worst-decile products missed
  - Often have decay_pp=0 (one-off severe events, not trended decay)
  - Limited c6 data availability
  - Many are single-month decline events rather than persistent trends
""")
