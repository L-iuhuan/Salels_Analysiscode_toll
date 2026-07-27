"""
客户分析评分模型。

包含RFM-π评分、机会/风险评分的核心计算逻辑。
（回款信用评分已废弃：客户整体回款状况好，不分层）
"""

import numpy as np
import pandas as pd


def _normalize_0_100(s):
    if s.max() > s.min():
        return (s - s.min()) / (s.max() - s.min()) * 100
    return pd.Series([50] * len(s), index=s.index)


def score_rfm_pi(
    customers: pd.DataFrame,
    r_col: str = "距上次采购天数",
    f_col: str = "常规平均采购间隔",
    m_col: str = "近12月毛利",
    p_col: str = "新品采购占比",
    r_weight: float = 0.30,
    f_weight: float = 0.20,
    m_weight: float = 0.30,
    p_weight: float = 0.20,
    channel_col: str = None,
    weights_by_channel: dict = None,
) -> pd.DataFrame:
    """RFM-π评分（B2B芯片行业适配版）。

    支持渠道隔离评分：各渠道独立进行五分位排名，使用渠道特定权重，
    避免代理客户因采购特征差异在混合评分中全面偏低。

    参数:
        customers: 客户数据表（每客户一行）
        r/f/m/p_col: 各维度列名
        r/f/m/p_weight: 各维度默认权重
        channel_col: 渠道列名（如"渠道类型"），启用渠道隔离
        weights_by_channel: 渠道权重字典
            {"渠道名": {"R": 0.30, "F": 0.20, "M": 0.30, "P": 0.20}}
            每渠道客户数 < 5 时回落为默认权重

    返回:
        增加了评分列的DataFrame
    """

    def _score_subset(df, w_r, w_f, w_m, w_p):
        """对子集执行五分位评分（内部函数）。"""
        sub = df.copy()
        dims = [
            (r_col, True, "R_得分"),
            (f_col, True, "F_得分"),
            (m_col, False, "M_得分"),
            (p_col, False, "P_得分"),
        ]
        for col, asc, score_name in dims:
            if col in sub.columns and sub[col].nunique() > 1:
                labels = [5, 4, 3, 2, 1] if asc else [1, 2, 3, 4, 5]
                try:
                    sub[score_name] = pd.qcut(
                        sub[col].rank(method="first"), 5,
                        labels=labels, duplicates="drop",
                    ).astype(int)
                except ValueError:
                    sub[score_name] = 3
            else:
                sub[score_name] = 3
        sub["RFMπ_综合分"] = sub["R_得分"] * w_r + sub["F_得分"] * w_f + sub["M_得分"] * w_m + sub["P_得分"] * w_p
        return sub

    result = customers.copy()

    if channel_col and channel_col in result.columns and weights_by_channel:
        # ---- 渠道隔离评分 ----
        all_scored = []
        for channel, w in weights_by_channel.items():
            mask = result[channel_col] == channel
            if mask.sum() >= 5:  # 最少5客户才有统计意义
                scored = _score_subset(
                    result[mask],
                    w.get("R", 0.30), w.get("F", 0.20),
                    w.get("M", 0.30), w.get("P", 0.20),
                )
            else:
                # 不足5客户时使用默认权重
                scored = _score_subset(result[mask], r_weight, f_weight, m_weight, p_weight)
            all_scored.append(scored)

        # 未在权重表中定义的渠道
        known_channels = list(weights_by_channel.keys())
        other_mask = ~result[channel_col].isin(known_channels)
        if other_mask.any():
            scored_other = _score_subset(result[other_mask], r_weight, f_weight, m_weight, p_weight)
            all_scored.append(scored_other)

        result = pd.concat(all_scored)
    else:
        # ---- 统一评分（原有逻辑） ----
        dims = [
            (r_col, True, "R_得分"),
            (f_col, True, "F_得分"),
            (m_col, False, "M_得分"),
            (p_col, False, "P_得分"),
        ]
        for col, asc, score_name in dims:
            if col in result.columns and result[col].nunique() > 1:
                labels = [5, 4, 3, 2, 1] if asc else [1, 2, 3, 4, 5]
                try:
                    result[score_name] = pd.qcut(
                        result[col].rank(method="first"), 5,
                        labels=labels, duplicates="drop",
                    ).astype(int)
                except ValueError:
                    result[score_name] = 3
            else:
                result[score_name] = 3
        result["RFMπ_综合分"] = (
            result["R_得分"] * r_weight
            + result["F_得分"] * f_weight
            + result["M_得分"] * m_weight
            + result["P_得分"] * p_weight
        )

    def _tier(score):
        if score >= 4.0:
            return "S级"
        elif score >= 3.5:
            return "A级"
        elif score >= 2.5:
            return "B级"
        else:
            return "C级"

    result["RFMπ_层级"] = result["RFMπ_综合分"].apply(_tier)
    return result


