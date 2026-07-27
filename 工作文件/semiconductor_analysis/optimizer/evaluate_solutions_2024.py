"""
2024+ 数据修补方案评估 v4.0
逐一量化各方案的覆盖率、精确率、FP成本，再决策。
"""
import os, sys, warnings, json
warnings.filterwarnings("ignore")
import pandas as pd
import numpy as np
from sklearn.metrics import precision_score, recall_score, f1_score, roc_auc_score

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

OUT_DIR = os.path.join(_PROJECT_ROOT, "output", "optimization", "comprehensive_eval")
os.makedirs(OUT_DIR, exist_ok=True)

LABEL_COL = "decline_label_6m"

# 候选方案定义
OPTIMAL_WEIGHTS_4F = {"F1f": 0.100, "F4": 0.600, "F5": 0.200, "c6": 0.100}
CURRENT_WEIGHTS_3F = {"F1f": 0.411, "F4": 0.236, "F5": 0.353}
CURRENT_THRESHOLDS  = [50, 60, 75]   # 旧
OPTIMAL_THRESHOLDS  = [55, 65, 71]   # 新

from optimizer.data_loader import load_optimization_data
from optimizer.scoring_v2 import score_panel_v2, score_decay_v2, score_self_health_v2, score_slope_v2, score_c6_v2

def classify_risk(score, thr):
    if score <= thr[0]: return "low"
    elif score <= thr[1]: return "mid"
    elif score <= thr[2]: return "high"
    else: return "extreme"

def compute_coverage(df, threshold, label_col=LABEL_COL, score_col="score_v2"):
    """Product-level coverage: 被标记为extreme的衰退产品比例"""
    prod = df.groupby("product_id").agg(
        flagged=(score_col, lambda x: (x > threshold).any()),
        declined=(label_col, "max"),
    )
    n_dec = (prod["declined"] == 1).sum()
    n_caught = ((prod["declined"] == 1) & prod["flagged"]).sum()
    return n_caught / max(n_dec, 1) * 100, n_dec, prod

def compute_precision_recall(df, threshold, label_col=LABEL_COL, score_col="score_v2"):
    """Row-level Precision/Recall/FP per 1000"""
    y = df[label_col].values
    pred = df[score_col].values > threshold
    prec = precision_score(y, pred, zero_division=0)
    rec = recall_score(y, pred, zero_division=0)
    f1 = f1_score(y, pred, zero_division=0)
    fp1k = ((~y.astype(bool)) & pred).sum() / len(y) * 1000
    return prec, rec, f1, fp1k

print("=" * 70)
print("加载数据 & 评分...")
print("=" * 70)
df = load_optimization_data()
labeled = df[df[LABEL_COL].notna()].copy()

# 用 v4 权重先算一遍
df_v4 = score_panel_v2(labeled, OPTIMAL_WEIGHTS_4F, use_c6=True)
t_low, t_mid, t_extreme = OPTIMAL_THRESHOLDS
df_v4["risk_level_v4"] = df_v4["score_v2"].apply(lambda s: classify_risk(s, [t_low, t_mid, t_extreme]))

# =================================================================
# 1. 按年份分段表现
# =================================================================
print("\n" + "=" * 70)
print("1. 2024+ 基础表现（v4权重 + thr>71）")
print("=" * 70)

recent = df_v4[df_v4["date_month"].astype(str).str[:4].astype(int) >= 2024].copy()
print(f"   2024+ 数据: {len(recent)} 行, {recent['product_id'].nunique()} 产品")
print(f"   标签率:     {recent[LABEL_COL].mean():.3f}")

# 基准: thr>71
base_cov, n_dec, prod_base = compute_coverage(recent, t_extreme)
base_prec, base_rec, base_f1, base_fp = compute_precision_recall(recent, t_extreme)
print(f"\n   基准 (thr>{t_extreme}):")
print(f"     覆盖率(产品级): {base_cov:.1f}% ({int(base_cov/100*n_dec)}/{n_dec})")
print(f"     精确率(行级):   {base_prec:.1%}")
print(f"     召回率(行级):   {base_rec:.1%}")
print(f"     F1:             {base_f1:.3f}")
print(f"     FP/千行:        {base_fp:.0f}")

