"""
风险评分函数 — v2.9 5因子模型。

因子1: 毛利率趋势斜率 (20%)
因子3: 订货波动性CV (10%, 阈值放宽)
因子4: 增速衰减 v4 (20%, 增长率感知)
因子5: 自比健康度 SH (35%, 新增)
因子6: ASP趋势 (15%)
"""

import pandas as pd
import numpy as np


def risk_slope(slope_ratio, thr, zero_profit=False):
    """因子1：毛利率趋势斜率 → 风险得分（0~100）。

    参数:
        slope_ratio: 斜率值（比率形式）
        thr: 阈值字典
        zero_profit: 是否无利润

    返回:
        int: 风险得分
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
    """因子3：订货波动性CV → 风险得分（v2.9阈值放宽至0.5/1.0/1.5）。

    参数:
        cv_val: 变异系数
        thr: 阈值字典

    返回:
        int: 风险得分
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
    """因子4：增速衰减 → 风险得分（v2.9: 增长率感知版本v4）

    核心逻辑：同样的衰减值，在不同增长率下含义完全不同。
    - 增长率 > 50%（快速正增长）：自然减速 → 低风险（≤0pp=10分, >0pp=30分, >10pp=50分）
    - 增长率 ≤ -10%（已萎缩）：衰减值已不是主信号 → 偏高-高风险
    - 正常区间：使用原阈值逻辑

    参数单位说明（混合单位，注意区分）:
        decay_val (float): 增速衰减值，单位是百分点(pp)
            例如 -5 表示近3月增长率比近12月增长率低5个百分点。
            正值 = 增速在加速（非衰减），负值 = 增速在衰减。
        yoy_change (float | None): 同比增长率，小数形式（ratio）
            例如 0.50 表示同比 +50%，-0.10 表示同比 -10%。
            为 None 表示无足够历史数据计算。
        thr (dict): 阈值字典。其中 decay_yoy_high 也是 ratio 形式（如 -0.10）。

    内部常量说明:
        GROWTH_RAPID = 0.5   — yoy_change > 0.5（即同比 +50%）进入高增长分支
        GROWTH_SHRUNK = -0.10 — yoy_change <= -0.10（即同比 <= -10%）进入萎缩分支
        decay_val 比较阈值 t_mid=0, t_high=-10 均为百分点(pp)。
    """
    t_yoy = float(thr.get("decay_yoy_high", -0.10))
    t_high = float(thr.get("decay_high_pp", -10))
    t_mid = float(thr.get("decay_mid_pp", 0))
    default = int(thr.get("decay_default_score", 20))

    if pd.isna(decay_val):
        return default

    # 增长率感知分支
    # 注意: yoy_change 是小数形式（如 0.5=+50%, -0.10=-10%）
    #       decay_val 是百分点形式（如 -15=-15pp）
    GROWTH_RAPID = 0.5    # >50% 为快速正增长
    GROWTH_SHRUNK = -0.10 # <=-10% 为已萎缩
    DECAY_RAPID_HIGH = 10 # 高增长分支的加速阈值(pp)：>10pp视为明显加速
    DECAY_RECOVER_HIGH = 10  # 萎缩分支的恢复阈值(pp)：>10pp视为明显恢复
    if yoy_change is not None and yoy_change > GROWTH_RAPID:
        # 快速正增长：自然减速，低风险
        # 注意：此处 decay_val 正值=减速/加速？decay=(last3_growth-growth)*100，
        # 正值表示近期增速 > 长期增速（即加速），负值表示近期 < 长期（即减速）。
        # 对高速增长产品：加速是潜在的过热信号，减速是自然收敛。
        if decay_val <= t_mid:          # ≤0pp: 稳定或减速 → 最低风险
            return 10
        elif decay_val <= DECAY_RAPID_HIGH:  # 0~10pp: 轻度加速 → 中低风险
            return 30
        else:                           # >10pp: 明显加速 → 中度风险
            return 50
    elif yoy_change is not None and yoy_change <= GROWTH_SHRUNK:
        # 已负增长：decay_val 变成恢复/恶化信号
        # decay_val 负值=加速恶化，正值=开始恢复
        if decay_val <= t_high:          # ≤-10pp: 加速恶化 → 极高风险
            return 80
        elif decay_val <= t_mid:         # -10~0pp: 稳定恶化 → 高风险
            return 70
        elif decay_val <= DECAY_RECOVER_HIGH:  # 0~10pp: 轻度恢复 → 中高风险
            return 60
        else:                            # >10pp: 明显恢复 → 中风险
            return 50
    else:
        # 正常区间：原逻辑（含同比下降检测）
        if yoy_change is not None and yoy_change < t_yoy:
            return 80
        elif decay_val < t_high:
            return 70
        elif decay_val < t_mid:
            return 50
        else:
            return default


def risk_self_health(health_pct, thr):
    """因子5：自比健康度 → 风险得分（v2.9新增）：健康度越低风险越高。

    评分逻辑：
        自比健康度 >= 70%:  10分（低风险）
        50~70%:            40分（中低风险）
        30~50%:            70分（高风险）
        < 30%:             90分（极高风险）
        NaN:               50分（兜底）

    参数:
        health_pct (float): 自比健康度，小数形式（ratio）。
            例如 0.70 表示当前毛利率达到历史参照的 70%。
            传入值可以是 0~∞，如 1.20 表示超过历史参照 20%。
            函数内部统一乘以 100 转为百分比与 thr 阈值比较。
        thr (dict): 阈值字典。health_low_pct=70, health_mid_pct=50, health_high_pct=30
            这些阈值已经是百分比形式（如 70 表示 70%），与 health_pct*100 比较。

    注意: 不要传入百分比值（如 70），应传入小数（如 0.70）。
          历史版本曾有百分比/小数混合问题，v2.9fix 已统一为小数输入。
    """
    if pd.isna(health_pct) or (isinstance(health_pct, float) and np.isinf(health_pct)):
        return int(thr.get("health_default_score", 50))
    # 输入始终为小数（0~∞），统一转为百分数
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
    """ASP趋势风险得分（0~100）。

    ASP趋势与毛利率趋势联合判定。
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
