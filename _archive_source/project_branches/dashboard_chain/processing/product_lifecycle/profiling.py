"""
产品画像核心引擎 — v4.0: 4因子(毛利率斜率+增速衰减+自比健康度+订货量变化)风险评分。

从v2.8的run_profiling解耦重写，v4.0新增订货量变化因子和增速衰减+毛利率斜率覆盖规则。
使用共享Silver层作为输入，输出产品快照表至Gold层。
(P0-04 Phase 1: 参照组、画像分类、风险评分已提取为独立函数)
"""

import time
import pandas as pd
import numpy as np

from shared.calc_utils import calc_slope, calc_age_months
from shared.classifiers import classify_slope_level
from shared.risk_scoring import (
    # v4.0新函数
    score_slope_v2, score_decay_v2, score_self_health_v2, score_c6_v2,
    # v2.9旧函数(向后兼容)
    risk_slope, risk_decay, risk_self_health,
)
# v4.0: CV(波动性), ASP(单价趋势)因子已移除
from shared.pricing import calc_asp_trend, calc_price_elasticity, calc_order_frequency_trend
from shared.forecasting import ets_forecast, weighted_ma_forecast, prepare_holiday_adjustment
from product_lifecycle.nine_grid import classify_9grid_full
from product_lifecycle.notes import generate_specific_note


# ============================================================
# Helper functions extracted from run_profiling (P0-04 Phase 1)
# ============================================================

def _compute_reference_groups(result_df, df, ref_priority, name_col,
                              products, latest_month, thr):
    """计算参照组加权均值与公司均值（P0-04提取）。"""
    exit_cutoff_pre = latest_month - int(thr.get("exit_months", 12))
    exit_min_hist_pre = int(thr.get("exit_min_age_months", 3))
    not_new = result_df.copy()
    if "当前画像" in result_df.columns:
        not_new = result_df[~result_df["当前画像"].isin(["新品观察", "清仓/偶发"])].copy()
    not_new = not_new[
        ~((not_new["_最后发货月"] <= exit_cutoff_pre) &
          (not_new["日历月龄"] >= exit_min_hist_pre))
    ].copy()

    if len(not_new) == 0:
        print("[警告] 所有产品均为新品观察，无足够产品计算参照组均值。")
        for i in result_df.index:
            result_df.at[i, "参照组加权均值%"] = 0
            result_df.at[i, "参照组均值来源"] = "无足够产品（全部为新品观察）"
            result_df.at[i, "他比健康度(pp)"] = 0
            result_df.at[i, "公司加权均值%"] = 0
            result_df.at[i, "vs公司均值(pp)"] = 0
        return 0, {}, {}

    valid_mask = pd.notna(not_new["_margin"]) & (not_new["_rev"] > 0)
    all_margins = not_new.loc[valid_mask, "_margin"].tolist()
    all_revs = not_new.loc[valid_mask, "_rev"].tolist()
    company_avg = sum(m * r for m, r in zip(all_margins, all_revs)) / sum(all_revs) if sum(all_revs) > 0 else 0

    all_ref_cols = set()
    for ref_col_name, _ in ref_priority:
        if ref_col_name != "（全公司均值）" and ref_col_name in df.columns:
            all_ref_cols.add(ref_col_name)

    product_groups = {}
    for ref_col in all_ref_cols:
        if ref_col in df.columns:
            mode_series = df.groupby(name_col)[ref_col].apply(
                lambda x: x.mode().iloc[0] if not x.mode().empty else "未分类"
            )
            prod_group_map = mode_series.to_dict()
            for p in products:
                if p not in prod_group_map:
                    prod_group_map[p] = "未分类"
        else:
            prod_group_map = {p: "未分类" for p in products}
        product_groups[ref_col] = prod_group_map

    group_stats = {}
    for ref_col in all_ref_cols:
        grp_map = product_groups[ref_col]
        valid = not_new[pd.notna(not_new["_margin"]) & (not_new["_rev"] > 0)].copy()
        if len(valid) == 0:
            continue
        valid["_grp"] = valid["产品名称"].map(grp_map).fillna("未分类")
        valid["_w_product"] = valid["_margin"] * valid["_rev"]
        grp_agg = valid.groupby("_grp").agg(
            count=("_w_product", "count"),
            rev_sum=("_rev", "sum"),
            weighted_sum=("_w_product", "sum")
        )
        for grp_val, r in grp_agg.iterrows():
            wavg = r["weighted_sum"] / r["rev_sum"] if r["rev_sum"] > 0 else 0
            group_stats[(ref_col, grp_val)] = {
                "count": int(r["count"]),
                "weighted_avg": wavg
            }

    return company_avg, product_groups, group_stats


