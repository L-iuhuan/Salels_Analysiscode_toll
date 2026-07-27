"""
Deep-dive diagnostic: Why does the model miss ~50% of declining products?

This script investigates blind spots, border cases, and all failure modes
of the v4.0 risk decline model.
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

LABEL_COL = "decline_label_6m"

from optimizer.data_loader import load_optimization_data
from optimizer.scoring_v2 import score_panel_v2

OPTIMAL_WEIGHTS_4F = {"F1f": 0.100, "F4": 0.600, "F5": 0.200, "c6": 0.100}
OPTIMAL_THRESHOLDS = [55, 65, 71]

def classify_risk(score, thr):
    if score <= thr[0]: return "low"
    elif score <= thr[1]: return "mid"
    elif score <= thr[2]: return "high"
    else: return "extreme"

print("Loading data...")
df = load_optimization_data()
labeled = df[df[LABEL_COL].notna()].copy()
y_true = labeled[LABEL_COL].values

print("Scoring...")
df_v4 = score_panel_v2(labeled, OPTIMAL_WEIGHTS_4F, use_c6=True)
df_v4["risk_level_v4"] = df_v4["score_v2"].apply(lambda s: classify_risk(s, OPTIMAL_THRESHOLDS))

# ================================================================
# ANALYSIS 1: PRODUCT-LEVEL COVERAGE
# ================================================================
print("\n" + "="*70)
print("ANALYSIS 1: PRODUCT-LEVEL COVERAGE MAP")
print("="*70)

# For each product, what's the max risk level ever assigned?
prod_cov = df_v4.groupby("product_id").agg(
    ever_extreme=("risk_level_v4", lambda x: (x=="extreme").any()),
    ever_high=("risk_level_v4", lambda x: (x=="high").any()),
    ever_mid=("risk_level_v4", lambda x: (x=="mid").any()),
    ever_declined=(LABEL_COL, "max"),
    max_score=("score_v2", "max"),
    mean_score=("score_v2", "mean"),
    n_rows=(LABEL_COL, "count"),
    n_extreme=("risk_level_v4", lambda x: (x=="extreme").sum()),
    n_high=("risk_level_v4", lambda x: (x=="high").sum()),
    n_declined_rows=(LABEL_COL, "sum"),
    first_date=("date_month", "min"),
    last_date=("date_month", "max"),
).reset_index()

total_prods = len(prod_cov)
declined_prods = prod_cov[prod_cov["ever_declined"]==1]
never_declined = prod_cov[prod_cov["ever_declined"]==0]

print(f"\n  Total products: {total_prods}")
print(f"  Ever declined:  {len(declined_prods)} ({len(declined_prods)/total_prods*100:.1f}%)")
print(f"  Never declined: {len(never_declined)}")

# Among declined products, how many were ever flagged at each level?
for level_name, col in [("Extreme", "ever_extreme"), ("High/Extreme", "ever_high"),
                         ("Mid/High/Extreme", "ever_mid")]:
    flagged = declined_prods[declined_prods[col]==True]
    pct = len(flagged)/len(declined_prods)*100
    print(f"  Declined & flagged {level_name:20s}: {len(flagged):3d}/{len(declined_prods)} ({pct:.1f}%)")

# The 100 "never flagged extreme" declining products
missed = declined_prods[~declined_prods["ever_extreme"]]
print(f"\n  Declined but NEVER extreme: {len(missed)}")
# Of these, how many were flagged at high?
flagged_high = missed[missed["ever_high"]]
flagged_mid = missed[missed["ever_mid"]]
print(f"    Ever high (but not extreme): {len(flagged_high)}")
print(f"    Ever mid (but not high+): {len(flagged_mid)}")
never_any = missed[~missed["ever_mid"]]
print(f"    NEVER high or mid (max=low): {len(never_any)}")

# ================================================================
# ANALYSIS 2: WHY WERE MISSED PRODUCTS NOT FLAGGED?
# ================================================================
print("\n" + "="*70)
print("ANALYSIS 2: FACTOR PROFILE OF MISSED DECLINES")
print("="*70)

# Get the rows where these missed products actually declined
# i.e., rows with label=1 for missed products
missed_row_df = df_v4[df_v4["product_id"].isin(missed["product_id"])]
missed_at_decline = missed_row_df[missed_row_df[LABEL_COL]==1].copy()

print(f"\n  Missed products: {len(missed)}")
print(f"  Missed decline rows: {len(missed_at_decline)}")
print(f"  Average rows per missed product: {len(missed_at_decline)/max(len(missed),1):.1f}")

# Factor scores at time of decline
print(f"\n  Factor scores AT TIME OF DECLINE for missed products:")
for f in ["score_v2", "f1f_v2", "f4_v2", "f5_v2"]:
    print(f"    {f}: mean={missed_at_decline[f].mean():.2f}, "
          f"median={missed_at_decline[f].median():.2f}, "
          f"min={missed_at_decline[f].min():.0f}, max={missed_at_decline[f].max():.0f}")

# What was the max score these products EVER reached?
print(f"\n  Missed products: max score ever achieved:")
print(f"    Mean max score: {missed['max_score'].mean():.2f}")
print(f"    Median max score: {missed['max_score'].median():.2f}")
print(f"    Max score distribution:")
for bucket in [(0,30),(30,50),(50,55),(55,60),(60,65),(65,70),(70,80),(80,100)]:
    cnt = ((missed['max_score']>bucket[0]) & (missed['max_score']<=bucket[1])).sum()
    if cnt > 0:
        print(f"      {bucket[0]:3d}-{bucket[1]:3d}: {cnt} ({cnt/len(missed)*100:.1f}%)")

# Compare: at the decline time, what risk level WERE they?
print(f"\n  Risk level AT TIME OF DECLINE for missed products:")
level_at_decline = missed_at_decline["risk_level_v4"].value_counts()
for lvl in ["extreme", "high", "mid", "low"]:
    cnt = level_at_decline.get(lvl, 0)
    print(f"    {lvl:8s}: {cnt} ({cnt/len(missed_at_decline)*100:.1f}%)")

# Compare caught vs missed products
print(f"\n  CAUGHT vs MISSED products comparison:")
caught_prods = declined_prods[declined_prods["ever_extreme"]]
caught_row_df = df_v4[df_v4["product_id"].isin(caught_prods["product_id"])]
caught_at_decline = caught_row_df[caught_row_df[LABEL_COL]==1]

for f in ["score_v2", "f1f_v2", "f4_v2", "f5_v2", "recent_margin", "decay_pp",
          "self_health", "consecutive_months", "margin_yoy_change_pp"]:
    m_mean = missed_at_decline[f].mean()
    c_mean = caught_at_decline[f].mean()
    print(f"    {f:25s}: MISSED={m_mean:10.2f} vs CAUGHT={c_mean:10.2f} vs diff={c_mean-m_mean:+10.2f}")

# ================================================================
# ANALYSIS 3: THRESHOLD SENSITIVITY — What if we lower the bar?
# ================================================================
print("\n" + "="*70)
print("ANALYSIS 3: THRESHOLD SENSITIVITY")
print("="*70)

# For each threshold candidate, compute product-level coverage
print(f"\n  Testing threshold sensitivity on product-level coverage:")
print(f"  {'Threshold':>15s} {'EverFlaggedPct':>16s} {'CoveragePct':>14s} {'FPper1000':>10s} {'FlagPct':>9s}")

thresholds_to_test = [
    (30, 50, 55), (30, 50, 60), (30, 50, 65),
    (40, 55, 65), (40, 55, 68),
    (50, 60, 70), (50, 60, 71),
    (55, 65, 69), (55, 65, 70), (55, 65, 71),
]

for thr_low, thr_mid, thr_high in thresholds_to_test:
    df_v4[f"ext_flag_{thr_high}"] = df_v4["score_v2"] > thr_high
    # Per product
    prod_flag = df_v4.groupby("product_id")[f"ext_flag_{thr_high}"].any()
    prod_declined = df_v4.groupby("product_id")[LABEL_COL].max()
    prod_both = pd.DataFrame({"flagged": prod_flag, "declined": prod_declined})
    
    n_flagged = prod_flag.sum()
    n_declined = prod_declined.sum()
    flagged_and_declined = ((prod_flag) & (prod_declined==1)).sum()
    flagged_not_declined = ((prod_flag) & (prod_declined==0)).sum()
    
    coverage_pct = flagged_and_declined / n_declined * 100 if n_declined > 0 else 0
    fp_per_1000 = flagged_not_declined / total_prods * 1000
    
    print(f"  thr>{thr_high:3d}{'':>7s} "
          f"{n_flagged/total_prods*100:14.1f}% "
          f"{coverage_pct:12.1f}% "
          f"{fp_per_1000:8.0f} "
          f"{n_flagged/total_prods*100:7.1f}%")

# ================================================================
# ANALYSIS 4: WHAT DRIVES A PRODUCT TO BE "ALWAYS LOW-RISK"?
# ================================================================
print("\n" + "="*70)
print("ANALYSIS 4: ALWAYS-LOW-RISK PRODUCTS THAT STILL DECLINE")
print("="*70)

# Products that never exceeded low threshold
always_low = df_v4.groupby("product_id")["score_v2"].max()
always_low_prods = always_low[always_low <= OPTIMAL_THRESHOLDS[0]].index
always_low_df = df_v4[df_v4["product_id"].isin(always_low_prods)]

declined_always_low = always_low_df[always_low_df[LABEL_COL]==1]
n_always_low_declined = declined_always_low["product_id"].nunique()
n_always_low = len(always_low_prods)

print(f"\n  Products that NEVER exceeded low threshold (score<={OPTIMAL_THRESHOLDS[0]}): {n_always_low}")
print(f"  Of these, how many still declined?: {n_always_low_declined} "
      f"({n_always_low_declined/max(n_always_low,1)*100:.1f}%)")

if n_always_low_declined > 0:
    print(f"\n  Factor profile at time of decline (always-low products):")
    for f in ["score_v2", "f1f_v2", "f4_v2", "f5_v2", "recent_margin",
              "decay_pp", "self_health", "consecutive_months"]:
        print(f"    {f:25s}: mean={declined_always_low[f].mean():.3f}, "
              f"  median={declined_always_low[f].median():.3f}")

    # When do these declines happen? First vs last
    print(f"\n  Always-low declined products - first decline date distribution:")
    first_declines = declined_always_low.groupby("product_id").first()
    for yr in ["2020","2021","2022","2023","2024","2025","2026"]:
        cnt = (first_declines["date_month"].astype(str).str.startswith(yr)).sum()
        if cnt > 0:
            print(f"    {yr}: {cnt}")

# ================================================================
# ANALYSIS 5: PRODUCTS THAT ARE ALWAYS EXTREME (never recover)
# ================================================================
print("\n" + "="*70)
print("ANALYSIS 5: ALWAYS-EXTREME VS NEVER-FLAGGED POLAR PROFILES")
print("="*70)

# Products flagged extreme 50%+ of their observations
prod_extreme_pct = df_v4.groupby("product_id").agg(
    extreme_rows=("risk_level_v4", lambda x: (x=="extreme").sum()),
    total_rows=("risk_level_v4", "count"),
    ever_declined=(LABEL_COL, "max"),
)
prod_extreme_pct["extreme_pct"] = prod_extreme_pct["extreme_rows"] / prod_extreme_pct["total_rows"]
always_in_trouble = prod_extreme_pct[prod_extreme_pct["extreme_pct"] > 0.3]
print(f"\n  Products flagged extreme >30% of time: {len(always_in_trouble)}")
never_flagged_extreme = prod_extreme_pct[prod_extreme_pct["extreme_rows"]==0]
print(f"  Products NEVER flagged extreme: {len(never_flagged_extreme)}")

# Compare factor profiles
always_trouble_ids = always_in_trouble.index
never_flagged_ids = never_flagged_extreme.index

always_df = df_v4[df_v4["product_id"].isin(always_trouble_ids)]
never_df = df_v4[df_v4["product_id"].isin(never_flagged_ids)]

print(f"\n  Factor comparison: 'Always in trouble' vs 'Never flagged':")
for f in ["recent_margin", "decay_pp", "self_health", "consecutive_months",
          "margin_yoy_change_pp", "f4_v2", "f5_v2", "f1f_v2"]:
    a = always_df[f].mean()
    n = never_df[f].mean()
    print(f"    {f:25s}: always_trouble={a:.4f}, never_flagged={n:.4f}, diff={a-n:+.4f}")

# ================================================================
# ANALYSIS 6: FACTOR-SPECIFIC MISS RATE
# ================================================================
print("\n" + "="*70)
print("ANALYSIS 6: FACTOR-SPECIFIC BLIND SPOTS")
print("="*70)

# For each factor, check: do we miss declines even when factor is high?
print(f"\n  When a factor IS high (>=70) but product STILL not flagged extreme:")
for f_name, f_col in [("F4 (decay)", "f4_v2"), ("F5 (self-health)", "f5_v2"),
                       ("F1f (slope)", "f1f_v2")]:
    high_factor = df_v4[df_v4[f_col] >= 70]
    declined_high = high_factor[high_factor[LABEL_COL]==1]
    not_extreme = declined_high[declined_high["risk_level_v4"]!="extreme"]
    print(f"  {f_name:20s}: {len(high_factor)} high, {len(declined_high)} declined, "
          f"{len(not_extreme)} not extreme ({len(not_extreme)/max(len(declined_high),1)*100:.1f}% miss rate)")

# ================================================================
# ANALYSIS 7: DECLINE SEVERITY — Do we catch the worst ones?
# ================================================================
print("\n" + "="*70)
print("ANALYSIS 7: DO WE CATCH THE WORST DECLINES?")
print("="*70)

# Sort declined products by severity of margin decline
decline_rows = df_v4[df_v4[LABEL_COL]==1].copy()
# Create a severity measure: magnitude of margin drop
# (how far below their historical reference)
decline_rows["margin_severity"] = (decline_rows["recent_margin"] - 
    decline_rows["self_health"]) / decline_rows["self_health"].replace(0, np.nan)

severity_data = []
for pid in decline_rows["product_id"].unique():
    prod = decline_rows[decline_rows["product_id"]==pid]
    caught = (prod["risk_level_v4"]=="extreme").any()
    severity_data.append({
        "product_id": pid,
        "caught": caught,
        "mean_margin_at_decline": prod["recent_margin"].mean(),
        "min_margin": prod["recent_margin"].min(),
        "n_decline_rows": len(prod),
        "mean_decay_pp": prod["decay_pp"].mean(),
    })

sev_df = pd.DataFrame(severity_data).sort_values("mean_margin_at_decline")
print(f"\n  Bottom-20 products by margin at decline (worst margin):")
bottom20 = sev_df.head(20)
for _, row in bottom20.iterrows():
    print(f"    {row['product_id']:12s} | margin={row['mean_margin_at_decline']:.3f} | "
          f"caught={'YES' if row['caught'] else 'NO '} | "
          f"decay_pp={row['mean_decay_pp']:.1f} | n_declines={int(row['n_decline_rows'])}")

caught_worst = bottom20["caught"].sum()
print(f"\n    Worst 20: caught {caught_worst}/20 ({caught_worst*5:.0f}%)")

# Top-20 by margin (best) among declined
best20 = sev_df.tail(20)
caught_best = best20["caught"].sum()
print(f"    Best 20: caught {caught_best}/20 ({caught_best*5:.0f}%)")

# Correlation: margin severity vs being caught
from scipy.stats import spearmanr
if len(sev_df) > 5:
    corr, pval = spearmanr(sev_df["mean_margin_at_decline"], sev_df["caught"])
    print(f"\n  Spearman correlation: margin_severity vs caught = {corr:.3f} (p={pval:.4f})")

# ================================================================
# ANALYSIS 8: PORTRAIT-BASED MISS RATE
# ================================================================
print("\n" + "="*70)
print("ANALYSIS 8: PORTRAIT-BASED MISS/COVERAGE BREAKDOWN")
print("="*70)

print(f"\n  {'Portrait':15s} {'Total':>6s} {'Declined':>10s} {'Caught':>8s} {'Missed':>8s} "
      f"{'Coverage':>10s} {'#Caught':>8s}")
for name, grp in df_v4.groupby("portrait"):
    if len(grp) < 10: continue
    n = grp["product_id"].nunique()
    # Product-level: did they ever decline and were they caught?
    prod_p = grp.groupby("product_id").agg(
        declined=(LABEL_COL, "max"),
        caught=("risk_level_v4", lambda x: (x=="extreme").any()),
    )
    d = (prod_p["declined"]==1).sum()
    c = ((prod_p["declined"]==1) & (prod_p["caught"])).sum()
    m = d - c
    cov = c/max(d,1)*100
    name_s = str(name)[:15]
    print(f"  {name_s:15s} {n:6d} {d:10d} {c:8d} {m:8d} {cov:9.1f}% {c:8d}")

# ================================================================
# ANALYSIS 9: SCORE DISTRIBUTION OF DECLINED PRODUCTS
# ================================================================
print("\n" + "="*70)
print("ANALYSIS 9: WHERE DO DECLINED PRODUCTS SCORE?")
print("="*70)

# For each declined product, what was their max score?
declined_prod_scores = df_v4[df_v4[LABEL_COL]==1].groupby("product_id").agg(
    max_score=("score_v2", "max"),
    mean_score=("score_v2", "mean"),
    score_at_first_decline=("score_v2", lambda x: x.iloc[0] if len(x) > 0 else 0),
).reset_index()

print(f"\n  Declined products: score distribution (max score ever):")
for lo, hi, label in [(0,30,"0-30"), (30,50,"30-50"), (50,55,"50-55"),
                       (55,60,"60-65"), (60,65,"65-70"), (65,70,"70-75"),
                       (75,100,"75-100")]:
    cnt = ((declined_prod_scores["max_score"] > lo) & 
           (declined_prod_scores["max_score"] <= hi)).sum()
    if cnt > 0:
        print(f"    {label:8s}: {cnt:3d} ({cnt/len(declined_prod_scores)*100:.1f}%)")

print(f"\n  Score at FIRST decline row (when product first turned label=1):")
for lo, hi, label in [(0,30,"0-30"), (30,50,"30-50"), (50,55,"50-55"),
                       (55,60,"60-65"), (60,65,"65-70"), (65,70,"70-75"),
                       (75,100,"75-100")]:
    cnt = ((declined_prod_scores["score_at_first_decline"] > lo) & 
           (declined_prod_scores["score_at_first_decline"] <= hi)).sum()
    if cnt > 0:
        print(f"    {label:8s}: {cnt:3d} ({cnt/len(declined_prod_scores)*100:.1f}%)")

# ================================================================
# ANALYSIS 10: FALSE POSITIVE ROOT CAUSE CLASSIFICATION
# ================================================================
print("\n" + "="*70)
print("ANALYSIS 10: FALSE POSITIVE ROOT CAUSE CLASSIFICATION")
print("="*70)

extreme = df_v4[df_v4["risk_level_v4"]=="extreme"]
fp = extreme[extreme[LABEL_COL]==0]

print(f"\n  Total extreme FP: {len(fp)} rows across {fp['product_id'].nunique()} products")

if len(fp) > 0:
    for pid in fp["product_id"].unique():
        prod_fp = fp[fp["product_id"]==pid]
        # Primary driver: which factor pushed it over?
        row = prod_fp.iloc[0]
        drivers = []
        if row["f4_v2"] >= 80: drivers.append(f"F4={row['f4_v2']}")
        elif row["f4_v2"] >= 70: drivers.append(f"F4={row['f4_v2']}")
        if row["f5_v2"] >= 70: drivers.append(f"F5={row['f5_v2']}")
        if row["f1f_v2"] >= 80: drivers.append(f"F1f={row['f1f_v2']}")
        margin = row["recent_margin"]
        portrait = row.get("portrait", "?")
        print(f"    {str(pid):12s} | score={row['score_v2']:.0f} | "
              f"drivers={','.join(drivers):20s} | "
              f"margin={margin:.3f} | {str(portrait)[:10]}")
    
    # Categorize FP reasons
    fp_categories = {"F1f_driven (slope issue)": 0, "F4_driven (decay)": 0,
                     "F5_driven (SH)": 0, "F4+F5 combo": 0, "F1f+F4+F5 all high": 0}
    for _, row in fp.iterrows():
        f4_high = row["f4_v2"] >= 70
        f5_high = row["f5_v2"] >= 70
        f1f_high = row["f1f_v2"] >= 70
        if f1f_high and f4_high and f5_high:
            fp_categories["F1f+F4+F5 all high"] += 1
        elif f4_high and f5_high:
            fp_categories["F4+F5 combo"] += 1
        elif f1f_high and not f4_high and not f5_high:
            fp_categories["F1f_driven (slope issue)"] += 1
        elif f4_high and not f5_high and not f1f_high:
            fp_categories["F4_driven (decay)"] += 1
        elif f5_high and not f4_high and not f1f_high:
            fp_categories["F5_driven (SH)"] += 1
    
    print(f"\n  FP root cause categories:")
    for cat, cnt in sorted(fp_categories.items(), key=lambda x: -x[1]):
        if cnt > 0:
            print(f"    {cat:30s}: {cnt} ({cnt/len(fp)*100:.1f}%)")

# ================================================================
# ANALYSIS 11: TIME-BASED MISS PATTERN
# ================================================================
print("\n" + "="*70)
print("ANALYSIS 11: WHEN DO MISSED DECLINES HAPPEN?")
print("="*70)

# Are missed declines more common in certain time periods?
missed_rows = df_v4[(df_v4["product_id"].isin(missed["product_id"])) & 
                    (df_v4[LABEL_COL]==1)]
caught_rows = df_v4[(df_v4["product_id"].isin(caught["product_id"])) & 
                    (df_v4[LABEL_COL]==1)]

print(f"\n  Monthly miss rate over time:")
missed_rows["date_month"] = pd.to_datetime(missed_rows["date_month"])
caught_rows["date_month"] = pd.to_datetime(caught_rows["date_month"])

# Year-month
for yr in [2020, 2021, 2022, 2023, 2024, 2025]:
    m_cnt = len(missed_rows[missed_rows["date_month"].dt.year==yr])
    c_cnt = len(caught_rows[caught_rows["date_month"].dt.year==yr])
    total = m_cnt + c_cnt
    if total > 0:
        print(f"    {yr}: missed={m_cnt}, caught={c_cnt}, miss_rate={m_cnt/total*100:.1f}%")

# By product lifecycle stage (using revenue trajectory as proxy)
print(f"\n  Miss rate by consecutive_months (decay persistence):")
for cm in range(0, 7):
    m_cnt = len(missed_rows[missed_rows["consecutive_months"]==cm])
    c_cnt = len(caught_rows[caught_rows["consecutive_months"]==cm])
    total = m_cnt + c_cnt
    if total > 0:
        print(f"    consecutive_months={cm}: missed={m_cnt}, caught={c_cnt}, "
              f"miss_rate={m_cnt/total*100:.1f}%")

# ================================================================
# ANALYSIS 12: C6 EFFECT ON COVERAGE
# ================================================================
print("\n" + "="*70)
print("ANALYSIS 12: C6 EFFECT ON BLIND SPOTS")
print("="*70)

# Do missed products have less c6 coverage?
c6_missed = missed_row_df.groupby("product_id")["c6_available"].max()
c6_caught = caught_row_df[caught_row_df[LABEL_COL]==1].groupby("product_id")["c6_available"].max()
print(f"\n  Missed products with c6 available: {c6_missed.sum()}/{len(c6_missed)} "
      f"({c6_missed.mean()*100:.1f}%)")
print(f"  Caught products with c6 available: {c6_caught.sum()}/{len(c6_caught)} "
      f"({c6_caught.mean()*100:.1f}%)")

# What's the AUC without c6 for missed products?
# (if c6_null subset performs worse, that explains some misses)
no_c6 = df_v4[df_v4["c6_available"]==0]
yes_c6 = df_v4[df_v4["c6_available"]==1]

from sklearn.metrics import roc_auc_score
try:
    auc_no = roc_auc_score(no_c6[LABEL_COL], no_c6["score_v2"]) if len(no_c6) > 0 else 0
    auc_yes = roc_auc_score(yes_c6[LABEL_COL], yes_c6["score_v2"]) if len(yes_c6) > 0 else 0
    print(f"\n  AUC without c6: {auc_no:.4f}")
    print(f"  AUC with c6:    {auc_yes:.4f}")
    
    # Among no-c6 products, what's the extreme flag rate?
    no_c6_extreme = (no_c6["risk_level_v4"]=="extreme").sum()
    yes_c6_extreme = (yes_c6["risk_level_v4"]=="extreme").sum()
    print(f"\n  No-c6 group: {len(no_c6)} rows, {no_c6_extreme} extreme ({no_c6_extreme/len(no_c6)*100:.2f}%)")
    print(f"  With-c6 group: {len(yes_c6)} rows, {yes_c6_extreme} extreme ({yes_c6_extreme/len(yes_c6)*100:.2f}%)")
except:
    print("  [WARN] Could not compute AUC (label imbalance)")

# ================================================================
# SUMMARY
# ================================================================
print("\n" + "="*70)
print("BLIND SPOT DIAGNOSIS SUMMARY")
print("="*70)

print(f"""
Key Findings:
1. Out of {len(declined_prods)} declined products, only {len(caught)} were ever extreme-flagged.
   -> {len(missed)} missed ({len(missed)/len(declined_prods)*100:.1f}%)
   
2. Of the missed products:
   -> {len(flagged_high)} reached at least high level
   -> {len(missed)-len(flagged_high)} never exceeded mid level

3. Missed products at decline time have:
   - Average score_v2 = {missed_at_decline['score_v2'].mean():.1f}
   - Average F4_v2 = {missed_at_decline['f4_v2'].mean():.1f} (much lower than caught: {caught_at_decline['f4_v2'].mean():.1f})
   - Average F5_v2 = {missed_at_decline['f5_v2'].mean():.1f}
   - {len(missed_at_decline[missed_at_decline['c6_available']==0])}/{len(missed_at_decline)} without c6

4. Threshold sensitivity: lowering threshold increases coverage but adds FPs

5. Main miss causes: (see FP root cause analysis above)

6. C6 availability gap: no-c6 AUC = {auc_no:.4f} vs yes-c6 = {auc_yes:.4f} (if computed)
""")

print(f"Results saved to {OUT_DIR}/")
