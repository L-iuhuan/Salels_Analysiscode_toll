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
    customer_monthly[date_col], latest_month = _ensure_period_dtype(
        customer_monthly[date_col], latest_month
    )

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
        c_data = customer_monthly[customer_monthly[cust_col] == cid].sort_values(date_col, kind='stable')
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
    customer_monthly[date_col], latest_month = _ensure_period_dtype(
        customer_monthly[date_col], latest_month
    )

    results = []

    for cid in customer_monthly[cust_col].unique():
        c_data = customer_monthly[customer_monthly[cust_col] == cid].sort_values(date_col, kind='stable')

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