def _score_all_products(result_df, thr, wgt, ref_priority, df,
                         product_groups, group_stats, company_avg,
                         latest_month):
    """第二循环：参照组赋值 → 他比健康度 → 退市 → 九宫格 → 风险评分（P0-04提取）。"""
    _ref_col_display = {
        "产品二级分类": "产品系列",
    }

    tg = float(thr.get("growth_accelerate", 0.15))
    tf = float(thr.get("growth_flat_lower", -0.10))
    th_h = float(thr.get("health_healthy", 0.70))
    th_s = float(thr.get("health_severe", 0.50))
    th_r = float(thr.get("health_relative", -10))

    exit_months_val = int(thr.get("exit_months", 12))
    exit_min_hist = int(thr.get("exit_min_age_months", 3))
    exit_cutoff = latest_month - exit_months_val

    for _col in ["参照组加权均值%", "参照组均值来源", "他比健康度(pp)", "公司加权均值%", "vs公司均值(pp)",
                   "_退市", "_产品寿命月", "销量动能", "盈利健康",
                   "毛利率斜率得分", "增速衰减得分",
                   "自比健康度得分", "订货量变化得分",
                   "_w_斜率", "_w_衰减", "_w_自比健康度", "_w_c6", "_w_sum"]:
        if _col not in result_df.columns:
            result_df[_col] = None

    for i, row in result_df.iterrows():
        if row.get("当前画像") in ["新品观察", "清仓/偶发"]:
            continue

        prod_name = row["产品名称"]

        ref_assigned = False
        for ref_col_name, min_n in ref_priority:
            if ref_col_name == "（全公司均值）":
                result_df.at[i, "参照组加权均值%"] = company_avg
                result_df.at[i, "参照组均值来源"] = "全公司均值（兜底）"
                ref_assigned = True
                break
            if ref_col_name not in df.columns:
                continue
            grp_val = product_groups.get(ref_col_name, {}).get(prod_name, "未分类")
            stats = group_stats.get((ref_col_name, grp_val))
            if stats and stats["count"] >= min_n:
                result_df.at[i, "参照组加权均值%"] = stats["weighted_avg"]
                display_name = _ref_col_display.get(ref_col_name, ref_col_name)
                result_df.at[i, "参照组均值来源"] = f"{display_name}: {grp_val} (n={stats['count']})"
                ref_assigned = True
                break
        if not ref_assigned:
            result_df.at[i, "参照组加权均值%"] = company_avg
            result_df.at[i, "参照组均值来源"] = "全公司均值（各级参照组均不满足条件）"

        margin = row["_margin"]
        cat_avg_val = result_df.at[i, "参照组加权均值%"]
        if pd.notna(margin) and pd.notna(cat_avg_val) and cat_avg_val > 0:
            rel_health = (margin - cat_avg_val) * 100
        else:
            rel_health = 0
        result_df.at[i, "他比健康度(pp)"] = rel_health
        result_df.at[i, "公司加权均值%"] = company_avg
        result_df.at[i, "vs公司均值(pp)"] = (margin - company_avg) * 100

        last_m = row.get("_最后发货月")
        first_m = row.get("_首次发货月")
        age = calc_age_months(first_m, last_m)
        if pd.notna(last_m) and pd.notna(first_m):
            is_exited = (last_m <= exit_cutoff) and (age >= exit_min_hist)
            result_df.at[i, "_退市"] = is_exited
            if is_exited:
                result_df.at[i, "_产品寿命月"] = age
        else:
            result_df.at[i, "_退市"] = False

        g = row["近12月增长率%"]
        if g > tg:
            m_full, m_short = "加速增长", "量增"
        elif g > 0:
            m_full, m_short = "稳定扩张", "量增"
        elif g > tf:
            m_full, m_short = "持平", "量稳"
        else:
            m_full, m_short = "萎缩", "量跌"

        sh = row["自比健康度%"]
        rh = result_df.at[i, "他比健康度(pp)"]
        is_severe = sh < th_s or rh < th_r
        if is_severe:
            h_full, h_short = "严重侵蚀", "利跌"
        elif sh >= th_h and rh >= 0:
            h_full, h_short = "健康", "利稳"
        else:
            h_full, h_short = "轻度侵蚀", "利稳"

        result_df.at[i, "销量动能"] = m_full
        result_df.at[i, "盈利健康"] = h_full

        portrait, summary, strategy = classify_9grid_full(m_full, h_full, row=result_df.iloc[i])
        result_df.at[i, "当前画像"] = portrait
        result_df.at[i, "管理层摘要"] = summary
        result_df.at[i, "通用策略建议"] = strategy

        # ── 毛利率斜率得分 (v4.0: 合并20/50分桶) ──
        if row.get("_slope_data_insufficient"):
            s1 = int(thr.get("slope_insufficient_score", 50))
        elif row.get("斜率等级") == "无利润/异常":
            s1 = 80
        else:
            s1 = score_slope_v2(
                row["_slope_ratio"],
                zero_profit=row.get("_zero_profit", False),
                slope_insufficient=False,
            )

        # ── 增速衰减得分 (v4.0: 数据驱动评分矩阵 + 内置连续下降加成) ──
        s4 = score_decay_v2(
            row.get("增速衰减(pp)"),
            row.get("_yoy_change"),
            consecutive_months=int(row.get("连续下降月数", 0)),
        )

        # v4.0: 爆炸增长截断 (防止高增产品误报)
        growth_cap = float(thr.get("decay_explosive_cap", 1.0))
        decay_thresh = float(thr.get("decay_explosive_threshold", -100))
        s4_cap = int(thr.get("decay_explosive_s4_cap", 50))
        if row["近12月增长率%"] > growth_cap and row["增速衰减(pp)"] < decay_thresh:
            last3_growth_ratio = row.get("_yoy_change")
            if last3_growth_ratio is not None and pd.notna(last3_growth_ratio) and last3_growth_ratio <= 0:
                result_df.at[i, "_decay_cap_removed"] = True
            else:
                s4 = min(s4, s4_cap)
                result_df.at[i, "_decay_cap_removed"] = False

        # ── 自比健康度得分 (v4.0: 修复顶部反转，<30%=70分) ──
        s_sh = score_self_health_v2(
            row.get("自比健康度%"),
            hist_margin_invalid=row.get("_no_valid_hist_margin", False),
        )

        # ── 订货量变化得分 (v4.0新增) ──
        c6_raw = row.get("c6_order_qty_change")
        c6_avail = not (c6_raw is None or pd.isna(c6_raw))
        s_c6 = score_c6_v2(c6_raw) if c6_avail else 0

        result_df.at[i, "毛利率斜率得分"] = round(s1)
        result_df.at[i, "增速衰减得分"] = round(s4)
        result_df.at[i, "自比健康度得分"] = round(s_sh)
        result_df.at[i, "订货量变化得分"] = round(s_c6) if c6_avail else "无数据"

        # ── 权重 (v4.0: 4因子, 从config读取) ──
        w1 = wgt.get("毛利率趋势斜率", 0.100)
        w4 = wgt.get("增速衰减", 0.600)
        w_sh = wgt.get("自比健康度", 0.200)
        w_c6 = wgt.get("c6", 0.100) if c6_avail else 0.0

        slope_reliable = not row.get("_slope_data_insufficient", False) and not row.get("_zero_profit", False)
        decay_reliable = True
        sh_reliable = not row.get("_no_valid_hist_margin", False)

        w = [w1, w4, w_sh]
        scores = [s1, s4, s_sh]
        reliable = [slope_reliable, decay_reliable, sh_reliable]
        for idx in range(3):
            if not reliable[idx]:
                w[idx] = 0.0

        if w_c6 > 0:
            w.append(w_c6)
            scores.append(s_c6)

        sum_w = sum(w)
        if sum_w > 0:
            w = [wi / sum_w for wi in w]

        result_df.at[i, "_w_斜率"] = round(w[0], 4)
        result_df.at[i, "_w_衰减"] = round(w[1], 4)
        result_df.at[i, "_w_自比健康度"] = round(w[2], 4) if len(w) > 2 else 0
        if len(w) > 3:
            result_df.at[i, "_w_c6"] = round(w[3], 4)
        else:
            result_df.at[i, "_w_c6"] = 0.0
        result_df.at[i, "_w_sum"] = round(sum_w, 4)

        total = sum(s * wi for s, wi in zip(scores, w))
        result_df.at[i, "综合评分"] = round(total, 1)

        # ── 衰退期最低风险兜底 ──
        if result_df.at[i, "当前画像"] == "衰退期":
            margin_val = row.get("近12月毛利率%", 0) or 0
            qty_val = row.get("近12月销量", 0) or 0
            exit_min_risk = int(thr.get("decay_portrait_min_risk", 50))
            if margin_val <= 0 or qty_val <= 0:
                non_sh_weights = [w[idx] for idx in range(len(w)) if idx != 2]
                non_sh_scores = [scores[idx] for idx in range(len(scores)) if idx != 2]
                non_sh_sum = sum(non_sh_weights)
                if non_sh_sum > 0:
                    non_sh_score = sum(s * wgt_i for s, wgt_i in zip(non_sh_scores, non_sh_weights)) / non_sh_sum
                    if non_sh_score < exit_min_risk:
                        total = max(exit_min_risk, total)
        result_df.at[i, "综合评分"] = round(total, 1)

        # ── 贡献度 & 主导因子 ──
        contributions = {
            "毛利率斜率": scores[0] * w[0],
            "增速衰减":   scores[1] * w[1],
            "自比健康度": scores[2] * w[2] if len(w) > 2 else 0,
        }
        if len(w) > 3:
            contributions["订货量变化"] = scores[3] * w[3]
        dominant = max(contributions, key=contributions.get)
        result_df.at[i, "风险主导因子"] = dominant

        # ── 综合风险等级 (v4.0阈值: [55, 65, 68]) ──
        t_low = float(thr.get("risk_low_max", 55))
        t_mid = float(thr.get("risk_mid_max", 65))
        t_high = float(thr.get("risk_high_max", 68))

        # ── 覆盖规则: 增速衰减≥80 & 毛利率斜率≥70 → 自动极高风险 ──
        # (捕捉增速衰减高但总分在阈值附近的衰退产品)
        if total <= t_high and s4 >= 80 and s1 >= 70:
            total = max(total, t_high + 1)
            result_df.at[i, "综合评分"] = round(total, 1)
            result_df.at[i, "_override_extreme"] = True
        else:
            result_df.at[i, "_override_extreme"] = False
        if total <= t_low:
            result_df.at[i, "综合风险等级"] = "低风险"
        elif total <= t_mid:
            result_df.at[i, "综合风险等级"] = "中风险"
        elif total <= t_high:
            result_df.at[i, "综合风险等级"] = "高风险"
        else:
            result_df.at[i, "综合风险等级"] = "极高风险"

        result_df.at[i, "特情说明"] = generate_specific_note(result_df.iloc[i], thr)

        quality_flags = []
        if row.get("_zero_profit"):
            quality_flags.append("ZP")
        if row.get("_negative_margin"):
            quality_flags.append("NM")
        if row.get("_slope_data_insufficient"):
            quality_flags.append("SL")
        # v4.0: F3/F6已移除, CV/AS标记不再使用
        # if row.get("_cv_invalid"):
        #     quality_flags.append("CV")
        # if row.get("_asp_insufficient"):
        #     quality_flags.append("AS")
        if row.get("_growth_clamped"):
            quality_flags.append("GC")
        if row.get("近12月销量", 0) == 0 and row.get("当前画像") not in ["新品观察", "清仓/偶发"]:
            quality_flags.append("ZS")
        if row.get("_no_valid_hist_margin"):
            quality_flags.append("NH")
        result_df.at[i, "数据质量标记"] = ",".join(quality_flags) if quality_flags else "全部可靠"


