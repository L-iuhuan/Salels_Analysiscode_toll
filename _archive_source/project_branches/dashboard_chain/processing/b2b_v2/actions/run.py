"""
行动建议汇总入口 — 串联 L1 告警 + 6策略引擎 + L3 交叉销售。
v4.3: 传递 neg_margin_summary + cross_sell_map 到策略引擎。
"""

import pandas as pd

from b2b_v2.actions.rules_engine import generate_actions_v2
from b2b_v2.actions.cross_sell import generate_cross_sell


def run_action_suggestions(
    customer_df, anomaly_log=None, silver=None,
    inv_aging=None, product_portrait=None, product_assoc=None,
    neg_margin_summary=None,  # v4.3: 负毛利摘要
) -> dict:
    # Build cross-sell map for S4
    cross_sell_map = {}
    if silver is not None and "customer_x_product" in (silver or {}):
        try:
            cross_sell = generate_cross_sell(
                silver["customer_x_product"],
                product_portrait=product_portrait,
                inv_aging=inv_aging,
                product_assoc=product_assoc,
            )
            for _, row in cross_sell.iterrows():
                recs = str(row.get("推荐品种","")).split("; ")
                cross_sell_map[row["客户编号"]] = [r for r in recs if r]
        except Exception:
            pass

    actions = generate_actions_v2(
        customer_df, anomaly_log, silver,
        neg_margin_summary=neg_margin_summary,
        cross_sell_map=cross_sell_map,
    )

    # L3 already computed above
    if silver is None or "customer_x_product" not in (silver or {}):
        cross_sell = pd.DataFrame(columns=["客户编号","推荐品种数","推荐品种","推荐理由"])
    else:
        try:
            cross_sell = generate_cross_sell(
                silver["customer_x_product"],
                product_portrait=product_portrait,
                inv_aging=inv_aging,
                product_assoc=product_assoc,
            )
        except Exception:
            cross_sell = pd.DataFrame(columns=["客户编号","推荐品种数","推荐品种","推荐理由"])

    return {"actions": actions, "cross_sell": cross_sell}
