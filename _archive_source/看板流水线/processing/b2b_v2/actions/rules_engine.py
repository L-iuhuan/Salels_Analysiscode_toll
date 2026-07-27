"""
分层策略引擎 v4.3 — 数据验证修正版。

优先级链（命中即停止）:
  S5(风控) → S6(激活) → S1(深度绑定) → S3(培育放量) → S4(品类拓展) → S2(重点维护) → 常规维护(静默)

v4.3变更:
  - 零采购阈值 0.50→0.90, CV按层级差异化, Top5 0.85→0.95, 中断×1.5→×2.0
  - S3: 5路径(A-E), 新增收入增长路径D和成长期直入路径E
  - S4: 使用"实际品类数"替代"产品线数"(恒=12 bug修复)
  - S6: 加入休眠期, 历史门槛3万→2万
  - S1: 毛利P70阈值, 连续交易≥12月仍为硬门槛
  - S2: S/A级兜底, B/C无触发完全静默
  - 所有模板: 产品层结构化诊断
  - KA/AA: 全策略差异化
"""

import pandas as pd
import numpy as np
import warnings

from b2b_v2.actions.product_insights import (
    build_customer_product_profiles,
    build_monthly_product_trend,
    build_historical_glory,
    format_product_list,
    analyze_margin_structure,
    format_ka_product_detail,
    get_margin_drain_product,
    get_margin_star_product,
)

warnings.filterwarnings("ignore", category=FutureWarning)


# ═══════════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════════

def _safe_float(val, default=0.0):
    try: return float(val) if pd.notna(val) else default
    except (ValueError, TypeError): return default

def _safe_str(val, default=""):
    try: return str(val) if pd.notna(val) else default
    except (ValueError, TypeError): return default

def _safe_int(val, default=0):
    try: return int(float(val)) if pd.notna(val) else default
    except (ValueError, TypeError): return default

def _compute_active_percentiles(df):
    active = df[df["近12月收入"].fillna(0) > 0].copy()
    if len(active) == 0: return {}
    p = {}
    for col in ["近12月毛利","近12月收入","增长动能分","实际品类数","收入CV","新品采购占比"]:
        if col in active.columns:
            vals = active[col].dropna()
            if len(vals) > 1:
                p[col] = {"p15":vals.quantile(0.15),"p20":vals.quantile(0.20),
                          "p25":vals.quantile(0.25),"p30":vals.quantile(0.30),
                          "p50":vals.quantile(0.50),"p65":vals.quantile(0.65),
                          "p70":vals.quantile(0.70),"p75":vals.quantile(0.75),
                          "p80":vals.quantile(0.80)}
    p["_active_count"] = len(active)
    return p

def _compute_trading_months(silver):
    if silver is None: return {}
    cm = silver.get("customer_monthly")
    if cm is None or len(cm) == 0: return {}
    has_rev = cm[cm["rev_sum"] > 0] if "rev_sum" in cm.columns else cm
    return has_rev.groupby("客户编号")["_月"].nunique().to_dict()

def _get_cv_threshold(tier):
    if tier in ("KA","AA"): return 4.0
    elif tier == "KM": return 3.5
    else: return 5.0


# ═══════════════════════════════════════════════════════════════
# S5: 风控收缩
# ═══════════════════════════════════════════════════════════════

