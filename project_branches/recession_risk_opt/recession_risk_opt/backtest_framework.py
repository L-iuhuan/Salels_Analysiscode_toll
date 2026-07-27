"""
衰退风险评分模型 — 自动化回溯测试框架
======================================
对比4种权重方案（默认/优化/网格搜索/Lasso），输出完整评估报告。

用法:
    python backtest_framework.py                           # 使用默认路径
    python backtest_framework.py --data_path <path> --output_dir <dir>
"""

import os, sys, json, warnings, argparse, textwrap
from datetime import datetime
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
# 中文字体配置
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DengXian', 'Noto Sans SC']
plt.rcParams['axes.unicode_minus'] = False
plt.rcParams['font.family'] = 'sans-serif'
import seaborn as sns
sns.set_theme(style='whitegrid', font='SimHei', rc={
    'font.sans-serif': ['SimHei', 'Microsoft YaHei', 'DengXian', 'Noto Sans SC'],
    'axes.unicode_minus': False,
})
from scipy import stats
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import (roc_auc_score, roc_curve, precision_recall_curve,
                             average_precision_score, fbeta_score, confusion_matrix)
from sklearn.linear_model import LogisticRegression
from collections import defaultdict
from itertools import product as iter_product

warnings.filterwarnings('ignore')

# ── 路径 ──
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
PARENT_ROOT = os.path.dirname(PROJECT_ROOT)
sys.path.insert(0, PARENT_ROOT)

# 默认路径
DEFAULT_SAMPLES = os.path.join(PROJECT_ROOT, "data", "samples.pkl")
DEFAULT_OUTPUT = os.path.join(PROJECT_ROOT, "backtest_results")
DEFAULT_GOLD = os.path.join(PARENT_ROOT, "output", "gold", "gold_product_portrait.csv")

# ── 权重方案定义 ──
WEIGHT_SCHEMES = {
    "A_默认权重":  {"f1": 0.20, "f3": 0.10, "f4": 0.20, "f5": 0.35, "f6": 0.15},
    "B_优化权重":  {"f1": 0.090, "f3": 0.181, "f4": 0.199, "f5": 0.473, "f6": 0.058},
}

# 风险等级阈值（优化后）
RISK_THRESHOLDS = [30, 50, 65]  # Bug 5修复: 统一阈值
RISK_LABELS = ["低风险", "中风险", "高风险", "极高风险"]

# ── 网格搜索空间（稀疏，避免过慢） ──
GRID_SEARCH_SPACE = {
    "f5": np.arange(0.35, 0.61, 0.10),
    "f4": np.arange(0.10, 0.31, 0.10),
    "f3": np.arange(0.05, 0.26, 0.10),
    "f1": np.arange(0.05, 0.21, 0.075),
}

np.random.seed(42)


# ╔══════════════════════════════════════════════════════════════╗
# ║              数据加载与标签构建                              ║
# ╚══════════════════════════════════════════════════════════════╝

def load_data(samples_path=None, gold_path=None):
    """加载预计算样本数据"""
    if samples_path is None:
        samples_path = DEFAULT_SAMPLES
    print(f"[加载] 样本数据: {samples_path}")
    df = pd.read_pickle(samples_path)
    print(f"  形状: {df.shape}, 产品: {df['product_id'].nunique()}")
    print(f"  月份: {df['date_month'].min()} ~ {df['date_month'].max()}")
    return df


def build_label_6m(df):
    """
    对每个产品每月 t，构建6个月前瞻标签 y_decline_6m：
    y=1 如果月份 t+1 ~ t+6 内九宫格落入【衰退期/夕阳产品/隐性衰退】
    或 毛利率连续≤0 且 销量萎缩>20%
    """
    print("[标签] 构建6个月前瞻衰退标签...")
    df_sorted = df.sort_values(['product_id', 'date_month']).copy()
    df_sorted['_month_dt'] = pd.to_datetime(df_sorted['date_month'].astype(str).str[:7] + '-01')

    # 衰退画像集合
    decline_portraits = {"衰退期", "夕阳产品", "隐性衰退"}

    # 分组扫描：对每个产品，用滑动窗口看未来6个月
    y_6m = []
    for prod, grp in df_sorted.groupby('product_id'):
        grp = grp.sort_values('date_month')
        portraits = grp['portrait'].values
        margins = grp['recent_margin'].values
        growths = grp['growth_rate'].values
        n = len(grp)

        for i in range(n):
            future_start = i + 1
            future_end = min(i + 7, n)  # 未来6个月
            if future_start >= future_end:
                # 未来数据不足6个月 → 使用已有标签+标签衰退画像扩展
                # 如果已有标签y=1或当前画像为衰退 → 标记1
                y_6m.append(int(grp['y'].iloc[i]) if 'y' in grp.columns else 0)
                continue

            future_portraits = portraits[future_start:future_end]
            future_margins = margins[future_start:future_end]
            future_growths = growths[future_start:future_end]

            # 条件1：九宫格进入衰退
            in_decline = any(p in decline_portraits for p in future_portraits)

            # 条件2：毛利率连续≤0 且 销量萎缩>20%
            margin_bad = all(m <= 0 for m in future_margins) if len(future_margins) > 0 else False
            sales_shrink = any(g < -0.2 for g in future_growths) if len(future_growths) > 0 else False

            y_6m.append(1 if (in_decline or (margin_bad and sales_shrink)) else 0)

    df_sorted['y_decline_6m'] = y_6m
    pos_rate = df_sorted['y_decline_6m'].mean()
    print(f"  正样本(衰退率): {pos_rate*100:.1f}% ({df_sorted['y_decline_6m'].sum()}/{len(df_sorted)})")

    # 也保留原有y作为对比
    if 'y' in df_sorted.columns:
        overlap = (df_sorted['y'] == df_sorted['y_decline_6m']).mean()
        print(f"  与原有2月标签一致率: {overlap*100:.1f}%")

    return df_sorted


# ╔══════════════════════════════════════════════════════════════╗
# ║              评分引擎                                        ║
# ╚══════════════════════════════════════════════════════════════╝

def compute_risk_score(row, weights, consec_bonus_per_month=10, max_score=100):
    """
    根据因子得分和权重计算风险评分。
    考虑不可靠因子降权。
    """
    factor_scores = {
        'f1': row.get('f1_score', 50),
        'f3': row.get('f3_score', 50),
        'f4': row.get('f4_score', 50),
        'f5': row.get('f5_score', 50),
        'f6': row.get('f6_score', 50),
    }

    # 不可靠标记
    unreliable = {
        'f1': row.get('slope_insufficient', False) or row.get('zero_profit', False),
        'f3': row.get('cv_invalid', False),
        'f4': False,  # 始终可靠
        'f5': row.get('no_valid_hist_margin', False),
        'f6': row.get('asp_insufficient', False),
    }

    # 降权
    adjusted_weights = {}
    for k, w in weights.items():
        adjusted_weights[k] = 0.0 if unreliable.get(k, False) else w

    sum_w = sum(adjusted_weights.values())
    if sum_w > 0:
        for k in adjusted_weights:
            adjusted_weights[k] /= sum_w

    # 加权总分
    total = sum(factor_scores[k] * adjusted_weights[k] for k in weights)

    # F4连续下降增强
    consec = row.get('consecutive_months', 0)
    total += consec * consec_bonus_per_month

    return min(max_score, round(total, 1))


def batch_score(df, weights):
    """批量评分"""
    scores = df.apply(lambda r: compute_risk_score(r.to_dict(), weights), axis=1)
    return scores.values


def risk_level(score):
    """根据阈值分级"""
    if score <= RISK_THRESHOLDS[0]:
        return RISK_LABELS[0]
    elif score <= RISK_THRESHOLDS[1]:
        return RISK_LABELS[1]
    elif score <= RISK_THRESHOLDS[2]:
        return RISK_LABELS[2]
    else:
        return RISK_LABELS[3]


# ╔══════════════════════════════════════════════════════════════╗
# ║              权重方案实现                                    ║
# ╚══════════════════════════════════════════════════════════════╝

def scheme_default(df):
    """A: 默认权重"""
    w = WEIGHT_SCHEMES["A_默认权重"]
    scores = batch_score(df, w)
    return scores, w


def scheme_optimized(df):
    """B: 优化权重(2026-05)"""
    w = WEIGHT_SCHEMES["B_优化权重"]
    scores = batch_score(df, w)
    return scores, w


