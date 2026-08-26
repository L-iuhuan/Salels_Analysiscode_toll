"""
客户产品洞察模块 — 为6策略引擎提供产品级深度分析数据。

功能：
  1. 每个客户的Top产品（按收入/利润/负毛利）
  2. 利润率担当 vs 利润率拖累产品识别
  3. 产品级月度变化（用于风控：识别哪个产品下降导致衰退）
  4. 历史辉煌产品（用于激活试探）
  5. 品类拓展推荐（FAE视角）

所有函数返回dict，key=客户编号。
"""

import pandas as pd
import numpy as np


def build_customer_product_profiles(
    customer_x_product: pd.DataFrame,
    customer_portrait: pd.DataFrame = None,
    silver: dict = None,
) -> dict:
    """构建每个客户的产品级深度画像。

    返回:
        dict[客户编号] = {
            "top5_by_revenue": [(产品, 收入, 毛利率), ...],
            "margin_stars": [(产品, 利润, 毛利率), ...],    # 利润贡献最大的
            "margin_drains": [(产品, 亏损额, 毛利率), ...], # 负毛利拖累
            "top1_product": (产品, 收入, 收入占比),
            "overall_margin": float,
            "product_count": int,
            "dominant_line": str,
        }
    """
    cxp = customer_x_product.copy()
    cust_col = "客户编号"
    prod_col = "产品品种"
    rev_col = "rev_sum" if "rev_sum" in cxp.columns else "金额"
    profit_col = "profit_clip_sum" if "profit_clip_sum" in cxp.columns else "_利润_裁剪"

    # 批次②.5车道B：原"逐客户 groupby 产品聚合"改为向量化。
    # 注意：原实现对 categorical 产品列 groupby 默认 observed=False，展开"客户×全部产品类别"
    # 的叉积（未采购产品 total_rev=0，product_count=全部类别数，top5 含 0 收入占位品）。
    # 用 reindex 复现同样的叉积（含 0 占位），逐值等价（含 float32 求和顺序）。
    actual = cxp.groupby([cust_col, prod_col], observed=True)[[rev_col, profit_col]].sum()
    if isinstance(cxp[cust_col].dtype, pd.CategoricalDtype):
        all_cids = list(cxp[cust_col].cat.categories)
    else:
        all_cids = list(actual.index.get_level_values(0).unique())
    if isinstance(cxp[prod_col].dtype, pd.CategoricalDtype):
        all_prods = sorted(cxp[prod_col].cat.categories)  # 与原 groupby 默认 sort=True 一致
    else:
        all_prods = sorted(actual.index.get_level_values(1).unique())
    full_index = pd.MultiIndex.from_product([all_cids, all_prods], names=[cust_col, prod_col])
    prod_agg = actual.reindex(full_index).fillna(0)
    prod_agg = prod_agg.rename(columns={rev_col: "total_rev", profit_col: "total_profit"})
    prod_agg["margin_pct"] = np.where(
        prod_agg["total_rev"] > 0,
        prod_agg["total_profit"] / prod_agg["total_rev"] * 100,
        0
    )

    # 客户级合计：与原逐客户 prod_agg["total_rev"].sum()（Series.sum 按产品名排序全量求和）逐位一致
    cust_rev = {c: g["total_rev"].sum() for c, g in prod_agg.groupby(cust_col, sort=False, observed=True)}
    cust_profit = {c: g["total_profit"].sum() for c, g in prod_agg.groupby(cust_col, sort=False, observed=True)}
    cust_agg = pd.DataFrame({"total_rev": cust_rev, "total_profit": cust_profit})
    cust_agg["overall_margin"] = np.where(
        cust_agg["total_rev"] > 0,
        cust_agg["total_profit"] / cust_agg["total_rev"] * 100,
        0
    ).round(1)
    cust_agg["product_count"] = len(all_prods)

    # Top5 by revenue（每客户 rev 降序稳定；并列保持产品名顺序——等价于对全量叉积 nlargest(5)）
    top5_df = (prod_agg.reset_index()
               .sort_values([cust_col, "total_rev"], ascending=[True, False], kind="stable")
               .groupby(cust_col, observed=True).head(5))
    # Margin stars（利润>0，按利润降序）
    star_df = (prod_agg[prod_agg["total_profit"] > 0].reset_index()
               .sort_values([cust_col, "total_profit"], ascending=[True, False], kind="stable")
               .groupby(cust_col, observed=True).head(5))
    # Margin drains（利润<0，按利润升序=最负优先）
    drain_df = (prod_agg[prod_agg["total_profit"] < 0].reset_index()
                .sort_values([cust_col, "total_profit"], ascending=[True, True], kind="stable")
                .groupby(cust_col, observed=True).head(5))

    # 主导产品线：复现原版 grp.groupby(cat_col) observed=False 的完整 line_rev（未采购类别=0.0）。
    # idxmax 在客户收入<=0 时返回排序后第一个 0.0 类别；空客户组同样得到第一个类别。
    cat_col = None
    for c in cxp.columns:
        if c in ("产品一级分类", "型号_产品品类"):
            cat_col = c
            break
    dominant = pd.Series(dtype=object)
    all_nan_cats = set()  # 客户有行但 cat 全 NaN → 原版 line_rev 为空 → 主导为空串
    if cat_col:
        line_rev = cxp.groupby([cust_col, cat_col], observed=True)[rev_col].sum()
        if isinstance(cxp[cat_col].dtype, pd.CategoricalDtype):
            all_cats = sorted(cxp[cat_col].cat.categories)
        else:
            all_cats = sorted(line_rev.index.get_level_values(1).unique())
        full_cat = pd.MultiIndex.from_product([all_cids, all_cats], names=[cust_col, cat_col])
        line_rev_full = line_rev.reindex(full_cat).fillna(0)
        dom_label = line_rev_full.groupby(cust_col, observed=True).idxmax()
        dominant = pd.Series([t[1] for t in dom_label], index=dom_label.index, dtype=object)
        in_line = set(line_rev.index.get_level_values(0).unique())
        present_cids = set(cxp[cust_col].unique())
        all_nan_cats = present_cids - in_line

    profiles = {}
    top5_by_cid = {c: g for c, g in top5_df.groupby(cust_col, sort=False, observed=True)}
    star_by_cid = {c: g for c, g in star_df.groupby(cust_col, sort=False, observed=True)}
    drain_by_cid = {c: g for c, g in drain_df.groupby(cust_col, sort=False, observed=True)}
    empty_slice = top5_df.iloc[0:0]
    for cid in all_cids:
        if cid not in cust_agg.index:
            profiles[cid] = {
                "top5_by_revenue": [], "margin_stars": [], "margin_drains": [],
                "top1_product": ("无", 0, 0), "overall_margin": 0,
                "total_revenue": 0, "total_profit": 0, "product_count": 0,
                "dominant_line": "",
            }
            continue
        # 用 .at 直接取原始标量（cust_agg.loc 行会因混合列 dtype 被提升为 float64）
        total_rev = cust_agg.at[cid, "total_rev"]
        total_profit = cust_agg.at[cid, "total_profit"]

        top5_list = [
            (r[prod_col], r["total_rev"], r["margin_pct"])
            for _, r in top5_by_cid.get(cid, empty_slice).iterrows()
        ]
        margin_stars = [
            (r[prod_col], r["total_profit"], r["margin_pct"])
            for _, r in star_by_cid.get(cid, empty_slice).iterrows()
        ]
        margin_drains = [
            (r[prod_col], r["total_profit"], r["margin_pct"])
            for _, r in drain_by_cid.get(cid, empty_slice).iterrows()
        ]

        if len(top5_list) > 0:
            top1 = top5_list[0]
            top1_share = top1[1] / total_rev if total_rev > 0 else 0
            top1_info = (top1[0], top1[1], top1_share)
        else:
            top1_info = ("无", 0, 0)

        # 客户有行但 cat 全 NaN → 原版 line_rev 空 → 主导为空串；其余取完整 line_rev 的 idxmax
        if cid in all_nan_cats:
            dominant_line = ""
        else:
            dominant_line = str(dominant.get(cid, "")) if len(dominant) else ""

        profiles[cid] = {
            "top5_by_revenue": top5_list,
            "margin_stars": margin_stars,
            "margin_drains": margin_drains,
            "top1_product": top1_info,
            "overall_margin": cust_agg.at[cid, "overall_margin"],
            "total_revenue": total_rev,
            "total_profit": total_profit,
            "product_count": int(cust_agg.at[cid, "product_count"]),
            "dominant_line": dominant_line,
        }

    return profiles


