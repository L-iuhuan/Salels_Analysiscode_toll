#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
口径决策预演（D-1 毛利率钳制 / D-2 负数量 / D-4 config.xlsx）— 批次③第一阶段
=====================================================================

用途：为业务对 D-1/D-2/D-4 拍板提供数字证据。每月可重跑（读当前 output\ 产物）。

用法：
  python scripts/impact_rehearsal.py                      # 读当前产物，打印摘要
  python scripts/impact_rehearsal.py --platform-dir <dir> # 指定平台目录
  python scripts/impact_rehearsal.py --out-json <path>    # 指定 JSON 输出路径（默认系统临时目录）

数据加载（宪法 S8 语义）：
  - 全部走生产路径 shared.data_cleaning.load_silver_table（同名 .parquet 存在且不早于 CSV 时读 parquet）
  - silver_cleaned_rows（主输入）/ silver_customer_x_product / silver_product_monthly（dtype map 归一）
  - gold_product_portrait.csv（gold 层，直接读 CSV）用于 9 宫格/风险/图表压缩参考

口径与近似说明（如实）：
  - D-2 全期与 YTD 的收入/毛利/毛利率：**精确重算**（cleaned_rows 行级直接聚合）
  - D-2 产品生命周期 9 宫格阶段分布：**行级近似**（按产品月聚合 + 简化动能/盈利健康代理分类，
    非生产 profiling.py 完整流水线；仅供量级对比）
  - D-1 产品风险评分（4 因素）分布与风险等级迁移矩阵：**行级近似**
    （按产品月聚合构建 4 因素输入，复用 production 现役 v4.0 评分函数
    shared.risk_scoring 的 score_slope_v2/score_decay_v2/score_self_health_v2/score_c6_v2/compute_composite_v2；
    非 profiling.py 的精确面板构建）
  - 图表压缩：基于 gold_product_portrait 的 近12月毛利率% / ASP趋势%/月 分布量化
    （不钳制 min~max vs 展示层 p1~p99 截断的坐标轴对比、极端散点数量）

