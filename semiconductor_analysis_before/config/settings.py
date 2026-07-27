"""
统一配置文件。

所有参数集中管理，方便调整而不改主程序逻辑。
"""

import os

# ============================================================
# 路径配置
# ============================================================

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output")
OUTPUT_SILVER = os.path.join(OUTPUT_DIR, "silver")
OUTPUT_GOLD = os.path.join(OUTPUT_DIR, "gold")
OUTPUT_REPORT = os.path.join(OUTPUT_DIR, "report")

# 原始产品生命周期系统路径（用于调用v2.8）
V28_DIR = os.path.join(os.path.dirname(PROJECT_ROOT), "产品生命周期评估")

# ============================================================
# ERP原始列名 → 标准列名映射
# 如果ERP导出的列名与默认不同，在此修改
# ============================================================

ERP_COL_MAP = {
    "代理商/直供名称": "客户编号",
    "存货名称": "产品品种",
    "发货数量": "数量",
    "RMB 未税金额小计": "金额",
    "利润": "利润",
    "发货日期": "发货日期",
    "成本": "成本",
    "产品线": "产品一级分类",
    "产品系列": "产品二级分类",
    "型号_产品品类": "型号_产品品类",
    "ERP订单号": "订单编号",
    "是否新品": "新品标记",
    "未税单价": "单价",
}

# ============================================================
# 数据列名映射
# ============================================================

COL_MAP = {
    "customer_id": "客户编号",
    "customer_name": "客户名称",
    "channel_type": "渠道类型",       # 直销/代理
    "order_id": "订单编号",
    "product_name": "产品品种",
    "product_line": "产品一级分类",
    "product_series": "产品二级分类",
    "order_date": "下单日期",
    "ship_date": "发货日期",
    "quantity": "数量",
    "unit_price": "单价",
    "revenue": "金额",
    "cost": "成本",
    "profit": "利润",
    "cust_grade": "客户等级",
    "region": "所属区域",
    "sales_owner": "业务负责人",
    "agent_name": "代理商名称",
    "end_customer": "终端客户名称",
    "new_product_flag": "新品标记",
}

# ============================================================
# 清洗参数
# ============================================================

CLEAN = {
    "winsor_lower": -0.50,       # 毛利率钳制下限
    "winsor_upper": 0.75,        # 毛利率钳制上限
    "sample_z_threshold": 2.0,   # 样品单识别Z分数阈值
}

# ============================================================
# 产品分析阈值
# ============================================================

PRODUCT_THRESHOLDS = {
    "growth_accelerate": 0.15,       # 加速增长阈值
    "growth_flat_lower": -0.10,     # 持平下限
    "health_healthy": 0.70,         # 健康度健康线
    "health_severe": 0.50,          # 健康度严重线
    "health_relative": -10,         # 他比严重阈值(pp)
    "pareto_key": 1000000,          # 重点产品线(元)
    "pareto_regular": 100000,       # 常规产品线(元)
}

# ============================================================
# 客户RFM-π评分权重
# ============================================================

RFM_PI_WEIGHTS = {
    "direct": {"R": 0.30, "F": 0.20, "M": 0.30, "P": 0.20},   # 直销
    "agent": {"R": 0.25, "F": 0.25, "M": 0.25, "P": 0.25},     # 代理
}

# ============================================================
# 机会/风险评分权重
# ============================================================

OPPORTUNITY_WEIGHTS = {
    "scale": 0.25,          # 收入规模（近12月）
    "growth": 0.25,         # 增长趋势（同比+环比，吸收原回款10%）
    "margin": 0.20,         # 毛利质量
    "new_product": 0.15,    # 新品渗透率
    "breadth": 0.15,        # 产品线广度（吸收原回款5%）
}

RISK_WEIGHTS = {
    "decline_months": 0.30,      # 连续下滑月数（吸收原逾期10%）
    "asp_decline": 0.20,         # ASP跌幅
    "margin_decline": 0.20,      # 毛利率跌幅
    "concentration": 0.15,       # 品种集中度
    "churn_warning": 0.15,       # 采购中断预警（新增）
}

# ============================================================
# 客户分析阈值（子项2/3/4）
# ============================================================

CUSTOMER_THRESHOLDS = {
    # 采购健康度
    "purchase_interval_exclude_first_months": 6,  # 剔除新品期月数
    "churn_multiplier": 1.5,                      # 采购中断预警倍率
    "churn_suspected_days": 90,                   # 疑似流失天数
    "churn_high_risk_days": 180,                  # 高危流失天数
    "concentration_top_n": 5,                     # 集中度前N大
    "concentration_threshold": 0.70,              # 强依赖阈值

    # 生命周期阶段
    "导入期月金额倍数": 3.0,                       # 首次采购月金额 >= 月均 × 倍数
    "爬坡期环比阈值": 0.05,                        # 近N月环比 >= 5%（N由下参数控制，默认3个月）
    "爬坡期_环比增长前N月均值": 3,                 # 环比对比窗口宽度（月数）
    "成熟期标准差倍数": 1.5,                       # 均值 ± N倍标准差
    "衰退期跌幅阈值": 0.15,                        # 连续3月低于均线15%

    # 新品判定
    "new_product_max_months": 12,                 # 首次销售距今 <= N月为新品
    "new_product_min_volume": 1000,               # 新品最小累计销售金额
    "cohort_window_months": 6,                    # Cohort追踪窗口

    # 价格治理
    "price_deviation_min_months": 3,               # 价格偏离度最低月数要求
    "price_dispersion_cv_threshold": 0.30,         # 价格混乱CV阈值
}

