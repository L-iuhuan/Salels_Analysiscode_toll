"""
价格分析函数 — ASP趋势、弹性计算、价格偏离度、价格带分布。

可被产品生命周期和客户分析复用。
"""

import numpy as np
import pandas as pd


def calc_asp_trend(monthly_prices, thr=None):
    """ASP趋势斜率（近12月均价变化率）。
    
    月均价 = rev_pos / qty_sum，最小二乘求斜率。
    
    参数:
        monthly_prices: 月度均价列表
        thr: 阈值字典（用于min_pts）
    
    返回:
        tuple: (斜率值 比率/月, 是否可靠)
    """
    prices = np.asarray(monthly_prices, dtype=float)
    min_pts = int(thr.get("slope_min_data_points", 3)) if thr else 3
    
    if len(prices) < min_pts:
        return (0.0, False)
    
    x = np.arange(len(prices))
    mask = ~(np.isnan(prices) | (prices <= 0))
    if mask.sum() < min_pts:
        return (0.0, False)
    
    slope = np.polyfit(x[mask], prices[mask], 1)[0]
    avg = np.nanmean(prices[mask])
    if avg > 0:
        return (slope / avg, True)
    return (0.0, False)


def calc_price_elasticity(monthly_prices, monthly_qtys, thr=None):
    """计算价格弹性系数。
    
    稳健方法：百分比变化中位数 + IQR过滤，结果裁剪。
    
    参数:
        monthly_prices: 月度均价列表
        monthly_qtys: 月度销量列表
        thr: 阈值字典
    
    返回:
        tuple: (弹性系数, 敏感度标签)
    """
    if len(monthly_prices) < 3 or len(monthly_qtys) < 3:
        return None, "数据不足"
    
    price_changes = np.diff(monthly_prices) / np.where(monthly_prices[:-1] > 0, monthly_prices[:-1], 1)
    qty_changes = np.diff(monthly_qtys) / np.where(monthly_qtys[:-1] > 0, monthly_qtys[:-1], 1)
    
    valid_mask = (np.abs(price_changes) > 1e-6) & ~np.isnan(qty_changes) & ~np.isnan(price_changes)
    if valid_mask.sum() < 2:
        return None, "数据不足"
    
    elasticities = qty_changes[valid_mask] / price_changes[valid_mask]
    
    q1, q3 = np.percentile(elasticities, [25, 75])
    iqr = q3 - q1
    filtered = elasticities[(elasticities >= q1 - 3*iqr) & (elasticities <= q3 + 3*iqr)]
    elasticity = np.median(filtered) if len(filtered) >= 2 else np.median(elasticities)
    
    elasticity = np.clip(elasticity, -10, 10)
    
    if thr:
        t_high = float(thr.get("elasticity_high", 1.5))
        t_mid = float(thr.get("elasticity_mid", 0.8))
    else:
        t_high, t_mid = 1.5, 0.8
    
    abs_el = abs(elasticity)
    if abs_el > t_high:
        sensitivity = "高敏感"
    elif abs_el > t_mid:
        sensitivity = "中敏感"
    else:
        sensitivity = "低敏感"
    
    return elasticity, sensitivity


def calc_order_frequency_trend(prod_data, latest_month, thr=None):
    """计算订单频次趋势。近3月 vs 前9月。
    
    参数:
        prod_data: 产品月度数据DataFrame（index为月份）
        latest_month: 最新月份（Period对象）
        thr: 阈值字典
    
    返回:
        tuple: (频次变化比率, 标签)
    """
    if prod_data.empty:
        return 0, "无数据"
    
    last3_mask = prod_data.index > (latest_month - 3)
    recent3_orders = prod_data.loc[last3_mask, '_order_count'].sum()
    recent3_avg = recent3_orders / 3
    
    prior9_mask = (prod_data.index <= (latest_month - 3)) & (prod_data.index > (latest_month - 12))
    prior9_orders = prod_data.loc[prior9_mask, '_order_count'].sum()
    prior9_months = prior9_mask.sum()
    prior9_avg = prior9_orders / prior9_months if prior9_months > 0 else 0
    
    if prior9_avg == 0:
        return 0, "无参照"
    
    freq_change = (recent3_avg - prior9_avg) / prior9_avg
    
    if thr:
        t_up = float(thr.get("freq_increase", 0.15))
        t_down = float(thr.get("freq_decrease", -0.10))
    else:
        t_up, t_down = 0.15, -0.10
    
    if freq_change > t_up:
        label = "增强"
    elif freq_change > t_down:
        label = "持平"
    else:
        label = "减弱"
    
    return freq_change, label


# ============================================================
# 价格治理：偏离度、价格带、跨客户离散度（子项1）
# ============================================================

