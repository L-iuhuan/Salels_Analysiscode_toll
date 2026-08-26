"""
客户全景画像计算。

按文档10大维度组织计算逻辑：
  1. 基本信息
  2. 经营势能（含趋势判断）
  3. 产品覆盖
  4. 产品线分布
  5. 采购健康度  ← 来自 dimensions.py 批量计算
  6. 价格治理     ← 来自 dimensions.py 批量计算
  7. 品类接受度   ← 来自 dimensions.py 批量计算
  8. SKU生命周期  ← 来自 dimensions.py 批量计算
  9. 新品渗透     ← 来自 dimensions.py 批量计算
 10. ASP/毛利率对比 ← 内联计算

批次②车道B：各 _dim_* 维度计算已从"逐客户 boolean 扫描 + Python 循环"
改为向量化/groupby 实现（_vec_* 系列），输出与逐行版逐值等价（浮点 1e-6 容差内）。
_derive_channel 逐客户版本保留（test/validation_suite.py 外部引用）。
"""

import os
import sys
import pandas as pd
import numpy as np

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from shared.data_cleaning import read_excel_auto
from config.settings import CUSTOMER_THRESHOLDS, CUSTOMER_COL_MAP, METRIC_CAPS, CHANNEL_DERIVE, DEPT_REGION_MAP, CUSTOMER_ANALYSIS_WINDOW
from customer_analysis.dimensions import (
    calc_purchase_interval,
    calc_churn_warning,
    calc_product_concentration,
    calc_category_acceptance,
    calc_price_band_distribution,
    calc_sku_lifecycle_stage,
    calc_customer_lifecycle_stage,
    calc_new_product_cohort,
    calc_opportunity_signals,
    calc_risk_signals,
)


# ============================================================
# 辅助函数：批量计算
# ============================================================

def _compute_batch_metrics(cust_monthly, cust_prod, prod_monthly, latest_month, cat_col):
    """执行所有批量计算，返回结果字典。"""
    thr = CUSTOMER_THRESHOLDS
    metrics = {}

    metrics["intervals"] = calc_purchase_interval(
        cust_monthly,
        exclude_first_months=thr.get("purchase_interval_exclude_first_months", 6),
    )
    metrics["churn"] = calc_churn_warning(
        cust_monthly, metrics["intervals"],
        multiplier=thr.get("churn_multiplier", 1.5),
    )
    metrics["concentration"] = calc_product_concentration(
        cust_prod,
        top_n=thr.get("concentration_top_n", 5),
        threshold=thr.get("concentration_threshold", 0.7),
    )
    metrics["category_acc"] = calc_category_acceptance(cust_prod, category_col=cat_col)
    metrics["price_bands"] = calc_price_band_distribution(cust_prod)
    metrics["sku_stages"] = calc_sku_lifecycle_stage(prod_monthly)
    metrics["cust_stages"] = calc_customer_lifecycle_stage(
        cust_monthly, latest_month=latest_month,
    )
    metrics["new_prod_cohort"] = calc_new_product_cohort(prod_monthly, cust_prod)
    metrics["opp_signals"] = calc_opportunity_signals(
        cust_monthly, prod_monthly, cust_prod, latest_month=latest_month,
    )
    metrics["risk_signals"] = calc_risk_signals(
        cust_monthly, cust_prod, latest_month=latest_month,
    )

    return metrics


# ============================================================
# 维度辅助函数（每个返回dict，合并到客户行）
# ============================================================

def _derive_channel(cid, raw_data):
    """从交易数据推导渠道类型。

    支持两种模式：
      1. source_col模式：直接从指定列取值并映射（如"销售模式" → 经销→代理、直销→直供）
      2. 旧模式：buyer_col/end_cust_col匹配计数
    """
    if raw_data is None:
        return "未知"
    cd = CHANNEL_DERIVE

    # 模式1：source_col + mapping（如"销售模式"列）
    source_col = cd.get("source_col")
    if source_col and source_col in raw_data.columns:
        mapping = cd.get("mapping", {})
        row_match = raw_data[raw_data["客户编号"] == cid]
        if len(row_match) > 0:
            val = row_match[source_col].iloc[0]
            return mapping.get(str(val), cd.get("default", "未知"))
        return cd.get("default", "未知")

    # 模式2：旧版 buyer_col / end_cust_col 匹配计数
    buyer_col = cd.get("buyer_col", "代理商/直供名称")
    end_col = cd.get("end_cust_col", "实际终端客户")

    buyer_mask = raw_data[buyer_col] == cid if buyer_col in raw_data.columns else pd.Series(False, index=raw_data.index)
    buyer_count = buyer_mask.sum()

    if end_col in raw_data.columns:
        end_mask = raw_data[end_col] == cid
        end_count = end_mask.sum()
    else:
        end_count = 0

    if buyer_count == 0 and end_count == 0:
        return cd.get("default", "未知")
    return "直供" if end_count >= buyer_count else "代理"


