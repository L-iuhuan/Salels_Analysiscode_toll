# -*- coding: utf-8 -*-
"""
Phase 2: F1 毛利率趋势因子修复
================================
测试 F1 的 6 种变体，找出单因子 AUC 最高的版本。

用法:
    python recession_risk_opt/phase2_f1_repair.py

输出:
    test_output/phase2_f1_comparison.csv  — 各变体每折AUC
    test_output/phase2_f1_boxplot.png     — 衰退前毛利率轨迹箱线图
    test_output/phase2_report.md          — 因子修复报告
"""
import os, sys, warnings
from datetime import datetime
import numpy as np
import pandas as pd

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
os.chdir(PROJECT_ROOT)

from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import roc_auc_score
from scipy import stats
from scipy.optimize import curve_fit
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
# 中文字体配置
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DengXian', 'Noto Sans SC']
plt.rcParams['axes.unicode_minus'] = False
plt.rcParams['font.family'] = 'sans-serif'
import matplotlib.ticker as mticker
import seaborn as sns
sns.set_theme(style='whitegrid', font='SimHei', rc={
    'font.sans-serif': ['SimHei', 'Microsoft YaHei', 'DengXian', 'Noto Sans SC'],
    'axes.unicode_minus': False,
})

warnings.filterwarnings('ignore')
np.random.seed(42)

CONFIG = {
    'samples_path': 'recession_risk_opt/data/samples.pkl',
    'data_path': 'data/所有的出货明细5.9.xlsx',
    'output_dir': 'test_output',
    'n_splits': 5,
    'forward_months': 6,
}

DECLINE_PORTRAITS = {"衰退期", "夕阳产品", "隐性衰退"}


def load_data():
    """加载 samples.pkl 和源数据"""
    print("=" * 60)
    print("Phase 2: 数据加载")
    print("=" * 60)

    sp = pd.read_pickle(CONFIG['samples_path'])
    print(f"samples.pkl: {sp.shape}, 产品: {sp['product_id'].nunique()}")

    # 标签构建
    df = sp.sort_values(['product_id', 'date_month']).copy()
    y_6m = []
    for prod, grp in df.groupby('product_id'):
        grp = grp.sort_values('date_month')
        portraits = grp['portrait'].values
        margins = grp['recent_margin'].values
        growths = grp['growth_rate'].values
        n = len(grp)
        for i in range(n):
            fs = i + 1
            fe = min(i + 7, n)
            if fs >= fe:
                y_6m.append(int(grp['y'].iloc[i]))
                continue
            # Bug 3修复: 收紧为连续3月条件
            fp = portraits[fs:fe]
            fm = margins[fs:fe]
            fg = growths[fs:fe]
            # 条件1：连续3月落入衰退九宫格
            if len(fp) >= 3:
                decline_bits = [1 if p in DECLINE_PORTRAITS else 0 for p in fp]
                in_decline_3m = any(sum(decline_bits[j:j+3]) == 3 for j in range(len(decline_bits) - 2))
            else:
                in_decline_3m = False
            # 条件2：连续3月毛利率≤0 且 销量萎缩>20%
            if len(fm) >= 3 and len(fg) >= 3:
                bad_bits = [1 if (m <= 0 and g < -0.2) else 0 for m, g in zip(fm, fg)]
                margin_bad_3m = any(sum(bad_bits[j:j+3]) == 3 for j in range(len(bad_bits) - 2))
            else:
                margin_bad_3m = False
            y_6m.append(1 if (in_decline_3m or margin_bad_3m) else 0)
    df['y_decline_6m'] = y_6m
    pos_rate = df['y_decline_6m'].mean()
    print(f"衰退率: {pos_rate*100:.1f}% ({df['y_decline_6m'].sum()}/{len(df)})")

    return df