def calc_price_deviation(
    cxp: pd.DataFrame,
    cust_col: str = "客户编号",
    prod_col: str = "产品品种",
    price_col: str = "avg_price",
    min_months: int = 3,
) -> pd.DataFrame:
    """计算每个客户-产品的价格偏离度。

    偏离度 = (客户价 - 全体客户中位价) / 全体客户中位价
    正值 = 买得贵，负值 = 买得便宜。
    只保留有 >= min_months 个月交易记录的组合。

    参数:
        cxp: customer_x_product 表（客户×产品×月份）
        cust_col: 客户编号列名
        prod_col: 产品品种列名
        price_col: 月度均价列名
        min_months: 最低月数要求

    返回:
        DataFrame: 每个客户-产品的价格偏离汇总
    """
    if price_col not in cxp.columns:
        cxp[price_col] = cxp["rev_sum"] / cxp["qty_sum"].replace(0, float("nan"))

    # 每个品种的全体客户中位价
    prod_median = cxp.groupby(prod_col)[price_col].median()
    prod_p25 = cxp.groupby(prod_col)[price_col].quantile(0.25)
    prod_p75 = cxp.groupby(prod_col)[price_col].quantile(0.75)

    # 客户-产品级别汇总
    cp_stats = cxp.groupby([cust_col, prod_col]).agg(
        avg_price=(price_col, "mean"),
        total_rev=("rev_sum", "sum"),
        total_qty=("qty_sum", "sum"),
        active_months=(price_col, "count"),
    ).reset_index()

    # 只保留有足够多交易记录的组合
    cp_stats = cp_stats[cp_stats["active_months"] >= min_months].copy()

    cp_stats["中位价"] = cp_stats[prod_col].map(prod_median)
    cp_stats["P25价"] = cp_stats[prod_col].map(prod_p25)
    cp_stats["P75价"] = cp_stats[prod_col].map(prod_p75)

    cp_stats["价格偏离度"] = (
        (cp_stats["avg_price"] - cp_stats["中位价"]) / cp_stats["中位价"].replace(0, float("nan"))
    )

    return cp_stats


def calc_price_band_distribution(
    cxp: pd.DataFrame,
    cust_col: str = "客户编号",
    prod_col: str = "产品品种",
    price_col: str = "avg_price",
) -> pd.DataFrame:
    """计算每个客户的价格带分布。

    将产品的价格分为低价带(<P25)、中价带(P25-P75)、高价带(>P75)。
    输出每个客户在低价带的采购金额占比。

    参数:
        cxp: customer_x_product 表
        cust_col, prod_col, price_col: 列名

    返回:
        DataFrame: 每个客户的价格带分布指标
    """
    if price_col not in cxp.columns:
        cxp[price_col] = cxp["rev_sum"] / cxp["qty_sum"].replace(0, float("nan"))

    # 计算每个产品的P25和P75分位价
    price_bounds = cxp.groupby(prod_col)[price_col].quantile([0.25, 0.75]).unstack()
    price_bounds.columns = ["P25", "P75"]

    cp = cxp.groupby([cust_col, prod_col]).agg(
        avg_price=(price_col, "mean"),
        total_rev=("rev_sum", "sum"),
    ).reset_index()

    cp = cp.merge(price_bounds, on=prod_col, how="left")

    conditions = [
        cp["avg_price"] <= cp["P25"],
        cp["avg_price"] <= cp["P75"],
    ]
    choices = ["低价带", "中价带"]
    cp["价格带"] = np.select(conditions, choices, default="高价带")

    # 客户维度汇总
    customer_bands = cp.groupby(cust_col).apply(
        lambda g: pd.Series({
            "低价品种收入": g[g["价格带"] == "低价带"]["total_rev"].sum(),
            "中价品种收入": g[g["价格带"] == "中价带"]["total_rev"].sum(),
            "高价品种收入": g[g["价格带"] == "高价带"]["total_rev"].sum(),
            "总收入": g["total_rev"].sum(),
        }),
        include_groups=False,
    ).reset_index()

    customer_bands["低价品种收入占比"] = (
        customer_bands["低价品种收入"] / customer_bands["总收入"].replace(0, float("nan"))
    )
    customer_bands["中价品种收入占比"] = (
        customer_bands["中价品种收入"] / customer_bands["总收入"].replace(0, float("nan"))
    )
    customer_bands["高价品种收入占比"] = (
        customer_bands["高价品种收入"] / customer_bands["总收入"].replace(0, float("nan"))
    )

    return customer_bands