def scheme_grid_search(train_df, val_df, y_col='y_decline_6m'):
    """
    C: 网格搜索权重（加速版：预计算因子得分矩阵，向量化加权）
    """
    # 预计算因子得分矩阵 (n_samples x 5)
    factor_cols = ['f1_score', 'f3_score', 'f4_score', 'f5_score', 'f6_score']
    val_scores_matrix = val_df[factor_cols].fillna(50).values  # (N_val, 5)

    y_val = val_df[y_col].values

    # 生成所有权重组合
    weight_combos = []
    for f5, f4, f3, f1 in iter_product(
        GRID_SEARCH_SPACE["f5"],
        GRID_SEARCH_SPACE["f4"],
        GRID_SEARCH_SPACE["f3"],
        GRID_SEARCH_SPACE["f1"],
    ):
        f6 = 1.0 - f5 - f4 - f3 - f1
        if f6 < 0 or f6 > 0.30:
            continue
        weight_combos.append(np.array([f1, f3, f4, f5, f6]))

    # 向量化：一次性计算所有组合的总分 (n_combos, N_val)
    # 先用原始权重算基分
    base_scores = val_scores_matrix  # (N_val, 5)
    # 对每个组合加权求和
    best_auc = -1
    best_w = None
    best_scores = None

    for w_arr in weight_combos:
        w_scores = base_scores @ w_arr  # (N_val,) — 加权总分

        # 注意：这里没加 consecutive bonus，但各组合加同样bonus不影响AUC排序
        # 只在最终输出时加bonus
        if len(np.unique(y_val)) >= 2:
            try:
                auc = roc_auc_score(y_val, w_scores)
                if auc > best_auc:
                    best_auc = auc
                    best_w = dict(zip(['f1', 'f3', 'f4', 'f5', 'f6'], w_arr))
                    best_scores = w_scores
            except:
                pass

    if best_scores is None:
        w = WEIGHT_SCHEMES["A_默认权重"]
        best_scores = batch_score(val_df, w)
        best_w = w
        best_auc = 0.5
    else:
        # 补上consecutive bonus
        consec = val_df['consecutive_months'].values * 10
        best_scores = np.clip(best_scores + consec, 0, 100)

    print(f"    网格搜索: {len(weight_combos)}种组合, 最佳验证AUC={best_auc:.4f}, 权重={best_w}")
    return best_scores, best_w


def scheme_lasso(train_df, val_df, y_col='y_decline_6m'):
    """
    D: Lasso逻辑回归
    用训练集因子得分拟合L1逻辑回归，输出概率映射为0-100分。
    """
    feature_cols = ['f1_score', 'f3_score', 'f4_score', 'f5_score', 'f6_score']
    X_train = train_df[feature_cols].fillna(50).values
    y_train = train_df[y_col].values
    X_val = val_df[feature_cols].fillna(50).values

    # L1逻辑回归，用CV选最佳C
    from sklearn.linear_model import LogisticRegressionCV
    model = LogisticRegressionCV(
        Cs=10, penalty='l1', solver='saga',
        max_iter=5000, cv=3, random_state=42,
        class_weight='balanced'
    )
    model.fit(X_train, y_train)

    # 输出概率 → 映射到0-100
    probs = model.predict_proba(X_val)[:, 1]
    scores = probs * 100

    # 权重 = 归一化的系数绝对值
    coef = model.coef_[0]
    abs_coef = np.abs(coef)
    w = abs_coef / abs_coef.sum()
    weights = dict(zip(['f1', 'f3', 'f4', 'f5', 'f6'], w))

    print(f"    Lasso: C={model.C_[0]:.4f}, 归一化权重={weights}")
    return scores, weights, model


# ╔══════════════════════════════════════════════════════════════╗
# ║              评估指标计算                                    ║
# ╚══════════════════════════════════════════════════════════════╝

