# -*- coding: utf-8 -*-
"""
Phase 1: 客户维度单因子测试
================================
计算c1~c6客户指标，评估单因子AUC-ROC、相关性、预警提前期。

用法:
    python recession_risk_opt/phase1_customer_factors.py

输出:
    test_output/phase1_customer_factors.csv  — 每产品每月的客户指标
    test_output/phase1_report.md            — 单因子评估报告
"""
import os, sys, json, warnings, argparse
from datetime import datetime
import numpy as np
import pandas as pd

# ── 路径 ──
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
os.chdir(PROJECT_ROOT)  # 确保相对路径正确

from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import roc_auc_score
from scipy import stats
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
# 中文字体配置 (SimHei排首位-最可靠的中文全字集字体)
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

# ── 配置 ──
CONFIG = {
    'data_path': 'data/所有的出货明细5.9.xlsx',
    'samples_path': 'recession_risk_opt/data/samples.pkl',
    'output_dir': 'test_output',
    'n_splits': 5,
    'forward_months': 6,
    'window_months': 6,  # 滚动窗口
    'top_n_customer': 5,  # Top N 客户数
    'min_customer_obs': 3,  # 最少客户观测数
}

# 衰退画像
DECLINE_PORTRAITS = {"衰退期", "夕阳产品", "隐性衰退"}


def load_data():
    """加载源数据和samples.pkl"""
    print("=" * 60)
    print("Phase 1: 数据加载")
    print("=" * 60)

    # 1. 加载samples.pkl（已有标签和因子）
    print(f"加载 samples.pkl: {CONFIG['samples_path']}")
    sp = pd.read_pickle(CONFIG['samples_path'])
    print(f"  形状: {sp.shape}, 产品: {sp['product_id'].nunique()}, 月份: {sp['date_month'].nunique()}")

    # 获取627个产品的列表（存货名称/型号名称）
    product_ids = set(sp['product_id'].unique())
    print(f"  产品列表: {len(product_ids)} 个")
    print(f"  示例: {sorted(list(product_ids))[:5]}")

    # 2. 加载源Excel（订单行数据）
    print(f"加载源数据: {CONFIG['data_path']}")
    # 只读需要的列以节省内存
    # 注意：源Excel中【存货名称】对应 samples.pkl 中的 product_id（产品型号名称）
    use_cols = ['发货日期', '客户订单号', '客户', '存货名称', '发货数量',
                '出货总金额', '利润', '单位成本', '未税单价']
    df = pd.read_excel(CONFIG['data_path'], usecols=use_cols)
    print(f"  形状: {df.shape}")

    # 过滤到我们关注的产品（使用存货名称匹配）
    df = df[df['存货名称'].isin(product_ids)].copy()
    print(f"  过滤后: {df.shape} (产品匹配)")

    # 添加月份字段
    df['年月'] = df['发货日期'].dt.to_period('M').astype(str)

    # 添加产品标准化id：直接用存货名称
    df = df.rename(columns={'存货名称': 'product_id'})

    # 3. 加载samples的标签和因子
    label_cols = ['product_id', 'date_month', 'portrait', 'y',
                  'f1_score', 'f3_score', 'f4_score', 'f5_score', 'f6_score',
                  'recent_margin', 'growth_rate']
    labels = sp[label_cols].copy()

    print(f"标签数据: {labels.shape}")
    print(f"  portrait分布:\n{labels['portrait'].value_counts()}")
    print(f"  源数据唯一产品数: {df['product_id'].nunique()}")

    return df, labels, product_ids


def build_labels_6m(labels):
    """构建6个月前瞻衰退标签（与backtest_framework.py一致）"""
    print("\n构建6个月前瞻标签...")
    df = labels.sort_values(['product_id', 'date_month']).copy()

    y_6m = []
    for prod, grp in df.groupby('product_id'):
        grp = grp.sort_values('date_month')
        portraits = grp['portrait'].values
        margins = grp['recent_margin'].values
        growths = grp['growth_rate'].values
        n = len(grp)

        for i in range(n):
            future_start = i + 1
            future_end = min(i + 7, n)
            if future_start >= future_end:
                y_6m.append(int(grp['y'].iloc[i]))
                continue

            future_portraits = portraits[future_start:future_end]
            future_margins = margins[future_start:future_end]
            future_growths = growths[future_start:future_end]

            in_decline = any(p in DECLINE_PORTRAITS for p in future_portraits)
            margin_bad = all(m <= 0 for m in future_margins) if len(future_margins) > 0 else False
            sales_shrink = any(g < -0.2 for g in future_growths) if len(future_growths) > 0 else False

            y_6m.append(1 if (in_decline or (margin_bad and sales_shrink)) else 0)

    df['y_decline_6m'] = y_6m
    pos_rate = df['y_decline_6m'].mean()
    print(f"  正样本(衰退率): {pos_rate*100:.1f}% ({df['y_decline_6m'].sum()}/{len(df)})")
    if 'y' in df.columns:
        overlap = (df['y'] == df['y_decline_6m']).mean()
        print(f"  与原2月标签一致率: {overlap*100:.1f}%")
    return df


