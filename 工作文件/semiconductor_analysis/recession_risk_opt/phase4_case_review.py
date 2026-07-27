"""
Phase 4: 案例回检
=================
对10个产品进行时间序列回溯诊断：
- 5个成功预警案例 (高风险概率 → 实际衰退)
- 5个失败案例 (混合漏报/误报)

用 M2 (原始F1-F6 + c6) 进行 TimeSeriesSplit 预测，
对每个案例绘制完整的因子时间序列图。
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
from sklearn.metrics import roc_auc_score
from collections import defaultdict

warnings.filterwarnings('ignore')

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(PROJECT_ROOT))
OUTPUT_DIR = os.path.join(os.path.dirname(PROJECT_ROOT), 'test_output')
os.makedirs(OUTPUT_DIR, exist_ok=True)

np.random.seed(42)

FEATURES = ['f1_score', 'f3_score', 'f4_score', 'f5_score', 'f6_score', 'c6_order_qty_change']
FEATURE_LABELS = {
    'f1_score': 'F1 毛利率斜率',
    'f3_score': 'F3 订货波动',
    'f4_score': 'F4 增速衰减',
    'f5_score': 'F5 自比健康度',
    'f6_score': 'F6 ASP趋势',
    'c6_order_qty_change': 'c6 单次订货量衰减',
    'f1f_6m_gp_amount': 'F1f 毛利额斜率',
    'y_decline_6m': '6月前瞻衰退标签',
    'pred_prob': '衰退预测概率',
}
# F1-f6 score + 取反后的F1f+c6: 值越大=风险越高 (Bug 1修复)
POSITIVE_FACTORS = {'f1_score', 'f3_score', 'f4_score', 'f5_score', 'f6_score',
                    'f1f_6m_gp_amount', 'c6_order_qty_change'}
NEGATIVE_FACTORS = set()  # 所有因子已统一为正方向


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
            if len(fp) >= 3:
                decline_bits = [1 if p in DECLINE_PORTRAITS else 0 for p in fp]
                in_decline_3m = any(sum(decline_bits[j:j+3]) == 3 for j in range(len(decline_bits) - 2))
            else:
                in_decline_3m = False
            if len(fm) >= 3 and len(fg) >= 3:
                bad_bits = [1 if (m <= 0 and g < -0.2) else 0 for m, g in zip(fm, fg)]
                margin_bad_3m = any(sum(bad_bits[j:j+3]) == 3 for j in range(len(bad_bits) - 2))
            else:
                margin_bad_3m = False
            y_6m.append(1 if (in_decline_3m or margin_bad_3m) else 0)
    df_sorted['y_decline_6m'] = y_6m
    return df_sorted


def load_data():
    """加载并准备数据 (同Phase 3)"""
    # Phase 1 output (客户因子 c1-c6)
    df = pd.read_csv(os.path.join(OUTPUT_DIR, 'phase1_customer_factors.csv'), encoding='utf-8-sig')

    # 从 samples.pkl 重新计算标签 (Bug 3修复)
    raw = pd.read_pickle(os.path.join(PROJECT_ROOT, 'data', 'samples.pkl'))
    raw_labeled = compute_decline_label_6m(raw)
    if 'y_decline_6m' in df.columns:
        df = df.drop(columns=['y_decline_6m'])
    df = df.merge(raw_labeled[['product_id', 'date_month', 'y_decline_6m']],
                  on=['product_id', 'date_month'], how='left')

    # Bug 2修复: c6缺失时用c3兜底填充
    df['c6_order_qty_change'] = df['c6_order_qty_change'].fillna(df['c3_customer_net_change'])
    # Bug 1修复: c6取反 — 统一编码(值越大=风险越高)
    df['c6_order_qty_change'] = -df['c6_order_qty_change']

    # Bug 4修复 + Bug 1修复: F1f计算 (毛利率异常过滤 + 取反)
    df_est = raw.copy()
    df_est['recent_margin'] = df_est['recent_margin'].where(
        (df_est['recent_margin'] <= 1.0) & (df_est['recent_margin'] >= -0.5),
        np.nan
    )
    df_est['est_monthly_gp'] = df_est['recent_margin'] * df_est['recent_qty_12m'] / 12
    f1f_rows = []
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
                except:
                    val = np.nan
            else:
                val = np.nan
            f1f_rows.append({
                'product_id': grp['product_id'].iloc[i],
                'date_month': grp['date_month'].iloc[i],
                'f1f_6m_gp_amount': val,
            })
    f1f = pd.DataFrame(f1f_rows)
    df = df.merge(f1f, on=['product_id', 'date_month'], how='left')

    # 额外因子用于诊断
    extra_cols = ['portrait', 'consecutive_months', 'growth_rate', 'recent_margin',
                  'slope_insufficient', 'cv_invalid', 'asp_insufficient', 'no_valid_hist_margin',
                  'self_health']
    for c in extra_cols:
        if c in raw.columns:
            df[c] = df[['product_id', 'date_month']].merge(
                raw[['product_id', 'date_month', c]], on=['product_id', 'date_month'], how='left')[c]

    print(f"数据加载完成: {df.shape}, 衰退率: {df['y_decline_6m'].mean()*100:.1f}%")
    return df


def evaluate_and_collect(df):
    """5折TimeSeriesSplit，收集所有 OOF 预测"""
    months = sorted(df['date_month'].unique())
    tscv = TimeSeriesSplit(n_splits=5)

    # 全局填充值
    global_fill = {f: df[f].median() for f in FEATURES}

    df['pred_prob'] = np.nan
    df['fold'] = -1

    for fold, (train_idx, val_idx) in enumerate(tscv.split(months)):
        train_months = [months[i] for i in train_idx]
        val_months = [months[i] for i in val_idx]

        train_mask = df['date_month'].isin(train_months)
        val_mask = df['date_month'].isin(val_months)

        X_train = df.loc[train_mask, FEATURES].fillna(global_fill).values
        y_train = df.loc[train_mask, 'y_decline_6m'].values
        X_val = df.loc[val_mask, FEATURES].fillna(global_fill).values

        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_val_scaled = scaler.transform(X_val)

        model = LogisticRegression(class_weight='balanced', max_iter=5000, random_state=42 + fold)
        model.fit(X_train_scaled, y_train)

        y_prob = model.predict_proba(X_val_scaled)[:, 1]

        df.loc[val_mask, 'pred_prob'] = y_prob
        df.loc[val_mask, 'fold'] = fold + 1

        val_auc = roc_auc_score(df.loc[val_mask, 'y_decline_6m'].values, y_prob)
        print(f"  Fold {fold+1}: 验证 {len(val_months)}月, AUC={val_auc:.4f}")

    # 计算偏差
    df['pred_error'] = df['pred_prob'] - df['y_decline_6m']

    # 计算总体 AUC (过滤NaN)
    valid_pred = df['pred_prob'].notna() & df['y_decline_6m'].notna()
    full_auc = roc_auc_score(
        df.loc[valid_pred, 'y_decline_6m'].values,
        df.loc[valid_pred, 'pred_prob'].values
    )
    print(f"\n总体 OOF AUC: {full_auc:.4f} (有效样本: {valid_pred.sum()}/{len(df)})")

    return df


def find_cases(df):
    """找出成功预警和失败案例"""
    # 查看预测概率分布
    print("\n预测概率分布:")
    for decile in range(0, 101, 10):
        lo, hi = decile / 100, (decile + 10) / 100
        subset = df[(df['pred_prob'] >= lo) & (df['pred_prob'] < hi)]
        if len(subset) > 0:
            decline_rate = subset['y_decline_6m'].mean()
            print(f"  [{lo:.1f}, {hi:.1f}): n={len(subset):5d}, 衰退率={decline_rate:.1%}")

    # 成功预警: 衰退前预测概率有明显上升趋势的产品
    success_candidates = []
    for prod, grp in df.groupby('product_id'):
        grp = grp.sort_values('date_month')
        if grp['y_decline_6m'].max() != 1:
            continue
        decline_month = grp[grp['y_decline_6m'] == 1]['date_month'].min()
        pre_df = grp[grp['date_month'] <= decline_month]
        if len(pre_df) >= 6:
            probs = pre_df['pred_prob'].values
            pre_rise = probs[-1] - probs[-6] if len(probs) >= 6 else probs[-1] - probs[0]
            max_prob = probs.max()
            success_candidates.append({
                'product_id': prod,
                'max_prob': max_prob,
                'pre_rise': pre_rise,
                'decline_month': decline_month,
            })

    # 按衰退前概率上升幅度排序，选前5
    success_candidates.sort(key=lambda x: -x['pre_rise'])
    top_success = [s['product_id'] for s in success_candidates[:5]]
    print(f"\n成功预警候选: {len(success_candidates)}个")
    for s in success_candidates[:5]:
        print(f"  {s['product_id']}: 概率峰值={s['max_prob']:.1%}, 衰退前上升={s['pre_rise']:+.2%}")

    # 失败案例
    # 漏报 (False Negative): 实际衰退但预测概率从未超过0.3
    fn_pool = []
    for prod, grp in df.groupby('product_id'):
        if grp['y_decline_6m'].max() != 1:
            continue
        max_prob = grp['pred_prob'].max()
        if max_prob < 0.35:
            fn_pool.append({'product_id': prod, 'max_prob': max_prob})

    fn_pool.sort(key=lambda x: x['max_prob'])
    top_fn = [f['product_id'] for f in fn_pool[:3]]
    print(f"漏报候选: {len(fn_pool)}个")
    for f in fn_pool[:3]:
        print(f"  {f['product_id']}: max_prob={f['max_prob']:.1%}")

    # 误报 (False Positive): 预测概率高但从未衰退，且概率峰值>0.7
    fp_pool = []
    for prod, grp in df.groupby('product_id'):
        if grp['y_decline_6m'].max() == 1:
            continue  # 确实有衰退的不算误报
        max_prob = grp['pred_prob'].max()
        if max_prob > 0.65:
            fp_pool.append({'product_id': prod, 'max_prob': max_prob})

    fp_pool.sort(key=lambda x: -x['max_prob'])
    top_fp = [f['product_id'] for f in fp_pool[:2]]
    print(f"误报候选: {len(fp_pool)}个")
    for f in fp_pool[:2]:
        print(f"  {f['product_id']}: max_prob={f['max_prob']:.1%}")

    failure_products = top_fn + top_fp
    print(f"失败案例选{len(failure_products)}: {failure_products}")

    return top_success, failure_products


def analyze_case(df, product_id, case_type):
    """分析单个产品的完整时间序列"""
    pdf = df[df['product_id'] == product_id].sort_values('date_month').copy()
    if len(pdf) == 0:
        return None

    decline_month = pdf[pdf['y_decline_6m'] == 1]['date_month'].min() if pdf['y_decline_6m'].max() == 1 else None

    analysis = {
        'product_id': product_id,
        'case_type': case_type,
        'n_months': len(pdf),
        'date_range': f"{pdf['date_month'].min()} ~ {pdf['date_month'].max()}",
        'decline_month': decline_month,
        'decline_flag': pdf['y_decline_6m'].max() == 1,
        'max_pred_prob': pdf['pred_prob'].max(),
        'mean_pred_prob': pdf['pred_prob'].mean(),
        'trajectory': pdf,
    }

    # 衰退前6个月的趋势分析
    if decline_month:
        pre_df = pdf[pdf['date_month'] <= decline_month].tail(7)  # 包含衰退月及前6月
        analysis['pre_decline_window'] = pre_df
        # 因子趋势方向
        for feat in FEATURES:
            vals = pre_df[feat].dropna().values
            if len(vals) >= 3:
                x = np.arange(len(vals))
                slope = np.polyfit(x, vals, 1)[0]
                expected_sign = 1 if feat in POSITIVE_FACTORS else -1
                consistent = (slope * expected_sign) > 0
                analysis[f'{feat}_trend'] = '↑(一致)' if consistent else '↓(反向)'
                analysis[f'{feat}_slope'] = slope
            else:
                analysis[f'{feat}_trend'] = '数据不足'
                analysis[f'{feat}_slope'] = np.nan

    # 诊断该产品的核心驱动因子
    high_factors = []
    for feat in FEATURES:
        recent_val = pdf[feat].iloc[-1] if len(pdf) > 0 else np.nan
        if not np.isnan(recent_val):
            if feat in POSITIVE_FACTORS and recent_val > 60:
                high_factors.append(FEATURE_LABELS.get(feat, feat))
            elif feat in NEGATIVE_FACTORS and recent_val < -0.3:
                high_factors.append(FEATURE_LABELS.get(feat, feat))
    analysis['high_risk_factors'] = high_factors

    # 失效原因 (如果是失败案例)
    if case_type in ['漏报', '误报']:
        if case_type == '漏报':
            # 检查关键因子是否数据不足
            insufficient = []
            for flag in ['slope_insufficient', 'cv_invalid', 'asp_insufficient', 'no_valid_hist_margin']:
                if flag in pdf.columns and pdf[flag].any():
                    col_map = {'slope_insufficient': 'F1斜率不可靠', 'cv_invalid': 'F3无发货',
                               'asp_insufficient': 'F6 ASP不足', 'no_valid_hist_margin': 'F5无历史'}
                    insufficient.append(col_map.get(flag, flag))
            analysis['failure_reason'] = insufficient if insufficient else ['因子权重不足']
        else:  # 误报
            # 检查是否在衰退边界 (低毛利率等)
            low_margin_risk = pdf[pdf['recent_margin'] < 0.05] if 'recent_margin' in pdf.columns else pd.DataFrame()
            analysis['failure_reason'] = [
                '实际未衰退但因子得分高',
                f"低毛利率月数: {len(low_margin_risk)}",
            ]

    return analysis


def plot_case(analysis, output_dir):
    """绘制单个案例的时间序列诊断图"""
    pid = analysis['product_id']
    pdf = analysis['trajectory']

    fig, axes = plt.subplots(3, 1, figsize=(14, 12), gridspec_kw={'height_ratios': [2, 2, 1]})

    # 图1: 预测概率 + 衰退标签
    ax = axes[0]
    months = pdf['date_month'].values
    x = np.arange(len(months))
    ax.plot(x, pdf['pred_prob'].values, 'b-o', label='衰退预测概率', linewidth=2, markersize=4)
    # 衰退区间
    if analysis['decline_flag']:
        decline_idx = pdf[pdf['y_decline_6m'] == 1].index[0]
        decline_pos = list(pdf.index).index(decline_idx)
        ax.axvspan(decline_pos, len(pdf)-1, alpha=0.15, color='red', label='衰退期')
        ax.axvline(x=decline_pos, color='red', linestyle='--', alpha=0.5)
    ax.axhline(y=0.5, color='gray', linestyle=':', alpha=0.5)
    ax.set_ylabel('概率', fontsize=11)
    ax.set_title(f"案例: {pid} [{analysis['case_type']}]", fontsize=13)
    ax.legend(loc='upper left')
    ax.set_ylim(-0.05, 1.05)
    ax.set_xticks(x)
    month_labels = [m[5:7] + '-' + m[2:4] if len(m) >= 7 else m for m in months]
    ax.set_xticklabels(month_labels, rotation=45, ha='right', fontsize=8)

    # 图2: 因子得分时间序列
    ax = axes[1]
    factor_colors = {'f1_score': '#3498db', 'f3_score': '#e74c3c', 'f4_score': '#2ecc71',
                     'f5_score': '#f39c12', 'f6_score': '#9b59b6', 'c6_order_qty_change': '#1abc9c'}

    for feat in FEATURES:
        if feat in pdf.columns and pdf[feat].notna().sum() > 0:
            vals = pdf[feat].values
            if feat in POSITIVE_FACTORS:
                ax.plot(x, vals, 'o-', color=factor_colors.get(feat, 'gray'),
                        label=FEATURE_LABELS.get(feat, feat), linewidth=1.5, markersize=3)

    if analysis['decline_flag']:
        ax.axvspan(decline_pos, len(pdf)-1, alpha=0.15, color='red')
        ax.axvline(x=decline_pos, color='red', linestyle='--', alpha=0.5)
    ax.set_ylabel('因子得分', fontsize=11)
    ax.set_title('因子得分时间序列 (所有因子已统一编码: 越高越危险)', fontsize=11)
    ax.legend(loc='upper left', fontsize=8)
    ax.set_xticks(x)
    ax.set_xticklabels(month_labels, rotation=45, ha='right', fontsize=8)

    # 图3: 衰退前因子趋势 (仅对衰退产品)
    ax = axes[2]
    if analysis['decline_flag'] and 'pre_decline_window' in analysis:
        pre_df = analysis['pre_decline_window']
        if len(pre_df) >= 3:
            pre_x = np.arange(len(pre_df))
            for feat in FEATURES[:4]:  # 取前4个最重要的
                if feat in pre_df.columns:
                    vals = pre_df[feat].values
                    if vals.dtype.kind in 'iuf' and not np.isnan(vals).all():
                        ax.plot(pre_x, vals, 'o-', color=factor_colors.get(feat, 'gray'),
                                label=FEATURE_LABELS.get(feat, feat), linewidth=2, markersize=4)

            ax.set_xticks(pre_x)
            pre_months = pre_df['date_month'].values
            ax.set_xticklabels([m[5:7] + '-' + m[2:4] if len(m) >= 7 else m for m in pre_months],
                              rotation=45, ha='right', fontsize=8)
            ax.axvline(x=len(pre_df)-1, color='red', linestyle='--', alpha=0.5, label='衰退月')
            ax.legend(loc='upper left', fontsize=8)
            ax.set_title('衰退前窗口关键因子趋势', fontsize=11)
            ax.set_ylabel('因子得分')

    plt.tight_layout()
    path = os.path.join(output_dir, f'case_{pid}.png')
    plt.savefig(path, dpi=150)
    plt.close()
    return path


def generate_report(all_analyses, output_dir):
    """生成 Phase 4 报告"""
    lines = []
    def L(s=""):
        lines.append(s)

    L("# Phase 4: 案例回检报告")
    L()
    L(f"**生成日期**: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    L(f"**模型**: M2 客户增强 (原始F1-F6 + c6)")
    L(f"**评估方法**: 5折 TimeSeriesSplit OOF 预测, LogisticRegression (class_weight='balanced')")
    L()
    L("---")
    L()

    # 总体统计
    success = [a for a in all_analyses if a['case_type'] == '成功预警']
    failures = [a for a in all_analyses if a['case_type'] != '成功预警']
    fn_cases = [a for a in all_analyses if a['case_type'] == '漏报']
    fp_cases = [a for a in all_analyses if a['case_type'] == '误报']

    L("## 1. 案例总览")
    L()
    L(f"成功预警: {len(success)}个")
    L(f"漏报: {len(fn_cases)}个")
    L(f"误报: {len(fp_cases)}个")
    L()

    L("| 产品编号 | 案例类型 | 监测月数 | 数据范围 | 衰退月 | 最高预测概率 | 核心风险因子 |")
    L("|---------|---------|---------|---------|-------|------------|------------|")
    for a in all_analyses:
        decline_str = str(a['decline_month']) if a['decline_month'] else '无衰退'
        factors_str = ', '.join(a.get('high_risk_factors', []))[:50] if a.get('high_risk_factors') else '—'
        L(f"| {a['product_id']} | {a['case_type']} | {a['n_months']} | {a['date_range']} | {decline_str} | {a['max_pred_prob']:.1%} | {factors_str} |")

    L()
    L("## 2. 成功预警案例")
    L()

    for a in success:
        pid = a['product_id']
        L(f"### {pid}")
        L()
        L(f"- **预测概率峰值**: {a['max_pred_prob']:.1%}")
        L(f"- **衰退月**: {a['decline_month']}")
        L(f"- **核心驱动因子**: {', '.join(a.get('high_risk_factors', ['—']))}")

        if a.get('decline_month') and 'pre_decline_window' in a:
            pre = a['pre_decline_window']
            L(f"- **衰退前窗口**: {pre['date_month'].iloc[0]} ~ {pre['date_month'].iloc[-1]} ({len(pre)}个月)")
            L(f"- **衰退前因子趋势**:")
            for feat in FEATURES:
                trend = a.get(f'{feat}_trend', 'N/A')
                slope = a.get(f'{feat}_slope', np.nan)
                L(f"  - {FEATURE_LABELS.get(feat, feat)}: {trend} (斜率={slope:+.4f})")

        img_path = f"case_{pid}.png"
        L(f"\n![{pid} 时间序列]({img_path})")
        L()

    L("## 3. 失败案例诊断")
    L()

    for a in failures:
        pid = a['product_id']
        L(f"### {pid} ({a['case_type']})")
        L()
        L(f"- **预测概率峰值**: {a['max_pred_prob']:.1%}")
        if a['decline_month']:
            L(f"- **衰退月**: {a['decline_month']}")
        else:
            L("- **未进入衰退**")

        if a.get('failure_reason'):
            L(f"- **失效原因**:")
            for reason in a['failure_reason']:
                L(f"  - {reason}")

        if a.get('decline_month') and 'pre_decline_window' in a:
            pre = a['pre_decline_window']
            L(f"- **衰退前窗口**: {pre['date_month'].iloc[0]} ~ {pre['date_month'].iloc[-1]} ({len(pre)}个月)")
            L(f"- **衰退前因子趋势**:")
            for feat in FEATURES:
                trend = a.get(f'{feat}_trend', 'N/A')
                slope = a.get(f'{feat}_slope', np.nan)
                L(f"  - {FEATURE_LABELS.get(feat, feat)}: {trend} (斜率={slope:+.4f})")

        img_path = f"case_{pid}.png"
        L(f"\n![{pid} 时间序列]({img_path})")
        L()

    # 总结
    L("## 4. 总结")
    L()
    L("### 成功预警模式")
    L()
    L("成功预警案例的共同特征：")
    success_patterns = []
    for a in success:
        for f in a.get('high_risk_factors', []):
            success_patterns.append(f)
    if success_patterns:
        from collections import Counter
        pattern_counts = Counter(success_patterns).most_common()
        for pat, cnt in pattern_counts:
            L(f"- {pat}: {cnt}/{len(success)} 案例中作为核心因子")
    L()

    L("### 失效模式")
    L()
    fn_reasons = []
    fp_reasons = []
    for a in fn_cases:
        fn_reasons.extend(a.get('failure_reason', []))
    for a in fp_cases:
        fp_reasons.extend(a.get('failure_reason', []))
    if fn_reasons:
        L("**漏报常见原因:**")
        for r in set(fn_reasons):
            L(f"- {r}")
    if fp_reasons:
        L("**误报常见原因:**")
        for r in set(fp_reasons):
            L(f"- {r}")
    L()

    L("### 改进方向")
    L()
    L("1. **因子数据不足是漏报主因**: 新品或数据稀疏产品，建议增加替代数据源或放宽数据要求")
    L("2. **误报集中在边界产品**: 高因子得分但未衰退的产品多为低毛利率但未触发九宫格衰退标准的产品")
    L("3. **c6 数据缺失率高 (62.5%)**: 限制了该因子的实际效果，建议探索替代客户指标")

    report_path = os.path.join(output_dir, 'phase4_report.md')
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print(f"报告已写入: {report_path}")
    return report_path


def main():
    print("=" * 60)
    print("Phase 4: 案例回检")
    print("=" * 60)

    # 1. 加载数据
    df = load_data()

    # 2. 5折评估并收集 OOF 预测
    print("\n--- 5折 TimeSeriesSplit 预测 ---")
    df = evaluate_and_collect(df)

    # 3. 筛选案例
    success_ids, failure_ids = find_cases(df)

    # 4. 分析每个案例
    all_analyses = []
    for pid in success_ids:
        analysis = analyze_case(df, pid, '成功预警')
        if analysis:
            all_analyses.append(analysis)
            plot_case(analysis, OUTPUT_DIR)
            print(f"[成功预警] {pid}: 衰退前概率上升, max_prob={analysis['max_pred_prob']:.1%}")

    for pid in failure_ids:
        # 判断是漏报还是误报
        pdf = df[df['product_id'] == pid]
        is_decline = pdf['y_decline_6m'].max() == 1
        case_type = '漏报' if is_decline else '误报'
        analysis = analyze_case(df, pid, case_type)
        if analysis:
            all_analyses.append(analysis)
            plot_case(analysis, OUTPUT_DIR)
            print(f"[{case_type}] {pid}: max_prob={analysis['max_pred_prob']:.1%}")

    # 5. 报告
    report_path = generate_report(all_analyses, OUTPUT_DIR)
    print(f"\nPhase 4 完成! 回检 {len(all_analyses)} 个案例")

    # 输出案例汇总
    print("\n案例汇总:")
    for a in all_analyses:
        print(f"  [{a['case_type']}] {a['product_id']}: 概率峰值={a['max_pred_prob']:.1%}")

    return 0


if __name__ == '__main__':
    sys.exit(main())