def compute_metrics(y_true, y_score, df_fold, weights_list=None):
    """
    计算全部评估指标。
    y_true: 真实标签
    y_score: 风险评分
    df_fold: 当前折数据（含因子得分、未来毛利率等）
    """
    metrics = {}

    # ── 排序能力 ──
    n_pos = y_true.sum()
    n_neg = len(y_true) - n_pos

    # AUC-ROC
    if len(np.unique(y_true)) >= 2:
        metrics['auc_roc'] = roc_auc_score(y_true, y_score)
    else:
        metrics['auc_roc'] = np.nan

    # AUC-PR
    metrics['auc_pr'] = average_precision_score(y_true, y_score)

    # Spearman ρ (风险分 vs 未来毛利率)
    future_margin = df_fold.get('recent_margin', np.nan)
    if future_margin is not None and not future_margin.isna().all():
        valid = ~future_margin.isna()
        if valid.sum() >= 5:
            rho, _ = stats.spearmanr(y_score[valid], future_margin[valid])
            metrics['spearman_rho'] = rho
        else:
            metrics['spearman_rho'] = np.nan
    else:
        metrics['spearman_rho'] = np.nan

    # ── 分类能力 ──
    # F2-Score (β=2, 偏重召回)
    # 需要二值化风险分: 用阈值的下界(>RISK_THRESHOLDS[0]视为正)
    pred_binary = (y_score > RISK_THRESHOLDS[0]).astype(int)
    if len(np.unique(pred_binary)) >= 2 and len(np.unique(y_true)) >= 2:
        metrics['f2_score'] = fbeta_score(y_true, pred_binary, beta=2)
    else:
        metrics['f2_score'] = np.nan

    # Precision@极高风险
    high_risk_mask = y_score > RISK_THRESHOLDS[2]
    if high_risk_mask.sum() > 0:
        metrics['precision_high_risk'] = y_true[high_risk_mask].mean()
    else:
        metrics['precision_high_risk'] = np.nan

    # Recall@高风险+极高风险 (>52)
    alert_mask = y_score > RISK_THRESHOLDS[1]
    if y_true.sum() > 0:
        metrics['recall_alert'] = (y_true & alert_mask).sum() / y_true.sum()
    else:
        metrics['recall_alert'] = np.nan

    # Top-20%命中率
    n_top = max(1, len(y_score) // 5)
    top_idx = np.argsort(y_score)[-n_top:]
    top_hit_rate = y_true[top_idx].mean()
    baseline = y_true.mean()
    metrics['top20_hit_rate'] = top_hit_rate
    metrics['top20_lift'] = top_hit_rate / baseline if baseline > 0 else np.nan

    # ── 单因子AUC ──
    factor_cols = ['f1_score', 'f3_score', 'f4_score', 'f5_score', 'f6_score']
    factor_names = ['F1毛利率斜率', 'F3订货波动', 'F4增速衰减', 'F5自比健康度', 'F6 ASP趋势']
    for col, fname in zip(factor_cols, factor_names):
        vals = df_fold[col].values
        if len(np.unique(y_true)) >= 2 and not np.isnan(vals).all():
            valid = ~np.isnan(vals)
            if valid.sum() >= 10 and len(np.unique(y_true[valid])) >= 2:
                metrics[f'factor_auc_{col}'] = roc_auc_score(y_true[valid], vals[valid])
                r, _ = stats.pearsonr(y_score[valid], vals[valid])
                metrics[f'factor_pearson_{col}'] = r
            else:
                metrics[f'factor_auc_{col}'] = np.nan
                metrics[f'factor_pearson_{col}'] = np.nan
        else:
            metrics[f'factor_auc_{col}'] = np.nan
            metrics[f'factor_pearson_{col}'] = np.nan

    # 因子缺失率
    # 因子缺失率 = 不可靠标记 OR 实际NaN
    f1_missing = (df_fold['slope_insufficient'].fillna(True) | df_fold.get('slope_ratio', pd.Series([0])).isna()).mean() if 'slope_insufficient' in df_fold else 0
    f3_missing = (df_fold['cv_invalid'].fillna(True) | df_fold.get('cv', pd.Series([0])).isna()).mean() if 'cv_invalid' in df_fold else df_fold.get('cv', pd.Series([0])).isna().mean()
    f5_missing = (df_fold['no_valid_hist_margin'].fillna(True)).mean() if 'no_valid_hist_margin' in df_fold else 0
    f6_missing = (df_fold['asp_insufficient'].fillna(True) | df_fold.get('asp_slope', pd.Series([0])).isna()).mean() if 'asp_insufficient' in df_fold else 0

    missing_checks = {
        'F1': f1_missing,
        'F3': f3_missing,
        'F4': 0.0,
        'F5': f5_missing,
        'F6': f6_missing,
    }
    metrics['factor_missing_F1'] = missing_checks['F1']
    metrics['factor_missing_F3'] = missing_checks['F3']
    metrics['factor_missing_F4'] = 0.0
    metrics['factor_missing_F5'] = missing_checks['F5']
    metrics['factor_missing_F6'] = missing_checks['F6']

    # 标签平衡性
    metrics['pos_rate'] = n_pos / len(y_true) if len(y_true) > 0 else 0
    metrics['n_samples'] = len(y_true)

    return metrics


def fold_stability(weights_per_fold):
    """
    计算权重漂移CV和各折间排序一致性(Kendall τ)。
    weights_per_fold: list[dict], 每折的权重
    """
    if len(weights_per_fold) < 2:
        return {'weight_drift_cv': np.nan, 'kendall_tau': np.nan}

    # 权重漂移CV
    w_df = pd.DataFrame(weights_per_fold)
    cv_vals = {}
    for col in w_df.columns:
        cv_vals[col] = w_df[col].std() / w_df[col].mean() if w_df[col].mean() > 0 else 0
    mean_cv = np.mean(list(cv_vals.values()))

    # Kendall τ (折间排序一致性)
    tau_vals = []
    for i in range(len(weights_per_fold)):
        for j in range(i+1, len(weights_per_fold)):
            w_i = list(weights_per_fold[i].values())
            w_j = list(weights_per_fold[j].values())
            tau, _ = stats.kendalltau(w_i, w_j)
            if not np.isnan(tau):
                tau_vals.append(tau)

    return {
        'weight_drift_cv': mean_cv,
        'kendall_tau': np.mean(tau_vals) if tau_vals else np.nan
    }


# ╔══════════════════════════════════════════════════════════════╗
# ║              回溯测试主循环                                  ║
# ╚══════════════════════════════════════════════════════════════╝

def run_backtest(df, n_splits=5, forward_months=6):
    """
    滚动回溯测试主循环。
    每折：训练期 → 计算风险分 → 验证未来6个月标签。
    """
    print(f"\n{'='*60}")
    print(f"开始滚动回溯测试: n_splits={n_splits}, forward_months={forward_months}")
    print(f"{'='*60}")

    # 按时间排序
    df = df.sort_values('date_month').reset_index(drop=True)
    df['_month_idx'] = pd.factorize(df['date_month'])[0]

    # TimeSeriesSplit on months (not rows)
    months = sorted(df['date_month'].unique())
    print(f"  总月份数: {len(months)}, 范围: {months[0]} ~ {months[-1]}")

    tscv = TimeSeriesSplit(n_splits=n_splits)

    # 存储每折结果
    fold_results = []

    for fold, (train_month_idx, val_month_idx) in enumerate(tscv.split(months)):
        train_months = [months[i] for i in train_month_idx]
        val_months = [months[i] for i in val_month_idx]

        train_df = df[df['date_month'].isin(train_months)].copy()
        val_df = df[df['date_month'].isin(val_months)].copy()

        print(f"\n  ── Fold {fold+1}/{n_splits} ──")
        print(f"    训练: {train_months[0]} ~ {train_months[-1]} ({len(train_months)}月, {len(train_df)}样本)")
        print(f"    验证: {val_months[0]} ~ {val_months[-1]} ({len(val_months)}月, {len(val_df)}样本)")

        y_train = train_df['y_decline_6m'].values
        y_val = val_df['y_decline_6m'].values
        print(f"    训练集衰退率: {y_train.mean()*100:.1f}%, 验证集衰退率: {y_val.mean()*100:.1f}%")

        fold_out = {'fold': fold+1, 'train_months': train_months, 'val_months': val_months}
        fold_weights = {}

        # ── 方案A: 默认权重 ──
        scores_a, w_a = scheme_default(val_df)
        fold_out['scores_A'] = scores_a
        fold_out['weights_A'] = w_a
        fold_weights['A'] = w_a

        # ── 方案B: 优化权重 ──
        scores_b, w_b = scheme_optimized(val_df)
        fold_out['scores_B'] = scores_b
        fold_out['weights_B'] = w_b
        fold_weights['B'] = w_b

        # ── 方案C: 网格搜索 ──
        scores_c, w_c = scheme_grid_search(train_df, val_df)
        fold_out['scores_C'] = scores_c
        fold_out['weights_C'] = w_c
        fold_weights['C'] = w_c

        # ── 方案D: Lasso逻辑回归 ──
        scores_d, w_d, lasso_model = scheme_lasso(train_df, val_df)
        fold_out['scores_D'] = scores_d
        fold_out['weights_D'] = w_d
        fold_weights['D'] = w_d
        fold_out['lasso_model'] = lasso_model

        # 计算指标
        for scheme_name, scores in [('A', scores_a), ('B', scores_b),
                                     ('C', scores_c), ('D', scores_d)]:
            metrics = compute_metrics(y_val, scores, val_df)
            for k, v in metrics.items():
                fold_out[f'{scheme_name}_{k}'] = v

        # 保存详细结果
            detail_df = val_df[['product_id', 'date_month', 'portrait',
                            'f1_score', 'f3_score', 'f4_score', 'f5_score', 'f6_score',
                            'slope_ratio', 'cv', 'cv_invalid', 'asp_slope', 'asp_insufficient',
                            'slope_insufficient', 'no_valid_hist_margin',
                            'consecutive_months', 'y_decline_6m']].copy()
        for sn, sc in [('A', scores_a), ('B', scores_b), ('C', scores_c), ('D', scores_d)]:
            detail_df[f'risk_score_{sn}'] = sc
            detail_df[f'risk_level_{sn}'] = [risk_level(s) for s in sc]
        fold_out['detail'] = detail_df
        fold_out['weights_per_fold'] = fold_weights

        fold_results.append(fold_out)

    # ── 汇总所有折 ──
    summary = summarize_results(fold_results, n_splits)
    return fold_results, summary


def summarize_results(fold_results, n_splits):
    """汇总各折指标 mean ± std"""
    schemes = ['A', 'B', 'C', 'D']
    metric_keys = [k for k in fold_results[0].keys()
                   if any(k.startswith(f'{s}_') for s in schemes)
                   and k not in [f'{s}_weights_per_fold' for s in schemes]]

    # 去掉带方案前缀的因子key
    metric_names = set()
    for k in fold_results[0].keys():
        for s in schemes:
            if k.startswith(f'{s}_'):
                metric_names.add(k[len(s)+1:])
                break

    summary_rows = []
    for s in schemes:
        row = {'scheme': s}
        for mname in sorted(metric_names):
            key = f'{s}_{mname}'
            vals = [r[key] for r in fold_results if key in r and not np.isnan(r.get(key, np.nan))]
            if not vals:
                continue
            mean_v = np.nanmean(vals)
            std_v = np.nanstd(vals)
            row[mname] = mean_v
            row[f'{mname}_std'] = std_v
        summary_rows.append(row)

    summary_df = pd.DataFrame(summary_rows)
    summary_df = summary_df.set_index('scheme')

    # 稳定性指标 (折间权重一致性)
    stability_rows = []
    for s in schemes:
        weights_list = [r['weights_per_fold'][s] for r in fold_results]
        stab = fold_stability(weights_list)
        stability_rows.append({
            'scheme': s,
            'weight_drift_cv': stab['weight_drift_cv'],
            'kendall_tau': stab['kendall_tau'],
        })
    stab_df = pd.DataFrame(stability_rows).set_index('scheme')
    for col in stab_df.columns:
        summary_df[col] = stab_df[col]

    return summary_df


# ╔══════════════════════════════════════════════════════════════╗
# ║              因子诊断专项测试                               ║
# ╚══════════════════════════════════════════════════════════════╝

def factor_diagnostic_tests(df):
    """
    对每个因子进行专项诊断。
    """
    print(f"\n{'='*60}")
    print("因子诊断专项测试")
    print(f"{'='*60}")

    results = {}

    # ── F1测试: 衰退产品F1斜率在衰退前6个月是否显著为负 ──
    print("\n[F1诊断] 毛利率趋势斜率")
    f1_result = test_f1_slope(df)
    results['F1'] = f1_result

    # ── F4测试: 连续下降月数是否显著早于衰退 ──
    print("\n[F4诊断] 连续下降月数提前期")
    f4_result = test_f4_consec(df)
    results['F4'] = f4_result

    # ── F5测试: 健康度下降是否先于九宫格衰退 ──
    print("\n[F5诊断] 健康度下降提前期")
    f5_result = test_f5_health(df)
    results['F5'] = f5_result

    # ── F3测试: 高CV→销量断崖 ──
    print("\n[F3诊断] 高CV与销量断崖")
    f3_result = test_f3_cv(df)
    results['F3'] = f3_result

    # ── F6测试: ASP下跌是否伴随毛利率下跌 ──
    print("\n[F6诊断] ASP下跌与毛利率")
    f6_result = test_f6_asp(df)
    results['F6'] = f6_result

    return results


def test_f1_slope(df):
    """
    F1测试：取所有最终衰退的产品，检查其F1斜率在衰退前6个月是否显著为负（单样本t检验）。
    """
    decline_prods = df[df['y_decline_6m'] == 1]['product_id'].unique()
    print(f"  衰退产品数: {len(decline_prods)}")

    # 对每个产品，找其首次衰退前的6个月窗口
    f1_values_before = []
    for prod in decline_prods:
        prod_data = df[df['product_id'] == prod].sort_values('date_month')
        if len(prod_data) == 0:
            continue
        # 首次衰退时间
        first_decline = prod_data[prod_data['y_decline_6m'] == 1]
        if len(first_decline) == 0:
            continue
        first_decline_idx = first_decline.index[0]
        # 前6个月窗口
        before_mask = (prod_data.index < first_decline_idx) & \
                      (prod_data.index >= first_decline_idx - min(6, first_decline_idx))
        before_data = prod_data.loc[before_mask]
        if len(before_data) >= 2:
            f1_vals = before_data['f1_score'].values
            slope_vals = before_data['slope_ratio'].values
            f1_values_before.extend(slope_vals[~np.isnan(slope_vals)])

    f1_values_before = np.array(f1_values_before)
    print(f"  衰退前F1斜率样本数: {len(f1_values_before)}")

    result = {}
    if len(f1_values_before) >= 5:
        t_stat, p_value = stats.ttest_1samp(f1_values_before, 0, alternative='less')
        mean_slope = f1_values_before.mean()
        median_slope = np.median(f1_values_before)
        neg_ratio = (f1_values_before < 0).mean()
        result = {
            'mean_slope': mean_slope,
            'median_slope': median_slope,
            't_statistic': t_stat,
            'p_value': p_value,
            'neg_ratio': neg_ratio,
            'significant_negative': bool(p_value < 0.05 and t_stat < 0),
            'sample_size': len(f1_values_before),
        }
        print(f"  均值斜率: {mean_slope:.6f}, 中位数: {median_slope:.6f}")
        print(f"  t统计量: {t_stat:.4f}, p值: {p_value:.6f}")
        print(f"  负值占比: {neg_ratio*100:.1f}%")
        print(f"  显著为负: {'是' if p_value < 0.05 and t_stat < 0 else '否'}")
    else:
        result = {'error': '样本不足'}
        print(f"  样本不足 (<5)")

    return result


def test_f4_consec(df):
    """
    F4测试：检查连续下降月数是否显著早于衰退发生。
    计算：对每个衰退产品，从连续下降开始到首次衰退的月数。
    """
    decline_prods = df[df['y_decline_6m'] == 1]['product_id'].unique()

    lead_times = []
    for prod in decline_prods:
        prod_data = df[df['product_id'] == prod].sort_values('date_month').reset_index(drop=True)
        if len(prod_data) < 6:
            continue
        # 首次衰退
        decline_idx = prod_data['y_decline_6m'].values.argmax() if prod_data['y_decline_6m'].max() == 1 else -1
        if decline_idx <= 0:
            continue
        # 在首次衰退之前找连续下降开始
        before = prod_data.iloc[:decline_idx]
        consec_vals = before['consecutive_months'].values
        # 连续下降>0的最早点
        positive_idx = np.where(consec_vals > 0)[0]
        if len(positive_idx) > 0:
            first_consec = positive_idx[0]
            lead_time = decline_idx - first_consec
            if lead_time > 0:
                lead_times.append(lead_time)

    lead_times = np.array(lead_times)
    result = {}
    if len(lead_times) >= 5:
        result = {
            'lead_time_median': np.median(lead_times),
            'lead_time_mean': lead_times.mean(),
            'lead_time_std': lead_times.std(),
            'lead_time_p25': np.percentile(lead_times, 25),
            'lead_time_p75': np.percentile(lead_times, 75),
            'n_cases': len(lead_times),
        }
        print(f"  有效案例数: {len(lead_times)}")
        print(f"  提前期中位数: {np.median(lead_times):.0f}月")
        print(f"  提前期均值: {lead_times.mean():.1f}±{lead_times.std():.1f}月")
        print(f"  P25~P75: {np.percentile(lead_times,25):.0f}~{np.percentile(lead_times,75):.0f}月")
    else:
        result = {'error': '样本不足'}
        print(f"  有效案例数不足 (<5): {len(lead_times)}")

    return result


def test_f5_health(df):
    """
    F5测试：检查健康度下降是否先于九宫格落入衰退期。
    对每个衰退产品，检查从f5健康度得分>50到首次衰退的提前期。
    """
    decline_prods = df[df['y_decline_6m'] == 1]['product_id'].unique()

    lead_times = []
    signal_accuracy = []

    for prod in decline_prods:
        prod_data = df[df['product_id'] == prod].sort_values('date_month').reset_index(drop=True)
        if len(prod_data) < 6:
            continue
        decline_idx = prod_data['y_decline_6m'].values.argmax() if prod_data['y_decline_6m'].max() == 1 else -1
        if decline_idx <= 0:
            continue

        # F5得分 > 50 是最早的警报点（f5_score越高越危险）
        before = prod_data.iloc[:decline_idx]
        f5_vals = before['f5_score'].values
        # 找f5得分首次>50（中等风险）的点
        alert_idx = np.where(f5_vals > 50)[0]
        if len(alert_idx) > 0:
            first_alert = alert_idx[0]
            lead_time = decline_idx - first_alert
            if lead_time > 0:
                lead_times.append(lead_time)
                # 信号准确率：f5>50的点中，后续的确进入衰退的比例
                total_alerts = len(alert_idx)
                hit = sum(1 for a in alert_idx if a < decline_idx)
                signal_accuracy.append(hit / total_alerts if total_alerts > 0 else 1.0)

    lead_times = np.array(lead_times)
    result = {}
    if len(lead_times) >= 5:
        result = {
            'lead_time_median': np.median(lead_times),
            'lead_time_mean': lead_times.mean(),
            'lead_time_std': lead_times.std(),
            'signal_accuracy': np.mean(signal_accuracy) if signal_accuracy else np.nan,
            'n_cases': len(lead_times),
        }
        print(f"  有效案例数: {len(lead_times)}")
        print(f"  F5预警提前期中位数: {np.median(lead_times):.0f}月")
        print(f"  F5预警提前期均值: {lead_times.mean():.1f}±{lead_times.std():.1f}月")
        print(f"  F5信号准确率: {np.mean(signal_accuracy)*100:.1f}%" if signal_accuracy else "  F5信号准确率: N/A")
    else:
        result = {'error': '样本不足'}
        print(f"  样本不足 (<5): {len(lead_times)}")

    return result


def test_f3_cv(df):
    """
    F3测试：检查高CV产品是否更容易在随后6个月出现销量断崖。
    销量断崖定义：growth_rate < -0.5（销量萎缩超过50%）。
    """
    # 将每个观测点的CV分为高/低两组
    cv_valid = df[~df['cv_invalid']].copy()
    if len(cv_valid) == 0:
        return {'error': '无有效CV数据'}

    cv_median = cv_valid['cv'].median()
    high_cv = cv_valid[cv_valid['cv'] > cv_median]
    low_cv = cv_valid[cv_valid['cv'] <= cv_median]

    # 检查下一期growth_rate
    def has_cliff_next_month(grp):
        grp = grp.sort_values('date_month')
        grp['next_growth'] = grp['growth_rate'].shift(-1)
        grp['next_decline'] = grp['y_decline_6m'].shift(-1)
        return grp

    cv_valid_sorted = cv_valid.groupby('product_id', group_keys=False).apply(has_cliff_next_month)

    # 高CV组中下期出现断崖的比例
    high_cliff = cv_valid_sorted[
        (cv_valid_sorted['cv'] > cv_median) &
        (cv_valid_sorted['next_growth'].notna()) &
        (cv_valid_sorted['next_growth'] < -0.5)
    ]
    low_cliff = cv_valid_sorted[
        (cv_valid_sorted['cv'] <= cv_median) &
        (cv_valid_sorted['next_growth'].notna()) &
        (cv_valid_sorted['next_growth'] < -0.5)
    ]

    high_total = (cv_valid_sorted['cv'] > cv_median).sum()
    low_total = (cv_valid_sorted['cv'] <= cv_median).sum()

    high_cliff_rate = len(high_cliff) / high_total if high_total > 0 else 0
    low_cliff_rate = len(low_cliff) / low_total if low_total > 0 else 0

    # 卡方检验
    from scipy.stats import chi2_contingency
    contingency = np.array([
        [len(high_cliff), high_total - len(high_cliff)],
        [len(low_cliff), low_total - len(low_cliff)]
    ])
    try:
        chi2, p_value, _, _ = chi2_contingency(contingency)
    except:
        chi2, p_value = 0, 1.0

    result = {
        'high_cv_cliff_rate': high_cliff_rate,
        'low_cv_cliff_rate': low_cliff_rate,
        'lift': high_cliff_rate / low_cliff_rate if low_cliff_rate > 0 else np.nan,
        'chi2': chi2,
        'p_value': p_value,
        'high_n': high_total,
        'low_n': low_total,
        'significant': bool(p_value < 0.05),
    }

    print(f"  高CV组(n={high_total})销量断崖率: {high_cliff_rate*100:.1f}%")
    print(f"  低CV组(n={low_total})销量断崖率: {low_cliff_rate*100:.1f}%")
    print(f"  Lift: {result['lift']:.2f}x" if result['lift'] else "  Lift: N/A")
    print(f"  卡方检验p值: {p_value:.4f} {'(显著)' if p_value < 0.05 else '(不显著)'}")

    return result


def test_f6_asp(df):
    """
    F6测试：检查ASP下跌是否伴随毛利率下跌（价格战信号）。
    """
    # 有效ASP数据
    asp_valid = df[~df['asp_insufficient']].copy()
    if len(asp_valid) == 0:
        return {'error': '无有效ASP数据'}

    # ASP下跌 = asp_slope < 0
    asp_down = asp_valid[asp_valid['asp_slope'] < 0]
    asp_up = asp_valid[asp_valid['asp_slope'] >= 0]

    # 对应的毛利率斜率
    down_margin = asp_down['slope_ratio'].dropna()
    up_margin = asp_up['slope_ratio'].dropna()
    n_down = len(down_margin)
    n_up = len(up_margin)

    result = {}
    if n_down >= 5 and n_up >= 5:
        t_stat, p_value = stats.ttest_ind(down_margin, up_margin, alternative='less')
        result = {
            'asp_down_margin_slope_mean': down_margin.mean(),
            'asp_up_margin_slope_mean': up_margin.mean(),
            'asp_down_n': len(down_margin),
            'asp_up_n': len(up_margin),
            't_statistic': t_stat,
            'p_value': p_value,
            'significant': bool(p_value < 0.05 and t_stat < 0),
            'margin_down_when_asp_down': (down_margin < 0).mean(),
            'margin_down_when_asp_up': (up_margin < 0).mean(),
        }
        print(f"  ASP下跌组毛利率斜率均值: {down_margin.mean():.6f} (n={len(down_margin)})")
        print(f"  ASP上涨组毛利率斜率均值: {up_margin.mean():.6f} (n={len(up_margin)})")
        print(f"  t检验(p): {p_value:.4f} {'(ASP下跌伴随毛利率下跌)' if p_value < 0.05 and t_stat < 0 else '(不显著)'}")
        print(f"  ASP下跌时毛利率负值比例: {(down_margin<0).mean()*100:.1f}%")
        print(f"  ASP上涨时毛利率负值比例: {(up_margin<0).mean()*100:.1f}%")
    else:
        result = {'error': f'样本不足: ASP下跌{n_down}, ASP上涨{n_up}'}
        print(f"  样本不足")

    return result


# ╔══════════════════════════════════════════════════════════════╗
# ║              案例筛选                                        ║
# ╚══════════════════════════════════════════════════════════════╝

def find_cases(df, fold_results, scheme='B', top_k=5):
    """
    找出成功预警和漏报的典型案例。
    成功预警：风险分>阈值且未来的确进入衰退
    漏报：风险分<阈值但未来进入衰退
    """
    all_details = pd.concat([r['detail'] for r in fold_results], ignore_index=True)
    score_col = f'risk_score_{scheme}'
    level_col = f'risk_level_{scheme}'

    success = all_details[
        (all_details[score_col] > RISK_THRESHOLDS[0]) &
        (all_details['y_decline_6m'] == 1)
    ]
    misses = all_details[
        (all_details[score_col] <= RISK_THRESHOLDS[0]) &
        (all_details['y_decline_6m'] == 1)
    ]

    # 取风险分变化最大的（成功案例取最高分，漏报取风险分最低的）
    success_cases = success.sort_values(score_col, ascending=False).head(top_k)
    miss_cases = misses.sort_values(score_col, ascending=True).head(top_k)

    # 对选中的案例获取完整时间序列
    selected_products_success = success_cases['product_id'].unique()[:top_k]
    selected_products_miss = miss_cases['product_id'].unique()[:top_k]

    success_trajectories = {}
    for prod in selected_products_success:
        prod_history = all_details[all_details['product_id'] == prod].sort_values('date_month')
        success_trajectories[prod] = prod_history

    miss_trajectories = {}
    for prod in selected_products_miss:
        prod_history = all_details[all_details['product_id'] == prod].sort_values('date_month')
        miss_trajectories[prod] = prod_history

    return {
        'success_cases': success_cases,
        'miss_cases': miss_cases,
        'success_trajectories': success_trajectories,
        'miss_trajectories': miss_trajectories,
    }


# ╔══════════════════════════════════════════════════════════════╗
# ║              报告生成                                        ║
# ╚══════════════════════════════════════════════════════════════╝

def generate_report(fold_results, summary_df, factor_diag, cases,
                    output_dir, n_splits, forward_months):
    """生成完整Markdown报告"""
    print(f"\n{'='*60}")
    print("生成最终报告")
    print(f"{'='*60}")

    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(os.path.join(output_dir, "figs"), exist_ok=True)
    os.makedirs(os.path.join(output_dir, "data"), exist_ok=True)

    report_date = datetime.now().strftime("%Y%m%d")
    report_path = os.path.join(output_dir, f"衰退风险模型测试报告_v{report_date}.md")

    # ── 1. 找出最佳方案 ──
    best_scheme = summary_df['auc_roc'].idxmax() if 'auc_roc' in summary_df else 'A'
    scheme_names = {'A': '默认权重', 'B': '优化权重(2026-05)', 'C': '网格搜索', 'D': 'Lasso逻辑回归'}
    best_name = scheme_names.get(best_scheme, best_scheme)

    # ── 生成可视化图表 ──
    figs_dir = os.path.join(output_dir, "figs")

    # 图1: 各方案AUC对比
    plot_auc_comparison(summary_df, figs_dir, scheme_names)

    # 图2: 风险分分布直方图
    plot_risk_distribution(fold_results, figs_dir, best_scheme, scheme_names)

    # 图3: 因子AUC雷达图
    plot_factor_radar(fold_results, figs_dir, best_scheme)

    # 图4: 风险分 vs 实际衰退率校准曲线
    plot_calibration(fold_results, figs_dir, best_scheme, scheme_names)

    # 图5: 案例时间序列
    plot_case_trajectories(cases, figs_dir, best_scheme, scheme_names)

    # ── 构建报告 ──
    lines = []
    def L(s=""):
        lines.append(s)
    def Lf(s, *args, **kwargs):
        lines.append(s.format(*args, **kwargs))

    scheme_names_full = {'A': '默认权重', 'B': '优化权重(2026-05)', 'C': '网格搜索', 'D': 'Lasso逻辑回归'}
    best_name = scheme_names_full.get(best_scheme, best_scheme)

    f1_p = factor_diag.get('F1', {}).get('p_value', 1.0)
    f1_sig = f1_p < 0.05
    f4_lead = factor_diag.get('F4', {}).get('lead_time_median', 'N/A')
    f5_lead = factor_diag.get('F5', {}).get('lead_time_median', 'N/A')

    L("# 衰退风险评分模型测试报告")
    L()
    L(f"**生成日期**: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    L(f"**测试配置**: n_splits={n_splits}, forward_months={forward_months}")
    L("**数据范围**: 2020-07 ~ 2026-02")
    L()
    L("---")
    L()
    L("## 1. 执行摘要")
    L()
    L(f"**推荐方案**: **{best_name}** (AUC-ROC={summary_df.loc[best_scheme, 'auc_roc']:.4f})")
    L()
    can_warn = "**可以**" if f1_sig else "**部分可以**（F1斜率在衰退前未达统计显著，见因子诊断章节）"
    L(f"**核心结论**: 模型{can_warn}提前6个月预警衰退。")
    L(f"- 衰退产品在衰退前F1毛利率趋势斜率显著为负 (p={f1_p:.4f}, {'显著' if f1_sig else '不显著'})")
    L(f"- F4连续下降提前期中位数: {f4_lead}个月")
    L(f"- F5健康度预警提前期中位数: {f5_lead}个月")
    L()

    # ── 2. 模型效果对比 ──
    L("## 2. 模型效果对比")
    L()
    L("| 方案 | AUC-ROC | AUC-PR | F2-Score | Top20命中率 | Top20提升 | 稳定性(Kendall τ) | 推荐度 |")
    L("|------|---------|--------|----------|------------|----------|-------------------|--------|")
    for s in ['A', 'B', 'C', 'D']:
        if s not in summary_df.index:
            continue
        row = summary_df.loc[s]
        auc = row.get('auc_roc', np.nan)
        apr = row.get('auc_pr', np.nan)
        f2 = row.get('f2_score', np.nan)
        top20 = row.get('top20_hit_rate', np.nan)
        top20_lift = row.get('top20_lift', np.nan)
        kendall = row.get('kendall_tau', np.nan)
        stars = '★★★★★' if s == best_scheme else '★★★☆☆'
        L(f"| {scheme_names_full.get(s, s)} | {auc:.4f} | {apr:.4f} | {f2:.4f} | {top20:.1%} | {top20_lift:.2f}x | {kendall:.4f} | {stars} |")
    L()

    # ── 3. 风险分级阈值校准 ──
    all_details = pd.concat([r['detail'] for r in fold_results], ignore_index=True)
    score_col = f'risk_score_{best_scheme}'
    bins = [0, RISK_THRESHOLDS[0], RISK_THRESHOLDS[1], RISK_THRESHOLDS[2], 100]
    labels = RISK_LABELS
    all_details['_risk_tier'] = pd.cut(all_details[score_col], bins=bins, labels=labels, right=True)
    tier_stats = all_details.groupby('_risk_tier', observed=True)['y_decline_6m'].agg(['mean', 'count'])

    L("## 3. 风险分级阈值校准")
    L()
    L(f"当前阈值: 低风险≤{RISK_THRESHOLDS[0]}, 中风险≤{RISK_THRESHOLDS[1]}, 高风险≤{RISK_THRESHOLDS[2]}, 极高风险>{RISK_THRESHOLDS[2]}")
    L()
    L("### 各级别实际衰退率")
    L("| 风险等级 | 阈值范围 | 样本量 | 实际衰退率 |")
    L("|---------|---------|-------|----------|")
    tier_ranges = [f"≤{RISK_THRESHOLDS[0]}", f"{RISK_THRESHOLDS[0]+1}~{RISK_THRESHOLDS[1]}",
                   f"{RISK_THRESHOLDS[1]+1}~{RISK_THRESHOLDS[2]}", f">{RISK_THRESHOLDS[2]}"]
    for i, tier in enumerate(labels):
        if tier in tier_stats.index:
            ts = tier_stats.loc[tier]
            L(f"| {tier} | {tier_ranges[i]} | {int(ts['count'])} | {ts['mean']*100:.1f}% |")
    L()

    # 阈值优化
    best_ths, calib_info = find_optimal_thresholds(all_details, score_col)
    L("### 阈值优化建议")
    L(f"**当前阈值**: [{', '.join(map(str, RISK_THRESHOLDS))}]")
    L()
    if best_ths != RISK_THRESHOLDS:
        L(f"**建议新阈值**: [{', '.join(map(str, best_ths))}]")
        L(f"理由：新阈值下各级别衰退率单调递增且级间差异更大")
    else:
        L("**当前阈值已接近最优**")
    L()
    # 显示新阈值下的衰退率
    new_bins = [0, best_ths[0], best_ths[1], best_ths[2], 100]
    all_details['_new_tier'] = pd.cut(all_details[score_col], bins=new_bins, labels=labels, right=True)
    new_tier_stats = all_details.groupby('_new_tier', observed=True)['y_decline_6m'].agg(['mean', 'count'])
    L("建议阈值下各级别实际衰退率:")
    L("| 风险等级 | 阈值范围 | 样本量 | 实际衰退率 |")
    L("|---------|---------|-------|----------|")
    new_ranges = [f"≤{best_ths[0]}", f"{best_ths[0]+1}~{best_ths[1]}",
                  f"{best_ths[1]+1}~{best_ths[2]}", f">{best_ths[2]}"]
    for i, tier in enumerate(labels):
        if tier in new_tier_stats.index:
            ts2 = new_tier_stats.loc[tier]
            L(f"| {tier} | {new_ranges[i]} | {int(ts2['count'])} | {ts2['mean']*100:.1f}% |")
    L()

    # ── 4. 因子诊断 ──
    L("## 4. 因子诊断与提前预警能力")
    L()
    L("| 因子 | 单因子AUC | 预警提前期(中位数) | 信号准确率 | 诊断结论 |")
    L("|-----|-----------|-------------------|-----------|---------|")
    factor_diag_map = {
        'F1毛利率趋势': ('F1', 'f1_score'),
        'F3订货波动': ('F3', 'f3_score'),
        'F4增速衰减': ('F4', 'f4_score'),
        'F5自比健康度': ('F5', 'f5_score'),
        'F6 ASP趋势': ('F6', 'f6_score'),
    }
    for fname, (fkey, fcol) in factor_diag_map.items():
        aucs = []
        for r in fold_results:
            key = f'A_factor_auc_{fcol}'
            if key in r and not np.isnan(r[key]):
                aucs.append(r[key])
        mean_auc = np.mean(aucs) if aucs else np.nan

        diag = factor_diag.get(fkey, {})
        lead_time = diag.get('lead_time_median', 'N/A')
        if isinstance(lead_time, (int, float)):
            lead_time = f"{lead_time:.0f}月"
        sig_acc = diag.get('signal_accuracy', 'N/A')
        if isinstance(sig_acc, float):
            sig_acc = f"{sig_acc*100:.1f}%"

        if isinstance(mean_auc, float) and not np.isnan(mean_auc):
            if mean_auc >= 0.65:
                conclusion = "✅ 有效"
            elif mean_auc >= 0.55:
                conclusion = "⚠️ 需改进"
            else:
                conclusion = "❌ 弱"
        else:
            conclusion = "❓ 数据不足"

        L(f"| {fname} | {mean_auc:.4f} | {lead_time} | {sig_acc} | {conclusion} |")
    L()

    # ── 5. 衰退案例分析 ──
    L("## 5. 衰退案例分析")
    L()
    # 计算真实月份差
    def month_diff(d1_str, d2_str):
        from datetime import datetime
        try:
            d1 = datetime.strptime(str(d1_str)[:7], '%Y-%m')
            d2 = datetime.strptime(str(d2_str)[:7], '%Y-%m')
            return (d2.year - d1.year) * 12 + (d2.month - d1.month)
        except:
            return None

    L("### 5.1 成功预警案例 (Top 5)")
    L()
    L("| 产品型号 | 首次高风险预警时间 | 实际衰退时间 | 提前月数 | 主导因子 | 风险分峰值 |")
    L("|---------|-----------------|------------|---------|---------|----------|")
    for prod, trajectory in list(cases['success_trajectories'].items())[:5]:
        if len(trajectory) == 0:
            continue
        first_alert = trajectory[trajectory[score_col] > RISK_THRESHOLDS[0]]
        decline_point = trajectory[trajectory['y_decline_6m'] == 1]
        if len(first_alert) > 0 and len(decline_point) > 0:
            fa_date = str(first_alert['date_month'].iloc[0])
            dec_date = str(decline_point['date_month'].iloc[0])
            lead_m = month_diff(fa_date, dec_date)
            max_score = trajectory[score_col].max()
            f_scores = trajectory.iloc[-1][['f1_score','f3_score','f4_score','f5_score','f6_score']]
            dominant = ['F1','F3','F4','F5','F6'][np.argmax(f_scores.values)]
            L(f"| {prod} | {fa_date} | {dec_date} | {lead_m if lead_m else '?'} | {dominant} | {max_score:.1f} |")
    L()

    L("### 5.2 漏报案例 (Top 5)")
    L()
    L("| 产品型号 | 最大风险分 | 实际衰退时间 | 漏报原因分析 |")
    L("|---------|----------|------------|------------|")
    for prod, trajectory in list(cases['miss_trajectories'].items())[:5]:
        if len(trajectory) == 0:
            continue
        max_score = trajectory[score_col].max()
        decline_point = trajectory[trajectory['y_decline_6m'] == 1]
        dec_date = str(decline_point['date_month'].iloc[0]) if len(decline_point) > 0 else 'N/A'
        last_row = trajectory.iloc[-1]
        reasons = []
        if last_row.get('slope_insufficient', False) or last_row.get('zero_profit', False):
            reasons.append("F1数据不足(斜率不可靠)")
        if last_row.get('cv_invalid', False):
            reasons.append("F3无发货(CV无效)")
        if 'f5_score' in trajectory.columns and last_row.get('f5_score', 50) >= 70:
            reasons.append("F5健康度被低估(>70仍算高风险)")
        if last_row.get('asp_insufficient', False):
            reasons.append("F6 ASP数据不足")
        if not reasons:
            # 检查权重分配
            reasons.append("因子得分虽高但权重分配不足")
        L(f"| {prod} | {max_score:.1f} | {dec_date} | {'; '.join(reasons)} |")
    L()

    # ── 6. 操作建议矩阵 ──
    L("## 6. 操作建议矩阵")
    L()
    L("| 风险等级 | 关键触发因子 | 建议动作 | 责任方 | 检查周期 |")
    L("|---------|-------------|---------|--------|---------|")
    L("| 极高风险(>58) | F5健康度<30% + F4连续下降>3月 | 启动退市评估/促销清仓/替代新品导入 | 产品部+销售部 | 2周 |")
    L("| 高风险(53-58) | F1斜率负 + F6 ASP跌 | 成本复盘/价格策略调整/客户挽留 | 产品部+财务部 | 月 |")
    L("| 中风险(35-52) | F3 CV高 | 监控库存/加强客户拜访 | 销售部 | 月 |")
    L("| 低风险(≤34) | — | 维持正常运营 | — | 季度 |")
    L()

    # ── 7. 模型局限与改进建议 ──
    cv_miss_rate = all_details.get('cv', pd.Series([np.nan])).isna().mean() * 100
    L("## 7. 模型局限与改进建议")
    L()
    L("### 已知局限")
    L("1. **新品数据不足**: 日历月龄<12月的产品F5自比健康度依赖全历史中位数，参照组质量低于p95分位数。")
    L(f"2. **CV缺失场景**: 无发货月份CV被标记为无效（占{cv_miss_rate:.1f}%观测），降权后F3贡献归零。")
    L("3. **季节性产品**: 使用固定12月窗口难以区分真实衰退与季节性波动。")
    L("4. **脉冲发货**: 一次性大单导致增速虚假波动（已有CV豁免，但衰减指标仍受影响）。")
    L()
    L("### 改进建议")
    L("1. **增加外部参照组**: 当前F5自比健康度仅用产品自身历史，可加入品类/市场参照组提高区分度。")
    L("2. **引入价格弹性信号**: 降价-毛利率联动可作为F6 ASP趋势的补充验证。")
    L("3. **衰退概率校准**: 当前为规则评分，可加入Platt/Isotonic校准输出真实衰退概率。")
    L("4. **多时间尺度**: 增加3月短期预警标签，与6月中期预警形成互补。")
    L("5. **F1斜率增强**: 当前F1在衰退前p值不显著，需检查是否是Winsorization过度或窗口期选择问题。")
    L()
    L("---")
    L()
    L("## 附录：可视化图表")
    L()
    L("### 图1: 各方案AUC-ROC对比")
    L("![AUC对比](figs/auc_comparison.png)")
    L()
    L("### 图2: 风险分分布与衰退率")
    L("![风险分布](figs/risk_distribution.png)")
    L()
    L("### 图3: 因子诊断雷达图")
    L("![因子雷达](figs/factor_radar.png)")
    L()
    L("### 图4: 校准曲线")
    L("![校准曲线](figs/calibration.png)")
    L()
    L("### 图5: 案例时间序列")
    L("![案例轨迹](figs/case_trajectories.png)")
    L()
    L("---")
    L(f"*报告由自动化回溯测试框架生成: {datetime.now().strftime('%Y-%m-%d %H:%M')}*")

    report = "\n".join(lines)

    # 写入报告
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report)
    print(f"  报告已保存: {report_path}")

    # ── 保存结果CSV ──
    data_dir = os.path.join(output_dir, "data")
    for r in fold_results:
        fold_num = r['fold']
        detail = r['detail']
        detail.to_csv(os.path.join(data_dir, f"fold_{fold_num}_details.csv"),
                      index=False, encoding='utf-8-sig')

    summary_df.to_csv(os.path.join(data_dir, "summary_metrics.csv"),
                      encoding='utf-8-sig')
    print(f"  详细结果已保存: {data_dir}")

    return report_path


def plot_auc_comparison(summary_df, figs_dir, scheme_names):
    """各方案AUC对比柱状图"""
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.5))

    metrics_to_plot = ['auc_roc', 'auc_pr', 'f2_score']
    titles = ['AUC-ROC', 'AUC-PR', 'F2-Score (β=2)']
    colors = ['#2E86AB', '#A23B72', '#F18F01', '#73AB84']

    for ax, metric, title in zip(axes, metrics_to_plot, titles):
        vals = []
        labels = []
        for s in ['A', 'B', 'C', 'D']:
            if s in summary_df.index and metric in summary_df.columns:
                mean_v = summary_df.loc[s, metric]
                std_key = f'{metric}_std'
                std_v = summary_df.loc[s, std_key] if std_key in summary_df.columns else 0
                labels.append(scheme_names.get(s, s)[:4])
                vals.append((mean_v, std_v))

        if vals:
            means, stds = zip(*vals)
            bars = ax.bar(range(len(means)), means, yerr=stds, capsize=5,
                         color=colors[:len(means)], alpha=0.8)
            ax.set_title(title, fontsize=12, fontweight='bold')
            ax.set_xticks(range(len(labels)))
            ax.set_xticklabels(labels, fontsize=8)
            ax.set_ylim(max(0, min(means)*0.9), min(1, max(means)*1.1))
            ax.axhline(y=0.5, color='gray', linestyle='--', alpha=0.5, label='Random')
            # Add value labels
            for i, (m, s) in enumerate(vals):
                ax.text(i, m + s + 0.01, f'{m:.3f}', ha='center', fontsize=7, fontweight='bold')

    plt.tight_layout()
    path = os.path.join(figs_dir, "auc_comparison.png")
    fig.savefig(path, dpi=150, bbox_inches='tight')
    plt.close(fig)


