"""
Task 1: 客户旅程阶段分类器 (Customer Journey Stage Classifier).

基于 ERP 月度聚合数据，将客户划分为 7 个旅程阶段：
  导入期 / 成长期 / 成熟期 / 衰退期 / 流失期 / 激活期 / 稳定期

输入: silver_customer_monthly (客户×月份聚合表)
输出: 每客户一行，标记阶段 + 持续时间 + 转换次数

依赖: config.settings.CUSTOMER_JOURNEY_THRESHOLDS
"""

import sys, os
import pandas as pd
import numpy as np

_SRC_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)


def classify_customer_journey_stage(
    customer_monthly_df: pd.DataFrame,
    config: dict,
    cust_col: str = "客户编号",
    date_col: str = "_月",
    rev_col: str = "rev_sum",
    qty_col: str = "qty_sum",
    channel_map: dict = None,  # type: ignore[type-arg]
) -> pd.DataFrame:
    """
    将客户划分为旅程阶段。

    参数
    ----------
    customer_monthly_df : DataFrame
        客户月度聚合表，需包含 cust_col, date_col, rev_col, qty_col 列。
        date_col 应为 pd.Period 类型，按升序排列。
    config : dict
        阈值字典，从 settings.CUSTOMER_JOURNEY_THRESHOLDS 读取，键包括:
        - onboarding_max_months (默认 6)
        - onboarding_max_orders (默认 3)
        - growth_growth_threshold (默认 0.30)
        - growth_frequency_surge_ratio (默认 2.0)
        - maturity_cv_threshold (默认 0.3)
        - maturity_revenue_rank_pct (默认 0.3)
        - decline_decline_threshold (默认 0.20)
        - decline_consecutive_months (默认 2)
        - churn_days (默认 90)
        - reactivation_window_days (默认 180)
    cust_col, date_col, rev_col, qty_col : str
        列名配置。
    channel_map : dict, optional
        {客户编号: 渠道类型} 映射。成熟期金额排名时按渠道分组（而非全局）。
        为 None 时使用全局排名。

    返回
    -------
    DataFrame
        每客户一行，列包括:
        - 客户编号
        - 客户旅程阶段
        - 阶段持续月数
        - 阶段转换次数
        - 首次交易日期
        - 距上次采购天数
        - 近6月交易额环比增长率
        - 近12月交易额CV

    异常
    ------
    数据缺失时 graceful degradation:
        - customer_monthly_df 为空 → 返回空 DataFrame
        - 某客户数据不足 → 标记为"稳定期"
    """
    # ── 阈值读取 + 默认值 ──
    onboarding_max_months = config.get("onboarding_max_months", 6)
    onboarding_max_orders = config.get("onboarding_max_orders", 3)
    growth_threshold = config.get("growth_growth_threshold", 0.30)
    growth_freq_ratio = config.get("growth_frequency_surge_ratio", 2.0)
    maturity_cv = config.get("maturity_cv_threshold", 0.3)
    maturity_rank_pct = config.get("maturity_revenue_rank_pct", 0.3)
    decline_threshold = config.get("decline_decline_threshold", 0.20)
    decline_consecutive = config.get("decline_consecutive_months", 2)
    churn_days = config.get("churn_days", 90)
    reactivation_window = config.get("reactivation_window_days", 180)

    # ── 空数据保护 ──
    if customer_monthly_df is None or len(customer_monthly_df) == 0:
        return pd.DataFrame(columns=[
            cust_col, "客户旅程阶段", "阶段持续月数", "阶段转换次数",
            "首次交易日期", "距上次采购天数",
            "近6月交易额环比增长率", "近12月交易额CV",
        ])

    df = customer_monthly_df.copy()
    if date_col in df.columns and not pd.api.types.is_period_dtype(df[date_col]):
        try:
            df[date_col] = pd.PeriodIndex(df[date_col], freq="M")
        except Exception:
            pass

    # ── 全局日期范围 ──
    all_months = df[date_col].dropna().unique()
    if len(all_months) == 0:
        return pd.DataFrame()
    all_months = sorted(all_months)
    global_latest = all_months[-1]

    results = []

    for cid, grp in df.groupby(cust_col):
        grp = grp.sort_values(date_col).reset_index(drop=True)
        n_months = len(grp)

        # 基本信息
        first_month = grp[date_col].iloc[0]
        last_month = grp[date_col].iloc[-1]
        months_since_last = _month_diff(last_month, global_latest)

        # 首次交易距今月数
        months_since_first = _month_diff(first_month, global_latest)

        # 交易频次
        total_orders = grp["order_count"].sum() if "order_count" in grp.columns else n_months

        # 近6月 vs 前6月交易额
        recent6 = grp[grp[date_col] > global_latest - 6]
        prior6 = grp[(grp[date_col] <= global_latest - 6) & (grp[date_col] > global_latest - 12)]
        recent6_rev = recent6[rev_col].sum() if len(recent6) > 0 else 0
        prior6_rev = prior6[rev_col].sum() if len(prior6) > 0 else 0
        growth_rate = (recent6_rev - prior6_rev) / max(prior6_rev, 1) if prior6_rev > 0 else 0

        # 近3月 vs 前3月频次
        recent3 = grp[grp[date_col] > global_latest - 3]
        prior3 = grp[(grp[date_col] <= global_latest - 3) & (grp[date_col] > global_latest - 6)]
        recent3_freq = recent3[rev_col].sum() if len(recent3) > 0 else 0
        prior3_freq = prior3[rev_col].sum() if len(prior3) > 0 else 0
        freq_surge = (recent3_freq / max(prior3_freq, 1)) if prior3_freq > 0 else 0

        # 近12月CV
        recent12 = grp[grp[date_col] > global_latest - 12]
        cv = recent12[rev_col].std() / max(recent12[rev_col].mean(), 1) if len(recent12) > 1 else 999

        # 近6月交易总额（用于排名）
        recent6_total = recent6_rev

        # 连续下滑月数
        decline_streak = 0
        grp_recent = grp[grp[date_col] > global_latest - 6].sort_values(date_col)
        for i in range(1, len(grp_recent)):
            if grp_recent[rev_col].iloc[i] < grp_recent[rev_col].iloc[i - 1]:
                decline_streak += 1
            else:
                decline_streak = 0

        # ── 阶段判定 ──
        # 优先级: 激活期 > 导入期 > 流失期 > 衰退期 > 成长期 > 成熟期 > 稳定期

        stage = "稳定期"  # 默认

        # 1) 激活期: 此前曾有超过 reactivation_window 天的沉默，然后重新交易
        # 近似: 上月无交易且本月有交易 + 整体跨度 > reactivation_window/30
        # 简化判断: 最近有交易，但历史有过 > reactivation_window 天的间隔
        has_long_gap = False
        if n_months >= 2:
            gaps = []
            for i in range(1, n_months):
                gap = _month_diff(grp[date_col].iloc[i - 1], grp[date_col].iloc[i])
                gaps.append(gap)
            max_gap = max(gaps) if gaps else 0
            # 最大间隔月数 * 30 ≈ 天数
            if max_gap > reactivation_window / 30 and months_since_last <= 1:
                has_long_gap = True

        if has_long_gap:
            stage = "激活期"

        # 2) 导入期: 首次交易距今 <= onboarding_max_months 且 交易频次 <= onboarding_max_orders
        if stage == "稳定期":
            if months_since_first <= onboarding_max_months and total_orders <= onboarding_max_orders:
                stage = "导入期"

        # 3) 流失期: 距上次采购 > churn_days/30 月 且 近6月无交易
        months_churn = churn_days / 30.0
        if stage == "稳定期":
            if months_since_last > months_churn and recent6_rev == 0:
                stage = "流失期"

        # 4) 衰退期: 近6月交易额环比下降 >= decline_threshold 且 连续下滑月数 >= decline_consecutive
        if stage == "稳定期":
            if growth_rate <= -decline_threshold and decline_streak >= decline_consecutive:
                stage = "衰退期"

        # 5) 成长期: 近6月交易额环比增长 >= growth_threshold 或 频次激增
        if stage == "稳定期":
            if growth_rate >= growth_threshold or freq_surge >= growth_freq_ratio:
                stage = "成长期"

        # 6) 成熟期: CV < maturity_cv 且 金额排名前30%（此条件需全局排名，留待外部处理）
        # 此处仅检查 CV 条件，金额排名在 batch 函数中修正
        if stage == "稳定期":
            if cv < maturity_cv:
                stage = "成熟期"

        # ── 阶段持续时间 ──
        # 计算最近一次阶段转换：扫描近12月，看哪个月开始进入当前状态特征
        duration_months = 1  # 至少1个月
        stage_seq = []
        if n_months >= 3:
            for i in range(max(0, n_months - 12), n_months):
                row = grp.iloc[i]
                stage_seq.append(_estimate_historical_stage(
                    row, grp, i, n_months, global_latest,
                    onboarding_max_months, churn_days,
                ))
            if stage_seq:
                # 从后往前找第一个不同于当前阶段的月份
                current_stage = stage
                consecutive = 0
                for s in reversed(stage_seq):
                    if s == current_stage:
                        consecutive += 1
                    else:
                        break
                duration_months = max(1, consecutive)

        # ── 阶段转换次数 ──
        transitions = 0
        if n_months >= 3:
            for i in range(1, len(stage_seq)):
                if stage_seq[i] != stage_seq[i - 1]:
                    transitions += 1

        # 距上次采购天数（近似为月数 * 30）
        days_since_last = months_since_last * 30

        results.append({
            cust_col: cid,
            "客户旅程阶段": stage,
            "阶段持续月数": duration_months,
            "阶段转换次数": transitions,
            "首次交易日期": str(first_month),
            "距上次采购天数": int(days_since_last),
            "近6月交易额环比增长率": round(growth_rate, 4),
            "近12月交易额CV": round(cv, 4),
        })

    out = pd.DataFrame(results)

    # ── 成熟期金额排名修正 ──
    if len(out) > 0 and "成熟期" in out["客户旅程阶段"].values:
        all_recent6_rev = []
        for cid, grp in df.groupby(cust_col):
            g = grp.sort_values(date_col)
            r6 = g[g[date_col] > global_latest - 6][rev_col].sum()
            all_recent6_rev.append(r6)
        rank_threshold = np.percentile(
            [r for r in all_recent6_rev if r > 0],
            (1 - maturity_rank_pct) * 100,
        ) if all_recent6_rev else 0

        # 计算每客户近6月营收
        cid_to_recent6 = {}
        for cid, grp in df.groupby(cust_col):
            g = grp.sort_values(date_col)
            r6 = g[g[date_col] > global_latest - 6][rev_col].sum()
            cid_to_recent6[cid] = r6

        if channel_map is not None:
            # 按渠道分组排名
            maturity_mask = out["客户旅程阶段"] == "成熟期"
            for idx in out[maturity_mask].index:
                cid = out.at[idx, cust_col]
                ch = channel_map.get(cid, "未知")
                # 同渠道中营收>0的客户
                peers = [
                    pid for pid in out[cust_col].tolist()
                    if channel_map.get(pid, "未知") == ch and cid_to_recent6.get(pid, 0) > 0
                ]
                if not peers:
                    continue
                threshold = np.percentile(
                    [cid_to_recent6[p] for p in peers],
                    (1 - maturity_rank_pct) * 100,
                )
                if cid_to_recent6.get(cid, 0) < threshold:
                    out.at[idx, "客户旅程阶段"] = "稳定期"
        else:
            # 全局排名（原逻辑）
            all_rev = [r for r in cid_to_recent6.values() if r > 0]
            rank_threshold = np.percentile(all_rev, (1 - maturity_rank_pct) * 100) if all_rev else 0
            maturity_mask = out["客户旅程阶段"] == "成熟期"
            for idx in out[maturity_mask].index:
                cid = out.at[idx, cust_col]
                if cid_to_recent6.get(cid, 0) < rank_threshold:
                    out.at[idx, "客户旅程阶段"] = "稳定期"

    return out


def _month_diff(a: pd.Period, b: pd.Period) -> int:
    """计算两个 Period 之间的月数差。"""
    try:
        return (b.year - a.year) * 12 + (b.month - a.month)
    except Exception:
        return 999


def _estimate_historical_stage(
    row, grp, idx, n_months, global_latest,
    onboarding_max_months, churn_days,
) -> str:
    """估计某个月份客户的旅程阶段（简化版）。"""
    # 简化：基于后续交易数据做近似判断
    # 流失期
    if row.get("rev_sum", 0) == 0:
        return "流失期"
    return "稳定期"


def batch_classify(
    customer_monthly_df: pd.DataFrame,
    config: dict,
    cust_col: str = "客户编号",
    date_col: str = "_月",
    rev_col: str = "rev_sum",
    qty_col: str = "qty_sum",
    channel_map: dict = None,  # type: ignore[type-arg]
) -> pd.DataFrame:
    """
    classify_customer_journey_stage 的批量封装。
    与 classify_customer_journey_stage 行为一致，仅提供更清晰的别名。
    """
    return classify_customer_journey_stage(
        customer_monthly_df, config,
        cust_col=cust_col, date_col=date_col,
        rev_col=rev_col, qty_col=qty_col,
        channel_map=channel_map,
    )
