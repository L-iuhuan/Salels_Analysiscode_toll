"""
负毛利深度分析模块。

功能：
  1. 识别每个客户采购的负毛利产品
  2. 计算负毛利产品造成的损失总额
  3. 计算"停售负毛利产品可挽回的利润"
  4. 生成分级建议：S/A级+KA/AA客户深度分析，B/C级简要提示

输出字段：
  - 客户编号
  - 整体毛利率%
  - 在采品种数
  - 负毛利品种数 / 负毛利品种占比
  - 负毛利产品损失总额（元）
  - 停售负毛利品可增加利润（元）
  - 负毛利产品清单（品种:毛利率:损失额）
  - 建议动作
  - 负毛利严重等级
"""

import pandas as pd
import numpy as np


def analyze_negative_margin(
    customer_x_product: pd.DataFrame,
    customer_portrait: pd.DataFrame = None,
) -> pd.DataFrame:
    """对每个客户进行负毛利产品分析。

    参数:
        customer_x_product: Silver层客户×产品×月聚合表
            (需含 客户编号, 产品品种, rev_sum, profit_clip_sum, 毛利率%)
        customer_portrait: 客户全景表（可选，用于获取层级/评分信息）

    返回:
        DataFrame: 每客户一行，含负毛利分析字段
    """
    cxp = customer_x_product.copy()

    # Determine column names
    cust_col = "客户编号"
    prod_col = "产品品种"
    rev_col = "rev_sum" if "rev_sum" in cxp.columns else "金额"
    profit_col = "profit_clip_sum" if "profit_clip_sum" in cxp.columns else "_利润_裁剪"
    margin_col = "毛利率%" if "毛利率%" in cxp.columns else None

    # If no pre-calculated margin, compute it
    if margin_col is None or margin_col not in cxp.columns:
        cxp["_margin_pct"] = np.where(
            cxp[rev_col] > 0,
            cxp[profit_col] / cxp[rev_col] * 100,
            0
        )
        margin_col = "_margin_pct"

    # Aggregate to customer×product level (sum across months)
    cp_agg = cxp.groupby([cust_col, prod_col], observed=True).agg(
        total_rev=(rev_col, "sum"),
        total_profit=(profit_col, "sum"),
    ).reset_index()
    cp_agg["毛利率%"] = np.where(
        cp_agg["total_rev"] > 0,
        cp_agg["total_profit"] / cp_agg["total_rev"] * 100,
        0
    )

    # Per-customer overall stats
    cust_stats = cp_agg.groupby(cust_col).agg(
        总采购额=("total_rev", "sum"),
        总毛利润=("total_profit", "sum"),
        在采品种数=(prod_col, "nunique"),
    ).reset_index()
    cust_stats["整体毛利率%"] = np.where(
        cust_stats["总采购额"] > 0,
        cust_stats["总毛利润"] / cust_stats["总采购额"] * 100,
        0
    ).round(2)

    # Identify negative-margin products per customer
    neg_mask = cp_agg["毛利率%"] < 0
    neg_products = cp_agg[neg_mask].copy()

    if len(neg_products) == 0:
        # No negative margin products exist
        cust_stats["负毛利品种数"] = 0
        cust_stats["负毛利品种占比"] = 0.0
        cust_stats["负毛利损失总额"] = 0.0
        cust_stats["停售可增加利润"] = 0.0
        cust_stats["负毛利产品清单"] = ""
        cust_stats["负毛利严重等级"] = "无"
        cust_stats["建议动作"] = ""
        return cust_stats

    # Aggregate negative margin info per customer
    neg_agg = neg_products.groupby(cust_col).agg(
        负毛利品种数=(prod_col, "nunique"),
        负毛利损失总额=("total_profit", "sum"),  # This will be negative
        负毛利产品清单=(prod_col, lambda x: "; ".join(
            f"{p}(毛利率{m:.1f}% 损失{abs(l):.0f}元)"
            for p, m, l in zip(
                neg_products.loc[x.index, prod_col],
                neg_products.loc[x.index, "毛利率%"],
                neg_products.loc[x.index, "total_profit"],
            )
        )),
    ).reset_index()

    # Merge into customer stats
    cust_stats = cust_stats.merge(neg_agg, on=cust_col, how="left")
    cust_stats["负毛利品种数"] = cust_stats["负毛利品种数"].fillna(0).astype(int)
    cust_stats["负毛利品种占比"] = np.where(
        cust_stats["在采品种数"] > 0,
        (cust_stats["负毛利品种数"] / cust_stats["在采品种数"] * 100).round(1),
        0.0
    )
    cust_stats["负毛利损失总额"] = cust_stats["负毛利损失总额"].fillna(0.0)
    # 停售可增加利润 = abs(负毛利损失)，即如果不做这些负毛利生意，利润增加多少
    cust_stats["停售可增加利润"] = (-cust_stats["负毛利损失总额"]).clip(lower=0).round(0)
    cust_stats["负毛利产品清单"] = cust_stats["负毛利产品清单"].fillna("")

    # --- Severity classification (v4.14: 加绝对损失门槛) ---
    def _classify_severity(row):
        """分级：严重/关注/轻微/无。v4.14加入绝对损失金额判断。"""
        if row["负毛利品种数"] == 0:
            return "无"
        loss = abs(row["负毛利损失总额"])
        # 绝对损失>15万 → 严重（不管整体是否正毛利）
        if loss > 150_000:
            return "严重"
        # 整体毛利率为负 → 严重
        if row["整体毛利率%"] < 0:
            return "严重"
        # 绝对损失>10万 → 至少关注
        if loss > 100_000:
            return "关注"
        # 负毛利品种超过30% 或 损失超过总采购额10%
        loss_ratio = abs(row["负毛利损失总额"]) / row["总采购额"] if row["总采购额"] > 0 else 0
        if row["负毛利品种占比"] > 30 or loss_ratio > 0.10:
            return "严重"
        if row["负毛利品种占比"] > 15 or loss_ratio > 0.05:
            return "关注"
        if row["负毛利品种数"] > 0:
            return "轻微"
        return "无"

    cust_stats["负毛利严重等级"] = cust_stats.apply(_classify_severity, axis=1)

    # --- Action recommendation per severity ---
    def _recommend(row):
        if row["负毛利严重等级"] == "无":
            return ""
        actions = []
        loss = abs(row["负毛利损失总额"])
        count = row["负毛利品种数"]
        total = row["在采品种数"]

        if row["整体毛利率%"] < 0:
            actions.append(
                f"【紧急】客户整体毛利率为{row['整体毛利率%']:.1f}%，"
                f"{count}个负毛利产品造成损失{loss:.0f}元。"
                f"建议立即审查定价策略，与客户协商提价或限制负毛利产品供应"
            )
        elif row["负毛利严重等级"] == "严重":
            actions.append(
                f"【重点关注】{count}/{total}个品种({row['负毛利品种占比']:.0f}%)为负毛利，"
                f"共计损失{loss:.0f}元。停售这些产品可增加利润{row['停售可增加利润']:.0f}元"
            )
        elif row["负毛利严重等级"] == "关注":
            actions.append(
                f"【关注】{count}个负毛利品种造成损失{loss:.0f}元，"
                f"建议逐品审查定价或考虑限量供应"
            )
        else:
            actions.append(
                f"【提示】{count}个品种存在负毛利(损失{loss:.0f}元)，可择机调整价格"
            )

        # Add stop-selling recommendation if significant
        if row["停售可增加利润"] > 1000 and row["负毛利严重等级"] in ("严重", "关注"):
            actions.append(
                f"【止损建议】停售全部负毛利产品可增加利润{row['停售可增加利润']:.0f}元。"
                f"首先考虑停止供应: {row['负毛利产品清单'][:200]}"
            )

        return " | ".join(actions)

    cust_stats["建议动作"] = cust_stats.apply(_recommend, axis=1)

    # --- Merge customer tier/score info if available ---
    if customer_portrait is not None and len(customer_portrait) > 0:
        merge_cols = ["客户编号"]
        for col in ["客户层级", "客户等级", "综合价值层级", "活跃状态",
                     "业务负责人", "近12月收入", "近12月毛利"]:
            if col in customer_portrait.columns:
                merge_cols.append(col)
        cust_stats = cust_stats.merge(
            customer_portrait[merge_cols], on="客户编号", how="left"
        )
    # v4.15: 非活跃客户(收入=0)降级 — 必须在merge之后执行(此时才有近12月收入列)
    if "近12月收入" in cust_stats.columns:
        inactive = cust_stats["近12月收入"].fillna(0) <= 0
        cust_stats.loc[inactive & (cust_stats["负毛利严重等级"] == "严重"), "负毛利严重等级"] = "关注"

    # Sort: severe → attention → mild → none
    severity_order = {"严重": 0, "关注": 1, "轻微": 2, "无": 3}
    cust_stats["_severity_sort"] = cust_stats["负毛利严重等级"].map(severity_order)
    cust_stats = cust_stats.sort_values(
        ["_severity_sort", "停售可增加利润"],
        ascending=[True, False],
        kind='stable'
    ).drop(columns=["_severity_sort"]).reset_index(drop=True)

    return cust_stats


def summarize_negative_margin_for_alert(
    neg_analysis: pd.DataFrame,
) -> dict:
    """生成负毛利汇总统计，用于行动建议引擎。

    返回:
        dict: {客户编号: {整体毛利率, 负毛利品种数, 停售可增加利润, ...}}
    """
    summary = {}
    for _, row in neg_analysis.iterrows():
        cid = row["客户编号"]
        summary[cid] = {
            "整体毛利率%": row.get("整体毛利率%", 0),
            "负毛利品种数": int(row.get("负毛利品种数", 0)),
            "在采品种数": int(row.get("在采品种数", 0)),
            "负毛利损失总额": float(row.get("负毛利损失总额", 0)),
            "停售可增加利润": float(row.get("停售可增加利润", 0)),
            "负毛利严重等级": row.get("负毛利严重等级", "无"),
            "负毛利产品清单": str(row.get("负毛利产品清单", "")),
            "建议动作": str(row.get("建议动作", "")),
        }
    return summary