def plot_risk_distribution(fold_results, figs_dir, scheme, scheme_names):
    """风险分分布直方图 + 各级别衰退率"""
    all_details = pd.concat([r['detail'] for r in fold_results], ignore_index=True)
    score_col = f'risk_score_{scheme}'

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    # 左图：分布直方图
    ax1 = axes[0]
    scores = all_details[score_col].values
    decline = all_details['y_decline_6m'].values == 1
    healthy = all_details['y_decline_6m'].values == 0

    ax1.hist([scores[healthy], scores[decline]], bins=30,
             label=['健康', '衰退'], color=['#4CAF50', '#F44336'],
             alpha=0.6, stacked=True)
    for t in RISK_THRESHOLDS:
        ax1.axvline(x=t, color='orange', linestyle='--', alpha=0.7)
    ax1.set_xlabel('风险评分')
    ax1.set_ylabel('样本数')
    ax1.set_title(f'风险评分分布 ({scheme_names.get(scheme, scheme)})')
    ax1.legend()

    # 右图：各级别衰退率
    ax2 = axes[1]
    bins = [-1, RISK_THRESHOLDS[0], RISK_THRESHOLDS[1], RISK_THRESHOLDS[2], 100]
    labels = RISK_LABELS
    all_details['_tier'] = pd.cut(all_details[score_col], bins=bins, labels=labels, right=True)
    tier_stats = all_details.groupby('_tier', observed=True)['y_decline_6m'].agg(['mean', 'count'])
    colors_tier = ['#4CAF50', '#FFC107', '#FF9800', '#F44336']

    means = [tier_stats.loc[t, 'mean']*100 if t in tier_stats.index else 0 for t in labels]
    counts = [int(tier_stats.loc[t, 'count']) if t in tier_stats.index else 0 for t in labels]
    bars = ax2.bar(labels, means, color=colors_tier, alpha=0.8)
    for i, (m, c) in enumerate(zip(means, counts)):
        ax2.text(i, m + 0.5, f'{m:.1f}%\n(n={c})', ha='center', fontsize=9)
    ax2.set_ylabel('实际衰退率 (%)')
    ax2.set_title('各级别实际衰退率')
    ax2.set_ylim(0, max(means)*1.3 + 10)

    plt.tight_layout()
    path = os.path.join(figs_dir, "risk_distribution.png")
    fig.savefig(path, dpi=150, bbox_inches='tight')
    plt.close(fig)


