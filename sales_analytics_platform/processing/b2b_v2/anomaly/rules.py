"""
规则检测器 — 6个独立异常检测器。

每个检测器输入客户全景表 + Silver数据，返回 [客户编号, 异常类型, 异常等级, 异常详情]。
"""

import pandas as pd
import numpy as np

from config.settings import ANOMALY_DETECTION, INVENTORY_AGING


# ── A1: 采购中断检测 ─────────────────────────────────────────

def detect_purchase_interruption(customer_df: pd.DataFrame) -> pd.DataFrame:
    """检测采购间隔异常的客户。

    规则: 距上次采购天数 > 常规间隔 × 2.0 且近12月金额 > P50
    批次②车道B：原 iterrows 循环改为向量化，输出逐值等价。
    """
    required = ["距上次采购天数", "常规平均采购间隔"]
    if not all(c in customer_df.columns for c in required):
        return pd.DataFrame(columns=["客户编号", "异常类型", "异常等级", "异常详情"])

    rev_col = "近12月收入" if "近12月收入" in customer_df.columns else None
    median_rev = customer_df[rev_col].median() if rev_col and rev_col in customer_df.columns else 0

    d = customer_df
    last_days = d["距上次采购天数"].fillna(0)
    avg_interval = d["常规平均采购间隔"].fillna(60)
    revenue = d[rev_col].fillna(0) if rev_col else 0

    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = last_days / avg_interval
    valid = (avg_interval > 0) & (ratio > 2.0)
    sel = d.loc[valid]
    if len(sel) == 0:
        return pd.DataFrame()

    level = np.where(revenue[valid] > median_rev, "高", "中")
    detail = pd.Series(
        [f"距上次采购{ld:.0f}天, 为常规间隔({ai:.0f}天)的{r:.1f}倍"
         for ld, ai, r in zip(last_days[valid], avg_interval[valid], ratio[valid])],
        index=sel.index,
    )
    return pd.DataFrame({
        "客户编号": sel["客户编号"].values,
        "异常类型": ["采购中断"] * len(sel),
        "异常等级": level,
        "异常详情": detail,
    })


# ── A2: 营收断崖检测 ─────────────────────────────────────────

def detect_revenue_cliff(customer_df: pd.DataFrame) -> pd.DataFrame:
    """检测营收断崖式下降的客户。

    规则: 近12月收入增长率 < -50% 且 连续下滑月数 >= 2
    使用收入增长率字段，避免依赖不存在的近3月收入字段。
    批次②车道B：原 iterrows 循环改为向量化，输出逐值等价。
    """
    # 检查必需列
    has_growth = "收入增长率" in customer_df.columns
    has_decline = "连续下滑月数" in customer_df.columns
    if not has_growth:
        return pd.DataFrame(columns=["客户编号", "异常类型", "异常等级", "异常详情"])

    d = customer_df
    growth = d["收入增长率"].fillna(0)
    decline_months = d["连续下滑月数"].fillna(0) if has_decline else 0
    rev_12m = d["近12月收入"].fillna(0) if "近12月收入" in d.columns else 0

    # 近12月收入必须>0（排除休眠客户）；增长率 <= -50% 且连续下滑 >= 2个月
    valid = (rev_12m > 0) & (growth <= -0.5) & (decline_months >= 2)
    sel = d.loc[valid]
    if len(sel) == 0:
        return pd.DataFrame()

    gv = growth[valid]
    rv = rev_12m[valid]
    dm = decline_months[valid]
    level = np.where(gv <= -0.8, "高", "中")
    detail = pd.Series(
        [f"近12月收入{rv_i:,.0f}, 增长率{gv_i:.0%}, 连续下滑{int(dm_i)}个月"
         for rv_i, gv_i, dm_i in zip(rv, gv, dm)],
        index=sel.index,
    )
    return pd.DataFrame({
        "客户编号": sel["客户编号"].values,
        "异常类型": ["营收断崖"] * len(sel),
        "异常等级": level,
        "异常详情": detail,
    })


# ── A3: 价格异常检测 ─────────────────────────────────────────