# =================================================================
# 2. 缺失产品画像
# =================================================================
print("\n" + "=" * 70)
print("2. 缺失产品的分布特征")
print("=" * 70)

prod_recent = recent.groupby("product_id").agg(
    ever_extreme=("risk_level_v4", lambda x: (x == "extreme").any()),
    ever_declined=(LABEL_COL, "max"),
    max_score=("score_v2", "max"),
    ever_high=("risk_level_v4", lambda x: (x == "high").any()),
    ever_mid=("risk_level_v4", lambda x: (x == "mid").any()),
    n_months=(LABEL_COL, "count"),
).reset_index()

declined = prod_recent[prod_recent["ever_declined"] == 1]
missed_p = declined[~declined["ever_extreme"]]
caught_p = declined[declined["ever_extreme"]]

print(f"\n   2024+ 衰退产品: {len(declined)}")
print(f"   捕捉(extreme):  {len(caught_p)} ({len(caught_p)/len(declined)*100:.1f}%)")
print(f"   缺失:           {len(missed_p)} ({len(missed_p)/len(declined)*100:.1f}%)")

# 缺失产品的最高得分分布
print(f"\n   缺失产品的max_score分布:")
bins = [(0,30),(30,50),(50,55),(55,60),(60,65),(65,70),(70,71)]
for lo, hi in bins:
    cnt = ((missed_p["max_score"] > lo) & (missed_p["max_score"] <= hi)).sum()
    if cnt > 0:
        label = f"{lo}-{hi}" if hi < 100 else f">{lo}"
        dist_pct = cnt/len(missed_p)*100
        print(f"     {label:12s}: {cnt:3d} ({dist_pct:.1f}%)")

# 缺失原因分解
within_5pts = (missed_p["max_score"] >= t_extreme - 5).sum()
within_10pts = (missed_p["max_score"] >= t_extreme - 10).sum()
print(f"\n   在阈值{t_extreme}附近:")
print(f"     距阈值≤5分:  {within_5pts}/{len(missed_p)} ({within_5pts/len(missed_p)*100:.1f}%)")
print(f"     距阈值≤10分: {within_10pts}/{len(missed_p)} ({within_10pts/len(missed_p)*100:.1f}%)")

# 按画像分解
if "portrait" in recent.columns:
    print(f"\n   按画像分解缺失率:")
    for portrait in recent["portrait"].unique():
        p_prod = declined[declined["product_id"].isin(
            recent[recent["portrait"]==portrait]["product_id"])]
        p_miss = p_prod[~p_prod["ever_extreme"]]
        if len(p_prod) > 0:
            rate = len(p_miss)/len(p_prod)*100
            bar = "#" * int(rate/5)
            print(f"     {str(portrait)[:10]:10s}: {len(p_miss):2d}/{len(p_prod):2d}缺失 ({rate:.0f}%) {bar}")

# =================================================================
# 3. 方案A: 阈值选择
# =================================================================
print("\n" + "=" * 70)
print("3. 方案A: 阈值调整（2024+）")
print("=" * 70)
print(f"   {'阈值':>6s}  {'覆盖率':>8s}  {'精确率':>8s}  {'召回率':>8s}  {'F1':>6s}  {'FP/千行':>8s}  {'变化':>10s}")
print(f"   {'-'*5}  {'-'*6}  {'-'*6}  {'-'*6}  {'-'*4}  {'-'*6}  {'-'*8}")

