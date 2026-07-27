"""
客户评价体系评分模块（v2.0） — 与客户分析解耦版本。

P2-E: 从 customer_analysis/scoring.py 提取。

5 维度评分卡：
  价值贡献(35%) + 增长动能(25%) + 稳定关系(20%) + 战略潜力(15%) + 效率运营(5%)

三独立评级：
  综合价值分 → S/A/B/C
  机会评级 → 极高/高/中/低
  风险评级 → 极高/高/中/低

双轴矩阵：
  价值贡献 × 增长动能 → 明星/金牛/培育/瘦狗
"""

import os
import sys
import pandas as pd
import numpy as np

from config.settings import (
    SCORE_DIMENSION_WEIGHTS,
    SCORE_SUB_WEIGHTS,
    SCORE_TIER_THRESHOLDS,
    CUSTOMER_TIER_MAP,
    SCORE_REVERSE_INDICATORS,
    SCORE_LIFECYCLE_MAP,
    SCORE_STABILITY_MAP,
    SCORE_TIER_SCORE_MAP,
    SCORE_INACTIVE_DEFAULT,
    SCORE_OPPORTUNITY_BLEND_WEIGHTS,
    SCORE_RISK_BLEND_WEIGHTS,
    CHURN_WARNING_TRUE_VALUES,
)


# ============================================================
# 辅助函数
# ============================================================

def _minmax_norm(s: pd.Series, reverse: bool = False) -> pd.Series:
    """Min-Max 归一化到 [0, 100]。缺失值不参与极值计算。

    调用方约定: 入参中 NaN 为缺失值(非活跃客户或数据缺失指标)，
    这些值不参与 min/max 计算，归一化后仍保持 NaN，
    由调用方在累加时通过 fillna(0) 处理。
    """
    if not pd.api.types.is_numeric_dtype(s):
        s = pd.to_numeric(s, errors="coerce")
    if s.dtype == bool:
        s = s.astype(int)
    valid = s.notna()
    if valid.sum() >= 2 and s[valid].max() > s[valid].min():
        norm = (s - s[valid].min()) / (s[valid].max() - s[valid].min()) * 100
        return 100 - norm if reverse else norm
    return pd.Series(50.0, index=s.index)


def _tier_from_score(score, tiers: dict, reverse: bool = False) -> str:
    """将分数映射为等级（按阈值降序匹配）。"""
    sorted_tiers = sorted(tiers.items(), key=lambda x: x[1], reverse=True)
    for label, threshold in sorted_tiers:
        if score >= threshold:
            return label
    return list(tiers.keys())[-1]


# ============================================================
# 维度评分计算
# ============================================================

def _score_dimension(
    df: pd.DataFrame, dim_key: str, active_mask: pd.Series = None,
) -> pd.Series:
    """计算单个维度的评分（子指标加权 Min-Max → 0-100）。"""
    sub_weights = SCORE_SUB_WEIGHTS.get(dim_key, {})
    if not sub_weights:
        return pd.Series(0.0, index=df.index)

    total = pd.Series(0.0, index=df.index)
    weight_sum = 0
    for indicator, w in sub_weights.items():
        if indicator not in df.columns:
            continue
        reverse = indicator in SCORE_REVERSE_INDICATORS
        raw = df[indicator]
        if active_mask is not None and active_mask.sum() > 1:
            norm = _minmax_norm(raw.where(active_mask, float("nan")), reverse=reverse)
            norm[~active_mask] = SCORE_INACTIVE_DEFAULT
        else:
            norm = _minmax_norm(raw, reverse=reverse)
        total += norm.fillna(0) * w
        weight_sum += w

    if weight_sum > 0:
        return total / weight_sum
    return pd.Series(0.0, index=df.index)


def _map_lifecycle_to_score(s: pd.Series) -> pd.Series:
    """客户生命周期 → 数值评分（越高越稳定）。"""
    return s.map(SCORE_LIFECYCLE_MAP).fillna(50)


def _map_stability_level_to_score(s: pd.Series) -> pd.Series:
    """稳定性等级 → 数值评分。"""
    return s.map(SCORE_STABILITY_MAP).fillna(50)


