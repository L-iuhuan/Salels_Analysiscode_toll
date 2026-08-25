"""
价格分析函数 — ASP趋势、弹性计算、价格偏离度、价格带分布。

可被产品生命周期和客户分析复用。
"""
import numpy as np
import pandas as pd


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

    # [批次⑤ 缺陷B修复] cp[prod_col] 为 category dtype（silver parquet 读入口径）时，
    # pandas≥2.3.2 下 .map() 结果保留 category，后续减法/除法抛
    # "Object with dtype category cannot perform the numpy op subtract"。
    # 中位价/总销量本就是数值，显式 np.asarray 去 category 外壳；
    # 不指定 dtype——保持映射结果的自然 dtype（float32 入 → float32 出），
    # 与生产环境 pandas 2.3.1 的列 dtype 及 CSV 打印格式逐位一致。
    cp["中位价"] = np.asarray(cp[prod_col].map(prod_median))
    cp["产品总销量"] = np.asarray(cp[prod_col].map(prod_total_qty))
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
        from config.settings import PRICING_RECOMMENDATION
        discount_rates = PRICING_RECOMMENDATION.get("markdown_discount_rates", [0.03, 0.05, 0.08, 0.10])

    if price_col not in cxp.columns:
        cxp[price_col] = cxp["rev_sum"] / cxp["qty_sum"].replace(0, float("nan"))

    # 品种级别聚合
    prod_stats = cxp.groupby(prod_col).agg(
        近12月销量=("qty_sum", "sum"),
        近12月收入=("rev_sum", "sum"),
        平均单价=(price_col, "mean"),
    ).reset_index()

    # 向量化计算：对每个产品×每个降价幅度，一次性计算所有行
    n_products = len(prod_stats)
    n_rates = len(discount_rates)

    # 将产品数据重复 N_rate 次（每个产品对应 N 个降价幅度）
    df_repeated = prod_stats.loc[prod_stats.index.repeat(n_rates)].reset_index(drop=True)
    # 将降价幅度平铺 N_product 次
    df_repeated["降价幅度"] = np.tile(discount_rates, n_products)

    current_price = df_repeated["平均单价"].values
    base_qty = df_repeated["近12月销量"].values
    base_rev = df_repeated["近12月收入"].values
    rate = df_repeated["降价幅度"].values

    new_price = current_price * (1 - rate)
    qty_increase = base_qty * abs(elasticity) * rate
    new_qty = base_qty + qty_increase
    new_rev = new_price * new_qty
    rev_change = new_rev - base_rev

    result = df_repeated[[prod_col]].copy()
    result["降价幅度"] = rate
    result["原价"] = current_price
    result["新价"] = new_price
    result["预测增量销量"] = qty_increase
    result["预测新营收"] = new_rev
    result["营收变化"] = rev_change
    result["盈亏判断"] = np.where(rev_change > 0, "可试", "谨慎")

    return result

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

    # 向量化：使用 DataFrame 列级操作替代 iterrows()
    df = customer_profile.copy()
    suggestion_col = "__suggestions"
    df[suggestion_col] = pd.Series("", index=df.index, dtype="object")

    # 1. 新品导入机会（向量化条件）
    np_col = "新品采购占比"
    if np_col in df.columns:
        mask_import = (df[np_col] < 0.05) & (df.get("在采品种数", 0) > 0)
        df.loc[mask_import, suggestion_col] += "建议导入新品/替代料验证; "

        mask_expand = df[np_col] > 0.20
        df.loc[mask_expand, suggestion_col] += "新品渗透良好，可扩大推广; "

    # 2. 流失预警（向量化）
    churn_col = "采购中断预警"
    if churn_col in df.columns:
        mask_churn = df[churn_col].fillna(False).astype(bool)
        df.loc[mask_churn, suggestion_col] += "客户采购间隔异常，建议回访确认需求变化; "

    # 3. 风险品种（向量化）
    conc_col = "强依赖标记"
    if conc_col in df.columns:
        mask_conc = df[conc_col].fillna(False).astype(bool)
        df.loc[mask_conc, suggestion_col] += "品种集中度过高，建议引导多品种采购降低风险; "

    # 4. 衰退信号（向量化）
    lc_col = "客户生命周期"
    if lc_col in df.columns:
        mask_decline = df[lc_col].isin(["衰退期", "休眠期", "流失期"])
        # 需要插入变量值，使用apply仅对命中行
        df.loc[mask_decline, suggestion_col] += (
            "客户处于" + df.loc[mask_decline, lc_col].astype(str) + "，建议启动挽回计划或控制信用额度; "
        )

    # 5. 提价机会 — 品种流失金额占比（向量化）
    sku_loss_col = "品种流失金额占比"
    if sku_loss_col in df.columns:
        mask_loss = df[sku_loss_col].fillna(0) > 0.15
        df.loc[mask_loss, suggestion_col] += "关键品种流失≥15%，需了解客户替代来源; "

    # 6. 价格谈判提价（向量化）
    price_dev_col = "低价品种收入占比"
    if price_dev_col in df.columns:
        mask_low_price = df[price_dev_col].fillna(0) > 0.50
        df.loc[mask_low_price, suggestion_col] += "高比例采购低价品种，有提价空间; "

    # 7. 生命周期行动 — 退市品种迁移（向量化）
    sku_stage_col = "主要SKU阶段"
    if sku_stage_col in df.columns:
        mask_exit = df[sku_stage_col] == "衰退出清"
        df.loc[mask_exit, suggestion_col] += "客户在用退市品种，需引导迁移替代型号; "

    # 聚合结果
    has_suggestions = df[suggestion_col].str.strip() != ""
    df.loc[has_suggestions, suggestion_col] = df.loc[has_suggestions, suggestion_col].str.rstrip("; ")
    df.loc[~has_suggestions, suggestion_col] = "暂无明显行动项"

    result = df[[cust_col, suggestion_col]].copy()
    result["行动建议数"] = result[suggestion_col].apply(
        lambda s: len(s.split(";")) if ";" in s and s != "暂无明显行动项" else (0 if s == "暂无明显行动项" else 1)
    )
    result = result.rename(columns={suggestion_col: "行动建议"})
    return result