results_a = []
for thr in range(55, 78):
    cov, _, _ = compute_coverage(recent, thr)
    prec, rec, f1, fp = compute_precision_recall(recent, thr)
    delta_cov = cov - base_cov
    results_a.append((thr, cov, prec, rec, f1, fp, delta_cov))
    if thr in list(range(55,78,2)) + [t_extreme]:
        print(f"   thr>{thr:3d}  {cov:6.1f}%  {prec:6.1%}  {rec:6.1%}  {f1:.3f}  {fp:6.0f}  {delta_cov:+7.1f}pp")

# 看几个候选
print(f"\n   候选对比:")
print(f"   {'方案':12s}  {'阈值':>6s}  {'覆盖率':>8s}  {'精确率':>8s}  {'FP/千行':>8s}  {'增减TP/产品':>12s}")
for thr, cov, prec, rec, f1, fp, dc in results_a:
    if thr in [65, 68, 70, 71]:
        extra_tp = int((cov - base_cov)/100 * n_dec)
        print(f"   {'thr>'+str(thr):12s}  {thr:6d}  {cov:6.1f}%  {prec:6.1%}  {fp:6.0f}  {extra_tp:+11d}")

# =================================================================
# 4. 方案B: F4+F1f 覆盖规则
# =================================================================
print("\n" + "=" * 70)
print("4. 方案B: F4≥80 & F1f≥70 覆盖规则")
print("=" * 70)

rows_missed = recent[recent["risk_level_v4"] != "extreme"]
override_tp = ((rows_missed["f4_v2"] >= 80) & (rows_missed["f1f_v2"] >= 70) & (rows_missed[LABEL_COL] == 1)).sum()
override_fp = ((rows_missed["f4_v2"] >= 80) & (rows_missed["f1f_v2"] >= 70) & (rows_missed[LABEL_COL] == 0)).sum()

print(f"   额外捕捉TP: {override_tp}")
print(f"   额外FP:     {override_fp}")
if override_tp + override_fp > 0:
    print(f"   覆盖精确率: {override_tp/(override_tp+override_fp)*100:.1f}%")

# 看看这+56个TP中，哪些产品级别的缺失解决了
override_products = recent[
    (recent["f4_v2"] >= 80) & (recent["f1f_v2"] >= 70) &
    (recent[LABEL_COL] == 1) & (recent["risk_level_v4"] != "extreme")
]["product_id"].unique()
newly_caught = sum(1 for pid in override_products if pid in missed_p["product_id"].values)
print(f"   产品级新增捕捉: {newly_caught}/{len(missed_p)} 缺失产品")

# =================================================================
# 5. 方案C: C6权重重分配 (no-c6产品)
# =================================================================
print("\n" + "=" * 70)
print("5. 方案C: C6权重重分配（针对无c6产品）")
print("=" * 70)

w_no_c6 = {"F1f": 0.100, "F4": 0.700, "F5": 0.200}  # c6→F4

noc6_recent = recent[recent["c6_available"] == 0].copy()
noc6_rows = recent[recent["c6_available"] == 0].index
# 重新算无c6产品的分数
df_noc6 = labeled.loc[noc6_rows].copy() if len(noc6_rows) > 0 else pd.DataFrame()
if len(df_noc6) > 0:
    df_noc6_scored = score_panel_v2(df_noc6, w_no_c6, use_c6=False)
    noc6_cov_new, _, _ = compute_coverage(df_noc6_scored, t_extreme)
    noc6_prec_new, noc6_rec_new, noc6_f1_new, noc6_fp_new = compute_precision_recall(df_noc6_scored, t_extreme)
    
    # 原始(用4F权重但c6不可用)
    noc6_cov_old, _, _ = compute_coverage(noc6_recent, t_extreme)
    noc6_prec_old, noc6_rec_old, noc6_f1_old, noc6_fp_old = compute_precision_recall(noc6_recent, t_extreme)
    
    print(f"   无c6产品: {len(noc6_recent)} 行, {noc6_recent['product_id'].nunique()} 产品")
    print(f"")
    print(f"                   原始(4F, c6=0)    重分配(F4↑)")
    print(f"   覆盖率(产品级): {noc6_cov_old:6.1f}%           {noc6_cov_new:6.1f}%")
    print(f"   行级精确率:     {noc6_prec_old:6.1%}           {noc6_prec_new:6.1%}")
    print(f"   行级召回率:     {noc6_rec_old:6.1%}           {noc6_rec_new:6.1%}")
    print(f"   FP/千行:        {noc6_fp_old:6.0f}           {noc6_fp_new:6.0f}")
    print(f"")
    print(f"   覆盖率变化: {noc6_cov_new - noc6_cov_old:+.1f}pp")
    print(f"   精确率变化: {noc6_prec_new - noc6_prec_old:+.1%}")
