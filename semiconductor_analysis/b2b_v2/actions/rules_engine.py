"""
行动建议引擎 — L1 紧急告警 + L2 策略建议。

L1: 直接对应异常检测"高"等级结果，生成具体操作指令。
L2: 基于客户生命周期+画像组合，生成中长期策略方向。
"""

import pandas as pd
import numpy as np


# ── L1: Emergency alerts from anomaly log ────────────────────

_L1_TEMPLATES = {
    "采购中断": {
        "高": "立即联系客户确认需求状态，建议48h内完成回访。若客户已切换供应商，启动流失挽回流程",
        "中": "关注客户采购节奏，本周内联系确认订单计划",
    },
    "营收断崖": {
        "高": "启动客户挽回流程，销售总监介入。排查是否丢单、客户自研替代或切换到竞品",
        "中": "连续跟进客户需求变化，确认是否为季节性波动",
    },
    "价格异常": {
        "高": "审核最近3笔报价，排查是否为定价错误或未经审批的大幅折扣",
        "中": "关注该客户定价策略，检查是否有同品类价格参照",
    },
    "集中度风险": {
        "高": "制定替代品种引入计划，降低单点依赖风险。优先推客户已试但未批量采购的品类",
        "中": "关注Top1品种的市场供应情况，提前储备替代方案",
    },
    "库存呆滞": {
        "高": "协商促销去库存方案，目标30天内降低50%。可考虑捆绑销售或阶梯折扣",
        "中": "在客户拜访中优先推进呆滞品种的增购，提供首单优惠",
        "低": "月度复盘时关注呆滞品种去化进度",
    },
    "长库龄积压": {
        "高": "超1年库存积压严重，建议启动特价清仓或报废处理评估，优先回笼资金",
    },
}


def _generate_l1_alerts(anomaly_log: pd.DataFrame) -> pd.DataFrame:
    """从异常日志生成L1紧急告警。

    返回: DataFrame keyed by 客户编号
    """
    if len(anomaly_log) == 0:
        return pd.DataFrame(columns=["客户编号", "告警数量", "紧急告警"])

    # Group by customer
    alerts = []
    for cid, group in anomaly_log.groupby("客户编号"):
        high_alerts = []
        mid_low_alerts = []
        for _, row in group.iterrows():
            atype = row["异常类型"]
            level = row["异常等级"]
            templates = _L1_TEMPLATES.get(atype, {})
            msg = templates.get(level)
            if msg is None:
                msg = templates.get("高", f"{atype}({level})")

            detail = row.get("异常详情", "")
            if level == "高":
                high_alerts.append(f"[紧急] {msg} | {detail}")
            else:
                mid_low_alerts.append(f"[关注] {msg} | {detail}")

        # High alerts first
        all_msgs = high_alerts + mid_low_alerts
        alerts.append({
            "客户编号": cid,
            "告警数量": len(all_msgs),
            "紧急告警": "; ".join(all_msgs) if all_msgs else "",
        })

    return pd.DataFrame(alerts)


# ── L2: Strategic recommendations ────────────────────────────

