"""
行动建议汇总入口 — 串联 L1/L2 告警+策略 + L3 交叉销售。
"""

import pandas as pd

from b2b_v2.actions.rules_engine import generate_actions_v2
from b2b_v2.actions.cross_sell import generate_cross_sell


def run_action_suggestions(
    customer_df: pd.DataFrame,
    anomaly_log: pd.DataFrame = None,
    silver: dict = None,
    inv_aging: pd.DataFrame = None,
    product_portrait: pd.DataFrame = None,
    product_assoc: pd.DataFrame = None,
) -> dict:
    """生成完整行动建议。

    参数:
        customer_df: 客户全景表
        anomaly_log: 异常检测日志
        silver: Silver层数据
        inv_aging: 产成品维度库龄表
        product_portrait: 产品画像表 (用于交叉销售 + L3)
        product_assoc: 产品关联分析结果 (用于L3)

    返回:
        dict: {
            "actions": DataFrame [客户编号, 告警数量, 紧急告警, 策略建议数量, 策略建议],
            "cross_sell": DataFrame [客户编号, 推荐品种数, 推荐品种, 推荐理由],
        }
    """
    # L1 + L2
    actions = generate_actions_v2(customer_df, anomaly_log, silver)

    # L3: Cross-sell
    if silver is not None and "customer_x_product" in (silver or {}):
        cross_sell = generate_cross_sell(
            silver["customer_x_product"],
            product_portrait=product_portrait,
            inv_aging=inv_aging,
            product_assoc=product_assoc,
        )
    else:
        cross_sell = pd.DataFrame(columns=["客户编号", "推荐品种数", "推荐品种", "推荐理由"])

    return {"actions": actions, "cross_sell": cross_sell}