def _vec_channel_derive(raw_data, cid_idx):
    """向量化渠道推导：一次调用等价于对所有客户执行 _derive_channel(cid, raw_data)。"""
    default = CHANNEL_DERIVE.get("default", "未知")
    if raw_data is None:
        return pd.Series(default, index=cid_idx, dtype=object)

    source_col = CHANNEL_DERIVE.get("source_col")
    if source_col and source_col in raw_data.columns:
        mapping = CHANNEL_DERIVE.get("mapping", {})
        # 每客户取首行 source_col 值，再按 mapping 映射（与 _derive_channel 的 iloc[0] 一致）
        first_vals = raw_data.groupby("客户编号")[source_col].first()
        ch = first_vals.map(lambda v: mapping.get(str(v), default))
        return ch.reindex(cid_idx).fillna(default).astype(object)

    # 旧模式：buyer_col / end_cust_col 匹配计数
    buyer_col = CHANNEL_DERIVE.get("buyer_col", "代理商/直供名称")
    end_col = CHANNEL_DERIVE.get("end_cust_col", "实际终端客户")
    buyer_count = (raw_data[buyer_col].value_counts()
                   if buyer_col in raw_data.columns else pd.Series(dtype=int))
    end_count = (raw_data[end_col].value_counts()
                 if end_col in raw_data.columns else pd.Series(dtype=int))
    bc = buyer_count.reindex(cid_idx).fillna(0)
    ec = end_count.reindex(cid_idx).fillna(0)
    ch = np.where((bc == 0) & (ec == 0), default,
                  np.where(ec >= bc, "直供", "代理"))
    return pd.Series(ch, index=cid_idx, dtype=object)


def _vec_base_info(cid_idx, cust_info, raw_data, attr_region=None, attr_owner=None):
    """向量化基本信息：等价于对每个客户执行 _dim_base_info()。

    渠道类型降级（从高到低）:
      1. cust_info中的"渠道类型"列（已从"销售模式"映射）
      2. 交易数据推导（向量化 _vec_channel_derive）
      3. 默认"未知"

    attr_region / attr_owner: 由 calc_customer_portrait 预计算的客户->区域/负责人 Series
    （None 表示原始数据缺少对应列）。
    """
    base = pd.DataFrame(index=cid_idx)
    derived = _vec_channel_derive(raw_data, cid_idx)
    base["渠道类型"] = derived

    # 客户信息表：每客户取首行（与 _dim_base_info 的 iloc[0] 一致）
    ci = cust_info
    if ci is not None and len(ci) > 0:
        ci = ci.drop_duplicates(subset="客户编号", keep="first").set_index("客户编号")
    else:
        ci = pd.DataFrame(index=cid_idx)
    ci_indexed = ci.reindex(cid_idx)
    in_ci = cid_idx.isin(ci.index)

    # 渠道类型：cust_info 中有效值优先，否则用交易推导值
    if "渠道类型" in ci.columns:
        ch = ci_indexed["渠道类型"]
        # 与 `if channel and channel != "未知"` 一致：None/空串/"未知"→推导；
        # NaN 在 Python 中为 truthy，原逻辑采用 NaN（此处亦保留该语义）
        use = (ch != "") & (ch != "未知") & (ch.notna() | (ch.astype(str) == "nan"))
        base["渠道类型"] = np.where(use, ch, derived)

    # 其他基础字段（列缺失→默认值；列存在但值为空→保留空值，与原 .get 一致）
    for col, default in [("客户等级", "未知"), ("客户类别", "未分类"),
                         ("所属区域", "未知"), ("业务负责人", "未知")]:
        if col in ci.columns:
            v = ci_indexed[col]
            base[col] = np.where(in_ci, v, default)
        else:
            base[col] = default

    # 客户不在客户信息表时的回退：
    #   attr_map 非空（原始数据含 销售部门/实际业务员）→ 用 attr 值，且 客户等级/客户类别 置空(NaN)
    #   attr_map 为空 → 保持默认"未知/未分类"
    not_ci = ~in_ci
    if (attr_region is not None) or (attr_owner is not None):
        if attr_region is not None:
            base.loc[not_ci, "所属区域"] = attr_region.reindex(cid_idx)[not_ci].values
        if attr_owner is not None:
            base.loc[not_ci, "业务负责人"] = attr_owner.reindex(cid_idx)[not_ci].values
        base.loc[not_ci, "客户等级"] = np.nan
        base.loc[not_ci, "客户类别"] = np.nan

    return base


