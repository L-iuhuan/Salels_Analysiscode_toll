"""
九宫格画像定位 — 产品生命周期专属。

从v2.8提取的classify_9grid_full和generate_contextual_strategy。
"""


def generate_contextual_strategy(portrait, row):
    """根据画像和实际数据动态生成策略建议。
    
    参数:
        portrait: 九宫格画像名称
        row: 产品数据行（dict-like或Series）
    
    返回:
        str: 上下文感知的策略建议
    """
    margin_yoy = row.get("毛利率同比变化(pp)", 0) if row.get("毛利率同比变化(pp)") is not None else 0
    rev_profit_diag = row.get("营收-毛利综合判断", "")
    sales = row.get("近12月销量", 0) or 0
    margin_current = row.get("近12月毛利率%", 0) or 0

    base_strategies = {
        "成长期": "量利齐升，加大投入",
        "健康扩张": "规模扩大但利润率需关注，维持投入",
        "预警增长": "销量增长掩盖利润恶化，立即查成本结构",
        "现金牛": "稳定收割，监控利润变化",
        "利润优化": "规模稳定盈利健康，优化成本结构",
        "隐性衰退": "表面稳定实则利润被侵蚀，需预警",
        "主动收缩": "量跌利升，可能是主动清退低毛利客户",
        "夕阳产品": "需求消退但利润尚可，准备换代",
        "衰退期": "量利双跌，建议安排退市",
        "新品观察": "持续跟踪，暂不参与周期判断",
        "清仓/偶发": "僵尸产品偶发销售，不作为正常周期分析",
    }

    margin_improving = margin_yoy > 0

    if portrait == "衰退期":
        if margin_improving:
            if margin_yoy > 10:
                return ("销量收缩但毛利率大幅回升，确认回升可持续性。"
                       "若为主动清退低毛利客户，调整至主动收缩策略；"
                       "若回升乏力，安排退市")
            else:
                return ("销量收缩但毛利率有所回升，观察回升趋势是否可持续。"
                       "若回升趋势确立，可暂缓退市；若回升仅为短期波动，安排退市")
        elif sales == 0:
            return "长期无发货，建议确认是否已实质退市，清理库存"
        else:
            return "量利双跌，建议安排退市"

    if portrait == "夕阳产品":
        if margin_improving and margin_yoy > 5:
            return "销量收缩但毛利率明显回升，利润尚可。控制库存，观察是否有企稳信号，暂缓换代"
        elif margin_improving:
            return "需求消退但利润尚可，控制库存，规划替代型号上市时间"
        else:
            return "需求消退但利润尚可，准备换代"

    if portrait == "隐性衰退":
        if margin_improving:
            return "销量平稳但毛利率已跌破历史水位，近期毛利率有所回升，观察回升是否可持续"
        else:
            return "表面稳定实则利润被侵蚀，需预警"

    if portrait == "预警增长":
        if rev_profit_diag == "减收增利":
            return "销量增长但利润仍低于历史峰值，毛利率近期回升，关注回升趋势"
        else:
            return "销量增长掩盖利润恶化，立即查成本结构"

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