def aggregate_customer_data(df):
    """聚合源数据到产品-客户-月级别"""
    print("\n聚合客户数据到产品-客户-月...")

    # 聚合订单行 → 产品-客户-月
    cust_month = df.groupby(['product_id', '客户', '年月']).agg(
        订单行数=('发货数量', 'count'),
        总数量=('发货数量', 'sum'),
        总金额=('出货总金额', 'sum'),
        平均单价=('未税单价', 'mean'),
        平均成本=('单位成本', 'mean'),
        总利润=('利润', 'sum'),
        订单数=('客户订单号', 'nunique'),
    ).reset_index()

    print(f"  产品-客户-月聚合: {cust_month.shape}")
    print(f"  产品数: {cust_month['product_id'].nunique()}")
    print(f"  客户数: {cust_month['客户'].nunique()}")
    print(f"  月份数: {cust_month['年月'].nunique()}")

    return cust_month


def compute_customer_metrics(cust_month, labels):
    """
    计算c1~c6客户指标。
    对每个产品-月份，使用滚动窗口（近6月 vs 前6月）。

    Parameters
    ----------
    cust_month : DataFrame 产品-客户-月级别
    labels : DataFrame 产品-月级别（含标签）

    Returns
    -------
    DataFrame 产品-月级别，含c1~c6指标
    """
    print("\n计算客户指标 c1~c6...")

    all_months = sorted(labels['date_month'].unique())
    w = CONFIG['window_months']

    results = []
    month_list = sorted(cust_month['年月'].unique())

    for prod in sorted(cust_month['product_id'].unique()):
        prod_cust = cust_month[cust_month['product_id'] == prod].copy()
        prod_labels = labels[labels['product_id'] == prod].set_index('date_month')

        for m_idx, curr_month in enumerate(all_months):
            # 获取该月的标签（如果存在）
            if curr_month not in prod_labels.index:
                continue

            # 确定窗口: 近6月 [curr_month - 5, curr_month], 前6月 [curr_month - 11, curr_month - 6]
            curr_dt = pd.Timestamp(curr_month + '-01')
            recent_start = (curr_dt - pd.DateOffset(months=w-1)).strftime('%Y-%m')
            prior_start = (curr_dt - pd.DateOffset(months=w*2-1)).strftime('%Y-%m')
            prior_end = (curr_dt - pd.DateOffset(months=w)).strftime('%Y-%m')

            # 过滤窗口数据
            recent = prod_cust[(prod_cust['年月'] >= recent_start) & (prod_cust['年月'] <= curr_month)]
            prior = prod_cust[(prod_cust['年月'] >= prior_start) & (prod_cust['年月'] <= prior_end)]

            if len(recent) < CONFIG['min_customer_obs']:
                results.append({
                    'product_id': prod, 'date_month': curr_month,
                    'c1_concentration_change': np.nan,
                    'c2_churn_rate': np.nan,
                    'c3_customer_net_change': np.nan,
                    'c4_price_cv': np.nan,
                    'c5_order_interval_change': np.nan,
                    'c6_order_qty_change': np.nan,
                })
                continue

            # --- c1: 客户集中度变化率 ---
            # 近6月 vs 前6月 Top3客户营收占比的变化率
            if len(recent) >= 3:
                recent_top3 = recent.nlargest(3, '总金额')['总金额'].sum()
                recent_total = recent['总金额'].sum()
                recent_concentration = recent_top3 / recent_total if recent_total > 0 else 0

                if len(prior) >= 3:
                    prior_top3 = prior.nlargest(3, '总金额')['总金额'].sum()
                    prior_total = prior['总金额'].sum()
                    prior_concentration = prior_top3 / prior_total if prior_total > 0 else 0
                    c1 = (recent_concentration - prior_concentration) / (prior_concentration + 0.01)
                else:
                    c1 = 0  # 无前6月数据，设为0
            else:
                c1 = np.nan

            # --- c2: 大客户流失率 ---
            # 前6月Top5客户中，近6月未下单客户占比
            if len(prior) >= 2:
                prior_top5 = prior.nlargest(5, '总金额')['客户'].unique()
                recent_customers = set(recent['客户'].unique())
                churned = sum(1 for c in prior_top5 if c not in recent_customers)
                c2 = churned / len(prior_top5)
            else:
                c2 = np.nan

            # --- c3: 活跃客户净变化率 ---
            recent_cust_count = recent['客户'].nunique()
            prior_cust_count = prior['客户'].nunique() if len(prior) > 0 else recent_cust_count
            c3 = (recent_cust_count - prior_cust_count) / (prior_cust_count + 1)

            # --- c4: 价格离散度 (CV of unit prices across customers) ---
            if len(recent) >= 3:
                avg_prices = recent.groupby('客户')['平均单价'].mean()
                if len(avg_prices) >= 2 and avg_prices.mean() > 0:
                    c4 = avg_prices.std() / avg_prices.mean()
                else:
                    c4 = np.nan
            else:
                c4 = np.nan

            # --- c5: 订货周期拉长 ---
            # Top5客户两次下单间隔中位数的变化率
            # 需要订单级别时间 → 使用原始数据
            c5 = np.nan  # 将在第二阶段用原始数据计算

            # --- c6: 单次订货量衰减 ---
            # Top5客户单次平均订货量变化率
            c6 = np.nan  # 将在第二阶段用原始数据计算

            results.append({
                'product_id': prod, 'date_month': curr_month,
                'c1_concentration_change': c1,
                'c2_churn_rate': c2,
                'c3_customer_net_change': c3,
                'c4_price_cv': c4,
            })

    # 转为DataFrame
    cdf = pd.DataFrame(results)
    print(f"  客户指标形状: {cdf.shape}")

    # 合并回标签数据
    merged = labels.merge(cdf, left_on=['product_id', 'date_month'],
                          right_on=['product_id', 'date_month'], how='left')

    # 统计缺失率
    for c in ['c1_concentration_change', 'c2_churn_rate', 'c3_customer_net_change', 'c4_price_cv']:
        missing = merged[c].isna().mean()
        print(f"  {c} 缺失率: {missing*100:.1f}%")

    return merged