def calc_cross_customer_price_dispersion(
    cxp: pd.DataFrame,
    prod_col: str = "产品品种",
    price_col: str = "avg_price",
) -> pd.DataFrame:
    """计算每个产品在跨客户间的价格离散度。

    用变异系数（CV = 标准差/均值）衡量。
    CV > 0.3 标记为"价格混乱"。

    参数:
        cxp: customer_x_product 表
        prod_col, price_col: 列名

    返回:
        DataFrame: 每个产品的价格离散度指标
    """
    if price_col not in cxp.columns:
        cxp[price_col] = cxp["rev_sum"] / cxp["qty_sum"].replace(0, float("nan"))

    dispersion = cxp.groupby(prod_col)[price_col].agg(
        客户月记录数="count",
        平均价="mean",
        标准差="std",
        中位价="median",
        最低价="min",
        最高价="max",
    ).reset_index()

    # 手动计算分位数
    p25 = cxp.groupby(prod_col)[price_col].quantile(0.25).reset_index()
    p25.columns = [prod_col, "P25"]
    p75 = cxp.groupby(prod_col)[price_col].quantile(0.75).reset_index()
    p75.columns = [prod_col, "P75"]

    dispersion = dispersion.merge(p25, on=prod_col, how="left")
    dispersion = dispersion.merge(p75, on=prod_col, how="left")

    dispersion["变异系数(CV)"] = (
        dispersion["标准差"] / dispersion["平均价"].replace(0, float("nan"))
    )
    dispersion["价格混乱标记"] = dispersion["变异系数(CV)"] > 0.3

    return dispersion


# ============================================================
# 客户采购健康度（子项2）
# ============================================================

def calc_purchase_interval(
    customer_monthly: pd.DataFrame,
    cust_col: str = "客户编号",
    date_col: str = "_月",
    exclude_first_months: int = 6,
) -> pd.DataFrame:
    """计算客户常规平均采购间隔。

    剔除前 exclude_first_months 个月（新品期）。
    至少需要 2 次采购才能计算间隔。

    参数:
        customer_monthly: 客户月度聚合表
        cust_col: 客户编号列名
        date_col: 月份列名（Period对象）
        exclude_first_months: 剔除前N个月

    返回:
        DataFrame: 每客户的采购间隔指标
    """
    df = customer_monthly.copy()
    df = df.sort_values([cust_col, date_col])

    # 剔除前N个月
    first_month = df.groupby(cust_col)[date_col].min().reset_index()
    first_month.columns = [cust_col, "首购月"]
    df = df.merge(first_month, on=cust_col, how="left")
    df = df[df[date_col] >= df["首购月"] + exclude_first_months].copy()

    def _avg_interval(group):
        months = group[date_col].sort_values().unique()
        if len(months) < 2:
            return float("nan")
        intervals = []
        for i in range(1, len(months)):
            delta = months[i].to_timestamp() - months[i-1].to_timestamp()
            intervals.append(delta.days)
        return np.mean(intervals) if intervals else float("nan")

    interval_data = df.groupby(cust_col, group_keys=False).apply(
        _avg_interval, include_groups=False
    ).reset_index(name="常规平均采购间隔")

    return interval_data


def calc_churn_warning(
    customer_monthly: pd.DataFrame,
    intervals: pd.DataFrame,
    cust_col: str = "客户编号",
    date_col: str = "_月",
    multiplier: float = 1.5,
) -> pd.DataFrame:
    """计算采购中断预警。

    最近一次采购距今天数 > 常规间隔 × multiplier 则触发预警。

    参数:
        customer_monthly: 客户月度聚合表
        intervals: calc_purchase_interval 的输出
        cust_col: 客户编号列名
        date_col: 月份列名
        multiplier: 预警倍率（默认1.5，后续根据误报率调整）

    返回:
        intervals 增加预警字段
    """
    result = intervals.copy()

    # 每个客户最近一次采购月
    last_purchase = customer_monthly.groupby(cust_col)[date_col].max().reset_index()
    last_purchase.columns = [cust_col, "最近采购月"]
    # 数据最大月份
    latest_month = customer_monthly[date_col].max()

    last_purchase["距上次采购月数"] = (
        (latest_month - last_purchase["最近采购月"]).apply(lambda x: x.n)
    )
    last_purchase["距上次采购天数"] = last_purchase["距上次采购月数"] * 30.0

    result = result.merge(last_purchase[[cust_col, "距上次采购天数"]], on=cust_col, how="left")

    result["采购中断预警"] = (
        (result["距上次采购天数"] > result["常规平均采购间隔"] * multiplier)
        & result["常规平均采购间隔"].notna()
    )

    return result


def calc_product_concentration(
    cxp: pd.DataFrame,
    cust_col: str = "客户编号",
    prod_col: str = "产品品种",
    top_n: int = 5,
    threshold: float = 0.7,
) -> pd.DataFrame:
    """计算客户的产品集中度。

    Top N 产品采购额占比 > threshold 标记为"强依赖"。

    参数:
        cxp: customer_x_product 表
        cust_col, prod_col: 列名
        top_n: 前N大产品
        threshold: 强依赖阈值

    返回:
        DataFrame: 每客户的集中度指标
    """
    customer_totals = cxp.groupby(cust_col)["rev_sum"].sum().reset_index()
    customer_totals.columns = [cust_col, "总采购额"]

    def _top_n_ratio(group):
        top_n_rev = group.nlargest(top_n, "rev_sum")["rev_sum"].sum()
        total = group["rev_sum"].sum()
        return top_n_rev / total if total > 0 else 0

    top_n_ratios = cxp.groupby(cust_col, group_keys=False).apply(
        _top_n_ratio, include_groups=False
    ).reset_index(name=f"Top{top_n}集中度")

    result = customer_totals.merge(top_n_ratios, on=cust_col, how="left")
    result["强依赖标记"] = result[f"Top{top_n}集中度"] > threshold

    return result