def compute_rolling_slope(series, window, method='ols'):
    """
    计算滚动窗口斜率。

    Parameters
    ----------
    series : pd.Series, 索引为月份数值
    window : int, 窗口大小
    method : str, 'ols' | 'exp' | 'yoy' | 'second_deriv'

    Returns
    -------
    slope at the last point
    """
    vals = series.dropna().values
    if len(vals) < 3:
        return np.nan

    x = np.arange(len(vals))

    if method == 'ols':
        # 普通最小二乘
        if len(vals) < 2:
            return np.nan
        slope, _ = np.polyfit(x, vals, 1)
        return slope

    elif method == 'exp':
        # 指数加权最小二乘（半衰期3月 = alpha=1-0.5^(1/3)=~0.206）
        if len(vals) < 2:
            return np.nan
        alpha = 1 - 0.5 ** (1/3)  # 半衰期3月的衰减因子
        weights = (1 - alpha) ** np.arange(len(vals))[::-1]
        # 加权最小二乘
        n = len(vals)
        sw = weights.sum()
        sx = (x * weights).sum()
        sy = (vals * weights).sum()
        sxx = (x * x * weights).sum()
        sxy = (x * vals * weights).sum()
        denom = sw * sxx - sx * sx
        if abs(denom) < 1e-10:
            return np.nan
        slope = (sw * sxy - sx * sy) / denom
        return slope

    elif method == 'yoy':
        # 同比斜率：今年 vs 去年同期
        # 需要至少2个同比数据点
        half = window // 2
        if len(vals) < half + 1:
            return np.nan
        current = vals[-half:]
        prior = vals[:half]
        if len(current) != len(prior):
            min_len = min(len(current), len(prior))
            current = current[-min_len:]
            prior = prior[:min_len]
        if len(current) < 2:
            return np.nan
        # 计算差值序列的变化斜率
        diffs = current - prior[:len(current)]
        slope, _ = np.polyfit(np.arange(len(diffs)), diffs, 1)
        return slope

    elif method == 'second_deriv':
        # 二阶导：斜率的变化速度
        if len(vals) < 4:
            return np.nan
        # 先算一阶导的滚动变化
        first_deriv = np.diff(vals)
        if len(first_deriv) < 2:
            return np.nan
        # 二阶导 = diff of first deriv
        second_deriv = np.diff(first_deriv)
        if len(second_deriv) == 0:
            return np.nan
        # 取最近二阶导的均值
        return np.mean(second_deriv[-3:]) if len(second_deriv) >= 3 else np.mean(second_deriv)

    return np.nan


def compute_all_f1_variants(df):
    """
    对每个产品-月份，计算所有6种F1变体。

    使用 recent_margin（月度毛利率）作为基础数据。
    对于 F1f（毛利额斜率），需要从源数据计算。

    注意: samples.pkl 的时间序列可能是不连续的（存在间隔）。
    我们按 date_month 排序后编号作为 x 轴。
    """
    print("\n计算所有F1变体...")

    variants = {
        'f1a_6m_ols': {'window': 6, 'method': 'ols'},
        'f1b_9m_ols': {'window': 9, 'method': 'ols'},
        'f1c_12m_exp': {'window': 12, 'method': 'exp'},
        'f1d_12m_yoy': {'window': 12, 'method': 'yoy'},
        'f1e_12m_2deriv': {'window': 12, 'method': 'second_deriv'},
    }

    results = []
    for prod, grp in df.groupby('product_id'):
        grp = grp.sort_values('date_month').reset_index(drop=True)
        margins = grp['recent_margin'].values
        n = len(grp)

        for i in range(n):
            row = {'product_id': prod, 'date_month': grp['date_month'].iloc[i]}

            for vname, vcfg in variants.items():
                w = vcfg['window']
                start = max(0, i - w + 1)
                window_vals = pd.Series(margins[start:i+1])

                if len(window_vals) >= 3:
                    row[vname] = compute_rolling_slope(window_vals, w, vcfg['method'])
                else:
                    row[vname] = np.nan

            # F1f 将在后面用完整数据计算


            results.append(row)

    fdf = pd.DataFrame(results)
    print(f"F1变体形状: {fdf.shape}")

    for v in variants:
        missing = fdf[v].isna().mean()
        print(f"  {v}: 缺失率 {missing*100:.1f}%")

    return fdf, list(variants.keys())


