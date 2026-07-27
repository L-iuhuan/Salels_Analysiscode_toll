"""
价格深度分析模块（Phase 3）。

4张价格分析表：
  1. 跨客户价格差异 — 同产品不同客户的定价离散度
  2. 渠道价格对比 — 代理 vs 直供价差
  3. 业务员定价偏离 — 各销售负责人的定价倾向
  4. 市场细分价格 — 按客户层级/区域/产品线聚合
"""

import os
import sys
import pandas as pd
import numpy as np

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from config.settings import CUSTOMER_COL_MAP
from config.settings import PRICE_DISPERSION_THRESHOLDS, PRICE_DEVIATION_THRESHOLDS, PRICE_ANALYSIS_MIN_CUSTOMERS


# ============================================================
# 辅助函数
# ============================================================

def _calc_price_per_row(row: pd.Series) -> float:
    """计算单行均价，零数量返回 NaN。"""
    qty = row.get("qty_sum", 0)
    if qty > 0:
        return row.get("rev_sum", 0) / qty
    return float("nan")


# ============================================================
# 1. 跨客户价格差异
# ============================================================

def calc_cross_customer_price_variation(
    cust_prod: pd.DataFrame,
    portrait_df: pd.DataFrame = None,
    min_customers: int = None,
) -> pd.DataFrame:
    """同产品跨客户价格差异分析。

    对每个产品品种，计算其在各客户中的均价分布：
    - 平均/中位数/P25/P75 价格
    - 价格CV（离散度）
    - 最低/最高价客户
    - 价差百分比
    - 价格差异等级

    参数:
        cust_prod: customer_x_product DataFrame（Silver层）
        portrait_df: 客户全景 DataFrame（用于获取客户名，可选）
        min_customers: 最少客户数，低于此值不纳入

    返回:
        DataFrame: 每产品一行
    """
    if min_customers is None:
        min_customers = PRICE_ANALYSIS_MIN_CUSTOMERS
    # 计算每客户-产品-月的均价，然后每个客户取中位数均价
    cp = cust_prod.copy()
    cat_col = CUSTOMER_COL_MAP.get("品类列", "产品一级分类")

    cp["均价"] = cp["rev_sum"] / cp["qty_sum"].replace(0, float("nan"))

    # 每客户-产品聚合（跨月取中位价）
    agg_dict = {"均价中位数": ("均价", "median")}
    if cat_col in cp.columns:
        agg_dict["产品一级分类"] = (cat_col, "first")
    cust_prod_price = cp.groupby(["客户编号", "产品品种"]).agg(**agg_dict).reset_index()
    if cat_col not in cp.columns or cust_prod_price["产品一级分类"].isna().all():
        cust_prod_price["产品一级分类"] = "未知"

    # 跨客户聚合
    grouped = cust_prod_price.groupby("产品品种")
    rows = []
    for prod, grp in grouped:
        n_cust = len(grp)
        if n_cust < min_customers:
            continue
        prices = grp["均价中位数"].dropna()
        if len(prices) < min_customers:
            continue

        mean_p = prices.mean()
        median_p = prices.median()
        p25 = prices.quantile(0.25)
        p75 = prices.quantile(0.75)
        cv = prices.std() / mean_p if mean_p > 0 else 0

        # 极值客户
        idx_min = prices.idxmin()
        idx_max = prices.idxmax()
        min_customer = grp.loc[idx_min, "客户编号"]
        max_customer = grp.loc[idx_max, "客户编号"]
        min_price = prices.min()
        max_price = prices.max()
        price_range_pct = (max_price - min_price) / median_p * 100 if median_p > 0 else 0

        # 价格离散度等级（阈值来自 settings.py:PRICE_DISPERSION_THRESHOLDS）
        _pdt = PRICE_DISPERSION_THRESHOLDS
        if cv > _pdt.get("高离散度阈值", 0.30):
            level = "高"
        elif cv > _pdt.get("中离散度阈值", 0.15):
            level = "中"
        else:
            level = _pdt.get("默认等级", "低")

        cat_val = grp["产品一级分类"].iloc[0] if "产品一级分类" in grp.columns else "未知"

        rows.append({
            "产品名称": prod,
            "产品一级分类": cat_val,
            "客户数": n_cust,
            "平均价格": round(mean_p, 2),
            "中位数价格": round(median_p, 2),
            "P25价格": round(p25, 2) if pd.notna(p25) else None,
            "P75价格": round(p75, 2) if pd.notna(p75) else None,
            "价格CV": round(cv, 4),
            "最低价客户": min_customer if pd.notna(min_customer) else "",
            "最低价": round(min_price, 2),
            "最高价客户": max_customer if pd.notna(max_customer) else "",
            "最高价": round(max_price, 2),
            "最高-最低价差%": round(price_range_pct, 1),
            "价格差异等级": level,
        })

    result = pd.DataFrame(rows)
    if len(result) > 0:
        result = result.sort_values("价格CV", ascending=False, kind='stable')
    # v4.4: 加入业务负责人（从portrait_df合并）
    if portrait_df is not None and len(portrait_df) > 0 and "最低价客户" in result.columns:
        owner_col = None
        for c in portrait_df.columns:
            if "业务" in c and "负责" in c:
                owner_col = c; break
        if owner_col and "客户编号" in portrait_df.columns:
            owner_map = dict(zip(portrait_df["客户编号"], portrait_df[owner_col]))
            result["最低价客户-业务负责人"] = result["最低价客户"].map(owner_map).fillna("")
            result["最高价客户-业务负责人"] = result["最高价客户"].map(owner_map).fillna("")

    return result