def compute_c5_c6_order_metrics(df_raw, cust_month, labels):
    """
    计算c5 (订货周期拉长) 和 c6 (单次订货量衰减)。
    需要订单号+日期级别的粒度 → 从原始数据计算。
    """
    print("\n计算 c5 订货周期 & c6 单次订货量...")

    all_months = sorted(labels['date_month'].unique())
    w = CONFIG['window_months']
    top_n = CONFIG['top_n_customer']

    # 按产品-客户聚合订单级数据
    # 每个订单的日期和总数量
    order_level = df_raw.groupby(['product_id', '客户', '客户订单号', '发货日期']).agg(
        订单总数量=('发货数量', 'sum'),
        订单总金额=('出货总金额', 'sum'),
    ).reset_index()

    results = []

    for prod in sorted(df_raw['product_id'].unique()):
        prod_orders = order_level[order_level['product_id'] == prod].copy()
        prod_orders = prod_orders.sort_values('发货日期')
        prod_orders['年月'] = prod_orders['发货日期'].dt.to_period('M').astype(str)
        prod_labels = labels[labels['product_id'] == prod].set_index('date_month')

        for curr_month in all_months:
            if curr_month not in prod_labels.index:
                continue

            curr_dt = pd.Timestamp(curr_month + '-01')
            recent_start = (curr_dt - pd.DateOffset(months=w-1)).strftime('%Y-%m')
            prior_start = (curr_dt - pd.DateOffset(months=w*2-1)).strftime('%Y-%m')
            prior_end = (curr_dt - pd.DateOffset(months=w)).strftime('%Y-%m')

            recent = prod_orders[(prod_orders['年月'] >= recent_start) &
                                 (prod_orders['年月'] <= curr_month)]
            prior = prod_orders[(prod_orders['年月'] >= prior_start) &
                                (prod_orders['年月'] <= prior_end)]

            c5 = np.nan
            c6 = np.nan

            if len(recent) >= 5 and len(prior) >= 5:
                # Top5客户（按金额）
                recent_top5 = recent.groupby('客户')['订单总金额'].sum().nlargest(top_n).index
                prior_top5 = prior.groupby('客户')['订单总金额'].sum().nlargest(top_n).index

                # c5: 订货周期 - 两单间隔中位数
                def median_interval(cust_orders, cust_name):
                    c_orders = cust_orders[cust_orders['客户'] == cust_name].sort_values('发货日期')
                    if len(c_orders) >= 2:
                        intervals = c_orders['发货日期'].diff().dropna().dt.days
                        return intervals.median() if len(intervals) > 0 else np.nan
                    return np.nan

                recent_intervals = [median_interval(recent, c) for c in recent_top5]
                prior_intervals = [median_interval(prior, c) for c in prior_top5]
                recent_intervals = [i for i in recent_intervals if not np.isnan(i)]
                prior_intervals = [i for i in prior_intervals if not np.isnan(i)]

                if len(recent_intervals) >= 2 and len(prior_intervals) >= 2:
                    recent_median = np.median(recent_intervals)
                    prior_median = np.median(prior_intervals)
                    if prior_median > 0:
                        c5 = (recent_median - prior_median) / prior_median
                    else:
                        c5 = 0

                # c6: 单次订货量
                def avg_order_qty(cust_orders, cust_name):
                    c_orders = cust_orders[cust_orders['客户'] == cust_name]
                    return c_orders['订单总数量'].mean() if len(c_orders) > 0 else np.nan

                recent_qtys = [avg_order_qty(recent, c) for c in recent_top5]
                prior_qtys = [avg_order_qty(prior, c) for c in prior_top5]
                recent_qtys = [q for q in recent_qtys if not np.isnan(q)]
                prior_qtys = [q for q in prior_qtys if not np.isnan(q)]

                if len(recent_qtys) >= 2 and len(prior_qtys) >= 2:
                    recent_mean = np.mean(recent_qtys)
                    prior_mean = np.mean(prior_qtys)
                    if prior_mean > 0:
                        c6 = (recent_mean - prior_mean) / prior_mean
                    else:
                        c6 = 0

            results.append({
                'product_id': prod, 'date_month': curr_month,
                'c5_order_interval_change': c5,
                'c6_order_qty_change': c6,
            })

    c56 = pd.DataFrame(results)
    print(f"  c5/c6 形状: {c56.shape}")
    print(f"  c5 缺失率: {c56['c5_order_interval_change'].isna().mean()*100:.1f}%")
    print(f"  c6 缺失率: {c56['c6_order_qty_change'].isna().mean()*100:.1f}%")

    return c56


