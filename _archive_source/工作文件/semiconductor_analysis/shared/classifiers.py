"""
分类函数 — 从v2.8提取的通用分类器。

可被产品生命周期和客户分析复用。
"""

import pandas as pd
import numpy as np


def classify_slope_level(slope_ratio, thr, zero_profit=False):
    """将毛利率趋势斜率映射为文字等级标签。
    
    参数:
        slope_ratio: 斜率比率值（如-0.008表示每月降0.8个百分点）
        thr: 阈值参数字典或数值字典
        zero_profit: 是否无利润
    
    返回:
        str: 等级标签
    """
    if zero_profit:
        return "无利润/异常"
    
    if isinstance(thr, dict):
        t_low = float(thr.get("slope_low_pct", 0)) / 100
        t_mid = float(thr.get("slope_mid_pct", -0.3)) / 100
        t_high = float(thr.get("slope_high_pct", -0.8)) / 100
    else:
        t_low, t_mid, t_high = 0.0, -0.003, -0.008
    
    if slope_ratio >= t_low:
        return "稳定/提升"
    elif slope_ratio > t_mid:
        return "轻度下降"
    elif slope_ratio > t_high:
        return "明显侵蚀"
    else:
        return "快速恶化"


def classify_momentum(growth, thresh_grow=0.15, thresh_flat=-0.10):
    """销量动能分类。
    
    参数:
        growth: 销量增长率（比率形式）
        thresh_grow: 加速增长阈值（默认0.15）
        thresh_flat: 持平下限阈值（默认-0.10）
    
    返回:
        tuple: (完整标签, 简写标签)
    """
    if growth > thresh_grow:
        return "加速增长", "量增"
    elif growth > 0:
        return "稳定扩张", "量增"
    elif growth > thresh_flat:
        return "持平", "量稳"
    else:
        return "萎缩", "量跌"


def classify_health(self_health, rel_health, thresh_healthy=0.70, thresh_severe=0.50, thresh_rel=-10):
    """盈利健康分类。
    
    参数:
        self_health: 自比健康度（当前毛利率/历史参照毛利率）
        rel_health: 他比健康度（当前毛利率-参照组毛利率，单位pp）
        thresh_healthy: 健康线（默认0.70）
        thresh_severe: 严重线（默认0.50）
        thresh_rel: 他比严重阈值（默认-10pp）
    
    返回:
        tuple: (等级标签, 简写标签)
    """
    is_severe = (self_health < thresh_severe) or (rel_health < thresh_rel)
    is_healthy = (self_health >= thresh_healthy) and (rel_health >= 0)
    if is_severe:
        return "严重侵蚀", "利跌"
    elif is_healthy:
        return "健康", "利稳"
    else:
        return "轻度侵蚀", "利稳"