def _vec_streaks(recent, cid_idx, growth_tolerance):
    """向量化连续增长/下滑月数：等价于 _dim_momentum 内的逐月状态机。

    规则（与原版逐月循环一致）:
      if v[i] > v[i-1]*tol: up+=1, down=0
      elif v[i] < v[i-1]:   down+=1, up=0
    最终值 = 末尾连续同向转换的段长（末尾为下滑则增长归0，反之亦然）。
    """
    if len(recent) == 0:
        return (pd.Series(0, index=cid_idx, dtype="int64"),
                pd.Series(0, index=cid_idx, dtype="int64"))
    rs = recent.sort_values(["客户编号", "_月"], kind="stable")
    prev = rs.groupby("客户编号", observed=True)["rev_sum"].shift(1)
    t_up = (rs["rev_sum"] > prev * growth_tolerance).fillna(False).astype(int)
    t_dn = ((~(rs["rev_sum"] > prev * growth_tolerance)) & (rs["rev_sum"] < prev)).fillna(False).astype(int)

    gcount = rs.groupby("客户编号", observed=True).cumcount()
    gsize = rs.groupby("客户编号", observed=True)["rev_sum"].transform("size")
    rev_rev = (gsize - 1 - gcount)  # 0 = 最新月（组内末尾）

    tmp = rs.assign(_rev_rev=rev_rev, _t_up=t_up, _t_dn=t_dn)
    tmp = tmp.sort_values(["客户编号", "_rev_rev"], kind="stable")
    first_zero_up = tmp[tmp["_t_up"] == 0].groupby("客户编号", observed=True)["_rev_rev"].min()
    first_zero_dn = tmp[tmp["_t_dn"] == 0].groupby("客户编号", observed=True)["_rev_rev"].min()
    streak_up = first_zero_up.reindex(cid_idx).fillna(0).astype("int64")
    streak_down = first_zero_dn.reindex(cid_idx).fillna(0).astype("int64")
    return streak_up, streak_down