def build_monthly_product_trend(
    customer_x_product: pd.DataFrame,
) -> dict:
    """构建客户×产品月度趋势数据（用于风控：定位下降产品）。

    返回:
        dict[客户编号] = {
            "declining_products": [(产品, 近3月跌幅%, 损失额), ...],
            "decline_months_detail": int,  # 连续下降月数
        }

    批次②.5车道B：原"逐客户×逐产品 isin+sum"双重循环（每客户每月每产品多次
    boolean mask + Period isin，实测 536s）改为一次 groupby 向量化，输出逐值等价。
    """
    cxp = customer_x_product.copy()
    if "_月" not in cxp.columns:
        return {}

    cust_col = "客户编号"
    prod_col = "产品品种"
    rev_col = "rev_sum" if "rev_sum" in cxp.columns else "金额"
    profit_col = "profit_clip_sum" if "profit_clip_sum" in cxp.columns else "_利润_裁剪"

    # 每客户月份密集排名（0=最早）与客户总月数；仅保留 ≥4 个月的客户
    cxp = cxp.sort_values([cust_col, "_月"], kind="stable")
    cxp = cxp.assign(
        _rank=cxp.groupby(cust_col, sort=False)["_月"].rank(method="dense") - 1,
        _M=cxp.groupby(cust_col, sort=False)["_月"].transform("nunique"),
    )
    cxp = cxp[cxp["_M"] >= 4]
    if len(cxp) == 0:
        return {}

    # recent_3 = 月末3个月（rank >= M-3）；prior_3 = 其前3个月（rank in [M-6, M-3)）
    is_recent = cxp["_rank"] >= cxp["_M"] - 3
    is_prior = (cxp["_rank"] >= cxp["_M"] - 6) & (cxp["_rank"] < cxp["_M"] - 3)

    recent_sum = cxp.loc[is_recent].groupby([cust_col, prod_col], observed=True)[rev_col].sum()
    prior_sum = cxp.loc[is_prior].groupby([cust_col, prod_col], observed=True)[rev_col].sum()
    # 与原逐产品 Series.sum 逐位一致（groupby 内部约简在 float32 下差 1ULP，
    # 会导致 round(跌幅,1)/round(损失,0) 在 .5 边界翻差）
    recent_sum = pd.Series({k: g[rev_col].sum()
                            for k, g in cxp.loc[is_recent].groupby([cust_col, prod_col], sort=False, observed=True)})
    prior_sum = pd.Series({k: g[rev_col].sum()
                           for k, g in cxp.loc[is_prior].groupby([cust_col, prod_col], sort=False, observed=True)})
    recent_sum.index = pd.MultiIndex.from_tuples(recent_sum.index, names=[cust_col, prod_col])
    prior_sum.index = pd.MultiIndex.from_tuples(prior_sum.index, names=[cust_col, prod_col])
    pair = pd.concat([recent_sum.rename("recent"), prior_sum.rename("prior")], axis=1).fillna(0)
    if len(pair) == 0:
        return {}

    pair = pair[(pair["prior"] > 0) & (pair["recent"] < pair["prior"])]
    if len(pair) == 0:
        return {}
    pair["decline_pct"] = (pair["recent"] - pair["prior"]) / pair["prior"] * 100
    pair["loss"] = pair["prior"] - pair["recent"]
    pair = pair[pair["decline_pct"] < -20]
    if len(pair) == 0:
        return {}
    pair["decline_pct"] = pair["decline_pct"].round(1)
    pair["loss"] = pair["loss"].round(0)
    # 每客户按跌幅升序（最负优先）；同跌幅保持产品名顺序（原版 grp.groupby(prod_col) 默认排序）
    pair = pair.sort_index()  # 先把 (客户,产品) 索引排成产品名顺序，保证并列跌幅的稳定排序
    pair = pair.sort_values([cust_col, "decline_pct"], kind="stable")

    # 每客户 recent_3/prior_3 月份（字符串；observed=True 只保留有数据的客户）
    m_df = cxp[["客户编号", "_月"]].drop_duplicates().sort_values(["客户编号", "_月"], kind="stable")
    m_rank = m_df.groupby("客户编号", sort=False, observed=True).cumcount()
    m_M = m_df.groupby("客户编号", sort=False, observed=True)["_月"].transform("size")
    recent_m = (m_df[m_rank >= m_M - 3]
                .groupby("客户编号", sort=False, observed=True)["_月"].agg(list)
                .map(lambda x: [str(m) for m in x]))
    prior_m = (m_df[(m_rank >= m_M - 6) & (m_rank < m_M - 3)]
               .groupby("客户编号", sort=False, observed=True)["_月"].agg(list)
               .map(lambda x: [str(m) for m in x]))

    # 每客户下降产品列表（已按跌幅升序）
    decl_by_cust = {}
    for cid, grp in pair.groupby(cust_col, sort=False):
        decl_by_cust[cid] = list(zip(grp.index.get_level_values(prod_col),
                                     grp["decline_pct"], grp["loss"]))[:5]

    trends = {}
    for cid in recent_m.index:
        trends[cid] = {
            "declining_products": decl_by_cust.get(cid, []),
            "recent_3_months": recent_m[cid],
            "prior_3_months": prior_m[cid],
        }
    return trends


