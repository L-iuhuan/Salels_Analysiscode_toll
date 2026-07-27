"""
销售能力画像 v4.13 — 8维能力评分（业绩+能力双轮驱动）

设计理念:
  KA/AA客户是公司分配 → 不计入能力维度, 但计入绝对贡献
  销售额代表管理+维系+长期积累 → 纳入绝对贡献力(20%)
  新增: 客户升级力(10%) + 产品结构优化力(10%)
"""

import pandas as pd
import numpy as np


def build_sales_profile(portrait_df: pd.DataFrame, silver: dict = None) -> pd.DataFrame:
    """构建销售人员的9维能力画像（v4.14：分层评比+组合抗风险）。

    分层逻辑: 按总营收分为重量级(>1000万)/中量级(100-1000万)/轻量级(<100万)，
    每个量级内部独立排名，避免332客户和12客户同尺竞争。
    """
    df = portrait_df.copy()
    if "业务负责人" not in df.columns:
        return pd.DataFrame()

    owners = df["业务负责人"].unique()
    owners = [o for o in owners if o and str(o) != "未知"]

    results = []
    for owner in owners:
        subset = df[df["业务负责人"] == owner]
        non_ka = subset[~subset["客户层级"].isin(["KA", "AA"])]
        scores = {}

        scores["绝对贡献力"] = _score_absolute(subset)
        scores["客户维系力"] = _score_retention(subset)
        scores["品类拓展力"] = _score_category_expand(subset)
        scores["定价博弈力"] = _score_pricing(subset, non_ka)
        scores["新客开拓力"] = _score_acquisition(subset)
        scores["客户激活力"] = _score_activation(subset)
        scores["客户升级力"] = _score_upgrade(subset)
        scores["产品结构优化力"] = _score_mix_improvement(subset)
        scores["组合抗风险力"] = _score_diversification(subset)  # 🆕

        # v4.14 权重
        # v4.14最终: 绝对贡献35%确保销冠不被per-customer指标拉低
        w = {"绝对贡献力": 0.35, "客户维系力": 0.10, "品类拓展力": 0.10,
             "定价博弈力": 0.06, "新客开拓力": 0.08, "客户激活力": 0.06,
             "客户升级力": 0.10, "产品结构优化力": 0.08, "组合抗风险力": 0.07}
        composite = sum(scores[k] * w[k] for k in scores)
        scores["综合能力分"] = round(composite, 1)

        # 量级
        total_rev = subset["近12月收入"].fillna(0).sum()
        if total_rev > 10_000_000: tier = "重量级"
        elif total_rev > 1_000_000: tier = "中量级"
        else: tier = "轻量级"

        row = {"业务负责人": owner, "客户总数": len(subset),
               "总营收": round(total_rev, 0),
               "KA_AA客户数": int(subset["客户层级"].isin(["KA","AA"]).sum()),
               "量级": tier}
        row.update({k: round(v, 1) for k, v in scores.items()})
        results.append(row)

    result = pd.DataFrame(results)

    # ── 分层评比: 量级→客户数亚组, 同结构比较 ──
    result["能力等级"] = "C级"
    result["亚组"] = ""
    for tier_name in ["重量级", "中量级", "轻量级"]:
        tier_mask = result["量级"] == tier_name
        tier_df = result.loc[tier_mask]
        # 亚组: 按客户数分
        for _, row in tier_df.iterrows():
            n = row["客户总数"]
            if n > 150: sub = "批量型"
            elif n > 50: sub = "均衡型"
            else: sub = "大客户型"
            result.loc[tier_mask & (result["业务负责人"] == row["业务负责人"]), "亚组"] = sub

        for sub_name in ["大客户型", "均衡型", "批量型"]:
            sub_mask = tier_mask & (result["亚组"] == sub_name)
            sub_df = result.loc[sub_mask]
            if len(sub_df) < 2:
                result.loc[sub_mask, "能力等级"] = "B级"
                continue
            rank = sub_df["综合能力分"].rank(pct=True) * 100
            result.loc[sub_mask & (rank >= 70), "能力等级"] = "A级"
            result.loc[sub_mask & (rank >= 40) & (rank < 70), "能力等级"] = "B级"
            result.loc[sub_mask & (rank < 25), "能力等级"] = "D级"

    # 硬保护: 营收>8000万→A级; 营收=0→D级（最后执行,不被覆盖）
    result.loc[result["总营收"] > 80_000_000, "能力等级"] = "A级"
    result.loc[result["总营收"] <= 0, "能力等级"] = "D级"

    result = result.sort_values(["量级", "综合能力分"], ascending=[True, False])
    return result