def _vec_momentum(cust_monthly, latest_month):
    """向量化经营势能：等价于对每个客户执行 _dim_momentum()。

    输出列（顺序与原版一致）：
      近N月收入, 近N月毛利, 近12月毛利率, 前N月收入, 近12月数量, 订单数,
      收入增长率, ASP_加权, 连续增长月数, 连续下滑月数, YoY同比增速
    """
    _win = CUSTOMER_ANALYSIS_WINDOW
    _value_win = _win.get("value_window_months", 12)
    _growth_win = _win.get("growth_window_months", 12)
    _short_win = _win.get("growth_window_short", 6)

    m = cust_monthly
    cid_idx = pd.Index(m["客户编号"].unique())

    is_recent = m["_月"] > (latest_month - _value_win)
    is_prior = (m["_月"] <= (latest_month - _growth_win)) & (m["_月"] > (latest_month - _growth_win * 2))
    is_recent_s = m["_月"] > (latest_month - _short_win)
    is_prior_s = (m["_月"] <= (latest_month - _short_win)) & (m["_月"] > (latest_month - _short_win * 2))
    is_yr = (m["_月"] <= (latest_month - _value_win)) & (m["_月"] > (latest_month - _value_win * 2))

    recent = m[is_recent]
    prior = m[is_prior]
    pos_mask = m["rev_sum"] > 0
    recent_pos = m[pos_mask & is_recent]
    prior_pos = m[pos_mask & is_prior]
    recent_s = m[pos_mask & is_recent_s]
    prior_s = m[pos_mask & is_prior_s]
    yr_ago_pos = m[pos_mask & is_yr]

    # 精确逐组聚合：与逐客户版的 Series.sum()/mean() 逐位一致。
    # 注意：pandas groupby.sum()/mean() 的约简顺序与 Series.sum()/mean() 不同，
    # 在 float32 下会产生 ~1e-7 级差异，故此处必须按 [客户编号,_月] 排序后逐组用 Series 方法。
    def _exact_agg(sub, sum_cols, mean_col=None):
        """返回 {列: {客户编号: 值}}；sub 无需预先排序（内部按客户+月份排序）。

        注意 groupby 必须 observed=True：否则 categorical 列会遍历空组，
        空组的 mean() 返回 float64 NaN，会污染 dict 导致 Series 被提升为 float64。
        """
        cols = list(sum_cols)
        if mean_col is not None:
            cols += ["_cnt", "_mean"]
        out = {c: {} for c in cols}
        if len(sub) == 0:
            return out
        sub = sub.sort_values(["客户编号", "_月"], kind="stable")
        for cid, grp in sub.groupby("客户编号", sort=False, observed=True):
            for c in sum_cols:
                out[c][cid] = grp[c].sum()
            if mean_col is not None:
                out["_cnt"][cid] = len(grp)
                out["_mean"][cid] = grp[mean_col].mean()
        return out

    sum_cols = ["rev_sum", "profit_clip_sum", "qty_sum"]
    if "order_count" in m.columns:
        sum_cols.append("order_count")
    a_recent = _exact_agg(recent, sum_cols)
    a_prior = _exact_agg(prior, ["rev_sum"])
    a_rp = _exact_agg(recent_pos, [], mean_col="rev_sum")
    a_pp = _exact_agg(prior_pos, ["rev_sum"], mean_col="rev_sum")
    a_rs = _exact_agg(recent_s, [], mean_col="rev_sum")
    a_ps = _exact_agg(prior_s, ["rev_sum"], mean_col="rev_sum")
    a_yr = _exact_agg(yr_ago_pos, ["rev_sum"], mean_col="rev_sum")

    def _ser(d):
        return pd.Series(d).reindex(cid_idx)

    # 近N月收入/毛利/数量、前N月收入、订单数
    rev_col = f"近{_value_win}月收入"
    profit_col = f"近{_value_win}月毛利"
    recent_rev = _ser(a_recent["rev_sum"]).fillna(0)
    recent_profit = _ser(a_recent["profit_clip_sum"]).fillna(0)
    recent_qty = _ser(a_recent["qty_sum"]).fillna(0)
    prior_rev = _ser(a_prior["rev_sum"]).fillna(0)
    if "order_count" in m.columns:
        orders = _ser(a_recent["order_count"]).fillna(0).astype("int64")
    else:
        orders = pd.Series(0, index=cid_idx)

    # 正收入月的均值/计数（用于增长率与YoY）
    r_count = _ser(a_rp["_cnt"])
    r_mean = _ser(a_rp["_mean"])
    p_count = _ser(a_pp["_cnt"])
    p_sum = _ser(a_pp["rev_sum"])
    p_mean = _ser(a_pp["_mean"])

    # 短窗口回退（针对新客户/数据不足）
    rs_count = _ser(a_rs["_cnt"])
    rs_mean = _ser(a_rs["_mean"])
    ps_count = _ser(a_ps["_cnt"])
    ps_sum = _ser(a_ps["rev_sum"])
    ps_mean = _ser(a_ps["_mean"])

    # 收入增长率：主窗口优先，其次短窗口，均不满足为 0
    primary_ok = (p_count >= 2) & (p_sum > 0)
    growth_primary = ((r_mean - p_mean) / p_mean).where(primary_ok)
    r_avg_short = rs_mean.where(rs_count > 0, 0.0)
    short_ok = (ps_count >= 1) & (ps_sum > 0)
    growth_short = ((r_avg_short - ps_mean) / ps_mean).where(short_ok, 0.0)
    growth = np.where(primary_ok.fillna(False), growth_primary, growth_short.fillna(0.0))
    growth = pd.Series(growth, index=cid_idx)

    # 增长率钳制（与产品生命周期v2.9一致）；NaN 语义与原版 max/min 一致 → 落到下界
    from config.settings import PRODUCT_LIFECYCLE
    _rev_lo = PRODUCT_LIFECYCLE.get("rev_growth_lower", -1.0)
    _rev_hi = PRODUCT_LIFECYCLE.get("rev_growth_upper", 5.0)
    growth = np.clip(np.nan_to_num(growth, nan=_rev_lo), _rev_lo, _rev_hi)

    # YoY 同比增速：当前12月 vs 前12月（需24月数据）
    yr_count = _ser(a_yr["_cnt"])
    yr_sum = _ser(a_yr["rev_sum"])
    yr_mean = _ser(a_yr["_mean"])
    yoy_ok = (yr_count >= 2) & (yr_sum > 0)
    yr_recent_avg = r_mean.where(r_count > 0, 0.0)
    yoy = ((yr_recent_avg - yr_mean) / yr_mean).where(yoy_ok, 0.0)

    # 连续增长/下滑月数（状态机等价于逐月循环，向量化实现）
    growth_tolerance = 1 - float(CUSTOMER_THRESHOLDS.get("growth_streak_tolerance", 0.05))
    streak_up, streak_down = _vec_streaks(recent, cid_idx, growth_tolerance)

    out = pd.DataFrame(index=cid_idx)
    out[rev_col] = recent_rev.astype("float32")
    out[profit_col] = recent_profit.astype("float32")
    out["近12月毛利率"] = (recent_profit / recent_rev * 100).where(recent_rev > 0, 0.0).astype("float64")
    out[f"前{_growth_win}月收入"] = prior_rev.astype("float32")
    out["近12月数量"] = recent_qty.astype("float32")
    out["订单数"] = orders
    out["收入增长率"] = growth.astype("float64")
    out["ASP_加权"] = (recent_rev / recent_qty).where(recent_qty > 0, 0.0).astype("float64")
    out["连续增长月数"] = streak_up
    out["连续下滑月数"] = streak_down
    out["YoY同比增速"] = yoy.astype("float64")
    return out