def _match_s5(row, p, trends=None, neg_margin=None):
    cid = _safe_str(row.get("客户编号"))
    margin = _safe_float(row.get("近12月毛利"))
    revenue = _safe_float(row.get("近12月收入"))
    lifecycle = _safe_str(row.get("客户生命周期"))
    journey = _safe_str(row.get("客户旅程阶段"))
    true_profit = _safe_float(row.get("估算真实利润率"))
    top3 = _safe_float(row.get("品种集中度Top3"))
    decline = _safe_int(row.get("连续下滑月数"))
    cv = _safe_float(row.get("收入CV"))
    zero_pct = _safe_float(row.get("零采购月占比"))
    churn = _safe_str(row.get("采购中断预警"))
    last_days = _safe_float(row.get("距上次采购天数"))
    avg_interval = _safe_float(row.get("常规平均采购间隔"), 60)
    customer_tier = _safe_str(row.get("客户层级"))
    is_ka = customer_tier in ("KA","AA")

    # ── 分级P30门槛 ──
    margin_p15 = p.get("近12月毛利",{}).get("p15",0)
    margin_p50 = p.get("近12月毛利",{}).get("p50",0)
    revenue_p50 = p.get("近12月收入",{}).get("p50",0)
    if margin < margin_p15:
        return {"match": False}  # 真正小客户，放弃风控

    # 趋势数据
    trend = trends.get(cid,{}) if trends else {}
    declining = trend.get("declining_products",[])
    cum_decline = sum(abs(pr[2]) for pr in declining) / revenue if declining and revenue > 0 else 0

    level = None
    reasons = []

    # ── 重度 ──
    if margin >= margin_p50:
        if (journey=="衰退期" or lifecycle=="衰退期") and decline >= 3 and cum_decline >= 0.30:
            reasons.append(f"衰退期+连续下滑{decline}月+累计跌幅{cum_decline:.0%}"); level = "重度"
        if true_profit <= 0 and revenue >= revenue_p50 and decline >= 2:
            reasons.append(f"真实利润率{true_profit:.1f}%+持续{decline}月")
            if not level: level = "重度"
        if top3 >= 0.95 and revenue >= revenue_p50 and decline >= 3:
            reasons.append(f"集中度{top3:.0%}+连续下滑{decline}月")
            if not level: level = "重度"

    # ── 中度 (仅毛利≥P50) ──
    if level is None and margin >= margin_p50:
        cv_thresh = _get_cv_threshold(customer_tier)
        if decline >= 3:
            reasons.append(f"连续下滑{decline}个月"); level = "中度"
        elif zero_pct >= 0.90 and cv >= cv_thresh:
            reasons.append(f"零采购{zero_pct:.0%}+CV={cv:.1f}"); level = "中度"
        elif (churn in ("是","True","1") or (avg_interval > 0 and last_days > avg_interval * 2.0)) and revenue >= revenue_p50 and journey != "流失期":
            reasons.append(f"中断预警(>{avg_interval*2:.0f}天)"); level = "中度"

    # ── 轻度 (毛利≥P50) ──
    if level is None and margin >= margin_p50:
        if churn in ("是","True","1") or (avg_interval > 0 and last_days > avg_interval * 1.5):
            reasons.append(f"距上次{last_days:.0f}天"); level = "轻度"

    # ── P15≤毛利<P50: 仅重度生效 ──
    if level is None and margin >= margin_p15:
        if (journey=="衰退期" or lifecycle=="衰退期") and decline >= 3 and cum_decline >= 0.30:
            reasons.append(f"衰退+下滑{decline}月"); level = "重度"
        elif true_profit <= 0 and revenue >= revenue_p50 and decline >= 2:
            reasons.append(f"亏损+下滑{decline}月"); level = "重度"
        elif top3 >= 0.95 and revenue >= revenue_p50 and decline >= 3:
            reasons.append(f"集中度{top3:.0%}+下滑{decline}月"); level = "重度"

    if level is None:
        return {"match": False}

    # v4.4: S/A级客户保护 — 不进入"风控收缩"，改为"升级监控"
    grade = _safe_str(row.get("综合价值层级"))
    if grade in ("S", "A") and not is_ka:
        level = "升级监控"

    # Build suggestion
    biz_owner = _safe_str(row.get("业务负责人"))
    owner_tag = f" @{biz_owner}" if biz_owner and biz_owner != "未知" else ""

    # Decline product detail
    dp_detail = ""
    if declining:
        dp_detail = "\n".join(
            f"  · {p[0]}：跌幅{p[1]:.0f}%，减收¥{p[2]:.0f}"
            for p in declining[:3]
        )

    # Negative margin integration
    nm_note = ""
    nm = neg_margin.get(cid,{}) if neg_margin else {}
    if nm.get("负毛利严重等级") in ("严重","关注"):
        stop_loss = nm.get("停售可增加利润",0)
        neg_count = nm.get("负毛利品种数",0)
        neg_list = str(nm.get("负毛利产品清单",""))[:200]
        nm_note = (
            f"\n━━━ 负毛利止损分析 ━━━\n"
            f"该客户有{neg_count}个负毛利产品，停售可挽回利润¥{stop_loss/10000:.1f}万。\n"
            f"负毛利产品：{neg_list}"
        )

    suggestions = []
    if is_ka and level in ("重度","中度"):
        suggestions.append(
            f"⚠️【KA风控·重点观察】{cid}（{customer_tier}级 | 年毛利¥{margin/10000:.1f}万 | "
            f"已进入风控{decline}个月）{owner_tag}\n"
            f"━━━ ⚠️ KA客户不收缩，升级监控+高层介入 ━━━\n"
            f"触发：{'；'.join(reasons)}\n"
            f"━━━ 下降产品精准诊断 ━━━\n{dp_detail}\n"
            f"━━━ 利润影响 ━━━\n"
            f"月度毛利损失约¥{margin/12/10000:.1f}万/月。\n"
            f"━━━ KA专项动作 ━━━\n"
            f"1.【立即】销售总监带队拜访，确认下滑原因\n"
            f"2.【48h内】输出「客户挽留方案」\n"
            f"3.【周度】KA经理每周汇报该客户动态\n"
            f"4.【月度】产品经理复核所有在供SKU竞品价格水位"
            f"{nm_note}"
        )
    elif level == "升级监控":
        # v4.4: S/A级客户不收缩，改为主动监控
        interrupt_type = "竞品替代可能，中断前持续下滑" if decline >= 3 else "项目间歇，中断前走势平稳"
        suggestions.append(
            f"⚠️【升级监控】{cid}（{grade}级 | 年毛利¥{margin/10000:.1f}万 | "
            f"中断{last_days:.0f}天）{owner_tag}\n"
            f"━━━ 中断原因分析 ━━━\n"
            f"中断类型：{interrupt_type}\n"
            f"━━━ 行动（不降投入，改主动回访） ━━━\n"
            f"1.【本周】致电对方采购确认中断原因\n"
            f"2.【2周内】确认延期→记录重启时间，正常跟进\n"
            f"3.【2周内】无回应→发微信/邮件+最新产品目录\n"
            f"4.【1月后】仍无回应→降级为S6激活试探\n"
            f"━━━ 中断产品影响 ━━━\n"
            f"{dp_detail}\n"
            f"━━━ 恢复条件 ━━━\n"
            f"任一下单行为 → 自动恢复正常跟进"
            f"{nm_note}"
        )
    elif level == "重度":
        suggestions.append(
            f"⚠️【风控·重度】{cid}（年毛利¥{margin/10000:.1f}万 | {'；'.join(reasons)}）{owner_tag}\n"
            f"该客户当前状态不适合追加投入。\n"
            f"━━━ 下降产品诊断 ━━━\n{dp_detail}\n"
            f"━━━ 动作 ━━━\n"
            f"收入端：暂停主动推新品，维持现有产品供应\n"
            f"信用端：账期收紧为款到发货\n"
            f"服务端：减少上门拜访，静默观察\n"
            f"若3个月内未改善，建议启动退出评估"
            f"{nm_note}"
        )
    elif level == "中度":
        # v4.4: 按触发原因拆分为3种子模板
        reason0 = reasons[0] if reasons else ""
        if "中断" in reason0 or "距上次" in reason0:
            suggestions.append(
                f"⚠️【风控·中度】{cid}：{reason0}。\n"
                f"━━━ 中断确认 ━━━\n"
                f"该客户中断{last_days:.0f}天（历史平均间隔{avg_interval:.0f}天）。\n"
                f"行动：本周致电确认原因，2周内完成首次触达。\n"
                f"恢复条件：任意下单→恢复正常 | 1月无回应→S6激活\n"
                f"{dp_detail}{nm_note}"
            )
        elif "连续下滑" in reason0:
            suggestions.append(
                f"⚠️【风控·中度】{cid}：{reason0}。\n"
                f"━━━ 下滑诊断 ━━━\n{dp_detail}\n"
                f"行动：核实下滑原因（项目结束/需求萎缩）。\n"
                f"若为项目结束→等待新项目启动。\n"
                f"恢复条件：单月环比增长>10%→恢复正常 | 连续下滑6月→S5重度"
                f"{nm_note}"
            )
        elif "零采购" in reason0:
            suggestions.append(
                f"⚠️【风控·中度】{cid}：{reason0}。\n"
                f"━━━ 零采购分析 ━━━\n"
                f"项目制客户采购不连续属正常现象。\n"
                f"行动：确认客户当前是否有在手项目，有→记录预计采购时间；无→关注。\n"
                f"恢复条件：恢复采购→正常 | 180天无采购→S6激活\n"
                f"{dp_detail}{nm_note}"
            )
        else:
            suggestions.append(
                f"⚠️【风控·中度】{cid}：{reason0}。\n"
                f"━━━ 诊断 ━━━\n{dp_detail}\n"
                f"行动：核实原因，2周内完成首次触达。\n"
                f"恢复条件：改善→恢复正常 | 恶化→升级"
                f"{nm_note}"
            )
    else:
        # v4.4: 轻度模板细化
        upgrade_days = avg_interval * 2.0 if avg_interval > 0 else 120
        suggestions.append(
            f"⚠️【风控·轻度】{cid}：{';'.join(reasons)}。\n"
            f"当前状态：轻度预警，暂不调整策略，维持正常跟进节奏。\n"
            f"关注要点：\n"
            f"· 若下次采购间隔超过{upgrade_days:.0f}天 → 自动升级为中度风控\n"
            f"· 若出现连续下滑 → 升级为中度风控\n"
            f"{dp_detail}"
        )

    strategy_name = "策略5: 升级监控" if level == "升级监控" else "策略9: 风控收缩"
    return {
        "match": True,
        "strategy": strategy_name,
        "level": level,
        "reasons": reasons,
        "suggestion": " | ".join(suggestions),
    }