def compute_f1f_gp_amount_from_samples(df):
    """
    从 samples.pkl 计算 F1f: 毛利额斜率。
    毛利额 ≈ recent_margin × (recent_qty_12m / 12)  (月均估计)
    然后计算 6月 OLS 斜率，归一化。
    """
    print("\n计算 F1f 毛利额斜率 (从 samples.pkl 估计)...")

    # Bug 4修复: 毛利率异常处理 — >100%或<-50%视为缺失
    df_est = df.copy()
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
                if mean_val > 0 and not np.isnan(slope):
                    results.append({
                        'product_id': grp['product_id'].iloc[i],
                        'date_month': grp['date_month'].iloc[i],
                        # Bug 1修复: 取反 — 值越大=风险越高
                        'f1f_6m_gp_amount': -slope / mean_val
                    })
                else:
                    results.append({
                        'product_id': grp['product_id'].iloc[i],
                        'date_month': grp['date_month'].iloc[i],
                        'f1f_6m_gp_amount': np.nan
                    })
            else:
                results.append({
                    'product_id': grp['product_id'].iloc[i],
                    'date_month': grp['date_month'].iloc[i],
                    'f1f_6m_gp_amount': np.nan
                })

    f1f = pd.DataFrame(results)
    print(f"F1f形状: {f1f.shape}")
    print(f"F1f缺失率: {f1f['f1f_6m_gp_amount'].isna().mean()*100:.1f}%")
    return f1f


def load_source_data(product_ids):
    """加载源数据并过滤到目标产品"""
    print("加载源数据计算F1f...")
    use_cols = ['发货日期', '存货名称', '出货总金额', '成本', '利润']
    df = pd.read_excel(CONFIG['data_path'], usecols=use_cols)
    df = df[df['存货名称'].isin(product_ids)].copy()
    df['年月'] = df['发货日期'].dt.to_period('M').astype(str)
    df = df.rename(columns={'存货名称': 'product_id'})
    print(f"  源数据过滤后: {df.shape}")
    return df


def evaluate_variants(df_full, variant_names):
    """TimeSeriesSplit评估每种变体的单因子AUC"""
    print("\n" + "=" * 60)
    print("单因子AUC评估")
    print("=" * 60)

    # 所有F1变体列表（含f1f）
    all_variants = variant_names + ['f1f_6m_gp_amount']

    # 确保列存在（处理可能的后缀）
    for v in all_variants:
        if v not in df_full.columns:
            suffix_col = f'{v}_f1f'
            if suffix_col in df_full.columns:
                df_full[v] = df_full[suffix_col]
                df_full = df_full.drop(columns=[suffix_col])
            else:
                df_full[v] = np.nan

    months = sorted(df_full['date_month'].unique())
    print(f"月份: {len(months)}, {months[0]} ~ {months[-1]}")

    # 标签列
    y_col = 'y_decline_6m'

    tscv = TimeSeriesSplit(n_splits=CONFIG['n_splits'])
    all_fold_results = []

    for fold, (train_idx, val_idx) in enumerate(tscv.split(months)):
        train_months = [months[i] for i in train_idx]
        val_months = [months[i] for i in val_idx]

        val_df = df_full[df_full['date_month'].isin(val_months)]
        y_val = val_df[y_col].values

        fold_result = {'fold': fold + 1}
        for vname in all_variants:
            vals = val_df[vname].values
            valid = ~np.isnan(vals)
            if valid.sum() >= 20 and len(np.unique(y_val[valid])) >= 2:
                try:
                    auc = roc_auc_score(y_val[valid], vals[valid])
                    if auc < 0.5:
                        auc = roc_auc_score(y_val[valid], -vals[valid])
                    fold_result[vname] = auc
                except:
                    fold_result[vname] = np.nan
            else:
                fold_result[vname] = np.nan
        all_fold_results.append(fold_result)

    # 汇总
    summary = {}
    print(f"\n{'变体':25s} {'AUC均值':>8s} {'AUC-std':>8s} {'有效折':>6s}")
    print("-" * 50)
    for vname in all_variants:
        aucs = [r[vname] for r in all_fold_results if not np.isnan(r.get(vname, np.nan))]
        if aucs:
            mean_auc = np.mean(aucs)
            std_auc = np.std(aucs)
            summary[vname] = {'mean_auc': mean_auc, 'std_auc': std_auc, 'n_folds': len(aucs)}
            print(f"{vname:25s} {mean_auc:8.4f} {std_auc:8.4f} {len(aucs):6d}")
        else:
            summary[vname] = {'mean_auc': np.nan, 'std_auc': np.nan, 'n_folds': 0}
            print(f"{vname:25s} {'N/A':>8s} {'N/A':>8s} {0:6d}")

    return summary, all_fold_results


