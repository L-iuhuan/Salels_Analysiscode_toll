"""
趋势分析深化模块（Phase 4）。

3张趋势分析表：
  1. 月度营收趋势 — 每客户每月 MA3/MA6/环比/同比/斜率/趋势方向
  2. 品类迁移分析 — 每半年品类结构变化
  3. 客户ETS预测 — 未来3月收入预测
"""

import os
import sys
import pandas as pd
import numpy as np

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from config.settings import CUSTOMER_COL_MAP, CUSTOMER_THRESHOLDS
from config.settings import (
    TREND_MA_WINDOWS, TREND_SLOPE_THRESHOLDS,
    TREND_CATEGORY_MIGRATION, TREND_FORECAST, TREND_GROWTH_CLIP,
)
from shared.calc_utils import calc_slope
from shared.forecasting import ets_forecast


# ============================================================
# 1. 月度营收趋势
# ============================================================

def calc_monthly_revenue_trend(
    cust_monthly: pd.DataFrame,
    latest_month,
    min_history: int = 3,
) -> pd.DataFrame:
    """月度营收趋势表：每客户每月一行，含趋势指标。

    输出字段：
      - 客户编号, 月份
      - 月收入, 月毛利, 月数量
      - MA3(收入3月均), MA6(收入6月均)
      - 月环比增速%, 月同比增速%
      - 收入斜率(6月), 趋势方向(上升/平稳/下降)

    参数:
        cust_monthly: Silver层客户月度数据
        latest_month: 最新月份（Period对象）
        min_history: 最少月数

    返回:
        DataFrame
    """
    df = cust_monthly.copy()
    df = df.sort_values(["客户编号", "_月"], kind='stable')

    results = []
    for cid, grp in df.groupby("客户编号"):
        grp = grp.sort_values("_月", kind='stable').reset_index(drop=True)

        for i in range(len(grp)):
            row = {"客户编号": cid, "月份": str(grp.loc[i, "_月"])}
            row["月收入"] = round(grp.loc[i, "rev_sum"], 2)
            row["月毛利"] = round(grp.loc[i, "profit_clip_sum"], 2) if "profit_clip_sum" in grp.columns else 0
            row["月数量"] = int(grp.loc[i, "qty_sum"])
            row["月订单数"] = int(grp.loc[i, "order_count"]) if "order_count" in grp.columns else 0

            # MA3 (前3月含本月) — 窗口大小来自 settings.py:TREND_MA_WINDOWS
            ma3_cfg = TREND_MA_WINDOWS.get("MA3", {"window": 3, "min_pts": 2})
            ma3_win = grp.loc[max(0, i - ma3_cfg["window"] + 1):i, "rev_sum"]
            row["MA3"] = round(ma3_win.mean(), 2) if len(ma3_win) >= ma3_cfg["min_pts"] else None

            # MA6
            ma6_cfg = TREND_MA_WINDOWS.get("MA6", {"window": 6, "min_pts": 3})
            ma6_win = grp.loc[max(0, i - ma6_cfg["window"] + 1):i, "rev_sum"]
            row["MA6"] = round(ma6_win.mean(), 2) if len(ma6_win) >= ma6_cfg["min_pts"] else None

            # 月环比 (本月 vs 上月)，钳制防止极端值
            _clip_cfg = TREND_GROWTH_CLIP
            _mom_upper = _clip_cfg.get("月环比上限", 999.0)
            _mom_lower = _clip_cfg.get("月环比下限", -999.0)
            if i > 0 and grp.loc[i - 1, "rev_sum"] > 1.0:
                raw_mom = (grp.loc[i, "rev_sum"] - grp.loc[i - 1, "rev_sum"]) / grp.loc[i - 1, "rev_sum"] * 100
                row["月环比%"] = round(max(_mom_lower, min(_mom_upper, raw_mom)), 1)
            else:
                row["月环比%"] = None

            # 月同比 (本月 vs 去年同月)，钳制防止极端值
            _yoy_upper = _clip_cfg.get("月同比上限", 999.0)
            _yoy_lower = _clip_cfg.get("月同比下限", -999.0)
            current_month = grp.loc[i, "_月"]
            target_month = current_month - 12
            match = grp[grp["_月"] == target_month]
            if len(match) > 0 and match.iloc[0]["rev_sum"] > 1.0:
                prev_rev = match.iloc[0]["rev_sum"]
                raw_yoy = (grp.loc[i, "rev_sum"] - prev_rev) / prev_rev * 100
                row["月同比%"] = round(max(_yoy_lower, min(_yoy_upper, raw_yoy)), 1)
            else:
                row["月同比%"] = None

            # 收入斜率（近6月线性回归）
            slope_win = grp.loc[max(0, i - 5):i, "rev_sum"].values
            if len(slope_win) >= min_history:
                slope_val = calc_slope(slope_win, min_pts=min_history)
                row["收入斜率"] = round(slope_val, 6) if slope_val != 0.0 else 0.0
            else:
                row["收入斜率"] = None

            results.append(row)

    result_df = pd.DataFrame(results)

    # 趋势方向判定（阈值来自 settings.py:TREND_SLOPE_THRESHOLDS）
    if "收入斜率" in result_df.columns:
        _slope_cfg = TREND_SLOPE_THRESHOLDS
        _up = _slope_cfg.get("上升阈值", 0.02)
        _down = _slope_cfg.get("下降阈值", -0.02)
        _flat = _slope_cfg.get("默认方向", "平稳")
        _unknown = _slope_cfg.get("未知方向", "未知")

        def _trend_dir(x):
            if pd.isna(x):
                return _unknown
            if x > _up:
                return "上升"
            elif x < _down:
                return "下降"
            return _flat

        result_df["趋势方向"] = result_df["收入斜率"].apply(_trend_dir)

    return result_df