# ═══════════════════════════════════════════════════════════════
# S6: 激活试探
# ═══════════════════════════════════════════════════════════════

def _match_s6(row, p, glories=None):
    cid = _safe_str(row.get("客户编号"))
    journey = _safe_str(row.get("客户旅程阶段"))
    lifecycle = _safe_str(row.get("客户生命周期"))
    last_days = _safe_float(row.get("距上次采购天数"))
    hist_rev = _safe_float(row.get("前12月收入"))
    avg_interval = _safe_float(row.get("常规平均采购间隔"), 60)
    decline = _safe_int(row.get("连续下滑月数"))
    customer_tier = _safe_str(row.get("客户层级"))
    is_ka = customer_tier in ("KA","AA")
    biz_owner = _safe_str(row.get("业务负责人"))
    owner_tag = f" @{biz_owner}" if biz_owner and biz_owner != "未知" else ""

    # v4.4: S/A级活跃客户不进入S6
    grade = _safe_str(row.get("综合价值层级"))
    revenue_check = _safe_float(row.get("近12月收入"))
    if grade in ("S","A") and revenue_check > 0: return {"match": False}

    # 休眠期+流失期+激活期
    is_dormant = (journey in ("休眠期","流失期","激活期") or lifecycle in ("休眠期","流失期")
                  or (last_days > 180 and hist_rev >= 20000))
    if not is_dormant: return {"match": False}
    if hist_rev < 20000: return {"match": False}

    # v4.4: 中断时长分层 + 递进式激活 + 退出规则分层
    grade = _safe_str(row.get("综合价值层级"))
    if decline >= 3:
        level = "弱激活"
        reason = f"中断前下跌{decline}月，可能被替代"
        urgency = "低"
        steps = (
            "第1周：邮件发送产品更新（不打电话，避免打扰）\n"
            "第2-3周：根据邮件回复情况决定是否升级电话\n"
            "第4周：无回应→月度邮件触达"
        )
    else:
        level = "建议激活"
        reason = "中断前走势平稳，大概率项目延期"
        if last_days <= 30: urgency = "高"
        elif last_days <= 90: urgency = "中"
        else: urgency = "低"
        steps = (
            "第1周：电话+微信联系采购负责人\n"
            "第2-3周（按反馈分支）：\n"
            "  · 确认延期→记录重启时间，重启前2周提醒备货\n"
            "  · 无回应→发产品更新邮件+技术资料\n"
            "  · 已转竞品→了解竞品型号和价格，评估回抢机会\n"
            "第4周：复盘→有回应则持续跟进，无回应则转入月度触达"
        )

    # Exit rules by grade
    if grade in ("S", "A"):
        exit_rule = "永不归档，每季度复查"
    elif grade == "B":
        exit_rule = "3个月无回应→季度邮件触达（不归档）"
    else:
        exit_rule = "1个月无回应→归档"

    glory = glories.get(cid,{}) if glories else {}
    glory_note = ""
    if glory.get("glory_product"):
        glory_note = (
            f"\n━━━ 历史辉煌诊断 ━━━\n"
            f"中断{last_days:.0f}天，历史峰值¥{glory.get('glory_revenue',0)/10000:.1f}万/年。\n"
            f"辉煌产品：「{glory['glory_product']}」（年收入¥{glory.get('glory_product_rev',0)/10000:.1f}万）\n"
            f"历史整体利润率{glory.get('glory_margin',0):.1f}%。\n"
            f"中断前3月走势：{'平稳' if decline < 3 else f'下跌{decline}月'}。判断：{reason}。\n"
            f"━━━ 激活钩子 ━━━\n"
            f"推荐切入点：以「{glory['glory_product']}」为话题切入，询问客户当前是否仍有该品类需求。"
        )

    if is_ka:
        suggestion = (
            f"⭐【KA激活·战略级】{cid}（{customer_tier}级 | 中断{last_days:.0f}天 | "
            f"历史¥{hist_rev/10000:.1f}万）{owner_tag}\n"
            f"━━━ KA三级递进激活 ━━━\n"
            f"第一级(本周)：销售总监亲自致电对方采购总监\n"
            f"第二级(有回应)：VP带队拜访，带新品样品+技术方案\n"
            f"第三级(确认延期)：建立月度对接机制，提前锁定产能\n"
            f"失败后：每半年KA经理复查一次，不放弃"
            f"{glory_note}"
        )
    else:
        suggestion = (
            f"🔄【激活试探·{level}】{cid}（中断{last_days:.0f}天 | "
            f"{grade}级 | 历史¥{hist_rev/10000:.1f}万）{owner_tag}\n"
            f"━━━ 中断诊断 ━━━\n"
            f"中断类型：{reason}\n"
            f"紧迫度：{urgency}\n"
            f"━━━ 递进式激活计划 ━━━\n{steps}\n"
            f"━━━ 退出规则 ━━━\n{exit_rule}"
            f"{glory_note}"
        )

    return {
        "match": True,
        "strategy": "策略6: 激活试探",
        "level": level,
        "reasons": [reason],
        "suggestion": suggestion,
    }