def calc_category_acceptance(
    cxp: pd.DataFrame,
    cust_col: str = "客户编号",
    category_col: str = "产品一级分类",
    dominant_threshold: float = 0.60,
    opportunity_threshold: float = 0.20,
) -> pd.DataFrame:
    """计算客户的品类接受度。

    如果数据中没有 product_line 信息则返回空 DataFrame。

    参数:
        cxp: customer_x_product 表（需含产品线信息）
        cust_col: 客户编号列名
        category_col: 产品线/品类列名
        dominant_threshold: 主导品类占比阈值
        opportunity_threshold: 未打开品类占比阈值

    返回:
        DataFrame: 每客户的品类接受度指标
    """
    if category_col not in cxp.columns:
        return pd.DataFrame({"客户编号": cxp[cust_col].unique(), "品类接受度": "数据缺失"})

    # 每个客户的品类占比
    category_share = cxp.groupby([cust_col, category_col])["rev_sum"].sum().reset_index()
    customer_total = cxp.groupby(cust_col)["rev_sum"].sum().reset_index()
    customer_total.columns = [cust_col, "总金额"]

    category_share = category_share.merge(customer_total, on=cust_col, how="left")
    category_share["占比"] = category_share["rev_sum"] / category_share["总金额"].replace(0, float("nan"))

    # 主导品类（占比最高的品类）
    dominant = category_share.loc[
        category_share.groupby(cust_col)["占比"].idxmax()
    ].reset_index(drop=True)
    dominant = dominant[[cust_col, category_col, "占比"]].rename(
        columns={category_col: "主导品类", "占比": "主导品类占比"}
    )

    # 未打开品类机会（客户占比极低但同类客户普遍采购的品类）
    all_cust_avg = cxp.groupby(category_col)["rev_sum"].sum() / cxp["rev_sum"].sum()
    high_penetration_categories = all_cust_avg[all_cust_avg > 0.10].index.tolist()

    opportunity_rows = []
    for cid in cxp[cust_col].unique():
        c_categories = set(category_share[category_share[cust_col] == cid][category_col])
        for cat in high_penetration_categories:
            if cat not in c_categories:
                opportunity_rows.append({cust_col: cid, "未打开品类机会": cat})

    result = dominant.copy()
    if opportunity_rows:
        opp_df = pd.DataFrame(opportunity_rows)
        opp_summary = opp_df.groupby(cust_col)["未打开品类机会"].apply(list).reset_index()
        result = result.merge(opp_summary, on=cust_col, how="left")

    result["品类机会标签"] = "常规"
    result.loc[result["主导品类占比"] > dominant_threshold, "品类机会标签"] = "优先导入同品类新品"

    if opportunity_rows:
        result.loc[result["未打开品类机会"].notna(), "品类机会标签"] = "观察未打开品类"

    return result


# ============================================================
# SKU生命周期状态机（子项3）
# ============================================================

def calc_sku_lifecycle_stage(
    prod_monthly: pd.DataFrame,
    prod_col: str = "产品品种",
    date_col: str = "_月",
    rev_col: str = "rev_sum",
    qty_col: str = "qty_sum",
    growth_threshold: float = 0.15,
    decline_threshold: float = -0.10,
    min_months: int = 6,
) -> pd.DataFrame:
    """计算每个SKU的生命周期阶段状态机。

    阶段定义：
      - 导入试销：历史总销量 ≤ min_qty（从prod_monthly看，在售时间<3月 + 低量）
      - 成长爬坡：近3月收入环比增速 > growth_threshold
      - 平稳成熟：近3月波动在±growth_threshold 内，持续≥min_months
      - 隐性衰退：收入连续3月下滑但总量仍可观
      - 衰退出清：收入连续3月下滑且已低于峰值30%
      - 退市清库：停售≥min_months后仍有微量出库

    参数:
        prod_monthly: 产品月度表
        prod_col: 产品品种列名
        date_col: 月份列名（Period对象）
        rev_col: 收入列名
        qty_col: 数量列名
        growth_threshold: 增速阈值
        decline_threshold: 衰退阈值
        min_months: 最低持续月数

    返回:
        DataFrame: 每个SKU的最新生命周期阶段
    """
    latest_month = prod_monthly[date_col].max()

    def _stage_for_sku(group):
        g = group.sort_values(date_col)
        g = g[(g[rev_col] > 0) | (g[qty_col] > 0)]
        if len(g) < 2:
            return "导入试销"

        in_months = len(g)
        total_rev = g[rev_col].sum()
        total_qty = g[qty_col].sum()

        # 最近3月和之前3月
        recent3 = g[g[date_col] > (latest_month - 3)]
        prior3 = g[(g[date_col] <= (latest_month - 3)) & (g[date_col] > (latest_month - 6))]

        recent3_rev_avg = recent3[rev_col].mean() if len(recent3) > 0 else 0
        prior3_rev_avg = prior3[rev_col].mean() if len(prior3) > 0 else 0

        peak_rev = g[rev_col].max()
        last3_rev = recent3[rev_col].sum()
        prior3_rev = prior3[rev_col].sum()

        # 连续下滑判断
        rev_vals = g.tail(6)[rev_col].values
        consecutive_decline = all(rev_vals[i] > rev_vals[i+1] for i in range(len(rev_vals)-1)) if len(rev_vals) >= 3 else False
        half_decline = sum(1 for i in range(len(rev_vals)-1) if rev_vals[i] > rev_vals[i+1]) >= 3 if len(rev_vals) >= 3 else False

        # 规则判定
        if in_months <= 3 and total_qty < 1000:
            return "导入试销"

        if half_decline and last3_rev < peak_rev * 0.30 and total_rev > 0:
            return "衰退出清"

        if half_decline and last3_rev > 0 and prior3_rev > 0 and last3_rev < prior3_rev * 0.70:
            return "隐性衰退"

        if prior3_rev_avg > 0 and (recent3_rev_avg - prior3_rev_avg) / prior3_rev_avg > growth_threshold:
            return "成长爬坡"

        if in_months >= min_months:
            return "平稳成熟"

        return "导入试销"

    stages = prod_monthly.groupby(prod_col, group_keys=False).apply(
        _stage_for_sku, include_groups=False
    ).reset_index(name="SKU生命周期阶段")

    return stages


