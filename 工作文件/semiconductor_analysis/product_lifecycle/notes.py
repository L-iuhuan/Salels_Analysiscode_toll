
"""
特情说明生成 — 产品生命周期专属（v4.0）。

v4.0改进:
- 新增覆盖规则提示: 增速衰减≥80 & 毛利率斜率≥70 触发极高风险自动判定

v3.0改进:
- 新增连续下降月数检测
- 修复错别字：崩坥→崩塌, 贝破→跌破

v2.9改进:
- 零销量时跳过自比/他比健康度比较，防语义矛盾
- 所有阈值改为config驱动
- 新增自比健康度极低检测
- 新增衰退期亏损遗漏补充
- _decay_cap_removed 分画像提示（成长期/健康扩张 vs 其他）
- 移除客户数据缺失提示（CM已移除）
"""


def generate_specific_note(row, thr):
    """根据产品各项指标的异常情况自动生成特情说明。

    参数:
        row: 产品数据行（dict-like或Series）
        thr: 阈值字典

    返回:
        str: 特情说明文本
    """
    notes = []

    # 判断是否为零销量（用于后续抑制无效的毛利率比较）
    is_zero_sales = (row.get("近12月销量", 0) == 0
                     and row.get("当前画像") not in ["新品观察", "清仓/偶发", None])

    growth_win = row.get("_growth_window", "12月")
    if growth_win not in ("12月", "", None):
        notes.append(f"历史不足12月，增长率基于{growth_win}窗口，可能不稳定")

    if row.get("增速方向") == "减速":
        notes.append("增长动能正在衰减")

    cust_warn_line = float(thr.get("note_conc_warning", 0.50))
    if row.get("客户集中度-前1大%", 0) > cust_warn_line:
        notes.append("客户集中度过高，存在单点崩塌风险")

    if row.get("斜率等级") in ("明显侵蚀", "快速恶化"):
        slope_pct = abs(row.get("毛利率趋势斜率%/月", 0))
        notes.append(f"毛利率以{slope_pct:.2f}%/月速度持续下降")

    if not is_zero_sales:
        sh_warn = float(thr.get("note_self_health_warn_pct", 50)) / 100.0
        sh_extreme = float(thr.get("note_self_extreme_pct", 30)) / 100.0
        sh_val = row.get("自比健康度%", 1.0)
        if sh_val is not None and sh_val < sh_warn and not row.get("_no_valid_hist_margin") and row.get("斜率等级") != "无利润/异常":
            # 只有不满足"极低"时才提示"跌破一半"（否则极低已覆盖）
            if sh_val >= sh_extreme:
                notes.append("毛利率已跌破历史参照值一半")
        his_warn = float(thr.get("note_rel_health_warn_pp", -10))
        if row.get("他比健康度(pp)", 0) < his_warn and not row.get("_no_valid_hist_margin") and row.get("斜率等级") != "无利润/异常":
            rh_abs = abs(row["他比健康度(pp)"])
            notes.append(f"毛利率低于参照组均值{rh_abs:.0f}个百分点")

    if row.get("_cv_invalid"):
        notes.append("近12个月无发货记录，订单波动性无法评估")

    if row.get("低量品标记") == "脉冲发货":
        notes.append("脉冲发货，订单波动性已豁免")

    if row.get("_slope_data_insufficient"):
        notes.append("毛利率有效数据不足，趋势判断不可靠")

    if row.get("斜率等级") == "无利润/异常":
        notes.insert(0, "近12月毛利率全为零，盈利能力丧失")

    if row.get("_no_valid_hist_margin"):
        notes.insert(0, "历史无有效毛利率数据，盈利健康无法评估")

    sh_extreme = float(thr.get("note_self_extreme_pct", 30)) / 100.0
    sh_val = row.get("自比健康度%")
    if sh_val is not None and sh_val < sh_extreme:
        notes.append("自比健康度极低，毛利率严重恶化")

    ref_source = row.get("参照组均值来源")
    if ref_source and ("兜底" in str(ref_source) or "不满足" in str(ref_source)):
        notes.insert(0, "同类参照组不足，他比健康度仅供参考")

    pareto = row.get("帕累托分类")
    if pareto == "重点产品":
        margin = row.get("近12月毛利率%", 0) or 0
        if 0 < margin < 1:
            leverage = round(1.0 - margin, 4)
            notes.append(f"重点产品：若降本1%，毛利率可提升{leverage:.2f}pp，建议持续降本与迭代升级")
        else:
            notes.append("重点产品：建议持续降本与迭代升级")

    if pareto == "常规产品":
        g_rate = row.get("近12月增长率%", 0)
        high_growth_thr = float(thr.get("note_regular_growth_threshold", 1.0))
        if g_rate > high_growth_thr:
            notes.append("高增长常规产品，建议加大投入抢占市场")

    if row.get("ASP-毛利率联合诊断") == "价格战风险":
        notes.append("ASP与毛利率同步下降，存在价格战风险，需关注竞争态势")

    # ===== 连续下降月数检测 =====
    consec_months = row.get("连续下降月数", 0)
    if consec_months >= 4:
        notes.insert(0, f"月销量已连续下跌{consec_months}个月，下跌持续性构成独立风险信号")
    elif consec_months >= 2:
        notes.append(f"月销量已连续下跌{consec_months}个月，需关注是否形成下降趋势")

    if is_zero_sales:
        notes.insert(0, "近12月无发货记录，当前画像与毛利率基于零销量推断，毛利率无实际意义")

    margin_12m = row.get("近12月毛利率%", 0) or 0
    if row.get("_negative_margin"):
        notes.insert(0, "当前处于亏损状态（近12月毛利率为负）")
    elif row.get("当前画像") == "衰退期" and margin_12m < 0:
        notes.insert(0, "当前处于亏损状态（近12月毛利率为负）")

    if row.get("_growth_clamped"):
        g_cap = float(thr.get("增长率_上限", 5.0))
        g_floor = float(thr.get("增长率_下限", -1.0))
        g_raw = row.get("近12月增长率%", 0)
        if g_raw >= g_cap:
            notes.append(f"增长率已达截断上限({g_cap*100:.0f}%)，实际增速更高")
        elif g_raw <= g_floor:
            notes.append(f"增长率已达截断下限({g_floor*100:.0f}%)，实际跌幅更深")

    if row.get("_decay_cap_removed"):
        portrait = row.get("当前画像", "")
        if portrait in ("成长期", "健康扩张"):
            notes.append("近期已转为实际下滑，当前画像基于更长窗口数据，需综合判断")
        else:
            notes.append("爆发增长后近期已转为实际下滑，增速衰减因子未享受上限保护")

    strategy = row.get("通用策略建议", "")
    rev_profit_diag = row.get("营收-毛利综合判断", "")
    margin_yoy = row.get("毛利率同比变化(pp)", 0) or 0
    if ("退市" in str(strategy) or "换代" in str(strategy)) and rev_profit_diag == "减收增利":
        notes.append("注意：毛利率同比回升，退市/换代判断需结合回升可持续性综合评估")
    rebound_thr = float(thr.get("note_rebound_threshold_pp", 5))
    if row.get("当前画像") == "衰退期" and margin_yoy > rebound_thr:
        notes.append(f"毛利率同比大幅回升{margin_yoy:.1f}pp，建议复核当前画像是否应为主动收缩")

    # ===== v4.0: 覆盖规则提示 =====
    if row.get("_override_extreme", False):
        notes.insert(0, "增速衰减(≥80)与毛利率斜率(≥70)双因子触发覆盖规则，已自动判定为极高风险")

    if notes:
        return "；".join(notes)
    return "暂无异常信号"