# ============================================================
# 2. 品类迁移分析
# ============================================================

def _to_half_year(period_str: str) -> str:
    """将月份转为半年标识，如 2024-01 → 2024H1, 2024-07 → 2024H2。"""
    try:
        parts = str(period_str).split("-")
        year = int(parts[0])
        month = int(parts[1])
        return f"{year}H{'1' if month <= 6 else '2'}"
    except (ValueError, IndexError):
        return str(period_str)


def calc_category_migration(
    cust_prod: pd.DataFrame,
    min_share: float = 0.01,
) -> pd.DataFrame:
    """品类迁移分析：每客户每半年的品类结构变化。

    观察客户采购品类结构的跨期变化：
    - 品类收入占比 vs 上期变化
    - 品类排名 vs 上期变化

    参数:
        cust_prod: customer_x_product DataFrame
        min_share: 最小品类占比阈值（低于此值合并为"其他"）

    返回:
        DataFrame: 每客户-期间-品类一行
    """
    cat_col = CUSTOMER_COL_MAP.get("品类列", "型号_产品线（新）")  # v4.14: 统一为产品线
    if cat_col not in cust_prod.columns:
        return pd.DataFrame()

    df = cust_prod.copy()
    df["期间"] = df["_月"].apply(_to_half_year)

    # 每客户-期间-品类 聚合
    cat_rev = df.groupby(["客户编号", "期间", cat_col], as_index=False)["rev_sum"].sum()

    rows = []
    # 品类占比阈值来自 settings.py:TREND_CATEGORY_MIGRATION
    _min_share = min_share if min_share is not None else TREND_CATEGORY_MIGRATION.get("min_share", 0.01)

    for (cid, period), grp in cat_rev.groupby(["客户编号", "期间"]):
        total = grp["rev_sum"].sum()
        if total <= 0:
            continue

        for _, r in grp.iterrows():
            share = r["rev_sum"] / total if total > 0 else 0
            if share >= _min_share:
                rows.append({
                    "客户编号": cid,
                    "期间": period,
                    "产品线": r[cat_col],
                    "产品线收入": round(r["rev_sum"], 2),
                    "产品线占比": round(share, 4),
                })

    result = pd.DataFrame(rows)
    if len(result) == 0:
        return result

    # 计算上期品类占比（对比变化）
    result = result.sort_values(["客户编号", "产品线", "期间"], kind='stable')
    for col in ["产品线占比"]:
        result[f"{col}变化"] = result.groupby(["客户编号", "产品线"])[col].diff()

    # 产品线排名（每期间内）
    result["产品线排名"] = result.groupby(["客户编号", "期间"])["产品线收入"].rank(
        method="dense", ascending=False
    ).astype(int)

    # 排名变化
    result["排名变化"] = result.groupby(["客户编号", "产品线"])["产品线排名"].diff()

    return result


