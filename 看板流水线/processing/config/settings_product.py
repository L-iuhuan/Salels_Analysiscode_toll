# ── 产品生命周期配置（分拆自 config/settings.py P1-A）──
# 设计意图：产品分析所用字段不存在缺失信息，使用全量数据。
#   与此对应，CUSTOMER_ANALYSIS_WINDOW 使用较晚日期因客户字段不全。
#   两个日期差异是设计选择。

# ============================================================
# 产品生命周期v4.0完整配置
# 来源: v4.0 优化结果: 4因子(毛利率斜率+增速衰减+自比健康度+订货量变化), 阈值[55,65,68]
# 数据源: product_monthly/product_x_customer聚合表
# 使用位置: product_lifecycle/profiling.py, nine_grid.py, notes.py
# ============================================================

PRODUCT_LIFECYCLE = {
    # ---- 基础参数 ----
    # 数据起始日期：过滤此日期之前的数据（替代硬编码"2020-01-01"）
    # 【设计意图】产品分析所用字段(数量/金额/利润等)不存在缺失信息，使用全量数据。
    #   CUSTOMER_ANALYSIS_WINDOW.start_date="2024-01-01" 使用较晚日期，
    #   因客户字段(等级/渠道/区域)在2024年前数据不全。两个日期差异是设计选择。
    # 【经验值】覆盖5年以上历史数据用于趋势分析
    "data_start_date": "2020-01-01",
    # 月份完整性判断阈值：最新月份的最大日期小于此值则视为不完整月，自动回退1月
    # 【经验值】ERP多数在25日前完成上月关账，25日之后的数据基本完整
    "incomplete_month_threshold_day": 25,

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

    # ---- 动能分类阈值 ---
    "growth_accelerate": 0.15,
    "growth_flat_lower": -0.10,

    # ---- 盈利健康分类 ---
    "health_healthy": 0.70,
    "health_severe": 0.50,
    "health_relative": -10,

    # ---- 新品判定 ---
    "new_product_mode": "月数",
    "new_product_months": 6,
    "new_product_min_volume": 100,
    "min_record_months": 3,

    # ---- SKU生命周期状态机阈值（shared/pricing.py:calc_sku_lifecycle_stage） ----
    "sku_intro_max_months": 3,       # 导入试销：在售≤N月
    "sku_intro_min_qty": 1000,       # 导入试销：总销量<N
    "sku_exit_ratio": 0.30,          # 衰退出清：近3月营收 < 峰值×此比例
    "sku_decline_ratio": 0.70,       # 隐性衰退：近3月营收 < 前3月×此比例

    # ---- 斜率计算 ---
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

    # ---- 历史参照组 ---
    "ref_percentile": 0.95,
    "ref_short_age_months": 12,
    "ref_short_percentile": 0.50,
    "ref_long_months": 24,
    "ref_long_percentile": 0.80,
    "ref_p95_min_months": 20,
    "ref_robust_min_points": 6,

    # ---- 自比健康度 ----
    "health_low_pct": 70,
    "health_mid_pct": 50,
    "health_high_pct": 30,
    "health_default_score": 50,

    # ---- 总风险等级 (v4.0校准: [55, 65, 68]) ----
    # v4.0: 阈值从[50,60,75]移至[55,65,68]，降低低风险要求同时放宽极高风险门槛
    "risk_low_max": 55,
    "risk_mid_max": 65,
    "risk_high_max": 68,

    # ---- ASP趋势 ---
    "asp_low_pct": 0.0,
    "asp_mid_pct": -0.5,
    "asp_high_pct": -1.0,
    "asp_default_score": 80,
    "asp_rising_pct": 0.5,
    "asp_falling_pct": -0.5,
    "joint_asp_pct": -0.5,
    "joint_margin_pct": -0.3,

    # ---- 帕累托分类 ----
    "pareto_key_revenue": 100,          # 重点产品线(万元)
    "pareto_regular_revenue": 10,       # 常规产品线(万元)

    # ---- 增长率截断 ----
    "rev_growth_lower": -1.0,
    "rev_growth_upper": 5.0,

    # ---- 低量品阈值 ---
    "长尾销量阈值": 1000,

    # ---- 首次6K ---
    "first_6k_threshold": 6000,

    # ---- ETS预测 ---
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
    "hist_portrait_n_workers": 4,

    # ---- 退市判定 ----
    "exit_months": 12,
    "exit_min_age_months": 3,

    # ---- 特情说明 ----
    "note_self_health_warn_pct": 50,
    "note_rel_health_warn_pp": -10,
    "note_self_extreme_pct": 30,
    "note_regular_growth_threshold": 1.0,
    "note_rebound_threshold_pp": 5,
    "decay_portrait_min_risk": 50,

    # ---- 参照组优先级 ----
    "ref_priority": [
        ("型号_产品品类", 3),
        ("产品二级分类", 3),
        ("（全公司均值）", 0),
    ],

    # ---- 风险因子权重（4因子 v4.0-optimized） ----
    # v4.0优化: 增速衰减权重从0.236升至0.600(主信号), 毛利率斜率从0.411降至0.100, 订货量变化新增0.100
    "risk_weights": {
        "毛利率趋势斜率": 0.100,
        "增速衰减": 0.600,
        "自比健康度": 0.200,
        "c6": 0.100,
    },

    # ---- 九宫格画像策略文本 ----
    # 【设计意图】业务方可直接编辑此配置调整策略表述，无需修改代码。
    "nine_grid_base_strategies": {
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
    },
    "nine_grid_contextual_strategies": {
        "衰退期_回升高": "销量收缩但毛利率大幅回升，确认回升可持续性。若为主动清退低毛利客户，调整至主动收缩策略；若回升乏力，安排退市",
        "衰退期_回升低": "销量收缩但毛利率有所回升，观察回升趋势是否可持续。若回升趋势确立，可暂缓退市；若回升仅为短期波动，安排退市",
        "衰退期_零销量": "长期无发货，建议确认是否已实质退市，清理库存",
        "衰退期_量利双跌": "量利双跌，建议安排退市",
        "夕阳_回升高": "销量收缩但毛利率明显回升，利润尚可。控制库存，观察是否有企稳信号，暂缓换代",
        "夕阳_回升低": "需求消退但利润尚可，控制库存，规划替代型号上市时间",
        "夕阳_需求消退": "需求消退但利润尚可，准备换代",
        "隐性衰退_回升": "销量平稳但毛利率已跌破历史水位，近期毛利率有所回升，观察回升是否可持续",
        "隐性衰退_利润侵蚀": "表面稳定实则利润被侵蚀，需预警",
        "预警增长_减收增利": "销量增长但利润仍低于历史峰值，毛利率近期回升，关注回升趋势",
        "预警增长_成本恶化": "销量增长掩盖利润恶化，立即查成本结构",
    },
}
