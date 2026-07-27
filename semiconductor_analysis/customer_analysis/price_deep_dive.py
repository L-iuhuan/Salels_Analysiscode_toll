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
            "产品品种": prod,
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
    """业务员定价偏离分析。

    对每个业务负责人（CRM拓尔销售优先），计算其负责客户的
    定价相对市场中位数的偏离程度。

    参数:
        cust_prod: customer_x_product DataFrame
        portrait_df: 客户全景 DataFrame（含拓尔销售/业务负责人）

    返回:
        DataFrame: 每业务负责人一行
    """
    cp = cust_prod.copy()
    cp["均价"] = cp["rev_sum"] / cp["qty_sum"].replace(0, float("nan"))

    # 自动选择业务负责人列（CRM优先）
    owner_col = _pick_owner_column(portrait_df)
    if not owner_col:
        return pd.DataFrame()

    # 获取区域列
    region_col = "所属区域" if "所属区域" in portrait_df.columns else None

    # 构建客户→负责人映射（保留原始列名用于输出时重命名）
    info_cols = ["客户编号", owner_col]
    if region_col:
        info_cols.append(region_col)
    owner_map = portrait_df[info_cols].drop_duplicates()
    owner_map = owner_map[owner_map[owner_col].notna() & (owner_map[owner_col] != "未知")]

    if len(owner_map) == 0:
        return pd.DataFrame()

    # 将负责人信息关联到交易数据
    cp = cp.merge(owner_map, on="客户编号", how="inner")

    # 全市场中位价（每产品）
    market_median = cp.groupby("产品品种")["均价"].median().rename("市场中位价")

    # 计算每个客户-产品的中位价
    cust_median = cp.groupby(["客户编号", "产品品种"]).agg(
        客户均价=("均价", "median"),
    ).reset_index()

    # 关联市场中位价
    cust_median = cust_median.merge(market_median, on="产品品种", how="left")

    # 计算偏离度
    safe_median = cust_median["市场中位价"].replace(0, float("nan"))
    cust_median["偏离%"] = ((cust_median["客户均价"] - safe_median) / safe_median * 100).fillna(0)

    # 标记高价/低价（阈值来自 settings.py:PRICE_DEVIATION_THRESHOLDS）
    _pdt = PRICE_DEVIATION_THRESHOLDS
    cust_median["高价标记"] = cust_median["偏离%"] > _pdt.get("高偏离阈值", 10.0)
    cust_median["低价标记"] = cust_median["偏离%"] < _pdt.get("低偏离阈值", -10.0)

    # 关联负责人信息
    owner_info = owner_map.rename(columns={owner_col: "_owner"})
    cust_median = cust_median.merge(owner_info, on="客户编号", how="left")

    # 按负责人聚合
    grouped = cust_median.groupby("_owner")
    rows = []
    for owner, grp in grouped:
        n_cust = grp["客户编号"].nunique()
        if n_cust == 0:
            continue

        region = ""
        if region_col and region_col in grp.columns:
            vals = grp[region_col].dropna()
            if len(vals) > 0:
                region = vals.mode().iloc[0] if len(vals.mode()) > 0 else vals.iloc[0]

        mean_deviation = grp["偏离%"].mean()
        high_pct = grp["高价标记"].sum() / len(grp) * 100
        low_pct = grp["低价标记"].sum() / len(grp) * 100

        # 总营收
        cust_ids = grp["客户编号"].unique()
        cp_owner = cp[cp["客户编号"].isin(cust_ids)]
        total_rev = cp_owner["rev_sum"].sum()

        # 定价倾向判定（阈值来自 settings.py:PRICE_DEVIATION_THRESHOLDS）
        _pdt = PRICE_DEVIATION_THRESHOLDS
        if mean_deviation > _pdt.get("偏高倾向阈值", 5.0):
            tendency = _pdt.get("偏高标签", "偏高")
        elif mean_deviation < _pdt.get("偏低倾向阈值", -5.0):
            tendency = _pdt.get("偏低标签", "偏低")
        else:
            tendency = _pdt.get("中性标签", "中性")

        rows.append({
            "业务负责人": owner,
            "所属区域": region,
            "平均定价偏离%": round(mean_deviation, 1),
            "高价占比%": round(high_pct, 1),
            "低价占比%": round(low_pct, 1),
            "客户数": n_cust,
            "总营收": round(total_rev, 2),
            "定价倾向": tendency,
        })

    result = pd.DataFrame(rows)
    if len(result) > 0:
        result = result.sort_values("客户数", ascending=False, kind='stable')

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
