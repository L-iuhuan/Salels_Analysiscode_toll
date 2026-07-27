"""
集团聚合模块。

功能：
  1. 识别客户所属集团（手工映射 + 自动前缀检测）
  2. 聚合集团级指标（成员数、总采购额、总毛利、产品线覆盖等）
  3. 标记集团级风险信号
"""

import re
import os
import sys
import pandas as pd
import numpy as np

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from config.settings import GROUP_MAPPING, GROUP_AGGREGATION, GROUP_LIFECYCLE_ACTIVE_STAGES, GROUP_LIFECYCLE_DORMANT_STAGES, GROUP_RISK_THRESHOLDS


# ============================================================
# 集团识别
# ============================================================

def _extract_chinese_prefix(name: str, n_chars: int = 3) -> str:
    """提取公司名的前N个中文字符作为集团候选前缀。"""
    chinese_chars = re.findall(r"[一-鿿]+", str(name))
    if chinese_chars:
        return chinese_chars[0][:n_chars]
    return ""


def identify_group(
    df: pd.DataFrame,
    name_col: str = "客户编号",
    group_mapping: dict = None,
    auto_detect: bool = True,
) -> pd.DataFrame:
    """识别每个客户所属集团，增加 _集团名称 字段。

    匹配优先级：
      1. 手工映射（GROUP_MAPPING 关键词匹配）
      2. 自动前缀检测（≥3个中文字符 + ≥min_members 成员）

    参数:
        df: 客户全景 DataFrame
        name_col: 客户名称列名
        group_mapping: 手工映射字典 {集团名: [关键词列表]}
        auto_detect: 是否启用自动前缀检测

    返回:
        DataFrame: 增加了 _集团名称 字段
    """
    result = df.copy()
    result["_集团名称"] = ""

    if group_mapping is None:
        group_mapping = GROUP_MAPPING

    names = result[name_col].astype(str).str.strip()

    # Step 1: 手工映射
    for group_name, keywords in group_mapping.items():
        for kw in keywords:
            mask = names.str.contains(kw, na=False, case=False)
            # 仅标记尚未归入集团的客户
            result.loc[mask & (result["_集团名称"] == ""), "_集团名称"] = group_name

    n_mapped = (result["_集团名称"] != "").sum()
    print(f"  [集团聚合] 手工映射: {n_mapped} 个客户归入 {len(group_mapping)} 个集团")

    # Step 2: 自动前缀检测
    if auto_detect and GROUP_AGGREGATION.get("auto_detect", True):
        min_len = GROUP_AGGREGATION.get("min_prefix_len", 3)
        min_members = GROUP_AGGREGATION.get("min_members", 3)
        exclude = set(GROUP_AGGREGATION.get("exclude_prefixes", []))

        # 对未归入集团的客户做前缀统计
        remaining = result["_集团名称"] == ""
        remaining_names = names[remaining]

        prefixes = remaining_names.apply(
            lambda x: _extract_chinese_prefix(x, min_len)
        )
        prefix_counts = prefixes.value_counts()
        # 过滤掉少于 min_members 的前缀和排除列表中的城市前缀
        valid_prefixes = prefix_counts[
            (prefix_counts >= min_members)
            & ~prefix_counts.index.isin(exclude)
        ]

        for prefix in valid_prefixes.index:
            if not prefix:
                continue
            member_mask = remaining & (prefixes == prefix)
            n_members = member_mask.sum()
            result.loc[member_mask, "_集团名称"] = f"{prefix}...（{n_members}家）"

        n_auto = (result["_集团名称"] != "").sum() - n_mapped
        print(f"  [集团聚合] 自动检测: 新增 {n_auto} 个客户归入 {len(valid_prefixes)} 个集团前缀")

    n_total = (result["_集团名称"] != "").sum()
    print(f"  [集团聚合] 共计: {n_total}/{len(result)} 个客户有集团归属")

    return result


# ============================================================
# 集团级聚合指标
# ============================================================

