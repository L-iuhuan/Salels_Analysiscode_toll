"""
品类擅长分析 v4.15 — 每位销售在各产品线的能力指数。

指标:
  1. 利润质量(30%): 品类毛利率偏离度 + 品类利润贡献占比
  2. 增长趋势(25%): 品类销售额YoY增速 vs 公司该品类大盘增速
  3. 新品推动(20%): 新品销售额占比(≤12月)
  4. 定价能力(15%): 品类均价 vs 全市场均价偏离
  5. 交叉销售(10%): 品类关联购买强度

输出: 销售×品类矩阵, 含擅长类型(利润型/推新型/流量型)和置信度
"""

import pandas as pd
import numpy as np


def build_category_aptitude(portrait_df, silver=None):
    """构建每位销售的品类擅长矩阵。

    Returns:
        DataFrame: 销售×产品线, 含能力分/擅长类型/置信度/擅长趋势
    """
    if silver is None or "customer_x_product" not in silver:
        return pd.DataFrame()

    cxp = silver["customer_x_product"].copy()
    if "产品品种" not in cxp.columns:
        return pd.DataFrame()

    # Determine product line column
    line_col = None
    for c in ["型号_产品线（新）", "产品一级分类"]:
        if c in cxp.columns: line_col = c; break
    if not line_col:
        return pd.DataFrame()

    rev_col = "rev_sum" if "rev_sum" in cxp.columns else "金额"
    profit_col = "profit_clip_sum" if "profit_clip_sum" in cxp.columns else "_利润_裁剪"
    qty_col = "qty_sum" if "qty_sum" in cxp.columns else "数量"

    # Merge salesperson info
    owner_map = {}
    if "业务负责人" in portrait_df.columns:
        owner_map = dict(zip(portrait_df["客户编号"], portrait_df["业务负责人"]))
    cxp["_owner"] = cxp["客户编号"].map(owner_map)
    cxp = cxp[cxp["_owner"].notna() & (cxp["_owner"] != "未知")]

    # Unit price
    cxp["_price"] = np.where(cxp[qty_col] > 0, cxp[rev_col] / cxp[qty_col], np.nan)

    # Company-level benchmarks per product line
    comp = cxp.groupby(line_col).agg(
        公司毛利率=("_毛利率", "mean") if "_毛利率" in cxp.columns else (profit_col, lambda x: x.sum() / max(cxp.loc[x.index, rev_col].sum(), 1) * 100),
        公司均价=("_price", "median"),
        公司总营收=(rev_col, "sum"),
        公司新品占比=("新品标记", lambda x: (x == "是").sum() / max(len(x), 1) * 100) if "新品标记" in cxp.columns else (rev_col, lambda x: 0),
    ).reset_index()

    results = []
    for owner, subset in cxp.groupby("_owner"):
        for line, grp in subset.groupby(line_col):
            total_rev = grp[rev_col].sum()
            total_profit = grp[profit_col].sum()
            margin = total_profit / max(total_rev, 1) * 100
            avg_price = grp["_price"].median()

            comp_row = comp[comp[line_col] == line]
            if len(comp_row) == 0: continue
            comp_row = comp_row.iloc[0]

            # 1. 利润质量
            comp_margin = comp_row["公司毛利率"]
            margin_dev = (margin - comp_margin) / max(abs(comp_margin), 1) * 100  # 偏离度%
            profit_share = total_profit / max(comp_row["公司总营收"], 1) * 100 if comp_row["公司总营收"] > 0 else 0
            profit_score = min(100, max(0, 50 + margin_dev * 0.5 + profit_share * 2))

            # 2. 增长趋势(近似: 近6月vs前6月)
            growth_score = 50  # default
            if "_月" in cxp.columns:
                recent = grp[grp["_月"] >= grp["_月"].max() - 6][rev_col].sum()
                prior = grp[(grp["_月"] < grp["_月"].max() - 6) & (grp["_月"] >= grp["_月"].max() - 12)][rev_col].sum()
                if prior > 0:
                    growth = (recent - prior) / prior * 100
                    growth_score = min(100, max(0, 50 + growth))

            # 3. 新品推动
            new_score = 50
            if "新品标记" in cxp.columns:
                new_rev = grp[grp["新品标记"] == "是"][rev_col].sum()
                new_pct = new_rev / max(total_rev, 1) * 100
                new_score = min(100, new_pct * 5)

            # 4. 定价能力
            comp_price = comp_row["公司均价"]
            price_dev = (avg_price - comp_price) / max(comp_price, 1) * 100 if comp_price > 0 else 0
            pricing_score = min(100, max(0, 50 + price_dev * 2))

            # 5. 交叉销售(该品类客户同时也买其他品类的比例)
            cross_score = 50
            custs_in_line = set(grp["客户编号"].unique())
            custs_other_lines = set(subset[subset[line_col] != line]["客户编号"].unique())
            cross_rate = len(custs_in_line & custs_other_lines) / max(len(custs_in_line), 1) * 100
            cross_score = min(100, cross_rate * 0.8)

            # 综合能力分
            composite = (profit_score * 0.30 + growth_score * 0.25 + new_score * 0.20
                       + pricing_score * 0.15 + cross_score * 0.10)

            # 擅长类型判定
            if margin_dev > 10 and profit_score > 60:
                apt_type = "利润型"
            elif new_score > 60:
                apt_type = "推新型"
            elif growth_score > 60:
                apt_type = "增长型"
            else:
                apt_type = "流量型"

            # 置信度
            n_cust = len(custs_in_line)
            confidence = min(95, max(30, n_cust * 5 + 30))

            # 擅长趋势(简化: 用近6月增速判断)
            if growth_score > 65: trend = "上升期"
            elif growth_score > 45: trend = "稳定期"
            else: trend = "衰退期"

            results.append({
                "业务负责人": owner, "产品线": line,
                "利润质量分": round(profit_score, 1),
                "增长趋势分": round(growth_score, 1),
                "新品推动分": round(new_score, 1),
                "定价能力分": round(pricing_score, 1),
                "交叉销售分": round(cross_score, 1),
                "综合能力分": round(composite, 1),
                "擅长类型": apt_type, "置信度": confidence, "擅长趋势": trend,
                "品类收入": round(total_rev, 0), "品类毛利率": round(margin, 1),
                "客户数": n_cust,
            })

    result = pd.DataFrame(results)
    if len(result) > 0:
        result = result.sort_values(["业务负责人", "综合能力分"], ascending=[True, False])
    return result