# ═══════════════════════════════════════════════════════════════
# S1: 深度绑定
# ═══════════════════════════════════════════════════════════════

def _match_s1(row, p, trading_months=None, profiles=None, db_profiles=None):
    cid = _safe_str(row.get("客户编号"))
    tier = _safe_str(row.get("综合价值层级"))
    margin = _safe_float(row.get("近12月毛利"))
    growth = _safe_float(row.get("增长动能分"))
    top3 = _safe_float(row.get("品种集中度Top3"))
    journey = _safe_str(row.get("客户旅程阶段"))
    customer_tier = _safe_str(row.get("客户层级"))
    is_ka = customer_tier in ("KA","AA")
    biz_owner = _safe_str(row.get("业务负责人"))
    owner_tag = f" @{biz_owner}" if biz_owner and biz_owner != "未知" else ""

    if tier not in ("S","A"): return {"match": False}

    trade_months = trading_months.get(cid,0) if trading_months else 0
    if trade_months < 12: return {"match": False}

    margin_p70 = p.get("近12月毛利",{}).get("p70",0)
    margin_p50 = p.get("近12月毛利",{}).get("p50",0)
    # KA/AA: P50宽松；普通S/A: P70
    threshold = margin_p50 if is_ka else margin_p70
    if margin < threshold: return {"match": False}

    # 加分条件
    bonuses = 0
    bonus_details = []
    growth_p50 = p.get("增长动能分",{}).get("p50",0)
    if growth >= growth_p50: bonuses += 1; bonus_details.append("增长动能≥中位数")

    pl = _safe_int(row.get("实际品类数"))
    pl_p75 = p.get("实际品类数",{}).get("p75",0)
    if pl >= pl_p75 and pl_p75 > 0: bonuses += 1; bonus_details.append(f"覆盖{pl}个品类≥P75")

    if top3 < 0.60: bonuses += 1; bonus_details.append("品类分布健康(Top5<60%)")

    if journey == "成熟期": bonuses += 1; bonus_details.append("关系进入稳态(成熟期)")

    if bonuses < 2 and not is_ka:
        # 降级为S2
        return {
            "match": True,
            "strategy": "策略2: 重点维护",
            "downgraded": True,
            "reasons": [f"加分条件仅{bonuses}项: {'; '.join(bonus_details)}"],
            "suggestion": _build_s2(row, p, profiles, f"加分不足({bonuses}/4)，降级"),
        }

    # 产品诊断
    profile = profiles.get(cid,{}) if profiles else {}
    margin_info = analyze_margin_structure(profile, db_profiles, cid) if db_profiles else {}
    overall_m = profile.get("overall_margin",0)
    margin_vs = margin_info.get("margin_vs_peers","无法比较")
    top5_share = margin_info.get("top5_share",0)

    product_section = ""
    if is_ka and profile:
        ka_detail = format_ka_product_detail(profile)
        drain = get_margin_drain_product(profile)
        star = get_margin_star_product(profile)
        drain_line = f"\n▶ 利润率拖累：{drain['name']}贡献{drain['share']:.0f}%收入但毛利率仅{drain['margin']:.1f}%，拉低整体{drain['drag_pp']:.1f}pp。" if drain else ""
        star_line = f"\n▶ 利润率担当：{star['name']}毛利率{star['margin']:.1f}%，毛利额¥{star['profit']/10000:.1f}万，务必维护不丢单。" if star else ""
        product_section = (
            f"\n━━━ 产品健康度诊断 ━━━\n{ka_detail}\n"
            f"整体毛利率{overall_m:.1f}%，在S1客户中{margin_vs}中位数水平。"
            f"{drain_line}{star_line}"
        )
        if top5_share >= 50:
            product_section += (
                f"\n⚠️ Top5集中度{top5_share:.0f}%（>50%）。建议：生产端提前4周备货预警；销售端关注竞品动态，防止单一产品丢单。"
            )
    elif profile:
        top5_str = format_product_list(profile.get("top5_by_revenue",[]))
        drain = margin_info.get("drain_detail","")
        star = margin_info.get("star_detail","")
        product_section = (
            f"\n━━━ 产品健康度诊断 ━━━\n"
            f"近12月主要产品（Top5）：{top5_str}\n"
            f"整体毛利率{overall_m:.1f}%，在S1客户中{margin_vs}中位数水平。"
        )
        if drain and drain != "无显著负毛利产品":
            product_section += f"\n▶ 利润率拖累：{drain}。"
        if star and star != "无显著盈利产品":
            product_section += f"\n▶ 利润率担当：{star}。"

    if is_ka:
        suggestion = (
            f"⭐【KA深度绑定·战略级】{cid}（{customer_tier}级 | {tier}级 | "
            f"年毛利¥{margin/10000:.1f}万 | 覆盖{pl}个品类）{owner_tag}\n"
            f"该客户是公司级战略资产。建议：年度框架协议、新品联合定义(JDM)、"
            f"季度高层互访、VP半年度互访。\n"
            f"加分项({bonuses}/4): {'; '.join(bonus_details)}"
            f"{product_section}"
        )
    else:
        suggestion = (
            f"【深度绑定】{cid}（{tier}级 | 年毛利¥{margin/10000:.1f}万 | "
            f"覆盖{pl}个品类）{owner_tag}\n"
            f"高价值+持续增长，属于公司级战略客户。"
            f"建议：年度框架协议锁定产能、新品联合定义、季度高层互访。"
            f"{product_section}\n"
            f"加分项({bonuses}/4): {'; '.join(bonus_details)}"
        )

    return {
        "match": True,
        "strategy": "策略1: 深度绑定",
        "reasons": bonus_details,
        "suggestion": suggestion,
    }