# ============================================================
# 定价建议参数（子项7/8）
# ============================================================

PRICING_RECOMMENDATION = {
    # 提价空间
    "markup_price_ratio": 0.90,           # 实际价 < 中位价 × 此值
    "markup_max_customer_share": 0.30,    # 客户采购量不超过总销量此比例
    "markup_min_active_months": 6,        # 最低持续交易月数

    # 降价策略
    "markdown_default_elasticity": -1.0,   # 固定弹性系数
    "markdown_discount_rates": [0.03, 0.05, 0.08, 0.10],  # 降价幅度档位
    "markdown_break_even_buffer": 1.2,     # 盈亏平衡容错余量
    "markdown_margin_growth_target": 0.10, # 总毛利增长目标
    "markdown_min_gross_margin_ratio": 0.80, # 新毛利率底线（相对公司整体）
}

# ============================================================
# 客户分析列映射（CUSTOMER_COL_MAP）
# 与PRODUCT_LIFECYCLE.col_map类似，可配置让后续灵活变动
# ============================================================

CUSTOMER_COL_MAP = {
    "客户列": "客户编号",
    "产品名称列": "产品品种",
    "发货日期列": "发货日期",
    "数量列": "数量",
    "金额列": "金额",
    "利润列": "利润",
    "成本列": "成本",
    "品类列": "产品一级分类",
    "产品系列列": "产品二级分类",
    "订单号列": "订单编号",
}

# ============================================================
# 回款信用等级阈值
# ============================================================

CREDIT_THRESHOLDS = {
    "dso_a": 45,    # A级上限（天）
    "dso_b": 60,    # B级上限
    "dso_c": 90,    # C级上限
    "overdue_days": 30,  # 逾期认定天数
}

# ============================================================
# 产品生命周期v2.9完整配置
# ============================================================