# ============================================================
# 客户生命周期阶段（子项4）
# ============================================================

def calc_customer_lifecycle_stage(
    customer_monthly: pd.DataFrame,
    cust_col: str = "客户编号",
    date_col: str = "_月",
    rev_col: str = "rev_sum",
    latest_month=None,
    thr: dict = None,
) -> pd.DataFrame:
    """计算每个客户的生命周期阶段。

    阶段定义：
      - 导入期：最近12月才有首次采购，且月金额≥月均×倍数
      - 爬坡期：近N月环比≥阈值（N和阈值可配置），持续6月以上
      - 成熟期：月收入在均值±1.5σ内稳定波动
      - 衰退期：连续3月低于近12月均线15%
      - 休眠期：超过180天无采购
      - 流失期：超过360天无采购

    参数:
        customer_monthly: 客户月度表
        cust_col: 客户编号列名
        date_col: 月份列名
        rev_col: 收入列名
        latest_month: 最新月份
        thr: 配置字典，可包含"爬坡期环比阈值"(默认0.15)、"爬坡期_环比增长前N月均值"(默认3)

    返回:
        DataFrame: 每客户的生命周期阶段
    """
    if latest_month is None:
        latest_month = customer_monthly[date_col].max()

    # 爬坡期配置
    _ramp_threshold = float((thr or {}).get("爬坡期环比阈值", 0.15))
    _ramp_window = int((thr or {}).get("爬坡期_环比增长前N月均值", 3))

    def _stage_for_cust(group):
        g = group.sort_values(date_col)
        total_months = len(g)
        recent12 = g[g[date_col] > (latest_month - 12)]
        last_month = g[date_col].max()
        months_since_last = (latest_month - last_month).n if pd.notna(last_month) else 999
        avg_rev = recent12[rev_col].mean()

        # 连续3月是否低于均线15%
        last3 = g.tail(3)
        if len(last3) == 3 and avg_rev > 0:
            all_below = all(r < avg_rev * 0.85 for r in last3[rev_col].values)
        else:
            all_below = False

        if months_since_last >= 12:
            return "流失期"
        if months_since_last >= 6:
            return "休眠期"

        first_purchase = g[date_col].min()
        if (latest_month - first_purchase).n <= 12:
            return "导入期"

        # 爬坡期判断：近N月环比 ≥ 阈值（N和阈值均可配置）
        recent_n = g[g[date_col] > (latest_month - _ramp_window)]
        prior_n = g[(g[date_col] <= (latest_month - _ramp_window)) & (g[date_col] > (latest_month - 2 * _ramp_window))]
        recent_n_avg = recent_n[rev_col].mean() if len(recent_n) > 0 else 0
        prior_n_avg = prior_n[rev_col].mean() if len(prior_n) > 0 else 0

        if prior_n_avg > 0 and (recent_n_avg - prior_n_avg) / prior_n_avg > _ramp_threshold:
            return "爬坡期"

        if all_below:
            return "衰退期"

        return "成熟期"

    stages = customer_monthly.groupby(cust_col, group_keys=False).apply(
        _stage_for_cust, include_groups=False
    ).reset_index(name="客户生命周期")

    return stages


# ============================================================
# 新品Cohort追踪（子项5）
# ============================================================