def margin_pre_decline_analysis(df_full):
    """
    衰退前毛利率轨迹分析：
    1. 对已知衰退产品，提取衰退前6个月的毛利率
    2. Mann-Whitney U 检验：衰退前3月/6月 vs 健康期
    3. 输出箱线图
    """
    print("\n" + "=" * 60)
    print("衰退前毛利率分析")
    print("=" * 60)

    y_col = 'y_decline_6m'

    # 找出每个产品首次衰退的时间
    decline_products = {}
    for prod, grp in df_full.groupby('product_id'):
        grp = grp.sort_values('date_month')
        dec_idx = grp[y_col].values.argmax() if grp[y_col].max() == 1 else -1
        if dec_idx >= 6:
            decline_products[prod] = {
                'decline_idx': dec_idx,
                'decline_month': grp['date_month'].iloc[dec_idx],
                'data': grp,
            }

    print(f"有足够历史的衰退产品: {len(decline_products)}")

    # 收集衰退前的毛利率轨迹
    pre_decline_margins = {m: [] for m in range(-6, 1)}  # T-6 到 T
    healthy_margins = []

    for prod, info in decline_products.items():
        data = info['data']
        di = info['decline_idx']

        for offset in range(-6, 1):
            idx = di + offset
            if 0 <= idx < len(data):
                m = data['recent_margin'].iloc[idx]
                if not np.isnan(m):
                    pre_decline_margins[offset].append(m)

        # 健康期：取所有非衰退前6月且不在衰退后的margin
        healthy_mask = data[y_col] == 0
        for idx in range(len(data)):
            if di - 6 <= idx <= di + 6:
                healthy_mask.iloc[idx] = False  # 排除衰退前后6月
        healthy = data.loc[healthy_mask, 'recent_margin'].dropna().values
        healthy_margins.extend(healthy.tolist())

    # Mann-Whitney U 检验
    mw_results = {}
    for offset_name, offset_months in [('T-3', -3), ('T-6', -6)]:
        pre = pre_decline_margins.get(offset_months, [])
        # 用最近2个月的健康margin做对比
        healthy_sample = healthy_margins[-len(pre)*10:] if len(healthy_margins) > len(pre)*10 else healthy_margins

        if len(pre) >= 5 and len(healthy_sample) >= 5:
            stat, p = stats.mannwhitneyu(pre, healthy_sample, alternative='less')
            mw_results[offset_name] = {
                'n_pre': len(pre),
                'n_healthy': len(healthy_sample),
                'median_pre': np.median(pre),
                'median_healthy': np.median(healthy_sample),
                'mean_pre': np.mean(pre),
                'statistic': stat,
                'p_value': p,
                'significant': p < 0.05,
            }
            print(f"\n{offset_name} (衰退前{3 if offset_name=='T-3' else 6}月) vs 健康期:")
            print(f"  衰退前中位数: {np.median(pre):.4f}")
            print(f"  健康期中位数: {np.median(healthy_sample):.4f}")
            tag = "[OK]" if p < 0.05 else "[NO]"
            print(f"  Mann-Whitney U: stat={stat:.2f}, p={p:.4f} {tag}")
        else:
            mw_results[offset_name] = {'error': '样本不足'}

    # 绘制箱线图
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    # 图1: 衰退前毛利率轨迹
    ax = axes[0]
    box_data = [pre_decline_margins[offset] for offset in range(-6, 1)]
    labels = [f'T{offset}' if offset < 0 else 'T' for offset in range(-6, 1)]
    bp = ax.boxplot(box_data, labels=labels, patch_artist=True)
    for patch in bp['boxes']:
        patch.set_facecolor('#e74c3c' if 'T' in patch.get_label() else '#3498db')
    ax.axhline(y=0, color='red', linestyle='--', alpha=0.5)
    ax.set_title('衰退前6个月毛利率轨迹', fontsize=13)
    ax.set_ylabel('毛利率')
    ax.set_xlabel('距衰退月数')

    # 图2: T-3 vs 健康期
    ax = axes[1]
    t3_data = pre_decline_margins.get(-3, [])
    healthy_sample_short = healthy_margins[:len(healthy_margins)]
    bp2 = ax.boxplot([t3_data, healthy_sample_short], labels=['衰退前3月', '健康期'], patch_artist=True)
    for patch, color in zip(bp2['boxes'], ['#e74c3c', '#2ecc71']):
        patch.set_facecolor(color)
    ax.set_title('衰退前3月 vs 健康期 毛利率对比', fontsize=13)
    ax.set_ylabel('毛利率')

    if mw_results.get('T-3', {}).get('p_value', 1) < 0.05:
        p_text = f"Mann-Whitney p={mw_results['T-3']['p_value']:.4f} ✅"
    else:
        p_text = f"Mann-Whitney p={mw_results.get('T-3', {}).get('p_value', 1):.4f} ❌"
    ax.text(0.5, 0.95, p_text, transform=ax.transAxes, ha='center', fontsize=11,
            bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))

    plt.tight_layout()
    path = os.path.join(CONFIG['output_dir'], 'phase2_f1_boxplot.png')
    plt.savefig(path, dpi=150)
    plt.close()
    print(f"\n箱线图已保存: {path}")

    return pre_decline_margins, healthy_margins, mw_results