def _finalize_output(result_df, thr):
    """输出列整理与格式化（P0-04提取）。"""
    min_products_ref = int(thr.get("ref_min_products", 3))
    exited_df = result_df[result_df["_退市"] == True]
    group_lifespan = {}
    if len(exited_df) > 0:
        for grp, grp_data in exited_df.groupby("_ref_group"):
            lifespans = grp_data["_产品寿命月"].dropna()
            if len(lifespans) >= min_products_ref:
                group_lifespan[grp] = lifespans.median()

    output_cols = [
        "产品名称", "所属参照组", "帕累托分类",
        "最新数据月份", "日历月龄", "活跃月数",
        "首次6K日期", "首次6K用时(月)", "是否已达6K",
        "当前画像", "管理层摘要", "销量动能", "盈利健康",
        "近12月销量", "前12月销量",
        "连续下降月数",  # 下跌趋势的持续时间
        "近12月增长率%", "前12月增长率%", "增速方向", "增速变化(pp)", "增速衰减(pp)", "低量品标记",
        "近12月销售额", "前12月销售额", "营收增长率%", "营收-毛利综合判断",
        "当月毛利率%", "近12月毛利率%",
        "前12月毛利率%", "毛利率同比变化(pp)",
        "历史参照毛利率%", "长期参照毛利率%",
        "自比健康度%", "他比健康度(pp)",
        "参照组加权均值%", "参照组均值来源",
        "公司加权均值%", "vs公司均值(pp)",
        "毛利率趋势斜率%/月", "斜率等级",
        "ASP趋势%/月",
        "ASP趋势方向", "ASP-毛利率联合诊断",
        "客户集中度-前1大%", "客户集中度-前3大%",
        "订货波动性CV",
        "近3月月均订单数", "订单频次变化%", "采购意愿",
        "价格弹性系数", "价格敏感度",
        "综合评分", "综合风险等级", "风险主导因子",
        "毛利率斜率得分", "增速衰减得分",
        "自比健康度得分", "订货量变化得分",
        "通用策略建议", "特情说明",
        "数据质量标记",
    ]

    output_cols = [c for c in output_cols if c in result_df.columns]
    out = result_df[output_cols].copy()

    ratio_cols = [
        "近12月增长率%", "前12月增长率%",
        "营收增长率%",
        "自比健康度%",
        "当月毛利率%", "近12月毛利率%", "前12月毛利率%",
        "历史参照毛利率%", "长期参照毛利率%",
        "参照组加权均值%", "公司加权均值%",
        "客户集中度-前1大%", "客户集中度-前3大%",
    ]

    pp_cols = [
        "增速变化(pp)", "增速衰减(pp)",
        "他比健康度(pp)", "vs公司均值(pp)",
        "毛利率同比变化(pp)",
        "毛利率趋势斜率%/月",
        "ASP趋势%/月",
    ]

    for c in ratio_cols:
        if c in out.columns:
            out[c] = out[c].apply(lambda x: round(x * 100, 2) if pd.notna(x) else x)

    for c in pp_cols:
        if c in out.columns:
            out[c] = out[c].apply(lambda x: round(x, 2) if pd.notna(x) else x)

    if "订货波动性CV" in out.columns:
        out["订货波动性CV"] = out["订货波动性CV"].apply(
            lambda x: round(x, 3) if pd.notna(x) else x
        )

    return out, ratio_cols, pp_cols


def _calc_forecast_extras(monthly_qty_arr, monthly_prices, pm, last3_mask,
                          prod, thr, latest_month, mode, order_col):
    """计算 ETS预测、价格弹性、订单频次。返回 row_out 更新字典。"""
    if mode != "full":
        return {}

    extras = {}
    pred_months = int(thr.get("forecast_months", 3))
    seasonal_p = int(thr.get("ets_seasonal_periods", 0))
    ma_window = int(thr.get("forecast_ma_window", 3))

    try:
        ets_result = ets_forecast(monthly_qty_arr, periods=pred_months, seasonal_periods=seasonal_p)
    except (ValueError, np.linalg.LinAlgError, RuntimeError) as _e:
        print(f"  [警告] 产品 '{prod}' ETS预测失败: {_e}")
        ets_result = None
    if ets_result and ets_result[0] is not None:
        forecast_vals, direction, pred_intervals, model_info = ets_result
        forecast_periods = [latest_month + i + 1 for i in range(pred_months)]
        holiday_adjs = prepare_holiday_adjustment(monthly_qty_arr, [latest_month - 11 + i for i in range(12)], forecast_periods, thr)
        adjusted_forecast = [max(0, round(v * adj, 0)) for v, adj in zip(forecast_vals, holiday_adjs)]

        extras["预测算法"] = "ETS+节假日调整"
        extras["预测模型类型"] = model_info.get("model_type", "")
        extras["预测_AIC"] = model_info.get("aic")
        for i in range(pred_months):
            extras[f"预测第{i+1}月销量"] = adjusted_forecast[i] if i < len(adjusted_forecast) else None
        extras["销量趋势预测"] = direction

        output_ci = int(thr.get("ets_output_ci", 1))
        if output_ci and pred_intervals:
            for ci_label in [80, 95]:
                lower, upper = pred_intervals.get(ci_label, (None, None))
                if lower and upper:
                    adj_lower = [max(0, round(l * a, 0)) for l, a in zip(lower, holiday_adjs)]
                    adj_upper = [max(0, round(u * a, 0)) for u, a in zip(upper, holiday_adjs)]
                    for m_idx in range(pred_months):
                        extras[f"预测_第{m_idx+1}月_置信下限{ci_label}%"] = adj_lower[m_idx] if m_idx < len(adj_lower) else None
                        extras[f"预测_第{m_idx+1}月_置信上限{ci_label}%"] = adj_upper[m_idx] if m_idx < len(adj_upper) else None
                else:
                    for m_idx in range(pred_months):
                        extras[f"预测_第{m_idx+1}月_置信下限{ci_label}%"] = None
                        extras[f"预测_第{m_idx+1}月_置信上限{ci_label}%"] = None
        extras["节假日调整系数"] = ",".join([f"{a:.2f}" for a in holiday_adjs]) if any(adj != 1.0 for adj in holiday_adjs) else "无"
    else:
        ma_forecast_vals, ma_direction = weighted_ma_forecast(monthly_qty_arr, periods=pred_months, window=ma_window)
        extras["预测算法"] = "WMA兜底"
        extras["预测模型类型"] = ""
        extras["预测_AIC"] = None
        for i in range(pred_months):
            extras[f"预测第{i+1}月销量"] = round(ma_forecast_vals[i], 0) if ma_forecast_vals else None
        extras["销量趋势预测"] = ma_direction if ma_forecast_vals else "无数据"
        extras["节假日调整系数"] = "无"
        for ci_label in [80, 95]:
            for m_idx in range(pred_months):
                extras[f"预测_第{m_idx+1}月_置信下限{ci_label}%"] = None
                extras[f"预测_第{m_idx+1}月_置信上限{ci_label}%"] = None

    try:
        elasticity, sensitivity = calc_price_elasticity(monthly_prices if len(monthly_prices) > 0 else np.array([]), monthly_qty_arr, thr)
    except (ValueError, TypeError) as _e:
        print(f"  [警告] 产品 '{prod}' 价格弹性计算失败: {_e}")
        elasticity, sensitivity = None, "计算失败"
    extras["价格弹性系数"] = round(elasticity, 2) if elasticity is not None else None
    extras["价格敏感度"] = sensitivity if elasticity is not None else "数据不足"

    if order_col and "_order_count" in pm.columns:
        try:
            freq_change, freq_label = calc_order_frequency_trend(pm, latest_month, thr)
        except (ValueError, TypeError) as _e:
            print(f"  [警告] 产品 '{prod}' 订单频次计算失败: {_e}")
            freq_change, freq_label = 0, "计算失败"
        extras["近3月月均订单数"] = round(pm.loc[last3_mask, "_order_count"].sum() / 3, 1) if len(pm) > 0 else 0
        extras["订单频次变化%"] = round(freq_change * 100, 1) if freq_change != 0 else 0
        extras["采购意愿"] = freq_label
    else:
        extras["近3月月均订单数"] = None
        extras["订单频次变化%"] = None
        extras["采购意愿"] = "无订单数据"

    return extras



