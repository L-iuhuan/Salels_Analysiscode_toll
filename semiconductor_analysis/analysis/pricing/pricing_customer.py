"""
价格分析函数 — ASP趋势、弹性计算、价格偏离度、价格带分布。

可被产品生命周期和客户分析复用。
"""
import numpy as np
import pandas as pd


def _ensure_period_dtype(date_series: pd.Series, latest_month=None):
    """Ensure _月 column is Period dtype (survives CSV round-trip).
    
    When Silver CSV is reloaded, the _月 column becomes string/object.
    This helper standardizes it back to Period[M] type.
    
    Returns:
        tuple: (standardized_series, standardized_latest_month)
    """
    if latest_month is not None and not isinstance(latest_month, pd.Period):
        latest_month = pd.to_datetime(str(latest_month)).to_period('M')
    if not isinstance(date_series.dtype, pd.PeriodDtype):
        date_series = pd.to_datetime(date_series).dt.to_period('M')
    return date_series, latest_month


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
    df = df.sort_values([cust_col, date_col], kind='stable')

    # 剔除前N个月
    first_month = df.groupby(cust_col)[date_col].min().reset_index()
    first_month.columns = [cust_col, "首购月"]
    df = df.merge(first_month, on=cust_col, how="left")
    df = df[df[date_col] >= df["首购月"] + exclude_first_months].copy()

    def _avg_interval(group):
        months = group[date_col].sort_values(kind='stable').unique()
        if len(months) < 2:
            return float("nan")
        intervals = []
        for i in range(1, len(months)):
            t_i = months[i].to_timestamp() if hasattr(months[i], 'to_timestamp') else pd.Period(months[i]).to_timestamp()
            t_prev = months[i-1].to_timestamp() if hasattr(months[i-1], 'to_timestamp') else pd.Period(months[i-1]).to_timestamp()
            delta = t_i - t_prev
            intervals.append(delta.days)
        return np.mean(intervals) if intervals else float("nan")

    interval_data = df.groupby(cust_col, group_keys=False).apply(
        _avg_interval, include_groups=False
    ).reset_index(name="常规平均采购间隔")

    return interval_data

    def _avg_interval(group):
        months = group[date_col].sort_values(kind='stable').unique()
        months = group[date_col].sort_values(kind='stable').unique()
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
    from config.settings import PRICING_RECOMMENDATION
    _days_per_month = PRICING_RECOMMENDATION.get("days_per_month_estimate", 30.4375)
    last_purchase["距上次采购天数"] = last_purchase["距上次采购月数"] * _days_per_month

    result = result.merge(last_purchase[[cust_col, "距上次采购天数"]], on=cust_col, how="left")

    result["采购中断预警"] = (
        (result["距上次采购天数"] > result["常规平均采购间隔"] * multiplier)
        & result["常规平均采购间隔"].notna()
    )

    return result

    from config.settings import PRICING_RECOMMENDATION
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

    def _top_n_ratio(group):
        top_n_rev = group.nlargest(top_n, "rev_sum")["rev_sum"].sum()
        top_n_rev = group.nlargest(top_n, "rev_sum")["rev_sum"].sum()
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

