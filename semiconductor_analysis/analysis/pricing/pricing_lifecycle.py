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

    # 读取SKU生命周期阈值（优先从config，回退到硬编码默认值）
    try:
        from config.settings import PRODUCT_LIFECYCLE as _plc
    except ImportError:
        _plc = {}
    _sku_intro_max_months = _plc.get("sku_intro_max_months", 3)
    _sku_intro_min_qty = _plc.get("sku_intro_min_qty", 1000)
    _sku_exit_ratio = _plc.get("sku_exit_ratio", 0.30)
    _sku_decline_ratio = _plc.get("sku_decline_ratio", 0.70)

    def _stage_for_sku(group):
        g = group.sort_values(date_col, kind='stable')
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
        if in_months <= _sku_intro_max_months and total_qty < _sku_intro_min_qty:
            return "导入试销"

        if half_decline and last3_rev < peak_rev * _sku_exit_ratio and total_rev > 0:
            return "衰退出清"

        if half_decline and last3_rev > 0 and prior3_rev > 0 and last3_rev < prior3_rev * _sku_decline_ratio:
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
    def _stage_for_sku(group):
        g = group.sort_values(date_col, kind='stable')
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
    # 防御：确保 Period 类型（CSV 重载后 _月 为字符串）
    customer_monthly[date_col], latest_month = _ensure_period_dtype(
        customer_monthly[date_col], latest_month
    )

    # 爬坡期配置
    _ramp_threshold = float((thr or {}).get("爬坡期环比阈值", 0.05))
    _ramp_window = int((thr or {}).get("爬坡期_环比增长前N月均值", 3))

    def _stage_for_cust(group):
        g = group.sort_values(date_col, kind='stable')
        total_months = len(g)
        recent12 = g[g[date_col] > (latest_month - 12)]
        last_month = g[date_col].max()
        months_since_last = (latest_month - last_month).n if pd.notna(last_month) else 999
        avg_rev = recent12[rev_col].mean()

        # 连续3月是否低于均线15%
        last3 = g.tail(3)
        if len(last3) == 3 and avg_rev > 0:
            _decline_ratio = 1 - float((thr or {}).get("衰退期跌幅阈值", 0.15))
            all_below = all(r < avg_rev * _decline_ratio for r in last3[rev_col].values)
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

    # 附加上置信度指标：数据覆盖月数 / 期望月数
    _expected = int((thr or {}).get("lifecycle_expected_months", 18))
    cust_months = customer_monthly.groupby(cust_col)[date_col].nunique().reset_index()
    cust_months.columns = [cust_col, "生命周期_覆盖月数"]
    cust_months["生命周期_置信度"] = cust_months["生命周期_覆盖月数"].apply(
        lambda n: "低" if n < 6 else ("中" if n < _expected else "高")
    )
    stages = stages.merge(cust_months, on=cust_col, how="left")

    return stages

    def _stage_for_cust(group):
        g = group.sort_values(date_col, kind='stable')
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
        return pd.DataFrame({"客户编号": cxp[cust_col].unique(), "新品采购额": 0, "新品品种数": 0, "新品采购占比": float("nan"), "是否采购新品": False, "新品渗透率": 0.0})

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

