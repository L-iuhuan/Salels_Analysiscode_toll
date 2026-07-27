"""
九宫格画像定位 — 产品生命周期专属。

从v2.8提取的classify_9grid_full和generate_contextual_strategy。
策略文本已抽取到 config/settings_product.py 中的
NINE_GRID_BASE_STRATEGIES 和 NINE_GRID_CONTEXTUAL_STRATEGIES。
"""

import os
import sys

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from config.settings import PRODUCT_LIFECYCLE


def _get_strategies():
    """从配置加载九宫格策略文本，带硬编码兜底。"""
    return (
        PRODUCT_LIFECYCLE.get("nine_grid_base_strategies", {}),
        PRODUCT_LIFECYCLE.get("nine_grid_contextual_strategies", {}),
    )


def generate_contextual_strategy(portrait, row):
    """根据画像和实际数据动态生成策略建议。
    
    策略文本可配置于 config/settings_product.py 的
    nine_grid_base_strategies 和 nine_grid_contextual_strategies。
    
    参数:
        portrait: 九宫格画像名称
        row: 产品数据行（dict-like或Series）
    
    返回:
        str: 上下文感知的策略建议
    """
    margin_yoy = row.get("毛利率同比变化(pp)") if row.get("毛利率同比变化(pp)") is not None else float("nan")
    rev_profit_diag = row.get("营收-毛利综合判断", "")
    sales = row.get("近12月销量", 0) or 0
    margin_current = row.get("近12月毛利率%", 0) or 0

    base_strategies, contextual = _get_strategies()

    margin_improving = margin_yoy > 0

    if portrait == "衰退期":
        if margin_improving:
            if margin_yoy > 10:
                return contextual.get("衰退期_回升高",
                    "销量收缩但毛利率大幅回升，确认回升可持续性。"
                    "若为主动清退低毛利客户，调整至主动收缩策略；"
                    "若回升乏力，安排退市")
            else:
                return contextual.get("衰退期_回升低",
                    "销量收缩但毛利率有所回升，观察回升趋势是否可持续。"
                    "若回升趋势确立，可暂缓退市；若回升仅为短期波动，安排退市")
        elif sales == 0:
            return contextual.get("衰退期_零销量",
                "长期无发货，建议确认是否已实质退市，清理库存")
        else:
            return contextual.get("衰退期_量利双跌",
                "量利双跌，建议安排退市")

    if portrait == "夕阳产品":
        if margin_improving and margin_yoy > 5:
            return contextual.get("夕阳_回升高",
                "销量收缩但毛利率明显回升，利润尚可。控制库存，观察是否有企稳信号，暂缓换代")
        elif margin_improving:
            return contextual.get("夕阳_回升低",
                "需求消退但利润尚可，控制库存，规划替代型号上市时间")
        else:
            return contextual.get("夕阳_需求消退",
                "需求消退但利润尚可，准备换代")

    if portrait == "隐性衰退":
        if margin_improving:
            return contextual.get("隐性衰退_回升",
                "销量平稳但毛利率已跌破历史水位，近期毛利率有所回升，观察回升是否可持续")
        else:
            return contextual.get("隐性衰退_利润侵蚀",
                "表面稳定实则利润被侵蚀，需预警")

    if portrait == "预警增长":
        if rev_profit_diag == "减收增利":
            return contextual.get("预警增长_减收增利",
                "销量增长但利润仍低于历史峰值，毛利率近期回升，关注回升趋势")
        else:
            return contextual.get("预警增长_成本恶化",
                "销量增长掩盖利润恶化，立即查成本结构")

    return base_strategies.get(portrait, "")


def classify_9grid_full(momentum_full, health_full, row=None):
    """完整九宫格定位：12种组合映射到9个画像标签。
    
    参数:
        momentum_full: 销量动能完整标签
        health_full: 盈利健康完整标签
        row: 可选，产品数据行，用于生成上下文感知的策略建议
    
    返回:
        tuple: (画像名称, 管理层摘要, 通用策略建议)
    """
    portrait_map = {
        ("加速增长", "健康"):     ("成长期",   "投入区"),
        ("加速增长", "轻度侵蚀"): ("健康扩张", "投入区"),
        ("加速增长", "严重侵蚀"): ("预警增长", "观察区"),
        ("稳定扩张", "健康"):     ("健康扩张", "投入区"),
        ("稳定扩张", "轻度侵蚀"): ("现金牛",   "维持区"),
        ("稳定扩张", "严重侵蚀"): ("预警增长", "观察区"),
        ("持平",     "健康"):     ("利润优化", "维持区"),
        ("持平",     "轻度侵蚀"): ("现金牛",   "维持区"),
        ("持平",     "严重侵蚀"): ("隐性衰退", "观察区"),
        ("萎缩",     "健康"):     ("主动收缩", "观察区"),
        ("萎缩",     "轻度侵蚀"): ("夕阳产品", "退出区"),
        ("萎缩",     "严重侵蚀"): ("衰退期",   "退出区"),
    }
    result = portrait_map.get((momentum_full, health_full))
    if result:
        portrait, summary = result
        strategy = generate_contextual_strategy(portrait, row) if row is not None else ""
        return (portrait, summary, strategy)
    return ("未分类", "待观察", "")
