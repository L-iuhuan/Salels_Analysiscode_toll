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

    profiles = {}

    for cid, grp in cxp.groupby(cust_col):
        # Aggregate to product level
        prod_agg = grp.groupby(prod_col).agg(
            total_rev=(rev_col, "sum"),
            total_profit=(profit_col, "sum"),
        ).reset_index()
        prod_agg["margin_pct"] = np.where(
            prod_agg["total_rev"] > 0,
            prod_agg["total_profit"] / prod_agg["total_rev"] * 100,
            0
        )

        total_rev = prod_agg["total_rev"].sum()
        total_profit = prod_agg["total_profit"].sum()
        overall_margin = (total_profit / total_rev * 100) if total_rev > 0 else 0

        # Top 5 by revenue
        top5 = prod_agg.nlargest(5, "total_rev")
        top5_list = [
            (r[prod_col], r["total_rev"], r["margin_pct"])
            for _, r in top5.iterrows()
        ]

        # Margin stars (positive profit, high margin)
        profit_pos = prod_agg[prod_agg["total_profit"] > 0].nlargest(5, "total_profit")
        margin_stars = [
            (r[prod_col], r["total_profit"], r["margin_pct"])
            for _, r in profit_pos.iterrows()
        ]

        # Margin drains (negative profit)
        profit_neg = prod_agg[prod_agg["total_profit"] < 0].nsmallest(5, "total_profit")
        margin_drains = [
            (r[prod_col], r["total_profit"], r["margin_pct"])
            for _, r in profit_neg.iterrows()
        ]

        # Top 1 product
        if len(top5_list) > 0:
            top1 = top5_list[0]
            top1_share = top1[1] / total_rev if total_rev > 0 else 0
            top1_info = (top1[0], top1[1], top1_share)
        else:
            top1_info = ("无", 0, 0)

        # Category from portrait
        dominant_line = ""
        cat_col = None
        for c in grp.columns:
            if c in ("产品一级分类", "型号_产品品类"):
                cat_col = c
                break
        if cat_col:
            line_rev = grp.groupby(cat_col)[rev_col].sum()
            if len(line_rev) > 0:
                dominant_line = line_rev.idxmax()

        profiles[cid] = {
            "top5_by_revenue": top5_list,
            "margin_stars": margin_stars,
            "margin_drains": margin_drains,
            "top1_product": top1_info,
            "overall_margin": round(overall_margin, 1),
            "total_revenue": total_rev,
            "total_profit": total_profit,
            "product_count": len(prod_agg),
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
    """
    cxp = customer_x_product.copy()
    if "_月" not in cxp.columns:
        return {}

    cxp = cxp.sort_values(["_月"], kind='stable')
    cust_col = "客户编号"
    prod_col = "产品品种"
    rev_col = "rev_sum" if "rev_sum" in cxp.columns else "金额"
    profit_col = "profit_clip_sum" if "profit_clip_sum" in cxp.columns else "_利润_裁剪"

    trends = {}

    for cid, grp in cxp.groupby(cust_col):
        months = sorted(grp["_月"].unique())
        if len(months) < 4:
            continue

        # Compare last 3 months vs previous 3 months per product
        recent_3 = months[-3:]
        prior_3 = months[-6:-3]

        declining = []
        for prod, pgrp in grp.groupby(prod_col):
            recent_rev = pgrp[pgrp["_月"].isin(recent_3)][rev_col].sum()
            prior_rev = pgrp[pgrp["_月"].isin(prior_3)][rev_col].sum()
            if prior_rev > 0 and recent_rev < prior_rev:
                decline_pct = (recent_rev - prior_rev) / prior_rev * 100
                loss = prior_rev - recent_rev
                if decline_pct < -20:  # Significant decline
                    declining.append((prod, round(decline_pct, 1), round(loss, 0)))

        declining.sort(key=lambda x: x[1])  # Sort by decline % (most negative first)

        trends[cid] = {
            "declining_products": declining[:5],
            "recent_3_months": [str(m) for m in recent_3],
            "prior_3_months": [str(m) for m in prior_3],
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

        for i in range(len(months) - 11):
            window = months[i:i+12]
            w = grp[grp["_月"].isin(window)]
            rev = w[rev_col].sum()
            profit = w[profit_col].sum()
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
        for cid in glories:
            cgrp = cxp[cxp[cust_col] == cid]
            if len(cgrp) > 0:
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
