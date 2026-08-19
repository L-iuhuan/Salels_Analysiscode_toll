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

    批次②.5 车道D（等价向量化）：
      原实现按客户循环，且在循环内重复执行 prod_monthly.groupby(prod_col)[date_col].min()
      （3143 个客户重复计算同一张首次销售表，且每次全表扫描 cxp/customer_monthly）。
      现改为：新品集合一次性预计算，渗透率 = 客户近12月新品去重数 / 全市场新品数（分组聚合），
      增长动量 = 近3月/前3月分组均值比。输出逐值与原版一致（浮点 1e-6 容差内）。
    """
    if latest_month is None:
        latest_month = customer_monthly[date_col].max()
    customer_monthly[date_col], latest_month = _ensure_period_dtype(
        customer_monthly[date_col], latest_month
    )

    cids = customer_monthly[cust_col].unique()

    # ---- 新品渗透（一次性预计算新品集合，避免循环内重复 groupby）----
    prod_first = prod_monthly.groupby(prod_col, observed=True)[date_col].min().reset_index()
    prod_first.columns = [prod_col, "首次销售月"]
    prod_first["是新品种"] = (latest_month - prod_first["首次销售月"]).apply(lambda x: x.n) <= 12
    new_prods = set(prod_first[prod_first["是新品种"]][prod_col])
    n_new = len(new_prods)

    if n_new > 0:
        mask12 = cxp[date_col] > (latest_month - 12)
        c_recent_new = cxp[mask12 & cxp[prod_col].isin(new_prods)]
        pen_cnt = c_recent_new.groupby(cust_col, observed=True)[prod_col].nunique()
        penetration = (pen_cnt / n_new).reindex(cids).fillna(0.0)
    else:
        penetration = pd.Series(0.0, index=pd.Index(cids))

    # ---- 增长动量：近3月 vs 前3月 分组均值（均值 = sum/count，与逐组 Series.mean() 等价）----
    mask_recent3 = customer_monthly[date_col] > (latest_month - 3)
    mask_prior3 = (customer_monthly[date_col] <= (latest_month - 3)) & (
        customer_monthly[date_col] > (latest_month - 6)
    )
    recent_avg = customer_monthly.loc[mask_recent3].groupby(cust_col, observed=True)[rev_col].mean()
    prior_avg = customer_monthly.loc[mask_prior3].groupby(cust_col, observed=True)[rev_col].mean()
    recent_avg = recent_avg.reindex(cids).fillna(0.0)
    prior_avg = prior_avg.reindex(cids).fillna(0.0)
    # 与原 `(recent-prior)/prior if prior>0 else 0` 一致：prior ≤ 0 时不除
    _ra = recent_avg.to_numpy(dtype="float64")
    _pa = prior_avg.to_numpy(dtype="float64")
    _g = np.zeros_like(_ra)
    np.divide(_ra - _pa, _pa, out=_g, where=_pa > 0)
    growth = pd.Series(_g, index=pd.Index(cids))

    return pd.DataFrame({
        cust_col: list(cids),
        "新品渗透机会": penetration.to_numpy(dtype="float64"),
        "增长动量": growth.to_numpy(dtype="float64"),
    })

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

    批次②.5 车道D（等价向量化）：
      原实现按客户循环做全表掩码 + 集合差集。现改为一次性分组聚合：
      品种流失 = 近12月 (客户,品种) 对中不在近3月出现的对（merge 反连接）的收入占比；
      营收跌幅 = 每客户按时间排序后"末3月 vs 其前3月"分组求和。
      输出逐值与原版一致（浮点 1e-6 容差内）。
    """
    if latest_month is None:
        latest_month = customer_monthly[date_col].max()
    customer_monthly[date_col], latest_month = _ensure_period_dtype(
        customer_monthly[date_col], latest_month
    )

    cids = customer_monthly[cust_col].unique()
    mask12 = cxp[date_col] > (latest_month - 12)
    mask3 = cxp[date_col] > (latest_month - 3)

    # ---- 品种流失金额占比 ----
    recent12 = cxp[mask12]
    total_rev_12m = recent12.groupby(cust_col, observed=True)[rev_col].sum().reindex(cids).fillna(0.0)

    pairs12 = recent12[[cust_col, prod_col]].drop_duplicates()
    pairs3 = cxp[mask3][[cust_col, prod_col]].drop_duplicates()
    # 反连接：近12月有、近3月无的 (客户,品种) 对 = 流失品种
    lost = pairs12.merge(pairs3, on=[cust_col, prod_col], how="left", indicator=True)
    lost = lost[lost["_merge"] == "left_only"][[cust_col, prod_col]]
    if len(lost) > 0:
        lost_rev = recent12.merge(lost, on=[cust_col, prod_col], how="inner") \
            .groupby(cust_col, observed=True)[rev_col].sum().reindex(cids).fillna(0.0)
    else:
        lost_rev = pd.Series(0.0, index=pd.Index(cids))
    lost_ratio = np.zeros_like(total_rev_12m.to_numpy(dtype="float64"))
    np.divide(lost_rev.to_numpy(dtype="float64"), total_rev_12m.to_numpy(dtype="float64"),
              out=lost_ratio, where=total_rev_12m.to_numpy() > 0)

    # ---- 近半年营收跌幅：每客户按时间排序，末3月求和 vs 其前3月求和 ----
    cd = customer_monthly.sort_values([cust_col, date_col], kind="stable")
    gcount = cd.groupby(cust_col, observed=True).cumcount()
    gsize = cd.groupby(cust_col, observed=True)[rev_col].transform("size")
    rev_rev = gsize - 1 - gcount  # 0 = 最新月（组内末尾）
    recent3_rev = cd.loc[rev_rev <= 2, rev_col].groupby(
        cd.loc[rev_rev <= 2, cust_col], observed=True).sum().reindex(cids).fillna(0.0)
    prior3_mask = (rev_rev >= 3) & (rev_rev <= 5) & (gsize >= 4)
    prior3_rev = cd.loc[prior3_mask, rev_col].groupby(
        cd.loc[prior3_mask, cust_col], observed=True).sum().reindex(cids).fillna(0.0)
    _p3 = prior3_rev.to_numpy(dtype="float64")
    _r3 = recent3_rev.to_numpy(dtype="float64")
    _d = np.zeros_like(_p3)
    np.divide(_p3 - _r3, _p3, out=_d, where=_p3 > 0)
    decline = _d

    return pd.DataFrame({
        cust_col: list(cids),
        "品种流失金额占比": lost_ratio.astype("float64"),
        "近半年营收跌幅": decline.astype("float64"),
    })

