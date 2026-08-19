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

    # 客户维度汇总（向量化：按 [客户, 价格带] 一次聚合，替换原逐客户 groupby.apply）
    # 原版逐客户 `g[...]["total_rev"].sum()` 对 float32 输入返回 float32；此处保持一致，
    # 缺失价格带补 np.float32(0) 并显式 astype("float32")，避免 unstack(fill_value) 提升为 float64。
    band_rev = cp.groupby([cust_col, "价格带"], observed=True)["total_rev"].sum().unstack()
    for _b in ["低价带", "中价带", "高价带"]:
        if _b not in band_rev.columns:
            band_rev[_b] = np.float32(0)
    band_rev = band_rev[["低价带", "中价带", "高价带"]].fillna(np.float32(0)).astype("float32")
    customer_bands = band_rev.reset_index()
    customer_bands["总收入"] = cp.groupby(cust_col, observed=True)["total_rev"].sum().to_numpy()
    customer_bands = customer_bands.rename(columns={
        "低价带": "低价品种收入", "中价带": "中价品种收入", "高价带": "高价品种收入",
    })
    customer_bands["总收入"] = customer_bands["总收入"].astype("float32")

    customer_bands["低价品种收入占比"] = (
        customer_bands["低价品种收入"] / customer_bands["总收入"].replace(0, float("nan"))
    )
    customer_bands["中价品种收入占比"] = (
        customer_bands["中价品种收入"] / customer_bands["总收入"].replace(0, float("nan"))
    )
    customer_bands["高价品种收入占比"] = (
        customer_bands["高价品种收入"] / customer_bands["总收入"].replace(0, float("nan"))
    )
    for _c in ["低价品种收入占比", "中价品种收入占比", "高价品种收入占比"]:
        customer_bands[_c] = customer_bands[_c].astype("float32")

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
    # v4.16: 样本量标记，单客户/月记录过少的价格离散度无统计意义
    dispersion["样本量标记"] = dispersion["客户月记录数"].apply(
        lambda n: "样本量不足" if n < 3 else "样本量充足"
    )

    return dispersion


# ============================================================