def evaluate_single_factor(merged, c56):
    """
    对每个客户指标运行TimeSeriesSplit回测，计算单因子AUC。

    Parameters
    ----------
    merged : DataFrame 含c1-c4和标签
    c56 : DataFrame 含c5-c6

    Returns
    -------
    (dict of metrics, merged DataFrame)
    """
    print("\n" + "=" * 60)
    print("单因子 AUC-ROC 评估")
    print("=" * 60)

    # 合并所有客户指标（处理c5/c6重复列问题）
    temp = merged.merge(c56, on=['product_id', 'date_month'], how='left', suffixes=('', '_from_c56'))
    # 优先使用c56中的真实值，回退到merged中的NaN
    for col in ['c5_order_interval_change', 'c6_order_qty_change']:
        c56_col = f'{col}_from_c56'
        if c56_col in temp.columns:
            temp[col] = temp[c56_col].fillna(temp.get(col))
            temp = temp.drop(columns=[c56_col])
    df = temp.sort_values('date_month').reset_index(drop=True)

    # 客户指标列
    customer_factors = [
        'c1_concentration_change', 'c2_churn_rate',
        'c3_customer_net_change', 'c4_price_cv',
        'c5_order_interval_change', 'c6_order_qty_change',
    ]

    # 现有因子
    existing_factors = ['f1_score', 'f3_score', 'f4_score', 'f5_score', 'f6_score']

    # 准备TimeSeriesSplit
    months = sorted(df['date_month'].unique())
    print(f"月份数: {len(months)}, 范围: {months[0]} ~ {months[-1]}")

    tscv = TimeSeriesSplit(n_splits=CONFIG['n_splits'])

    # 存储结果
    fold_results = []
    metric_results = {cf: {'aucs': [], 'corr_with_existing': {ef: [] for ef in existing_factors}}
                      for cf in customer_factors}

    for fold, (train_idx, val_idx) in enumerate(tscv.split(months)):
        train_months = [months[i] for i in train_idx]
        val_months = [months[i] for i in val_idx]

        train_df = df[df['date_month'].isin(train_months)]
        val_df = df[df['date_month'].isin(val_months)]

        y_val = val_df['y_decline_6m'].values
        fold_detail = {'fold': fold + 1, 'train_months': train_months, 'val_months': val_months}

        for cf in customer_factors:
            vals = val_df[cf].values
            valid = ~np.isnan(vals)

            # 单因子AUC
            if valid.sum() >= 20 and len(np.unique(y_val[valid])) >= 2:
                try:
                    auc = roc_auc_score(y_val[valid], vals[valid])
                    # 将原始值映射到0-100方向（高的风险高）
                    # c1(集中度上升=风险↑)、c2(流失率↑=风险↑)、c3(客户减少=风险↓←需反转)、
                    # c4(价格离散↑=风险↑)、c5(周期拉长↑=风险↑)、c6(订货量↓=风险↑←需反转)
                    # 自动检测方向：如果auc<0.5，反转
                    if auc < 0.5:
                        auc = roc_auc_score(y_val[valid], -vals[valid])
                    metric_results[cf]['aucs'].append(auc)
                    fold_detail[f'auc_{cf}'] = auc
                except:
                    fold_detail[f'auc_{cf}'] = np.nan
                    metric_results[cf]['aucs'].append(np.nan)
            else:
                fold_detail[f'auc_{cf}'] = np.nan
                metric_results[cf]['aucs'].append(np.nan)

            # 与现有因子的相关
            for ef in existing_factors:
                ef_vals = val_df[ef].values
                both_valid = valid & ~np.isnan(ef_vals)
                if both_valid.sum() >= 10:
                    r, _ = stats.pearsonr(vals[both_valid], ef_vals[both_valid])
                    metric_results[cf]['corr_with_existing'][ef].append(r)
                else:
                    metric_results[cf]['corr_with_existing'][ef].append(np.nan)

        fold_results.append(fold_detail)

    # 汇总
    print("\n各指标单因子 AUC-ROC（n_splits 均值）:")
    header = f"{'指标':30s} {'AUC均值':>8s} {'AUC-std':>8s} {'有效折数':>8s} {'与F1相关':>10s} {'与F3相关':>10s} {'与F4相关':>10s} {'与F5相关':>10s} {'与F6相关':>10s}"
    print(header)
    print("-" * len(header))

    summary = {}
    for cf in customer_factors:
        aucs = metric_results[cf]['aucs']
        valid_aucs = [a for a in aucs if not np.isnan(a)]
        mean_auc = np.mean(valid_aucs) if valid_aucs else np.nan
        std_auc = np.std(valid_aucs) if valid_aucs else np.nan

        # 平均相关性
        corrs = {}
        for ef in existing_factors:
            valid_c = [c for c in metric_results[cf]['corr_with_existing'][ef] if not np.isnan(c)]
            corrs[ef] = np.mean(valid_c) if valid_c else np.nan

        print(f"{cf:30s} {mean_auc:8.4f} {std_auc:8.4f} {len(valid_aucs):8d} "
              f"{corrs['f1_score']:10.4f} {corrs['f3_score']:10.4f} {corrs['f4_score']:10.4f} "
              f"{corrs['f5_score']:10.4f} {corrs['f6_score']:10.4f}")

        summary[cf] = {
            'mean_auc': mean_auc,
            'std_auc': std_auc,
            'n_valid_folds': len(valid_aucs),
            'corr_f1': corrs['f1_score'],
            'corr_f3': corrs['f3_score'],
            'corr_f4': corrs['f4_score'],
            'corr_f5': corrs['f5_score'],
            'corr_f6': corrs['f6_score'],
        }

    return summary, df