PRODUCT_LIFECYCLE = {
    # ---- 列映射 ----
    "col_map": {
        "产品名称列": "产品品种",
        "发货日期列": "发货日期",
        "销量列": "数量",
        "营收列": "金额",
        "利润列": "利润",
        "成本列": "成本",
        "客户列": "客户编号",
        "分类参照列": "型号_产品品类",
        "产品系列列": "产品二级分类",
        "订单号列": "客户订单号",
    },

    # ---- 动能分类 ----
    "growth_accelerate": 0.15,
    "growth_flat_lower": -0.10,

    # ---- 盈利健康分类 ----
    "health_healthy": 0.70,
    "health_severe": 0.50,
    "health_relative": -10,

    # ---- 新品判定 ----
    "new_product_mode": "月数",
    "new_product_months": 6,
    "new_product_min_volume": 100,
    "min_record_months": 3,

    # ---- 斜率阈值 ----
    "slope_low_pct": 0.0,
    "slope_mid_pct": -0.3,
    "slope_high_pct": -0.8,
    "slope_default_score": 80,
    "slope_min_data_points": 3,
    "slope_insufficient_score": 50,

    # ---- CV（订货波动性） ----
    "cv_low": 0.5,
    "cv_mid": 1.0,
    "cv_high": 1.5,
    "cv_default_score": 85,
    "cv_pulse_value": 0.5,

    # ---- 增速衰减 ----
    "decay_high_pp": -10,
    "decay_mid_pp": 0,
    "decay_yoy_high": -0.10,
    "decay_default_score": 20,
    "decay_explosive_cap": 1.0,
    "decay_explosive_threshold": -100,
    "decay_explosive_s4_cap": 50,

    # ---- 历史参照 ----
    "ref_percentile": 0.95,
    "ref_short_age_months": 12,
    "ref_short_percentile": 0.50,
    "ref_long_months": 24,
    "ref_long_percentile": 0.80,
    "ref_p95_min_months": 20,
    "ref_robust_min_points": 6,

    # ---- 自比健康度阈值（v2.9新增） ----
    "health_low_pct": 70,
    "health_mid_pct": 50,
    "health_high_pct": 30,
    "health_default_score": 50,

    # ---- 总风险等级 ----
    "risk_low_max": 25,
    "risk_mid_max": 50,
    "risk_high_max": 75,

    # ---- ASP趋势 ----
    "asp_low_pct": 0.0,
    "asp_mid_pct": -0.5,
    "asp_high_pct": -1.0,
    "asp_default_score": 80,
    "asp_rising_pct": 0.5,
    "asp_falling_pct": -0.5,
    "joint_asp_pct": -0.5,
    "joint_margin_pct": -0.3,

    # ---- 帕累托分类（单位：万） ----
    "pareto_key_revenue": 100,
    "pareto_regular_revenue": 10,
    # ---- 增长率截断 ----
    "rev_growth_lower": -1.0,
    "rev_growth_upper": 5.0,
    # ---- 低量品阈值 ----
    "长尾销量阈值": 1000,

    # ---- 首次6K ----
    "first_6k_threshold": 6000,

    # ---- ETS预测 ----
    "ets_seasonal_periods": 0,
    "ets_output_ci": 1,
    "forecast_months": 3,
    "forecast_ma_window": 3,
    "forecast_holiday_adjust": 1,

    # ---- 价格弹性 ----
    "elasticity_high": 1.5,
    "elasticity_mid": 0.8,

    # ---- 订单频次 ----
    "freq_increase": 0.15,
    "freq_decrease": -0.10,

    # ---- RFM ----
    "rfm_churn_days": 90,

    # ---- 关联分析 ----
    "assoc_min_support": 0.02,
    "assoc_min_confidence": 0.15,

    # ---- 历史画像追踪 ----
    "hist_portrait_enabled": 1,
    "hist_portrait_points": "auto_12",
    "hist_portrait_min_months": 6,

    # ---- 退市判定 ----
    "exit_months": 12,
    "exit_min_age_months": 3,

    # ---- 特情说明（v2.9） ----
    "note_self_health_warn_pct": 50,   # 自比健康预警值%
    "note_rel_health_warn_pp": -10,    # 他比健康预警值(pp)
    "note_self_extreme_pct": 30,       # 自比极低阈值%
    "note_regular_growth_threshold": 1.0,  # 常规产品高增长阈值
    "note_rebound_threshold_pp": 5,    # 衰退毛利率回升阈值(pp)
    "decay_portrait_min_risk": 50,

    # ---- 参照组优先级 ----
    "ref_priority": [
        ("型号_产品品类", 3),
        ("产品二级分类", 3),
        ("（全公司均值）", 0),
    ],

    # ---- 风险因子权重（v2.9 5因子） ----
    "risk_weights": {
        "ASP趋势": 0.15,
        "毛利率趋势斜率": 0.20,
        "订货波动性(CV)": 0.10,
        "增速衰减": 0.20,
        "自比健康度": 0.35,
    },
}

# ============================================================
# B2B客户评分系统 v2: 客户旅程阶段阈值 (Task 1)
# ============================================================

CUSTOMER_JOURNEY_THRESHOLDS = {
    "onboarding_max_months": 6,           # 导入期最长月数
    "onboarding_max_orders": 3,           # 导入期最高订单数
    "growth_growth_threshold": 0.30,      # 成长期增长率阈值
    "growth_frequency_surge_ratio": 2.0,  # 成长期频次激增倍数
    "maturity_cv_threshold": 0.3,         # 成熟期CV上限
    "maturity_revenue_rank_pct": 0.3,     # 成熟期金额排名前%
    "decline_decline_threshold": 0.20,    # 衰退期跌幅阈值
    "decline_consecutive_months": 2,      # 衰退期连续下滑月数
    "churn_days": 90,                     # 流失期认定天数
    "reactivation_window_days": 180,      # 激活期沉默窗口天数
}

# ============================================================
# B2B客户评分系统 v2: 采购波动性指标 (Task 5)
# ============================================================

VOLATILITY_METRICS = {
    "stable_cv_threshold": 0.3,           # 高稳定CV上限
    "stable_zero_month_ratio": 0.10,      # 高稳定零采购月占比上限
    "moderate_cv_threshold": 0.6,         # 中等稳定CV上限
    "moderate_zero_month_ratio": 0.20,    # 中等稳定零采购月占比上限
}

# ============================================================
# B2B客户评分系统 v2: 估算成本参数 (Task 6)
# ============================================================

ESTIMATED_COST = {
    "order_processing_cost": 50.0,        # 每单处理成本（元），需要 `订单数` 字段
    "logistics_cost_rate": 0.02,          # 物流成本：营收比例（半导体行业不宜按件计费）
    "aftersales_cost_ratio": 0.30,        # 售后成本占退货金额比例，需要 `退货金额` 字段
    "capital_cost_annual_rate": 0.06,     # 资金占用年化利率，需要 `应收账款` 字段；DSO从 CREDIT_THRESHOLDS 读取
}

# ============================================================
# 运行模式
# ============================================================

RUN_STAGES = ["silver", "product", "customer", "kpi", "cross_ref"]
SKIP_SILVER_IF_EXISTS = True
