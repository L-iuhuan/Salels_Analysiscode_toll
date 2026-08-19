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

    批次②.5 车道D（等价向量化）：原 _stage_for_sku 逐SKU groupby.apply + 有序状态机，
    现改为一次性分组聚合计算全部谓词后按原优先级级联判定（导入→衰退出清→隐性衰退→成长→平稳→导入）。
    输出逐值与原版一致（浮点 1e-6 容差内）。
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

    # 过滤：与原 `g[(rev>0)|(qty>0)]` 一致
    filt = prod_monthly[(prod_monthly[rev_col] > 0) | (prod_monthly[qty_col] > 0)]
    if len(filt) == 0:
        all_prods = prod_monthly[prod_col].drop_duplicates().sort_values(kind="stable")
        return pd.DataFrame({prod_col: list(all_prods), "SKU生命周期阶段": "导入试销"})

    filt = filt.sort_values([prod_col, date_col], kind="stable")
    g = filt.groupby(prod_col, observed=True)

    # ---- 每SKU基础量 ----
    f_size = g.size()
    total_rev = g[rev_col].sum()
    total_qty = g[qty_col].sum()
    peak_rev = g[rev_col].max()

    # 窗口：近3月/前3月（latest_month 取自过滤前全表，与原版一致）
    mask_r3 = filt[date_col] > (latest_month - 3)
    mask_p3 = (filt[date_col] <= (latest_month - 3)) & (filt[date_col] > (latest_month - 6))
    recent3_rev_avg = filt.loc[mask_r3, rev_col].groupby(
        filt.loc[mask_r3, prod_col], observed=True).mean().reindex(f_size.index).fillna(0.0)
    prior3_rev_avg = filt.loc[mask_p3, rev_col].groupby(
        filt.loc[mask_p3, prod_col], observed=True).mean().reindex(f_size.index).fillna(0.0)
    last3_rev = filt.loc[mask_r3, rev_col].groupby(
        filt.loc[mask_r3, prod_col], observed=True).sum().reindex(f_size.index).fillna(0.0)
    prior3_rev = filt.loc[mask_p3, rev_col].groupby(
        filt.loc[mask_p3, prod_col], observed=True).sum().reindex(f_size.index).fillna(0.0)

    # ---- 末6条连续/半数下滑判断（原 g.tail(6) + 逐对比较）----
    gcount = g.cumcount()
    gsize = g[rev_col].transform("size")
    rev_rev = gsize - 1 - gcount  # 0 = 最新（过滤后按时间排序）
    prev_rev = g[rev_col].shift(1)  # 时间上更早一行
    t_dec = (prev_rev > filt[rev_col]).fillna(False)  # 与更早行相比收入下降
    n_trans_row = np.minimum(5, gsize - 1)  # 窗口内相邻对数（每行）
    is_trans = rev_rev < n_trans_row
    t_sum = t_dec.where(is_trans, False).groupby(filt[prod_col], observed=True).sum()
    t_sum = t_sum.reindex(f_size.index).fillna(0)
    n_trans = np.minimum(5, f_size - 1)  # 每SKU窗口内相邻对数
    consecutive_decline = (n_trans >= 2) & (t_sum == n_trans)
    half_decline = (n_trans >= 2) & (t_sum >= 3)

    # ---- 优先级级联判定（与原有序 if/return 一致）----
    in_months = f_size
    last3 = last3_rev
    prior3 = prior3_rev
    idx = f_size.index
    stage = np.full(len(idx), "导入试销", dtype=object)
    i_intro = (in_months <= _sku_intro_max_months) & (total_qty < _sku_intro_min_qty)
    i_exit = half_decline & (last3 < peak_rev * _sku_exit_ratio) & (total_rev > 0)
    i_hidden = half_decline & (last3 > 0) & (prior3 > 0) & (last3 < prior3 * _sku_decline_ratio)
    _pa = prior3_rev_avg.to_numpy(dtype="float64")
    _ra = recent3_rev_avg.to_numpy(dtype="float64")
    _gr = np.zeros_like(_pa)
    np.divide(_ra - _pa, _pa, out=_gr, where=_pa > 0)
    i_growth = (prior3_rev_avg > 0) & (_gr > growth_threshold)
    i_mature = in_months >= min_months

    stage[(~i_intro) & i_exit.to_numpy()] = "衰退出清"
    stage[(~i_intro) & (~i_exit.to_numpy()) & i_hidden.to_numpy()] = "隐性衰退"
    stage[(~i_intro) & (~i_exit.to_numpy()) & (~i_hidden.to_numpy()) & i_growth.to_numpy()] = "成长爬坡"
    stage[(~i_intro) & (~i_exit.to_numpy()) & (~i_hidden.to_numpy()) & (~i_growth.to_numpy()) & i_mature.to_numpy()] = "平稳成熟"
    # 其余（含 in_months < 2 的过滤后单行SKU）保持"导入试销"

    # 原版输出覆盖 prod_monthly 全部产品（过滤后无行的产品 len(g)<2 → 导入试销）
    all_prods = prod_monthly[prod_col].drop_duplicates().sort_values(kind="stable").reset_index(drop=True)
    stage_map = dict(zip(idx, stage))
    stages = pd.DataFrame({prod_col: all_prods,
                           "SKU生命周期阶段": all_prods.map(stage_map).fillna("导入试销").to_numpy()})

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

    批次②.5 车道D（等价向量化）：原 _stage_for_cust 逐客户 groupby.apply + 有序状态机，
    现改为一次性分组聚合计算全部谓词后按原优先级级联判定（流失→休眠→导入→爬坡→衰退→成熟）。
    输出逐值与原版一致（浮点 1e-6 容差内）。
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
    _decline_ratio = 1 - float((thr or {}).get("衰退期跌幅阈值", 0.15))

    cd = customer_monthly.sort_values([cust_col, date_col], kind="stable")
    # observed=False：客户编号为 categorical 时保留全部分类（含空分类，空分类 → 流失期，
    # 与原版 `groupby(cust_col).apply(_stage_for_cust)` 的 observed=False 行为一致）
    g = cd.groupby(cust_col, observed=False)

    # ---- 每客户基础量：距上次采购月数、客户月龄、近12月均收入、末3月是否全低于均线×衰减比 ----
    last_month = g[date_col].max()
    first_purchase = g[date_col].min()
    cust_size = g[rev_col].size()
    months_since_last = (latest_month.ordinal - last_month.astype("int64")).where(
        last_month.notna(), 999)
    age_months = latest_month.ordinal - first_purchase.astype("int64")

    mask12 = cd[date_col] > (latest_month - 12)
    avg_rev = cd.loc[mask12, rev_col].groupby(
        cd.loc[mask12, cust_col], observed=False).mean()
    avg_rev = avg_rev.reindex(last_month.index)

    # 末3月（组内时间排序后 rev_rev 0=最新）全部低于均线×衰减比 → 衰退期候选
    gcount = g.cumcount()
    gsize = g[rev_col].transform("size")
    rev_rev = gsize - 1 - gcount
    is_last3 = rev_rev <= 2
    last3 = cd[is_last3]
    if len(last3) > 0:
        row_avg = avg_rev.reindex(last3[cust_col]).to_numpy()
        below = last3[rev_col].to_numpy() < (row_avg * _decline_ratio)
        below_all = pd.Series(below, index=last3.index).groupby(
            last3[cust_col], observed=True).all()
        below_all = below_all.reindex(last_month.index).fillna(False)
    else:
        below_all = pd.Series(False, index=last_month.index)
    all_below = below_all & (cust_size >= 3) & (avg_rev > 0)

    # ---- 爬坡期：近N月均值环比（prior > 0 时才除，与原版 if prior_n_avg>0 一致）----
    mask_recent_n = cd[date_col] > (latest_month - _ramp_window)
    mask_prior_n = (cd[date_col] <= (latest_month - _ramp_window)) & (
        cd[date_col] > (latest_month - 2 * _ramp_window))
    recent_n_avg = cd.loc[mask_recent_n, rev_col].groupby(
        cd.loc[mask_recent_n, cust_col], observed=False).mean().reindex(last_month.index).fillna(0.0)
    prior_n_avg = cd.loc[mask_prior_n, rev_col].groupby(
        cd.loc[mask_prior_n, cust_col], observed=False).mean().reindex(last_month.index).fillna(0.0)
    _pa = prior_n_avg.to_numpy(dtype="float64")
    _rn = recent_n_avg.to_numpy(dtype="float64")
    _g = np.zeros_like(_pa)
    np.divide(_rn - _pa, _pa, out=_g, where=_pa > 0)
    is_ramp = (prior_n_avg > 0) & (_g > _ramp_threshold)

    # ---- 优先级级联判定（与原有序 if/return 一致）----
    msl = months_since_last.to_numpy()
    age = age_months.to_numpy()
    stage = np.full(len(last_month.index), "成熟期", dtype=object)
    i_lost = msl >= 18
    i_sleep = (~i_lost) & (msl >= 6)
    i_intro = (~i_lost) & (msl < 6) & (age <= 12)
    i_ramp = (~i_lost) & (~i_sleep) & (~i_intro) & is_ramp.to_numpy()
    i_decline = (~i_lost) & (~i_sleep) & (~i_intro) & (~is_ramp.to_numpy()) & all_below.to_numpy()
    stage[i_lost] = "流失期"
    stage[i_sleep] = "休眠期"
    stage[i_intro] = "导入期"
    stage[i_ramp] = "爬坡期"
    stage[i_decline] = "衰退期"

    # 客户编号保持 categorical（含全部分类），与原版 groupby.apply().reset_index() 一致
    stages = pd.DataFrame({cust_col: last_month.index.values, "客户生命周期": stage})

    # 附加上置信度指标：数据覆盖月数 / 期望月数
    _expected = int((thr or {}).get("lifecycle_expected_months", 18))
    cust_months = customer_monthly.groupby(cust_col)[date_col].nunique().reset_index()
    cust_months.columns = [cust_col, "生命周期_覆盖月数"]
    cust_months["生命周期_置信度"] = np.select(
        [cust_months["生命周期_覆盖月数"] < 6,
         cust_months["生命周期_覆盖月数"] < _expected],
        ["低", "中"], default="高")
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

