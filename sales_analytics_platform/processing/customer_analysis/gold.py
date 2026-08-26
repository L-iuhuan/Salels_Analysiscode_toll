"""
Gold 层表生成。

接收客户全景DataFrame和Silver层数据，生成8+张 Gold 层CSV表：
   客户全景、客户产品桥接、客户组合健康度、价格离散度、
   SKU生命周期、品类接受度、提价机会、降价策略试算、
   产品关联分析
"""

import os
import sys
import pandas as pd

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from analysis.rfm_pi import (
    score_rfm_pi,
)
from analysis.gold_builders import (
    build_customer_product_bridge as _build_customer_product_bridge,
    build_portfolio_health as _build_portfolio_health,
    build_product_association as _build_product_association,
)
from customer_analysis.dimensions import (
    calc_cross_customer_price_dispersion,
    calc_sku_lifecycle_stage,
    calc_category_acceptance,
    calc_markup_opportunity,
    calc_markdown_recommendation,
)
from b2b_v2.anomaly.inventory import get_inventory_aging, calc_customer_inventory_risk
from b2b_v2.anomaly.run import run_anomaly_detection
from b2b_v2.actions.run import run_action_suggestions
from config.settings import (
    CUSTOMER_COL_MAP,
    RFM_PI_WEIGHTS,
    CUSTOMER_JOURNEY_THRESHOLDS,
    VOLATILITY_METRICS,
    ESTIMATED_COST,
)
from b2b_v2.journey.stage_classifier import classify_customer_journey_stage
from b2b_v2.behavior.volatility import batch_calc_volatility
from b2b_v2.profitability.true_profit_estimator import batch_estimate_true_profit

from analysis.scoring import calc_composite_scores, calc_customer_tier
from customer_analysis.group_aggregation import run_group_aggregation
from customer_analysis.price_deep_dive import (
    calc_cross_customer_price_variation,
    calc_channel_price_comparison,
    calc_sales_owner_price_deviation,
    calc_segment_price_analysis,
)
from customer_analysis.trend_analysis import (
    calc_monthly_revenue_trend,
    calc_category_migration,
    calc_customer_forecast,
)

# [批次⑤ 缺陷A修复] OUTPUT_GOLD 统一从 config.settings 引入（指向包根 output/）
from config.settings import OUTPUT_GOLD


