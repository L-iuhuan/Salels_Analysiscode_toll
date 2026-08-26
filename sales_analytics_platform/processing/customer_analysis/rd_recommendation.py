"""
产品研发建议模块 v4.16

将销售数据转成研发决策语言：哪些产品被高价值客户认可、需求稳定、毛利健康，值得做二代/降本/扩SKU。
"""

import pandas as pd
import numpy as np


def build_rd_recommendations(silver, portrait_df=None):
    pm = silver.get("product_monthly")
    cxp = silver.get("customer_x_product")
    if pm is None or cxp is None or len(pm) == 0 or len(cxp) == 0:
        return pd.DataFrame()
    latest = pm["_月"].max()
    recent6 = pm[pm["_月"] > latest - 6].copy()
    yoy6 = pm[(pm["_月"] > latest - 18) & (pm["_月"] <= latest - 12)].copy()

    # customer tier mapping
    tier_map = {}
    if portrait_df is not None and "客户层级" in portrait_df.columns:
        tier_map = dict(zip(portrait_df["客户编号"], portrait_df["客户层级"]))
    cxp2 = cxp.copy()
    cxp2["客户层级"] = cxp2["客户编号"].map(tier_map).fillna("MM")

    rows = []
    # [批次⑥ P4] 三处循环内重复计算提升，全部与原值逐位一致：
    #  1) 全公司高质量/总收入占比与产品无关，原为每产品重算（800×2次全表 isin+过滤）→ 循环外算一次；
    #  2) yoy6 / cxp2 按产品一次性预分组（groupby(sort=False) 组内行序与原布尔过滤一致），
    #     替代每产品 yoy6[yoy6["产品品种"]==prod] 与 cxp2[...]==prod 全表扫描（800×151K 行）。
    _recent6m = cxp2["_月"] > latest - 6
    _high_mask_all = cxp2["客户层级"].isin(["KA", "AA", "KM"])
    company_high_rev = cxp2[_high_mask_all & _recent6m]["rev_sum"].sum()
    company_total_rev = cxp2[_recent6m]["rev_sum"].sum()
    base_high_share = company_high_rev / company_total_rev * 100 if company_total_rev > 0 else 0
    _YOY_BY_PROD = {k: g for k, g in yoy6.groupby("产品品种", sort=False)}
    _CXP6_BY_PROD = {k: g for k, g in cxp2[_recent6m].groupby("产品品种", sort=False)}
    _CXP6_EMPTY = cxp2.iloc[0:0]
    for prod, grp in recent6.groupby("产品品种", observed=True):
        rev = grp["rev_sum"].sum(); qty = grp["qty_sum"].sum(); profit = grp["profit_clip_sum"].sum()
        if rev <= 0 or qty <= 0: continue
        # YoY
        yoy_grp = _YOY_BY_PROD.get(prod)  # [批次⑥ P4] 预分组（无→None，与原空过滤一致）
        yoy_qty = yoy_grp["qty_sum"].sum() if yoy_grp is not None and len(yoy_grp) else 0
        yoy_growth = (qty - yoy_qty) / yoy_qty * 100 if yoy_qty > 0 else None
        # CV of monthly qty
        monthly = grp.groupby("_月")["qty_sum"].sum()
        cv = monthly.std() / monthly.mean() if monthly.mean() > 0 and len(monthly) > 1 else 0
        # customer quality
        prod_cxp = _CXP6_BY_PROD.get(prod, _CXP6_EMPTY)  # [批次⑥ P4] 预分组
        high = prod_cxp[prod_cxp["客户层级"].isin(["KA", "AA", "KM"])]
        high_rev = high["rev_sum"].sum()
        hq_pen = high_rev / rev * 100 if rev > 0 else 0
        high_cust = high["客户编号"].nunique()
        total_cust = prod_cxp["客户编号"].nunique()
        # HPI: 高价值客户收入占比 / 高价值客户公司总收入占比
        hpi = (hq_pen / base_high_share) if base_high_share > 0 else 0
        margin = profit / rev * 100 if rev > 0 else 0
        asp = rev / qty if qty > 0 else 0
        rigidity = "高" if cv < 0.3 and total_cust >= 5 else ("中" if cv < 0.8 else "低")
        # Recommendation rules
        if hpi > 1.3 and total_cust >= 10 and cv < 0.8:
            rec = "二代立项"
            reason = "高价值客户偏好明显，客户数充足且需求稳定"
        elif rev > 500000 and margin < 20:
            rec = "降本优化"
            reason = "收入规模较大但毛利率偏低"
        elif total_cust >= 20 and hq_pen < 30:
            rec = "KA导入专项"
            reason = "客户数多但高价值客户渗透不足"
        elif yoy_growth is not None and yoy_growth < -30 and margin < 20:
            rec = "清退或替代"
            reason = "销量下滑且毛利偏低"
        else:
            rec = "维持观察"
            reason = "暂无强烈研发动作信号"
        rows.append({
            "产品名称": prod, "近6月月均销量": round(qty/6, 2), "近6月月均收入": round(rev/6, 2),
            "近6月毛利率%": round(margin, 2), "销量同比%": round(yoy_growth, 1) if yoy_growth is not None else None,
            "高质量客户渗透率%": round(hq_pen, 1), "高质量客户数": high_cust, "客户数": total_cust,
            "HPI指数": round(hpi, 2), "需求刚性等级": rigidity, "销量CV": round(cv, 3), "ASP": round(asp, 6),
            "研发建议": rec, "建议理由": reason
        })
    df = pd.DataFrame(rows)
    if len(df) > 0:
        order = {"二代立项":0,"降本优化":1,"KA导入专项":2,"清退或替代":3,"维持观察":4}
        df["_sort"] = df["研发建议"].map(order).fillna(9)
        df = df.sort_values(["_sort","近6月月均收入"], ascending=[True,False]).drop(columns=["_sort"])
    return df