def _vec_product_coverage(cid_idx, cust_prod):
    """向量化产品覆盖：等价于对每个客户执行 _dim_product_coverage()。"""
    out = pd.DataFrame(index=cid_idx)
    out["品种集中度Top3"] = 0.0
    out["品种总数"] = 0
    if cust_prod is None or len(cust_prod) == 0 or "产品品种" not in cust_prod.columns:
        return out

    rev = cust_prod.groupby(["客户编号", "产品品种"], observed=True)["rev_sum"].sum()
    if len(rev) == 0:
        return out

    # 品种总数 = 每客户不重复品种数（与原 len(top_products) 一致，NaN 品种被 groupby 排除）
    out["品种总数"] = rev.groupby("客户编号", observed=True).size().reindex(cid_idx).fillna(0).astype("int64")

    total = rev.groupby("客户编号", observed=True).sum()
    # Top3：每客户 rev 降序稳定排序后取前3求和（与原 sort_values(desc, stable).head(3) 一致）
    rev_df = rev.reset_index(name="v")
    rev_df = rev_df.sort_values(["客户编号", "v"], ascending=[True, False], kind="stable")
    top3 = rev_df.groupby("客户编号", observed=True).head(3).groupby("客户编号", observed=True)["v"].sum()

    total_idx = total.reindex(cid_idx).fillna(0)
    top3_idx = top3.reindex(cid_idx).fillna(0)
    out["品种集中度Top3"] = (top3_idx / total_idx).where(total_idx > 0, 0.0).astype("float64")
    return out