def calc_group_aggregation(
    df: pd.DataFrame,
    cust_x_prod: pd.DataFrame = None,
    cat_col: str = "产品一级分类",
) -> pd.DataFrame:
    """计算集团级聚合指标。

    输入：已含 _集团名称 字段的客户全景 DataFrame
    可选：cust_x_prod — customer_x_product 表，用于计算真实产品线并集
    输出：集团级 DataFrame（每集团一行）
    """
    grouped = df[df["_集团名称"] != ""].copy()
    if len(grouped) == 0:
        print("  [集团聚合] 无集团数据，跳过聚合")
        return pd.DataFrame()

    agg_list = []
    for group_name, grp in grouped.groupby("_集团名称"):
        n_members = len(grp)

        row = {"集团名称": group_name, "成员数": n_members}

        # 财务汇总
        for col in ["近12月收入", "近12月毛利", "订单数"]:
            if col in grp.columns:
                row[col] = grp[col].fillna(0).sum()
            else:
                row[col] = 0

        # 平均毛利率（加权）
        total_rev = row.get("近12月收入", 0)
        total_profit = row.get("近12月毛利", 0)
        row["集团加权毛利率"] = (
            round(total_profit / total_rev * 100, 1)
            if total_rev > 0 else 0.0
        )

        # 产品线覆盖（并集 — 从原始数据计算唯一品类数）
        if cust_x_prod is not None and cat_col in cust_x_prod.columns:
            grp_ids = set(grp["客户编号"])
            row["集团产品线覆盖"] = int(
                cust_x_prod[cust_x_prod["客户编号"].isin(grp_ids)][cat_col].nunique()
            )
        elif "产品线数" in grp.columns:
            # 回退：求和（不准确，但无原始数据时勉强可用）
            row["集团产品线覆盖"] = int(grp["产品线数"].fillna(0).sum())
        else:
            row["集团产品线覆盖"] = 0

        # 衰退风险
        for img in ["预警增长_金额", "隐性衰退_金额", "衰退期_金额"]:
            if img in grp.columns:
                row.setdefault(f"集团_{img}", grp[img].fillna(0).sum())

        if total_rev > 0:
            risk_amount = sum(
                row.get(f"集团_{img}", 0) for img in
                ["预警增长_金额", "隐性衰退_金额", "衰退期_金额"]
            )
            row["集团衰退风险占比"] = round(risk_amount / total_rev * 100, 1)
        else:
            row["集团衰退风险占比"] = 0.0

        # 集团活跃度
        if "客户生命周期" in grp.columns:
            lifecycle_stages = grp["客户生命周期"].value_counts()
            row["集团活跃成员"] = int(
                grp["客户生命周期"].isin(GROUP_LIFECYCLE_ACTIVE_STAGES).sum()
            )
            row["集团流失/休眠成员"] = int(
                grp["客户生命周期"].isin(GROUP_LIFECYCLE_DORMANT_STAGES).sum()
            )
        else:
            row["集团活跃成员"] = n_members
            row["集团流失/休眠成员"] = 0

        # 集团风险标记（阈值来自 settings.py:GROUP_RISK_THRESHOLDS）
        _grt = GROUP_RISK_THRESHOLDS
        if n_members > 0 and row["集团流失/休眠成员"] >= n_members * _grt.get("全成员停滞阈值", 1.0):
            row["集团风险"] = "高危（全部成员停滞）"
        elif row["集团流失/休眠成员"] > n_members * _grt.get("多数停滞阈值", 0.5):
            row["集团风险"] = "警告（大部分成员停滞）"
        elif row["集团衰退风险占比"] > _grt.get("衰退品占比阈值", 50.0):
            row["集团风险"] = "关注（衰退品占比高）"
        else:
            row["集团风险"] = "正常"

        # 成员名单
        member_names = grp["客户编号"].tolist() if "客户编号" in grp.columns else []
        row["集团成员"] = "、".join(member_names)

        agg_list.append(row)

    agg_df = pd.DataFrame(agg_list)
    agg_df = agg_df.sort_values("近12月收入", ascending=False, kind='stable').reset_index(drop=True)
    return agg_df


# ============================================================
# 主入口
# ============================================================

def run_group_aggregation(
    customer_df: pd.DataFrame,
    cust_x_prod: pd.DataFrame = None,
    cat_col: str = "产品一级分类",
) -> dict:
    """执行集团聚合全流程。

    参数:
        customer_df: 客户全景 DataFrame
        cust_x_prod: customer_x_product 表（可选，用于计算真实产品线并集）
        cat_col: 品类列名

    返回:
        dict: {"customer_df": 增加集团归属, "group_df": 集团聚合表}
    """
    if not GROUP_AGGREGATION.get("enabled", True):
        return {"customer_df": customer_df, "group_df": pd.DataFrame()}

    # 识别集团
    result = identify_group(customer_df)

    # 聚合集团指标
    group_df = calc_group_aggregation(result, cust_x_prod=cust_x_prod, cat_col=cat_col)

    # 输出
    output_dir = os.path.join(PROJECT_ROOT, "output", "gold")
    os.makedirs(output_dir, exist_ok=True)

    if len(group_df) > 0:
        group_df.to_csv(
            os.path.join(output_dir, "集团聚合.csv"),
            index=False, encoding="utf-8-sig",
        )
        print(f"  [集团聚合] 输出 {len(group_df)} 个集团到 Gold 层")

    return {"customer_df": result, "group_df": group_df}