# ═══════════════════════════════════════════════════════════════
# S2: 重点维护 (S/A兜底)
# ═══════════════════════════════════════════════════════════════

def _build_s2(row, p, profiles=None, extra=""):
    cid = _safe_str(row.get("客户编号"))
    tier = _safe_str(row.get("综合价值层级"))
    margin = _safe_float(row.get("近12月毛利"))
    cv = _safe_float(row.get("收入CV"))
    customer_tier = _safe_str(row.get("客户层级"))
    is_ka = customer_tier in ("KA","AA")
    biz_owner = _safe_str(row.get("业务负责人"))
    owner_tag = f" @{biz_owner}" if biz_owner and biz_owner != "未知" else ""

    profile = profiles.get(cid,{}) if profiles else {}
    top5_str = format_product_list(profile.get("top5_by_revenue",[]))
    overall_m = profile.get("overall_margin",0)
    margin_info = analyze_margin_structure(profile,{},cid) if profile else {}
    star = get_margin_star_product(profile)

    stability = "高度稳定" if cv < 0.3 else ("较稳定" if cv < 0.6 else "采购不规律")
    product_note = ""
    if top5_str and top5_str != "无数据":
        product_note = (
            f"\n━━━ 产品稳定度巡检 ━━━\n"
            f"近12月主力产品：{top5_str}\n"
            f"整体毛利率{overall_m:.1f}%。"
        )
        if star:
            product_note += (
                f"\n▶ 需维护利润的产品：{star['name']}（毛利率{star['margin']:.1f}%，毛利额¥{star['profit']/10000:.1f}万）"
            )

    if is_ka:
        suggestion = (
            f"⭐【KA重点维护·战略级】{cid}（{customer_tier}级 | {tier}级 | "
            f"年毛利¥{margin/10000:.1f}万）{owner_tag}\n"
            f"━━━ KA现金牛，守城不攻坚 ━━━\n"
            f"建议节奏：月度技术交流(FAE陪同)，季度高层对接。"
            f"重点监控竞品价格水位和客户终端市场变化。"
            f"{product_note}\n"
            f"━━━ 防流失巡检 ━━━\n"
            f"□ 竞品动态：该客户是否在测试/导入竞品型号？\n"
            f"□ 终端市场：该客户所在行业景气度变化？\n"
            f"□ 采购组织：采购/研发决策人是否有变动？\n"
            f"□ 价格水位：我方报价vs市场价差距是否在拉大？\n"
            f"升级信号：若连续2月下滑>15%，自动升级为S5风控关注。"
        )
    else:
        suggestion = (
            f"🐂【重点维护】{cid}（{tier}级 | 年毛利¥{margin/10000:.1f}万 | "
            f"CV={cv:.2f}→{stability}）{owner_tag}\n"
            f"贡献可观但增长趋稳，属于\"现金牛\"。核心策略是守城而非攻坚。\n"
            f"建议节奏：月度电话回访，季度拜访。重点监控竞品是否切入。"
            f"{product_note}\n"
            f"机会留意：若出现新品采购/品类迁移信号，可升级为「培育」策略。"
        )
    if extra: suggestion += f"\n({extra})"
    return suggestion


# S7: 维护型静默 — B级客户的轻量维护（v4.5新增）
def _build_s7(row, p, profiles=None):
    cid = _safe_str(row.get("客户编号"))
    margin = _safe_float(row.get("近12月毛利"))
    revenue = _safe_float(row.get("近12月收入"))
    biz_owner = _safe_str(row.get("业务负责人"))
    owner_tag = f" @{biz_owner}" if biz_owner and biz_owner != "未知" else ""
    profile = profiles.get(cid, {}) if profiles else {}
    top5 = profile.get("top5_by_revenue", [])
    top_products = "、".join(p[0] for p in top5[:3]) if top5 else "无数据"
    monthly_avg = revenue / 12 if revenue > 0 else 0
    upgrade_threshold = monthly_avg * 1.5
    return (
        f"📋【维护型静默】{cid}（B级 | 年毛利¥{margin/10000:.1f}万）{owner_tag}\n"
        f"━━━ 维护节奏 ━━━\n"
        f"· 季度邮件/微信：分享行业动态+新品信息\n"
        f"· 半年度电话：确认业务状态和采购需求\n"
        f"主力产品：{top_products}\n"
        f"━━━ 升级信号（满足任一即可升级） ━━━\n"
        f"· 单月采购>¥{upgrade_threshold:.0f}（1.5倍月均）→ 升级为S3培育放量\n"
        f"· 主动询问新品/新型号 → 升级为S4品类拓展\n"
        f"· 连续3月有采购 → 升级为S2重点维护"
    )


