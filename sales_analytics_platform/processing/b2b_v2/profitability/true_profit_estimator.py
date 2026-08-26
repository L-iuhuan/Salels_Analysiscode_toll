"""
Task 6: 真实利润贡献度 (True Profit).

v4.5: 删除物流成本/售后成本/资金占用成本估算（缺乏真实数据，估算值无区分度）。
真实利润 = 毛利 - 订单处理成本。

物流成本、售后成本、资金占用成本在缺乏真实物流数据/退货数据/应收账款数据时，
统一按营收比例估算对所有客户无区分度，反而引入噪声。待真实成本数据就绪后重新启用。
"""

import sys, os
import pandas as pd
import numpy as np

_SRC_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)


def estimate_true_profit(customer_row: dict, config: dict = None) -> dict:
    """估算单个客户的真实利润贡献。

    真实利润 = 毛利 - 订单处理成本（50元/单）
    """
    cfg = config or {}
    order_cost = cfg.get("order_processing_cost", 50.0)

    gross_profit = float(customer_row.get("近12月毛利", 0) or 0)
    revenue = float(customer_row.get("近12月收入", 0) or 0)
    default_rev_per_order = float(cfg.get("default_revenue_per_order", 5000.0))
    order_count = float(customer_row.get("订单数", 0) or max(1, revenue / default_rev_per_order))

    if revenue <= 0:
        processing_cost = 0.0
    else:
        processing_cost = order_count * order_cost

    true_profit = gross_profit - processing_cost
    true_margin = true_profit / max(revenue, 1) * 100

    # 利润等级: >=35%高利润, 0~35%微利, <=0亏损
    margin_tiers = cfg.get("profit_margin_tiers", {"high_profit_pct": 35, "low_profit_pct": 0})
    _high_pct = margin_tiers.get("high_profit_pct", 35)
    _low_pct = margin_tiers.get("low_profit_pct", 0)
    if true_margin >= _high_pct:
        tier_label = "高利润"
    elif true_margin > _low_pct:
        tier_label = "微利"
    else:
        tier_label = "亏损"

    return {
        "近12月毛利": round(gross_profit, 2),
        "估算真实利润": round(true_profit, 2),
        "估算真实利润率": round(true_margin, 2),
        "利润等级": tier_label,
        "订单处理成本": round(processing_cost, 2),
    }


def batch_estimate_true_profit(customers_df: pd.DataFrame, config: dict = None) -> pd.DataFrame:
    """批量估算真实利润。"""
    if customers_df is None or len(customers_df) == 0:
        print("  [利润] 输入为空，返回空表")
        return pd.DataFrame(columns=["客户编号", "估算真实利润", "估算真实利润率", "利润等级", "订单处理成本"])
    results = []
    for _, row in customers_df.iterrows():
        r = estimate_true_profit(row.to_dict(), config)
        r["客户编号"] = row["客户编号"]
        results.append(r)
    result = pd.DataFrame(results)
    n_high = (result["利润等级"] == "高利润").sum()
    n_low = (result["利润等级"] == "微利").sum()
    n_loss = (result["利润等级"] == "亏损").sum()
    print(f"  [利润] 高利润:{n_high} 微利:{n_low} 亏损:{n_loss} (>=35%高利润, 0-35%微利)")

    # Only return new columns (not full df, to avoid duplicate column suffixes on merge)
    return result[["客户编号", "估算真实利润", "估算真实利润率", "利润等级", "订单处理成本"]]