def build_historical_glory(
    customer_monthly: pd.DataFrame,
    customer_x_product: pd.DataFrame = None,
) -> dict:
    """查找客户的历史辉煌期（用于激活试探）。

    返回:
        dict[客户编号] = {
            "glory_product": str,        # 历史上最大的产品
            "glory_revenue": float,      # 峰值年收入
            "glory_profit": float,       # 峰值年利润
            "glory_margin": float,       # 峰值毛利率
            "glory_period": str,         # 辉煌期
        }
    """
    cm = customer_monthly.copy()
    if "_月" not in cm.columns:
        return {}

    cm = cm.sort_values(["_月"], kind='stable')
    cust_col = "客户编号"

    glories = {}
    for cid, grp in cm.groupby(cust_col):
        if len(grp) < 6:
            continue

        # Find peak 12-month rolling window
        months = sorted(grp["_月"].unique())
        best_rev = 0
        best_profit = 0
        best_period = ""

        rev_col = "rev_sum" if "rev_sum" in grp.columns else "金额"
        profit_col = "profit_clip_sum" if "profit_clip_sum" in grp.columns else "_利润_裁剪"

        # [批次⑥ P4] customer_monthly 每客户每月一行（groupby 聚合产物），
        # months[i:i+12] 窗口与 grp.iloc[i:i+12] 完全等价（同序同值）；
        # 窗口求和用 ndarray 切片 .sum() —— 与原 w[rev_col].sum() 同为
        # np.add.reduce 同一实现同一顺序，逐位一致；
        # 替代原"每窗口 grp[grp["_月"].isin(window)] 全组掩码扫描"（57K 次）。
        rev_arr = grp[rev_col].to_numpy(dtype="float64", na_value=np.nan)
        profit_arr = grp[profit_col].to_numpy(dtype="float64", na_value=np.nan)
        if np.isnan(rev_arr).any() or np.isnan(profit_arr).any():
            # 兜底：含 NaN 时回到原 isin 路径（Series.sum 默认 skipna，与 ndarray.sum 语义不同）
            for i in range(len(months) - 11):
                window = months[i:i+12]
                w = grp[grp["_月"].isin(window)]
                rev = w[rev_col].sum()
                profit = w[profit_col].sum()
                if rev > best_rev:
                    best_rev = rev
                    best_profit = profit
                    best_period = f"{window[0]}~{window[-1]}"
        else:
            for i in range(len(months) - 11):
                window = months[i:i+12]
                rev = rev_arr[i:i+12].sum()
                profit = profit_arr[i:i+12].sum()
                if rev > best_rev:
                    best_rev = rev
                    best_profit = profit
                    best_period = f"{window[0]}~{window[-1]}"

        if best_rev > 0:
            margin = best_profit / best_rev * 100 if best_rev > 0 else 0
            glories[cid] = {
                "glory_revenue": round(best_rev, 0),
                "glory_profit": round(best_profit, 0),
                "glory_margin": round(margin, 1),
                "glory_period": best_period,
            }

    # Add top product info if available
    if customer_x_product is not None:
        cxp = customer_x_product.copy()
        prod_col = "产品品种"
        rev_col = "rev_sum" if "rev_sum" in cxp.columns else "金额"
        profit_col = "profit_clip_sum" if "profit_clip_sum" in cxp.columns else "_利润_裁剪"
        # [批次⑥ P4] 按客户一次性预分组，替代"每客户 cxp[cxp[cust_col]==cid] 全表布尔扫描"
        # （glories 客户×151K行 object 比较，是本函数最大耗时；组内行序一致 →
        # groupby(prod_col) 聚合与 idxmax 结果逐位一致）
        _cxp_by_cust = {k: g for k, g in cxp.groupby(cust_col, sort=False)}
        for cid in glories:
            cgrp = _cxp_by_cust.get(cid)
            if cgrp is not None and len(cgrp) > 0:
                prod_rev = cgrp.groupby(prod_col)[rev_col].sum()
                if len(prod_rev) > 0:
                    top_prod = prod_rev.idxmax()
                    top_rev = prod_rev.max()
                    glories[cid]["glory_product"] = str(top_prod)
                    glories[cid]["glory_product_rev"] = round(top_rev, 0)

    return glories


