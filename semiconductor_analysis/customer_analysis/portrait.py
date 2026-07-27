"""
客户全景画像计算。

按文档10大维度组织计算逻辑：
  1. 基本信息
  2. 经营势能（含趋势判断）
  3. 产品覆盖
  4. 产品线分布
  5. 采购健康度  ← 来自 dimensions.py 批量计算
  6. 价格治理     ← 来自 dimensions.py 批量计算
  7. 品类接受度   ← 来自 dimensions.py 批量计算
  8. SKU生命周期  ← 来自 dimensions.py 批量计算
  9. 新品渗透     ← 来自 dimensions.py 批量计算
 10. ASP/毛利率对比 ← 内联计算
"""

import os
import sys
import pandas as pd
import numpy as np

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from shared.data_cleaning import read_excel_auto
from config.settings import CUSTOMER_THRESHOLDS, CUSTOMER_COL_MAP, METRIC_CAPS, CHANNEL_DERIVE, DEPT_REGION_MAP, CUSTOMER_ANALYSIS_WINDOW
from customer_analysis.dimensions import (
    calc_purchase_interval,
    calc_churn_warning,
    calc_product_concentration,
    calc_category_acceptance,
    calc_price_band_distribution,
    calc_sku_lifecycle_stage,
    calc_customer_lifecycle_stage,
    calc_new_product_cohort,
    calc_opportunity_signals,
    calc_risk_signals,
)


# ============================================================
# 辅助函数：批量计算
# ============================================================

def _compute_batch_metrics(cust_monthly, cust_prod, prod_monthly, latest_month, cat_col):
    """执行所有批量计算，返回结果字典。"""
    thr = CUSTOMER_THRESHOLDS
    metrics = {}

    metrics["intervals"] = calc_purchase_interval(
        cust_monthly,
        exclude_first_months=thr.get("purchase_interval_exclude_first_months", 6),
    )
    metrics["churn"] = calc_churn_warning(
        cust_monthly, metrics["intervals"],
        multiplier=thr.get("churn_multiplier", 1.5),
    )
    metrics["concentration"] = calc_product_concentration(
        cust_prod,
        top_n=thr.get("concentration_top_n", 5),
        threshold=thr.get("concentration_threshold", 0.7),
    )
    metrics["category_acc"] = calc_category_acceptance(cust_prod, category_col=cat_col)
    metrics["price_bands"] = calc_price_band_distribution(cust_prod)
    metrics["sku_stages"] = calc_sku_lifecycle_stage(prod_monthly)
    metrics["cust_stages"] = calc_customer_lifecycle_stage(
        cust_monthly, latest_month=latest_month,
    )
    metrics["new_prod_cohort"] = calc_new_product_cohort(prod_monthly, cust_prod)
    metrics["opp_signals"] = calc_opportunity_signals(
        cust_monthly, prod_monthly, cust_prod, latest_month=latest_month,
    )
    metrics["risk_signals"] = calc_risk_signals(
        cust_monthly, cust_prod, latest_month=latest_month,
    )

    return metrics


# ============================================================
# 维度辅助函数（每个返回dict，合并到客户行）
# ============================================================

def _derive_channel(cid, raw_data):
    """从交易数据推导渠道类型。

    规则：
      - 客户编号出现在"代理商/直供名称"列 → 该客户为代理商
      - 客户编号出现在"实际终端客户"列 → 该客户为直供终端
      - 同时出现在两列 → 看出现次数比例
    """
    if raw_data is None:
        return "未知"
    cd = CHANNEL_DERIVE
    buyer_col = cd.get("buyer_col", "代理商/直供名称")
    end_col = cd.get("end_cust_col", "实际终端客户")

    buyer_mask = raw_data[buyer_col] == cid
    buyer_count = buyer_mask.sum()

    if end_col in raw_data.columns:
        end_mask = raw_data[end_col] == cid
        end_count = end_mask.sum()
    else:
        end_count = 0

    if buyer_count == 0 and end_count == 0:
        return cd.get("default", "未知")
    return "直供" if end_count >= buyer_count else "代理"