_L2_RULES = [
    # (condition, suggestion)
    # condition is a lambda: row → bool
    {
        "condition": lambda r: r.get("客户生命周期") in ("衰退期", "休眠期", "流失期")
                              and r.get("近12月收入", 0) > r.get("_median_rev", 0),
        "suggestion": "启动关键客户挽回计划：定制化报价+FAE上门技术对接，重点确认是否切换竞品",
    },
    {
        "condition": lambda r: r.get("客户生命周期") == "导入期"
                              and r.get("在采品种数", 0) >= 3,
        "suggestion": "安排FAE技术对接，加速Design-in。提供样品和评估板，缩短导入周期",
    },
    {
        "condition": lambda r: r.get("客户生命周期") == "成熟期"
                              and r.get("低价品种收入占比", 0) > 0.5,
        "suggestion": "推动产品升级替换：推荐高性能/高毛利替代型号，提升ASP和毛利率",
    },
    {
        "condition": lambda r: r.get("客户生命周期") == "休眠期"
                              and r.get("近12月收入", 0) > r.get("_p75_rev", 0),
        "suggestion": "安排销售回访了解流失原因。如有历史退货或质量问题，优先解决售后",
    },
    {
        "condition": lambda r: r.get("客户生命周期") == "爬坡期"
                              and r.get("在采品种数", 0) < 3,
        "suggestion": "客户处于增长期但品种单一，建议交叉推荐关联品类扩大钱包份额",
    },
    {
        "condition": lambda r: r.get("新品采购占比", 0) > 0.30,
        "suggestion": "新品渗透良好，可作为标杆案例推广。关注新品供应稳定性，确保持续供货",
    },
    {
        "condition": lambda r: r.get("强依赖标记") in ("是", True, "1", 1)
                              or r.get("品种集中度Top3", 0) > 0.85,
        "suggestion": "集中度风险较高，建议引导多品种采购。优先从客户已用品类中推荐替代型号",
    },
    {
        "condition": lambda r: r.get("连续下滑月数", 0) >= 3
                              and r.get("近12月收入", 0) > r.get("_median_rev", 0),
        "suggestion": "连续下滑但体量较大，建议销售上门了解客户生产计划变化，排查是否客户业务收缩",
    },
    {
        "condition": lambda r: r.get("距上次采购天数", 999) > r.get("常规平均采购间隔", 60) * 1.5,
        "suggestion": "采购节奏放慢，建议联系客户确认后续订单排期，避免被动等待导致库存积压",
    },
    {
        "condition": lambda r: r.get("主要SKU阶段") == "衰退出清",
        "suggestion": "客户在用退市品种，需引导迁移替代型号。提供兼容替代方案及样品测试",
    },
]


def _generate_l2_strategic(customer_df: pd.DataFrame) -> pd.DataFrame:
    """从客户画像生成L2策略建议。

    返回: DataFrame keyed by 客户编号
    """
    if len(customer_df) == 0:
        return pd.DataFrame(columns=["客户编号", "策略建议数量", "策略建议"])

    df = customer_df.copy()

    # Pre-compute reference values for conditions
    if "近12月收入" in df.columns:
        df["_median_rev"] = df["近12月收入"].median()
        df["_p75_rev"] = df["近12月收入"].quantile(0.75)

    results = []
    for _, row in df.iterrows():
        suggestions = []
        for rule in _L2_RULES:
            try:
                if rule["condition"](row):
                    suggestions.append(rule["suggestion"])
            except (KeyError, TypeError):
                continue

        results.append({
            "客户编号": row["客户编号"],
            "策略建议数量": len(suggestions),
            "策略建议": "; ".join(suggestions) if suggestions else "",
        })

    return pd.DataFrame(results)


# ── Combined entry ───────────────────────────────────────────

def generate_actions_v2(
    customer_df: pd.DataFrame,
    anomaly_log: pd.DataFrame = None,
    silver: dict = None,
) -> pd.DataFrame:
    """生成升级版行动建议 (L1 + L2)。

    参数:
        customer_df: 客户全景表
        anomaly_log: 异常日志 (from run_anomaly_detection)
        silver: Silver层数据 (unused, reserved for future)

    返回:
        DataFrame: [客户编号, 告警数量, 紧急告警, 策略建议数量, 策略建议]
    """
    # L1: Emergency alerts from anomaly log
    if anomaly_log is not None and len(anomaly_log) > 0:
        l1 = _generate_l1_alerts(anomaly_log)
    else:
        l1 = pd.DataFrame(columns=["客户编号", "告警数量", "紧急告警"])

    # L2: Strategic recommendations from customer profile
    l2 = _generate_l2_strategic(customer_df)

    # Merge L1 + L2
    result = l2.merge(l1, on="客户编号", how="left")
    result["告警数量"] = result["告警数量"].fillna(0).astype(int)
    result["紧急告警"] = result["紧急告警"].fillna("")

    n_alerts = (result["告警数量"] > 0).sum()
    n_strategy = (result["策略建议数量"] > 0).sum()
    print(f"  [行动建议] L1告警: {n_alerts}客户, L2策略: {n_strategy}客户")

    return result