def compute_lead_time(df):
    """
    计算每个客户指标的预警提前期。
    对每个衰退产品，c指标首次触发异常到实际衰退的中位数月数。
    """
    print("\n" + "=" * 60)
    print("预警提前期分析")
    print("=" * 60)

    # 定义各指标异常阈值
    alert_thresholds = {
        'c1_concentration_change': lambda x: x > 0.3,       # 集中度上升>30%
        'c2_churn_rate': lambda x: x > 0.2,                 # 流失率>20%
        'c3_customer_net_change': lambda x: x < -0.2,       # 客户数减少>20%
        'c4_price_cv': lambda x: x > 0.5,                   # 价格CV>0.5
        'c5_order_interval_change': lambda x: x > 0.3,       # 订货周期拉长>30%
        'c6_order_qty_change': lambda x: x < -0.2,           # 单次订货量减少>20%
    }

    factor_names = {
        'c1_concentration_change': 'c1客户集中度',
        'c2_churn_rate': 'c2大客户流失率',
        'c3_customer_net_change': 'c3活跃客户净变化',
        'c4_price_cv': 'c4价格离散度',
        'c5_order_interval_change': 'c5订货周期拉长',
        'c6_order_qty_change': 'c6单次订货量衰减',
    }

    decline_prods = df[df['y_decline_6m'] == 1]['product_id'].unique()
    lead_results = {}

    for cf, threshold_fn in alert_thresholds.items():
        lead_times = []
        for prod in decline_prods:
            prod_data = df[(df['product_id'] == prod) & df[cf].notna()].sort_values('date_month')
            if len(prod_data) < 6:
                continue

            decline_series = prod_data['y_decline_6m'].values
            decline_idx = decline_series.argmax() if decline_series.max() == 1 else -1
            if decline_idx <= 0:
                continue

            # 首次触发异常的月份
            before = prod_data.iloc[:decline_idx]
            vals = before[cf].values
            alerts = [i for i, v in enumerate(vals) if threshold_fn(v)]
            if alerts:
                first_alert = alerts[0]
                lead_time = decline_idx - first_alert
                if lead_time > 0:
                    lead_times.append(lead_time)

        lead_times = np.array(lead_times)
        name = factor_names.get(cf, cf)
        if len(lead_times) >= 5:
            lead_results[cf] = {
                'n_cases': len(lead_times),
                'lead_median': np.median(lead_times),
                'lead_mean': lead_times.mean(),
                'lead_std': lead_times.std(),
                'lead_p25': np.percentile(lead_times, 25),
                'lead_p75': np.percentile(lead_times, 75),
            }
            print(f"  {name:20s} 有效:{len(lead_times):4d} 提前期中位数:{np.median(lead_times):5.0f}月  "
                  f"均值:{lead_times.mean():.1f}±{lead_times.std():.1f}  P25~P75:{np.percentile(lead_times,25):.0f}~{np.percentile(lead_times,75):.0f}")
        else:
            lead_results[cf] = {'error': f'样本不足({len(lead_times)}<5)'}
            print(f"  {name:20s} 样本不足({len(lead_times)}<5)")

    return lead_results


