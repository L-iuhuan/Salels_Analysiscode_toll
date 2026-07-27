"""
规则检测器 — 6个独立异常检测器。

每个检测器输入客户全景表 + Silver数据，返回 [客户编号, 异常类型, 异常等级, 异常详情]。
"""

import pandas as pd
import numpy as np

from config.settings import ANOMALY_DETECTION, INVENTORY_AGING


def _safe_val(row, col, default=np.nan):
    """Safely extract a value from a row (Series or dict)."""
    if hasattr(row, "__getitem__"):
        try:
            v = row[col]
            if pd.isna(v) if isinstance(v, (float, type(np.nan))) else v is None:
                return default
            return v
        except (KeyError, IndexError):
            return default
    return default


# ── A1: 采购中断检测 ─────────────────────────────────────────

def detect_purchase_interruption(customer_df: pd.DataFrame) -> pd.DataFrame:
    """检测采购间隔异常的客户。

    规则: 距上次采购天数 > 常规间隔 × 2.0 且近12月金额 > P50
    """
    results = []
    required = ["距上次采购天数", "常规平均采购间隔"]
    if not all(c in customer_df.columns for c in required):
        return pd.DataFrame(columns=["客户编号", "异常类型", "异常等级", "异常详情"])

    rev_col = "近12月收入" if "近12月收入" in customer_df.columns else None
    median_rev = customer_df[rev_col].median() if rev_col and rev_col in customer_df.columns else 0

    for _, row in customer_df.iterrows():
        last_days = _safe_val(row, "距上次采购天数", 0)
        avg_interval = _safe_val(row, "常规平均采购间隔", 60)
        revenue = _safe_val(row, rev_col, 0) if rev_col else 0

        if avg_interval <= 0:
            continue

        ratio = last_days / avg_interval
        if ratio > 2.0:
            level = "高" if revenue > median_rev else "中"
            results.append({
                "客户编号": row["客户编号"],
                "异常类型": "采购中断",
                "异常等级": level,
                "异常详情": (
                    f"距上次采购{last_days:.0f}天, 为常规间隔({avg_interval:.0f}天)的{ratio:.1f}倍"
                ),
            })

    return pd.DataFrame(results)


# ── A2: 营收断崖检测 ─────────────────────────────────────────

def detect_revenue_cliff(customer_df: pd.DataFrame) -> pd.DataFrame:
    """检测营收断崖式下降的客户。

    规则: 近3月月均收入 / 前12月月均收入 < 0.3, 且非新客户(有12月以上历史)
    """
    results = []
    threshold = ANOMALY_DETECTION.get("revenue_cliff_ratio", 0.3)

    needed = ["近12月收入", "近3月收入"]
    has_rev = "近12月收入" in customer_df.columns
    if not has_rev:
        needed = ["recent12_rev", "recent3_rev"]
    if not all(c in customer_df.columns for c in needed[:1]):
        return pd.DataFrame(columns=["客户编号", "异常类型", "异常等级", "异常详情"])

    for _, row in customer_df.iterrows():
        # Try to find revenue columns
        rev_12m = _safe_val(row, "近12月收入", 0)
        if rev_12m == 0:
            rev_12m = _safe_val(row, "recent12_rev", 0)
        if rev_12m <= 0:
            continue

        rev_3m = _safe_val(row, "近3月收入", 0)
        if rev_3m == 0:
            rev_3m = _safe_val(row, "recent3_rev", 0)

        monthly_12 = rev_12m / 12
        monthly_3 = rev_3m / 3

        if monthly_12 <= 0:
            continue

        ratio = monthly_3 / monthly_12
        if ratio < threshold:
            # Check if it's a new customer (we don't penalize new customers)
            # Try to assess data history
            active_months = _safe_val(row, "活跃月数", 0)
            if active_months > 0 and active_months < 6:
                continue

            level = "高" if ratio < threshold / 2 else "中"
            results.append({
                "客户编号": row["客户编号"],
                "异常类型": "营收断崖",
                "异常等级": level,
                "异常详情": (
                    f"近3月月均{monthly_3:.0f} vs 近12月月均{monthly_12:.0f}, "
                    f"降幅{1 - ratio:.0%}"
                ),
            })

    return pd.DataFrame(results)


# ── A3: 价格异常检测 ─────────────────────────────────────────

