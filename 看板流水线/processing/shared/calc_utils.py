import numpy as np
import pandas as pd


def calc_slope(y_values, min_pts=3):
    """对 y_values 做线性回归，返回斜率（单位/月）。数据点不足时返回 0.0。
    
    与产品生命周期v2.8的 calc_slope 逻辑一致。
    """
    if len(y_values) < min_pts:
        return 0.0
    x = np.arange(len(y_values))
    mask = ~np.isnan(y_values)
    if mask.sum() < min_pts:
        return 0.0
    slope = np.polyfit(x[mask], y_values[mask], 1)[0]
    return slope


def calc_age_months(first_period, last_period):
    """计算两个Period之间的月数差。"""
    if pd.isna(first_period) or pd.isna(last_period):
        return 0
    return (last_period - first_period).n + 1


def calc_moving_growth_rate(recent_values, prior_values, method="月均"):
    """计算增长率。

    method='月均': 用月均法（总量/活跃月数），消除窗口月份数不一致的影响
    method='总量': 直接用总量对比（仅当前后窗口月数一致时使用）

    返回:
        (growth_rate, window_label)
        growth_rate: 比率形式（如0.15表示15%），已截断到[-1.0, 5.0]
        window_label: 实际使用的窗口描述
    """
    if method == "月均":
        recent_avg = np.mean(recent_values) if len(recent_values) > 0 else 0
        prior_avg = np.mean(prior_values) if len(prior_values) > 0 else 0
    else:
        recent_avg = sum(recent_values)
        prior_avg = sum(prior_values)

    if prior_avg > 0:
        growth = (recent_avg - prior_avg) / prior_avg
    else:
        growth = 0.0

    growth = max(-1.0, min(growth, 5.0))
    return growth


def calc_growth_with_window_auto(monthly_qty_series, latest_month, min_months=2):
    """自动缩窗计算增长率。

    优先使用近12月 vs 前12月，若前12月无数据则依次尝试6月、3月窗口。

    参数:
        monthly_qty_series: 以月份Period为index的销量Series
        latest_month: 最新月份Period
        min_months: 最小有效月数

    返回:
        (growth_rate, window_label, is_clamped)
    """
    growth_window_label = "12月"

    # 尝试12月窗口
    recent_mask = monthly_qty_series.index > (latest_month - 12)
    prior_mask = (monthly_qty_series.index <= (latest_month - 12)) & (
        monthly_qty_series.index > (latest_month - 24)
    )
    recent_vals = monthly_qty_series[recent_mask].values
    prior_vals = monthly_qty_series[prior_mask].values

    if len(prior_vals) >= min_months and prior_vals.sum() > 0:
        return calc_moving_growth_rate(recent_vals, prior_vals), "12月", False

    # 缩至6月窗口
    prior_mask_6 = (monthly_qty_series.index <= (latest_month - 6)) & (
        monthly_qty_series.index > (latest_month - 12)
    )
    prior_vals_6 = monthly_qty_series[prior_mask_6].values
    if len(prior_vals_6) >= min_months and prior_vals_6.sum() > 0:
        recent_mask_6 = monthly_qty_series.index > (latest_month - 6)
        recent_vals_6 = monthly_qty_series[recent_mask_6].values
        return calc_moving_growth_rate(recent_vals_6, prior_vals_6), "6月", False

    # 缩至3月窗口
    prior_mask_3 = (monthly_qty_series.index <= (latest_month - 3)) & (
        monthly_qty_series.index > (latest_month - 6)
    )
    prior_vals_3 = monthly_qty_series[prior_mask_3].values
    if len(prior_vals_3) >= min_months and prior_vals_3.sum() > 0:
        recent_mask_3 = monthly_qty_series.index > (latest_month - 3)
        recent_vals_3 = monthly_qty_series[recent_mask_3].values
        return calc_moving_growth_rate(recent_vals_3, prior_vals_3), "3月", False

    return 0.0, "无参照", False


def calculate_top_n_concentration(g, rev_col, n=3):
    """计算前N大集中度。
    
    参数:
        g: DataFrame，含客户和收入列
        rev_col: 收入列名
        n: 前N大

    返回:
        (top1_ratio, top3_ratio)
    """
    tot = g[rev_col].sum()
    if tot == 0:
        return 0.0, 0.0
    s = g[rev_col].sort_values(ascending=False, kind='stable')
    top1 = s.iloc[0] / tot if len(s) >= 1 else 0
    topn = s.iloc[:n].sum() / tot if len(s) >= n else 1.0
    return top1, topn


def calculate_hhi(shares):
    """计算赫芬达尔-赫希曼指数（品类集中度）。

    参数:
        shares: 各品类采购占比的列表或数组

    返回:
        HHI值（0-1之间）
    """
    shares = np.array(shares)
    shares = shares[shares > 0]
    if len(shares) == 0:
        return 0
    return (shares ** 2).sum()


def percentile_cut(series, n_bins=5, ascending=True, labels=None):
    """对序列做等深分位切割，返回分位得分。

    参数:
        series: 待切割序列
        n_bins: 分位数
        ascending: True=低分位得低分，False=低分位得高分
        labels: 自定义标签列表（长度=n_bins）

    返回:
        分位得分Series
    """
    if labels is None:
        labels = list(range(1, n_bins + 1)) if ascending else list(range(n_bins, 0, -1))
    try:
        return pd.qcut(series, n_bins, labels=labels, duplicates="drop").astype(int)
    except ValueError:
        return pd.Series([labels[len(labels) // 2]] * len(series), index=series.index)