def plot_correlation_heatmap(df, customer_factors, existing_factors, output_dir):
    """绘制客户指标与现有因子的相关性热力图"""
    corr_data = df[customer_factors + existing_factors].dropna().corr()
    # 只取客户 vs 现有的交叉部分
    cross_corr = corr_data.loc[customer_factors, existing_factors]

    fig, ax = plt.subplots(figsize=(10, 6))
    sns.heatmap(cross_corr, annot=True, fmt='.3f', cmap='RdBu_r',
                vmin=-1, vmax=1, center=0, ax=ax)
    ax.set_title('客户指标 vs 现有因子 Pearson 相关性', fontsize=14)
    plt.tight_layout()
    path = os.path.join(output_dir, 'phase1_correlation_heatmap.png')
    plt.savefig(path, dpi=150)
    plt.close()
    print(f"相关性热力图: {path}")


def plot_factor_auc_comparison(summary, output_dir):
    """绘制单因子AUC对比图"""
    names = list(summary.keys())
    aucs = [summary[n]['mean_auc'] for n in names]

    # 简短标签
    short_names = ['c1集中度', 'c2流失率', 'c3客户变化', 'c4价格CV', 'c5订货周期', 'c6订货量']

    fig, ax = plt.subplots(figsize=(10, 6))
    colors = ['#2ecc71' if a >= 0.58 else ('#f39c12' if a >= 0.55 else '#e74c3c') for a in aucs]
    bars = ax.bar(range(len(short_names)), aucs, color=colors, edgecolor='gray', alpha=0.8)

    # 添加阈值线
    ax.axhline(y=0.58, color='green', linestyle='--', alpha=0.7, label='通过标准(0.58)')
    ax.axhline(y=0.55, color='orange', linestyle='--', alpha=0.7, label='参考线(0.55)')
    ax.axhline(y=0.50, color='red', linestyle=':', alpha=0.5, label='随机(0.50)')

    # 数值标签
    for bar, auc in zip(bars, aucs):
        if not np.isnan(auc):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.01,
                    f'{auc:.4f}', ha='center', va='bottom', fontsize=9)

    ax.set_xticks(range(len(short_names)))
    ax.set_xticklabels(short_names, rotation=30, ha='right')
    ax.set_ylabel('AUC-ROC')
    ax.set_title('客户维度单因子 AUC-ROC 对比', fontsize=14)
    ax.set_ylim(0.4, 0.75)
    ax.legend()
    plt.tight_layout()
    path = os.path.join(output_dir, 'phase1_auc_comparison.png')
    plt.savefig(path, dpi=150)
    plt.close()
    print(f"AUC对比图: {path}")