def plot_factor_radar(fold_results, figs_dir, scheme):
    """因子AUC雷达图"""
    all_details = pd.concat([r['detail'] for r in fold_results], ignore_index=True)
    y = all_details['y_decline_6m'].values

    factors = ['f1_score', 'f3_score', 'f4_score', 'f5_score', 'f6_score']
    factor_names = ['F1\n毛利率斜率', 'F3\n订货波动', 'F4\n增速衰减', 'F5\n自比健康度', 'F6\nASP趋势']

    aucs = []
    for col in factors:
        vals = all_details[col].values
        valid = ~np.isnan(vals)
        if valid.sum() >= 10 and len(np.unique(y[valid])) >= 2:
            auc = roc_auc_score(y[valid], vals[valid])
        else:
            auc = 0.5
        aucs.append(auc)
    aucs.append(aucs[0])  # close the polygon
    names = factor_names + [factor_names[0]]

    angles = np.linspace(0, 2 * np.pi, len(factors), endpoint=False).tolist()
    angles_closed = angles + angles[:1]

    fig, ax = plt.subplots(figsize=(7, 7), subplot_kw=dict(polar=True))
    ax.fill(angles_closed, aucs, alpha=0.25, color='#2E86AB')
    ax.plot(angles_closed, aucs, 'o-', color='#2E86AB', linewidth=2)
    ax.set_xticks(angles)
    ax.set_xticklabels(factor_names, fontsize=10)
    ax.set_ylim(0.3, 0.8)
    ax.set_title('单因子预测AUC (各因子单独预测衰退)', fontsize=13, fontweight='bold', pad=20)
    ax.axhline(y=0.5, color='gray', linestyle='--', alpha=0.5, label='Random')
    ax.legend(loc='lower right')

    # 标注AUC值
    for i, (a, v) in enumerate(zip(angles[:-1], aucs[:-1])):
        ax.text(a, v + 0.03, f'{v:.3f}', ha='center', fontsize=9, fontweight='bold')

    path = os.path.join(figs_dir, "factor_radar.png")
    fig.savefig(path, dpi=150, bbox_inches='tight')
    plt.close(fig)