def label_product(name: str, rev: float, margin_pct: float, overall_margin: float) -> str:
    """给产品打标签：利润担当/销量担当/利润拖累。"""
    if margin_pct < 0:
        return "利润拖累"
    if margin_pct > overall_margin * 1.3:
        return "利润担当"
    if rev > 0 and margin_pct > 0:
        return "销量担当"
    return "一般"


def format_ka_product_detail(profile: dict, top_n: int = 5) -> str:
    """格式化KA/AA客户的产品逐项分析。"""
    if not profile:
        return ""
    top5 = profile.get("top5_by_revenue", [])
    overall_m = profile.get("overall_margin", 0)
    total_rev = profile.get("total_revenue", 1)

    if not top5:
        return "  · 无产品数据"

    lines = []
    for p in top5[:top_n]:
        name, rev, margin = p[0], p[1], p[2]
        share = rev / total_rev * 100 if total_rev > 0 else 0
        label = label_product(name, rev, margin, overall_m)
        lines.append(f"  · {name}：¥{rev/10000:.1f}万（占比{share:.0f}%，毛利率{margin:.1f}%）→ {label}")
    return "\n".join(lines)


def get_margin_drain_product(profile: dict) -> dict:
    """找出最拖累毛利率的产品。"""
    top5 = profile.get("top5_by_revenue", [])
    total_rev = profile.get("total_revenue", 1)
    overall_m = profile.get("overall_margin", 0)
    # Find high-revenue, low-margin product
    worst = None
    worst_impact = 0
    for p in top5:
        name, rev, margin = p[0], p[1], p[2]
        if margin < overall_m:
            impact = (overall_m - margin) * rev / total_rev  # pp drag
            if impact > worst_impact:
                worst_impact = impact
                worst = {"name": name, "rev": rev, "margin": margin, "share": rev/total_rev*100, "drag_pp": impact}
    return worst or {}


