"""
周期经营分析模块 v4.16

新增：
- 经营周期总览（月/季度 + MoM/QoQ/YoY）
- 量价拆解（收入变化拆为数量效应/价格效应/结构效应）
- KA/AA月度雷达
- 销售人员周期表现

注意：按用户要求暂不单独输出"产品线周期表现"和"SKU周期表现"两张P2表。
"""

import pandas as pd
import numpy as np


def _period_to_quarter(p):
    p = pd.Period(str(p), freq="M")
    return f"{p.year}Q{((p.month - 1)//3) + 1}"


def _safe_pct(cur, base):
    return round((cur - base) / base * 100, 1) if base and base != 0 else None


def _agg_metrics(df):
    if df is None or len(df) == 0:
        return {"收入": 0.0, "毛利": 0.0, "数量": 0.0, "ASP": 0.0, "客户数": 0, "产品数": 0, "订单数": 0}
    revenue = df["rev_sum"].sum() if "rev_sum" in df.columns else 0.0
    profit = df["profit_clip_sum"].sum() if "profit_clip_sum" in df.columns else 0.0
    qty = df["qty_sum"].sum() if "qty_sum" in df.columns else 0.0
    return {
        "收入": round(revenue, 2),
        "毛利": round(profit, 2),
        "数量": round(qty, 2),
        "ASP": round(revenue / qty, 6) if qty else 0.0,
        "毛利率%": round(profit / revenue * 100, 2) if revenue else 0.0,
        "客户数": df["客户编号"].nunique() if "客户编号" in df.columns else 0,
        "产品数": df["产品品种"].nunique() if "产品品种" in df.columns else 0,
        "订单数": int(df["order_count"].sum()) if "order_count" in df.columns else 0,
    }


def build_period_overview(silver, portrait_df=None):
    """经营周期总览：月度+季度的收入/毛利/数量/ASP/客户数/产品数及环比同比。"""
    cm = silver.get("customer_monthly")
    cxp = silver.get("customer_x_product")
    if cm is None or len(cm) == 0:
        return pd.DataFrame()
    df = cm.copy()
    latest = df["_月"].max()
    rows = []

    # 月度
    for m in sorted(df["_月"].unique()):
        cur = df[df["_月"] == m]
        prev = df[df["_月"] == (m - 1)]
        yoy = df[df["_月"] == (m - 12)]
        met = _agg_metrics(cur)
        prev_met = _agg_metrics(prev)
        yoy_met = _agg_metrics(yoy)
        row = {"期间类型": "月", "期间": str(m), **met}
        for k in ["收入", "毛利", "数量", "ASP"]:
            row[f"{k}环比%"] = _safe_pct(met[k], prev_met[k])
            row[f"{k}同比%"] = _safe_pct(met[k], yoy_met[k])
        rows.append(row)

    # 季度
    qdf = df.copy()
    qdf["季度"] = qdf["_月"].apply(_period_to_quarter)
    quarters = sorted(qdf["季度"].unique())
    for i, q in enumerate(quarters):
        cur = qdf[qdf["季度"] == q]
        prev_q = quarters[i-1] if i > 0 else None
        # 去年同季
        year = int(q[:4]); qn = q[-2:]
        yoy_q = f"{year-1}{qn}"
        prev = qdf[qdf["季度"] == prev_q] if prev_q else qdf.iloc[0:0]
        yoy = qdf[qdf["季度"] == yoy_q]
        met = _agg_metrics(cur)
        prev_met = _agg_metrics(prev)
        yoy_met = _agg_metrics(yoy)
        row = {"期间类型": "季度", "期间": q, **met}
        for k in ["收入", "毛利", "数量", "ASP"]:
            row[f"{k}环比%"] = _safe_pct(met[k], prev_met[k])
            row[f"{k}同比%"] = _safe_pct(met[k], yoy_met[k])
        rows.append(row)
    return pd.DataFrame(rows)


def build_volume_price_decomposition(silver, dimension_col="型号_产品线（新）"):
    """量价拆解：按产品线、客户层级、渠道进行月度收入变化拆解。"""
    cxp = silver.get("customer_x_product")
    if cxp is None or len(cxp) == 0:
        return pd.DataFrame()
    df = cxp.copy()
    dims = []
    if dimension_col in df.columns:
        dims.append(("产品线", dimension_col))
    # 其他维度在cxp中可能没有，先仅做产品线维度，避免强依赖客户画像
    rows = []
    for dim_name, col in dims:
        grouped = df.groupby(["_月", col], observed=True).agg(
            收入=("rev_sum", "sum"),
            数量=("qty_sum", "sum"),
            毛利=("profit_clip_sum", "sum"),
            客户数=("客户编号", "nunique"),
            产品数=("产品品种", "nunique"),
        ).reset_index()
        grouped["ASP"] = grouped["收入"] / grouped["数量"].replace(0, np.nan)
        grouped = grouped.sort_values([col, "_月"])
        for val, grp in grouped.groupby(col, observed=True):
            grp = grp.sort_values("_月").reset_index(drop=True)
            for i in range(1, len(grp)):
                cur = grp.loc[i]; base = grp.loc[i-1]
                delta = cur["收入"] - base["收入"]
                qty_eff = (cur["数量"] - base["数量"]) * (base["ASP"] if pd.notna(base["ASP"]) else 0)
                price_eff = ((cur["ASP"] if pd.notna(cur["ASP"]) else 0) - (base["ASP"] if pd.notna(base["ASP"]) else 0)) * cur["数量"]
                struct_eff = delta - qty_eff - price_eff
                if qty_eff >= 0 and price_eff >= 0: tag = "量价齐升"
                elif qty_eff >= 0 and price_eff < 0: tag = "以价换量"
                elif qty_eff < 0 and price_eff >= 0: tag = "提价缩量"
                else: tag = "量价双杀"
                rows.append({
                    "期间类型": "月", "期间": str(cur["_月"]), "分析维度": dim_name, "维度值": val,
                    "本期收入": round(cur["收入"], 2), "基期收入": round(base["收入"], 2),
                    "收入变化": round(delta, 2), "收入环比%": _safe_pct(cur["收入"], base["收入"]),
                    "本期数量": round(cur["数量"], 2), "基期数量": round(base["数量"], 2),
                    "数量效应金额": round(qty_eff, 2),
                    "本期ASP": round(cur["ASP"], 6) if pd.notna(cur["ASP"]) else None,
                    "基期ASP": round(base["ASP"], 6) if pd.notna(base["ASP"]) else None,
                    "价格效应金额": round(price_eff, 2),
                    "结构效应金额": round(struct_eff, 2),
                    "量价标签": tag,
                    "毛利率%": round(cur["毛利"] / cur["收入"] * 100, 2) if cur["收入"] else 0,
                })
    return pd.DataFrame(rows)