# ============================================================
# 3. 客户ETS预测
# ============================================================

def calc_customer_forecast(
    cust_monthly: pd.DataFrame,
    latest_month,
    forecast_months: int = 3,
    min_history: int = 12,
) -> pd.DataFrame:
    """每客户未来N月收入预测（ETS模型）。

    仅对历史 >= min_history 个月的客户运行。
    输出可信度标注：MAPE < 30% 为可信。

    参数:
        cust_monthly: Silver层客户月度数据
        latest_month: 最新月份
        forecast_months: 预测月数
        min_history: 最少历史月数

    返回:
        DataFrame: 每客户-预测月一行
    """
    df = cust_monthly.copy()
    df = df.sort_values(["客户编号", "_月"], kind='stable')

    # 预测参数来自 settings.py:TREND_FORECAST
    _n_forecast = forecast_months if forecast_months is not None else TREND_FORECAST.get("forecast_months", 3)
    _min_hist = min_history if min_history is not None else TREND_FORECAST.get("min_history", 12)

    results = []
    for cid, grp in df.groupby("客户编号"):
        grp = grp.sort_values("_月", kind='stable')

        if len(grp) < _min_hist:
            continue

        rev_series = grp["rev_sum"].values
        forecast, direction, pred_int, model_info = ets_forecast(
            rev_series,
            periods=_n_forecast,
        )

        if forecast is None:
            continue

        # pred_int: {80: (lower_list, upper_list), 95: (lower_list, upper_list)}
        pred_lower_80 = None
        pred_upper_80 = None
        if isinstance(pred_int, dict) and 80 in pred_int:
            pred_lower_80 = pred_int[80][0] if isinstance(pred_int[80], (list, tuple)) and len(pred_int[80]) > 0 else None
            pred_upper_80 = pred_int[80][1] if isinstance(pred_int[80], (list, tuple)) and len(pred_int[80]) > 1 else None

        for m in range(_n_forecast):
            future_month = latest_month + (m + 1)

            # 安全取值：检查NaN/INF
            def _safe_round(v, digits=2):
                if v is None:
                    return None
                try:
                    vf = float(v)
                    if pd.isna(vf) or np.isinf(vf):
                        return None
                    return round(vf, digits)
                except (ValueError, TypeError):
                    return None

            row = {
                "客户编号": cid,
                "预测月份": str(future_month),
                "预测收入": _safe_round(forecast[m]) if m < len(forecast) else None,
                "预测下限(80%CI)": _safe_round(pred_lower_80[m]) if pred_lower_80 is not None and m < len(pred_lower_80) else None,
                "预测上限(80%CI)": _safe_round(pred_upper_80[m]) if pred_upper_80 is not None and m < len(pred_upper_80) else None,
                "预测方向": direction if isinstance(direction, str) else "未知",
            }

            # 模型信息（仅第一行附带）
            if m == 0 and model_info is not None:
                row["模型类型"] = model_info.get("model_type", "未知")
                row["AIC"] = model_info.get("aic", None)
                # MAPE 需要额外计算，暂不输出
                row["可信"] = "是" if model_info.get("aic") is not None else "否"
            else:
                row["模型类型"] = None
                row["AIC"] = None
                row["可信"] = None

            results.append(row)

    return pd.DataFrame(results)