def _process_product(prod, pinfo, pm, p2, thr, latest_month, mode, order_col):
    """计算单个产品的所有画像指标。从 run_profiling 第一循环提取。"""
    row_out = {"产品名称": prod}
    first_month = pinfo["first_month"]
    last_month = pinfo["last_month"]
    calendar_age = pinfo["calendar_age"]
    active_months = pinfo["active_months"]

    row_out["日历月龄"] = calendar_age
    row_out["活跃月数"] = active_months
    row_out["最新数据月份"] = str(latest_month)

    recent_24m_mask = (pm.index > (latest_month - 24))
    active_in_24m = pm.loc[recent_24m_mask, "qty_sum"].apply(lambda x: x > 0).sum() if len(pm) > 0 else 0

    recent_qty_12m = pinfo.get("recent_qty", 0)
    if calendar_age >= 24 and active_in_24m <= 1 and recent_qty_12m == 0:
        row_out["当前画像"] = "清仓/偶发"
        row_out["管理层摘要"] = "退出区"
        row_out["通用策略建议"] = "僵尸产品偶发销售，不作为正常周期分析"
        row_out["近12月销量"] = pinfo["recent_qty"]
        row_out["近12月毛利率%"] = None
        row_out["当月毛利率%"] = None
        row_out["自比健康度%"] = None
        row_out["他比健康度(pp)"] = None
        row_out["_ref_group"] = pinfo["_ref_group"]
        row_out["所属参照组"] = pinfo["_ref_group"]
        row_out["客户集中度-前1大%"] = pinfo["top1_ratio"]
        row_out["客户集中度-前3大%"] = pinfo["top3_ratio"]
        row_out["综合评分"] = None
        row_out["综合风险等级"] = "暂无评分"
        row_out["_margin"] = np.nan
        row_out["_rev"] = 0
        row_out["近12月销售额"] = pinfo.get("recent_rev", 0)
        row_out["前12月销售额"] = None
        row_out["_首次发货月"] = first_month
        row_out["_最后发货月"] = last_month
        return row_out

    if pinfo["is_new"]:
        recent_qty_val = pinfo["recent_qty"]
        if p2["has"]:
            recent_rev_val = p2["recent"].get("rev", {}).get(prod, 0)
            recent_profit_clipped = p2["recent"].get("profit", {}).get(prod, 0)
        else:
            _r_mask = pm.index > (latest_month - 12)
            recent_rev_val = pm.loc[_r_mask, "rev_pos"].sum() if len(pm) > 0 else 0
            recent_profit_clipped = pm.loc[_r_mask, "profit_clip_sum"].sum() if len(pm) > 0 else 0
        recent_margin_val = recent_profit_clipped / recent_rev_val if recent_rev_val > 0 else 0

        row_out["当前画像"] = "新品观察"
        row_out["管理层摘要"] = "待观察"
        row_out["通用策略建议"] = "持续跟踪，暂不参与周期判断"
        curr_mask = pm.index == latest_month
        curr_profit = pm.loc[curr_mask, "profit_clip_sum"].sum() if len(pm) > 0 and curr_mask.any() else 0
        curr_rev = pm.loc[curr_mask, "rev_pos"].sum() if len(pm) > 0 and curr_mask.any() else 0
        curr_margin = curr_profit / curr_rev if curr_rev > 0 else None

        row_out["近12月销量"] = recent_qty_val
        row_out["近12月毛利率%"] = recent_margin_val
        row_out["当月毛利率%"] = curr_margin
        row_out["自比健康度%"] = None
        row_out["历史参照毛利率%"] = None
        row_out["参照组加权均值%"] = None
        row_out["参照组均值来源"] = ""
        row_out["他比健康度(pp)"] = None
        row_out["公司加权均值%"] = None
        row_out["vs公司均值(pp)"] = None
        row_out["客户集中度-前1大%"] = pinfo["top1_ratio"]
        row_out["客户集中度-前3大%"] = pinfo["top3_ratio"]
        row_out["所属参照组"] = pinfo["_ref_group"]
        row_out["_ref_group"] = pinfo["_ref_group"]
        row_out["_margin"] = recent_margin_val
        row_out["_rev"] = recent_rev_val
        return row_out

    recent_mask_pm = pm.index > (latest_month - 12)
    prior_mask_pm = (pm.index <= (latest_month - 12)) & (pm.index > (latest_month - 24))

    if p2["has"]:
        recent_qty_val = p2["recent"].get("qty", {}).get(prod, 0)
        prior_qty_val = p2["prior"].get("qty", {}).get(prod, 0)
        recent_rev_val = p2["recent"].get("rev", {}).get(prod, 0)
        prior_rev_val = p2["prior"].get("rev", {}).get(prod, 0)
        recent_profit_clipped = p2["recent"].get("profit", {}).get(prod, 0)
        prior_profit_clipped = p2["prior"].get("profit", {}).get(prod, 0)
        recent_months = p2["recent"].get("months", {}).get(prod, 0)
        prior_months = p2["prior"].get("months", {}).get(prod, 0)
    else:
        recent_qty_val = pm.loc[recent_mask_pm, "qty_sum"].sum() if len(pm) > 0 else 0
        prior_qty_val = pm.loc[prior_mask_pm, "qty_sum"].sum() if len(pm) > 0 else 0
        recent_rev_val = pm.loc[recent_mask_pm, "rev_pos"].sum() if len(pm) > 0 else 0
        prior_rev_val = pm.loc[prior_mask_pm, "rev_pos"].sum() if len(pm) > 0 else 0
        recent_profit_clipped = pm.loc[recent_mask_pm, "profit_clip_sum"].sum() if len(pm) > 0 else 0
        prior_profit_clipped = pm.loc[prior_mask_pm, "profit_clip_sum"].sum() if len(pm) > 0 else 0
        recent_months = pm.loc[recent_mask_pm].shape[0] if len(pm) > 0 else 0
        prior_months = pm.loc[prior_mask_pm].shape[0] if len(pm) > 0 else 0

    row_out["近12月销量"] = recent_qty_val
    row_out["前12月销量"] = prior_qty_val
    row_out["近12月销售额"] = recent_rev_val
    row_out["前12月销售额"] = prior_rev_val

    growth_window_label = "12月"
    MIN_MONTHS = 2
    if prior_months >= MIN_MONTHS and prior_qty_val > 0:
        recent_avg = recent_qty_val / recent_months if recent_months > 0 else 0
        prior_avg = prior_qty_val / prior_months
        growth = (recent_avg - prior_avg) / prior_avg
    else:
        prior6_mask = (pm.index <= (latest_month - 6)) & (pm.index > (latest_month - 12))
        if p2["has"]:
            prior6_qty = p2["prior6"].get("qty", {}).get(prod, 0)
            prior6_months = p2["prior6"].get("months", {}).get(prod, 0)
        else:
            prior6_qty = pm.loc[prior6_mask, "qty_sum"].sum() if len(pm) > 0 else 0
            prior6_months = pm.loc[prior6_mask].shape[0] if len(pm) > 0 else 0
        if prior6_months >= MIN_MONTHS and prior6_qty > 0:
            if p2["has"]:
                _l3q = p2["last3"].get("qty", {}).get(prod, 0)
                _p3q = p2["prior3"].get("qty", {}).get(prod, 0)
                _l3m = p2["last3"].get("months", {}).get(prod, 0)
                _p3m = p2["prior3"].get("months", {}).get(prod, 0)
                recent6_qty = _l3q + _p3q
                recent6_months = _l3m + _p3m
            else:
                recent6_mask = pm.index > (latest_month - 6)
                recent6_qty = pm.loc[recent6_mask, "qty_sum"].sum() if len(pm) > 0 else 0
                recent6_months = pm.loc[recent6_mask].shape[0] if len(pm) > 0 else 0
            recent6_avg = recent6_qty / recent6_months if recent6_months > 0 else 0
            prior6_avg = prior6_qty / prior6_months
            growth = (recent6_avg - prior6_avg) / prior6_avg
            growth_window_label = "6月"
        else:
            prior3_mask = (pm.index <= (latest_month - 3)) & (pm.index > (latest_month - 6))
            if p2["has"]:
                prior3_qty = p2["prior3"].get("qty", {}).get(prod, 0)
                prior3_months = p2["prior3"].get("months", {}).get(prod, 0)
            else:
                prior3_qty = pm.loc[prior3_mask, "qty_sum"].sum() if len(pm) > 0 else 0
                prior3_months = pm.loc[prior3_mask].shape[0] if len(pm) > 0 else 0
            if prior3_months >= MIN_MONTHS and prior3_qty > 0:
                if p2["has"]:
                    recent3_qty = p2["last3"].get("qty", {}).get(prod, 0)
                    recent3_months = p2["last3"].get("months", {}).get(prod, 0)
                else:
                    recent3_mask = pm.index > (latest_month - 3)
                    recent3_qty = pm.loc[recent3_mask, "qty_sum"].sum() if len(pm) > 0 else 0
                    recent3_months = pm.loc[recent3_mask].shape[0] if len(pm) > 0 else 0
                recent3_avg = recent3_qty / recent3_months if recent3_months > 0 else 0
                prior3_avg = prior3_qty / prior3_months
                growth = (recent3_avg - prior3_avg) / prior3_avg
                growth_window_label = "3月"
            else:
                growth = 0.0
                growth_window_label = "无参照"

    growth_raw = growth
    growth = max(-1.0, min(growth, 5.0))
    row_out["近12月增长率%"] = growth
    row_out["_growth_window"] = growth_window_label
    row_out["_growth_clamped"] = (growth_raw != growth)

    recent_margin_val = recent_profit_clipped / recent_rev_val if recent_rev_val > 0 else 0
    prior_margin_val = prior_profit_clipped / prior_rev_val if prior_rev_val > 0 else 0
    curr_mask = pm.index == latest_month
    curr_profit = pm.loc[curr_mask, "profit_clip_sum"].sum() if len(pm) > 0 and curr_mask.any() else 0
    curr_rev = pm.loc[curr_mask, "rev_pos"].sum() if len(pm) > 0 and curr_mask.any() else 0
    curr_margin = curr_profit / curr_rev if curr_rev > 0 else None

    row_out["近12月毛利率%"] = recent_margin_val
    row_out["当月毛利率%"] = curr_margin
    row_out["前12月毛利率%"] = prior_margin_val
    row_out["毛利率同比变化(pp)"] = (recent_margin_val - prior_margin_val) * 100

    growth_lower = float(thr.get("rev_growth_lower", -1.0))
    growth_upper = float(thr.get("rev_growth_upper", 5.0))
    rev_growth = 0.0
    if prior_rev_val > 0 and prior_months >= 2:
        recent_rev_avg = recent_rev_val / recent_months if recent_months > 0 else 0
        prior_rev_avg = prior_rev_val / prior_months
        rev_growth = (recent_rev_avg - prior_rev_avg) / prior_rev_avg
    rev_growth = max(growth_lower, min(rev_growth, growth_upper))
    row_out["营收增长率%"] = rev_growth
    if rev_growth > 0 and recent_margin_val > prior_margin_val:
        row_out["营收-毛利综合判断"] = "双增"
    elif rev_growth > 0 and recent_margin_val <= prior_margin_val:
        row_out["营收-毛利综合判断"] = "增收不增利"
    elif rev_growth <= 0 and recent_margin_val > prior_margin_val:
        row_out["营收-毛利综合判断"] = "减收增利"
    else:
        row_out["营收-毛利综合判断"] = "双降"

    para_key = float(thr.get("pareto_key_revenue", 100)) * 10000
    para_reg = float(thr.get("pareto_regular_revenue", 10)) * 10000
    if recent_rev_val >= para_key:
        row_out["帕累托分类"] = "重点产品"
    elif recent_rev_val >= para_reg:
        row_out["帕累托分类"] = "常规产品"
    else:
        row_out["帕累托分类"] = "潜力产品"

    f6k_date = pinfo.get("first_6k_date")
    if pd.notna(f6k_date):
        row_out["首次6K日期"] = f6k_date.strftime("%Y-%m-%d")
        row_out["是否已达6K"] = "是"
        f6k_period = pd.Period(f6k_date, freq="M")
        if pd.notna(first_month):
            row_out["首次6K用时(月)"] = (f6k_period - first_month).n + 1
        else:
            row_out["首次6K用时(月)"] = None
    else:
        row_out["首次6K日期"] = None
        row_out["是否已达6K"] = "否"
        row_out["首次6K用时(月)"] = None

    monthly_margins = (pm["profit_clip_sum"] / pm["rev_pos"].replace(0, np.nan)).dropna()
    monthly_margins = monthly_margins[monthly_margins > 0]
    hist_pct = float(thr.get("ref_percentile", 0.95))
    short_age_threshold = int(thr.get("ref_short_age_months", 12))
    short_age_pct = float(thr.get("ref_short_percentile", 0.50))
    min_effective_months = int(thr.get("ref_p95_min_months", 20))
    long_ref_months = int(thr.get("ref_long_months", 24))
    long_ref_pct = float(thr.get("ref_long_percentile", 0.80))
    min_data_for_robust_pct = int(thr.get("ref_robust_min_points", 6))

    if len(monthly_margins) == 0:
        hist_ref_margin = 0
    elif calendar_age < short_age_threshold:
        if len(monthly_margins) < min_data_for_robust_pct:
            robust_pct = short_age_pct * 0.6
            hist_ref_margin = monthly_margins.quantile(robust_pct)
        else:
            hist_ref_margin = monthly_margins.quantile(short_age_pct)
    else:
        n_effective = len(monthly_margins)
        if n_effective >= min_effective_months:
            hist_ref_margin = monthly_margins.quantile(hist_pct)
        else:
            fallback_pct = max(0.90, short_age_pct + 0.10)
            hist_ref_margin = monthly_margins.quantile(fallback_pct)
    row_out["历史参照毛利率%"] = hist_ref_margin

    if calendar_age >= 36:
        recent_n = min(long_ref_months, len(monthly_margins))
        recent_margins = monthly_margins.iloc[-recent_n:]
        long_ref_margin = recent_margins.quantile(long_ref_pct)
        row_out["长期参照毛利率%"] = long_ref_margin
    else:
        row_out["长期参照毛利率%"] = None

    if len(monthly_margins) == 0:
        self_health = 0.0
        row_out["_no_valid_hist_margin"] = True
    elif recent_margin_val < 0:
        self_health = 0.0
        row_out["_no_valid_hist_margin"] = False
        row_out["_negative_margin"] = True
    else:
        self_health = recent_margin_val / hist_ref_margin if hist_ref_margin > 0 else 1.0
        row_out["_no_valid_hist_margin"] = False
        row_out["_negative_margin"] = False
    row_out["自比健康度%"] = self_health

    row_out["所属参照组"] = pinfo["_ref_group"]
    row_out["_ref_group"] = pinfo["_ref_group"]
    row_out["_margin"] = recent_margin_val
    row_out["_rev"] = recent_rev_val

    # v4.0: 毛利率斜率 = 6个月毛利额(profit_clip_sum)斜率, 均值归一化
    _gp_months = pd.period_range(latest_month - 5, latest_month, freq="M")
    gp_series = pd.Series(index=_gp_months, dtype=float)
    for _m in _gp_months:
        if _m in pm.index:
            _sub = pm.loc[[_m]]
            _gp = _sub["profit_clip_sum"].sum()
            gp_series[_m] = _gp if _gp > 0 else 0.0
        else:
            gp_series[_m] = np.nan

    gp_valid = gp_series.dropna()
    if len(gp_valid) >= 3:
        x = np.arange(len(gp_valid))
        slope, _ = np.polyfit(x, np.asarray(gp_valid.values, dtype=float), 1)
        mean_gp = float(gp_valid.mean())
        if mean_gp > 0:
            slope_ratio = -slope / mean_gp  # 负斜率(毛利额下降)→正分(高风险)
        else:
            slope_ratio = 0.0
    else:
        slope_ratio = 0.0

    row_out["_slope_ratio"] = slope_ratio
    row_out["毛利率趋势斜率%/月"] = slope_ratio * 100

    recent_valid = np.asarray(gp_valid.values, dtype=float) if len(gp_valid) > 0 else np.array([])
    zero_profit = (len(recent_valid) > 0 and np.nanmax(recent_valid) <= 0.001)

    valid_margin_count = len(recent_valid)
    min_slope_pts = int(thr.get("slope_min_data_points", 3))
    if zero_profit:
        row_out["_zero_profit"] = True
        row_out["斜率等级"] = classify_slope_level(slope_ratio, thr, zero_profit=True)
        row_out["_slope_data_insufficient"] = False
    elif valid_margin_count < min_slope_pts:
        row_out["_zero_profit"] = False
        row_out["斜率等级"] = "数据不足"
        row_out["_slope_data_insufficient"] = True
    else:
        row_out["_zero_profit"] = False
        row_out["斜率等级"] = classify_slope_level(slope_ratio, thr)
        row_out["_slope_data_insufficient"] = False

    if calendar_age >= 24:
        if p2["has"]:
            prior_12_qty = p2["prior"].get("qty", {}).get(prod, 0)
            prior_12_months = p2["prior"].get("months", {}).get(prod, 0)
            prior_12_prior_qty = p2["p24"].get("qty", {}).get(prod, 0)
            prior_12_prior_months = p2["p24"].get("months", {}).get(prod, 0)
        else:
            prior_12_mask = (pm.index <= (latest_month - 12)) & (pm.index > (latest_month - 24))
            prior_12_qty = pm.loc[prior_12_mask, "qty_sum"].sum() if len(pm) > 0 else 0
            prior_12_months = pm.loc[prior_12_mask].shape[0] if len(pm) > 0 else 0
            prior_12_prior_mask = (pm.index <= (latest_month - 24)) & (pm.index > (latest_month - 36))
            prior_12_prior_qty = pm.loc[prior_12_prior_mask, "qty_sum"].sum() if len(pm) > 0 else 0
            prior_12_prior_months = pm.loc[prior_12_prior_mask].shape[0] if len(pm) > 0 else 0
        prior_12_avg = prior_12_qty / prior_12_months if prior_12_months > 0 else 0
        prior_12_prior_avg = prior_12_prior_qty / prior_12_prior_months if prior_12_prior_months > 0 else 0
        prior_12_growth = (prior_12_avg - prior_12_prior_avg) / prior_12_prior_avg if prior_12_prior_avg > 0 else 0
        growth_change = growth - prior_12_growth
        row_out["前12月增长率%"] = prior_12_growth
        row_out["增速变化(pp)"] = growth_change * 100
        row_out["增速方向"] = "加速" if growth_change > 0 else ("持平" if growth_change == 0 else "减速")
    elif calendar_age >= 12:
        # 数据不足24月：使用近12月增长率作为方向（无同比基准）
        row_out["前12月增长率%"] = None
        row_out["增速变化(pp)"] = growth * 100 if not pd.isna(growth) else None
        row_out["增速方向"] = "加速" if growth > 0 else ("减速" if growth < 0 else "持平")
    else:
        row_out["前12月增长率%"] = None
        row_out["增速变化(pp)"] = None
        row_out["增速方向"] = ""

    row_out["客户集中度-前1大%"] = pinfo["top1_ratio"]
    row_out["客户集中度-前3大%"] = pinfo["top3_ratio"]

    monthly_qty_series = pm.loc[recent_mask_pm, "qty_sum"] if len(pm) > 0 else pd.Series(dtype=float)
    if recent_qty_val <= 0 or (len(monthly_qty_series) > 0 and monthly_qty_series.sum() <= 0):
        row_out["订货波动性CV"] = None
        row_out["_cv_invalid"] = True
        row_out["低量品标记"] = "是"
    else:
        low_vol_threshold = float(thr.get("长尾销量阈值", 1000))
        active_recent_months = (monthly_qty_series > 0).sum()
        is_pulse_demand = (active_recent_months <= 4) and (recent_qty_val > low_vol_threshold)

        if monthly_qty_series.mean() < low_vol_threshold and len(monthly_qty_series) >= 6:
            median_qty = monthly_qty_series.median()
            mad = (monthly_qty_series - monthly_qty_series.median()).abs().median()
            cv = mad / median_qty if median_qty > 0 else 0
            row_out["低量品标记"] = "是"
        elif is_pulse_demand:
            cv = 0.5
            row_out["低量品标记"] = "脉冲发货"
        else:
            cv = monthly_qty_series.std() / monthly_qty_series.mean() if monthly_qty_series.mean() > 0 else 0
            row_out["低量品标记"] = "否"

        row_out["订货波动性CV"] = cv
        row_out["_cv_invalid"] = False

    last3_mask = pm.index > (latest_month - 3)
    prior3_mask = (pm.index <= (latest_month - 3)) & (pm.index > (latest_month - 6))
    if p2["has"]:
        last3_qty = p2["last3"].get("qty", {}).get(prod, 0)
        prior3_qty = p2["prior3"].get("qty", {}).get(prod, 0)
        last3_months = p2["last3"].get("months", {}).get(prod, 0)
        prior3_months = p2["prior3"].get("months", {}).get(prod, 0)
    else:
        last3_qty = pm.loc[last3_mask, "qty_sum"].sum() if len(pm) > 0 else 0
        prior3_qty = pm.loc[prior3_mask, "qty_sum"].sum() if len(pm) > 0 else 0
        last3_months = pm.loc[last3_mask].shape[0] if len(pm) > 0 else 0
        prior3_months = pm.loc[prior3_mask].shape[0] if len(pm) > 0 else 0
    last3_avg = last3_qty / last3_months if last3_months > 0 else 0
    prior3_avg = prior3_qty / prior3_months if prior3_months > 0 else 0
    if prior3_avg > 0:
        last3_growth = (last3_avg - prior3_avg) / prior3_avg
    else:
        last3_growth = 0
    decay = (last3_growth - growth) * 100
    row_out["增速衰减(pp)"] = decay

    yoy_change = None
    if calendar_age >= 15:
        if p2["has"]:
            yoy_last3_qty = p2["yoy"].get("qty", {}).get(prod, 0)
            yoy_last3_months = p2["yoy"].get("months", {}).get(prod, 0)
        else:
            yoy_last3_mask = (pm.index > (latest_month - 15)) & (pm.index <= (latest_month - 12))
            yoy_last3_qty = pm.loc[yoy_last3_mask, "qty_sum"].sum() if len(pm) > 0 else 0
            yoy_last3_months = pm.loc[yoy_last3_mask].shape[0] if len(pm) > 0 else 0
        yoy_last3_avg = yoy_last3_qty / yoy_last3_months if yoy_last3_months > 0 else 0
        if yoy_last3_avg > 0:
            yoy_change = (last3_avg - yoy_last3_avg) / yoy_last3_avg
    row_out["_yoy_change"] = yoy_change

    row_out["_首次发货月"] = first_month
    row_out["_最后发货月"] = last_month

    monthly_qty_arr = pm.loc[recent_mask_pm, "qty_sum"].values
    monthly_prices = pm.loc[recent_mask_pm, "_avg_price"].values
    asp_slope, asp_reliable_flag = calc_asp_trend(monthly_prices if len(monthly_prices) > 0 else np.array([]), thr)
    row_out["ASP趋势%/月"] = asp_slope * 100 if asp_reliable_flag else None
    row_out["_asp_insufficient"] = not asp_reliable_flag
    asp_up_threshold = float(thr.get("asp_rising_pct", 0.5)) / 100
    asp_down_threshold = float(thr.get("asp_falling_pct", -0.5)) / 100
    if asp_slope > asp_up_threshold:
        row_out["ASP趋势方向"] = "上升"
    elif asp_slope < asp_down_threshold:
        row_out["ASP趋势方向"] = "下降"
    else:
        row_out["ASP趋势方向"] = "平稳"

    slope_ratio_check = row_out.get("_slope_ratio", 0)
    asp_diag_t = float(thr.get("joint_asp_pct", -0.5)) / 100
    margin_diag_t = float(thr.get("joint_margin_pct", -0.3)) / 100
    if asp_slope < asp_diag_t and slope_ratio_check < margin_diag_t:
        row_out["ASP-毛利率联合诊断"] = "价格战风险"
    elif asp_slope > asp_diag_t and slope_ratio_check < margin_diag_t:
        row_out["ASP-毛利率联合诊断"] = "成本问题"
    elif asp_slope < asp_diag_t and slope_ratio_check > margin_diag_t:
        row_out["ASP-毛利率联合诊断"] = "规模效应"
    else:
        row_out["ASP-毛利率联合诊断"] = "正常"

    row_out.update(_calc_forecast_extras(
        monthly_qty_arr, monthly_prices, pm, last3_mask,
        prod, thr, latest_month, mode, order_col
    ))

    try:
        return row_out
    except MemoryError as _e:
        print(f"  [警告] 产品 '{prod}' 写入结果集失败: {_e}")
        return None