def build_kaaa_monthly_radar(silver, portrait_df):
    """KA/AA月度雷达：按KA/AA客户×月输出经营指标和同比环比。"""
    cm = silver.get("customer_monthly")
    if cm is None or portrait_df is None or len(portrait_df) == 0:
        return pd.DataFrame()
    kaaa_ids = set(portrait_df[portrait_df["客户层级"].isin(["KA", "AA"])] ["客户编号"])
    df = cm[cm["客户编号"].isin(kaaa_ids)].copy()
    if len(df) == 0:
        return pd.DataFrame()
    info_cols = [c for c in ["客户编号", "客户层级", "客户等级", "业务负责人", "综合价值层级", "策略名称"] if c in portrait_df.columns]
    info = portrait_df[info_cols].drop_duplicates()
    df = df.merge(info, on="客户编号", how="left")
    rows = []
    for cid, grp in df.groupby("客户编号"):
        grp = grp.sort_values("_月").reset_index(drop=True)
        for i, r in grp.iterrows():
            prev = grp[grp["_月"] == r["_月"] - 1]
            yoy = grp[grp["_月"] == r["_月"] - 12]
            prev_rev = prev.iloc[0]["rev_sum"] if len(prev) else 0
            yoy_rev = yoy.iloc[0]["rev_sum"] if len(yoy) else 0
            rows.append({
                "客户编号": cid, "月份": str(r["_月"]), "客户层级": r.get("客户层级"),
                "客户等级": r.get("客户等级"), "业务负责人": r.get("业务负责人"),
                "综合价值层级": r.get("综合价值层级"), "策略名称": r.get("策略名称"),
                "月收入": round(r["rev_sum"], 2), "月毛利": round(r["profit_clip_sum"], 2),
                "月数量": round(r["qty_sum"], 2), "月毛利率%": round(r["profit_clip_sum"] / r["rev_sum"] * 100, 2) if r["rev_sum"] else 0,
                "月ASP": round(r["rev_sum"] / r["qty_sum"], 6) if r["qty_sum"] else 0,
                "月环比%": _safe_pct(r["rev_sum"], prev_rev), "月同比%": _safe_pct(r["rev_sum"], yoy_rev),
            })
    return pd.DataFrame(rows)


def build_sales_period_performance(silver, portrait_df):
    """销售人员周期表现：业务负责人×月。"""
    cm = silver.get("customer_monthly")
    if cm is None or portrait_df is None or len(portrait_df) == 0:
        return pd.DataFrame()
    info = portrait_df[["客户编号", "业务负责人", "客户层级", "客户等级"]].drop_duplicates()
    df = cm.merge(info, on="客户编号", how="left")
    df = df[df["业务负责人"].notna() & (df["业务负责人"] != "未知")]
    rows = []
    agg = df.groupby(["业务负责人", "_月"]).agg(
        月收入=("rev_sum", "sum"), 月毛利=("profit_clip_sum", "sum"), 月数量=("qty_sum", "sum"),
        客户数=("客户编号", "nunique"), 订单数=("order_count", "sum") if "order_count" in df.columns else ("rev_sum", "count"),
    ).reset_index()
    agg["月ASP"] = agg["月收入"] / agg["月数量"].replace(0, np.nan)
    agg = agg.sort_values(["业务负责人", "_月"])
    for owner, grp in agg.groupby("业务负责人"):
        grp = grp.sort_values("_月").reset_index(drop=True)
        for i, r in grp.iterrows():
            prev = grp[grp["_月"] == r["_月"] - 1]
            yoy = grp[grp["_月"] == r["_月"] - 12]
            prev_rev = prev.iloc[0]["月收入"] if len(prev) else 0
            yoy_rev = yoy.iloc[0]["月收入"] if len(yoy) else 0
            rows.append({
                "业务负责人": owner, "月份": str(r["_月"]), "月收入": round(r["月收入"], 2),
                "月毛利": round(r["月毛利"], 2), "月数量": round(r["月数量"], 2),
                "月ASP": round(r["月ASP"], 6) if pd.notna(r["月ASP"]) else None,
                "客户数": int(r["客户数"]), "订单数": int(r["订单数"]),
                "月环比%": _safe_pct(r["月收入"], prev_rev), "月同比%": _safe_pct(r["月收入"], yoy_rev),
            })
    return pd.DataFrame(rows)