def _dim_base_info(cid, cust_info, raw_data=None, attr_map=None):
    """基本信息：渠道类型、客户等级、所属区域、业务负责人。

    渠道类型三级降级（从高到低）:
      1. CRM客户信息表（cust_info）中的"渠道类型"列
      2. 交易数据推导 _derive_channel()
      3. 默认"未知"
    """
    row = {}
    info = cust_info[cust_info["客户编号"] == cid]
    if len(info) > 0:
        info = info.iloc[0]
        # 渠道类型：CRM→交易推导三级降级
        channel = info.get("渠道类型")
        if channel and channel != "未知":
            row["渠道类型"] = channel
        else:
            row["渠道类型"] = _derive_channel(cid, raw_data)
        row["客户等级"] = info.get("客户等级", "未知")
        row["所属区域"] = info.get("所属区域", "未知")
        row["业务负责人"] = info.get("业务负责人", "未知")
    else:
        row["渠道类型"] = _derive_channel(cid, raw_data)
        # 从交易数据映射回退
        if attr_map and cid in attr_map:
            row["所属区域"] = attr_map[cid].get("所属区域", "未知")
            row["业务负责人"] = attr_map[cid].get("业务负责人", "未知")
        else:
            row["客户等级"] = "未知"
            row["所属区域"] = "未知"
            row["业务负责人"] = "未知"
    return row


def _dim_momentum(c_data, latest_month):
    """经营势能（含趋势判断）：
    近N月收入/毛利/毛利率、前N月收入、增长率、订单数、
    ASP_加权、连续增长/下滑月数。
    窗口长度来自 settings.py:CUSTOMER_ANALYSIS_WINDOW。
    """
    row = {}
    _win = CUSTOMER_ANALYSIS_WINDOW
    _value_win = _win.get("value_window_months", 12)
    _growth_win = _win.get("growth_window_months", 12)
    _short_win = _win.get("growth_window_short", 6)

    recent = c_data[c_data["_月"] > (latest_month - _value_win)]
    prior = c_data[
        (c_data["_月"] <= (latest_month - _growth_win))
        & (c_data["_月"] > (latest_month - _growth_win * 2))
    ]

    row[f"近{_value_win}月收入"] = recent["rev_sum"].sum()
    row[f"近{_value_win}月毛利"] = recent["profit_clip_sum"].sum()
    row["近12月毛利率"] = (
        row.get(f"近{_value_win}月毛利", 0) / row.get(f"近{_value_win}月收入", 1) * 100
        if row.get(f"近{_value_win}月收入", 0) > 0 else 0
    )
    row[f"前{_growth_win}月收入"] = prior["rev_sum"].sum()
    row["近12月数量"] = recent["qty_sum"].sum()
    row["订单数"] = recent["order_count"].sum() if "order_count" in recent.columns else 0

    recent_months = recent[recent["rev_sum"] > 0]
    prior_months = prior[prior["rev_sum"] > 0]
    if len(prior_months) >= 2 and prior_months["rev_sum"].sum() > 0:
        r_avg = recent_months["rev_sum"].mean()
        p_avg = prior_months["rev_sum"].mean()
        row["收入增长率"] = (r_avg - p_avg) / p_avg
    else:
        # 短窗口回退：近N月 vs 前N月（针对新客户/数据不足的客户）
        recent_s = c_data[
            (c_data["_月"] > (latest_month - _short_win)) & (c_data["rev_sum"] > 0)
        ]
        prior_s = c_data[
            (c_data["_月"] <= (latest_month - _short_win))
            & (c_data["_月"] > (latest_month - _short_win * 2))
        ]
        prior_s = prior_s[prior_s["rev_sum"] > 0]
        if len(prior_s) >= 1 and prior_s["rev_sum"].sum() > 0:
            r_avg = recent_s["rev_sum"].mean() if len(recent_s) > 0 else 0
            p_avg = prior_s["rev_sum"].mean()
            row["收入增长率"] = (r_avg - p_avg) / p_avg if p_avg > 0 else 0
        else:
            row["收入增长率"] = 0

    # 增长率钳制：防止极端值扭曲评分（与产品生命周期v2.9一致）
    from config.settings import PRODUCT_LIFECYCLE
    _rev_lo = PRODUCT_LIFECYCLE.get("rev_growth_lower", -1.0)
    _rev_hi = PRODUCT_LIFECYCLE.get("rev_growth_upper", 5.0)
    row["收入增长率"] = max(_rev_lo, min(row["收入增长率"], _rev_hi))

    row["ASP_加权"] = (
        row["近12月收入"] / row["近12月数量"] if row["近12月数量"] > 0 else 0
    )

    growth_tolerance = 1 - float(CUSTOMER_THRESHOLDS.get("growth_streak_tolerance", 0.05))
    monthly_rev = recent.sort_values("_月", kind='stable')["rev_sum"].values
    streak_up = 0
    streak_down = 0
    for i in range(1, len(monthly_rev)):
        # 放宽连续增长判定：环比下降不超过配置容差%仍计为增长
        if monthly_rev[i] > monthly_rev[i - 1] * growth_tolerance:
            streak_up += 1
            streak_down = 0
        elif monthly_rev[i] < monthly_rev[i - 1]:
            streak_down += 1
            streak_up = 0
    row["连续增长月数"] = streak_up
    row["连续下滑月数"] = streak_down

    # YoY同比增速：当前12月 vs 前12月（需24月数据）
    yr_ago = c_data[
        (c_data["_月"] <= (latest_month - _value_win))
        & (c_data["_月"] > (latest_month - _value_win * 2))
    ]
    yr_ago = yr_ago[yr_ago["rev_sum"] > 0]
    if len(yr_ago) >= 2 and yr_ago["rev_sum"].sum() > 0:
        yr_recent_avg = recent_months["rev_sum"].mean() if len(recent_months) > 0 else 0
        yr_prior_avg = yr_ago["rev_sum"].mean()
        row["YoY同比增速"] = (yr_recent_avg - yr_prior_avg) / yr_prior_avg if yr_prior_avg > 0 else 0
    else:
        row["YoY同比增速"] = 0

    return row