def run_profiling(df, latest_month, thr, name_col, date_col, qty_col, rev_col, profit_col, cust_col, order_col, cat_col, ref_priority, wgt, mode='full', prod_month=None):
    """核心画像引擎 — P0-04重构版。"""

    _t_func_start = time.time()

    if prod_month is None:
        if "_月" not in df.columns:
            df["_月"] = df[date_col].dt.to_period("M")
        df["rev_pos"] = df[rev_col].clip(lower=0)
        _agg_kwargs = {
            "qty_sum": (qty_col, "sum"),
            "rev_pos": ("rev_pos", lambda x: x[x > 0].sum()),
            "profit_clip_sum": ("_利润_裁剪", "sum"),
        }
        if order_col and order_col in df.columns:
            _agg_kwargs["_order_count"] = (order_col, "nunique")
        prod_month = df.groupby([name_col, "_月"]).agg(**_agg_kwargs).reset_index()
        prod_month["_avg_price"] = prod_month["rev_pos"] / prod_month["qty_sum"].replace(0, float("nan"))

    products = sorted(prod_month[name_col].unique())
    min_history_months = int(thr.get("min_history_months", 6))
    min_volume = float(thr.get("min_volume", 100))
    min_record_months = int(thr.get("min_record_months", 3))
    new_product_mode = thr.get("new_product_mode", "月数")

    _prod_recent_mask = prod_month["_月"] > (latest_month - 12)
    prod_info = prod_month.groupby(name_col).agg(
        first_month=("_月", "min"),
        last_month=("_月", "max"),
        active_months=("_月", "nunique"),
    ).reset_index()
    prod_info["calendar_age"] = (latest_month - prod_info["first_month"]).apply(
        lambda x: getattr(x, "n", 0) + 1 if hasattr(x, "n") else 1
    )

    _recent = prod_month[_prod_recent_mask].groupby(name_col).agg(
        recent_qty=("qty_sum", "sum"),
        recent_rev=("rev_pos", "sum"),
    ).reset_index()
    prod_info = prod_info.merge(_recent, on=name_col, how="left")
    prod_info["recent_qty"] = prod_info["recent_qty"].fillna(0)
    prod_info["recent_rev"] = prod_info["recent_rev"].fillna(0)

    if cat_col and cat_col in df.columns:
        _cat_map = df[[name_col, cat_col]].drop_duplicates()
        if len(_cat_map) > 0:
            _cat_map = _cat_map.groupby(name_col)[cat_col].first().to_dict()
            prod_info["_ref_group"] = prod_info[name_col].map(_cat_map).fillna("未分类")
        else:
            prod_info["_ref_group"] = "未分类"
    else:
        prod_info["_ref_group"] = "未分类"

    if cust_col and cust_col in df.columns:
        _recent_df = df[df["_月"] > (latest_month - 12)].copy()
        if len(_recent_df) > 0:
            cr = _recent_df.groupby([name_col, cust_col])[rev_col].sum().reset_index()
            def conc_top(g):
                tot = g[rev_col].sum()
                if tot == 0:
                    return pd.Series({"top1_ratio": 0.0, "top3_ratio": 0.0})
                s = g[rev_col].sort_values(ascending=False, kind='stable')
                return pd.Series({
                    "top1_ratio": s.iloc[0] / tot,
                    "top3_ratio": s.iloc[:3].sum() / tot if len(s) >= 3 else 1.0
                })
            cc = cr.groupby(name_col).apply(conc_top, include_groups=False).reset_index()
            prod_info = prod_info.merge(cc, on=name_col, how="left")
            prod_info["top1_ratio"] = prod_info["top1_ratio"].fillna(0)
            prod_info["top3_ratio"] = prod_info["top3_ratio"].fillna(0)
        else:
            prod_info["top1_ratio"] = 0
            prod_info["top3_ratio"] = 0
    else:
        prod_info["top1_ratio"] = 0
        prod_info["top3_ratio"] = 0

    _f6k_threshold = float(thr.get("first_6k_threshold", 6000))
    _f6k_mask = df[qty_col] >= _f6k_threshold
    if _f6k_mask.any():
        _f6k = df.loc[_f6k_mask].groupby(name_col)[date_col].min().reset_index()
        _f6k.columns = [name_col, "first_6k_date"]
        prod_info = prod_info.merge(_f6k, on=name_col, how="left")
    else:
        prod_info["first_6k_date"] = pd.NaT

    if "新品标记" in df.columns:
        _prod_new_flag = df[df["_月"] > (latest_month - 12)].groupby(name_col)["新品标记"].apply(
            lambda s: (s == "是").any()
        ).reset_index()
        _prod_new_flag.columns = [name_col, "is_new"]
        prod_info = prod_info.merge(_prod_new_flag, on=name_col, how="left")
        prod_info["is_new"] = prod_info["is_new"].eq(True)
        print(f"  [新品判定] 使用ERP标记（新品标记列），新品数: {prod_info['is_new'].sum()}")
    else:
        prod_info["is_new"] = prod_info["calendar_age"] < min_history_months if new_product_mode == "月数" else prod_info["recent_qty"] < min_volume
        print(f"  [新品判定] 无ERP标记，使用自动计算（{new_product_mode}），新品数: {prod_info['is_new'].sum()}")

    data_insufficient_mask = prod_info["calendar_age"] < min_record_months
    data_insufficient_df = prod_info[data_insufficient_mask][
        [name_col, "calendar_age", "active_months", "first_month", "last_month", "recent_qty"]
    ].copy()
    data_insufficient_df.columns = ["产品名称", "日历月龄", "活跃月数", "首次发货月", "最后发货月", "近12月销量"]
    data_insufficient_df["首次发货月"] = data_insufficient_df["首次发货月"].apply(lambda x: str(x) if pd.notna(x) else "")
    data_insufficient_df["最后发货月"] = data_insufficient_df["最后发货月"].apply(lambda x: str(x) if pd.notna(x) else "")
    data_insufficient_list = data_insufficient_df.to_dict("records")
    valid_prods = prod_info[~data_insufficient_mask].copy()

    print(f"产品总数: {len(products)}")
    _t_preloop = time.time()
    print(f"  [计时] 窗口划分+预聚合: {_t_preloop - _t_func_start:.1f}s")

    results = []
    pm_dict = {k: v.set_index("_月").sort_index() for k, v in prod_month.groupby(name_col)}

    _p2_t = time.time()
    _p2_has = len(prod_month) > 0
    _p2_all_months = pd.period_range(latest_month - 11, latest_month, freq="M")
    if _p2_has:
        if "_avg_price" not in prod_month.columns:
            prod_month["_avg_price"] = prod_month["rev_pos"] / prod_month["qty_sum"].replace(0, float("nan"))

        _w_last3 = prod_month["_月"] > (latest_month - 3)
        _w_prior3 = (prod_month["_月"] <= (latest_month - 3)) & (prod_month["_月"] > (latest_month - 6))
        _w_prior6 = (prod_month["_月"] <= (latest_month - 6)) & (prod_month["_月"] > (latest_month - 12))
        _w_recent = prod_month["_月"] > (latest_month - 12)
        _w_prior = (prod_month["_月"] <= (latest_month - 12)) & (prod_month["_月"] > (latest_month - 24))
        _w_yoy = (prod_month["_月"] > (latest_month - 15)) & (prod_month["_月"] <= (latest_month - 12))
        _w_p24 = (prod_month["_月"] <= (latest_month - 24)) & (prod_month["_月"] > (latest_month - 36))

        def _p2_agg(mask):
            sub = prod_month[mask]
            if len(sub) == 0:
                return {}
            g = sub.groupby(name_col).agg(
                qty=("qty_sum", "sum"), rev=("rev_pos", "sum"),
                profit=("profit_clip_sum", "sum"), months=("_月", "nunique")
            )
            return g.to_dict(orient="series")

        _p2_recent = _p2_agg(_w_recent)
        _p2_prior = _p2_agg(_w_prior)
        _p2_last3 = _p2_agg(_w_last3)
        _p2_prior3 = _p2_agg(_w_prior3)
        _p2_prior6 = _p2_agg(_w_prior6)
        _p2_yoy = _p2_agg(_w_yoy)
        _p2_p24 = _p2_agg(_w_p24)

        for _d in [_p2_recent, _p2_prior, _p2_last3, _p2_prior3, _p2_prior6, _p2_yoy, _p2_p24]:
            if _d:
                for _k in _d:
                    if hasattr(_d[_k], "to_dict"):
                        _d[_k] = _d[_k].to_dict()
                    elif isinstance(_d[_k], pd.Series):
                        _d[_k] = _d[_k].to_dict()

        _p2_rm = prod_month[_w_recent]
        if len(_p2_rm) > 0:
            _p2_rm = _p2_rm.copy()
            _p2_rm["_margin"] = _p2_rm["profit_clip_sum"] / _p2_rm["rev_pos"].replace(0, np.nan)
            _p2_mar_pivot = _p2_rm.pivot_table(index="_月", columns=name_col, values="_margin")
            _p2_mar_pivot = _p2_mar_pivot.reindex(_p2_all_months)
        else:
            _p2_mar_pivot = None

        print(f"  [计时] P-2预计算: {time.time() - _p2_t:.1f}s ({len(prod_month)}行)")
    else:
        _p2_recent = _p2_prior = _p2_last3 = _p2_prior3 = _p2_prior6 = _p2_yoy = _p2_p24 = None
        _p2_mar_pivot = None

        # ============ P0-04 Phase 2: delegated to _process_product() ============
    _p2_bundle = {
        "recent": _p2_recent, "prior": _p2_prior, "last3": _p2_last3,
        "prior3": _p2_prior3, "prior6": _p2_prior6, "yoy": _p2_yoy,
        "p24": _p2_p24, "mar_pivot": _p2_mar_pivot,
        "has": _p2_has, "all_months": _p2_all_months,
    }
    for _, pinfo in valid_prods.iterrows():
        prod = pinfo[name_col]
        pm = pm_dict.get(prod, pd.DataFrame())
        row_out = _process_product(prod, pinfo, pm, _p2_bundle, thr, latest_month, mode, order_col)
        results.append(row_out)
    result_df = pd.DataFrame(results)
    _t3 = time.time()

    # ===== 计算连续下降月数 =====
    consec_map = {}
    for prod_name, pm in pm_dict.items():
        if pm.empty or "qty_sum" not in pm.columns:
            consec_map[prod_name] = 0
            continue
        qty_vals = pm["qty_sum"].tail(13).values
        consec = 0
        for i in range(len(qty_vals) - 1, 0, -1):
            if qty_vals[i] < qty_vals[i - 1]:
                consec += 1
            else:
                break
        consec_map[prod_name] = consec
    result_df["连续下降月数"] = result_df["产品名称"].map(consec_map).fillna(0).astype(int)
    print(f"  [计时] 连续下降月数计算完成: {time.time() - _t3:.1f}s")

    print(f"  [计时] 逐个产品指标计算: {_t3 - _t_preloop:.1f}s ({len(valid_prods)}个有效产品)")

    if len(result_df) == 0:
        print("无有效产品数据，退出")
        return result_df, [], result_df, [], [], time.time()

    company_avg, product_groups, group_stats = _compute_reference_groups(
        result_df, df, ref_priority, name_col,
        products=list(products), latest_month=latest_month, thr=thr
    )

    _t4 = time.time()
    print(f"  [计时] 参照组计算: {_t4 - _t3:.1f}s")

    _score_all_products(result_df, thr, wgt, ref_priority, df,
                         product_groups, group_stats, company_avg,
                         latest_month)

    out, ratio_cols, pp_cols = _finalize_output(result_df, thr)
    return result_df, data_insufficient_list, out, ratio_cols, pp_cols, _t4