def detect_price_anomaly(
    customer_df: pd.DataFrame,
    silver: dict,
) -> pd.DataFrame:
    """检测ASP异常的客户。

    规则: 近3月ASP偏离近12月ASP超过30%
    """
    results = []
    price_dev = ANOMALY_DETECTION.get("price_anomaly_deviation", 0.3)

    # Check if we have ASP columns in customer_df
    asp_change_col = None
    for c in ["ASP变化率", "asp_change", "价格变化率"]:
        if c in customer_df.columns:
            asp_change_col = c
            break

    if asp_change_col is None:
        # Try to compute from silver
        cust_monthly = silver.get("customer_monthly") if silver else None
        if cust_monthly is None or len(cust_monthly) == 0:
            return pd.DataFrame(columns=["客户编号", "异常类型", "异常等级", "异常详情"])

        cm = cust_monthly.copy()
        if not isinstance(cm["_月"].dtype, pd.PeriodDtype):
            cm["_月"] = pd.to_datetime(cm["_月"]).dt.to_period("M")
        latest = cm["_月"].max()

        rev_col = None
        for c in ["rev_pos", "rev_sum", "金额"]:
            if c in cm.columns:
                rev_col = c
                break
        qty_col = None
        for c in ["qty_sum", "数量"]:
            if c in cm.columns:
                qty_col = c
                break
        if rev_col is None or qty_col is None:
            return pd.DataFrame(columns=["客户编号", "异常类型", "异常等级", "异常详情"])

        cm["_asp"] = cm[rev_col] / cm[qty_col].replace(0, float("nan"))

        recent3 = cm[cm["_月"] > (latest - 3)]
        prior12 = cm[(cm["_月"] <= (latest - 3)) & (cm["_月"] > (latest - 15))]

        asp3 = recent3.groupby("客户编号").apply(
            lambda g: g[rev_col].sum() / g[qty_col].sum() if g[qty_col].sum() > 0 else 0,
            include_groups=False,
        )
        asp12 = prior12.groupby("客户编号").apply(
            lambda g: g[rev_col].sum() / g[qty_col].sum() if g[qty_col].sum() > 0 else 0,
            include_groups=False,
        )

        for cid in asp3.index:
            a3 = asp3.get(cid, 0)
            a12 = asp12.get(cid, 0)
            if a12 <= 0 or a3 <= 0:
                continue
            change = (a3 - a12) / a12
            if abs(change) > price_dev:
                direction = "上涨" if change > 0 else "下跌"
                results.append({
                    "客户编号": cid,
                    "异常类型": "价格异常",
                    "异常等级": "中",
                    "异常详情": f"近3月ASP{a3:.2f} vs 前12月ASP{a12:.2f}, {direction}{abs(change):.0%}",
                })
        return pd.DataFrame(results)

    # Use column
    for _, row in customer_df.iterrows():
        change = _safe_val(row, asp_change_col, 0)
        if abs(change) > price_dev:
            direction = "上涨" if change > 0 else "下跌"
            results.append({
                "客户编号": row["客户编号"],
                "异常类型": "价格异常",
                "异常等级": "中",
                "异常详情": f"ASP{direction}{abs(change):.0%}",
            })

    return pd.DataFrame(results)


# ── A4: 集中度风险 ───────────────────────────────────────────

def detect_concentration_risk(customer_df: pd.DataFrame) -> pd.DataFrame:
    """检测品种集中度过高的客户。

    规则: Top1品种金额占比 > 80%, 且该品种处于衰退期
    """
    results = []
    threshold = ANOMALY_DETECTION.get("concentration_risk_threshold", 0.8)

    conc_col = None
    for c in ["Top1品种金额占比", "品种集中度Top1", "top1_share"]:
        if c in customer_df.columns:
            conc_col = c
            break

    life_col = None
    for c in ["客户生命周期", "customer_lifecycle"]:
        if c in customer_df.columns:
            life_col = c
            break

    if conc_col is None:
        return pd.DataFrame(columns=["客户编号", "异常类型", "异常等级", "异常详情"])

    for _, row in customer_df.iterrows():
        conc = _safe_val(row, conc_col, 0)

        if conc > threshold:
            life = _safe_val(row, life_col, "未知") if life_col else "未知"
            level = "高" if life in ("衰退期", "休眠期", "流失期") else "中"
            results.append({
                "客户编号": row["客户编号"],
                "异常类型": "集中度风险",
                "异常等级": level,
                "异常详情": (
                    f"Top1品种占比{conc:.0%}, "
                    f"客户生命周期: {life}"
                ),
            })

    return pd.DataFrame(results)