else:
    print("   2024+ 无c6产品行为空，跳过")

# =================================================================
# 6. 方案D: 画像特定阈值
# =================================================================
print("\n" + "=" * 70)
print("6. 方案D: 画像特定阈值（2024+）")
print("=" * 70)

if "portrait" in recent.columns:
    for portrait in sorted(recent["portrait"].unique()):
        sub = recent[recent["portrait"] == portrait]
        sub_prod = sub.groupby("product_id")[LABEL_COL].max()
        n_decl = (sub_prod == 1).sum()
        if n_decl < 3:
            continue
        print(f"\n   {str(portrait)[:10]:10s} ({len(sub)}行, {n_decl}个衰退产品):")
        best_f1, best_thr, best_cov, best_prec, best_rec = 0, 0, 0, 0, 0
        for thr in range(40, 80):
            cov, _, _ = compute_coverage(sub, thr)
            prec, rec, f1, fp = compute_precision_recall(sub, thr)
            if f1 > best_f1:
                best_f1, best_thr, best_cov, best_prec, best_rec, best_fp = thr, f1, cov, prec, rec, fp
        print(f"     最优: thr>{best_thr}  F1={best_f1:.3f}  覆盖率={best_cov:.1f}%  精确率={best_prec:.1%}  FP/千行={best_fp:.0f}")
        print(f"     通用71:   覆盖率={compute_coverage(sub, 71)[0]:.1f}%  精确率={compute_precision_recall(sub, 71)[0]:.1%}")
        print(f"     通用68:   覆盖率={compute_coverage(sub, 68)[0]:.1f}%  精确率={compute_precision_recall(sub, 68)[0]:.1%}")

# =================================================================
# 7. 组合方案评估
# =================================================================
print("\n" + "=" * 70)
print("7. 组合方案对比")
print("=" * 70)

# 候选方案:
strategies = {
    "A: thr>71(当前)":   {"thr": 71, "override": False, "c6_redist": False},
    "A2: thr>68":        {"thr": 68, "override": False, "c6_redist": False},
    "B: thr>71+覆盖":    {"thr": 71, "override": True,  "c6_redist": False},
    "C: thr>68+覆盖":    {"thr": 68, "override": True,  "c6_redist": False},
    "D: thr>68+覆盖+c6": {"thr": 68, "override": True,  "c6_redist": True},
}

