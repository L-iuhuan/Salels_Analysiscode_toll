"""
客户分析维度计算包装层。

按文档维度组织 shared/pricing.py 的各函数调用，提供客户分析默认参数。
每个包装函数从 config.settings 读取默认阈值，调用 shared.pricing 对应函数。
"""

from shared.pricing import (
    calc_purchase_interval as _calc_purchase_interval,
    calc_churn_warning as _calc_churn_warning,
    calc_product_concentration as _calc_product_concentration,
    calc_category_acceptance as _calc_category_acceptance,
    calc_price_band_distribution as _calc_price_band_distribution,
    calc_cross_customer_price_dispersion as _calc_cross_customer_price_dispersion,
    calc_sku_lifecycle_stage as _calc_sku_lifecycle_stage,
    calc_customer_lifecycle_stage as _calc_customer_lifecycle_stage,
    calc_new_product_cohort as _calc_new_product_cohort,
    calc_opportunity_signals as _calc_opportunity_signals,
    calc_risk_signals as _calc_risk_signals,
    calc_markup_opportunity as _calc_markup_opportunity,
    calc_markdown_recommendation as _calc_markdown_recommendation,
    generate_action_suggestions as _generate_action_suggestions,
)


# ============================================================
# 维度1: 采购健康度
# ============================================================

def calc_purchase_interval(customer_monthly, **overrides):
    """常规平均采购间隔（剔除初始N个月）。"""
    from config.settings import CUSTOMER_THRESHOLDS
    defaults = {"exclude_first_months": CUSTOMER_THRESHOLDS.get("purchase_interval_exclude_first_months", 6)}
    defaults.update(overrides)
    return _calc_purchase_interval(customer_monthly, **defaults)


def calc_churn_warning(customer_monthly, intervals, **overrides):
    """采购中断预警：距上次采购天数 > 常规间隔 × 倍数。"""
    from config.settings import CUSTOMER_THRESHOLDS
    defaults = {"multiplier": CUSTOMER_THRESHOLDS.get("churn_multiplier", 1.5)}
    defaults.update(overrides)
    return _calc_churn_warning(customer_monthly, intervals, **defaults)


def calc_product_concentration(cust_prod, **overrides):
    """产品集中度：Top5集中度 + 强依赖标记。"""
    from config.settings import CUSTOMER_THRESHOLDS
    defaults = {
        "top_n": CUSTOMER_THRESHOLDS.get("concentration_top_n", 5),
        "threshold": CUSTOMER_THRESHOLDS.get("concentration_threshold", 0.7),
    }
    defaults.update(overrides)
    return _calc_product_concentration(cust_prod, **defaults)


# ============================================================
# 维度2: 品类接受度
# ============================================================

def calc_category_acceptance(cust_prod, **overrides):
    """品类接受度：主导品类 + 品类机会标签。"""
    return _calc_category_acceptance(cust_prod, **overrides)


# ============================================================
# 维度3: 价格治理
# ============================================================

def calc_price_band_distribution(cust_prod, **overrides):
    """价格带分布：低价/中价/高价品种收入占比。"""
    return _calc_price_band_distribution(cust_prod, **overrides)


def calc_cross_customer_price_dispersion(cust_prod, **overrides):
    """跨客户价格离散度（CV法）。"""
    return _calc_cross_customer_price_dispersion(cust_prod, **overrides)


# ============================================================
# 维度4: 生命周期
# ============================================================

def calc_sku_lifecycle_stage(prod_monthly, **overrides):
    """SKU生命周期阶段状态机。"""
    return _calc_sku_lifecycle_stage(prod_monthly, **overrides)


def calc_customer_lifecycle_stage(customer_monthly, latest_month=None, **overrides):
    """客户生命周期阶段（6阶段）。"""
    from config.settings import CUSTOMER_THRESHOLDS
    defaults = {"thr": CUSTOMER_THRESHOLDS}
    defaults.update(overrides)
    return _calc_customer_lifecycle_stage(customer_monthly, latest_month=latest_month, **defaults)


def calc_new_product_cohort(prod_monthly, cust_prod, **overrides):
    """新品Cohort追踪：新品采购额/品种数/占比。"""
    return _calc_new_product_cohort(prod_monthly, cust_prod, **overrides)


# ============================================================
# 维度5: 机会/风险信号
# ============================================================

def calc_opportunity_signals(customer_monthly, prod_monthly, cust_prod, latest_month=None, **overrides):
    """新品渗透机会 + 增长动量。"""
    return _calc_opportunity_signals(customer_monthly, prod_monthly, cust_prod, latest_month=latest_month, **overrides)


def calc_risk_signals(customer_monthly, cust_prod, latest_month=None, **overrides):
    """品种流失金额占比 + 近半年营收跌幅。"""
    return _calc_risk_signals(customer_monthly, cust_prod, latest_month=latest_month, **overrides)


# ============================================================
# 维度6: 定价建议
# ============================================================

def calc_markup_opportunity(cust_prod, **overrides):
    """提价空间分析（3条件过滤）。"""
    from config.settings import PRICING_RECOMMENDATION
    defaults = {
        "min_active_months": PRICING_RECOMMENDATION.get("markup_min_active_months", 6),
        "price_ratio_threshold": PRICING_RECOMMENDATION.get("markup_price_ratio", 0.90),
    }
    defaults.update(overrides)
    return _calc_markup_opportunity(cust_prod, **defaults)


def calc_markdown_recommendation(cust_prod, **overrides):
    """降价策略试算（4档弹性试算）。"""
    from config.settings import PRICING_RECOMMENDATION
    defaults = {
        "elasticity": PRICING_RECOMMENDATION.get("markdown_default_elasticity", -1.0),
        "discount_rates": PRICING_RECOMMENDATION.get("markdown_discount_rates", [0.03, 0.05, 0.08, 0.10]),
    }
    defaults.update(overrides)
    return _calc_markdown_recommendation(cust_prod, **defaults)


def generate_action_suggestions(customer_profile, **overrides):
    """行动建议规则引擎。"""
    return _generate_action_suggestions(customer_profile, **overrides)