# ── A5: 库存呆滞检测 ─────────────────────────────────────────

def detect_inventory_stagnant(
    customer_inv_risk: pd.DataFrame,
) -> pd.DataFrame:
    """检测客户采购产品库存呆滞。

    规则: 呆滞金额占比 > 30% 或 超1年金额占比 > 10%
    """
    results = []
    stagnant_ratio = INVENTORY_AGING.get("stagnant_warn_ratio", 0.3)
    dead_ratio = INVENTORY_AGING.get("dead_stock_ratio", 0.1)

    if len(customer_inv_risk) == 0:
        return pd.DataFrame(columns=["客户编号", "异常类型", "异常等级", "异常详情"])

    for _, row in customer_inv_risk.iterrows():
        stagnant_pct = _safe_val(row, "呆滞金额占比", 0)
        dead_pct = _safe_val(row, "超1年金额占比", 0)
        stagnant_count = _safe_val(row, "呆滞品种数", 0)
        dead_count = _safe_val(row, "超1年品种数", 0)

        if stagnant_pct > stagnant_ratio:
            results.append({
                "客户编号": row["客户编号"],
                "异常类型": "库存呆滞",
                "异常等级": "中",
                "异常详情": (
                    f"呆滞品种{stagnant_count}个, 金额占比{stagnant_pct:.1%}; "
                    f"超1年品种{dead_count}个, 金额占比{dead_pct:.1%}"
                ),
            })
        elif dead_pct > dead_ratio:
            results.append({
                "客户编号": row["客户编号"],
                "异常类型": "库存呆滞",
                "异常等级": "低",
                "异常详情": (
                    f"超1年品种{dead_count}个, 金额占比{dead_pct:.1%}"
                ),
            })

    return pd.DataFrame(results)


# ── A6: 长库龄积压(产品维度) ─────────────────────────────────

def detect_dead_stock(
    inv_aging: pd.DataFrame,
    silver: dict,
) -> pd.DataFrame:
    """检测产品级别长库龄积压。

    规则: 库龄_1年以上 > 阈值 且月均销量 < 库存量 × 5% (去化困难)
    返回的是产品维度异常 (用于交叉销售去库存推荐)
    """
    results = []
    slow_ratio = INVENTORY_AGING.get("slow_moving_ratio", 0.05)

    if len(inv_aging) == 0 or "库龄_1年以上" not in inv_aging.columns:
        return pd.DataFrame(columns=["产品品种", "异常类型", "异常等级", "异常详情"])

    # Get monthly sales
    prod_monthly = silver.get("product_monthly") if silver else None
    monthly_sales = pd.Series(dtype=float)
    if prod_monthly is not None and len(prod_monthly) > 0:
        pm = prod_monthly.copy()
        if not isinstance(pm["_月"].dtype, pd.PeriodDtype):
            pm["_月"] = pd.to_datetime(pm["_月"]).dt.to_period("M")
        latest = pm["_月"].max()
        recent3 = pm[pm["_月"] > (latest - 3)]
        qty_col = "qty_sum" if "qty_sum" in pm.columns else "数量"
        monthly_sales = recent3.groupby("产品品种")[qty_col].sum() / 3

    for _, row in inv_aging.iterrows():
        prod = row["产品品种"]
        dead_qty = _safe_val(row, "库龄_1年以上", 0)
        total = _safe_val(row, "库龄_库存总量", 0)

        if dead_qty <= 0 or total <= 0:
            continue

        monthly = monthly_sales.get(prod, 0) if len(monthly_sales) > 0 else 0

        if monthly < dead_qty * slow_ratio:
            ratio_pct = (monthly / dead_qty * 100) if dead_qty > 0 else 100
            results.append({
                "产品品种": prod,
                "异常类型": "长库龄积压",
                "异常等级": "高",
                "异常详情": (
                    f"超1年库存{dead_qty:.0f}(占总库存{dead_qty/total:.0%}), "
                    f"月均销量{monthly:.0f}, 去化速度仅{ratio_pct:.1f}%/月"
                ),
            })

    return pd.DataFrame(results)