def _score_diversification(subset):
    """组合抗风险力: 客户营收集中度越低越稳定 (v4.14新增)"""
    rev = subset["近12月收入"].fillna(0)
    total = rev.sum()
    if total <= 0: return 50.0
    hhi = ((rev / total) ** 2).sum()  # 0~1
    score = (1 - hhi) * 100  # 转成0-100, 越高越分散
    return max(0, min(100, score))


# ═══════════════════════════════════════════════════════════════
# 维度评分函数
# ═══════════════════════════════════════════════════════════════

def _score_absolute(subset):
    """绝对贡献力: 总营收+总毛利+增长率"""
    score = 50.0
    total_rev = subset["近12月收入"].fillna(0).sum()
    total_profit = subset["近12月毛利"].fillna(0).sum()

    # 营收评分(log scale): 10万=40分, 100万=60分, 1000万=80分, 1亿=100分
    if total_rev > 0:
        rev_score = min(100, max(20, np.log10(total_rev) * 20))
        score += (rev_score - 50) * 0.5

    # 毛利评分
    if total_profit > 0:
        profit_score = min(100, max(20, np.log10(total_profit + 1) * 20))
        score += (profit_score - 50) * 0.3

    # 增长率
    growth = subset["收入增长率"].dropna()
    if len(growth) > 0:
        avg_growth = growth.median() * 100  # 转换为%
        score += min(max(avg_growth, -20), 50) * 0.2

    return max(0, min(100, score))


def _score_retention(subset):
    """客户维系力: 长期客户占比+存续时长+活跃占比"""
    score = 50.0
    total = len(subset)
    if total == 0: return score

    # 活跃客户占比
    active = (subset["近12月收入"].fillna(0) > 0).sum()
    active_pct = active / total * 100
    score += (active_pct - 40) * 0.4

    # 长期客户占比(存续>24月): 用首次交易在2年前近似
    if "首次交易日期" in subset.columns:
        first_dates = pd.to_datetime(subset["首次交易日期"], errors="coerce")
        long_term = (first_dates < pd.Timestamp.now() - pd.DateOffset(months=24)).sum()
        long_pct = long_term / total * 100
        score += min(long_pct * 0.3, 20)

    return max(0, min(100, score))


def _score_pricing(all_cust, non_ka):
    """定价博弈力: 负毛利控制+高利润绝对数(v4.14: 加入绝对数奖励)"""
    score = 50.0
    total = len(all_cust)
    if total == 0: return score

    # 负毛利客户占比
    neg_col = None
    for c in all_cust.columns:
        if "负毛利" in c and "品种" in c: neg_col = c; break
    if neg_col:
        neg_pct = (all_cust[neg_col] > 0).sum() / max(total, 1) * 100
        score += (100 - min(neg_pct * 2, 100)) * 0.2  # 降权

    # 高利润客户绝对数(排除KA/AA)
    if "利润等级" in non_ka.columns and len(non_ka) > 0:
        high_n = (non_ka["利润等级"] == "高利润").sum()
        high_pct = high_n / max(len(non_ka), 1) * 100
        score += (high_pct - 30) * 0.25  # 降权
        score += min(np.log10(max(high_n, 1)) * 15, 25)  # 绝对数奖励

    # 低价品惩罚(降权)
    low_cols = [c for c in all_cust.columns if "低价" in c and "占比" in c]
    if low_cols and len(all_cust) > 0:
        avg_low = all_cust[low_cols[0]].mean()
        score -= min(avg_low, 50) * 0.2

    return max(0, min(100, score))


