"""
Task 6: 估算真实利润贡献度 (Estimated True Profit).

在毛利率基础上，扣除估算的服务成本，得到更真实的利润贡献。

真实利润 = 毛利 - 订单处理成本 - 物流成本 - 售后成本 - 资金占用成本

所有参数从 settings.ESTIMATED_COST 读取。
输出字段标记为"估算值"，待真实成本数据就绪后替换。
"""

import sys, os
import pandas as pd
import numpy as np

_SRC_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from config.settings import CREDIT_THRESHOLDS as _CREDIT_TH


def estimate_true_profit(
    customer_row: dict,
    config: dict = None,
) -> dict:
    """
    估算单个客户的真实利润贡献。

    参数
    ----------
    customer_row : dict
        客户数据字典，需包含以下键:
        - 近12月毛利 (float): 近12个月的毛利总额
        - 近12月数量 (float): 近12个月的发货数量
        - 近12月收入 (float): 近12个月的收入总额
        - 订单数 (float, optional): 近12月订单数，默认从收入估算
        - 退货金额 (float, optional): 近12月退货金额，默认 0
        - 应收账款 (float, optional): 当前应收账款余额，默认 0
        - 客户等级 (str, optional): A/B/C 用于 DSO 估算
    config : dict or None
        成本参数，从 settings.ESTIMATED_COST 读取，键:
        - order_processing_cost (默认 50.0 元/单)
        - logistics_cost_rate (默认 0.02, 营收比例)
        - aftersales_cost_ratio (默认 0.30)
        - capital_cost_annual_rate (默认 0.06)

    返回
    -------
    dict
        {
            "近12月毛利": float,
            "估算真实利润": float,
            "估算真实利润率": float,
            "利润等级": str,  # "高利润" | "微利" | "亏损"
            "订单处理成本": float,
            "物流成本": float,
            "售后成本": float,
            "资金占用成本": float,
        }

    异常
    ------
    - 缺少关键字段 → 该成本项设为 0，不阻断
    - 所有成本项合计 > 毛利 → 利润等级 = "亏损"
    """
    cfg = config or {}

    # ── 成本参数 ──
    order_cost = cfg.get("order_processing_cost", 50.0)
    # 物流成本：按营收比例估算（半导体行业量级大，不宜按件计费）
    logistics_cost_rate = cfg.get("logistics_cost_rate", 0.02)
    aftersales_ratio = cfg.get("aftersales_cost_ratio", 0.30)
    capital_rate = cfg.get("capital_cost_annual_rate", 0.06)

    # ── 输入值 ──
    gross_profit = float(customer_row.get("近12月毛利", 0) or 0)
    quantity = float(customer_row.get("近12月数量", 0) or 0)
    revenue = float(customer_row.get("近12月收入", 0) or 0)
    order_count = float(customer_row.get("订单数", 0) or max(1, revenue / 5000))  # 默认按每单5000元估算
    return_amount = float(customer_row.get("退货金额", 0) or 0)
    receivable = float(customer_row.get("应收账款", 0) or 0)

    # DSO: 按客户等级估算（从配置读取）
    tier = str(customer_row.get("客户等级", "B"))
    dso_map = {"A": _CREDIT_TH["dso_a"], "B": _CREDIT_TH["dso_b"], "C": _CREDIT_TH["dso_c"]}
    dso = dso_map.get(tier, _CREDIT_TH["dso_b"])

    # ── 成本计算 ──
    # 1. 订单处理成本
    processing_cost = order_count * order_cost

    # 2. 物流成本（按营收比例估算，适配半导体行业量级）
    logistics_cost = revenue * logistics_cost_rate

    # 3. 售后成本
    aftersales_cost = return_amount * aftersales_ratio
    # 如无退货金额，按收入估算 2% 退货率
    if return_amount <= 0 and revenue > 0:
        aftersales_cost = revenue * 0.02 * aftersales_ratio

    # 4. 资金占用成本
    capital_cost = receivable * capital_rate * dso / 365.0

    # ── 真实利润 ──
    total_cost = processing_cost + logistics_cost + aftersales_cost + capital_cost
    true_profit = gross_profit - total_cost
    true_margin = true_profit / max(revenue, 1) * 100

    # 利润等级
    if true_margin > 15:
        tier_label = "高利润"
    elif true_margin > 0:
        tier_label = "微利"
    else:
        tier_label = "亏损"

    return {
        "近12月毛利": round(gross_profit, 2),
        "估算真实利润": round(true_profit, 2),
        "估算真实利润率": round(true_margin, 2),
        "利润等级": tier_label,
        "订单处理成本": round(processing_cost, 2),
        "物流成本": round(logistics_cost, 2),
        "售后成本": round(aftersales_cost, 2),
        "资金占用成本": round(capital_cost, 2),
    }


def batch_estimate_true_profit(
    customer_profile_df: pd.DataFrame,
    config: dict = None,
    cust_col: str = "客户编号",
) -> pd.DataFrame:
    """
    批量估算所有客户的真实利润。

    参数
    ----------
    customer_profile_df : DataFrame
        客户画像表，需包含近12月毛利、近12月收入、近12月数量等列。
    config : dict or None
        成本参数。
    cust_col : str
        客户编号列名。

    返回
    -------
    DataFrame
        每客户一行，包含真实利润相关列。
    """
    if customer_profile_df is None or len(customer_profile_df) == 0:
        return pd.DataFrame(columns=[
            cust_col, "估算真实利润", "估算真实利润率", "利润等级",
        ])

    results = []
    for _, row in customer_profile_df.iterrows():
        result = estimate_true_profit(row.to_dict(), config)
        result[cust_col] = row.get(cust_col, "")
        results.append(result)

    out = pd.DataFrame(results)
    cols = [
        cust_col, "近12月毛利", "估算真实利润", "估算真实利润率",
        "利润等级", "订单处理成本", "物流成本", "售后成本", "资金占用成本",
    ]
    return out[[c for c in cols if c in out.columns]]
