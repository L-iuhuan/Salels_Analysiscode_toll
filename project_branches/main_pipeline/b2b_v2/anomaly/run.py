"""
异常检测汇总入口 — 串联所有检测器，返回合并异常日志。
"""

import pandas as pd

from b2b_v2.anomaly.rules import (
    detect_purchase_interruption,
    detect_revenue_cliff,
    detect_price_anomaly,
    detect_concentration_risk,
    detect_inventory_stagnant,
    detect_dead_stock,
)
from b2b_v2.anomaly.isolation_forest import detect_anomaly_isolation_forest


def run_anomaly_detection(
    customer_df: pd.DataFrame,
    silver: dict,
    inv_aging: pd.DataFrame = None,
    customer_inv_risk: pd.DataFrame = None,
) -> pd.DataFrame:
    """运行全部检测器，返回合并后的异常日志。

    参数:
        customer_df: 客户全景表 (from calc_customer_portrait)
        silver: Silver层数据字典
        inv_aging: 产成品维度库龄表 (from get_inventory_aging)
        customer_inv_risk: 客户维度库龄风险 (from calc_customer_inventory_risk)

    返回:
        DataFrame: 异常日志 [客户编号, 异常类型, 异常等级, 异常详情]
    """
    all_results = []

    # A1: 采购中断
    a1 = detect_purchase_interruption(customer_df)
    if len(a1) > 0:
        all_results.append(a1)

    # A2: 营收断崖
    a2 = detect_revenue_cliff(customer_df)
    if len(a2) > 0:
        all_results.append(a2)

    # A3: 价格异常
    a3 = detect_price_anomaly(customer_df, silver)
    if len(a3) > 0:
        all_results.append(a3)

    # A4: 集中度风险
    a4 = detect_concentration_risk(customer_df)
    if len(a4) > 0:
        all_results.append(a4)

    # A5: 库存呆滞 (需要客户维度库龄风险)
    if customer_inv_risk is not None and len(customer_inv_risk) > 0:
        a5 = detect_inventory_stagnant(customer_inv_risk)
        if len(a5) > 0:
            all_results.append(a5)

    # A6: 长库龄积压 (产品维度 — 单独输出到独立表，不混入客户异常日志)
    if inv_aging is not None and len(inv_aging) > 0:
        a6 = detect_dead_stock(inv_aging, silver)
        if len(a6) > 0:
            a6["异常类型"] = "长库龄积压(产品)"
            all_results.append(a6.rename(columns={"产品品种": "客户编号"}))

    if not all_results:
        return pd.DataFrame(columns=["客户编号", "异常类型", "异常等级", "异常详情"])

    combined = pd.concat(all_results, ignore_index=True)

    # Sort by severity: 高 > 中 > 低
    severity_order = {"高": 0, "中": 1, "低": 2}
    combined["_severity_sort"] = combined["异常等级"].map(severity_order).fillna(3)
    combined = combined.sort_values(["_severity_sort", "异常类型"], kind='stable')
    combined = combined.drop(columns=["_severity_sort"])

    print(f"  [异常检测] 共发现 {len(combined)} 条异常 "
          f"(高={(combined['异常等级']=='高').sum()}, "
          f"中={(combined['异常等级']=='中').sum()}, "
          f"低={(combined['异常等级']=='低').sum()})")

    return combined.reset_index(drop=True)