# S8: 观察型静默 — C级客户低成本维护（v4.5新增）
def _build_s8(row, p):
    cid = _safe_str(row.get("客户编号"))
    margin = _safe_float(row.get("近12月毛利"))
    return (
        f"📌【观察型静默】{cid}（C级 | 年毛利¥{margin/10000:.1f}万）\n"
        f"低投入维护：半年度批量邮件触达。\n"
        f"升级信号：主动下单或采购频次恢复 → 升级为S7维护型静默。"
    )


# ═══════════════════════════════════════════════════════════════
# S3: 培育放量 (5路径)
# ═══════════════════════════════════════════════════════════════

def _match_s3(row, p, trading_months=None, profiles=None):
    cid = _safe_str(row.get("客户编号"))
    tier = _safe_str(row.get("综合价值层级"))
    increase = _safe_int(row.get("连续增长月数"))
    growth = _safe_float(row.get("增长动能分"))
    journey = _safe_str(row.get("客户旅程阶段"))
    lifecycle = _safe_str(row.get("客户生命周期"))
    new_pct = _safe_float(row.get("新品采购占比"))
    revenue = _safe_float(row.get("近12月收入"))
    rev_growth = _safe_float(row.get("收入增长率"))
    top3 = _safe_float(row.get("品种集中度Top3"))
    pl = _safe_int(row.get("实际品类数"))
    customer_tier = _safe_str(row.get("客户层级"))
    is_ka = customer_tier in ("KA","AA")
    biz_owner = _safe_str(row.get("业务负责人"))
    owner_tag = f" @{biz_owner}" if biz_owner and biz_owner != "未知" else ""

    trade = trading_months.get(cid,0) if trading_months else 0

    # 排除
    if top3 >= 0.95: return {"match": False}
    if lifecycle in ("衰退期","流失期") or journey in ("衰退期","流失期"): return {"match": False}
    if trade < 3: return {"match": False}

    growth_p65 = p.get("增长动能分",{}).get("p65",0)
    growth_p70 = p.get("增长动能分",{}).get("p70",0)
    revenue_p20 = p.get("近12月收入",{}).get("p20",0)

    triggered = False
    trigger_type = ""
    reasons = []

    # A: 连续增长≥3月 + 增速≥15%
    if increase >= 3:
        triggered = True; trigger_type = "连续增长驱动"; reasons.append(f"连续增长{increase}月")

    # B: C/B级 + 增长动能≥P70
    if not triggered and tier in ("C","B") and growth >= growth_p70:
        triggered = True; trigger_type = "动能驱动"; reasons.append(f"增长动能≥P70")

    # C: 新品占比>15% + 收入≥P20 + 交易≥3月
    if not triggered and new_pct > 0.15 and revenue >= revenue_p20:
        triggered = True; trigger_type = "新品导入驱动"; reasons.append(f"新品占比{new_pct:.0%}")

    # D: 收入增长率>10% + 增长动能≥P70 + 交易≥3月
    if not triggered and rev_growth > 0.10 and growth >= growth_p70:
        triggered = True; trigger_type = "收入增长驱动"; reasons.append(f"收入增长率{rev_growth:.0%}")

    # E: 旅程=成长期 + 增长动能≥P65 + 交易≥3月
    if not triggered and journey == "成长期" and growth >= growth_p65:
        triggered = True; trigger_type = "成长期直入"; reasons.append("处于成长期")

    if not triggered: return {"match": False}

    # 产品级增长分析
    profile = profiles.get(cid,{}) if profiles else {}
    top5 = profile.get("top5_by_revenue",[])
    overall_m = profile.get("overall_margin",0)

    growth_detail = ""
    if top5:
        growth_detail = f"\n━━━ 增长驱动力拆解 ━━━\n触发类型：{trigger_type}\n"
        if len(top5) >= 1:
            growth_detail += f"增长最大的产品：{top5[0][0]}（¥{top5[0][1]/10000:.1f}万，毛利率{top5[0][2]:.1f}%）"
            if len(top5) > 1:
                growth_detail += f"\n其次：{'、'.join(p[0] for p in top5[1:3])}"
        growth_detail += f"\n整体毛利率{overall_m:.1f}%。"
        if new_pct > 0:
            growth_detail += f"新品导入毛利率{'良好' if overall_m > 20 else '需关注定价'}。"
        growth_detail += f"\n当前覆盖{pl}个品类，品类拓展空间大。"

    if is_ka:
        suggestion = (
            f"⭐【KA培育放量·战略级】{cid}（{customer_tier}级 | {tier}级→{trigger_type}）{owner_tag}\n"
            f"━━━ KA级专项动作 ━━━\n"
            f"· FAE对接：指派专职FAE跟进新品导入和Design-in\n"
            f"· 产能预留：基于增长趋势提前4周锁定核心产品产能\n"
            f"· 三方会战：组织销售+FAE+产品经理制定全品类导入计划\n"
            f"· 升级节点：若连续增长6月+月均突破¥{revenue*2/10000:.1f}万→升级为深度绑定"
            f"{growth_detail}"
        )
    else:
        suggestion = (
            f"🌱【培育放量】{cid}（{tier}级→{trigger_type} | "
            f"新品占比{new_pct:.0%}）{owner_tag}\n"
            f"体量不大但增长势头明确。{'；'.join(reasons)}。"
            f"{growth_detail}\n"
            f"建议：安排FAE对接新品导入，每月技术交流。\n"
            f"升级节点：连续增长6月+月均突破¥{revenue*2/10000:.1f}万→深度绑定候选。"
        )

    return {
        "match": True,
        "strategy": "策略3: 培育放量",
        "reasons": reasons,
        "suggestion": suggestion,
    }


# ═══════════════════════════════════════════════════════════════
# S4: 品类拓展
# ═══════════════════════════════════════════════════════════════