def _map_tier_to_score(s: pd.Series) -> pd.Series:
    """客户层级 → 数值评分。"""
    return s.map(SCORE_TIER_SCORE_MAP).fillna(50)


# ============================================================
# 主入口：综合评分
# ============================================================

def calc_composite_scores(df: pd.DataFrame) -> pd.DataFrame:
    """计算 5 维度评分、综合价值分、机会评级、风险评级、双轴矩阵。

    输入：calc_customer_portrait() 输出的客户全景 DataFrame（每客户一行）
    输出：增加了以下字段的 DataFrame：
        - 价值贡献分, 增长动能分, 稳定关系分, 战略潜力分, 效率运营分
        - 综合价值分, 综合价值层级 (S/A/B/C)
        - 机会评级分, 机会评级 (极高/高/中/低)
        - 风险评级分, 风险评级 (极高/高/中/低)
        - 双轴分类 (明星/金牛/培育/瘦狗)
    """
    result = df.copy()

    # ---- 活跃客户标记（v4.4: 三级分级） ----
    revenue = result["近12月收入"].fillna(0) if "近12月收入" in result.columns else pd.Series(0, index=result.index)
    # P25 threshold for "active" (meaningful revenue)
    active_p25 = revenue[revenue > 0].quantile(0.25) if (revenue > 0).sum() > 0 else 1
    # active_mask: used for min-max normalization (unchanged: any transaction = participate)
    active_mask = revenue > 0

    # ---- 预处理：分类字段数值化 ----
    if "客户生命周期" in result.columns:
        result["_生命周期分值"] = _map_lifecycle_to_score(result["客户生命周期"])

    if "稳定性等级" in result.columns:
        result["_稳定性等级分值"] = _map_stability_level_to_score(result["稳定性等级"])

    if "客户层级" in result.columns:
        result["_客户层级分值"] = _map_tier_to_score(result["客户层级"])

    # 采购中断预警：bool/str → 0/100（反向指标，100=有预警=差）
    if "采购中断预警" in result.columns:
        result["_采购中断预警分值"] = result["采购中断预警"].map(
            lambda x: 100 if x in CHURN_WARNING_TRUE_VALUES else 0,
        ).fillna(0)

    # 收入CV：如果没有现成字段，检查是否有 volatility 模块输出的 CV
    if "收入CV" not in result.columns and "收入CV_月度金额" in result.columns:
        result["收入CV"] = result["收入CV_月度金额"]

    # 新品品种数：如果没有默认0
    if "新品品种数" not in result.columns:
        result["新品品种数"] = 0

    # 在采品种数（品种广度）：回退到品种总数
    if "在采品种数" not in result.columns:
        if "品种总数" in result.columns:
            result["在采品种数"] = result["品种总数"]

    # 效率运营：从估算真实利润结果中取订单处理成本率
    if "订单处理成本" in result.columns and "近12月收入" in result.columns:
        rev_safe = result["近12月收入"].replace(0, float("nan"))
        result["订单处理成本率"] = (result["订单处理成本"] / rev_safe * 100).fillna(0)

    # ---- 计算各维度评分 ----
    dimensions = ["value", "growth", "stability", "potential", "efficiency"]
    dim_col_map = {
        "value": "价值贡献分",
        "growth": "增长动能分",
        "stability": "稳定关系分",
        "potential": "战略潜力分",
        "efficiency": "效率运营分",
    }

    for dim_key, col_name in dim_col_map.items():
        result[col_name] = _score_dimension(result, dim_key, active_mask)

    # ---- 综合价值分 ----
    dim_w = SCORE_DIMENSION_WEIGHTS
    composite = pd.Series(0.0, index=result.index)
    for dim_key, col_name in dim_col_map.items():
        composite += result[col_name].fillna(0) * dim_w.get(dim_key, 0)

    result["综合价值分"] = composite.round(1)

    # 综合价值层级
    tier_map = SCORE_TIER_THRESHOLDS.get(
        "composite", {"S": 36, "A": 30, "B": 26, "C": 0},
    )
    result["综合价值层级"] = result["综合价值分"].apply(
        lambda x: _tier_from_score(x, tier_map),
    )

    # ---- 活跃状态标记 + 非活跃客户层级覆写（v4.4: 三级分级） ----
    # 非活跃（收入=0）→ "休眠"; 微量活跃（0<收入<P25）→ "微量活跃"; 活跃（收入≥P25）→ "活跃"
    result["活跃状态"] = "活跃"
    result.loc[(revenue > 0) & (revenue < active_p25), "活跃状态"] = "微量活跃"
    result.loc[revenue == 0, "活跃状态"] = "非活跃"
    # 将非活跃客户的综合价值层级覆写为"休眠"
    inactive_mask = revenue == 0
    inactive_labels = result.loc[inactive_mask, "综合价值层级"].value_counts()
    if len(inactive_labels) > 0:
        micro_count = ((revenue > 0) & (revenue < active_p25)).sum()
        active_count = (revenue >= active_p25).sum()
        print(f"  [活跃标记] 非活跃->休眠: {dict(inactive_labels)} 微量活跃(P25={active_p25:.0f}): {micro_count}人 活跃: {active_count}人")
    result.loc[inactive_mask, "综合价值层级"] = "休眠"

    # ---- 机会评级（增长动能×权重 + 战略潜力×权重） ----
    _opp_weights = SCORE_OPPORTUNITY_BLEND_WEIGHTS
    opportunity_score = (
        result["增长动能分"].fillna(0) * _opp_weights.get("growth", 0.60)
        + result["战略潜力分"].fillna(0) * _opp_weights.get("potential", 0.40)
    )
    result["机会评级分"] = opportunity_score.round(1)
    opp_tier = SCORE_TIER_THRESHOLDS.get(
        "opportunity", {"极高": 27, "高": 20, "中": 13, "低": 0},
    )
    result["机会评级"] = result["机会评级分"].apply(
        lambda x: _tier_from_score(x, opp_tier),
    )

    # ---- 风险评级（(100-稳定关系)×权重 + (100-效率运营)×权重） ----
    _risk_weights = SCORE_RISK_BLEND_WEIGHTS
    risk_score = (
        (100 - result["稳定关系分"].fillna(0))
        * _risk_weights.get("stability", 0.70)
        + (100 - result["效率运营分"].fillna(0))
        * _risk_weights.get("efficiency", 0.30)
    )
    result["风险评级分"] = risk_score.round(1)
    risk_tier = SCORE_TIER_THRESHOLDS.get(
        "risk", {"极高": 70, "高": 50, "中": 20, "低": 0},
    )
    result["风险评级"] = result["风险评级分"].apply(
        lambda x: _tier_from_score(x, risk_tier),
    )

    # ---- 双轴矩阵（v4.4: 非活跃客户排除+重命名）----
    value_threshold = (
        result.loc[active_mask, "价值贡献分"].median()
        if active_mask.sum() > 0 else 50
    )
    growth_threshold = (
        result.loc[active_mask, "增长动能分"].median()
        if active_mask.sum() > 0 else 50
    )
    result["双轴分类"] = result.apply(
        lambda r: _classify_dual_axis(r, value_threshold, growth_threshold,
                                       is_active=r.get("近12月收入", 0) > 0),
        axis=1,
    )

    # ---- 清理临时字段 ----
    _temp_cols = [c for c in result.columns if c.startswith("_")]
    result = result.drop(columns=_temp_cols, errors="ignore")

    return result


