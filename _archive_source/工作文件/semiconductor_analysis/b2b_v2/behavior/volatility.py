"""
Task 5: 采购波动性/稳定性指标 (Volatility Metrics).

量化客户采购稳定性，影响安全库存和排产计划。

指标:
  1. 收入变异系数 (CV) = std / mean
  2. 最大单月跌幅 = max(月环比下跌)
  3. 零采购月数占比 = 零采购月数 / 总月数
  4. 趋势稳定性 = 线性趋势 R²（接近 1 = 稳定）

稳定性等级:
  - 高稳定: CV < 0.3 且 零采购月占比 < 10%
  - 中等稳定: CV < 0.6 且 零采购月占比 < 20%
  - 高波动: 其他

依赖: config.settings.VOLATILITY_METRICS（或回退默认值）
"""

import sys, os
import pandas as pd
import numpy as np

_SRC_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)


def calc_volatility_metrics(
    monthly_revenue_series: pd.Series,
    config: dict = None,
) -> dict:
    """
    计算单个客户的采购波动性指标。

    参数
    ----------
    monthly_revenue_series : pd.Series
        客户近 N 个月的月度金额序列（含零值月份），index 为月份。
    config : dict or None
        阈值字典，可选键:
        - stable_cv_threshold: 0.3
        - stable_zero_month_ratio: 0.10
        - moderate_cv_threshold: 0.6
        - moderate_zero_month_ratio: 0.20
        为 None 时使用上述默认值。

    返回
    -------
    dict
        {
            "收入CV": float,
            "最大单月跌幅": float,
            "零采购月占比": float,
            "趋势R²": float,
            "稳定性等级": str,  # "高稳定" | "中等稳定" | "高波动"
        }

    异常
    ------
    - 空序列或全部为零 → 返回全零指标 + "高波动"等级
    - 不足 3 个数据点 → CV 可用但 R² 返回 0
    """
    # ── 阈值 ──
    stable_cv = (config or {}).get("stable_cv_threshold", 0.3)
    stable_zero = (config or {}).get("stable_zero_month_ratio", 0.10)
    moderate_cv = (config or {}).get("moderate_cv_threshold", 0.6)
    moderate_zero = (config or {}).get("moderate_zero_month_ratio", 0.20)

    # ── 空数据保护 ──
    if monthly_revenue_series is None or len(monthly_revenue_series) == 0:
        return {"收入CV": 0, "最大单月跌幅": 0, "零采购月占比": 1, "趋势R²": 0, "稳定性等级": "高波动"}

    vals = monthly_revenue_series.values.astype(float)

    # 1. 收入变异系数
    mean_val = np.mean(vals)
    std_val = np.std(vals, ddof=1) if len(vals) > 1 else 0
    cv = std_val / mean_val if mean_val > 0 else 999.0

    # 2. 最大单月跌幅
    max_drop = 0.0
    if len(vals) >= 2:
        diffs = np.diff(vals)
        negative_diffs = diffs[diffs < 0]
        if len(negative_diffs) > 0:
            # 跌幅 = 下跌额 / 前一个月值
            prev_vals = vals[:-1][diffs < 0]
            drop_ratios = np.abs(negative_diffs) / np.maximum(prev_vals, 1)
            max_drop = float(np.max(drop_ratios))

    # 3. 零采购月占比
    zero_ratio = np.sum(vals == 0) / len(vals) if len(vals) > 0 else 1.0

    # 4. 趋势稳定性 R²
    r_squared = 0.0
    if len(vals) >= 3:
        try:
            x = np.arange(len(vals))
            mask = ~np.isnan(vals)
            if np.sum(mask) >= 3:
                coeffs = np.polyfit(x[mask], vals[mask], 1)
                y_pred = np.polyval(coeffs, x[mask])
                ss_res = np.sum((vals[mask] - y_pred) ** 2)
                ss_tot = np.sum((vals[mask] - np.mean(vals[mask])) ** 2)
                r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0
        except (ValueError, TypeError, np.linalg.LinAlgError):
            r_squared = 0.0

    # 5. 稳定性等级（v4.5: 加权评分制替代AND逻辑）
    cv_score = 100 if cv < stable_cv else (60 if cv < moderate_cv else 20)
    zero_score = 100 if zero_ratio < 0.75 else (60 if zero_ratio < 0.95 else 20)
    r2_score = r_squared * 100 if r_squared > 0 else 0
    stability_score = cv_score * 0.4 + zero_score * 0.3 + r2_score * 0.3
    if stability_score >= 70:
        tier = "高稳定"
    elif stability_score >= 40:
        tier = "中等稳定"
    else:
        tier = "高波动"

    return {
        "收入CV": round(cv, 4),
        "最大单月跌幅": round(max_drop, 4),
        "零采购月占比": round(zero_ratio, 4),
        "趋势R²": round(r_squared, 4),
        "稳定性等级": tier,
    }


def batch_calc_volatility(
    cust_monthly: pd.DataFrame,
    config: dict = None,
    cust_col: str = "客户编号",
    date_col: str = "_月",
    rev_col: str = "rev_sum",
) -> pd.DataFrame:
    """
    批量计算所有客户的波动性指标。

    参数
    ----------
    cust_monthly : DataFrame
        客户月度聚合表。
    config : dict or None
        阈值字典，传入 calc_volatility_metrics。
    cust_col, date_col, rev_col : str
        列名。

    返回
    -------
    DataFrame
        每客户一行，列:
        - 客户编号
        - 收入CV
        - 最大单月跌幅
        - 零采购月占比
        - 趋势R²
        - 稳定性等级
    """
    if cust_monthly is None or len(cust_monthly) == 0:
        return pd.DataFrame(columns=[
            cust_col, "收入CV", "最大单月跌幅", "零采购月占比", "趋势R²", "稳定性等级",
        ])

    # 全时间范围（用于零填充缺失月份）
    all_months = sorted(cust_monthly[date_col].dropna().unique())
    results = []
    for cid, grp in cust_monthly.groupby(cust_col):
        grp = grp.sort_values(date_col, kind='stable')
        series = grp.set_index(date_col)[rev_col]
        # 回填缺失月份为0（否则零采购月占比永远为0）
        series = series.reindex(all_months, fill_value=0.0)
        metrics = calc_volatility_metrics(series, config)
        metrics[cust_col] = cid
        results.append(metrics)

    out = pd.DataFrame(results)
    # 确保列顺序
    cols = [cust_col, "收入CV", "最大单月跌幅", "零采购月占比", "趋势R²", "稳定性等级"]
    return out[[c for c in cols if c in out.columns]]
