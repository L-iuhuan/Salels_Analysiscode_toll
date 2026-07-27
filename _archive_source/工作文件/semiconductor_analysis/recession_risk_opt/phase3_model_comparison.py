"""
Phase 3: 四模型对比评估
======================
M0 (基线): 原始 F1-F6 因子
M1 (F1修复): F1f(毛利额斜率) 替换 F1
M2 (客户增强): 原始因子 + c6(单次订货量衰减)
M3 (双轨): F1f + 原始F3-F6 + c6

评估方法: TimeSeriesSplit 5折, LogisticRegression (class_weight='balanced')
"""

import os, sys, warnings
from datetime import datetime
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
# 中文字体配置
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DengXian', 'Noto Sans SC']
plt.rcParams['axes.unicode_minus'] = False
plt.rcParams['font.family'] = 'sans-serif'
from sklearn.model_selection import TimeSeriesSplit
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import (roc_auc_score, roc_curve, average_precision_score,
                             precision_recall_curve, fbeta_score, confusion_matrix)
from scipy import stats

warnings.filterwarnings('ignore')

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(PROJECT_ROOT))
OUTPUT_DIR = os.path.join(os.path.dirname(PROJECT_ROOT), 'test_output')
os.makedirs(OUTPUT_DIR, exist_ok=True)

np.random.seed(42)

CONFIG = {
    'phase1_path': os.path.join(OUTPUT_DIR, 'phase1_customer_factors.csv'),
    'samples_path': os.path.join(PROJECT_ROOT, 'data', 'samples.pkl'),
    'n_splits': 5,
    'output_dir': OUTPUT_DIR,
}

# ── 模型定义 ──
MODELS = {
    'M0_基线': {
        'display': 'M0 基线 (原始F1-F6)',
        'features': ['f1_score', 'f3_score', 'f4_score', 'f5_score', 'f6_score'],
    },
    'M1_F1修复': {
        'display': 'M1 F1修复 (F1f替代F1)',
        'features': ['f1f_6m_gp_amount', 'f3_score', 'f4_score', 'f5_score', 'f6_score'],
    },
    'M2_客户增强': {
        'display': 'M2 客户增强 (原始F1-F6 + c6)',
        'features': ['f1_score', 'f3_score', 'f4_score', 'f5_score', 'f6_score', 'c6_order_qty_change'],
    },
    'M3_双轨': {
        'display': 'M3 双轨 (F1f + F3-F6 + c6)',
        'features': ['f1f_6m_gp_amount', 'f3_score', 'f4_score', 'f5_score', 'f6_score', 'c6_order_qty_change'],
    },
}

RISK_THRESHOLDS = [30, 50, 65]


def compute_f1f_from_samples(df):
    """从 samples.pkl 计算 F1f: 毛利额斜率"""
    print("计算 F1f 毛利额斜率 (从 samples.pkl 估计)...")
    df_est = df.copy()
    # Bug 4修复: 毛利率异常 — >100%或<-50%视为缺失
    df_est['recent_margin'] = df_est['recent_margin'].where(
        (df_est['recent_margin'] <= 1.0) & (df_est['recent_margin'] >= -0.5),
        np.nan
    )
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
                # Bug 1修复: 取反 — 值越大=风险越高
                val = -slope / mean_val if (mean_val > 0 and not np.isnan(slope)) else np.nan
            else:
                val = np.nan
            results.append({
                'product_id': grp['product_id'].iloc[i],
                'date_month': grp['date_month'].iloc[i],
                'f1f_6m_gp_amount': val,
            })

    f1f = pd.DataFrame(results)
    miss = f1f['f1f_6m_gp_amount'].isna().mean() * 100
    print(f"  F1f 形状: {f1f.shape}, 缺失率: {miss:.1f}%")
    return f1f


DECLINE_PORTRAITS = {"衰退期", "夕阳产品", "隐性衰退"}


