"""
风险评分函数 — v4.0 4因子模型 (优化版)。

因子: 毛利率趋势斜率, 增速衰减(数据驱动矩阵), 自比健康度(修复顶部反转), 订货量变化(新增)。

v4.0变更:
1. 毛利率斜率: 合并冗余20/50分桶 → 统一50分
2. 增速衰减: 数据驱动评分矩阵替代原增长率感知逻辑（修复评分反转）
3. 自比健康度: 修复顶部反转（<30%时从90分降为70分）
4. 订货量变化: 分桶映射（非线性关系处理）
5. 权重: 毛利率斜率=0.100, 增速衰减=0.600, 自比健康度=0.200, 订货量变化=0.100
6. 阈值: 低≤55, 中≤65, 高≤68, >68=极高

v2.9旧函数保留用作向后兼容。
"""

import pandas as pd
import numpy as np

# ─────────────────────────────────────────────────────────────────
# v4.0: 新评分函数
# ─────────────────────────────────────────────────────────────────

# 增速衰减评分矩阵 (数据驱动): (yoy_group, decay_group) → score
_DECAY_SCORE_MATRIX = {
    ("high_growth", "accelerating"): 20,
    ("high_growth", "stable"):       10,
    ("high_growth", "decelerating"): 10,
    ("growing",     "accelerating"): 40,
    ("growing",     "stable"):       30,
    ("growing",     "decelerating"): 20,
    ("flat",        "accelerating"): 70,
    ("flat",        "stable"):       60,
    ("flat",        "decelerating"): 50,
    ("shrinking",   "accelerating"): 80,
    ("shrinking",   "stable"):       80,
    ("shrinking",   "decelerating"): 70,
}

# 连续下降月加成
_CONSECUTIVE_BONUS_PER_MONTH = 5
_CONSECUTIVE_BONUS_MAX = 25

# 毛利率斜率分桶 (合并20/50)
_F1F_BUCKETS = [
    (0.0,      np.inf,  10),
    (-0.008,   0.0,     50),
    (-np.inf, -0.008,   80),
]

# F5 分桶 (修复顶部反转: <30% = 70分, 非90分)
_F5_BUCKETS = [
    (0.70, np.inf, 10),
    (0.50, 0.70,   40),
    (0.30, 0.50,   70),
    (-np.inf, 0.30, 70),
]

# c6 分桶
_C6_BUCKETS = [
    (-np.inf, -0.5,  95),
    (-0.5,    -0.2,  75),
    (-0.2,     0.0,  50),
    (0.0,      np.inf, 25),
]


def score_slope_v2(slope_ratio, zero_profit=False, slope_insufficient=False):
    """F1f v2: 毛利率趋势斜率评分。

    合并冗余20/50分桶，经验衰减率:
        slope > 0:      13.0% → 10分
        -0.008~0:       15.7% → 50分 (原20+50合并，含slope=0)
        < -0.008:       26.1% → 80分

    返回: [10, 50, 80] 之一
    """
    if zero_profit or slope_insufficient:
        return 80
    if slope_ratio is None or (isinstance(slope_ratio, float) and np.isnan(slope_ratio)):
        return 50
    for lo, hi, score in _F1F_BUCKETS:
        if lo < slope_ratio <= hi:
            return score
    return 50


def _classify_yoy_group(yoy_change):
    if yoy_change is None or pd.isna(yoy_change):
        return "unknown"
    if yoy_change > 0.5:
        return "high_growth"
    elif yoy_change > 0:
        return "growing"
    elif yoy_change > -0.1:
        return "flat"
    else:
        return "shrinking"


def _classify_decay_group(decay_pp):
    if decay_pp is None or pd.isna(decay_pp):
        return "unknown"
    if decay_pp > 0:
        return "accelerating"
    elif decay_pp >= -10:
        return "stable"
    else:
        return "decelerating"


def score_decay_v2(decay_pp, yoy_change, consecutive_months=0):
    """F4 v2: 增速衰减评分（数据驱动矩阵）。

    使用经验校准的评分矩阵，修复原v2.9增长率感知逻辑的评分反转。

    参数:
        decay_pp: 增速衰减(pp)，负=减速
        yoy_change: 同比增长率(ratio)
        consecutive_months: 连续下降月数(加成)

    返回: 10~100
    """
    if pd.isna(decay_pp) or decay_pp is None:
        return 20
    yoy_grp = _classify_yoy_group(yoy_change)
    decay_grp = _classify_decay_group(decay_pp)
    score = _DECAY_SCORE_MATRIX.get((yoy_grp, decay_grp), 50)
    if consecutive_months and consecutive_months > 0:
        bonus = min(consecutive_months * _CONSECUTIVE_BONUS_PER_MONTH,
                    _CONSECUTIVE_BONUS_MAX)
        score = min(100, score + bonus)
    return score