def generate_report(summary, lead_results, df, output_dir):
    """生成Phase 1 Markdown报告"""
    print("\n" + "=" * 60)
    print("生成报告")
    print("=" * 60)

    customer_factors = [
        'c1_concentration_change', 'c2_churn_rate',
        'c3_customer_net_change', 'c4_price_cv',
        'c5_order_interval_change', 'c6_order_qty_change',
    ]
    factor_names = {
        'c1_concentration_change': 'c1 客户集中度变化率',
        'c2_churn_rate': 'c2 大客户流失率',
        'c3_customer_net_change': 'c3 活跃客户净变化率',
        'c4_price_cv': 'c4 价格离散度(CV)',
        'c5_order_interval_change': 'c5 订货周期拉长',
        'c6_order_qty_change': 'c6 单次订货量衰减',
    }

    lines = []
    def L(s=""):
        lines.append(s)

    L("# Phase 1 客户维度单因子测试报告")
    L()
    L(f"**生成日期**: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    L(f"**配置**: n_splits={CONFIG['n_splits']}, window={CONFIG['window_months']}月, forward={CONFIG['forward_months']}月")
    L()
    L("---")
    L()

    L("## 1. 单因子AUC-ROC对比")
    L()
    L("| 指标代码 | 指标名称 | AUC-ROC均值 | AUC-ROC标准差 | 有效折数 | 通过(>0.58)? |")
    L("|---------|---------|------------|-------------|---------|------------|")

    pass_count = 0
    for cf in customer_factors:
        s = summary.get(cf, {})
        auc = s.get('mean_auc', np.nan)
        std = s.get('std_auc', np.nan)
        n = s.get('n_valid_folds', 0)
        passed = auc >= 0.58 if not np.isnan(auc) else False
        if passed:
            pass_count += 1
        status = "✅ 通过" if passed else ("⚠️ 边缘" if not np.isnan(auc) and auc >= 0.55 else "❌ 未通过")
        L(f"| {cf[:20]:20s} | {factor_names.get(cf, cf):20s} | {auc:.4f} | {std:.4f} | {n} | {status} |")
    L()
    L(f"**通过率**: {pass_count}/{len(customer_factors)} 个指标 AUC > 0.58")
    L()

    # 相关性矩阵
    L("## 2. 与现有因子的相关性")
    L()
    L("| 指标 | F1毛利率斜率 | F3订货波动 | F4增速衰减 | F5自比健康度 | F6 ASP趋势 | 最大|r| |")
    L("|------|------------|-----------|-----------|------------|-----------|--------|")
    existing_factors = ['f1_score', 'f3_score', 'f4_score', 'f5_score', 'f6_score']
    ef_names = ['F1', 'F3', 'F4', 'F5', 'F6']

    for cf in customer_factors:
        s = summary.get(cf, {})
        corrs = [s.get(f'corr_{ef}', np.nan) for ef in ['f1', 'f3', 'f4', 'f5', 'f6']]
        max_abs = max([abs(c) for c in corrs if not np.isnan(c)], default=np.nan)
        corr_str = " | ".join(f"{c:.4f}" if not np.isnan(c) else "N/A" for c in corrs)
        L(f"| {factor_names.get(cf, cf)} | {corr_str} | {max_abs:.4f} |")
    L()
    L("**通过标准**: 至少有一个指标 |r| < 0.70 且 AUC > 0.58")

    # 预警提前期
    L()
    L("## 3. 预警提前期分布")
    L()
    L("| 指标 | 有效案例数 | 提前期中位数 | 均值±标准差 | P25~P75 |")
    L("|------|----------|------------|------------|--------|")
    for cf in customer_factors:
        lr = lead_results.get(cf, {})
        name = factor_names.get(cf, cf)
        if 'error' in lr:
            L(f"| {name} | {lr['error']} | - | - | - |")
        else:
            L(f"| {name} | {lr.get('n_cases', 0)} | {lr.get('lead_median', 0):.0f}月 | {lr.get('lead_mean', 0):.1f}±{lr.get('lead_std', 0):.1f}月 | {lr.get('lead_p25', 0):.0f}~{lr.get('lead_p75', 0):.0f}月 |")
    L()

    # 数据统计
    L("## 4. 数据覆盖统计")
    L()
    total_months = df['date_month'].nunique()
    total_products = df['product_id'].nunique()
    total_rows = len(df)
    L(f"- 总样本数: {total_rows}")
    L(f"- 产品数: {total_products}")
    L(f"- 月份数: {total_months}")
    L()

    for cf in customer_factors:
        missing = df[cf].isna().mean() * 100
        L(f"- {factor_names.get(cf, cf)}: 缺失率 {missing:.1f}%")
    L()

    # 结论
    L("## 5. 结论与建议")
    L()
    best_cf = max(customer_factors, key=lambda cf: summary.get(cf, {}).get('mean_auc', -1))
    best_auc = summary.get(best_cf, {}).get('mean_auc', np.nan)
    best_name = factor_names.get(best_cf, best_cf)

    L(f"**最优指标**: {best_name} (AUC={best_auc:.4f})")

    if best_auc >= 0.58:
        L("**判定**: ✅ 达到通过标准，可以进入 Phase 3 多因子组合测试。")
    elif best_auc >= 0.55:
        L("**判定**: ⚠️ 边缘通过，客户指标有辅助价值但不足以单独主导。")
    else:
        L("**判定**: ❌ 未达到通过标准(AUC<0.55)，建议停止客户维度探索。")
    L()

    # 如果最优指标相关性过高也说明问题
    if not np.isnan(best_auc) and best_auc >= 0.55:
        max_corr = max([abs(summary.get(best_cf, {}).get(f'corr_{ef}', 0))
                       for ef in ['f1', 'f3', 'f4', 'f5', 'f6']], default=1)
        if max_corr < 0.70:
            L(f"**增量信息**: ✅ 与现有因子最大|r|={max_corr:.4f} < 0.70，具备增量信息。")
        else:
            L(f"**增量信息**: ⚠️ 与现有因子最大|r|={max_corr:.4f} >= 0.70，共线性风险高。")

    L()
    L("---")
    L()
    L("## 6. 可视化图表")
    L()
    L("![AUC对比](phase1_auc_comparison.png)")
    L()
    L("![相关性热力图](phase1_correlation_heatmap.png)")

    # 写入文件
    report_path = os.path.join(output_dir, 'phase1_report.md')
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    print(f"报告已写入: {report_path}")
    return report_path


def main():
    # 1. 加载数据
    df_raw, labels, product_ids = load_data()

    # 2. 构建标签
    labels = build_labels_6m(labels)

    # 3. 聚合客户数据
    cust_month = aggregate_customer_data(df_raw)

    # 4. 计算c1-c4
    merged = compute_customer_metrics(cust_month, labels)

    # 5. 计算c5-c6（需要原始订单数据）
    c56 = compute_c5_c6_order_metrics(df_raw, cust_month, labels)

    # 6. 评估单因子AUC
    summary, df_all = evaluate_single_factor(merged, c56)

    # 7. 预警提前期
    lead_results = compute_lead_time(df_all)

    # 8. 客户指标与现有因子热力图
    output_dir = CONFIG['output_dir']
    os.makedirs(output_dir, exist_ok=True)

    customer_factors = ['c1_concentration_change', 'c2_churn_rate',
                        'c3_customer_net_change', 'c4_price_cv',
                        'c5_order_interval_change', 'c6_order_qty_change']
    existing_factors = ['f1_score', 'f3_score', 'f4_score', 'f5_score', 'f6_score']
    plot_correlation_heatmap(df_all, customer_factors, existing_factors, output_dir)
    plot_factor_auc_comparison(summary, output_dir)

    # 9. 生成报告
    generate_report(summary, lead_results, df_all, output_dir)

    # 10. 保存因子数据
    out_cols = ['product_id', 'date_month', 'y_decline_6m'] + customer_factors + existing_factors + ['portrait']
    out_cols = [c for c in out_cols if c in df_all.columns]
    df_out = df_all[out_cols].copy()
    csv_path = os.path.join(output_dir, 'phase1_customer_factors.csv')
    df_out.to_csv(csv_path, index=False, encoding='utf-8-sig')
    print(f"\n客户因子数据已保存: {csv_path}")

    return 0


if __name__ == '__main__':
    sys.exit(main())