所有指标同时写入 JSON（默认系统临时目录 impact_rehearsal_YYYYMMDD.json）。
"""

import argparse
import datetime
import json
import os
import sys
import time

import numpy as np
import pandas as pd

# ── 路径 ──
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_PLATFORM = os.path.join(_REPO_ROOT, "sales_analytics_platform")

# D-1 钳制阈值（与 settings_product PRODUCT_LIFECYCLE 口径开关一致：-0.5 / 0.75）
CLIP_LOWER = -0.50
CLIP_UPPER = 0.75
# 风险等级阈值（与 config/settings_product.py risk_low_max/mid_max/high_max 一致）
RISK_LEVELS = [("低", 0.0, 55.0), ("中", 55.0, 65.0), ("高", 65.0, 68.0), ("极高", 68.0, np.inf)]


def _load_silver(platform_dir, rel, dtype=None):
    """生产路径加载 silver 表（load_silver_table，优先 parquet，dtype 归一）。"""
    from shared.data_cleaning import load_silver_table
    p = os.path.join(platform_dir, "output", "silver", rel)
    return load_silver_table(p, dtype=dtype, low_memory=False)


def _load_gold_csv(platform_dir, name):
    return pd.read_csv(os.path.join(platform_dir, "output", "gold", name),
                       encoding="utf-8-sig")


def _ytd_mask(df, data_month):
    """YTD 掩码：年份 == data_month 年份 且 月份 <= data_month。"""
    y = int(str(data_month)[:4])
    ym = df["_ym"].astype(str)
    return ym.str.startswith(str(y)) & (ym <= str(data_month))


def _margin_pct(profit, rev):
    return float(profit / rev) * 100 if rev else float("nan")


def _apply_clip_profit(cr):
    """v2.8 口径数据层钳制利润：clip(利润/金额, -0.5, 0.75) * 金额 (rev>0)，否则原利润。"""
    rev = cr["金额"].to_numpy(dtype=float)
    profit = cr["利润"].to_numpy(dtype=float)
    margin = np.where(rev > 0, profit / np.where(rev != 0, rev, np.nan), np.nan)
    margin_clip = np.clip(margin, CLIP_LOWER, CLIP_UPPER)
    profit_clip = np.where(rev > 0, np.nan_to_num(margin_clip, nan=0.0) * rev, profit)
    return pd.Series(profit_clip, index=cr.index)


# ══════════════════════════════════════════════════════════════════
# D-2：负数量
# ══════════════════════════════════════════════════════════════════

def compute_d2(cr, data_month):
    out = {}
    cr = cr.copy()
    cr["_ym"] = cr["_ym"].astype(str)
    ytd = cr[_ytd_mask(cr, data_month)]

    # 负数量行画像
    neg = cr[cr["数量"] < 0]
    out["neg_rows"] = int(len(neg))
    out["neg_rows_pct"] = round(len(neg) / len(cr) * 100, 3)
    out["neg_amount"] = float(neg["金额"].sum())
    out["neg_amount_pct_rev"] = float(neg["金额"].sum() / cr["金额"].sum() * 100)
    out["neg_profit"] = float(neg["利润"].sum())
    out["zero_qty_rows"] = int((cr["数量"] == 0).sum())

    def agg(df):
        rev = float(df["金额"].sum())
        profit = float(df["利润"].sum())
        return {"rev": rev, "profit": profit, "margin_pct": _margin_pct(profit, rev),
                "rows": int(len(df))}

    keep_full = agg(cr)
    keep_ytd = agg(ytd)
    filt_full = agg(cr[cr["数量"] > 0])
    filt_ytd = agg(ytd[ytd["数量"] > 0])

    def diff(a, b):
        return {
            "rev_diff": a["rev"] - b["rev"],
            "rev_diff_pct": (a["rev"] - b["rev"]) / b["rev"] * 100,
            "profit_diff": a["profit"] - b["profit"],
            "profit_diff_pct": (a["profit"] - b["profit"]) / b["profit"] * 100,
            "margin_pct_diff_pp": a["margin_pct"] - b["margin_pct"],
        }

    out["full_period"] = {"keep": keep_full, "filter": filt_full,
                          "keep_minus_filter": diff(keep_full, filt_full)}
    out["ytd"] = {"keep": keep_ytd, "filter": filt_ytd,
                  "keep_minus_filter": diff(keep_ytd, filt_ytd)}

    # 月度收入序列对比
    m_keep = cr.groupby("_ym")["金额"].sum()
    m_filt = cr[cr["数量"] > 0].groupby("_ym")["金额"].sum()
    m_keep = m_keep.reindex(sorted(set(m_keep.index) | set(m_filt.index))).fillna(0)
    m_filt = m_filt.reindex(m_keep.index).fillna(0)
    dev = (m_keep - m_filt).abs()
    out["monthly"] = {
        "months": list(m_keep.index),
        "keep_series_wan": [round(v / 1e4, 2) for v in m_keep.values],
        "filter_series_wan": [round(v / 1e4, 2) for v in m_filt.values],
        "max_month_deviation_amount": float(dev.max()),
        "max_month_deviation_month": str(dev.idxmax()),
        "max_month_deviation_pct": float((dev / m_keep.replace(0, np.nan)).max() * 100),
    }
    # 符号翻转月数（收入/毛利）
    out["monthly"]["sign_flip_months_rev"] = int(((m_keep > 0) != (m_filt > 0)).sum())
    p_keep = cr.groupby("_ym")["利润"].sum()
    p_filt = cr[cr["数量"] > 0].groupby("_ym")["利润"].sum()
    p_keep = p_keep.reindex(sorted(set(p_keep.index) | set(p_filt.index))).fillna(0)
    p_filt = p_filt.reindex(p_keep.index).fillna(0)
    out["monthly"]["sign_flip_months_profit"] = int(((p_keep > 0) != (p_filt > 0)).sum())

    # 产品生命周期 9 宫格阶段分布影响（行级近似）
    out["nine_grid"] = _nine_grid_approx(cr)

    # Top10 退货客户/产品（按负数量金额，取最负）
    neg_cust = neg.groupby("客户编号")["金额"].sum().sort_values()
    neg_prod = neg.groupby("产品品种")["金额"].sum().sort_values()
    out["top10_return_customers"] = [
        {"客户编号": str(k), "金额": round(float(v), 2), "万元": round(float(v) / 1e4, 2)}
        for k, v in neg_cust.head(10).items()]
    out["top10_return_products"] = [
        {"产品品种": str(k), "金额": round(float(v), 2), "万元": round(float(v) / 1e4, 2)}
        for k, v in neg_prod.head(10).items()]
    if not neg_cust.empty:
        out["top1_return_customer_share_pct"] = round(
            abs(float(neg_cust.iloc[0])) / abs(float(neg["金额"].sum())) * 100, 2)
    return out


def _stage_proxy(g):
    """单产品的 9 宫格阶段代理（简化，非生产流水线；近似）。"""
    n = len(g)
    if n < 2:
        return "新品观察/数据不足"
    recent = g.tail(3)
    prior = g.iloc[:-3].tail(3) if n >= 6 else g.iloc[:-3]
    if len(prior) == 0:
        return "新品观察/数据不足"
    q_recent = recent["qty"].sum()
    q_prior = prior["qty"].sum()
    momentum = (q_recent - q_prior) / q_prior if q_prior else 0.0
    rev_recent = recent["rev"].sum()
    margin_recent = (recent["profit"].sum() / rev_recent) if rev_recent else float("nan")
    rev_all = g["rev"].sum()
    margin_all = (g["profit"].sum() / rev_all) if rev_all else float("nan")
    if not np.isfinite(margin_recent) or not np.isfinite(margin_all):
        health = 0.5
    else:
        health = margin_recent / margin_all if margin_all != 0 else 0.5
    healthy = health >= 0.95
    weak = health <= 0.7
    if momentum > 0.15:
        return "成长期" if healthy else "预警增长"
    elif momentum > 0:
        return "健康扩张" if healthy else ("隐性衰退" if weak else "利润优化")
    elif momentum > -0.1:
        return "现金牛" if healthy else ("隐性衰退" if weak else "利润优化")
    else:
        return "主动收缩" if healthy else ("衰退期" if weak else "夕阳产品")


def _nine_grid_approx(cr):
    """9 宫格阶段分布（行级近似）：保留 vs 过滤 的阶段分布与迁移数。"""
    res = {}
    pmk = cr.groupby(["产品品种", "_ym"]).agg(
        qty=("数量", "sum"), rev=("金额", "sum"), profit=("利润", "sum")).reset_index()
    pmk = pmk.sort_values(["产品品种", "_ym"])
    pmf = cr[cr["数量"] > 0].groupby(["产品品种", "_ym"]).agg(
        qty=("数量", "sum"), rev=("金额", "sum"), profit=("利润", "sum")).reset_index()
    pmf = pmf.sort_values(["产品品种", "_ym"])
    stage_k = {p: _stage_proxy(g) for p, g in pmk.groupby("产品品种")}
    stage_f = {p: _stage_proxy(g) for p, g in pmf.groupby("产品品种")}
    res["keep"] = {"n_products": int(len(stage_k)),
                   "dist": dict(sorted(pd.Series(stage_k).value_counts().to_dict().items(), key=lambda x: -x[1]))}
    res["filter"] = {"n_products": int(len(stage_f)),
                     "dist": dict(sorted(pd.Series(stage_f).value_counts().to_dict().items(), key=lambda x: -x[1]))}
    allp = sorted(set(stage_k) | set(stage_f))
    moved = [p for p in allp if stage_k.get(p) != stage_f.get(p)]
    res["stage_change_count"] = int(len(moved))
    res["stage_change_pct"] = round(len(moved) / len(allp) * 100, 2) if allp else 0
    res["changed_products"] = [{"产品品种": p, "keep": stage_k.get(p), "filter": stage_f.get(p)}
                               for p in moved[:20]]
    return res


# ══════════════════════════════════════════════════════════════════
# D-1：毛利率钳制
# ══════════════════════════════════════════════════════════════════

def compute_d1(cr, data_month, gpp):
    out = {}
    margin = cr["_毛利率"].dropna()

    # 毛利率分布（行级）
    q = margin.quantile([0.01, 0.05, 0.50, 0.95, 0.99])
    out["margin_dist"] = {
        "min": round(float(margin.min()), 4), "p1": round(float(q[0.01]), 4),
        "p5": round(float(q[0.05]), 4), "p50": round(float(q[0.50]), 4),
        "p95": round(float(q[0.95]), 4), "p99": round(float(q[0.99]), 4),
        "max": round(float(margin.max()), 4), "n_nonnull": int(margin.notna().sum()),
    }

    # 被钳行（margin < -0.5 或 > 0.75）
    clipped_mask = (cr["_毛利率"] < CLIP_LOWER) | (cr["_毛利率"] > CLIP_UPPER)
    clipped = cr[clipped_mask]
    rev_total = float(cr["金额"].sum())
    profit_total = float(cr["利润"].sum())
    out["clip"] = {
        "lower": CLIP_LOWER, "upper": CLIP_UPPER,
        "clipped_rows": int(len(clipped)),
        "clipped_rows_pct": round(len(clipped) / len(cr) * 100, 4),
        "clipped_rev": float(clipped["金额"].sum()),
        "clipped_rev_pct": round(float(clipped["金额"].sum()) / rev_total * 100, 4),
        "clipped_profit": float(clipped["利润"].sum()),
        "clipped_profit_pct": round(float(clipped["利润"].sum()) / profit_total * 100, 4),
        "below_lower_rows": int((cr["_毛利率"] < CLIP_LOWER).sum()),
        "above_upper_rows": int((cr["_毛利率"] > CLIP_UPPER).sum()),
    }

    # 极端行画像（|毛利率| > 0.75 即超出钳制带；含小分母噪声指标）
    extreme = cr[cr["_毛利率"].abs() > CLIP_UPPER]
    small_denom = extreme[(extreme["金额"].abs() < 1000)]  # 金额<1000 视为小分母/噪声行
    out["extreme"] = {
        "rows": int(len(extreme)),
        "rows_pct": round(len(extreme) / len(cr) * 100, 4),
        "rev": float(extreme["金额"].sum()),
        "rev_pct": round(float(extreme["金额"].sum()) / rev_total * 100, 4),
        "profit": float(extreme["利润"].sum()),
        "abs_margin_gt_1_rows": int((cr["_毛利率"].abs() > 1).sum()),
        "small_denom_rows": int(len(small_denom)),
        "small_denom_rev_pct": round(float(small_denom["金额"].sum()) / rev_total * 100, 4),
        "median_amount": round(float(extreme["金额"].median()), 2),
    }

    # 产品风险评分（4 因素）分布与迁移矩阵（行级近似，复用 v4.0 现役评分函数）
    risk = _risk_approx(cr, data_month)
    out["risk"] = risk

    # 图表压缩专项（基于 gold_product_portrait 产品级分布）
    out["chart"] = _chart_compression(gpp)
    return out


def _risk_approx(cr, data_month):
    """产品风险评分（行级近似）：按产品月聚合 → 4 因素 → v4.0 评分函数。

    近似方法：slope = 月毛利率线性回归斜率；decay_pp = 近3月毛利率均值 - 前3月毛利率均值(pp)；
    yoy_change = 近12月收入同比；self_health = 近3月毛利率 / 全期毛利率；
    c6 = 近3月数量环比。clip 口径下用钳制后利润重算月毛利率。
    """
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                    "sales_analytics_platform", "processing"))
    from shared.risk_scoring import compute_composite_v2

    cr = cr.copy()
    cr["_ym"] = cr["_ym"].astype(str)
    profit_clip = _apply_clip_profit(cr)

    def score_all(profit_series, label):
        sub = cr.copy()
        sub["利润"] = profit_series
        pm = sub.groupby(["产品品种", "_ym"]).agg(
            qty=("数量", "sum"), rev=("金额", "sum"), profit=("利润", "sum")).reset_index()
        pm = pm.sort_values(["产品品种", "_ym"])
        scores = {}
        for prod, g in pm.groupby("产品品种"):
            scores[prod] = _product_risk(g)
        s = pd.Series(scores, dtype=float)
        return s

    base = score_all(cr["利润"], "no_clip")
    clipped = score_all(profit_clip, "clip")

    def level_of(x):
        for name, lo, hi in RISK_LEVELS:
            if lo <= x < hi:
                return name
        return "极高"

    dist = lambda s: dict(s.map(level_of).value_counts().reindex(
        ["低", "中", "高", "极高"]).fillna(0).astype(int).to_dict())
    levels = ["低", "中", "高", "极高"]
    mig = pd.crosstab(base.map(level_of), clipped.map(level_of)).reindex(
        index=levels, columns=levels).fillna(0).astype(int)
    out = {
        "approx_method": "行级近似（产品月聚合 + v4.0 现役评分函数，非 profiling 精确面板）",
        "n_products": int(len(base)),
        "mean_score": {"no_clip": round(float(base.mean()), 2),
                       "clip": round(float(clipped.mean()), 2),
                       "clip_minus_noclip": round(float(clipped.mean() - base.mean()), 2)},
        "dist": {"no_clip": dist(base), "clip": dist(clipped)},
        "migration_matrix": {"levels": levels, "matrix": mig.values.tolist()},
        "products_risk_level_changed": int((base.map(level_of) != clipped.map(level_of)).sum()),
    }
    return out


def _product_risk(g):
    """单产品 4 因素 → v4.0 综合评分（近似）。"""
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                    "sales_analytics_platform", "processing"))
    from shared.risk_scoring import compute_composite_v2
    if len(g) < 3:
        return np.nan
    rev = g["rev"].to_numpy(dtype=float)
    profit = g["profit"].to_numpy(dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        m = np.where(rev != 0, profit / np.where(rev != 0, rev, np.nan), np.nan)
    finite = np.isfinite(m)
    # 斜率：月毛利率线性回归
    if finite.sum() >= 3:
        idx = np.arange(len(m))[finite]
        slope = np.polyfit(idx, m[finite], 1)[0]
    else:
        slope = np.nan
    # 近3月 vs 前3月毛利率
    rec = m[-3:][np.isfinite(m[-3:])]
    pri = m[-6:-3][np.isfinite(m[-6:-3])]
    decay_pp = (rec.mean() - pri.mean()) * 100 if len(rec) and len(pri) else np.nan
    # 同比（近12月 vs 前12月收入）
    if len(rev) >= 12:
        yoy = (rev[-12:].sum() - rev[-24:-12].sum()) / rev[-24:-12].sum() if rev[-24:-12].sum() else np.nan
    elif len(rev) >= 6:
        yoy = (rev[-6:].sum() - rev[:-6].sum()) / rev[:-6].sum() if rev[:-6].sum() else np.nan
    else:
        yoy = np.nan
    # 自比健康度：近3月毛利率 / 全期毛利率
    overall = m[finite].mean() if finite.any() else np.nan
    self_health = rec.mean() / overall if len(rec) and overall else np.nan
    # c6：近3月数量环比
    q = g["qty"].to_numpy(dtype=float)
    if len(q) >= 6:
        c6 = (q[-3:].sum() - q[-6:-3].sum()) / q[-6:-3].sum() if q[-6:-3].sum() else np.nan
    else:
        c6 = np.nan
    r = compute_composite_v2(
        slope_ratio=slope, decay_pp=decay_pp, yoy_change=yoy, self_health=self_health,
        c6_raw=c6, c6_available=True, zero_profit=False, slope_insufficient=not np.isfinite(slope),
        hist_margin_invalid=False)
    return r["score_v2"]


def _chart_compression(gpp):
    """图表压缩专项：产品级 近12月毛利率% / ASP趋势%/月 的坐标轴对比与极端散点。"""
    out = {}
    for col, key in [("近12月毛利率%", "margin"), ("ASP趋势%/月", "asp")]:
        s = pd.to_numeric(gpp[col], errors="coerce").dropna()
        if len(s) == 0:
            out[key] = {"n": 0}
            continue
        p1, p99 = s.quantile(0.01), s.quantile(0.99)
        mn, mx = s.min(), s.max()
        out[key] = {
            "n": int(len(s)),
            "min": round(float(mn), 2), "p1": round(float(p1), 2),
            "p99": round(float(p99), 2), "max": round(float(mx), 2),
            "axis_no_clip_range": round(float(mx - mn), 2),
            "axis_p1p99_range": round(float(p99 - p1), 2),
            "extreme_below_p1": int((s < p1).sum()),
            "extreme_above_p99": int((s > p99).sum()),
            "extreme_pct": round(float(((s < p1) | (s > p99)).sum()) / len(s) * 100, 2),
        }
    # 钳制带外产品（图表若按钳制带截断）
    m = pd.to_numeric(gpp["近12月毛利率%"], errors="coerce")
    out["outside_clip_band_products"] = {
        "below_-50pct": int((m < CLIP_LOWER * 100).sum()),
        "above_75pct": int((m > CLIP_UPPER * 100).sum()),
        "total_pct": round(float(((m < CLIP_LOWER * 100) | (m > CLIP_UPPER * 100)).sum())
                           / m.notna().sum() * 100, 2),
    }
    return out


# ══════════════════════════════════════════════════════════════════
# 综合：2×2 组合主表 + D-4
# ══════════════════════════════════════════════════════════════════

def compute_combo(cr, data_month):
    """D-2 {保留, 过滤} × D-1 {不钳制, 数据层钳制} 的组合：收入/毛利/毛利率/风险均值。"""
    cr = cr.copy()
    cr["_ym"] = cr["_ym"].astype(str)
    profit_clip = _apply_clip_profit(cr)

    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                    "sales_analytics_platform", "processing"))
    from shared.risk_scoring import compute_composite_v2

    combos = []
    for d2_name, sub in [("keep", cr), ("filter", cr[cr["数量"] > 0])]:
        sub = sub.copy()
        for d1_name, profit_src in [("no_clip", sub["利润"]), ("clip", profit_clip.reindex(sub.index))]:
            rev = float(sub["金额"].sum())
            profit = float(profit_src.sum())
            # 风险均值（行级近似，仅对 保留 口径全量算；过滤口径复用保留的因子近似标注）
            score = _combo_risk_mean(sub, profit_src, data_month, compute_composite_v2)
            combos.append({
                "D2": d2_name, "D1": d1_name,
                "rev": round(rev, 2), "rev_wan": round(rev / 1e4, 2),
                "profit": round(profit, 2), "profit_wan": round(profit / 1e4, 2),
                "margin_pct": round(_margin_pct(profit, rev), 4),
                "risk_mean_approx": score,
                "rows": int(len(sub)),
            })
    return {"combos": combos, "note": "风险均值=行级近似（见 risk.approx_method）"}


def _combo_risk_mean(sub, profit_series, data_month, compute_composite_v2):
    """组合口径下的产品风险均值（行级近似）。"""
    s = sub.copy()
    s["利润"] = profit_series
    pm = s.groupby(["产品品种", "_ym"]).agg(
        qty=("数量", "sum"), rev=("金额", "sum"), profit=("利润", "sum")).reset_index()
    pm = pm.sort_values(["产品品种", "_ym"])
    scores = []
    for _, g in pm.groupby("产品品种"):
        r = _product_risk(g)
        if np.isfinite(r):
            scores.append(r)
    return round(float(np.mean(scores)), 2) if scores else None


def check_d4(platform_dir):
    """D-4：config.xlsx 现状核查。"""
    cfg_xlsx = os.path.join(platform_dir, "config.xlsx")
    # 也查 processing 下与可能的配置位置
    candidates = [cfg_xlsx,
                  os.path.join(platform_dir, "processing", "config.xlsx"),
                  os.path.join(platform_dir, "data", "config.xlsx")]
    existing = [c for c in candidates if os.path.exists(c)]
    return {
        "config_xlsx_exists": bool(existing),
        "existing_paths": existing,
        "note": "product_lifecycle/run.py 的 load_config_from_xlsx 目前只作为兼容入口存在，"
                "config.xlsx 不存在时回退 PRODUCT_LIFECYCLE 配置；属业务确认项（D-4）。",
    }


# ══════════════════════════════════════════════════════════════════
# 主流程
# ══════════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser(description="口径决策预演（D-1/D-2/D-4）")
    ap.add_argument("--platform-dir", default=DEFAULT_PLATFORM,
                    help=f"销售分析平台目录（默认 {DEFAULT_PLATFORM}）")
    ap.add_argument("--out-json", default=None,
                    help="JSON 输出路径（默认系统临时目录 impact_rehearsal_YYYYMMDD.json）")
    args = ap.parse_args()

    platform = os.path.abspath(args.platform_dir)
    t_all = time.time()

    # 生产路径 sys.path（processing/ 为共享模块根）
    sys.path.insert(0, os.path.join(platform, "processing"))

    from shared.data_cleaning import SILVER_DTYPE_CUSTOMER_X_PRODUCT, SILVER_DTYPE_PRODUCT_MONTHLY

    # ── 加载（生产路径：load_silver_table，优先 parquet；gold 直接读 CSV）──
    cr = _load_silver(platform, "silver_cleaned_rows.csv", dtype=None)
    cxp = _load_silver(platform, "silver_customer_x_product.csv", dtype=SILVER_DTYPE_CUSTOMER_X_PRODUCT)
    pm = _load_silver(platform, "silver_product_monthly.csv", dtype=SILVER_DTYPE_PRODUCT_MONTHLY)
    gpp = _load_gold_csv(platform, "gold_product_portrait.csv")

    cr = cr.copy()
    cr["发货日期"] = pd.to_datetime(cr["发货日期"], errors="coerce")
    cr["_ym"] = cr["发货日期"].dt.strftime("%Y-%m")
    data_month = cr["_ym"].max()

    # 基线对账（baseline\20260818_batch1 锚点：YTD 收入≈43080.6万 / 毛利率≈34.4% / 客户数 3143）
    ytd = cr[_ytd_mask(cr, data_month)]
    ytd_rev_wan = float(ytd["金额"].sum()) / 1e4
    ytd_margin = _margin_pct(float(ytd["利润"].sum()), float(ytd["金额"].sum()))
    n_cust_full = int(cr["客户编号"].nunique())
    n_cust_ytd = int(ytd["客户编号"].nunique())
    anchors = {"ytd_rev_wan": 43080.6, "ytd_margin_pct": 34.4, "n_customers": 3143}
    base_check = {
        "data_month": data_month,
        "ytd_rev_wan": round(ytd_rev_wan, 2),
        "ytd_margin_pct": round(ytd_margin, 2),
        "n_customers_full": n_cust_full,
        "n_customers_ytd": n_cust_ytd,
        "vs_anchor_rev_pct": round((ytd_rev_wan - anchors["ytd_rev_wan"]) / anchors["ytd_rev_wan"] * 100, 4),
        "vs_anchor_margin_pp": round(ytd_margin - anchors["ytd_margin_pct"], 4),
        "vs_anchor_customers": n_cust_full - anchors["n_customers"],
    }

    # ── 计算 ──
    d2 = compute_d2(cr, data_month)
    d1 = compute_d1(cr, data_month, gpp)
    combo = compute_combo(cr, data_month)
    d4 = check_d4(platform)

    result = {
        "generated_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "platform_dir": platform,
        "loaded": {"cleaned_rows": int(len(cr)), "rows_cxp": int(len(cxp)), "rows_pm": int(len(pm))},
        "data_month": data_month,
        "clip_thresholds": {"lower": CLIP_LOWER, "upper": CLIP_UPPER},
        "method_notes": {
            "D2_aggregates": "精确重算（cleaned_rows 行级聚合）",
            "D2_nine_grid": "行级近似（简化动能/盈利健康代理分类）",
            "D1_risk": "行级近似（产品月聚合 + v4.0 现役评分函数）",
            "D1_chart": "基于 gold_product_portrait 产品级分布",
        },
        "baseline_check": base_check,
        "D2": d2,
        "D1": d1,
        "combo_2x2": combo,
        "D4": d4,
    }

    # ── 写 JSON ──
    if args.out_json:
        json_path = os.path.abspath(args.out_json)
    else:
        tmp = os.environ.get("TEMP") or os.environ.get("TMP") or "/tmp"
        json_path = os.path.join(tmp, f"impact_rehearsal_{datetime.datetime.now().strftime('%Y%m%d')}.json")
    os.makedirs(os.path.dirname(json_path), exist_ok=True)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"[JSON] {json_path}")

    # ── 打印摘要 ──
    print("=" * 70)
    print("口径决策预演摘要（数据月份 %s，共 %d 行）" % (data_month, len(cr)))
    print("=" * 70)
    print(f"基线对账: YTD收入 {base_check['ytd_rev_wan']}万(锚43080.6, 差{base_check['vs_anchor_rev_pct']}%) | "
          f"毛利率 {base_check['ytd_margin_pct']}%(锚34.4) | 客户数 {base_check['n_customers_full']}(锚3143)")
    print(f"\n[D-2 负数量] 负数量行 {d2['neg_rows']} 行, 金额 {d2['neg_amount']/1e4:.2f}万(占收入 {d2['neg_amount_pct_rev']:.3f}%)")
    kf = d2["full_period"]["keep_minus_filter"]
    yf = d2["ytd"]["keep_minus_filter"]
    print(f"  全期 保留vs过滤: 收入差 {kf['rev_diff']/1e4:.2f}万({kf['rev_diff_pct']:.3f}%), "
          f"毛利差 {kf['profit_diff']/1e4:.2f}万({kf['profit_diff_pct']:.3f}%), "
          f"毛利率差 {kf['margin_pct_diff_pp']:.3f}pp")
    print(f"  YTD  保留vs过滤: 收入差 {yf['rev_diff']/1e4:.2f}万({yf['rev_diff_pct']:.3f}%), "
          f"毛利差 {yf['profit_diff']/1e4:.2f}万({yf['profit_diff_pct']:.3f}%), "
          f"毛利率差 {yf['margin_pct_diff_pp']:.3f}pp")
    mm = d2["monthly"]
    print(f"  月度收入最大单月偏差 {mm['max_month_deviation_amount']/1e4:.2f}万({mm['max_month_deviation_month']}), "
          f"符号翻转月 收入{mm['sign_flip_months_rev']}/毛利{mm['sign_flip_months_profit']}")
    ng = d2["nine_grid"]
    print(f"  9宫格阶段迁移: {ng['stage_change_count']} 个产品({ng['stage_change_pct']}%) 阶段变化(行级近似)")
    print(f"\n[D-1 毛利率钳制] 分布 p1={d1['margin_dist']['p1']} p5={d1['margin_dist']['p5']} "
          f"p50={d1['margin_dist']['p50']} p95={d1['margin_dist']['p95']} p99={d1['margin_dist']['p99']}")
    c = d1["clip"]
    print(f"  被钳行 {c['clipped_rows']} 行({c['clipped_rows_pct']}%), 收入占 {c['clipped_rev_pct']}%, 利润占 {c['clipped_profit_pct']}%")
    e = d1["extreme"]
    print(f"  极端行(|毛利率|>0.75) {e['rows']} 行, 收入占 {e['rev_pct']}%, 小分母(<1000) {e['small_denom_rows']} 行")
    r = d1["risk"]
    print(f"  风险评分均值: 不钳制 {r['mean_score']['no_clip']} vs 钳制 {r['mean_score']['clip']} "
          f"(差 {r['mean_score']['clip_minus_noclip']:+})，等级变动 {r['products_risk_level_changed']} 个产品(近似)")
    ch = d1["chart"]
    for key in ("margin", "asp"):
        if key in ch:
            cc = ch[key]
            print(f"  图表压缩[{key}]: 轴 不钳制({cc['min']}~{cc['max']}) vs p1~p99({cc['p1']}~{cc['p99']}), "
                  f"极端点 {cc['extreme_below_p1']}+{cc['extreme_above_p99']}={cc['extreme_pct']}%")
    print(f"\n[2×2 组合]")
    for cb in combo["combos"]:
        print(f"  D2={cb['D2']:<6} D1={cb['D1']:<7} 收入 {cb['rev_wan']:>10,.2f}万 | 毛利 {cb['profit_wan']:>10,.2f}万 | "
              f"毛利率 {cb['margin_pct']:>7.3f}% | 风险均值 {cb['risk_mean_approx']}")
    print(f"\n[D-4] config.xlsx 存在: {d4['config_xlsx_exists']}；{d4['note']}")
    print(f"\n总耗时 {time.time() - t_all:.1f}s")


if __name__ == "__main__":
    main()