def _vec_product_line_distribution(cid_idx, cust_prod, cat_col, cat_detail_col=None):
    """向量化产品线分布：等价于对每个客户执行 _dim_product_line_distribution()。

    Phase 0 fix: 新增"实际品类数"从 cat_detail_col 聚合（"产品一级分类"恒=12无区分度）。
    """
    out = pd.DataFrame(index=cid_idx)
    out["实际品类数"] = 0
    if cust_prod is None or len(cust_prod) == 0:
        out["产品线数"] = 0
        out["主导产品线"] = "数据缺失"
        out["主导产品线占比"] = 0.0
        out["产品线HHI"] = 1.0
        return out

    detail_line = cat_detail_col or cat_col
    if detail_line in cust_prod.columns:
        detail_cnt = cust_prod.groupby("客户编号", observed=True)[detail_line].nunique()
        out["实际品类数"] = detail_cnt.reindex(cid_idx).fillna(0).astype("int64")

    if cat_col not in cust_prod.columns:
        out["产品线数"] = 0
        out["主导产品线"] = "数据缺失"
        out["主导产品线占比"] = 0.0
        out["产品线HHI"] = 1.0
        return out

    rev_s = cust_prod.groupby(["客户编号", cat_col], observed=True)["rev_sum"].sum()
    if len(rev_s) == 0:
        out["产品线数"] = 0
        out["主导产品线"] = "无"
        out["主导产品线占比"] = 0.0
        out["产品线HHI"] = 1.0
        return out

    line_total = rev_s.groupby("客户编号", observed=True).sum().reindex(cid_idx).fillna(0)
    line_cnt = rev_s.groupby("客户编号", observed=True).size().reindex(cid_idx).fillna(0)

    # 每行占比：分母为每客户线收入合计（对 [客户编号, cat_col] 排序后逐组 Series.sum，与逐客户版逐位一致）
    # [批次⑤ 缺陷B修复] CategoricalIndex.map() 在 pandas≥2.3.2 下保留 category dtype，
    # 直接相除会抛 "Object with dtype category cannot perform the numpy op divide"。
    # 这里只需要逐位置的分母数值，显式转 float64 ndarray（值与原 map 结果完全一致，
    # 分母仍按 rev_s 行序对齐，计算结果零变化）。
    tot_map = np.asarray(
        rev_s.index.get_level_values(0).map(rev_s.groupby("客户编号", observed=True).sum()),
        dtype="float64",
    )
    shares = rev_s / tot_map

    # 主导产品线：groupby 内 idxmax 返回 MultiIndex 标签 (客户编号, cat_col)，
    # 取第 2 级即品类名（并列时取字典序最小，与原 line_rev.idxmax() 一致）
    dom_label = rev_s.groupby("客户编号", observed=True).idxmax()
    dom_cat = pd.Series([t[1] for t in dom_label], index=dom_label.index, dtype=object)
    dom_cat = dom_cat.reindex(cid_idx).fillna("无")

    max_share = shares.groupby("客户编号", observed=True).max().reindex(cid_idx).fillna(0)
    hhi = (shares ** 2).groupby("客户编号", observed=True).sum().reindex(cid_idx).fillna(1.0)

    positive = line_total > 0
    out["产品线数"] = np.where(positive, line_cnt, 0).astype("int64")
    out["主导产品线"] = np.where(positive, dom_cat, "无")
    out["主导产品线占比"] = np.where(positive, max_share, 0.0).astype("float64")
    out["产品线HHI"] = np.where(positive, hhi, 1.0).astype("float64")
    return out



def _vec_merge_batch_fields(cid_idx, idx_metrics):
    """向量化合并批量计算字段：等价于对每个客户执行 _merge_batch_fields_fast()。"""
    merge_specs = [
        ("intervals", ["常规平均采购间隔"]),
        ("churn", ["距上次采购天数", "采购中断预警"]),
        ("concentration", ["Top5集中度", "强依赖标记", "总采购额"]),
        ("price_bands", ["低价品种收入占比", "中价品种收入占比", "高价品种收入占比"]),
        ("category_acc", ["主导品类", "主导品类占比", "品类机会标签"]),
        ("cust_stages", ["客户生命周期"]),
        ("new_prod_cohort", ["新品采购额", "新品品种数", "新品采购占比", "是否采购新品"]),
        ("opp_signals", ["新品渗透机会", "增长动量"]),
        ("risk_signals", ["品种流失金额占比", "近半年营收跌幅"]),
    ]
    parts = []
    for key, fields in merge_specs:
        idx_df = idx_metrics.get(key)
        if idx_df is None:
            continue
        # 原版逐客户合并的 dtype 语义：
        #   客户在框内（含 float32 NaN 值）→ 保持 float32；
        #   客户不在框内（.loc 抛 KeyError → 该字段缺失）→ pd.DataFrame 会将 float32+缺失 提升为 float64
        missing = len(idx_df) < len(cid_idx)
        for f in fields:
            if f in idx_df.columns:
                col = idx_df[f].reindex(cid_idx).rename(f)
                if missing and pd.api.types.is_float_dtype(col):
                    col = col.astype("float64")
                parts.append(col)
    if not parts:
        return pd.DataFrame(index=cid_idx)
    return pd.concat(parts, axis=1)