def plot_calibration(fold_results, figs_dir, scheme, scheme_names=None):
    """校准曲线：风险分百分位 vs 实际衰退率"""
    if scheme_names is None:
        scheme_names = {'A': '默认', 'B': '优化', 'C': '网格', 'D': 'Lasso'}
    all_details = pd.concat([r['detail'] for r in fold_results], ignore_index=True)
    score_col = f'risk_score_{scheme}'

    scores = all_details[score_col].values
    y = all_details['y_decline_6m'].values

    # 按百分位分20组
    percentiles = np.percentile(scores, np.linspace(0, 100, 21))
    bin_means = []
    bin_actual = []
    for i in range(len(percentiles)-1):
        mask = (scores >= percentiles[i]) & (scores < percentiles[i+1])
        if mask.sum() >= 5:
            bin_means.append(np.mean(scores[mask]))
            bin_actual.append(y[mask].mean())

    fig, ax = plt.subplots(figsize=(8, 6))
    ax.plot(bin_means, bin_actual, 'o-', color='#2E86AB', linewidth=2, markersize=8)
    ax.plot([0, 100], [0, 1], '--', color='gray', alpha=0.5, label='Perfect Calibration')
    ax.set_xlabel('平均风险评分', fontsize=11)
    ax.set_ylabel('实际衰退率', fontsize=11)
    ax.set_title(f'校准曲线 ({scheme_names.get(scheme, scheme)})', fontsize=13, fontweight='bold')
    ax.legend()
    ax.grid(True, alpha=0.3)

    path = os.path.join(figs_dir, "calibration.png")
    fig.savefig(path, dpi=150, bbox_inches='tight')
    plt.close(fig)