def detect_price_anomaly(
    customer_df: pd.DataFrame,
    silver: dict,
) -> pd.DataFrame:
    """检测ASP异常的客户。

    规则: 近3月ASP偏离近12月ASP超过30%
    批次②车道B：iterrows 循环与 silver 路径的 groupby.apply 均改为向量化，输出逐值等价。
    """
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

        recent3 = cm[cm["_月"] > (latest - 3)]
        prior12 = cm[(cm["_月"] <= (latest - 3)) & (cm["_月"] > (latest - 15))]

        # 向量化 ASP：近3月 vs 前12月（等价于原 groupby.apply 逐组除法）
        def _asp(df_part):
            g = df_part.groupby("客户编号", sort=False)[[rev_col, qty_col]].sum()
            return (g[rev_col] / g[qty_col]).where(g[qty_col] > 0, 0.0)

        asp3 = _asp(recent3).rename("a3")
        asp12 = _asp(prior12).rename("a12")
        both = pd.concat([asp3, asp12], axis=1, join="outer").fillna(0)

        change = (both["a3"] - both["a12"]) / both["a12"]
        valid = (both["a12"] > 0) & (both["a3"] > 0) & (change.abs() > price_dev)
        sel = both.loc[valid]
        if len(sel) == 0:
            return pd.DataFrame()

        direction = np.where(sel["a3"] > sel["a12"], "上涨", "下跌")
        detail = pd.Series(
            [f"近3月ASP{a3:.2f} vs 前12月ASP{a12:.2f}, {d}{abs(c):.0%}"
             for a3, a12, d, c in zip(sel["a3"], sel["a12"], direction, change.loc[sel.index])],
            index=sel.index,
        )
        return pd.DataFrame({
            "客户编号": sel.index,
            "异常类型": ["价格异常"] * len(sel),
            "异常等级": ["中"] * len(sel),
            "异常详情": detail,
        })

    # Use column
    d = customer_df
    change = d[asp_change_col].fillna(0)
    valid = change.abs() > price_dev
    sel = d.loc[valid]
    if len(sel) == 0:
        return pd.DataFrame()
    direction = np.where(change[valid] > 0, "上涨", "下跌")
    detail = pd.Series(
        [f"ASP{d}{abs(c):.0%}" for d, c in zip(direction, change[valid])],
        index=sel.index,
    )
    return pd.DataFrame({
        "客户编号": sel["客户编号"].values,
        "异常类型": ["价格异常"] * len(sel),
        "异常等级": ["中"] * len(sel),
        "异常详情": detail,
    })


# ── A4: 集中度风险 ───────────────────────────────────────────

def detect_concentration_risk(customer_df: pd.DataFrame) -> pd.DataFrame:
    """检测品种集中度过高的客户。

    规则: Top1品种金额占比 > 80%, 且该品种处于衰退期
    批次②车道B：原 iterrows 循环改为向量化，输出逐值等价。
    """
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

    d = customer_df
    conc = d[conc_col].fillna(0)
    valid = conc > threshold
    sel = d.loc[valid]
    if len(sel) == 0:
        return pd.DataFrame()

    life = sel[life_col].fillna("未知") if life_col else pd.Series("未知", index=sel.index)
    level = np.where(life.isin(["衰退期", "休眠期", "流失期"]), "高", "中")
    detail = pd.Series(
        [f"Top1品种占比{c:.0%}, 客户生命周期: {l}" for c, l in zip(conc[valid], life)],
        index=sel.index,
    )
    return pd.DataFrame({
        "客户编号": sel["客户编号"].values,
        "异常类型": ["集中度风险"] * len(sel),
        "异常等级": level,
        "异常详情": detail,
    })


# ── A5: 库存呆滞检测 ─────────────────────────────────────────