def _vec_sku_dominant_stage(cid_idx, cust_prod, sku_stage_map):
    """向量化SKU阶段：等价于对每个客户执行 _dim_sku_dominant_stage_fast()。"""
    out = pd.DataFrame(index=cid_idx)
    out["主要SKU阶段"] = "未知"
    if not sku_stage_map or cust_prod is None or len(cust_prod) == 0 or "产品品种" not in cust_prod.columns:
        return out

    uniq = cust_prod[["客户编号", "产品品种"]].drop_duplicates()
    uniq = uniq.assign(_stage=uniq["产品品种"].map(sku_stage_map))
    uniq = uniq[uniq["_stage"].notna()]
    if len(uniq) == 0:
        return out

    # 每客户取众数；并列时取字典序最小（与原 pd.Series(c_stages).mode().iloc[0] 一致）
    cnt = uniq.groupby(["客户编号", "_stage"], observed=True).size().reset_index(name="c")
    cnt = cnt.sort_values(["客户编号", "c", "_stage"], ascending=[True, False, True], kind="stable")
    dom = cnt.groupby("客户编号", observed=True)["_stage"].first()
    out["主要SKU阶段"] = dom.reindex(cid_idx).fillna("未知")
    return out


def _vec_asp_comparison(asp_series, global_asp_all, cap):
    """向量化ASP对比：等价于对每个客户执行 _dim_asp_comparison_fast()。

    与原版一致采用 float32 运算（ASP_加权 与 global 均为 float32）。
    """
    out = pd.DataFrame(index=asp_series.index)
    if global_asp_all > 0:
        drop = (asp_series.astype("float32") - global_asp_all) / global_asp_all * 100
    else:
        drop = pd.Series(0.0, index=asp_series.index)
    out["ASP_跌幅%"] = np.clip(drop, -cap, cap).astype("float64")
    return out


def _vec_margin_trend(cust_monthly, cur_margin_series, latest_month):
    """向量化毛利率跌幅%：等价于对每个客户执行 _dim_margin_trend()。

    近N月 vs 前N月毛利率变化，窗口长度来自 settings.py:CUSTOMER_ANALYSIS_WINDOW。
    """
    _win = CUSTOMER_ANALYSIS_WINDOW.get("value_window_months", 12)
    m = cust_monthly
    cid_idx = cur_margin_series.index
    is_prior = (m["_月"] <= (latest_month - _win)) & (m["_月"] > (latest_month - _win * 2))
    prior = m[is_prior]

    # 精确逐组求和（与逐客户版 Series.sum() 逐位一致，按[客户编号,_月]排序）
    prior_profit_d = {}
    prior_rev_d = {}
    if len(prior) > 0:
        prior = prior.sort_values(["客户编号", "_月"], kind="stable")
        for cid, grp in prior.groupby("客户编号", sort=False, observed=True):
            prior_profit_d[cid] = grp["profit_clip_sum"].sum()
            prior_rev_d[cid] = grp["rev_sum"].sum()
    prior_profit = pd.Series(prior_profit_d).reindex(cid_idx).fillna(0)
    prior_rev = pd.Series(prior_rev_d).reindex(cid_idx).fillna(0)
    prior_margin = (prior_profit / prior_rev).where(prior_rev > 0, 0.0)

    # 与原版一致采用 float32 运算（近12月毛利率/100 与 prior_margin 均为 float32）
    cur_margin = cur_margin_series.astype("float32") / 100
    out = pd.DataFrame(index=cid_idx)
    drop = (cur_margin - prior_margin) / prior_margin * 100
    out["毛利率跌幅%"] = drop.where(prior_margin > 0, 0.0).astype("float64")
    return out


# ============================================================
# 主入口
# ============================================================