# ============================================================
# 2. 渠道价格差异
# ============================================================

def calc_channel_price_comparison(
    cust_prod: pd.DataFrame,
    portrait_df: pd.DataFrame,
    min_customers: int = None,
) -> pd.DataFrame:
    """渠道价格差异：代理 vs 直供 同产品均价对比。

    参数:
        cust_prod: customer_x_product DataFrame
        portrait_df: 客户全景 DataFrame（含渠道类型）
        min_customers: 最少客户数

    返回:
        DataFrame: 每产品一行，含代理/直供均价及价差
    """
    if min_customers is None:
        min_customers = PRICE_ANALYSIS_MIN_CUSTOMERS
    cp = cust_prod.copy()
    cp["均价"] = cp["rev_sum"] / cp["qty_sum"].replace(0, float("nan"))

    # 获取渠道类型
    channel_map = portrait_df[["客户编号", "渠道类型"]].drop_duplicates()
    cp = cp.merge(channel_map, on="客户编号", how="left")

    # 每客户-产品聚合（跨月中位价）
    cust_prod_median = cp.groupby(["客户编号", "产品品种", "渠道类型"]).agg(
        均价中位数=("均价", "median"),
    ).reset_index()

    # 按渠道分组聚合
    rows = []
    for prod, grp in cust_prod_median.groupby("产品品种"):
        agent = grp[grp["渠道类型"] == "代理"]["均价中位数"].dropna()
        direct = grp[grp["渠道类型"] == "直供"]["均价中位数"].dropna()

        n_agent = len(agent)
        n_direct = len(direct)

        if n_agent + n_direct < min_customers:
            continue
        # v4.16: 仅双渠道且每个渠道样本>=3才比较（单客户渠道无统计意义）
        if n_direct < 3 or n_agent < 3:
            continue

        agent_mean = agent.mean()
        direct_mean = direct.mean()

        if pd.notna(direct_mean) and direct_mean > 0 and pd.notna(agent_mean):
            spread = (agent_mean - direct_mean) / direct_mean * 100
        else:
            spread = float("nan")

        rows.append({
            "产品品种": prod,
            "代理均价": round(agent_mean, 2) if pd.notna(agent_mean) else None,
            "直供均价": round(direct_mean, 2) if pd.notna(direct_mean) else None,
            "代理-直供价差%": round(spread, 1) if pd.notna(spread) else None,
            "代理客户数": n_agent,
            "直供客户数": n_direct,
            "总客户数": n_agent + n_direct,
        })

    result = pd.DataFrame(rows)
    if len(result) > 0:
        result = result.sort_values("代理-直供价差%", ascending=False, na_position="last", kind='stable')

    return result


# ============================================================
# 3. 业务员定价偏离
# ============================================================

def _pick_owner_column(portrait_df: pd.DataFrame) -> str:
    """选择最佳可用的业务负责人列：CRM拓尔销售优先，业务负责人回退。"""
    candidates = [c for c in portrait_df.columns if "拓尔销售" in c or "业务负责人" in c]
    for col in candidates:
        n_unique = portrait_df[col].nunique()
        n_non_null = portrait_df[col].notna().sum()
        if n_unique >= 2 and n_non_null > 0:  # 至少有区分度
            return col
    return candidates[0] if candidates else ""


