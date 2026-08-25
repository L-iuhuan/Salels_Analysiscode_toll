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
    if date_col in df.columns and not isinstance(df[date_col].dtype, pd.PeriodDtype):
        try:
            df[date_col] = pd.PeriodIndex(df[date_col], freq="M")
        except (ValueError, TypeError):
            pass

    # ── 全局日期范围 ──
    all_months = df[date_col].dropna().unique()
    if len(all_months) == 0:
        return pd.DataFrame()
    all_months = sorted(all_months)
    global_latest = all_months[-1]

    results = []
    _recent6_by_cid = {}  # [批次⑥ P4] 主循环顺带记录近6月营收，供成熟期排名修正复用（原逻辑在修正段重复全表 groupby 两遍）

    # [批次⑥ P4] 历史阶段判定的乘数配置在函数顶部读取一次（原为每次调用 _estimate_historical_stage
    # 时在循环内 import 并读取，配置静态不变，值完全一致）
    from config.settings import CUSTOMER_JOURNEY_THRESHOLDS as _jcfg
    _hist_decline_mul = float(_jcfg.get("hist_decline_multiplier", 0.9))
    _hist_growth_mul = float(_jcfg.get("hist_growth_multiplier", 1.1))

    for cid, grp in df.groupby(cust_col):
        grp = grp.sort_values(date_col, kind='stable').reset_index(drop=True)
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
        mean_val = recent12[rev_col].mean()
        cv = recent12[rev_col].std() / max(mean_val, 1) if (len(recent12) > 1 and pd.notna(mean_val)) else 999

        # 近6月交易总额（用于排名）
        recent6_total = recent6_rev

        # 连续下滑月数
        decline_streak = 0
        grp_recent = grp[grp[date_col] > global_latest - 6].sort_values(date_col, kind='stable')
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
        # [批次⑥ P4] 每客户一次性取 numpy 数组 + 首个正收入位置，替代逐月
        # Series.iloc/.get 与每月一次的 grp[grp["rev_sum"]>0] 掩码扫描
        # （原 25,609 次调用 14.9s；数组索引值与 Series 取数完全一致）
        _rev_arr = grp[rev_col].to_numpy(dtype="float64", na_value=np.nan)
        _pos_idx = np.nonzero(_rev_arr > 0)[0]
        duration_months = 1  # 至少1个月
        stage_seq = []
        if n_months >= 3:
            for i in range(max(0, n_months - 12), n_months):
                stage_seq.append(_estimate_historical_stage_arr(
                    _rev_arr, _pos_idx, i, n_months,
                    onboarding_max_months,
                    _hist_decline_mul, _hist_growth_mul,
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

        _recent6_by_cid[cid] = recent6_rev  # [批次⑥ P4] 供成熟期修正复用

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
        # [批次⑥ P4] 近6月营收直接在主循环记录（值与原"再跑两遍全表 groupby"逐位一致），
        # 原实现在此对 df.groupby(cust_col) 又完整迭代两遍（每遍 3032 组逐组 sort+过滤）
        cid_to_recent6 = _recent6_by_cid

        if channel_map is not None:
            # [批次⑥ P4] 渠道→客户列表预计算一次（原为每个成熟期客户都全表扫描 3032 客户）
            _chan_peers = {}
            for pid in out[cust_col].tolist():
                if cid_to_recent6.get(pid, 0) > 0:
                    _chan_peers.setdefault(channel_map.get(pid, "未知"), []).append(pid)
            # 按渠道分组排名
            maturity_mask = out["客户旅程阶段"] == "成熟期"
            for idx in out[maturity_mask].index:
                cid = out.at[idx, cust_col]
                ch = channel_map.get(cid, "未知")
                peers = _chan_peers.get(ch, [])
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
    except (ValueError, TypeError):
        return 999


def _estimate_historical_stage_arr(
    rev_arr, pos_idx, idx, n_months,
    onboarding_max_months,
    hist_decline_mul, hist_growth_mul,
) -> str:
    """估计某个月份客户的旅程阶段（数组版，[批次⑥ P4] 性能等价改写）。

    与原 _estimate_historical_stage 语义逐条一致，仅把 Series.iloc/.get/掩码扫描
    换成调用方预计算的 numpy 数组：
      - rev_arr: 客户按月升序的 rev_sum 数组
      - pos_idx: rev_arr > 0 的位置数组（替代每次调用 grp[grp["rev_sum"]>0].index[0]）
      - 乘数配置由调用方顶部读取一次传入（原在函数内每次 import 读取，值相同）

    判定逻辑（与原一致）：
      - 流失期：当月无交易额
      - 导入期：首次交易后 onboarding_max_months 个月内
      - 衰退期：后续3月收入趋势持续下降
      - 预警期：后续3月波动下降或近期交易额低迷
      - 爬坡期：后续3月收入持续增长
      - 稳定期：其余情况
    """
    rev = rev_arr[idx]

    # 流失期：当月无交易
    if rev == 0:
        return "流失期"

    # 导入期：首次交易后指定月数内
    first_rev_idx = pos_idx[0] if len(pos_idx) > 0 else idx
    months_since_first = idx - first_rev_idx
    if months_since_first <= onboarding_max_months:
        return "导入期"

    # 后续趋势判断：最多看后续3个月
    lookahead = min(idx + 4, n_months)
    future_months = list(range(idx + 1, lookahead))
    if len(future_months) >= 2:
        future_revs = [rev_arr[fi] for fi in future_months if fi < n_months]

        if len(future_revs) >= 2:
            # 连续下降/增长判定（乘数从配置读取）
            declines = sum(
                1 for i in range(1, len(future_revs))
                if future_revs[i] < future_revs[i - 1] * hist_decline_mul
            )
            # 连续增长
            grows = sum(
                1 for i in range(1, len(future_revs))
                if future_revs[i] > future_revs[i - 1] * hist_growth_mul
            )

            if declines >= 2:
                return "衰退期"
            if declines >= 1:
                return "预警期"
            if grows >= 2:
                return "爬坡期"

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
