"""
RFM-π 评分模型（B2B 芯片行业适配版）。

P2-E: 从 customer_analysis/models.py 提取，与客户分析解耦。

支持渠道隔离评分：各渠道独立进行五分位排名，使用渠道特定权重，
避免代理客户因采购特征差异在混合评分中全面偏低。
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
    """RFM-π 评分（B2B 芯片行业适配版）。

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
        增加了评分列的 DataFrame
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
                    q = pd.qcut(
                        sub[col].rank(method="dense"), 5,
                        labels=labels, duplicates="drop",
                    )
                    sub[score_name] = q.astype('Int64').fillna(3).astype(int)
                except ValueError:
                    sub[score_name] = 3
            else:
                sub[score_name] = 3
        sub["RFMπ_综合分"] = (
            sub["R_得分"] * w_r + sub["F_得分"] * w_f
            + sub["M_得分"] * w_m + sub["P_得分"] * w_p
        )
        return sub

    result = customers.copy()

    if channel_col and channel_col in result.columns and weights_by_channel:
        # 渠道隔离评分
        all_scored = []
        for channel, w in weights_by_channel.items():
            mask = result[channel_col] == channel
            if mask.sum() >= 5:
                scored = _score_subset(
                    result[mask],
                    w.get("R", 0.30), w.get("F", 0.20),
                    w.get("M", 0.30), w.get("P", 0.20),
                )
            else:
                print(f"  [RFM-π] 渠道'{channel}'仅{mask.sum()}个客户(<5)，回落统一评分权重")
                scored = _score_subset(
                    result[mask], r_weight, f_weight, m_weight, p_weight,
                )
            all_scored.append(scored)

        known_channels = list(weights_by_channel.keys())
        other_mask = ~result[channel_col].isin(known_channels)
        if other_mask.any():
            scored_other = _score_subset(
                result[other_mask], r_weight, f_weight, m_weight, p_weight,
            )
            all_scored.append(scored_other)

        result = pd.concat(all_scored)
    else:
        result = _score_subset(
            result, r_weight, f_weight, m_weight, p_weight,
        )

    from config.settings import RFM_PI_TIERS as _RFM_TIERS

    _tier_thresholds = (
        _RFM_TIERS if _RFM_TIERS else {"S": 4.0, "A": 3.5, "B": 2.5, "C": 0}
    )

    def _tier(score):
        if score >= _tier_thresholds.get("S", 4.0):
            return "S级"
        elif score >= _tier_thresholds.get("A", 3.5):
            return "A级"
        elif score >= _tier_thresholds.get("B", 2.5):
            return "B级"
        else:
            return "C级"

    result["RFMπ_层级"] = result["RFMπ_综合分"].apply(_tier)
    return result