def _dim_product_coverage(cp_data):
    """产品覆盖：品种集中度Top3、品种总数。"""
    row = {}
    if len(cp_data) > 0:
        top_products = (
            cp_data.groupby("产品品种")["rev_sum"].sum().sort_values(ascending=False, kind='stable')
        )
        total_rev = top_products.sum()
        top3_rev = top_products.head(3).sum()
        row["品种集中度Top3"] = top3_rev / total_rev if total_rev > 0 else 0
        row["品种总数"] = len(top_products)
    else:
        row["品种集中度Top3"] = 0
        row["品种总数"] = 0
    return row


def _dim_product_line_distribution(cp_data, cat_col):
    """产品线分布：产品线数、主导产品线及占比、产品线HHI。"""
    row = {}
    if cat_col in cp_data.columns:
        line_rev = cp_data.groupby(cat_col)["rev_sum"].sum()
        row["产品线数"] = len(line_rev)
        line_total = line_rev.sum()
        if line_total > 0:
            line_shares = line_rev / line_total
            row["主导产品线"] = line_rev.idxmax()
            row["主导产品线占比"] = line_shares.max()
            row["产品线HHI"] = (line_shares ** 2).sum()
        else:
            row["产品线数"] = 0
            row["主导产品线"] = "无"
            row["主导产品线占比"] = 0
            row["产品线HHI"] = 1.0
    else:
        row["产品线数"] = 0
        row["主导产品线"] = "数据缺失"
        row["主导产品线占比"] = 0
        row["产品线HHI"] = 1.0
    return row