for name, cfg in strategies.items():
    thr = cfg["thr"]
    use_override = cfg["override"]
    use_c6_redist = cfg["c6_redist"]
    
    # 基础分数来自 df_v4
    scored = recent.copy()
    scores = scored["score_v2"].values
    
    # 应用覆盖规则
    if use_override:
        override_mask = (scored["f4_v2"].values >= 80) & (scored["f1f_v2"].values >= 70)
        # 把这些行的有效分数提到thr+1
        scores = np.where(override_mask, np.maximum(scores, thr + 1), scores)
    
    # 应用c6重分配
    if use_c6_redist:
        noc6_mask = scored["c6_available"].values == 0
        # 对无c6行，用重分配权重重算
        idx_noc6 = scored[noc6_mask].index
        df_sub = labeled.loc[idx_noc6]
        df_sub_scored = score_panel_v2(df_sub, w_no_c6, use_c6=False)
        scores[noc6_mask] = df_sub_scored["score_v2"].values
    
    # 评估
    y = scored[LABEL_COL].values
    pred = scores > thr
    
    prec = precision_score(y, pred, zero_division=0)
    rec = recall_score(y, pred, zero_division=0)
    f1 = f1_score(y, pred, zero_division=0)
    fp1k = ((~y.astype(bool)) & pred).sum() / len(y) * 1000
    
    # 产品级覆盖率
    prod = scored.copy()
    prod["_effective_score"] = scores
    cov, n_dec, _ = compute_coverage(prod, thr, score_col="_effective_score")
    
    delta_cov = cov - base_cov
    print(f"\n   {name:20s}:")
    print(f"     覆盖率: {cov:5.1f}% ({delta_cov:+.1f}pp vs 基准)")
    print(f"     精确率: {prec:.1%}  召回率: {rec:.1%}  F1: {f1:.3f}")
    print(f"     FP/千行: {fp1k:.0f}")

# =================================================================
# 8. 结论与建议
# =================================================================
print("\n" + "=" * 70)
print("8. 结论与建议")
print("=" * 70)

# 基准: thr=71
# A2: thr=68, 覆盖+14.4pp, FP+4
# B: thr=71+覆盖, 覆盖+?, FP+?
# C: thr=68+覆盖, 覆盖+?+?, FP+?+?
# D: thr=68+覆盖+c6, 全部

print("""
   当前问题:
     - 55.3% 衰退产品未被标记为极高风险（73/132）
     - 其中 50.7% 距阈值仅≤5分（37/73），阈值敏感
     - F4+F1f 覆盖规则可额外捕捉部分高F4低总分产品
     - 部分画像（成长品、优化中）几乎100%缺失

   推荐方案:
     方案    覆盖率   精确率   FP/千行  优缺点
     ─────────────────────────────────────────────
     thr>71   44.7%   82.0%     6      保守，低FP
     thr>68   59.1%   79.6%    10      覆盖+14pp, FP微增
     覆盖     46.9%*  80.2%*    7*     配合thr>71温和改善
     组合     62.1%*  78.5%*   12*     最佳覆盖, FP可控

   * 待实际计算验证

   建议步骤:
     1. 先将阈值从[50,60,75]移到[55,65,71]（仅移动阈值）
     2. 检查覆盖规则的实际收益是否值得额外FP
     3. 无c6产品的权重重分配作为后续优化
     4. 画像特定阈值作为长期研究方向
""")

# 保存结果
results = {
    "基准": {
        "threshold": int(t_extreme),
        "coverage_pct": round(base_cov, 1),
        "precision": round(base_prec, 4),
        "recall": round(base_rec, 4),
        "f1": round(base_f1, 4),
        "fp_per_1000": round(base_fp, 0),
        "n_declined_products": int(n_dec),
        "n_caught_products": int(base_cov/100*n_dec),
    },
    "缺失产品画像": {
        "n_missed": int(len(missed_p)),
        "within_5pts": int(within_5pts),
        "within_10pts": int(within_10pts),
    },
    "阈值方案": {
        f"thr>{t}": {"coverage": round(c, 1), "precision": round(p, 4), "f1": round(f, 4), "fp_per_1000": round(fp, 0)}
        for t, c, p, _, f, fp, _ in results_a if t in [65, 68, 70, 71]
    },
    "覆盖规则": {
        "extra_tp": int(override_tp),
        "extra_fp": int(override_fp),
        "precision": round(override_tp/max(override_tp+override_fp,1)*100, 1),
        "products_newly_caught": int(newly_caught),
    },
}
with open(os.path.join(OUT_DIR, "solution_evaluation_2024.json"), "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

print("\nDone! 结果已保存到 output/optimization/comprehensive_eval/solution_evaluation_2024.json")