def calc_new_product_cohort(
    prod_monthly: pd.DataFrame,
    cxp: pd.DataFrame,
    cust_col: str = "客户编号",
    prod_col: str = "产品品种",
    date_col: str = "_月",
    max_months: int = 12,
    window_months: int = 6,
) -> pd.DataFrame:
    """计算新产品的Cohort渗透率和客户参与度。

    新品定义（按优先级）：
      1. 如果 prod_monthly 包含"新品标记"列（来自ERP的"是否新品"字段），
         则产品最新记录中标记为"是"即为新品。
      2. 否则回退为自动判断：首次销售距今 ≤ max_months 个月。

    追踪Cohort从上市到当前月的新品在客户中的渗透情况。

    参数:
        prod_monthly: 产品月度表（可选包含"新品标记"列）
        cxp: customer_x_product 表
        cust_col, prod_col, date_col: 列名
        max_months: 新品判定月数阈值（仅回退模式使用）
        window_months: Cohort追踪窗口月数

    返回:
        DataFrame: 每个客户的新品采购情况
    """
    latest_month = prod_monthly[date_col].max()

    # ---- 新品判定（优先级：ERP标记 > 自动计算） ----
    if "新品标记" in prod_monthly.columns:
        # 使用ERP标记：近12月内如有任一行标记为"是"即为新品
        # （与 profiling.py 的 df_recent 窗口一致）
        _recent_mask = prod_monthly[date_col] > (latest_month - max_months)
        _prod_new = prod_monthly[_recent_mask].groupby(prod_col)["新品标记"].apply(
            lambda s: (s == "是").any()
        )
        new_products = _prod_new[_prod_new].index.tolist()
    else:
        # 回退模式：根据首次销售月自动判断
        prod_first_sale = prod_monthly.groupby(prod_col)[date_col].min().reset_index()
        prod_first_sale.columns = [prod_col, "首次销售月"]
        prod_first_sale["新品标记_auto"] = (latest_month - prod_first_sale["首次销售月"]).apply(lambda x: x.n) <= max_months
        new_products = prod_first_sale[prod_first_sale["新品标记_auto"]][prod_col].unique()

    if len(new_products) == 0:
        return pd.DataFrame({"客户编号": cxp[cust_col].unique(), "新品渗透率": 0.0, "新品采购占比": 0.0})

    # 每个客户是否采购了新品 + 新品采购金额占比
    cxp_new = cxp[cxp[prod_col].isin(new_products)]

    customer_new = cxp_new.groupby(cust_col).agg(
        新品采购额=("rev_sum", "sum"),
        新品品种数=(prod_col, "nunique"),
    ).reset_index()

    customer_total = cxp.groupby(cust_col).agg(
        总采购额=("rev_sum", "sum"),
    ).reset_index()

    result = customer_total.merge(customer_new, on=cust_col, how="left")
    result["新品采购额"] = result["新品采购额"].fillna(0)
    result["新品品种数"] = result["新品品种数"].fillna(0)
    result["新品采购占比"] = result["新品采购额"] / result["总采购额"].replace(0, float("nan"))
    result["是否采购新品"] = result["新品采购额"] > 0

    # 全市场新品总渗透率
    total_customers = cxp[cust_col].nunique()
    new_buyers = result[result["是否采购新品"]][cust_col].nunique()
    result["新品渗透率"] = new_buyers / total_customers if total_customers > 0 else 0

    return result


# ============================================================
# 客户机会/风险信号（子项6）
# ============================================================

def calc_opportunity_signals(
    customer_monthly: pd.DataFrame,
    prod_monthly: pd.DataFrame,
    cxp: pd.DataFrame,
    cust_col: str = "客户编号",
    prod_col: str = "产品品种",
    date_col: str = "_月",
    rev_col: str = "rev_sum",
    margin_col: str = "margin",
    latest_month=None,
) -> pd.DataFrame:
    """计算客户机会信号：新品渗透、品类扩展、渠道下沉、竞品切换。

    参数:
        customer_monthly: 客户月度表
        prod_monthly: 产品月度表
        cxp: customer_x_product 表
        cust_col, prod_col, date_col: 列名
        latest_month: 最新月份

    返回:
        DataFrame: 每个客户的机会信号汇总
    """
    if latest_month is None:
        latest_month = customer_monthly[date_col].max()

    results = []

    for cid in customer_monthly[cust_col].unique():
        c_recent = cxp[(cxp[cust_col] == cid) & (cxp[date_col] > (latest_month - 12))]

        # 新品渗透
        prod_first = prod_monthly.groupby(prod_col)[date_col].min().reset_index()
        prod_first.columns = [prod_col, "首次销售月"]
        prod_first["是新品种"] = (latest_month - prod_first["首次销售月"]).apply(lambda x: x.n) <= 12
        new_prods = set(prod_first[prod_first["是新品种"]][prod_col])
        c_prods = set(c_recent[prod_col].unique())
        new_penetration = len(new_prods & c_prods) / len(new_prods) if len(new_prods) > 0 else 0

        # 品类扩展机会
        c_data = customer_monthly[customer_monthly[cust_col] == cid].sort_values(date_col)
        recent3 = c_data[c_data[date_col] > (latest_month - 3)]
        prior3 = c_data[(c_data[date_col] <= (latest_month - 3)) & (c_data[date_col] > (latest_month - 6))]
        recent_avg = recent3[rev_col].mean() if len(recent3) > 0 else 0
        prior_avg = prior3[rev_col].mean() if len(prior3) > 0 else 0
        growth_rate = (recent_avg - prior_avg) / prior_avg if prior_avg > 0 else 0

        results.append({
            cust_col: cid,
            "新品渗透机会": new_penetration,
            "增长动量": growth_rate,
        })

    return pd.DataFrame(results)