def score_self_health_v2(health_pct, hist_margin_invalid=False):
    """F5 v2: 自比健康度评分（修复顶部反转）。

    经验衰减率:
        SH>70%:  11.3% → 10分
        50~70%:  27.1% → 40分 (含SH=70%)
        30~50%:  37.0% → 70分 (实际最高风险!)
        <30%:    35.3% → 70分 (从90降为70)

    返回: [10, 40, 50, 70]
    """
    if hist_margin_invalid:
        return 50
    if health_pct is None or pd.isna(health_pct):
        return 50
    for lo, hi, score in _F5_BUCKETS:
        if lo < health_pct <= hi:
            return score
    return 50


def score_c6_v2(c6_raw):
    """c6 v2: 大客户单次订货量变化评分。

    经验衰减率:
        c6<=-0.5: 45.2% → 95分
        -0.5~-0.2: 21.3% → 75分
        -0.2~0:   17.4% → 50分
        >0:       ~15%  → 25分

    缺失时返回 0 (零填充，权重重分配).
    返回: [0, 25, 50, 75, 95]
    """
    if c6_raw is None or pd.isna(c6_raw):
        return 0
    for lo, hi, score in _C6_BUCKETS:
        if lo < c6_raw <= hi:
            return score
    return 25


def compute_composite_v2(slope_ratio, decay_pp, yoy_change, self_health,
                         consecutive_months=0, c6_raw=None, c6_available=False,
                         zero_profit=False, slope_insufficient=False,
                         hist_margin_invalid=False, weights=None):
    """v4.0 composite: 可靠性感知的加权综合评分。

    weights默认: {"F1f": 0.100, "F4": 0.600, "F5": 0.200, "c6": 0.100}
    不可靠因子权重自动重分配至可靠因子。

    返回dict: {score_v2, f1f_v2, f4_v2, f5_v2, c6_v2, factor_weights}
    """
    if weights is None:
        weights = {"F1f": 0.100, "F4": 0.600, "F5": 0.200, "c6": 0.100}

    s1 = score_slope_v2(slope_ratio, zero_profit=zero_profit,
                        slope_insufficient=slope_insufficient)
    s4 = score_decay_v2(decay_pp, yoy_change, consecutive_months=consecutive_months)
    s5 = score_self_health_v2(self_health, hist_margin_invalid=hist_margin_invalid)

    w_f1f = float(weights.get("F1f", 0.100))
    w_f4 = float(weights.get("F4", 0.600))
    w_f5 = float(weights.get("F5", 0.200))

    w = [w_f1f, w_f4, w_f5]
    scores = [s1, s4, s5]
    reliable = [
        not zero_profit and not slope_insufficient,
        True,  # decay always available with panel
        not hist_margin_invalid,
    ]
    for idx in range(3):
        if not reliable[idx]:
            w[idx] = 0.0

    c6_on = bool(c6_available) and bool(weights.get("c6", 0))
    s_c6 = score_c6_v2(c6_raw) if c6_on else 0
    if c6_on:
        w.append(float(weights.get("c6", 0.100)))
        scores.append(s_c6)

    sum_w = sum(w)
    if sum_w > 0:
        w = [wi / sum_w for wi in w]
    else:
        w = [1.0 / len(w)] * len(w)

    total = sum(s * wi for s, wi in zip(scores, w))

    result = {
        "score_v2": round(total, 1),
        "f1f_v2": s1,
        "f4_v2": s4,
        "f5_v2": s5,
        "c6_v2": s_c6,
        "factor_weights": {
            "F1f": w[0],
            "F4": w[1] if len(w) > 1 else 0,
            "F5": w[2] if len(w) > 2 else 0,
        },
    }
    if len(w) > 3:
        result["factor_weights"]["c6"] = w[3]
    return result


# ─────────────────────────────────────────────────────────────────
# v2.9 旧函数（向后兼容，标记为deprecated）
# ─────────────────────────────────────────────────────────────────

