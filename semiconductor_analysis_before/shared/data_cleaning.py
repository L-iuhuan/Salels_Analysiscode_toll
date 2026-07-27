import pandas as pd
import numpy as np

from config.settings import ERP_COL_MAP


def rename_erp_columns(df: pd.DataFrame) -> pd.DataFrame:
    """将ERP原始列名重命名为标准列名（存在则改，不存在则跳过）。"""
    rename_map = {k: v for k, v in ERP_COL_MAP.items() if k in df.columns}
    if rename_map:
        df = df.rename(columns=rename_map)
    return df


def winsorize_margins(
    df: pd.DataFrame,
    profit_col: str = "利润",
    rev_col: str = "金额",
    lower: float = -0.50,
    upper: float = 0.75,
    inplace: bool = True,
) -> pd.DataFrame:
    """对逐行毛利率做Winsorization钳制。

    在行级计算毛利率并钳制到[lower, upper]范围，防止极端值影响月度汇总。
    与产品生命周期v2.8的清洗逻辑一致：
      - 下限-50%：允许真实亏损进入汇总，同时防止成本多输零等录入错误
      - 上限75%：超过此值基本是样品单或成本未记账

    参数:
        df: 包含利润列和收入列的DataFrame
        profit_col: 利润（未税）列名
        rev_col: 收入（未税）列名
        lower: 毛利率下限（默认-0.50即-50%）
        upper: 毛利率上限（默认0.75即75%）
        inplace: 是否原地修改

    返回:
        增加了'_毛利率'和'_利润_裁剪'两列的DataFrame
    """
    result = df if inplace else df.copy()
    result["_毛利率"] = result[profit_col] / result[rev_col].replace(0, float("nan"))
    result["_毛利率"] = result["_毛利率"].clip(lower=lower, upper=upper)
    result["_利润_裁剪"] = result["_毛利率"] * result[rev_col]
    return result


def filter_negative_qty(
    df: pd.DataFrame,
    qty_col: str = "数量",
    inplace: bool = True,
) -> pd.DataFrame:
    """剔除销量为负的记录（退货/红冲），从物理层面避免比率失真。

    与产品生命周期v2.8的过滤逻辑一致。
    """
    result = df if inplace else df.copy()
    before = len(result)
    result = result[result[qty_col] > 0].copy()
    removed = before - len(result)
    if removed > 0:
        print(f"  负销量过滤: 剔除 {removed} 条记录 ({removed/before*100:.1f}%)")
    return result


def monthly_aggregate(
    df: pd.DataFrame,
    date_col: str = "发货日期",
    group_cols: list = None,
    value_cols: dict = None,
    date_format: str = "M",
) -> pd.DataFrame:
    """按月聚合数据。

    参数:
        df: 输入DataFrame（需包含date_col）
        date_col: 日期列名
        group_cols: 分组列名列表，如['客户编号', '产品品种']
        value_cols: 值列聚合方式字典，如{'金额': 'sum', '数量': 'sum'}
        date_format: 日期格式，'M'=月度Period，'D'=日期

    返回:
        按月+分组聚合后的DataFrame，包含'_月'列
    """
    if group_cols is None:
        group_cols = []
    if value_cols is None:
        value_cols = {"金额": "sum", "数量": "sum", "成本": "sum", "利润": "sum"}

    result = df.copy()
    result["_月"] = df[date_col].dt.to_period(date_format)

    agg_dict = {k: v for k, v in value_cols.items() if k in result.columns}
    for k in value_cols:
        if k not in result.columns:
            print(f"  [警告] 聚合字段 '{k}' 在数据中不存在，已跳过")

    monthly = result.groupby(["_月"] + group_cols).agg(agg_dict).reset_index()
    monthly = monthly.sort_values(["_月"] + group_cols).reset_index(drop=True)
    return monthly