def calc_risk_signals(
    customer_monthly: pd.DataFrame,
    cxp: pd.DataFrame,
    cust_col: str = "客户编号",
    prod_col: str = "产品品种",
    date_col: str = "_月",
    rev_col: str = "rev_sum",
    latest_month=None,
) -> pd.DataFrame:
    """计算客户风险信号：营收下滑、品种流失、毛利恶化、采购中断。

    参数类似 calc_opportunity_signals。

    返回:
        DataFrame: 每个客户的风险信号汇总
    """
    if latest_month is None:
        latest_month = customer_monthly[date_col].max()

    results = []

    for cid in customer_monthly[cust_col].unique():
        c_data = customer_monthly[customer_monthly[cust_col] == cid].sort_values(date_col)

        # 品种流失：过去12个月曾采购但最近3月不再采购的品种
        recent12 = cxp[(cxp[cust_col] == cid) & (cxp[date_col] > (latest_month - 12))]
        recent3 = cxp[(cxp[cust_col] == cid) & (cxp[date_col] > (latest_month - 3))]
        past_prods = set(recent12[prod_col].unique())
        current_prods = set(recent3[prod_col].unique())
        lost_prods = past_prods - current_prods
        lost_rev_12m = recent12[recent12[prod_col].isin(lost_prods)]["rev_sum"].sum()
        total_rev_12m = recent12["rev_sum"].sum()
        lost_ratio = lost_rev_12m / total_rev_12m if total_rev_12m > 0 else 0

        # 营收下滑幅度
        recent_months = c_data.tail(6)
        if len(recent_months) >= 3:
            recent3_rev = recent_months.tail(3)[rev_col].sum()
            prior3_rev = recent_months.head(len(recent_months) - 3)[rev_col].sum() if len(recent_months) > 3 else 0
            decline = (prior3_rev - recent3_rev) / prior3_rev if prior3_rev > 0 else 0
        else:
            decline = 0

        results.append({
            cust_col: cid,
            "品种流失金额占比": lost_ratio,
            "近半年营收跌幅": decline,
        })

    return pd.DataFrame(results)


# ============================================================
# 定价建议：提价空间（子项7）
# ============================================================

def calc_markup_opportunity(
    cxp: pd.DataFrame,
    prod_col: str = "产品品种",
    cust_col: str = "客户编号",
    price_col: str = "avg_price",
    min_active_months: int = 6,
    price_ratio_threshold: float = 0.90,
) -> pd.DataFrame:
    """计算提价空间。

    条件：
      1. 客户当前实际价 ≤ 产品中位价 × price_ratio_threshold（买得便宜）
      2. 客户连续采购 ≥ min_active_months（非临时客户）
      3. 提品种非强依赖（客户采购量 ≤ 总销量 × 30%，否则反噬）

    参数:
        cxp: customer_x_product 表
        prod_col, cust_col, price_col: 列名
        min_active_months: 最低持续交易月数
        price_ratio_threshold: 价格比值阈值

    返回:
        DataFrame: 每个客户-产品的提价机会
    """
    if price_col not in cxp.columns:
        cxp[price_col] = cxp["rev_sum"] / cxp["qty_sum"].replace(0, float("nan"))

    # 每个产品的全市场中位价
    prod_median = cxp.groupby(prod_col)[price_col].median()

    # 每个产品的总销量
    prod_total_qty = cxp.groupby(prod_col)["qty_sum"].sum()

    # 客户-产品级别统计
    cp = cxp.groupby([cust_col, prod_col]).agg(
        avg_price=(price_col, "mean"),
        total_rev=("rev_sum", "sum"),
        total_qty=("qty_sum", "sum"),
        active_months=(price_col, "count"),
    ).reset_index()

    cp["中位价"] = cp[prod_col].map(prod_median)
    cp["产品总销量"] = cp[prod_col].map(prod_total_qty)
    cp["客户销量占比"] = cp["total_qty"] / cp["产品总销量"].replace(0, float("nan"))

    # 条件筛选
    cp["提价空间"] = cp["中位价"] - cp["avg_price"]
    cp["提价比率"] = cp["提价空间"] / cp["中位价"].replace(0, float("nan"))
    cp["可提价标记"] = (
        (cp["avg_price"] < cp["中位价"] * price_ratio_threshold)
        & (cp["active_months"] >= min_active_months)
        & (cp["客户销量占比"].fillna(0) <= 0.30)
    )

    return cp