def risk_slope(slope_ratio, thr, zero_profit=False):
    """因子1：毛利率趋势斜率 → 风险得分（0~100）。[deprecated v2.9]
    请使用 score_slope_v2().
    """
    if zero_profit:
        return 80
    t_low = float(thr.get("slope_low_pct", 0)) / 100
    t_mid = float(thr.get("slope_mid_pct", -0.3)) / 100
    t_high = float(thr.get("slope_high_pct", -0.8)) / 100
    default = int(thr.get("slope_default_score", 80))
    if slope_ratio >= t_low:
        return 10
    elif slope_ratio > t_mid:
        return 20
    elif slope_ratio > t_high:
        return 50
    else:
        return default


def risk_cv(cv_val, thr):
    """因子3：订货波动性CV → 风险得分 (v3.1已移除)。[deprecated]
    """
    if pd.isna(cv_val) or (isinstance(cv_val, float) and np.isinf(cv_val)):
        return int(thr.get("cv_default_score", 85))
    t_low = float(thr.get("cv_low", 0.5))
    t_mid = float(thr.get("cv_mid", 1.0))
    t_high = float(thr.get("cv_high", 1.5))
    default = int(thr.get("cv_default_score", 85))
    if cv_val < t_low:
        return 10
    elif cv_val < t_mid:
        return 40
    elif cv_val < t_high:
        return 65
    else:
        return default


def risk_decay(decay_val, yoy_change, thr):
    """因子4：增速衰减 → 风险得分（v2.9增长率感知4代算法）。[deprecated v2.9]
    请使用 score_decay_v2().
    """
    t_yoy = float(thr.get("decay_yoy_high", -0.10))
    t_high = float(thr.get("decay_high_pp", -10))
    t_mid = float(thr.get("decay_mid_pp", 0))
    default = int(thr.get("decay_default_score", 20))
    if pd.isna(decay_val):
        return default
    GROWTH_RAPID = 0.5
    GROWTH_SHRUNK = -0.10
    DECAY_RAPID_HIGH = 10
    DECAY_RECOVER_HIGH = 10
    if yoy_change is not None and yoy_change > GROWTH_RAPID:
        if decay_val <= t_mid:
            return 10
        elif decay_val <= DECAY_RAPID_HIGH:
            return 30
        else:
            return 50
    elif yoy_change is not None and yoy_change <= GROWTH_SHRUNK:
        if decay_val <= t_high:
            return 80
        elif decay_val <= t_mid:
            return 70
        elif decay_val <= DECAY_RECOVER_HIGH:
            return 60
        else:
            return 50
    else:
        if yoy_change is not None and yoy_change < t_yoy:
            return 80
        elif decay_val < t_high:
            return 70
        elif decay_val < t_mid:
            return 50
        else:
            return default


def risk_self_health(health_pct, thr):
    """因子5：自比健康度 → 风险得分（v2.9）。[deprecated v2.9]
    请使用 score_self_health_v2().
    """
    if pd.isna(health_pct) or (isinstance(health_pct, float) and np.isinf(health_pct)):
        return int(thr.get("health_default_score", 50))
    pct = health_pct * 100
    low = float(thr.get("health_low_pct", 70))
    mid = float(thr.get("health_mid_pct", 50))
    high = float(thr.get("health_high_pct", 30))
    if pct >= low:
        return 10
    elif pct >= mid:
        return 40
    elif pct >= high:
        return 70
    else:
        return 90


def risk_asp(asp_slope, margin_slope, thr):
    """ASP趋势风险得分 (v3.1已移除)。[deprecated]
    """
    t_low = float(thr.get("asp_low_pct", 0)) / 100
    t_mid = float(thr.get("asp_mid_pct", -0.5)) / 100
    t_high = float(thr.get("asp_high_pct", -1.0)) / 100
    margin_t = float(thr.get("slope_mid_pct", -0.3)) / 100
    default = int(thr.get("asp_default_score", 80))
    if asp_slope >= t_low:
        return 10
    elif asp_slope > t_mid:
        if margin_slope is not None and margin_slope <= margin_t:
            return 50
        return 20
    elif asp_slope > t_high:
        if margin_slope is not None and margin_slope > margin_t:
            return 20
        return 50
    else:
        return default


def risk_customer_order_change(order_qty_change, thr):
    """c6 旧版(stub)。[deprecated] 请使用 score_c6_v2()."""
    if pd.isna(order_qty_change):
        return int(thr.get("c6_default_score", 50))
    score = 50 - order_qty_change * 40
    return int(np.clip(score, 10, 90))