def calc_sales_owner_price_deviation(
    cust_prod: pd.DataFrame,
    portrait_df: pd.DataFrame,
) -> pd.DataFrame:
    """业务员定价偏离分析 v4.10。

    核心逻辑: 不是看"平均偏离"，而是看"低价值客户获得比高价值客户更低价格"的笔数。
    KA/AA客户获得低价=合理战略优惠，不计入问题。
    MM客户+非战略+低价=异常，需审查。

    输出新增: 异常低价客户Top5、集中品类、品类偏差标记。
    """
    cp = cust_prod.copy()
    cp["均价"] = cp["rev_sum"] / cp["qty_sum"].replace(0, float("nan"))

    owner_col = _pick_owner_column(portrait_df)
    if not owner_col: return pd.DataFrame()

    region_col = "所属区域" if "所属区域" in portrait_df.columns else None
    info_cols = ["客户编号", owner_col]
    if region_col: info_cols.append(region_col)
    owner_map = portrait_df[info_cols].drop_duplicates()
    owner_map = owner_map[owner_map[owner_col].notna() & (owner_map[owner_col] != "未知")]
    if len(owner_map) == 0: return pd.DataFrame()

    # 合并客户层级+策略信息
    _tier_cols = ["客户编号", "客户层级"]
    for _c in ["策略名称", "帕累托利润分级"]:
        if _c in portrait_df.columns:
            _tier_cols.append(_c)
    tier_info = portrait_df[_tier_cols].drop_duplicates()
    owner_map = owner_map.merge(tier_info, on="客户编号", how="left")
    owner_map["客户层级"] = owner_map["客户层级"].fillna("MM")

    cp = cp.merge(owner_map, on="客户编号", how="inner")

    # 产品中位价
    market_median = cp.groupby("产品品种")["均价"].median().rename("市场中位价")
    _agg_dict = {
        "客户均价": ("均价", "median"),
        "客户层级": ("客户层级", "first"),
    }
    if "策略名称" in cp.columns:
        _agg_dict["策略名称"] = ("策略名称", "first")
    if "帕累托利润分级" in cp.columns:
        _agg_dict["帕累托分级"] = ("帕累托利润分级", "first")
    _line_col = next((c for c in ["型号_产品线（新）", "产品一级分类"] if c in cp.columns), None)
    if _line_col:
        _agg_dict["产品线"] = (_line_col, "first")
    cust_median = cp.groupby(["客户编号", "产品品种"]).agg(**_agg_dict).reset_index()
    cust_median = cust_median.merge(market_median, on="产品品种", how="left")
    safe = cust_median["市场中位价"].replace(0, float("nan"))
    cust_median["偏离%"] = ((cust_median["客户均价"] - safe) / safe * 100).fillna(0)

    # 分类: KA/AA低价=合理, MM低价+非战略=异常
    def _classify(row):
        tier = str(row.get("客户层级","MM"))
        dev = float(row.get("偏离%",0))
        strategy = str(row.get("策略名称",""))
        is_strategic = "深度绑定" in strategy or "重点维护" in strategy
        if tier in ("KA","AA") and dev < -10: return "合理低价(KA优惠)"
        if tier == "MM" and dev < -10 and not is_strategic: return "异常低价(小客户)"
        if dev < -10: return "偏低(关注)"
        if dev > 10: return "偏高"
        return "正常"

    cust_median["分类"] = cust_median.apply(_classify, axis=1)
    abnormal = cust_median[cust_median["分类"] == "异常低价(小客户)"].copy()

    # 关联负责人
    owner_info = owner_map.rename(columns={owner_col: "_owner"})
    cust_median = cust_median.merge(owner_info[["客户编号","_owner"]].drop_duplicates(), on="客户编号", how="left")

    rows = []
    for owner, grp in cust_median.groupby("_owner"):
        n_cust = grp["客户编号"].nunique()
        if n_cust == 0: continue

        total = len(grp)
        ka_low = (grp["分类"] == "合理低价(KA优惠)").sum()
        mm_abnormal = (grp["分类"] == "异常低价(小客户)").sum()
        low_concern = (grp["分类"] == "偏低(关注)").sum()
        high = (grp["分类"] == "偏高").sum()

        # 异常低价客户Top5
        ab_grp = grp[grp["分类"] == "异常低价(小客户)"]
        top_cust = ab_grp.groupby("客户编号").agg(
            笔数=("偏离%","count"), 均偏离=("偏离%","mean")
        ).sort_values("笔数", ascending=False).head(5)
        top_cust_str = "; ".join(f"{c}({int(r['笔数'])}笔,均偏离{r['均偏离']:.0f}%)" for c, r in top_cust.iterrows())

        # 集中品类: 异常低价中最多的品类
        cat_col = "产品线" if "产品线" in ab_grp.columns else None
        cat_note = ""
        if cat_col and len(ab_grp) > 0:
            cat_cnt = ab_grp[cat_col].value_counts()
            top_cat = cat_cnt.index[0] if len(cat_cnt) > 0 else ""
            top_cat_pct = cat_cnt.iloc[0] / len(ab_grp) * 100 if len(ab_grp) > 0 else 0
            cat_note = f"{top_cat}({top_cat_pct:.0f}%)" if top_cat else ""
            if top_cat_pct > 80: cat_note += " [品类系统性偏低]"

        # 定价倾向: 用MM客户数占比(非总交易占比)
        mm_total = (grp["客户层级"] == "MM").sum()
        mm_pct = mm_abnormal / mm_total * 100 if mm_total > 0 else 0
        if mm_abnormal >= 10 and mm_pct > 15: tendency = "异常低价偏高"
        elif mm_abnormal >= 3: tendency = "需关注"
        elif ka_low > 0: tendency = "正常(含KA优惠)"
        else: tendency = "正常"

        # 区域
        region = ""
        if region_col and region_col in grp.columns:
            vals = grp[region_col].dropna()
            if len(vals) > 0: region = vals.mode().iloc[0] if len(vals.mode()) > 0 else vals.iloc[0]

        cust_ids = grp["客户编号"].unique()
        total_rev = cp[cp["客户编号"].isin(cust_ids)]["rev_sum"].sum()

        rows.append({
            "业务负责人": owner, "所属区域": region,
            "总交易笔数": total,
            "KA合理低价值": ka_low, "MM异常低价数": mm_abnormal,
            "异常低价占比%": round(mm_pct, 1),
            "偏高笔数": high, "偏低关注笔数": low_concern,
            "客户数": n_cust, "总营收": round(total_rev, 2),
            "定价倾向": tendency,
            "异常低价客户Top5": top_cust_str,
            "集中品类": cat_note,
        })

    result = pd.DataFrame(rows)
    if len(result) > 0:
        result = result.sort_values("MM异常低价数", ascending=False)
    return result


