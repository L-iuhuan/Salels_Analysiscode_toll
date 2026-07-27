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

OUTPUT_GOLD = os.path.join(PROJECT_ROOT, "output", "gold")


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

    # ---- 客户评价体系 v2: 5维度评分 + 综合评级 + 双轴矩阵 ----
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
    gold["异常日志"] = anomaly_log

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
        )
    # Override old action columns with v2 results
    df = df.drop(columns=["行动建议数", "行动建议"], errors="ignore")
    df = df.merge(actions_result["actions"], on="客户编号", how="left")
    # Build backward-compatible "行动建议" = 紧急告警 + 策略建议
    if "告警数量" in df.columns:
        df["行动建议数"] = df["告警数量"].fillna(0).astype(int)
    else:
        df["行动建议数"] = 0
    df["行动建议"] = df.apply(
        lambda r: "; ".join(
            s for s in [
                str(r.get("紧急告警", "")).strip() if pd.notna(r.get("紧急告警")) else "",
                str(r.get("策略建议", "")).strip() if pd.notna(r.get("策略建议")) else "",
            ] if s
        ), axis=1
    )
    df["行动建议"] = df["行动建议"].replace("", "暂无明显行动项")

    if len(actions_result.get("cross_sell", pd.DataFrame())) > 0:
        gold["交叉销售建议"] = actions_result["cross_sell"]

    # ---- 客户×产品桥接 ----
    gold["客户产品桥接"] = _build_customer_product_bridge(silver, product_portrait_path)

    # ---- 客户组合健康度（先于集团聚合，后者依赖衰退风险列） ----
    gold["客户组合健康度"] = _build_portfolio_health(gold["客户产品桥接"])
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

    gold["客户全景"] = df

    # ---- 集团聚合 ----
    if len(group_df) > 0:
        gold["集团聚合"] = group_df

    # ---- 价格离散度 ----
    cxp = silver["customer_x_product"].copy()
    dispersion = calc_cross_customer_price_dispersion(cxp)
    gold["价格离散度"] = dispersion

    # ---- SKU生命周期 ----
    prod_monthly = silver["product_monthly"].copy()
    sku_stages = calc_sku_lifecycle_stage(prod_monthly)
    gold["SKU生命周期"] = sku_stages

    # ---- 品类接受度（条件性） ----
    cat_col = CUSTOMER_COL_MAP.get("品类列", "产品一级分类")
    if cat_col in cxp.columns:
        cat_acc = calc_category_acceptance(cxp, category_col=cat_col)
        gold["品类接受度"] = cat_acc

    # ---- 提价机会 ----
    markup = calc_markup_opportunity(cxp)
    gold["提价机会"] = markup

    # ---- 降价策略试算 ----
    markdown = calc_markdown_recommendation(cxp)
    gold["降价策略试算"] = markdown

    # ---- Phase 3: 价格深度分析 ----
    # 跨客户价格差异
    price_var = calc_cross_customer_price_variation(cxp, df)
    if len(price_var) > 0:
        gold["跨客户价格差异"] = price_var

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
            gold["客户月度趋势"] = trend

        # 品类迁移分析
        migration = calc_category_migration(cxp)
        if len(migration) > 0:
            gold["品类迁移"] = migration

        # 客户ETS预测
        forecast = calc_customer_forecast(cust_monthly, latest_month)
        if len(forecast) > 0:
            gold["客户预测"] = forecast

    return gold