def _match_s4(row, p, trading_months=None, profiles=None, cross_sell_map=None):
    cid = _safe_str(row.get("客户编号"))
    tier = _safe_str(row.get("综合价值层级"))
    pl = _safe_int(row.get("实际品类数"))
    opportunity = _safe_str(row.get("品类机会标签"))
    revenue = _safe_float(row.get("近12月收入"))
    margin = _safe_float(row.get("近12月毛利"))
    dominant = _safe_str(row.get("主导产品线")) or _safe_str(row.get("主导品类"))
    lifecycle = _safe_str(row.get("客户生命周期"))
    journey = _safe_str(row.get("客户旅程阶段"))
    decline = _safe_int(row.get("连续下滑月数"))
    customer_tier = _safe_str(row.get("客户层级"))
    is_ka = customer_tier in ("KA","AA")
    biz_owner = _safe_str(row.get("业务负责人"))
    owner_tag = f" @{biz_owner}" if biz_owner and biz_owner != "未知" else ""

    # 排除
    if lifecycle in ("衰退期","流失期") or journey in ("衰退期","流失期"): return {"match": False}
    if decline >= 2: return {"match": False}

    # 必须条件
    pl_p50 = p.get("实际品类数",{}).get("p50",0)
    if pl >= pl_p50 and pl_p50 > 0: return {"match": False}  # 覆盖已达标
    if not opportunity or opportunity in ("无","暂无",""): return {"match": False}
    if revenue < 5000: return {"match": False}

    trade = trading_months.get(cid,0) if trading_months else 0
    if trade < 3 and tier not in ("A","B"): return {"match": False}

    # 品类缺口
    pl_p75 = p.get("实际品类数",{}).get("p75",0)
    gap = max(0, pl_p75 - pl) if pl_p75 > 0 else 1
    reasons = [f"品类覆盖率{pl}/{pl_p75:.0f}条(缺口{gap:.0f}条)，机会：「{opportunity}」"]

    profile = profiles.get(cid,{}) if profiles else {}
    top5 = profile.get("top5_by_revenue",[])

    # 交叉销售
    cs_note = ""
    cs_recs = cross_sell_map.get(cid,[]) if cross_sell_map else []
    if cs_recs:
        cs_note = f"\n【交叉销售推荐】{'、'.join(cs_recs[:3])}"

    fae_note = (
        f"\n━━━ 导入策略 ━━━\n"
        f"Step 1：从与「{dominant}」相邻的品类切入（决策门槛最低）\n"
        f"Step 2：安排FAE带「{opportunity}」产品线样品随现有订单寄送\n"
        f"Step 3：若拓品成功，该客户综合评级有望提升。"
    )

    if is_ka:
        suggestion = (
            f"⭐【KA品类拓展·战略级】{cid}（{customer_tier}级 | 年毛利¥{margin/10000:.1f}万 | "
            f"仅覆盖{pl}个品类，缺口{gap}个）{owner_tag}\n"
            f"━━━ KA品类空白分析 ━━━\n"
            f"KA客户品类覆盖不足是最大的收入流失——每少覆盖一个品类，"
            f"就是放弃了该品类上的全部份额。\n"
            f"已主导品类：「{dominant}」。品类机会：「{opportunity}」。"
            f"{fae_note}"
            f"\n━━━ KA专项 ━━━\n"
            f"· 同行业案例：同层级KA客户已覆盖品类可供参考\n"
            f"· 5日FAE响应：KA客户品类导入需求5日内安排FAE对接\n"
            f"· 季度品类复盘：每季度review该客户品类覆盖进展"
            f"{cs_note}"
        )
    else:
        suggestion = (
            f"📦【品类拓展】{cid}（年毛利¥{margin/10000:.1f}万 | "
            f"仅覆盖{pl}个品类，缺口{gap}个）{owner_tag}\n"
            f"主导品类：「{dominant}」。品类机会：「{opportunity}」。"
            f"{fae_note}"
            f"{cs_note}"
        )

    return {
        "match": True,
        "strategy": "策略4: 品类拓展",
        "reasons": reasons,
        "suggestion": suggestion,
    }


# ═══════════════════════════════════════════════════════════════
# 优先级链调度
# ═══════════════════════════════════════════════════════════════

def _match_strategy(row, p, trading_months, profiles, trends, glories,
                   db_profiles, neg_margin, cross_sell_map):
    # v4.5: 休眠分级（浅度/中度/深度）
    active = _safe_str(row.get("活跃状态"))
    if active == "非活跃" or _safe_str(row.get("综合价值层级")) == "休眠":
        cid = _safe_str(row.get("客户编号"))
        last_days = _safe_float(row.get("距上次采购天数"))
        if last_days <= 365:
            return {"strategy": "休眠·浅度(待激活)", "suggestion": f"💤【浅度休眠】{cid}（距上次{last_days:.0f}天）\n距休眠不远，后续如有激活活动优先触达。"}
        elif last_days <= 730:
            return {"strategy": "休眠·中度(低优先级)", "suggestion": f"💤【中度休眠】{cid}（距上次{last_days:.0f}天）\n年度邮件触达，标记低优先级唤醒。"}
        else:
            return {"strategy": "休眠·深度(归档)", "suggestion": ""}

    # 优先级链: S5→S6→S1→S3→S4→S2→静默
    result = _match_s5(row, p, trends, neg_margin)
    if result.get("match"): return result

    result = _match_s6(row, p, glories)
    if result.get("match"): return result

    result = _match_s1(row, p, trading_months, profiles, db_profiles)
    if result.get("match"): return result

    result = _match_s3(row, p, trading_months, profiles)
    if result.get("match"): return result

    result = _match_s4(row, p, trading_months, profiles, cross_sell_map)
    if result.get("match"): return result

    # S2兜底: S/A级客户
    tier = _safe_str(row.get("综合价值层级"))
    if tier in ("S","A"):
        return {
            "match": True,
            "strategy": "策略2: 重点维护",
            "reasons": ["S/A级兜底维护"],
            "suggestion": _build_s2(row, p, profiles, "S/A级兜底"),
        }

    # v4.5: B级→S7维护型静默, C级→S8观察型静默
    if tier == "B":
        return {
            "match": True,
            "strategy": "策略7: 维护型静默",
            "reasons": ["B级静默维护"],
            "suggestion": _build_s7(row, p, profiles),
        }
    return {
        "strategy": "策略8: 观察型静默",
        "reasons": ["C级静默观察"],
        "suggestion": _build_s8(row, p),
    }