# ============================================================
# 4. 市场细分价格
# ============================================================

def calc_segment_price_analysis(
    cust_prod: pd.DataFrame,
    portrait_df: pd.DataFrame,
) -> pd.DataFrame:
    """市场细分价格分析。

    按客户层级/所属区域/产品线三个维度聚合均价，计算价格指数。

    参数:
        cust_prod: customer_x_product DataFrame
        portrait_df: 客户全景 DataFrame

    返回:
        DataFrame: 每细分维度一行
    """
    cp = cust_prod.copy()
    cat_col = CUSTOMER_COL_MAP.get("品类列", "产品一级分类")
    cp["均价"] = cp["rev_sum"] / cp["qty_sum"].replace(0, float("nan"))

    # 整体均价基准
    overall_mean = cp["均价"].mean()

    rows = []

    # 维度配置：每个维度的列名来源
    dim_configs = [
        ("客户层级", "客户层级"),
        ("所属区域", "所属区域"),
        ("产品线", cat_col),
    ]

    for dim_name, dim_col in dim_configs:
        if dim_col not in portrait_df.columns and dim_col not in cp.columns:
            continue

        if dim_name == "产品线" and dim_col in cp.columns:
            # 产品线维度直接在 cp 中已有，无需 merge
            cp_dim = cp[cp[dim_col].notna() & (cp[dim_col] != "未知")].copy()
        elif dim_col in portrait_df.columns:
            cust_dim = portrait_df[["客户编号", dim_col]].drop_duplicates()
            cust_dim = cust_dim[cust_dim[dim_col].notna() & (cust_dim[dim_col] != "未知")]
            cp_dim = cp.merge(cust_dim, on="客户编号", how="inner")
        else:
            # dim_col 仅在 cp 中（如 产品一级分类 已在上层处理）
            continue

        grouped = cp_dim.groupby(dim_col)
        for val, grp in grouped:
            seg_mean = grp["均价"].mean()
            price_index = (seg_mean / overall_mean * 100) if overall_mean > 0 else 100
            n_cust = grp["客户编号"].nunique()
            total_rev = grp["rev_sum"].sum()
            n_trans = len(grp)

            rows.append({
                "细分维度": dim_name,
                "维度值": val,
                "均价": round(seg_mean, 2),
                "价格指数": round(price_index, 1),
                "客户数": n_cust,
                "总营收": round(total_rev, 2),
                "交易记录数": n_trans,
            })

    result = pd.DataFrame(rows)
    if len(result) > 0:
        result = result.sort_values(["细分维度", "客户数"], ascending=[True, False], kind='stable')

    return result