def _classify_dual_axis(row, value_threshold=None, growth_threshold=None, is_active=True) -> str:
    """依据价值贡献分和增长动能分进行双轴分类。

    v4.4: 非活跃客户单独标记，四象限重命名为明星/潜力/金牛/瘦狗。
    """
    if not is_active:
        return "非活跃客户"
    value_score = row.get("价值贡献分", 50)
    growth_score = row.get("增长动能分", 50)
    v_thr = value_threshold if value_threshold is not None else 50
    g_thr = growth_threshold if growth_threshold is not None else 50

    if value_score >= v_thr and growth_score >= g_thr:
        return "明星(高价值高增长)"
    elif value_score < v_thr and growth_score >= g_thr:
        return "潜力(低价值高增长)"
    elif value_score >= v_thr and growth_score < g_thr:
        return "金牛(高价值低增长)"
    else:
        return "瘦狗(低价值低增长)"


# ============================================================
# 客户层级取数
# ============================================================

def calc_customer_tier(df: pd.DataFrame) -> pd.DataFrame:
    """计算客户层级（KA/AA/KM/MM）。

    取数规则（降序）：
      1. 如果"客户层级"列已存在且有非空值 → 直接填充默认值后返回
      2. 否则从终端客户主数据的"客户类别"字段通过 keyword 映射
      3. 均无可映射 → "未分类"

    参数:
        df: 已整合终端客户主数据的客户全景 DataFrame

    返回:
        增加了"客户层级"字段的 DataFrame
    """
    result = df.copy()
    tier_map = CUSTOMER_TIER_MAP
    tier_default = tier_map.get("default", "未分类")

    if "客户层级" in result.columns and result["客户层级"].notna().any():
        result["客户层级"] = result["客户层级"].fillna(tier_default)
        return result

    tier_cols = [
        c for c in result.columns
        if (c.startswith("终端") and "客户类别" in c) or c == "客户类别"
    ]
    if tier_cols:
        src_col = tier_cols[0]
        mapping = tier_map.get("mapping", {})
        result["客户层级"] = result[src_col].map(
            lambda x: next(
                (v for k, v in mapping.items()
                 if pd.notna(x) and k in str(x)),
                tier_default,
            )
        ).fillna(tier_default)
        return result

    result["客户层级"] = tier_default
    return result