def _merge_batch_fields_fast(cid, idx_metrics):
    """快速合并：使用预索引DataFrame的O(1) .loc 查找。"""
    row = {}
    merge_specs = [
        ("intervals", ["常规平均采购间隔"]),
        ("churn", ["距上次采购天数", "采购中断预警"]),
        ("concentration", ["Top5集中度", "强依赖标记", "总采购额"]),
        ("price_bands", ["低价品种收入占比", "中价品种收入占比", "高价品种收入占比"]),
        ("category_acc", ["主导品类", "主导品类占比", "品类机会标签"]),
        ("cust_stages", ["客户生命周期"]),
        ("new_prod_cohort", ["新品采购额", "新品品种数", "新品采购占比", "是否采购新品"]),
        ("opp_signals", ["新品渗透机会", "增长动量"]),
        ("risk_signals", ["品种流失金额占比", "近半年营收跌幅"]),
    ]
    for key, fields in merge_specs:
        idx_df = idx_metrics.get(key)
        if idx_df is None:
            continue
        try:
            s = idx_df.loc[cid]
            for f in fields:
                if f in s.index:
                    row[f] = s[f]
        except (KeyError, TypeError):
            pass
    return row


def _dim_sku_dominant_stage_fast(cp_data, sku_stage_map):
    """快速SKU阶段：使用预建立的产品->阶段dict，O(1)查表。"""
    row = {}
    c_prod_names = cp_data["产品品种"].unique()
    c_stages = [sku_stage_map.get(p) for p in c_prod_names if p in sku_stage_map]
    c_stages = [s for s in c_stages if s is not None]
    if c_stages:
        dominant = pd.Series(c_stages).mode()
        row["主要SKU阶段"] = dominant.iloc[0] if len(dominant) > 0 else "未知"
    else:
        row["主要SKU阶段"] = "未知"
    return row

def _dim_asp_comparison_fast(row_in, global_asp_all, cap):
    """快速ASP对比：使用预计算的全局ASP。"""
    row = {}
    row["ASP_跌幅%%"] = ((row_in["ASP_加权"] - global_asp_all) / global_asp_all * 100
                       if global_asp_all > 0 else 0)
    row["ASP_跌幅%%"] = max(min(row["ASP_跌幅%%"], cap), -cap)
    return row

def _dim_margin_trend(row_in, c_data, latest_month):
    """毛利率跌幅%：近N月 vs 前N月毛利率变化。
    窗口长度来自 settings.py:CUSTOMER_ANALYSIS_WINDOW。"""
    row = {}
    _win = CUSTOMER_ANALYSIS_WINDOW.get("value_window_months", 12)
    prior = c_data[
        (c_data["_月"] <= (latest_month - _win)) & (c_data["_月"] > (latest_month - _win * 2))
    ]
    prior_profit = prior["profit_clip_sum"].sum()
    prior_rev = prior["rev_sum"].sum()
    prior_margin = prior_profit / prior_rev if prior_rev > 0 else 0
    cur_margin = row_in["近12月毛利率"] / 100
    row["毛利率跌幅%"] = (cur_margin - prior_margin) / prior_margin * 100 if prior_margin > 0 else 0
    return row


# ============================================================
# 主入口
# ============================================================