# ============================================================
# 定价合理性分析 (v4.8: 方案A+B)
# ============================================================

def calc_pricing_fairness(cust_prod, portrait_df=None):
    """计算每客户×每产品的定价合理性评分，标记异常低价。

    v4.9: +归因分析列(对比基准客户及价格) + 体量分改用帕累托分级 + 中文化列名
    """
    from config.settings_customer import PRICING_FAIRNESS
    cfg = PRICING_FAIRNESS
    min_cust = cfg.get("异常低价_最小客户数", 5)

    cxp = cust_prod.copy()
    rev_col = "rev_sum" if "rev_sum" in cxp.columns else "金额"
    qty_col = "qty_sum" if "qty_sum" in cxp.columns else "数量"
    profit_col = "profit_clip_sum" if "profit_clip_sum" in cxp.columns else "_利润_裁剪"

    # 每客户×产品聚合
    cp_agg = cxp.groupby(["客户编号", "产品品种"]).agg(
        交易总额=(rev_col, "sum"), 交易总量=(qty_col, "sum"),
        交易总利润=(profit_col, "sum"),
    ).reset_index()
    cp_agg = cp_agg[cp_agg["交易总量"] > 0]
    cp_agg["单价"] = cp_agg["交易总额"] / cp_agg["交易总量"]
    cp_agg["毛利率%"] = np.where(cp_agg["交易总额"] > 0,
        cp_agg["交易总利润"] / cp_agg["交易总额"] * 100, 0)

    # v4.16: 先合并渠道类型，用同渠道基准避免代理/直供混比
    if portrait_df is not None and "渠道类型" in portrait_df.columns:
        cust_col = "客户编号" if "客户编号" in portrait_df.columns else "客户名称"
        ch_map = portrait_df[[cust_col, "渠道类型"]].drop_duplicates()
        ch_map = ch_map.rename(columns={cust_col: "客户编号"})
        cp_agg = cp_agg.merge(ch_map, on="客户编号", how="left")
        cp_agg["渠道类型"] = cp_agg["渠道类型"].fillna("未知")
    else:
        cp_agg["渠道类型"] = "全部"

    # 每产品×渠道: 单价分位 + 对比基准客户
    prod_stats = cp_agg.groupby(["产品品种", "渠道类型"], observed=True).agg(
        产品总销售额=("交易总额", "sum"),
        产品P15单价=("单价", lambda x: x.quantile(0.15)),
        产品P25单价=("单价", lambda x: x.quantile(0.25)),
        产品P50单价=("单价", "median"),
        产品均价=("单价", "mean"),
        产品客户数=("交易总额", "count"),
        最高价客户=("单价", "idxmax"),  # 单价最高客户
        最高单价=("单价", "max"),
    ).reset_index()
    prod_stats = prod_stats[prod_stats["产品客户数"] >= min_cust]
    prod_stats["最高价客户"] = prod_stats["最高价客户"].map(
        lambda i: cp_agg.loc[i, "客户编号"] if i in cp_agg.index else ""
    )

    result = cp_agg.merge(prod_stats, on=["产品品种", "渠道类型"], how="inner")

    # 采购集中度
    cust_total = cp_agg.groupby("客户编号")["交易总额"].sum().to_dict()
    result["客户总采购额"] = result["客户编号"].map(cust_total)
    result["采购集中度"] = np.maximum(
        np.where(result["产品总销售额"] > 0, result["交易总额"] / result["产品总销售额"], 0),
        np.where(result["客户总采购额"] > 0, result["交易总额"] / result["客户总采购额"], 0))
    result["采购集中度百分位"] = result["采购集中度"].rank(pct=True) * 100 if len(result) > 1 else 50

    # 价格偏离
    result["价格偏离P50%"] = np.where(result["产品P50单价"] > 0,
        (result["单价"] - result["产品P50单价"]) / result["产品P50单价"] * 100, 0)

    # 合并客户画像
    if portrait_df is not None and len(portrait_df) > 0:
        cust_col_pf = "客户编号" if "客户编号" in portrait_df.columns else "客户名称"
        merge_cols = [cust_col_pf]
        for c in ["客户层级", "策略名称", "稳定关系分", "帕累托利润分级", "业务负责人", "近12月毛利"]:
            if c in portrait_df.columns: merge_cols.append(c)
        merge_df = portrait_df[merge_cols].rename(columns={cust_col_pf: "客户编号"})
        result = result.merge(merge_df, on="客户编号", how="left")

    # 体量分: 用帕累托利润分级映射(比固定KA/AA更细粒度)
    pareto_score_map = {"A级": 100, "B级": 80, "C级": 60, "D级": 30}
    result["体量分"] = result.get("帕累托利润分级", pd.Series("D级")).map(pareto_score_map).fillna(25)
    # 若帕累托分级不可用，回退到客户层级
    tier_map = {"KA": 100, "AA": 75, "KM": 50, "MM": 25}
    result.loc[result["体量分"] == 25, "体量分"] = (
        result.loc[result["体量分"] == 25, "客户层级"].map(tier_map).fillna(25))

    # 战略合作分
    strategy_map = {"策略1: 深度绑定": 100, "策略2: 重点维护": 80, "策略3: 培育放量": 60}
    result["战略合作分"] = result.get("策略名称", pd.Series("")).map(strategy_map).fillna(30)
    result["_稳定分"] = result.get("稳定关系分", pd.Series(50)).fillna(50)

    w = (cfg.get("体量分权重", 0.35), cfg.get("采购集中度分权重", 0.25),
         cfg.get("战略合作分权重", 0.25), cfg.get("稳定关系分权重", 0.15))
    result["定价合理性分"] = (result["体量分"] * w[0] + result["采购集中度百分位"] * w[1]
                            + result["战略合作分"] * w[2] + result["_稳定分"] * w[3])

    # 异常低价标记
    anomaly_pct = cfg.get("异常低价分位阈值", 15)
    result["单价低于P{}".format(anomaly_pct)] = result["单价"] < result["产品P{}单价".format(anomaly_pct)]
    anomaly = (
        result["单价低于P{}".format(anomaly_pct)]
        & result.get("客户层级", pd.Series("MM")).isin(cfg.get("异常低价_体量上限", ["MM"]))
        & (result["战略合作分"] < cfg.get("异常低价_战略分上限", 50))
    )
    result["异常低价标记"] = np.where(anomaly, "异常低价-需审查", "正常")
    result = result.drop(columns=["_稳定分"], errors="ignore")

    # 归因分析: 构建对比基准说明
    def _build_attribution(row):
        """解释该客户的低价是和哪些客户对比得出的。"""
        tier = row.get("客户层级", "MM")
        pareto = row.get("帕累托利润分级", "D级")
        # 同产品P50价和高价客户作为基准
        parts = [
            f"同渠道({row.get('渠道类型','全部')})该产品共{int(row['产品客户数'])}个客户",
            f"市场中位价¥{row['产品P50单价']:.4f}",
            f"该客户价¥{row['单价']:.4f}(偏离{row['价格偏离P50%']:.0f}%)",
            f"最高价客户「{row['最高价客户']}」¥{row['最高单价']:.4f}",
            f"该客户为{tier}级/{pareto}利润贡献",
        ]
        if row["战略合作分"] < 30:
            parts.append("非战略合作客户")
        return "；".join(parts)

    # 只输出异常行
    anomaly_df = result[result["异常低价标记"] == "异常低价-需审查"].copy()
    if len(anomaly_df) == 0:
        anomaly_df = result.nsmallest(50, "定价合理性分")
    anomaly_df["归因分析"] = anomaly_df.apply(_build_attribution, axis=1)

    # 输出列(中文化)
    out_cols = ["客户编号", "产品品种", "渠道类型", "单价", "毛利率%", "产品P15单价",
                "产品P50单价", "价格偏离P50%", "体量分", "采购集中度百分位",
                "战略合作分", "定价合理性分", "异常低价标记", "归因分析"]
    for c in ["客户层级", "帕累托利润分级", "业务负责人", "最高价客户", "最高单价", "产品客户数"]:
        if c in anomaly_df.columns: out_cols.append(c)
    return anomaly_df[out_cols]