def monthly_aggregate_double_pass(
    df: pd.DataFrame,
    date_col: str = "发货日期",
    profit_col: str = "利润",
    rev_col: str = "金额",
    qty_col: str = "数量",
    cost_col: str = "成本",
    cust_col: str = "客户编号",
    prod_col: str = "产品品种",
    order_col: str = None,
    winsor_lower: float = -0.50,
    winsor_upper: float = 0.75,
) -> dict:
    """双通道月度聚合：同时生成客户级和产品级的月度聚合表。

    这是共享数据管道的核心入口，一次调用同时输出两套系统需要的silver层数据。

    参数:
        df: 清洗后的行级数据（已做负销量过滤、Winsorization）
        date_col, profit_col, rev_col, qty_col, cost_col: 列名
        cust_col: 客户编号列名
        prod_col: 产品品种列名
        order_col: 订单号列名（用于统计订单数）。不指定时自动尝试常见列名。

    返回:
        dict:
          'customer_monthly': 客户×月份聚合表
          'product_monthly':  产品×月份聚合表
          'customer_x_product': 客户×产品×月份聚合表（下钻桥梁基础数据）
    """
    df = df.copy()
    df["_月"] = df[date_col].dt.to_period("M")

    # 客户×月份
    cust_monthly = (
        df.groupby(["_月", cust_col])
        .agg(
            qty_sum=(qty_col, "sum"),
            rev_sum=(rev_col, "sum"),
            cost_sum=(cost_col, "sum"),
            profit_raw_sum=(profit_col, "sum"),
            profit_clip_sum=("_利润_裁剪", "sum"),
            order_count=(order_col or "订单编号", "nunique")
            if (order_col or "订单编号") in df.columns
            else (qty_col, "count"),
        )
        .reset_index()
    )
    cust_monthly["毛利率%"] = (
        cust_monthly["profit_clip_sum"] / cust_monthly["rev_sum"].replace(0, float("nan")) * 100
    )

    # 产品×月份（动态agg：基础指标 + 可选新品标记）
    _prod_agg = {
        "qty_sum": (qty_col, "sum"),
        "rev_sum": (rev_col, "sum"),
        "cost_sum": (cost_col, "sum"),
        "profit_raw_sum": (profit_col, "sum"),
        "profit_clip_sum": ("_利润_裁剪", "sum"),
        "avg_price": (rev_col, lambda x: x.sum() / df.loc[x.index, qty_col].sum() if df.loc[x.index, qty_col].sum() > 0 else float("nan")),
    }
    # 如果源数据有"新品标记"（来自ERP的"是否新品"列），携带至Silver层
    if "新品标记" in df.columns:
        _prod_agg["新品标记"] = ("新品标记", "first")

    prod_monthly = (
        df.groupby(["_月", prod_col])
        .agg(**_prod_agg)
        .reset_index()
    )
    prod_monthly["毛利率%"] = (
        prod_monthly["profit_clip_sum"] / prod_monthly["rev_sum"].replace(0, float("nan")) * 100
    )

    # 客户×产品×月份（下钻桥梁）
    cust_prod_monthly = (
        df.groupby(["_月", cust_col, prod_col])
        .agg(
            qty_sum=(qty_col, "sum"),
            rev_sum=(rev_col, "sum"),
            profit_clip_sum=("_利润_裁剪", "sum"),
        )
        .reset_index()
    )
    cust_prod_monthly["毛利率%"] = (
        cust_prod_monthly["profit_clip_sum"] / cust_prod_monthly["rev_sum"].replace(0, float("nan")) * 100
    )

    return {
        "customer_monthly": cust_monthly,
        "product_monthly": prod_monthly,
        "customer_x_product": cust_prod_monthly,
    }


def identify_sample_orders(
    df: pd.DataFrame,
    cust_col: str = "客户编号",
    prod_col: str = "产品品种",
    price_col: str = "单价",
    std_dev_threshold: float = 2.0,
) -> pd.DataFrame:
    """按 客户×产品品种 分组识别可能的样品单。

    单价低于该组合均值减 N 倍标准差的记录标记为候选异常单。

    返回:
        原DataFrame增加'_候选_样品单'列（True/False）
        以及'_单价_z偏移量'列
    """
    result = df.copy()
    stats = (
        result.groupby([cust_col, prod_col])[price_col]
        .agg(["mean", "std", "count"])
        .reset_index()
    )
    stats.columns = [cust_col, prod_col, "_price_mean", "_price_std", "_price_n"]
    stats["_price_std"] = stats["_price_std"].fillna(0)

    result = result.merge(stats, on=[cust_col, prod_col], how="left")
    result["_单价_z偏移量"] = (
        (result[price_col] - result["_price_mean"]) / result["_price_std"].replace(0, float("nan"))
    )
    result["_候选_样品单"] = result["_单价_z偏移量"] < -std_dev_threshold
    return result