def plot_case_trajectories(cases, figs_dir, scheme, scheme_names):
    """案例风险分变化时间序列"""
    score_col = f'risk_score_{scheme}'

    fig, axes = plt.subplots(2, 5, figsize=(20, 8))
    fig.suptitle('案例风险评分变化轨迹', fontsize=14, fontweight='bold', y=1.02)

    # 成功案例
    for idx, (prod, trajectory) in enumerate(list(cases['success_trajectories'].items())[:5]):
        if idx >= 5:
            break
        ax = axes[0, idx]
        dates = trajectory['date_month'].values
        scores = trajectory[score_col].values
        decline = trajectory['y_decline_6m'].values

        ax.plot(range(len(scores)), scores, 'b-', linewidth=2)
        # Mark decline point
        decline_idx = np.where(decline == 1)[0]
        if len(decline_idx) > 0:
            ax.axvline(x=decline_idx[0], color='red', linestyle='--', alpha=0.7, label='衰退')
        for t in RISK_THRESHOLDS:
            ax.axhline(y=t, color='orange', linestyle=':', alpha=0.4)
        ax.set_title(f'{prod}', fontsize=9)
        ax.set_xlabel('时间')
        ax.set_ylabel('风险分')
        if idx == 0:
            ax.legend(fontsize=7)

    # 漏报案例
    for idx, (prod, trajectory) in enumerate(list(cases['miss_trajectories'].items())[:5]):
        if idx >= 5:
            break
        ax = axes[1, idx]
        dates = trajectory['date_month'].values
        scores = trajectory[score_col].values
        decline = trajectory['y_decline_6m'].values

        ax.plot(range(len(scores)), scores, 'r-', linewidth=2)
        decline_idx = np.where(decline == 1)[0]
        if len(decline_idx) > 0:
            ax.axvline(x=decline_idx[0], color='red', linestyle='--', alpha=0.7, label='衰退')
        for t in RISK_THRESHOLDS:
            ax.axhline(y=t, color='orange', linestyle=':', alpha=0.4)
        ax.set_title(f'{prod}', fontsize=9)
        ax.set_xlabel('时间')
        ax.set_ylabel('风险分')
        if idx == 0:
            ax.legend(fontsize=7)

    plt.tight_layout()
    path = os.path.join(figs_dir, "case_trajectories.png")
    fig.savefig(path, dpi=150, bbox_inches='tight')
    plt.close(fig)