def calc_markdown_recommendation(
    cxp: pd.DataFrame,
    prod_col: str = "产品品种",
    cust_col: str = "客户编号",
    price_col: str = "avg_price",
    elasticity: float = -1.0,
    discount_rates: list = None,
) -> pd.DataFrame:
    """计算降价策略建议。

    对高频低价品种，给出不同降价幅度下的销量增量预测和盈亏评估。

    参数:
        cxp: customer_x_product 表
        prod_col, cust_col, price_col: 列名
        elasticity: 固定弹性系数（默认-1.0）
        discount_rates: 降价幅度试算列表

    返回:
        DataFrame: 每个品种的降价策略评估
    """
    if discount_rates is None:
        discount_rates = [0.03, 0.05, 0.08, 0.10]

    if price_col not in cxp.columns:
        cxp[price_col] = cxp["rev_sum"] / cxp["qty_sum"].replace(0, float("nan"))

    # 品种级别聚合
    prod_stats = cxp.groupby(prod_col).agg(
        近12月销量=("qty_sum", "sum"),
        近12月收入=("rev_sum", "sum"),
        平均单价=(price_col, "mean"),
    ).reset_index()

    # 对每个降价幅度计算效果
    records = []
    for _, row in prod_stats.iterrows():
        prod = row[prod_col]
        current_price = row["平均单价"]
        base_qty = row["近12月销量"]
        base_rev = row["近12月收入"]

        for rate in discount_rates:
            new_price = current_price * (1 - rate)
            # 弹性公式：ΔQ/Q = ε × ΔP/P
            qty_increase = base_qty * abs(elasticity) * rate
            new_qty = base_qty + qty_increase
            new_rev = new_price * new_qty
            rev_change = new_rev - base_rev

            records.append({
                prod_col: prod,
                "降价幅度": rate,
                "原价": current_price,
                "新价": new_price,
                "预测增量销量": qty_increase,
                "预测新营收": new_rev,
                "营收变化": rev_change,
                "盈亏判断": "可试" if rev_change > 0 else "谨慎",
            })

    return pd.DataFrame(records)


# ============================================================
# 行动建议生成（子项11）
# ============================================================

def generate_action_suggestions(
    customer_profile: pd.DataFrame,
    markup_df: pd.DataFrame = None,
    cust_col: str = "客户编号",
) -> pd.DataFrame:
    """为客户生成可执行行动建议（标签）。

    基于客户画像和定价建议，自动产出行动建议。
    每个客户可能有多条建议。

    参数:
        customer_profile: 客户全景表
        markup_df: 提价空间表（可选）
        cust_col: 客户编号列名

    返回:
        DataFrame: 每客户的行动建议
    """
    suggestions = []

    for _, row in customer_profile.iterrows():
        cid = row[cust_col]
        user_suggestions = []

        # 1. 新品导入机会
        np_col = "新品采购占比"
        if np_col in row and pd.notna(row[np_col]):
            if row[np_col] < 0.05 and row.get("在采品种数", 0) > 0:
                user_suggestions.append("建议导入新品/替代料验证")
            elif row[np_col] > 0.20:
                user_suggestions.append("新品渗透良好，可扩大推广")

        # 2. 流失预警
        churn_col = "采购中断预警"
        if churn_col in row and row[churn_col]:
            user_suggestions.append("客户采购间隔异常，建议回访确认需求变化")

        # 3. 风险品种
        conc_col = "强依赖标记"
        if conc_col in row and row[conc_col]:
            user_suggestions.append("品种集中度过高，建议引导多品种采购降低风险")

        # 4. 衰退信号
        lc_col = "客户生命周期"
        if lc_col in row and row[lc_col] in ("衰退期", "休眠期", "流失期"):
            user_suggestions.append(f"客户处于{row[lc_col]}，建议启动挽回计划或控制信用额度")

        # 5. 提价机会
        sku_loss_col = "品种流失金额占比"
        if sku_loss_col in row and pd.notna(row.get(sku_loss_col)):
            if row[sku_loss_col] > 0.15:
                user_suggestions.append("关键品种流失≥15%，需了解客户替代来源")

        # 6. 价格谈判提价
        price_dev_col = "低价品种收入占比"
        if price_dev_col in row and pd.notna(row.get(price_dev_col)):
            if row[price_dev_col] > 0.50:
                user_suggestions.append("高比例采购低价品种，有提价空间")

        # 7. 生命周期行动
        sku_stage_col = "主要SKU阶段"
        if sku_stage_col in row and row.get(sku_stage_col) == "衰退出清":
            user_suggestions.append("客户在用退市品种，需引导迁移替代型号")

        if user_suggestions:
            suggestions.append({
                cust_col: cid,
                "行动建议数": len(user_suggestions),
                "行动建议": "; ".join(user_suggestions),
            })
        else:
            suggestions.append({
                cust_col: cid,
                "行动建议数": 0,
                "行动建议": "暂无明显行动项",
            })

    return pd.DataFrame(suggestions)