# ═══════════════════════════════════════════════════════════════
# 帕累托利润分级 (v4.8: 方案A+B)
# ═══════════════════════════════════════════════════════════════

def calc_pareto_profit_tier(df: pd.DataFrame) -> pd.DataFrame:
    """基于近12月毛利的累计占比，给活跃客户打ABCD帕累托标签。

    A级: 累计利润≤70% → 核心利润贡献者 (~3%客户)
    B级: 70-90% → 重要贡献者 (~10%)
    C级: 90-99% → 一般贡献者 (~25%)
    D级: >99% 或 非活跃 → 低利润 (~62%)

    阈值从 config.PARETO_PROFIT_TIERS 读取，可配置。
    """
    from config.settings_customer import PARETO_PROFIT_TIERS
    result = df.copy()
    a_cut = PARETO_PROFIT_TIERS.get("A级累计上限", 70)
    b_cut = PARETO_PROFIT_TIERS.get("B级累计上限", 90)
    c_cut = PARETO_PROFIT_TIERS.get("C级累计上限", 99)

    active_mask = (result.get("近12月收入", 0).fillna(0) > 0)
    active = result[active_mask].copy()
    if len(active) == 0:
        result["帕累托利润分级"] = "D级"
        return result

    profit_sorted = active.sort_values("近12月毛利", ascending=False)
    total_profit = profit_sorted["近12月毛利"].sum()
    if total_profit <= 0:
        result["帕累托利润分级"] = "D级"
        return result

    cumsum_pct = profit_sorted["近12月毛利"].cumsum() / total_profit * 100
    tier_map = {}
    for i, (idx, cum) in enumerate(zip(profit_sorted.index, cumsum_pct)):
        if cum <= a_cut:
            tier_map[idx] = "A级"
        elif cum <= b_cut:
            tier_map[idx] = "B级"
        elif cum <= c_cut:
            tier_map[idx] = "C级"
        else:
            tier_map[idx] = "D级"

    result["帕累托利润分级"] = "D级"
    result.loc[active_mask, "帕累托利润分级"] = result.loc[active_mask].index.map(
        lambda i: tier_map.get(i, "D级")
    )
    n_a = (result["帕累托利润分级"] == "A级").sum()
    n_b = (result["帕累托利润分级"] == "B级").sum()
    n_c = (result["帕累托利润分级"] == "C级").sum()
    n_d = (result["帕累托利润分级"] == "D级").sum()
    print(f"  [帕累托利润分级] A:{n_a} B:{n_b} C:{n_c} D:{n_d} (阈值A≤{a_cut}% B≤{b_cut}% C≤{c_cut}%)")
    return result