def compute_decline_label_6m(df):
    """收紧版标签：连续3月衰退九宫格 OR 连续3月毛利率≤0且销量萎缩>20% (Bug 3修复)"""
    df_sorted = df.sort_values(['product_id', 'date_month']).copy()
    y_6m = []
    for prod, grp in df_sorted.groupby('product_id'):
        grp = grp.sort_values('date_month')
        portraits = grp['portrait'].values
        margins = grp['recent_margin'].values
        growths = grp['growth_rate'].values
        n = len(grp)
        for i in range(n):
            fs = i + 1
            fe = min(i + 7, n)
            if fs >= fe:
                y_6m.append(int(grp['y'].iloc[i]) if 'y' in grp.columns else 0)
                continue
            fp = portraits[fs:fe]
            fm = margins[fs:fe]
            fg = growths[fs:fe]
            # 条件1：连续3月衰退九宫格
            if len(fp) >= 3:
                decline_bits = [1 if p in DECLINE_PORTRAITS else 0 for p in fp]
                in_decline_3m = any(sum(decline_bits[j:j+3]) == 3 for j in range(len(decline_bits) - 2))
            else:
                in_decline_3m = False
            # 条件2：连续3月毛利率≤0且销量萎缩>20%
            if len(fm) >= 3 and len(fg) >= 3:
                bad_bits = [1 if (m <= 0 and g < -0.2) else 0 for m, g in zip(fm, fg)]
                margin_bad_3m = any(sum(bad_bits[j:j+3]) == 3 for j in range(len(bad_bits) - 2))
            else:
                margin_bad_3m = False
            y_6m.append(1 if (in_decline_3m or margin_bad_3m) else 0)
    df_sorted['y_decline_6m'] = y_6m
    return df_sorted


def load_data():
    """加载并准备完整数据集"""
    print("=" * 60)
    print("Phase 3: 加载数据")
    print("=" * 60)

    # 从 samples.pkl 重新计算标签 (Bug 3修复)
    raw = pd.read_pickle(CONFIG['samples_path'])
    raw_labeled = compute_decline_label_6m(raw)
    label_cols = ['product_id', 'date_month', 'y_decline_6m']
    new_labels = raw_labeled[label_cols]
    pos_rate = new_labels['y_decline_6m'].mean()
    print(f"新标签衰退率: {pos_rate*100:.1f}% ({new_labels['y_decline_6m'].sum()}/{len(new_labels)})")

    # Phase 1 output (客户因子 c1-c6)
    df = pd.read_csv(CONFIG['phase1_path'], encoding='utf-8-sig')
    print(f"Phase 1 数据: {df.shape}")

    # 用新标签覆盖旧标签
    if 'y_decline_6m' in df.columns:
        df = df.drop(columns=['y_decline_6m'])
    df = df.merge(new_labels, on=['product_id', 'date_month'], how='left')
    print(f"标签更新后: y_decline_6m 衰退率={df['y_decline_6m'].mean()*100:.1f}%")

    # 计算 F1f
    f1f = compute_f1f_from_samples(raw)

    # 合并 F1f
    df = df.merge(f1f, on=['product_id', 'date_month'], how='left')
    print(f"合并 F1f 后: {df.shape}")
    print(f"F1f 缺失率: {df['f1f_6m_gp_amount'].isna().mean()*100:.1f}%")

    # Bug 2修复: c6缺失时用c3兜底填充
    c6_miss_before = df['c6_order_qty_change'].isna().mean() * 100
    df['c6_order_qty_change'] = df['c6_order_qty_change'].fillna(df['c3_customer_net_change'])
    c6_miss_after = df['c6_order_qty_change'].isna().mean() * 100
    print(f"c6缺失率: {c6_miss_before:.1f}% → {c6_miss_after:.1f}% (c3兜底填充后)")

    # Bug 1修复: c6取反 — 统一编码(值越大=风险越高)
    df['c6_order_qty_change'] = -df['c6_order_qty_change']

    print(f"月份: {df['date_month'].min()} ~ {df['date_month'].max()}, {df['date_month'].nunique()} 个月")
    print(f"产品: {df['product_id'].nunique()}")

    return df