def detect_inventory_stagnant(
    customer_inv_risk: pd.DataFrame,
) -> pd.DataFrame:
    """检测客户采购产品库存呆滞。

    规则: 呆滞金额占比 > 30% 或 超1年金额占比 > 10%
    批次②车道B：原 iterrows 循环改为向量化，输出逐值等价。
    """
    stagnant_ratio = INVENTORY_AGING.get("stagnant_warn_ratio", 0.3)
    dead_ratio = INVENTORY_AGING.get("dead_stock_ratio", 0.1)

    if len(customer_inv_risk) == 0:
        return pd.DataFrame(columns=["客户编号", "异常类型", "异常等级", "异常详情"])

    d = customer_inv_risk
    stagnant_pct = d["呆滞金额占比"].fillna(0)
    dead_pct = d["超1年金额占比"].fillna(0)
    stagnant_count = d["呆滞品种数"].fillna(0)
    dead_count = d["超1年品种数"].fillna(0)

    mask_stag = stagnant_pct > stagnant_ratio
    mask_dead = (dead_pct > dead_ratio) & ~mask_stag  # 原 elif：呆滞命中时不再记低等级

    rows = []
    if mask_stag.any():
        sc = stagnant_count[mask_stag]
        dc = dead_count[mask_stag]
        sp = stagnant_pct[mask_stag]
        dp = dead_pct[mask_stag]
        detail = pd.Series(
            [f"呆滞品种{sc_i:.0f}个, 金额占比{sp_i:.1%}; 超1年品种{dc_i:.0f}个, 金额占比{dp_i:.1%}"
             for sc_i, dc_i, sp_i, dp_i in zip(sc, dc, sp, dp)],
            index=d.index[mask_stag],
        )
        rows.append(pd.DataFrame({
            "客户编号": d.loc[mask_stag, "客户编号"].values,
            "异常类型": ["库存呆滞"] * int(mask_stag.sum()),
            "异常等级": ["中"] * int(mask_stag.sum()),
            "异常详情": detail,
        }))
    if mask_dead.any():
        dc2 = dead_count[mask_dead]
        dp2 = dead_pct[mask_dead]
        detail2 = pd.Series(
            [f"超1年品种{dc_i:.0f}个, 金额占比{dp_i:.1%}" for dc_i, dp_i in zip(dc2, dp2)],
            index=d.index[mask_dead],
        )
        rows.append(pd.DataFrame({
            "客户编号": d.loc[mask_dead, "客户编号"].values,
            "异常类型": ["库存呆滞"] * int(mask_dead.sum()),
            "异常等级": ["低"] * int(mask_dead.sum()),
            "异常详情": detail2,
        }))
    if not rows:
        return pd.DataFrame()
    return pd.concat(rows, ignore_index=True)


# ── A6: 长库龄积压(产品维度) ─────────────────────────────────

def detect_dead_stock(
    inv_aging: pd.DataFrame,
    silver: dict,
) -> pd.DataFrame:
    """检测产品级别长库龄积压。

    规则: 库龄_1年以上 > 阈值 且月均销量 < 库存量 × 5% (去化困难)
    返回的是产品维度异常 (用于交叉销售去库存推荐)
    批次②车道B：原 iterrows 循环改为向量化，输出逐值等价。
    """
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
        monthly_sales = recent3.groupby("产品品种", sort=False)[qty_col].sum() / 3

    d = inv_aging
    dead_qty = d["库龄_1年以上"].fillna(0)
    total = d["库龄_库存总量"].fillna(0)
    monthly = d["产品品种"].map(monthly_sales).fillna(0) if len(monthly_sales) > 0 else 0

    valid = (dead_qty > 0) & (total > 0) & (monthly < dead_qty * slow_ratio)
    sel = d.loc[valid]
    if len(sel) == 0:
        return pd.DataFrame()

    dq = dead_qty[valid]
    tt = total[valid]
    mm = monthly[valid]
    ratio_pct = mm / dq * 100
    detail = pd.Series(
        [f"超1年库存{dq_i:.0f}(占总库存{tt_i:.0%}), 月均销量{mm_i:.0f}, 去化速度仅{rp_i:.1f}%/月"
         for dq_i, tt_i, mm_i, rp_i in zip(dq, dq / tt, mm, ratio_pct)],
        index=sel.index,
    )
    return pd.DataFrame({
        "产品品种": sel["产品品种"].values,
        "异常类型": ["长库龄积压"] * len(sel),
        "异常等级": ["高"] * len(sel),
        "异常详情": detail,
    })
