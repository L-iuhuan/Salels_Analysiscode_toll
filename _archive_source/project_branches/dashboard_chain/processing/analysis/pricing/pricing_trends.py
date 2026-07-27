"""
价格分析函数 — ASP趋势、弹性计算、价格偏离度、价格带分布。

可被产品生命周期和客户分析复用。
"""
import numpy as np
import pandas as pd


def _ensure_period_dtype(date_series: pd.Series, latest_month=None):
    """Ensure _月 column is Period dtype (survives CSV round-trip).
    
    When Silver CSV is reloaded, the _月 column becomes string/object.
    This helper standardizes it back to Period[M] type.
    
    Returns:
        tuple: (standardized_series, standardized_latest_month)
    """
    if latest_month is not None and not isinstance(latest_month, pd.Period):
        latest_month = pd.to_datetime(str(latest_month)).to_period('M')
    if not isinstance(date_series.dtype, pd.PeriodDtype):
        date_series = pd.to_datetime(date_series).dt.to_period('M')
    return date_series, latest_month


def calc_asp_trend(monthly_prices, thr=None):
    """ASP趋势斜率（近12月均价变化率）。
    
    月均价 = rev_pos / qty_sum，最小二乘求斜率。
    
    参数:
        monthly_prices: 月度均价列表
        thr: 阈值字典（用于min_pts）
    
    返回:
        tuple: (斜率值 比率/月, 是否可靠)
    """
    prices = np.asarray(monthly_prices, dtype=float)
    min_pts = int(thr.get("slope_min_data_points", 3)) if thr else 3
    
    if len(prices) < min_pts:
        return (0.0, False)
    
    x = np.arange(len(prices))
    mask = ~(np.isnan(prices) | (prices <= 0))
    if mask.sum() < min_pts:
        return (0.0, False)
    
    slope = np.polyfit(x[mask], prices[mask], 1)[0]
    avg = np.nanmean(prices[mask])
    if avg > 0:
        return (slope / avg, True)
    return (0.0, False)


def calc_price_elasticity(monthly_prices, monthly_qtys, thr=None):
    """计算价格弹性系数。
    
    稳健方法：百分比变化中位数 + IQR过滤，结果裁剪。
    
    参数:
        monthly_prices: 月度均价列表
        monthly_qtys: 月度销量列表
        thr: 阈值字典
    
    返回:
        tuple: (弹性系数, 敏感度标签)
    """
    if len(monthly_prices) < 3 or len(monthly_qtys) < 3:
        return None, "数据不足"
    
    price_changes = np.diff(monthly_prices) / np.where(monthly_prices[:-1] > 0, monthly_prices[:-1], 1)
    qty_changes = np.diff(monthly_qtys) / np.where(monthly_qtys[:-1] > 0, monthly_qtys[:-1], 1)
    
    valid_mask = (np.abs(price_changes) > 1e-6) & ~np.isnan(qty_changes) & ~np.isnan(price_changes)
    if valid_mask.sum() < 2:
        return None, "数据不足"
    
    elasticities = qty_changes[valid_mask] / price_changes[valid_mask]
    
    q1, q3 = np.percentile(elasticities, [25, 75])
    iqr = q3 - q1
    filtered = elasticities[(elasticities >= q1 - 3*iqr) & (elasticities <= q3 + 3*iqr)]
    elasticity = np.median(filtered) if len(filtered) >= 2 else np.median(elasticities)
    
    elasticity = np.clip(elasticity, -10, 10)
    
    if thr:
        t_high = float(thr.get("elasticity_high", 1.5))
        t_mid = float(thr.get("elasticity_mid", 0.8))
    else:
        t_high, t_mid = 1.5, 0.8
    
    abs_el = abs(elasticity)
    if abs_el > t_high:
        sensitivity = "高敏感"
    elif abs_el > t_mid:
        sensitivity = "中敏感"
    else:
        sensitivity = "低敏感"
    
    return elasticity, sensitivity


def calc_order_frequency_trend(prod_data, latest_month, thr=None):
    """计算订单频次趋势。近3月 vs 前9月。
    
    参数:
        prod_data: 产品月度数据DataFrame（index为月份）
        latest_month: 最新月份（Period对象）
        thr: 阈值字典
    
    返回:
        tuple: (频次变化比率, 标签)
    """
    if prod_data.empty:
        return 0, "无数据"

    if '_order_count' not in prod_data.columns:
        return 0, "无订单频次数据"

    last3_mask = prod_data.index > (latest_month - 3)
    recent3_orders = prod_data.loc[last3_mask, '_order_count'].sum()
    recent3_avg = recent3_orders / 3
    
    prior9_mask = (prod_data.index <= (latest_month - 3)) & (prod_data.index > (latest_month - 12))
    prior9_orders = prod_data.loc[prior9_mask, '_order_count'].sum()
    prior9_months = prior9_mask.sum()
    prior9_avg = prior9_orders / prior9_months if prior9_months > 0 else 0
    
    if prior9_avg == 0:
        return 0, "无参照"
    
    freq_change = (recent3_avg - prior9_avg) / prior9_avg
    
    if thr:
        t_up = float(thr.get("freq_increase", 0.15))
        t_down = float(thr.get("freq_decrease", -0.10))
    else:
        t_up, t_down = 0.15, -0.10
    
    if freq_change > t_up:
        label = "增强"
    elif freq_change > t_down:
        label = "持平"
    else:
        label = "减弱"
    
    return freq_change, label