def score_opportunity(
    customers: pd.DataFrame,
    scale_col: str = "近12月收入",
    growth_col: str = "增长动量",
    margin_col: str = "近12月毛利率",
    new_product_col: str = "新品采购占比",
    breadth_col: str = "在采品种数",
    scale_weight: float = 0.25,
    growth_weight: float = 0.25,
    margin_weight: float = 0.20,
    new_product_weight: float = 0.15,
    breadth_weight: float = 0.15,
) -> pd.DataFrame:
    """机会评分（0-100）。"""
    result = customers.copy()

    elements = [
        (scale_col, scale_weight),
        (growth_col, growth_weight),
        (margin_col, margin_weight),
        (new_product_col, new_product_weight),
        (breadth_col, breadth_weight),
    ]

    total_score = pd.Series(0.0, index=result.index)
    for col, weight in elements:
        if col not in result.columns:
            continue
        s = result[col].fillna(0)
        if not pd.api.types.is_numeric_dtype(s):
            s = pd.to_numeric(s, errors="coerce").fillna(0)
        if s.dtype == bool:
            s = s.astype(int)
        if s.max() > s.min():
            normalized = (s - s.min()) / (s.max() - s.min()) * 100
        else:
            normalized = pd.Series(0.0, index=result.index)
        total_score += normalized * weight

    result["机会分"] = total_score.round(1)

    def _tier(score):
        if score >= 80:
            return "极高"
        elif score >= 60:
            return "高"
        elif score >= 40:
            return "中"
        else:
            return "低"

    result["机会等级"] = result["机会分"].apply(_tier)
    return result


def score_risk(
    customers: pd.DataFrame,
    decline_months_col: str = "连续下滑月数",
    asp_decline_col: str = "ASP_跌幅%",
    margin_decline_col: str = "毛利率跌幅%",
    concentration_col: str = "强依赖标记",
    churn_warning_col: str = "采购中断预警",
    decline_weight: float = 0.30,
    asp_weight: float = 0.20,
    margin_weight: float = 0.20,
    concentration_weight: float = 0.15,
    churn_weight: float = 0.15,
) -> pd.DataFrame:
    """风险评分（0-100）。"""
    result = customers.copy()

    elements = [
        (decline_months_col, decline_weight, True),
        (asp_decline_col, asp_weight, True),
        (margin_decline_col, margin_weight, True),
        (concentration_col, concentration_weight, True),
        (churn_warning_col, churn_weight, True),
    ]

    total_score = pd.Series(0.0, index=result.index)
    for col, weight, higher_is_riskier in elements:
        if col not in result.columns:
            continue
        s = result[col].fillna(0)
        if not pd.api.types.is_numeric_dtype(s):
            s = pd.to_numeric(s, errors="coerce").fillna(0)
        if s.dtype == bool:
            s = s.astype(int)
        if s.max() > s.min():
            normalized = (s - s.min()) / (s.max() - s.min()) * 100
        else:
            normalized = pd.Series(0.0, index=result.index)
        total_score += normalized * weight

    result["风险分"] = total_score.round(1)

    def _tier(score):
        if score >= 80:
            return "极高"
        elif score >= 60:
            return "高"
        elif score >= 30:
            return "中"
        else:
            return "低"

    result["风险等级"] = result["风险分"].apply(_tier)
    return result