def get_margin_star_product(profile: dict) -> dict:
    """找出利润率担当产品（毛利额最高且毛利率>整体均值）。"""
    top5 = profile.get("top5_by_revenue", [])
    total_profit = profile.get("total_profit", 0)
    overall_m = profile.get("overall_margin", 0)
    best = None
    best_profit = 0
    for p in top5:
        name, rev, margin = p[0], p[1], p[2]
        profit = rev * margin / 100
        if profit > best_profit and margin > overall_m:
            best_profit = profit
            best = {"name": name, "rev": rev, "margin": margin, "profit": profit, "profit_share": profit/total_profit*100 if total_profit else 0}
    return best or {}


def format_product_list(products: list, top_n: int = 5) -> str:
    """格式化产品列表为字符串。"""
    if not products:
        return "无数据"
    items = []
    for p in products[:top_n]:
        name = str(p[0])
        if len(p) >= 3:
            items.append(f"{name}(¥{p[1]/10000:.1f}万,毛利率{p[2]:.1f}%)")
        else:
            items.append(f"{name}(¥{p[1]/10000:.1f}万)")
    return "、".join(items)


def analyze_margin_structure(profile: dict, deep_binding_profiles: dict = None, cid: str = None) -> dict:
    """分析客户利润率结构。

    返回:
        {
            "margin_vs_peers": str,        # "高于"/"低于"/"持平" 同类客户
            "margin_drain_product": str,    # 最拖累利润率的产品
            "margin_star_product": str,     # 利润率担当产品
            "top5_share": float,            # Top5产品收入占比
            "top5_list_str": str,           # Top5产品格式化字符串
            "drain_detail": str,            # 拖累产品详情
            "star_detail": str,             # 担当产品详情
        }
    """
    result = {}

    # Top 5 share
    top5 = profile.get("top5_by_revenue", [])
    total_rev = profile.get("total_revenue", 1)
    top5_rev = sum(p[1] for p in top5)
    result["top5_share"] = round(top5_rev / total_rev * 100, 1) if total_rev > 0 else 0
    result["top5_list_str"] = format_product_list(top5)

    # Margin comparison with peers — fixed: use cid as key, not profile dict object
    if deep_binding_profiles and cid and cid in deep_binding_profiles:
        peer_margins = [
            p.get("overall_margin", 0)
            for pid, p in deep_binding_profiles.items()
            if pid != cid  # exclude self
        ]
        if peer_margins:
            peer_median = sorted(peer_margins)[len(peer_margins)//2]
            my_margin = profile.get("overall_margin", 0)
            if my_margin > peer_median * 1.1:
                result["margin_vs_peers"] = "高于"
            elif my_margin < peer_median * 0.9:
                result["margin_vs_peers"] = "低于"
            else:
                result["margin_vs_peers"] = "持平"
        else:
            result["margin_vs_peers"] = "无法比较"
    else:
        result["margin_vs_peers"] = "无法比较"

    # Margin drain (#1 negative profit product)
    drains = profile.get("margin_drains", [])
    if drains:
        d = drains[0]
        result["margin_drain_product"] = str(d[0])
        result["drain_detail"] = f"{d[0]}(亏损¥{abs(d[1]):.0f},毛利率{d[2]:.1f}%)"
    else:
        result["margin_drain_product"] = "无"
        result["drain_detail"] = "无显著负毛利产品"

    # Margin star (#1 positive profit product)
    stars = profile.get("margin_stars", [])
    if stars:
        s = stars[0]
        result["margin_star_product"] = str(s[0])
        result["star_detail"] = f"{s[0]}(利润¥{s[1]:.0f},毛利率{s[2]:.1f}%)"
    else:
        result["margin_star_product"] = "无"
        result["star_detail"] = "无显著盈利产品"

    return result