def calc_customer_portrait(silver: dict, source_path: str, latest_month,
                          raw_data: pd.DataFrame = None,
                          cust_info_df: pd.DataFrame = None) -> pd.DataFrame:
    """计算客户全景画像（每客户一行，60+列）。

    参数:
        silver: Silver层数据字典（customer_monthly, customer_x_product, product_monthly）
        source_path: 源Excel路径（用于读取客户信息表）
        latest_month: 最新月份（Period对象）
        raw_data: 原始交易数据（可选，避免重读Excel）
        cust_info_df: 客户信息表DataFrame（可选，避免重读Excel）

    返回:
        DataFrame: 每客户一行，包含基本信息、经营势能、产品覆盖等60+指标
    """
    cust_monthly = silver["customer_monthly"].copy()
    cust_prod = silver["customer_x_product"].copy()
    prod_monthly = silver["product_monthly"].copy()

    cat_col = CUSTOMER_COL_MAP.get("品类列", "产品一级分类")

    # 加载客户信息表（优先使用传入的DataFrame，避免重读Excel）
    if cust_info_df is not None and not cust_info_df.empty:
        cust_info = cust_info_df
    else:
        try:
            cust_info = read_excel_auto(source_path, sheet_name="客户信息表")
        except (ValueError, FileNotFoundError):
            cust_info = pd.DataFrame({"客户编号": cust_monthly["客户编号"].unique()})

    customers = cust_monthly["客户编号"].unique()

    # 从原始交易数据映射客户属性（回退补充）
    if raw_data is not None and len(raw_data) > 0:
        _attr_map = {}
        if "销售部门" in raw_data.columns:
            _dept_map = raw_data.groupby("客户编号")["销售部门"].first().to_dict()
            for cid in customers:
                dept = _dept_map.get(cid, "")
                _attr_map.setdefault(cid, {})["所属区域"] = DEPT_REGION_MAP.get(str(dept).strip(), "未知")
        if "实际业务员" in raw_data.columns:
            _owner_map = raw_data.groupby("客户编号")["实际业务员"].first().to_dict()
            for cid in customers:
                _attr_map.setdefault(cid, {})["业务负责人"] = _owner_map.get(cid, "未知")
    else:
        _attr_map = {}

    customers = cust_monthly["客户编号"].unique()

    # ---- 批量计算 ----
    metrics = _compute_batch_metrics(cust_monthly, cust_prod, prod_monthly, latest_month, cat_col)

    # ---- 预计算循环外不依赖于单个客户的值 ----
    # 全局ASP（所有产品近N月加权均价）
    _win_asp = CUSTOMER_ANALYSIS_WINDOW.get("value_window_months", 12)
    _prod_recent = prod_monthly[prod_monthly["_月"] > (latest_month - _win_asp)]
    _global_asp_all = (_prod_recent["rev_sum"].sum() / _prod_recent["qty_sum"].sum()
                       if _prod_recent["qty_sum"].sum() > 0 else 0)
    _asp_cap = METRIC_CAPS.get("asp_decline_max_pct", 100)

    # 预建立SKU阶段映射（产品->阶段，避免每客户scan全表）
    _sku_stage_map = {}
    if "sku_stages" in metrics and "产品品种" in metrics["sku_stages"].columns:
        _sku_stage_df = metrics["sku_stages"]
        if "SKU生命周期阶段" in _sku_stage_df.columns:
            _sku_stage_map = _sku_stage_df.set_index("产品品种")["SKU生命周期阶段"].to_dict()

    # 预索引批处理DataFrame（避免循环内重复boolean mask）
    _idx_metrics = {}
    for _key in ["intervals", "churn", "concentration", "price_bands",
                 "category_acc", "cust_stages", "new_prod_cohort",
                 "opp_signals", "risk_signals"]:
        if _key in metrics and "客户编号" in metrics[_key].columns:
            _idx_metrics[_key] = metrics[_key].set_index("客户编号")

    # ---- 逐个客户计算维度指标 ----
    results = []
    for cid in customers:
        row = {"客户编号": cid}
        c_mask = cust_monthly["客户编号"] == cid
        c_data = cust_monthly[c_mask].sort_values("_月", kind='stable')
        cp_mask = cust_prod["客户编号"] == cid
        cp_data = cust_prod[cp_mask]

        # 各维度计算
        row.update(_dim_base_info(cid, cust_info, raw_data, _attr_map))
        row.update(_dim_momentum(c_data, latest_month))
        row.update(_dim_product_coverage(cp_data))
        row.update(_dim_product_line_distribution(cp_data, cat_col))
        # 使用预索引的DataFrame进行O(1)查找
        row.update(_merge_batch_fields_fast(cid, _idx_metrics))
        row.update(_dim_sku_dominant_stage_fast(cp_data, _sku_stage_map))
        row.update(_dim_asp_comparison_fast(row, _global_asp_all, _asp_cap))
        row.update(_dim_margin_trend(row, c_data, latest_month))

        results.append(row)

    result_df = pd.DataFrame(results)
    return result_df