# ═══════════════════════════════════════════════════════════════
# 合并入口
# ═══════════════════════════════════════════════════════════════

def generate_actions_v2(customer_df, anomaly_log=None, silver=None,
                        neg_margin_summary=None, cross_sell_map=None):
    df = customer_df.copy()
    p = _compute_active_percentiles(df)
    trading_months = _compute_trading_months(silver)

    cxp = silver.get("customer_x_product") if silver else None
    cm = silver.get("customer_monthly") if silver else None
    # 产品画像取近12月数据，与客户年毛利口径一致
    if cxp is not None and "_月" in cxp.columns:
        cxp["_ym"] = cxp["_月"].astype(str)
        latest_ym = str(cxp["_ym"].max())
        cutoff_ym = f"{int(latest_ym[:4])-1}-{latest_ym[5:]}"
        cxp_12m = cxp[(cxp["_ym"] >= cutoff_ym) & (cxp["_ym"] <= latest_ym)].copy()
    else:
        cxp_12m = cxp
    profiles = build_customer_product_profiles(cxp_12m) if cxp_12m is not None else {}
    trends = build_monthly_product_trend(cxp_12m) if cxp_12m is not None else {}
    glories = build_historical_glory(cm, cxp) if cm is not None else {}

    # 预计算S1候选集（用于同行对比）
    sa_mask = df["综合价值层级"].isin(["S", "A"]) if "综合价值层级" in df.columns else pd.Series(False, index=df.index)
    sa_cids = df.loc[sa_mask, "客户编号"]
    db_profiles = {cid: profiles[cid] for cid in sa_cids if cid in profiles}

    if neg_margin_summary is None: neg_margin_summary = {}
    if cross_sell_map is None: cross_sell_map = {}

    def _apply_strategy(row):
        result = _match_strategy(row, p, trading_months, profiles, trends, glories,
                                db_profiles, neg_margin_summary, cross_sell_map)
        cid = row["客户编号"]
        strategy = result.get("strategy","常规维护(静默)")
        reasons = "; ".join(result.get("reasons",[]))
        return pd.Series({
            "客户编号": cid,
            "策略名称": strategy,
            "策略建议": result.get("suggestion",""),
            "策略原因": reasons,
        })

    result_df = df.apply(_apply_strategy, axis=1)
    strategy_counts = result_df["策略名称"].value_counts().to_dict()

    # L1告警（仅P1-P3）
    if anomaly_log is not None and len(anomaly_log) > 0:
        l1 = _gen_l1(anomaly_log, df)
    else:
        l1 = pd.DataFrame(columns=["客户编号","告警数量","紧急告警"])
    result_df = result_df.merge(l1, on="客户编号", how="left")
    result_df["告警数量"] = result_df["告警数量"].fillna(0).astype(int)
    result_df["紧急告警"] = result_df["紧急告警"].fillna("")

    # 排序输出
    order = ["策略5","策略6","策略1","策略3","策略4","策略2","常规维护","不适用"]
    def _order(s):
        for i, prefix in enumerate(order):
            if s.startswith(prefix): return i
        return 99
    sorted_items = sorted(strategy_counts.items(), key=lambda x: _order(x[0]))
    summary = ", ".join(f"{k}={v}" for k, v in sorted_items)
    print(f"  [6策略引擎v4.3] {summary}")

    return result_df


def _gen_l1(anomaly_log, customer_df):
    if len(anomaly_log) == 0:
        return pd.DataFrame(columns=["客户编号","告警数量","紧急告警"])
    def _compute_priority(row):
        tier = _safe_str(row.get("综合价值层级"))
        ct = _safe_str(row.get("客户层级"))
        active = _safe_str(row.get("活跃状态"))
        if active == "非活跃" or tier == "休眠": return 5
        elif tier == "S" or ct in ("KA","AA"): return 1
        elif tier == "A": return 2
        elif tier == "B": return 3
        else: return 4
    priority_map = dict(zip(customer_df["客户编号"], customer_df.apply(_compute_priority, axis=1)))

    alerts = []
    for cid, group in anomaly_log.groupby("客户编号"):
        pri = priority_map.get(cid,4)
        if pri >= 4: continue
        msgs = []
        for _, row in group.iterrows():
            atype = row["异常类型"]; level = row["异常等级"]
            detail = str(row.get("异常详情",""))[:100]
            # v4.4: 营收断崖仅连续下滑>=3月或跌幅>80%触发紧急告警
            if atype == "营收断崖" and pri > 2: continue
            if atype == "营收断崖" and level == "高":
                try:
                    decline = float(str(row.get("异常详情","")).split("降幅")[-1].replace("%","").strip() or "0")
                    if decline < 80 and pri <= 2:
                        level = "中"  # 降级为注意级别
                except (ValueError, KeyError, TypeError): pass
            if level == "高":
                msgs.append(f"【{'紧急' if pri<=2 else '关注'}】{atype}: {detail}" if pri<=2 else f"【关注】{atype}")
            elif level == "中" and pri <= 2:
                msgs.append(f"[注意]{atype}: {detail[:80]}")
        if msgs:
            biz_owner = _safe_str(customer_df.loc[customer_df["客户编号"]==cid,"业务负责人"].iloc[0] if len(customer_df[customer_df["客户编号"]==cid])>0 else "")
            ot = f" @{biz_owner}" if biz_owner and biz_owner != "未知" else ""
            alerts.append({"客户编号":cid,"告警数量":len(msgs),"紧急告警":"; ".join(msgs)+ot})
    if not alerts: return pd.DataFrame(columns=["客户编号","告警数量","紧急告警"])
    result = pd.DataFrame(alerts)
    print(f"  [L1告警] {len(result)}客户(仅P1-P3)")
    return result