def generate_gold_tables(
    customer_df: pd.DataFrame,
    silver: dict,
    product_portrait_path: str = None,
    # P3: 可选适配器 — 提供则使用 DI 注入的适配器，否则使用直接 import（向后兼容）
    stage_classifier=None,
    volatility_calculator=None,
    profit_estimator=None,
    anomaly_detector=None,
    action_engine=None,
) -> dict:
    """生成所有 Gold 层表。

    参数:
        customer_df: calc_customer_portrait() 输出的客户全景DataFrame
        silver: Silver层数据字典
        product_portrait_path: 产品画像CSV路径（用于桥接）
        stage_classifier: P3 — IStageClassifier 适配器（可选）
        volatility_calculator: P3 — IVolatilityCalculator 适配器（可选）
        profit_estimator: P3 — IProfitEstimator 适配器（可选）
        anomaly_detector: P3 — IAnomalyDetector 适配器（可选，需配合库存逻辑）
        action_engine: P3 — IActionEngine 适配器（可选）

    返回:
        dict: {表名: DataFrame}
    """
    gold = {}
    df = customer_df.copy()

    # ---- 评分（默认填充值，缺失时使用） ----
    # 距上次采购天数缺失时默认180天（约6个月无交易=中等风险信号）
    df["距上次采购天数"] = df.get("距上次采购天数", 180)
    # 新品采购占比缺失时默认0（未采购新品）
    df["新品采购占比"] = df.get("新品采购占比", 0)
    # 常规平均采购间隔缺失时默认60天（行业平均采购周期经验值）
    df["常规平均采购间隔"] = df.get("常规平均采购间隔", 60)
    # 近12月毛利缺失时默认0
    df["近12月毛利"] = df.get("近12月毛利", 0)
    df = score_rfm_pi(
        df,
        channel_col="渠道类型" if "渠道类型" in df.columns else None,
        weights_by_channel=RFM_PI_WEIGHTS,
    )

    # ---- 行动建议（旧版静态建议，作为基础兜底） ----
    from customer_analysis.dimensions import generate_action_suggestions as _old_actions
    actions = _old_actions(df)
    df = df.merge(actions[["客户编号", "行动建议数", "行动建议"]], on="客户编号", how="left")

    # ---- B2B v2: 客户旅程阶段 ----
    cust_monthly = silver.get("customer_monthly")
    if cust_monthly is not None and len(cust_monthly) > 0:
        channel_map = (
            dict(zip(df["客户编号"], df["渠道类型"]))
            if "渠道类型" in df.columns else None
        )
        if stage_classifier is not None:
            journey_df = stage_classifier.classify(
                cust_monthly, CUSTOMER_JOURNEY_THRESHOLDS,
                channel_map=channel_map,
            )
        else:
            journey_df = classify_customer_journey_stage(
                cust_monthly, CUSTOMER_JOURNEY_THRESHOLDS,
                channel_map=channel_map,
            )
        if "距上次采购天数" in df.columns:
            df = df.drop(columns=["距上次采购天数"])
        df = df.merge(journey_df, on="客户编号", how="left")

    # ---- B2B v2: 采购波动性 ----
    if cust_monthly is not None and len(cust_monthly) > 0:
        if volatility_calculator is not None:
            volatility_df = volatility_calculator.batch_calculate(
                cust_monthly, VOLATILITY_METRICS,
            )
        else:
            volatility_df = batch_calc_volatility(cust_monthly, VOLATILITY_METRICS)
        df = df.merge(volatility_df, on="客户编号", how="left")

    # ---- B2B v2: 估算真实利润 ----
    if profit_estimator is not None:
        profit_df = profit_estimator.batch_estimate(df, ESTIMATED_COST)
    else:
        profit_df = batch_estimate_true_profit(df, ESTIMATED_COST)
    profit_df = profit_df.drop(columns=["近12月毛利"], errors="ignore")
    df = df.merge(profit_df, on="客户编号", how="left")

    # ---- v4.8: 帕累托利润分级 ----
    from analysis.scoring import calc_pareto_profit_tier
    df = calc_pareto_profit_tier(df)

    # ---- 客户评价体系 v2: 5维度评分 + 综合评级 + 双轴矩阵 ----
    # v4.15: 增长指标Winsorize截断(P1-P99), 防止极端值扭曲评分
    for col in ["增长动量", "近6月交易额环比增长率"]:
        if col in df.columns:
            lo, hi = df[col].quantile(0.01), df[col].quantile(0.99)
            df[col] = df[col].clip(lo, hi)

    df = calc_customer_tier(df)
    df = calc_composite_scores(df)

    # ==== 异常检测 + 库龄风险 ====
    product_portrait_path_actual = product_portrait_path or os.path.join(
        OUTPUT_GOLD, "gold_product_portrait.csv"
    )
    product_portrait_df = None
    if os.path.exists(product_portrait_path_actual):
        import pandas as _pd
        product_portrait_df = _pd.read_csv(product_portrait_path_actual, encoding="utf-8-sig")

    inv_aging = get_inventory_aging(
        inv_path=None,
        bom_path=None,
        silver=silver,
        product_portrait=product_portrait_df,
    )
    customer_inv_risk = calc_customer_inventory_risk(
        silver.get("customer_x_product", pd.DataFrame()),
        inv_aging,
    )

    # 合并客户维度库龄风险到全景表
    if len(customer_inv_risk) > 0:
        inv_cols = [c for c in customer_inv_risk.columns if c not in df.columns or c == "客户编号"]
        df = df.merge(customer_inv_risk[inv_cols], on="客户编号", how="left")

    if anomaly_detector is not None:
        anomaly_log = anomaly_detector.detect(
            df, silver,
            inv_aging=inv_aging,
            customer_inv_risk=customer_inv_risk,
        )
    else:
        anomaly_log = run_anomaly_detection(df, silver, inv_aging=inv_aging, customer_inv_risk=customer_inv_risk)
    # v4.4: tier injection helper (define early, before first use)
    tier_map = {}
    if "客户等级" in df.columns and "客户编号" in df.columns:
        tier_map_df_local = df[["客户编号", "客户等级"]].drop_duplicates()
        tier_map = dict(zip(tier_map_df_local["客户编号"], tier_map_df_local["客户等级"]))

    def _inject_tier(gold_df, cust_col="客户编号"):
        if gold_df is None or len(gold_df) == 0 or cust_col not in gold_df.columns:
            return gold_df
        if "客户等级" in gold_df.columns:
            return gold_df
        if tier_map:
            gold_df = gold_df.copy()
            gold_df["客户等级"] = gold_df[cust_col].map(tier_map).fillna("未知")
        return gold_df

    gold["异常日志"] = _inject_tier(anomaly_log)

    # ==== v4.3: 负毛利分析移到action engine之前 ====
    from b2b_v2.actions.negative_margin import analyze_negative_margin, summarize_negative_margin_for_alert
    neg_margin_df = analyze_negative_margin(
        silver.get("customer_x_product", pd.DataFrame()),
        customer_portrait=df,
    )
    if len(neg_margin_df) > 0:
        gold["负毛利分析"] = neg_margin_df
        neg_margin_summary = summarize_negative_margin_for_alert(neg_margin_df)
        n_severe = (neg_margin_df["负毛利严重等级"] == "严重").sum()
        n_watch = (neg_margin_df["负毛利严重等级"] == "关注").sum()
        total_loss = neg_margin_df["负毛利损失总额"].sum()
        recoverable = neg_margin_df["停售可增加利润"].sum()
        print(f"  [负毛利分析] 严重:{n_severe} 关注:{n_watch} "
              f"总损失:{abs(total_loss):.0f}元 可挽回:{recoverable:.0f}元")
    else:
        neg_margin_summary = {}

    # ==== 升级版行动建议（替换旧版静态建议） ====
    if action_engine is not None:
        actions_result = action_engine.suggest(
            df, anomaly_log=anomaly_log, silver=silver,
            inv_aging=inv_aging,
            product_portrait=product_portrait_df,
        )
    else:
        actions_result = run_action_suggestions(
            df, anomaly_log, silver,
            inv_aging=inv_aging,
            product_portrait=product_portrait_df,
            neg_margin_summary=neg_margin_summary,
        )
    # v4.4: 合并为4个清晰列（去除告警数量/行动建议数/行动建议冗余列）
    df = df.drop(columns=["行动建议数", "行动建议", "策略建议数量", "策略建议",
                           "策略名称", "策略原因", "告警数量", "紧急告警"], errors="ignore")
    df = df.merge(actions_result["actions"], on="客户编号", how="left")
    # 重命名: 策略建议→策略详细建议, 策略原因→策略触发原因
    if "策略建议" in df.columns:
        df = df.rename(columns={"策略建议": "策略详细建议"})
    if "策略原因" in df.columns:
        df = df.rename(columns={"策略原因": "策略触发原因"})
    # 合并告警数量+紧急告警→异常告警汇总
    if "紧急告警" in df.columns and "告警数量" in df.columns:
        df["异常告警汇总"] = df.apply(
            lambda r: f"[{int(r.get('告警数量',0))}条告警] {r.get('紧急告警','')}".strip()
            if pd.notna(r.get("紧急告警")) and str(r.get("紧急告警","")).strip()
            else "",
            axis=1
        )
        df = df.drop(columns=["告警数量", "紧急告警"], errors="ignore")
    elif "紧急告警" in df.columns:
        df = df.rename(columns={"紧急告警": "异常告警汇总"})
    # 确保空值
    for col in ["策略详细建议", "策略触发原因", "异常告警汇总"]:
        if col in df.columns:
            df[col] = df[col].fillna("")
    # v4.4: 异常告警汇总空值补占位符
    if "异常告警汇总" in df.columns:
        df["异常告警汇总"] = df["异常告警汇总"].replace("", "[0条告警]")

    if len(actions_result.get("cross_sell", pd.DataFrame())) > 0:
        gold["交叉销售建议"] = _inject_tier(actions_result["cross_sell"])

    # ---- 客户×产品桥接 ----
    gold["客户产品桥接"] = _build_customer_product_bridge(silver, product_portrait_path)

    # ---- 客户组合健康度（先于集团聚合，后者依赖衰退风险列） ----
    gold["客户组合健康度"] = _inject_tier(_build_portfolio_health(gold["客户产品桥接"]))
    # 将组合健康度的衰退风险列合并到客户全景，供集团聚合使用
    if len(gold["客户组合健康度"]) > 0:
        ph_cols = ["客户编号"] + [c for c in ["预警增长_金额", "隐性衰退_金额", "衰退期_金额", "衰退风险品金额占比"]
                                    if c in gold["客户组合健康度"].columns]
        df = df.merge(gold["客户组合健康度"][ph_cols], on="客户编号", how="left")

    # ==== 集团聚合（传入customer_x_product以计算真实产品线并集） ====
    group_result = run_group_aggregation(
        df,
        cust_x_prod=silver.get("customer_x_product"),
        cat_col=CUSTOMER_COL_MAP.get("品类列", "产品一级分类"),
    )
    df = group_result["customer_df"]
    group_df = group_result["group_df"]

    # v4.16: 列排序+精简 — 删除冗余评价列，7模块重组
    _drop_cols = [c for c in ["客户类别", "RFMπ_层级", "客户旅程阶段", "稳定性等级", "_estimated",
                               "呆滞品种数", "超1年品种数", "呆滞金额占比", "超1年金额占比", "加权平均超180天占比",
                               "风险评级分", "机会评级分", "所属区域"]
                  if c in df.columns]
    if _drop_cols:
        df = df.drop(columns=_drop_cols)
    # 列名优化：客户编号→客户名称，机会评级→增长潜力，帕累托→利润贡献等级，利润等级→利润率情况
    df = df.rename(columns={
        "客户编号": "客户名称", "机会评级": "增长潜力",
        "帕累托利润分级": "利润贡献等级", "利润等级": "利润率情况",
    })
    # 向后兼容：下游函数可能仍引用旧列名
    df["客户编号"] = df["客户名称"]
    df["帕累托利润分级"] = df["利润贡献等级"]
    df["机会评级"] = df["增长潜力"]
    df["利润等级"] = df["利润率情况"]
    if "策略名称" not in df.columns and "策略详细建议" in df.columns:
        df["策略名称"] = ""
    _order = ["客户名称","业务负责人","渠道类型","客户层级","活跃状态","综合价值层级","双轴分类",
              "增长潜力","风险评级","客户生命周期","利润率情况","主要SKU阶段","利润贡献等级",
              "近12月收入","前12月收入","收入增长率","YoY同比增速","连续增长月数","连续下滑月数",
              "近12月毛利","近12月毛利率","毛利率跌幅%","估算真实利润","估算真实利润率",
              "品种总数","在采品种数","实际品类数","产品线数","主导产品线","主导产品线占比",
              "品种集中度Top3","Top5集中度","强依赖标记","品类机会标签","主导品类","主导品类占比",
              "ASP_加权","ASP_跌幅%","低价品种收入占比","中价品种收入占比","高价品种收入占比",
              "近12月数量","订单数","订单处理成本","订单处理成本率",
              "常规平均采购间隔","距上次采购天数","采购中断预警","零采购月占比",
              "收入CV","最大单月跌幅","趋势R²","增长动量","近6月交易额环比增长率",
              "策略详细建议","策略触发原因","异常告警汇总",
              "价值贡献分","增长动能分","稳定关系分","战略潜力分","效率运营分","综合价值分",
              "新品采购占比","是否采购新品","新品采购额","新品品种数",
              "R_得分","F_得分","M_得分","P_得分","RFMπ_综合分",
    ]
    _existing = [c for c in _order if c in df.columns]
    _remaining = [c for c in df.columns if c not in _existing and c != "策略名称"]
    df = df[_existing + _remaining]

    gold["客户全景"] = df

    # ---- 集团聚合 ----
    if len(group_df) > 0:
        gold["集团聚合"] = group_df

    # ---- 价格离散度 ----
    cxp = silver["customer_x_product"].copy()
    dispersion = calc_cross_customer_price_dispersion(cxp)
    if "产品品种" in dispersion.columns:
        dispersion = dispersion.rename(columns={"产品品种": "产品名称"})
    gold["价格离散度"] = dispersion

    # ---- SKU生命周期 ----
    prod_monthly = silver["product_monthly"].copy()
    sku_stages = calc_sku_lifecycle_stage(prod_monthly)
    gold["SKU生命周期"] = sku_stages

    # ---- 品类接受度（条件性） ----
    cat_sub_col = CUSTOMER_COL_MAP.get("品类细分列", "型号_产品品类")
    if cat_sub_col in cxp.columns:
        cat_acc = calc_category_acceptance(cxp, category_col=cat_sub_col)
        gold["品类接受度"] = _inject_tier(cat_acc)

    # ---- 提价机会 ----
    markup = calc_markup_opportunity(cxp)
    # [批次⑦] 只输出有效行（可提价标记=True）：category 模式下 categorical groupby
    # 默认 observed=False 展开客户×产品叉积（真实数据 2,633,504 行 / 178.6MB），
    # 其中有效行仅 505 行；未标记行无下游消费（2026-08-25 用户拍板确认）。
    # 过滤后 CSV 降至几十 KB，Excel 报告（若开启）同步瘦身。
    markup = markup[markup["可提价标记"]]
    gold["提价机会"] = _inject_tier(markup)

    # ---- 降价策略试算 ----
    markdown = calc_markdown_recommendation(cxp)
    gold["降价策略试算"] = markdown

    # ---- Phase 3: 价格深度分析 ----
    # 跨客户价格差异
    price_var = calc_cross_customer_price_variation(cxp, df)
    if len(price_var) > 0:
        gold["跨客户价格差异"] = price_var

    # v4.8: 定价合理性分析
    from customer_analysis.price_deep_dive import calc_pricing_fairness
    fairness_df = calc_pricing_fairness(cxp, df)
    if len(fairness_df) > 0:
        gold["定价合理性分析"] = fairness_df
        n_anomaly = (fairness_df["异常低价标记"] == "异常低价-需审查").sum()
        print(f"  [定价合理性] 异常低价: {n_anomaly} 条 (共{len(fairness_df)}条)")

    # ---- v4.11: 销售能力画像 ----
    from b2b_v2.actions.sales_profiling import build_sales_profile
    sales_profile = build_sales_profile(df)
    if len(sales_profile) > 0:
        gold["销售画像"] = sales_profile
        gc = sales_profile["能力等级"].value_counts().to_dict()
        print(f"  [销售画像] {len(sales_profile)}人 {gc}")

    # ---- v4.15: 品类擅长分析 ----
    from b2b_v2.actions.category_aptitude import build_category_aptitude
    cat_apt = build_category_aptitude(df, silver)
    if len(cat_apt) > 0:
        gold["品类擅长"] = cat_apt
        print(f"  [品类擅长] {len(cat_apt)}条记录 {cat_apt['业务负责人'].nunique()}人")

    # ---- v4.16: 周期经营分析（跳过单独产品线/SKU周期表） ----
    from customer_analysis.period_analysis import (
        build_period_overview, build_volume_price_decomposition,
        build_kaaa_monthly_radar, build_sales_period_performance,
    )
    period_overview = build_period_overview(silver, df)
    if len(period_overview) > 0:
        gold["经营周期总览"] = period_overview
    vp_decomp = build_volume_price_decomposition(silver)
    if len(vp_decomp) > 0:
        gold["量价拆解"] = vp_decomp
    kaaa_radar = build_kaaa_monthly_radar(silver, df)
    if len(kaaa_radar) > 0:
        gold["KA_AA月度雷达"] = kaaa_radar
    sales_period = build_sales_period_performance(silver, df)
    if len(sales_period) > 0:
        gold["销售人员周期表现"] = sales_period

    # ---- v4.16: 产品研发建议 ----
    from customer_analysis.rd_recommendation import build_rd_recommendations
    rd_rec = build_rd_recommendations(silver, df)
    if len(rd_rec) > 0:
        gold["产品研发建议"] = rd_rec
        print(f"  [研发建议] {len(rd_rec)}个产品，二代立项{(rd_rec['研发建议']=='二代立项').sum()}个")

    # 渠道价格对比
    channel_price = calc_channel_price_comparison(cxp, df)
    if len(channel_price) > 0:
        gold["渠道价格对比"] = channel_price

    # 业务员定价偏离
    owner_dev = calc_sales_owner_price_deviation(cxp, df)
    if len(owner_dev) > 0:
        gold["业务员定价偏离"] = owner_dev

    # 市场细分价格
    seg_price = calc_segment_price_analysis(cxp, df)
    if len(seg_price) > 0:
        gold["市场细分价格"] = seg_price

    # ---- 产品关联分析（购物篮规则） ----
    gold["产品关联分析"] = _build_product_association(silver)

    # ---- Phase 4: 趋势分析深化 ----
    cust_monthly = silver.get("customer_monthly")
    latest_month = silver["product_monthly"]["_月"].max() if "product_monthly" in silver else None

    if cust_monthly is not None and latest_month is not None:
        # 月度营收趋势
        trend = calc_monthly_revenue_trend(cust_monthly, latest_month)
        if len(trend) > 0:
            gold["客户月度趋势"] = _inject_tier(trend)

        # 品类迁移分析
        migration = calc_category_migration(cxp)
        if len(migration) > 0:
            gold["产品线迁移"] = _inject_tier(migration)

        # 客户ETS预测
        forecast = calc_customer_forecast(cust_monthly, latest_month)
        if len(forecast) > 0:
            gold["客户预测"] = _inject_tier(forecast)

    return gold