def calc_customer_portrait(silver: dict, source_path: str, latest_month,
                          raw_data: pd.DataFrame = None,
                          cust_info_df: pd.DataFrame = None) -> pd.DataFrame:
    """计算客户全景画像（每客户一行，60+列）。

    参数:
        silver: Silver层数据字典（customer_monthly, customer_x_product, product_monthly）
        source_path: 源Excel路径（用于读取客户信息表）
        latest_month: 最新月份（Period对象）
        raw_data: 原始交易数据（可选，避免重读Excel）
        cust_info_df: 客户信息表DataFrame（可选，避免重读Excel）

    返回:
        DataFrame: 每客户一行，包含基本信息、经营势能、产品覆盖等60+指标
    """
    cust_monthly = silver["customer_monthly"].copy()
    cust_prod = silver["customer_x_product"].copy()
    prod_monthly = silver["product_monthly"].copy()

    cat_col = CUSTOMER_COL_MAP.get("品类列", "产品一级分类")
    cat_sub_col = CUSTOMER_COL_MAP.get("品类细分列", "型号_产品品类")
    # ★ Phase 0 fix: 产品线数从"型号_产品品类"聚合（"产品一级分类"恒=12无区分度）
    cat_detail_col = cat_sub_col if cat_sub_col in cust_prod.columns else cat_col

    # 加载客户信息表（优先使用传入的DataFrame，避免重读Excel）
    if cust_info_df is not None and not cust_info_df.empty:
        cust_info = cust_info_df
    else:
        try:
            cust_info = read_excel_auto(source_path, sheet_name="客户信息表")
        except (ValueError, FileNotFoundError):
            cust_info = pd.DataFrame({"客户编号": cust_monthly["客户编号"].unique()})

    customers = cust_monthly["客户编号"].unique()
    cid_idx = pd.Index(customers)

    # 从原始交易数据映射客户属性（回退补充；向量化预计算，等价于原 _attr_map 构建）
    attr_region = None
    attr_owner = None
    if raw_data is not None and len(raw_data) > 0:
        if "销售部门" in raw_data.columns:
            _dept = raw_data.groupby("客户编号")["销售部门"].first()
            attr_region = _dept.map(lambda d: DEPT_REGION_MAP.get(str(d).strip(), "未知")).reindex(cid_idx).fillna("未知")
        if "实际业务员" in raw_data.columns:
            attr_owner = raw_data.groupby("客户编号")["实际业务员"].first().reindex(cid_idx).fillna("未知")

    # ---- 批量计算 ----
    metrics = _compute_batch_metrics(cust_monthly, cust_prod, prod_monthly, latest_month, cat_sub_col)

    # ---- 预计算不依赖于单个客户的值 ----
    # 全局ASP（所有产品近N月加权均价）
    _win_asp = CUSTOMER_ANALYSIS_WINDOW.get("value_window_months", 12)
    _prod_recent = prod_monthly[prod_monthly["_月"] > (latest_month - _win_asp)]
    _global_asp_all = (_prod_recent["rev_sum"].sum() / _prod_recent["qty_sum"].sum()
                       if _prod_recent["qty_sum"].sum() > 0 else 0)
    _asp_cap = METRIC_CAPS.get("asp_decline_max_pct", 100)

    # 预建立SKU阶段映射（产品->阶段）
    _sku_stage_map = {}
    if "sku_stages" in metrics and "产品品种" in metrics["sku_stages"].columns:
        _sku_stage_df = metrics["sku_stages"]
        if "SKU生命周期阶段" in _sku_stage_df.columns:
            _sku_stage_map = _sku_stage_df.set_index("产品品种")["SKU生命周期阶段"].to_dict()

    # 预索引批处理DataFrame
    _idx_metrics = {}
    for _key in ["intervals", "churn", "concentration", "price_bands",
                 "category_acc", "cust_stages", "new_prod_cohort",
                 "opp_signals", "risk_signals"]:
        if _key in metrics and "客户编号" in metrics[_key].columns:
            _idx_metrics[_key] = metrics[_key].set_index("客户编号")

    # ---- 向量化计算各维度（等价于原逐客户循环，一次 groupby 完成全部客户） ----
    base = _vec_base_info(cid_idx, cust_info, raw_data, attr_region, attr_owner)
    mom = _vec_momentum(cust_monthly, latest_month)
    cov = _vec_product_coverage(cid_idx, cust_prod)
    pline = _vec_product_line_distribution(cid_idx, cust_prod, cat_col, cat_detail_col)
    batch = _vec_merge_batch_fields(cid_idx, _idx_metrics)
    sku = _vec_sku_dominant_stage(cid_idx, cust_prod, _sku_stage_map)
    asp = _vec_asp_comparison(mom["ASP_加权"], _global_asp_all, _asp_cap)
    mtrend = _vec_margin_trend(cust_monthly, mom["近12月毛利率"], latest_month)

    result_df = pd.concat([base, mom, cov, pline, batch, sku, asp, mtrend], axis=1)
    result_df.insert(0, "客户编号", result_df.index.astype(object))
    result_df = result_df.reset_index(drop=True)
    return result_df