def generate_report(summary, mw_results, all_fold_results, df_full, output_dir):
    """生成Phase 2报告"""
    print("\n" + "=" * 60)
    print("生成报告")
    print("=" * 60)

    variant_names_full = {
        'f1a_6m_ols': 'F1a 近6月 OLS斜率',
        'f1b_9m_ols': 'F1b 近9月 OLS斜率',
        'f1c_12m_exp': 'F1c 近12月 指数加权',
        'f1d_12m_yoy': 'F1d 近12月 同比斜率',
        'f1e_12m_2deriv': 'F1e 近12月 二阶导',
        'f1f_6m_gp_amount': 'F1f 近6月 毛利额斜率',
    }

    lines = []
    def L(s=""):
        lines.append(s)

    L("# Phase 2 F1 毛利率趋势因子修复报告")
    L()
    L(f"**生成日期**: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    L()
    L("---")
    L()
    L("## 1. F1变体 AUC-ROC 对比")
    L()
    L("| 变体 | AUC均值 | AUC-std | 有效折数 | 排名 |")
    L("|------|--------|--------|---------|------|")

    all_aucs = [(v, summary[v]['mean_auc']) for v in summary
                 if 'mean_auc' in summary[v] and not np.isnan(summary[v]['mean_auc'])]
    all_aucs.sort(key=lambda x: -x[1])

    # 现有的 slope_ratio 作为基准
    existing_slope = 'slope_ratio'
    if existing_slope in df_full.columns:
        months = sorted(df_full['date_month'].unique())
        tscv = TimeSeriesSplit(n_splits=CONFIG['n_splits'])
        existing_aucs = []
        for train_idx, val_idx in tscv.split(months):
            val_df = df_full[df_full['date_month'].isin([months[i] for i in val_idx])]
            vals = val_df[existing_slope].values
            y_val = val_df['y_decline_6m'].values
            valid = ~np.isnan(vals)
            if valid.sum() >= 20 and len(np.unique(y_val[valid])) >= 2:
                try:
                    auc = roc_auc_score(y_val[valid], vals[valid])
                    if auc < 0.5:
                        auc = roc_auc_score(y_val[valid], -vals[valid])
                    existing_aucs.append(auc)
                except:
                    pass
        existing_mean = np.mean(existing_aucs) if existing_aucs else np.nan
    else:
        existing_mean = 0.5624  # 从Phase 0约值

    L(f"| 原F1(12月OLS) | {existing_mean:.4f} | — | — | 基准线 |")

    for rank, (vname, auc) in enumerate(all_aucs):
        if np.isnan(auc):
            continue
        s = summary[vname]
        name = variant_names_full.get(vname, vname)
        L(f"| {name} | {auc:.4f} | {s['std_auc']:.4f} | {s['n_folds']} | #{rank+1} |")
    L()

    best_variant = all_aucs[0][0] if all_aucs else None
    best_auc = all_aucs[0][1] if all_aucs else np.nan
    best_name = variant_names_full.get(best_variant, best_variant) if best_variant else 'N/A'

    L(f"**最优变体**: {best_name} (AUC={best_auc:.4f})")
    if best_auc >= 0.58:
        L("**判定**: ✅ AUC > 0.58，通过")
    else:
        L("**判定**: ❌ AUC < 0.58，未通过")
    L()

    # Mann-Whitney 检验结果
    L("## 2. 衰退前毛利率统计检验")
    L()
    L("| 对比组 | 衰退前中位数 | 健康期中位数 | Mann-Whitney p | 显著? |")
    L("|-------|------------|------------|---------------|------|")
    for offset_name in ['T-3', 'T-6']:
        mw = mw_results.get(offset_name, {})
        if 'error' in mw:
            L(f"| {offset_name} | — | — | {mw['error']} | — |")
        else:
            sig = "✅" if mw.get('significant') else "❌"
            L(f"| {offset_name} | {mw.get('median_pre', 0):.4f} | {mw.get('median_healthy', 0):.4f} | {mw.get('p_value', 1):.6f} | {sig} |")
    L()

    # 结论
    L("## 3. 结论与建议")
    L()

    if best_auc >= 0.58 or any(mw_results.get(k, {}).get('significant', False) for k in ['T-3', 'T-6']):
        L("**F1修复结论**: ✅ 至少一项通过标准达到，可以采用最优变体替换原有F1。")
    else:
        L("**F1修复结论**: ❌ 所有变体AUC<0.58且Mann-Whitney不显著，建议用c6客户指标或毛利额趋势替代F1核心地位。")
    L()
    L(f"- 推荐变体: **{best_name}** (AUC={best_auc:.4f})")
    L("- 改进方向: 比原F1(12月OLS) AUC提升 {:.2f}%".format(
        (best_auc - existing_mean) / existing_mean * 100 if existing_mean > 0 else 0))
    L()
    L("---")
    L()
    L("## 4. 可视化图表")
    L()
    L("![衰退前毛利率箱线图](phase2_f1_boxplot.png)")

    report_path = os.path.join(output_dir, 'phase2_report.md')
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print(f"报告已写入: {report_path}")
    return report_path, best_variant, best_auc


def main():
    output_dir = CONFIG['output_dir']
    os.makedirs(output_dir, exist_ok=True)

    # 1. 加载数据
    df = load_data()
    product_ids = set(df['product_id'].unique())

    # 2. 计算F1a~F1e from samples.pkl margin data
    fdf, variant_names = compute_all_f1_variants(df)

    # 3. 计算F1f from samples.pkl estimates
    f1f = compute_f1f_gp_amount_from_samples(df)

    # 4. 合并所有变体
    df_full = df.merge(fdf, on=['product_id', 'date_month'], how='left')
    df_full = df_full.merge(f1f, on=['product_id', 'date_month'], how='left')

    # 输出各变体缺失率
    all_variants = variant_names + ['f1f_6m_gp_amount']
    print("\n各变体最终缺失率（在完整数据集上）:")
    for v in all_variants:
        # 处理可能的后缀列名
        col_name = v
        if col_name not in df_full.columns and f'{col_name}_f1f' in df_full.columns:
            col_name = f'{col_name}_f1f'
        if col_name in df_full.columns:
            missing = df_full[col_name].isna().mean()
            print(f"  {v}: {missing*100:.1f}%")
        else:
            print(f"  {v}: 列不存在")

    # 5. 评估
    summary, fold_results = evaluate_variants(df_full, variant_names)

    # 6. 衰退前毛利率分析
    pre_data, healthy_data, mw_results = margin_pre_decline_analysis(df_full)

    # 7. 保存比较数据
    summary_df = pd.DataFrame(summary).T
    summary_df.to_csv(os.path.join(output_dir, 'phase2_f1_comparison.csv'), encoding='utf-8-sig')
    print(f"\n比较数据已保存: {output_dir}/phase2_f1_comparison.csv")

    # 8. 生成报告
    report_path, best_var, best_auc = generate_report(
        summary, mw_results, fold_results, df_full, output_dir)

    print(f"\nPhase 2 完成! 最优变体: {best_var} (AUC={best_auc:.4f})")
    return 0


if __name__ == '__main__':
    sys.exit(main())