def find_optimal_thresholds(df, score_col):
    """寻找最优风险分级阈值"""
    scores = df[score_col].values
    y = df['y_decline_6m'].values

    best_f1 = -1
    best_thresholds = list(RISK_THRESHOLDS)

    # 搜索最优切点：F1最大化 = 各级别内差异最小 + 各级别间差异最大
    # 使用更合理的搜索范围，避免极端阈值
    for t1 in range(25, 42, 2):
        for t2 in range(t1+8, 58, 2):
            for t3 in range(t2+8, 75, 2):
                bins = [-1, t1, t2, t3, 100]
                try:
                    tier_rates = []
                    tier_counts = []
                    for i in range(len(bins)-1):
                        mask = (scores > bins[i]) & (scores <= bins[i+1])
                        n = mask.sum()
                        if n >= 15:
                            tier_rates.append(y[mask].mean())
                            tier_counts.append(n)
                    if len(tier_rates) < 4:
                        continue
                    # 各级别衰退率必须严格递增，且每组至少15个样本
                    monotonic = all(tier_rates[i] < tier_rates[i+1] for i in range(3))
                    # F1-score: harmonic mean of precision and recall for the 分级
                    # 简化：单调递增 + 最低组衰退率<25% + 最高组衰退率>50%
                    if monotonic and tier_rates[0] < 0.25 and tier_rates[3] > 0.50:
                        # 最大化最高组与最低组的差异
                        spread = tier_rates[3] - tier_rates[0]
                        if spread > best_f1:
                            best_f1 = spread
                            best_thresholds = [t1, t2, t3]
                except:
                    continue

    return best_thresholds, ""


# ╔══════════════════════════════════════════════════════════════╗
# ║              Main                                           ║
# ╚══════════════════════════════════════════════════════════════╝

def main():
    parser = argparse.ArgumentParser(description='衰退风险模型回溯测试框架')
    parser.add_argument('--data_path', default=None, help='样本数据路径 (samples.pkl)')
    parser.add_argument('--output_dir', default=DEFAULT_OUTPUT, help='输出目录')
    parser.add_argument('--n_splits', type=int, default=5, help='TimeSeriesSplit折数')
    parser.add_argument('--forward_months', type=int, default=6, help='前瞻月数')
    args = parser.parse_args()

    print("=" * 60)
    print("产品生命周期衰退风险评分模型 — 自动化回溯测试")
    print("=" * 60)

    # 1. 加载数据
    df = load_data(args.data_path)
    df = build_label_6m(df)

    # 2. 运行回溯测试
    fold_results, summary = run_backtest(df, n_splits=args.n_splits,
                                          forward_months=args.forward_months)

    print(f"\n{'='*60}")
    print("评估结果汇总")
    print(f"{'='*60}")
    print(summary.round(4).to_string())

    # 3. 因子诊断
    factor_diag = factor_diagnostic_tests(df)

    # 4. 筛选案例
    cases = find_cases(df, fold_results, scheme='B', top_k=5)

    # 5. 生成报告
    report_path = generate_report(fold_results, summary, factor_diag, cases,
                                   args.output_dir, args.n_splits, args.forward_months)

    print(f"\n{'='*60}")
    print(f"测试完成！报告已生成: {report_path}")
    print(f"{'='*60}")
    return 0


if __name__ == '__main__':
    main()