def evaluate_model(model_key, model_info, df_full, tscv, months):
    """对单个模型进行 TimeSeriesSplit 评估"""
    features = model_info['features']
    display = model_info['display']

    # 检查特征缺失
    for f in features:
        miss = df_full[f].isna().mean() * 100
        if miss > 0:
            print(f"  [警告] 特征 '{f}' 缺失率 {miss:.1f}%")

    # 全局填充值 (用全量数据中位数，避免某些折样本不足)
    global_fill = {}
    for f in features:
        global_fill[f] = df_full[f].median()

    fold_results = []
    all_y_true = []
    all_y_score = []

    for fold, (train_idx, val_idx) in enumerate(tscv.split(months)):
        train_months = [months[i] for i in train_idx]
        val_months = [months[i] for i in val_idx]

        train_df = df_full[df_full['date_month'].isin(train_months)].copy()
        val_df = df_full[df_full['date_month'].isin(val_months)].copy()

        X_train = train_df[features].fillna(global_fill).values
        y_train = train_df['y_decline_6m'].values
        X_val = val_df[features].fillna(global_fill).values
        y_val = val_df['y_decline_6m'].values

        # 标准化
        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_val_scaled = scaler.transform(X_val)

        # 训练
        model = LogisticRegression(
            class_weight='balanced',
            max_iter=5000,
            random_state=42 + fold,
            solver='lbfgs',
        )
        model.fit(X_train_scaled, y_train)

        # 预测概率
        y_prob = model.predict_proba(X_val_scaled)[:, 1]
        all_y_true.extend(y_val.tolist())
        all_y_score.extend(y_prob.tolist())

        # 系数 (反标准化后)
        coef = model.coef_[0]
        importance = pd.Series(coef, index=features).abs().sort_values(ascending=False)

        # 折内指标
        fold_metrics = {'fold': fold + 1}
        if len(np.unique(y_val)) >= 2:
            fold_metrics['auc_roc'] = roc_auc_score(y_val, y_prob)
        else:
            fold_metrics['auc_roc'] = np.nan
        fold_metrics['auc_pr'] = average_precision_score(y_val, y_prob)
        fold_metrics['n_train'] = len(y_train)
        fold_metrics['n_val'] = len(y_val)
        fold_metrics['pos_rate_val'] = y_val.mean()
        fold_metrics['coef'] = dict(zip(features, coef))

        # F2-Score (beta=2, 偏重召回)
        pred_binary = (y_prob > 0.5).astype(int)
        if len(np.unique(pred_binary)) >= 2 and len(np.unique(y_val)) >= 2:
            fold_metrics['f2_score'] = fbeta_score(y_val, pred_binary, beta=2)
        else:
            fold_metrics['f2_score'] = np.nan

        # Top-20% 命中率
        n_top = max(1, len(y_prob) // 5)
        top_idx = np.argsort(y_prob)[-n_top:]
        fold_metrics['top20_hit_rate'] = y_val[top_idx].mean()
        fold_metrics['baseline_rate'] = y_val.mean()

        # 校准: 预测概率 vs 实际频率 (分10桶)
        prob_bins = np.linspace(0, 1, 11)
        bin_indices = np.digitize(y_prob, prob_bins) - 1
        bin_indices = np.clip(bin_indices, 0, 9)
        bin_actual = np.array([y_val[bin_indices == i].mean() if (bin_indices == i).sum() > 0 else np.nan
                               for i in range(10)])
        bin_pred = np.array([y_prob[bin_indices == i].mean() if (bin_indices == i).sum() > 0 else np.nan
                             for i in range(10)])
        valid_cal = ~(np.isnan(bin_actual) | np.isnan(bin_pred))
        if valid_cal.sum() >= 3:
            fold_metrics['calibration_intercept'] = np.mean(bin_pred[valid_cal] - bin_actual[valid_cal])
        else:
            fold_metrics['calibration_intercept'] = np.nan

        fold_results.append(fold_metrics)

    # 汇总
    summary = {}
    metrics_to_avg = ['auc_roc', 'auc_pr', 'f2_score', 'top20_hit_rate', 'calibration_intercept']
    for m in metrics_to_avg:
        vals = [r[m] for r in fold_results if not np.isnan(r.get(m, np.nan))]
        if vals:
            summary[m] = np.mean(vals)
            summary[f'{m}_std'] = np.std(vals)
        else:
            summary[m] = np.nan
            summary[f'{m}_std'] = np.nan

    # 合并预测
    all_y_true = np.array(all_y_true)
    all_y_score = np.array(all_y_score)

    # 系数稳定性
    coef_list = [r['coef'] for r in fold_results if 'coef' in r]
    if coef_list:
        coef_df = pd.DataFrame(coef_list)
        summary['coef_mean'] = coef_df.mean().to_dict()
        summary['coef_std'] = coef_df.std().to_dict()
        summary['coef_stability_cv'] = (coef_df.std() / coef_df.mean().abs()).mean()

    # Spearman rho (风险分 vs 实际衰退)
    if len(np.unique(all_y_true)) >= 2:
        rho, p = stats.spearmanr(all_y_score, all_y_true)
        summary['spearman_rho'] = rho
        summary['spearman_p'] = p

    # 综合分
    if not np.isnan(summary.get('auc_roc', np.nan)):
        summary['composite_score'] = (
            summary['auc_roc'] * 0.5 +                          # AUC权重50%
            summary.get('auc_pr', 0) * 0.2 +                    # PR-AUC权重20%
            summary.get('top20_hit_rate', 0) * 0.2 +            # Top20命中率20%
            max(0, 1 - abs(summary.get('calibration_intercept', 0))) * 0.1  # 校准误差10%
        )

    print(f"  [{display}] AUC={summary.get('auc_roc', np.nan):.4f} +- {summary.get('auc_roc_std', np.nan):.4f} | "
          f"PR-AUC={summary.get('auc_pr', np.nan):.4f} | "
          f"Top20命中率={summary.get('top20_hit_rate', np.nan):.1%} | "
          f"综合={summary.get('composite_score', np.nan):.4f}")

    return summary, fold_results, all_y_true, all_y_score


def evaluate_all_models(df_full):
    """评估全部4个模型"""
    print("\n" + "=" * 60)
    print("4模型 5折 TimeSeriesSplit 评估")
    print("=" * 60)

    months = sorted(df_full['date_month'].unique())
    tscv = TimeSeriesSplit(n_splits=CONFIG['n_splits'])
    print(f"月份: {len(months)}, {months[0]} ~ {months[-1]}")
    print()

    all_results = {}
    for key, info in MODELS.items():
        print(f"\n--- 评估 {info['display']} ---")
        summary, fold_results, y_true, y_score = evaluate_model(key, info, df_full, tscv, months)
        all_results[key] = {
            'summary': summary,
            'fold_results': fold_results,
            'y_true': y_true,
            'y_score': y_score,
            'info': info,
        }

    return all_results


def plot_roc_curves(all_results):
    """绘制4模型ROC曲线对比"""
    fig, ax = plt.subplots(figsize=(10, 8))

    colors = ['#3498db', '#e74c3c', '#2ecc71', '#f39c12']
    for (key, res), color in zip(all_results.items(), colors):
        y_true = res['y_true']
        y_score = res['y_score']
        auc_val = res['summary'].get('auc_roc', np.nan)
        if len(np.unique(y_true)) >= 2 and not np.isnan(y_score).all():
            fpr, tpr, _ = roc_curve(y_true, y_score)
            ax.plot(fpr, tpr, color=color, lw=2,
                    label=f"{res['info']['display']} (AUC={auc_val:.4f})")

    ax.plot([0, 1], [0, 1], 'k--', lw=1, alpha=0.6, label='随机')
    ax.set_xlabel('假阳性率 (FPR)', fontsize=12)
    ax.set_ylabel('真阳性率 (TPR)', fontsize=12)
    ax.set_title('Phase 3: 4模型 ROC 曲线对比', fontsize=14)
    ax.legend(loc='lower right', fontsize=10)
    ax.grid(alpha=0.3)
    plt.tight_layout()
    path = os.path.join(CONFIG['output_dir'], 'phase3_roc_comparison.png')
    plt.savefig(path, dpi=150)
    plt.close()
    print(f"ROC曲线已保存: {path}")


def plot_feature_importance(all_results):
    """绘制各模型特征重要性对比"""
    n_models = len([k for k in all_results if all_results[k]['summary'].get('coef_mean')])
    if n_models == 0:
        return

    fig, axes = plt.subplots(1, n_models, figsize=(5 * n_models, 5))
    if n_models == 1:
        axes = [axes]

    idx = 0
    for key, res in all_results.items():
        if 'coef_mean' not in res['summary']:
            continue
        coef_mean = res['summary']['coef_mean']
        coef_std = res['summary'].get('coef_std', {})
        features_sorted = sorted(coef_mean.keys(), key=lambda x: abs(coef_mean[x]), reverse=True)
        vals = [coef_mean[f] for f in features_sorted]
        errs = [coef_std.get(f, 0) for f in features_sorted]

        colors = ['#e74c3c' if v < 0 else '#2ecc71' for v in vals]
        axes[idx].barh(features_sorted, vals, xerr=errs, color=colors, alpha=0.8)
        axes[idx].axvline(0, color='black', lw=0.5)
        axes[idx].set_title(f"{res['info']['display']}", fontsize=11)
        axes[idx].set_xlabel('标准化系数')
        idx += 1

    plt.tight_layout()
    path = os.path.join(CONFIG['output_dir'], 'phase3_feature_importance.png')
    plt.savefig(path, dpi=150)
    plt.close()
    print(f"特征重要性已保存: {path}")


def generate_report(all_results):
    """生成 Phase 3 报告"""
    print("\n" + "=" * 60)
    print("生成报告")
    print("=" * 60)

    lines = []
    def L(s=""):
        lines.append(s)

    L("# Phase 3: 四模型组合对比报告")
    L()
    L(f"**生成日期**: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    L(f"**评估方法**: TimeSeriesSplit {CONFIG['n_splits']}折, LogisticRegression (class_weight='balanced')")
    L()
    L("---")
    L()

    # 1. 模型效果对比表
    L("## 1. 模型效果对比")
    L()
    L("| 模型 | AUC-ROC | AUC-PR | F2-Score | Top20%命中率 | 校准误差 | 综合得分 | 排名 |")
    L("|------|---------|--------|----------|------------|---------|---------|------|")

    metrics_table = []
    for key, res in all_results.items():
        s = res['summary']
        auc = s.get('auc_roc', np.nan)
        apr = s.get('auc_pr', np.nan)
        f2 = s.get('f2_score', np.nan)
        top20 = s.get('top20_hit_rate', np.nan)
        calib = s.get('calibration_intercept', np.nan)
        composite = s.get('composite_score', np.nan)
        auc_str = f"{auc:.4f}"
        apr_str = f"{apr:.4f}" if not np.isnan(apr) else "N/A"
        f2_str = f"{f2:.4f}" if not np.isnan(f2) else "N/A"
        top20_str = f"{top20:.1%}" if not np.isnan(top20) else "N/A"
        calib_str = f"{calib:+.4f}" if not np.isnan(calib) else "N/A"
        comp_str = f"{composite:.4f}" if not np.isnan(composite) else "N/A"
        metrics_table.append({
            'key': key,
            'display': res['info']['display'],
            'auc_roc': auc,
            'auc_pr': apr,
            'f2': f2,
            'top20': top20,
            'calib': calib,
            'composite': composite,
            'auc_str': auc_str,
            'apr_str': apr_str,
            'f2_str': f2_str,
            'top20_str': top20_str,
            'calib_str': calib_str,
            'comp_str': comp_str,
        })

    # 按 AUC 排序
    metrics_table.sort(key=lambda x: -x['auc_roc'] if not np.isnan(x['auc_roc']) else -1)
    for rank, m in enumerate(metrics_table):
        L(f"| {m['display']} | {m['auc_str']} | {m['apr_str']} | {m['f2_str']} | {m['top20_str']} | {m['calib_str']} | {m['comp_str']} | #{rank+1} |")

    best_model = metrics_table[0]
    L()
    L(f"**最优模型**: **{best_model['display']}** (AUC-ROC={best_model['auc_str']}, 综合得分={best_model['comp_str']})")
    L()

    # 2. AUC 提升明细
    L("## 2. AUC 提升路径分析")
    L()
    L("| 对比 | 模型A | 模型B | AUC提升 | 提升幅度 | 效果 |")
    L("|------|-------|-------|--------|---------|------|")

    m0_auc = next((m['auc_roc'] for m in metrics_table if 'M0' in m['key']), np.nan)
    for m in metrics_table:
        if 'M0' in m['key']:
            continue
        key_b = m['key']
        auc_b = m['auc_roc']
        if not np.isnan(m0_auc) and not np.isnan(auc_b):
            improvement = auc_b - m0_auc
            pct = improvement / m0_auc * 100
            tag = "[OK]" if improvement > 0 else "[NO]"
            note = "显著提升" if pct > 2 else ("略有提升" if pct > 0 else "无提升")
            m0_name = next((x['display'] for x in metrics_table if 'M0' in x['key']), 'M0')
            L(f"| F1修复效果 | {m0_name} | {m['display']} | {improvement:+.4f} | {pct:+.2f}% | {note} {tag} |")

    # 交叉对比 (M0 vs M1 vs M2 vs M3)
    if len(metrics_table) >= 2:
        L()
        L("### 各增强路径效果")
        L()
        for m in metrics_table:
            if 'M0' in m['key']:
                L(f"- **{m['display']} (基线)**: AUC={m['auc_str']}")
            elif 'M1' in m['key']:
                imp = m['auc_roc'] - m0_auc if not np.isnan(m['auc_roc']) and not np.isnan(m0_auc) else 0
                L(f"- **{m['display']}**: AUC={m['auc_str']} (vs 基线 {imp:+.4f})")
            elif 'M2' in m['key']:
                imp = m['auc_roc'] - m0_auc if not np.isnan(m['auc_roc']) and not np.isnan(m0_auc) else 0
                L(f"- **{m['display']}**: AUC={m['auc_str']} (vs 基线 {imp:+.4f})")
            elif 'M3' in m['key']:
                imp_m1 = m['auc_roc'] - next((x['auc_roc'] for x in metrics_table if 'M1' in x['key']), np.nan)
                imp_m2 = m['auc_roc'] - next((x['auc_roc'] for x in metrics_table if 'M2' in x['key']), np.nan)
                L(f"- **{m['display']}**: AUC={m['auc_str']} (vs M1 {imp_m1:+.4f}, vs M2 {imp_m2:+.4f})")
    L()

    # 3. 特征重要性
    L("## 3. 特征重要性分析")
    L()
    for key, res in all_results.items():
        if 'coef_mean' not in res['summary']:
            continue
        coef_mean = res['summary']['coef_mean']
        coef_std = res['summary'].get('coef_std', {})
        features_sorted = sorted(coef_mean.keys(), key=lambda x: abs(coef_mean[x]), reverse=True)

        L(f"### {res['info']['display']}")
        L()
        L("| 特征 | 标准化系数 | 标准差 | 影响方向 | 重要性排名 |")
        L("|------|-----------|-------|---------|----------|")
        for rank_f, fname in enumerate(features_sorted):
            val = coef_mean[fname]
            std = coef_std.get(fname, 0)
            direction = "正向(风险↑)" if val > 0 else "负向(风险↓)"
            L(f"| {fname} | {val:+.4f} | {std:.4f} | {direction} | #{rank_f+1} |")
        L()

    # 4. 各折稳定性
    L("## 4. 跨折稳定性分析")
    L()
    L("| 模型 | AUC均值 | AUC标准差 | 变异系数(CV) | 系数稳定性CV |")
    L("|------|---------|----------|-------------|-------------|")
    for m in metrics_table:
        key = m['key']
        res = all_results[key]
        s = res['summary']
        auc_std = s.get('auc_roc_std', np.nan)
        auc_mean = s.get('auc_roc', np.nan)
        cv = auc_std / auc_mean if (not np.isnan(auc_std) and not np.isnan(auc_mean) and auc_mean > 0) else np.nan
        coef_cv = s.get('coef_stability_cv', np.nan)
        cv_str = f"{cv:.4f}" if not np.isnan(cv) else "N/A"
        coef_cv_str = f"{coef_cv:.4f}" if not np.isnan(coef_cv) else "N/A"
        L(f"| {m['display']} | {m['auc_str']} | {auc_std:.4f} | {cv_str} | {coef_cv_str} |")
    L()

    # 5. 结论与建议
    L("## 5. 结论与建议")
    L()

    # 对比最佳 vs 基线
    best_name = best_model['display']
    best_auc = best_model['auc_roc']
    m0_auc_val = next((m['auc_roc'] for m in metrics_table if 'M0' in m['key']), np.nan)
    improvement = best_auc - m0_auc_val if not np.isnan(best_auc) and not np.isnan(m0_auc_val) else 0
    improvement_pct = improvement / m0_auc_val * 100 if not np.isnan(m0_auc_val) and m0_auc_val > 0 else 0

    if improvement_pct >= 5:
        L(f"**推荐模型**: **{best_name}**")
        L(f"- 相比 M0 基线，AUC 提升 {improvement_pct:.1f}% ({improvement:+.4f})")
    else:
        L(f"**模型选择建议**：各模型差异不大（最大差距 < 5%），建议综合考虑计算成本和可解释性。")
        L(f"- 若追求最高 AUC: **{best_name}** (AUC={best_auc:.4f})")
        L(f"- 若追求简洁: M0 基线已足够 (AUC={m0_auc_val:.4f})")

    L()
    if not np.isnan(m0_auc_val):
        L(f"- **M0 (基线)**: AUC={m0_auc_val:.4f} — 原始模型基准")
    for m in metrics_table:
        if m['key'] == 'M0':
            continue
        imp = m['auc_roc'] - m0_auc_val if not np.isnan(m['auc_roc']) and not np.isnan(m0_auc_val) else 0
        imp_str = f"{imp:+.4f}" if not np.isnan(imp) else "N/A"
        L(f"- **{m['display']}**: AUC={m['auc_str']} (vs 基线 {imp_str})")

    L()
    L("### 特征价值判断")
    L()
    L("| 特征 | 影响力 | 说明 |")
    L("|------|-------|------|")

    # 从 M3 看特征重要性
    if 'M3_双轨' in all_results and 'coef_mean' in all_results['M3_双轨']['summary']:
        coef_m3 = all_results['M3_双轨']['summary']['coef_mean']
        for f, v in sorted(coef_m3.items(), key=lambda x: -abs(x[1])):
            direction = "[OK]正向贡献" if v > 0 else "[NO]负向(需反转)"
            if f == 'f1f_6m_gp_amount':
                L(f"| F1f (毛利额斜率) | {v:+.4f} | 毛利额下降 → 风险上升 {direction} |")
            elif f == 'f1_score':
                L(f"| F1 (毛利率斜率) | {v:+.4f} | 原始毛利率趋势因子 {direction} |")
            elif f == 'c6_order_qty_change':
                L(f"| c6 (单次订货量衰减) | {v:+.4f} | 客户订货量萎缩 → 风险上升 {direction} |")
            elif f == 'f3_score':
                L(f"| F3 (订货波动) | {v:+.4f} | CV高 → 风险信号 {direction} |")
            elif f == 'f4_score':
                L(f"| F4 (增速衰减) | {v:+.4f} | 连续下降月数 {direction} |")
            elif f == 'f5_score':
                L(f"| F5 (自比健康度) | {v:+.4f} | 自比健康度下降 {direction} |")
            elif f == 'f6_score':
                L(f"| F6 (ASP趋势) | {v:+.4f} | 价格趋势 {direction} |")
            else:
                L(f"| {f} | {v:+.4f} | {direction} |")

    L()
    L("### 下阶段建议")
    L()
    L("1. **Phase 4 (案例回检)**: 对10个产品 (5个成功预警, 5个漏报/误报) 进行人工复盘")
    L("2. **Phase 5 (业务行动基线)**: 从历史数据中提取衰退前的业务行动模式")
    L()

    # 保存报告
    report_path = os.path.join(CONFIG['output_dir'], 'phase3_report.md')
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print(f"报告已写入: {report_path}")

    # 保存详细结果 CSV
    results_data = []
    for key, res in all_results.items():
        row = {'model': res['info']['display']}
        for k, v in res['summary'].items():
            if isinstance(v, dict):
                continue
            row[k] = v
        results_data.append(row)
    results_df = pd.DataFrame(results_data)
    csv_path = os.path.join(CONFIG['output_dir'], 'phase3_model_comparison.csv')
    results_df.to_csv(csv_path, index=False, encoding='utf-8-sig')
    print(f"详细结果已保存: {csv_path}")

    return report_path


def main():
    # 1. 加载数据
    df = load_data()

    # 2. 评估4个模型
    all_results = evaluate_all_models(df)

    # 3. 可视化
    plot_roc_curves(all_results)
    plot_feature_importance(all_results)

    # 4. 报告
    report_path = generate_report(all_results)

    # 5. 找最优
    best_key = max(all_results, key=lambda k: all_results[k]['summary'].get('composite_score',
                                              all_results[k]['summary'].get('auc_roc', 0)))
    best_auc = all_results[best_key]['summary'].get('auc_roc', np.nan)
    print(f"\nPhase 3 完成! 最优模型: {MODELS[best_key]['display']} (AUC={best_auc:.4f})")
    return 0


if __name__ == '__main__':
    sys.exit(main())