def _score_acquisition(subset):
    """新客开拓力: 真正新客+沉睡唤醒"""
    score = 50.0
    total = len(subset)
    if total == 0: return score

    lifecycle = subset.get("客户生命周期", pd.Series())
    journey = subset.get("客户旅程阶段", pd.Series())
    days = subset.get("距上次采购天数", pd.Series())

    # A: 真正新客(导入期+爬坡期) 100%权重
    new_cust = (lifecycle.isin(["导入期", "爬坡期"])).sum()
    score += (new_cust / max(total, 1) * 100) * 0.5

    # B: 沉睡唤醒 (浅50%|中30%|深100%)
    shallow = ((journey == "激活期") & days.between(1, 365)).sum()
    medium = ((journey == "激活期") & days.between(366, 730)).sum()
    deep = ((journey == "激活期") & (days > 730)).sum()
    score += (shallow * 0.5 + medium * 0.3 + deep * 1.0) / max(total, 1) * 100 * 0.5

    # C: 新客质量(B级以上)
    if "综合价值层级" in subset.columns and new_cust > 0:
        new_quality = subset[lifecycle.isin(["导入期", "爬坡期"])]
        quality = (new_quality["综合价值层级"].isin(["S","A","B"])).sum() / max(len(new_quality), 1) * 100
        score += (quality - 40) * 0.2

    return max(0, min(100, score))


def _score_category_expand(subset):
    """品类拓展力: 品类覆盖占比 + 绝对多品类客户数"""
    score = 50.0
    total = len(subset)
    if total == 0: return score

    # 多品类客户占比(≥3品类)
    if "实际品类数" in subset.columns:
        multi = (subset["实际品类数"] >= 3)
        multi_pct = multi.sum() / max(total, 1) * 100
        score += (multi_pct - 30) * 0.3  # 占比权重降低

        # 绝对数奖励: 多品类客户绝对数 (log scale, 照顾量大销售)
        multi_n = multi.sum()
        score += min(np.log10(max(multi_n, 1)) * 20, 30)  # 10人=20分, 50人=34分, 100人=40分

    # 新品渗透
    if "新品采购占比" in subset.columns:
        has_new = (subset["新品采购占比"] > 0).sum()
        score += min(has_new / max(total, 1) * 100, 30) * 0.3
        avg_new = subset["新品采购占比"].mean()
        score += min(avg_new * 1.5, 15)

    return max(0, min(100, score))


def _score_activation(subset):
    """客户激活力: 休眠唤醒数"""
    score = 50.0
    total = len(subset)
    if total == 0: return score

    strategy = subset.get("策略名称", pd.Series())
    s6 = strategy.str.contains("激活试探", na=False)
    lifecycle = subset.get("客户生命周期", pd.Series())
    activated = (lifecycle.isin(["导入期","爬坡期","成熟期"])) & s6

    if s6.sum() > 0:
        rate = activated.sum() / s6.sum() * 100
        score += (rate - 20) * 0.5
    return max(0, min(100, score))


def _score_upgrade(subset):
    """客户升级力: S/A客户绝对数+占比双维度 (v4.13修正)

    用绝对数衡量"培养了多少优质客户"(不受总客户数影响),
    用占比作为辅助调节(防止只做大客户忽视中小客户成长).
    """
    score = 50.0
    non_ka = subset[~subset["客户层级"].isin(["KA","AA"])]
    if len(non_ka) == 0: return score

    tier = non_ka.get("综合价值层级", pd.Series())
    sa_count = tier.isin(["S","A"]).sum()
    sa_pct = sa_count / max(len(non_ka), 1) * 100

    # 绝对数: 0人=30分, 5人=50分, 10人=65分, 20人=80分, 30人=100分
    score += min(sa_count * 2.5, 50)  # 绝对数最多加50分
    # 占比: 15%=基准, 每高5%加5分
    score += max(0, (sa_pct - 15) * 1.0)
    return max(0, min(100, score))


def _score_mix_improvement(subset):
    """产品结构优化力: 高利润客户绝对数+毛利率中位数 (v4.13修正)

    高利润客户越多=产品结构越偏高端。毛利率中位数作为辅助。
    """
    score = 50.0
    total = len(subset)
    if total == 0: return score

    # 高利润客户绝对数(含KA/AA): log scale, 1人=30分, 10人=50分, 50人=70分, 100人=90分
    if "利润等级" in subset.columns:
        high_n = (subset["利润等级"] == "高利润").sum()
        score += min(np.log10(max(high_n, 1)) * 30, 40)

    # 毛利率中位数
    margin = subset["近12月毛利率"].dropna()
    if len(margin) > 0:
        median_margin = margin.median()
        score += min(max(0, (median_margin - 15) * 0.5), 20)

    return max(0, min(100, score))
