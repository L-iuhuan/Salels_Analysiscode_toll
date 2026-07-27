# -*- coding: utf-8 -*-
# run_0.0.7_corrected_hierarchy_eligibility.py
# 实验 0.0.7: 字段修正版层级准入
# 使用锁定字段口径，读取原始Excel直接评估各产品线在各预测层级上的数据就绪度
# 创建: 2026-06-12

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# ── 项目根目录 ──────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXPERIMENT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = EXPERIMENT_DIR / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ── 固定种子 ────────────────────────────────────────────────
np.random.seed(42)

EPS = 1e-9

# ── 字段口径：按 field_spec_locked_20260612.md ──────────────
# 使用字段（按锁定口径，从原始Excel读取）:
#   发货日期, 型号_产品线（新）, 型号_产品品类, 存货编码, 存货名称,
#   终端客户简称, 代理商/直供名称, 实际终端客户, 终端客户名称_客户类别,
#   发货数量, RMB 未税金额小计

RAW_COLUMNS = [
    "发货日期", "型号_产品线（新）", "型号_产品品类",
    "存货编码", "存货名称",
    "终端客户简称", "代理商/直供名称", "实际终端客户", "终端客户名称_客户类别",
    "发货数量", "RMB 未税金额小计",
]

# ── Excel 读取：优先 calamine，fallback openpyxl ───────────
def read_excel_auto(path, sheet_name=0, usecols=None, **kwargs):
    """优先使用 calamine 引擎，fallback openpyxl。"""
    try:
        import python_calamine  # noqa: F401
        _has_calamine = True
    except ImportError:
        _has_calamine = False

    if _has_calamine:
        df = pd.read_excel(path, sheet_name=sheet_name, engine="calamine", **kwargs)
        if callable(usecols):
            keep = [c for c in df.columns if usecols(c)]
            df = df[keep]
        elif usecols is not None:
            df = df[usecols]
        return df
    else:
        return pd.read_excel(path, sheet_name=sheet_name, usecols=usecols, **kwargs)


# ── 操作日志 ─────────────────────────────────────────────────
class OperationLog:
    def __init__(self) -> None:
        self.rows: List[Dict[str, object]] = []
        self.t0 = time.time()

    def add(self, step: str, op: str, result: str, file: str = "", n_rows: Optional[int] = None) -> None:
        self.rows.append({
            "时间": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
            "耗时秒": round(time.time() - self.t0, 2),
            "步骤": step,
            "操作": op,
            "结果": result,
            "文件": file,
            "行数": n_rows,
        })

    def to_frame(self) -> pd.DataFrame:
        return pd.DataFrame(self.rows)


# ══════════════════════════════════════════════════════════════
# 主流程
# ══════════════════════════════════════════════════════════════

def main():
    log = OperationLog()
    print("=" * 80)
    print("EXPERIMENT 0.0.7: 字段修正版层级准入")
    print("=" * 80)

    # ── 1. 读取原始Excel ────────────────────────────────────
    data_path = PROJECT_ROOT / "data" / "财务分析-5月（6.3）.xlsx"
    sheet_name = "总表"
    print(f"\n[1] 读取原始Excel: {data_path} / sheet={sheet_name}")
    print(f"    优先使用 calamine 引擎...")

    df_raw = read_excel_auto(
        data_path,
        sheet_name=sheet_name,
        usecols=lambda c: c in set(RAW_COLUMNS),
    )
    log.add("01读取", "读取原始Excel必要字段",
            f"工作表={sheet_name}, 列数={len(df_raw.columns)}, 原始行数={len(df_raw):,}",
            str(data_path), len(df_raw))

    # 缺失列补全
    for c in RAW_COLUMNS:
        if c not in df_raw.columns:
            df_raw[c] = pd.NA
            log.add("01读取", f"列缺失补NA", f"列={c}", "", 0)

    print(f"    读取完成: {len(df_raw):,} 行, {len(df_raw.columns)} 列")
    print(f"    实际列: {list(df_raw.columns)}")

    # ── 2. 清洗 ─────────────────────────────────────────────
    print(f"\n[2] 数据清洗...")
    before_clean = len(df_raw)

    # 2a. 发货日期解析
    df_raw["发货日期"] = pd.to_datetime(df_raw["发货日期"], errors="coerce")
    invalid_date = df_raw["发货日期"].isna().sum()

    # 2b. 数值列
    for c in ["发货数量", "RMB 未税金额小计"]:
        df_raw[c] = pd.to_numeric(df_raw[c], errors="coerce")

    # 2c. 字符串列 strip
    str_cols = [
        "型号_产品线（新）", "型号_产品品类", "存货编码", "存货名称",
        "终端客户简称", "代理商/直供名称", "实际终端客户", "终端客户名称_客户类别",
    ]
    for c in str_cols:
        if c in df_raw.columns:
            df_raw[c] = df_raw[c].astype("string").str.strip()
            df_raw.loc[df_raw[c] == "", c] = pd.NA

    # 2d. 过滤：发货日期有效、发货数量 > 0
    mask_valid = df_raw["发货日期"].notna() & (df_raw["发货数量"].fillna(0) > 0)
    df = df_raw[mask_valid].copy()
    non_pos_qty = (df_raw["发货数量"].fillna(0) <= 0).sum()

    log.add("02清洗", "过滤无效日期和零/负数量",
            f"剔除无效日期={invalid_date}, 剔除负/零数量={non_pos_qty}, "
            f"清洗前={before_clean:,}, 清洗后={len(df):,}",
            "", len(df))

    print(f"    清洗前: {before_clean:,} 行")
    print(f"    无效日期剔除: {invalid_date}")
    print(f"    负/零数量剔除: {non_pos_qty}")
    print(f"    清洗后: {len(df):,} 行")

    # ── 3. 缺失处理：产品线、品类 ────────────────────────────
    print(f"\n[3] 缺失处理...")

    # 3a. 产品线缺失 → 未分类
    pline_missing_mask = df["型号_产品线（新）"].isna()
    df.loc[pline_missing_mask, "型号_产品线（新）"] = "未分类"
    n_pline_filled = pline_missing_mask.sum()
    log.add("03缺失处理", "产品线缺失归'未分类'",
            f"填充行数={n_pline_filled}", "", n_pline_filled)
    print(f"    产品线缺失→未分类: {n_pline_filled} 行")

    # 3b. 品类缺失 → 未知品类
    cat_missing_mask = df["型号_产品品类"].isna()
    df.loc[cat_missing_mask, "型号_产品品类"] = "未知品类"
    n_cat_filled = cat_missing_mask.sum()
    log.add("03缺失处理", "品类缺失归'未知品类'",
            f"填充行数={n_cat_filled}", "", n_cat_filled)
    print(f"    品类缺失→未知品类: {n_cat_filled} 行")

    # ── 4. 派生字段：按锁定口径 ──────────────────────────────
    print(f"\n[4] 派生预测字段（按锁定口径）...")

    # 4a. SKU预测键 = 存货编码 → 存货名称 → 未知SKU
    df["SKU预测键_来源"] = "存货编码"
    df["SKU预测键"] = df["存货编码"].astype(str).str.strip()
    sku_mask1 = df["SKU预测键"].isna() | (df["SKU预测键"] == "")
    df.loc[sku_mask1, "SKU预测键"] = df.loc[sku_mask1, "存货名称"].astype(str).str.strip()
    df.loc[sku_mask1 & df["SKU预测键"].notna() & (df["SKU预测键"] != ""), "SKU预测键_来源"] = "存货名称"
    sku_mask2 = df["SKU预测键"].isna() | (df["SKU预测键"] == "")
    df.loc[sku_mask2, "SKU预测键"] = "未知SKU"
    df.loc[sku_mask2, "SKU预测键_来源"] = "兜底_未知SKU"
    n_sku_unknown = sku_mask2.sum()
    log.add("04派生", "SKU预测键派生",
            f"存货编码→存货名称→未知SKU, 未知SKU行数={n_sku_unknown}", "", n_sku_unknown)
    print(f"    SKU预测键: 未知SKU={n_sku_unknown} 行")

    # 4b. 预测客户名称 = 终端客户简称 → 代理商/直供名称 → 实际终端客户 → 未知终端客户
    df["预测客户名称_来源"] = "终端客户简称"
    df["预测客户名称"] = df["终端客户简称"].astype(str).str.strip()
    cust_mask1 = df["预测客户名称"].isna() | (df["预测客户名称"] == "")
    df.loc[cust_mask1, "预测客户名称"] = df.loc[cust_mask1, "代理商/直供名称"].astype(str).str.strip()
    df.loc[cust_mask1 & df["预测客户名称"].notna() & (df["预测客户名称"] != ""), "预测客户名称_来源"] = "代理商/直供名称"
    cust_mask2 = df["预测客户名称"].isna() | (df["预测客户名称"] == "")
    df.loc[cust_mask2, "预测客户名称"] = df.loc[cust_mask2, "实际终端客户"].astype(str).str.strip()
    df.loc[cust_mask2 & df["预测客户名称"].notna() & (df["预测客户名称"] != ""), "预测客户名称_来源"] = "实际终端客户"
    cust_mask3 = df["预测客户名称"].isna() | (df["预测客户名称"] == "")
    df.loc[cust_mask3, "预测客户名称"] = "未知终端客户"
    df.loc[cust_mask3, "预测客户名称_来源"] = "兜底_未知终端客户"
    n_cust_unknown = cust_mask3.sum()
    log.add("04派生", "预测客户名称派生",
            f"终端客户简称→代理商→实际终端→未知终端客户, 未知终端客户行数={n_cust_unknown}", "", n_cust_unknown)
    print(f"    预测客户名称: 未知终端客户={n_cust_unknown} 行")

    # 4c. 客户类别预测 = 终端客户名称_客户类别, 缺失归 Unknown
    df["客户类别预测"] = df["终端客户名称_客户类别"].astype(str).str.strip()
    tier_mask = df["客户类别预测"].isna() | (df["客户类别预测"] == "")
    df.loc[tier_mask, "客户类别预测"] = "Unknown"
    n_tier_unknown = tier_mask.sum()
    log.add("04派生", "客户类别预测派生",
            f"终端客户名称_客户类别→Unknown, Unknown行数={n_tier_unknown}", "", n_tier_unknown)
    print(f"    客户类别预测: Unknown={n_tier_unknown} 行")

    # ── 5. 时间窗口 ──────────────────────────────────────────
    print(f"\n[5] 确定时间窗口...")
    df["month_key"] = df["发货日期"].dt.to_period("M")
    df["year"] = df["发货日期"].dt.year

    all_months = sorted(df["month_key"].unique())
    latest_month = all_months[-1]
    cutoff_36m = latest_month - 35  # 最近36个完整月
    recent_36_months = [m for m in all_months if m >= cutoff_36m]
    actual_n_months = len(recent_36_months)

    log.add("05时间窗口", "确定36个月窗口",
            f"最新月份={latest_month}, 窗口={recent_36_months[0]}~{recent_36_months[-1]}, "
            f"可用月数={actual_n_months}", "", actual_n_months)

    print(f"    日期范围: {df['发货日期'].min().date()} ~ {df['发货日期'].max().date()}")
    print(f"    最新月份: {latest_month}")
    print(f"    36月窗口: {recent_36_months[0]} ~ {recent_36_months[-1]} ({actual_n_months} 个月)")

    # ── 6. 产品线列表 ────────────────────────────────────────
    print(f"\n[6] 产品线识别...")
    df["产品线键"] = df["型号_产品线（新）"].fillna("未分类")
    product_lines = sorted(df["产品线键"].unique())
    log.add("06产品线", "识别产品线",
            f"产品线数={len(product_lines)}", "", len(product_lines))
    for i, pl in enumerate(product_lines):
        n_rows = (df["产品线键"] == pl).sum()
        n_months = df[df["产品线键"] == pl]["month_key"].nunique()
        print(f"    {i+1:2d}. {pl}: {n_rows:,} 行, {n_months} 个月")

    # ── 7. 逐产品线计算准入 ──────────────────────────────────
    print(f"\n[7] 逐产品线计算层级准入...")
    print(f"    {'产品线':<28s} PL_Q  PL_M  Cat_M SKU_M P_Cus C_Tier")
    print(f"    {'-'*28} {'-'*4} {'-'*4} {'-'*4} {'-'*4} {'-'*5} {'-'*6}")

    results = []
    coverage_rows = []

    for pline in product_lines:
        pline_mask = df["产品线键"] == pline
        pline_df = df[pline_mask].copy()
        total_rows_pline = len(pline_df)

        row = {"产品线": pline}

        # ─── 7a. product_line_quarterly ─────────────────────
        row["product_line_quarterly_eligible"] = True
        row["product_line_quarterly_reason"] = "OK (always eligible)"

        # ─── 7b. product_line_monthly ────────────────────────
        # 最近36个月有效月份 >= 18 且 zero-month ratio < 60%
        pline_recent = pline_df[pline_df["month_key"].isin(recent_36_months)]
        effective_months_pline = pline_recent["month_key"].nunique()
        zero_months_pline = actual_n_months - effective_months_pline
        zero_month_ratio_pline = zero_months_pline / actual_n_months if actual_n_months > 0 else 1.0

        pl_m_eligible = (effective_months_pline >= 18) and (zero_month_ratio_pline < 0.60)
        row["product_line_monthly_eligible"] = pl_m_eligible
        pl_m_reasons = []
        if effective_months_pline < 18:
            pl_m_reasons.append(f"有效月份{effective_months_pline}/{actual_n_months}<18")
        if zero_month_ratio_pline >= 0.60:
            pl_m_reasons.append(f"零月率{zero_month_ratio_pline:.1%}>=60%")
        row["product_line_monthly_reason"] = (
            "; ".join(pl_m_reasons) if pl_m_reasons else
            f"OK ({effective_months_pline}/{actual_n_months}有效月, 零月率={zero_month_ratio_pline:.1%})"
        )

        # ─── 7c. category_monthly ────────────────────────────
        # 品类数>=2，至少2个品类有>=6有效月份，未知品类销售额占比<20%
        cat_series = pline_df.groupby("型号_产品品类")["RMB 未税金额小计"].sum()
        categories = sorted(cat_series.index.tolist())
        n_categories = len(categories)

        # 未知品类销售额占比
        total_pline_sales = cat_series.sum()
        unknown_cat_sales = cat_series.get("未知品类", 0.0)
        unknown_cat_ratio = unknown_cat_sales / total_pline_sales if total_pline_sales > 0 else 0.0

        # 每个品类的36个月有效月份
        cats_with_enough_months = 0
        for cat in categories:
            cat_recent = pline_df[
                (pline_df["型号_产品品类"] == cat) &
                (pline_df["month_key"].isin(recent_36_months))
            ]
            if cat_recent["month_key"].nunique() >= 6:
                cats_with_enough_months += 1

        cat_m_reasons = []
        if n_categories < 2:
            cat_m_reasons.append(f"品类数{n_categories}<2")
        if cats_with_enough_months < 2:
            cat_m_reasons.append(f"仅{cats_with_enough_months}/{n_categories}个品类有>=6有效月")
        if unknown_cat_ratio >= 0.20:
            cat_m_reasons.append(f"未知品类销售额占比{unknown_cat_ratio:.1%}>=20%")

        cat_m_eligible = (
            n_categories >= 2
            and cats_with_enough_months >= 2
            and unknown_cat_ratio < 0.20
        )
        row["category_monthly_eligible"] = cat_m_eligible
        row["category_monthly_reason"] = (
            "; ".join(cat_m_reasons) if cat_m_reasons else
            f"OK ({n_categories}品类, {cats_with_enough_months}个>=6月, 未知品类占比={unknown_cat_ratio:.1%})"
        )

        # ─── 7d. sku_monthly ─────────────────────────────────
        # 合格SKU数>=3（合格=有效月数>=6或非零月数>=4）
        # 头部SKU累计销售额覆盖>=70%
        sku_sales = pline_df.groupby("SKU预测键")["RMB 未税金额小计"].sum().sort_values(ascending=False)
        total_sku_sales = sku_sales.sum()

        sku_eligible_set = set()
        head_skus_list = []
        cumulative_sales = 0.0
        head_covered = False

        for sku_key, sales_val in sku_sales.items():
            sku_df = pline_df[pline_df["SKU预测键"] == sku_key]
            sku_eff_months = sku_df["month_key"].nunique()
            sku_nonzero_months = sku_df[sku_df["RMB 未税金额小计"] > 0]["month_key"].nunique()

            if sku_eff_months >= 6 or sku_nonzero_months >= 4:
                sku_eligible_set.add(sku_key)

            cumulative_sales += sales_val
            if not head_covered:
                head_skus_list.append(sku_key)
                if total_sku_sales > 0 and cumulative_sales / total_sku_sales >= 0.70:
                    head_covered = True

        total_skus = len(sku_sales)
        n_eligible_skus = len(sku_eligible_set)
        n_head_skus = len(head_skus_list)
        n_head_eligible = len([s for s in head_skus_list if s in sku_eligible_set])

        sku_m_reasons = []
        MIN_ELIGIBLE_SKUS = 3
        if n_eligible_skus < MIN_ELIGIBLE_SKUS:
            sku_m_reasons.append(f"合格SKU数{n_eligible_skus}<{MIN_ELIGIBLE_SKUS}")
        if not head_covered:
            sku_m_reasons.append(f"头部SKU({n_head_skus}个)未覆盖70%销售额")

        sku_m_eligible = (n_eligible_skus >= MIN_ELIGIBLE_SKUS) and head_covered
        row["sku_monthly_eligible"] = sku_m_eligible
        row["sku_monthly_reason"] = (
            "; ".join(sku_m_reasons) if sku_m_reasons else
            f"OK ({n_eligible_skus}合格/{total_skus}SKU, {n_head_eligible}/{n_head_skus}头部合格)"
        )

        # ─── 7e. product_customer ─────────────────────────────
        # 头部SKU×预测客户名称组合:
        #   至少3个组合有效月数>=6，
        #   或者头部组合覆盖销售额>=50%且至少1个组合有效月数>=6（避免小线全部失败）
        pline_df["pc_key"] = (
            pline_df["SKU预测键"].astype(str) + "|||" + pline_df["预测客户名称"].astype(str)
        )

        pc_eff_months = pline_df.groupby("pc_key")["month_key"].nunique()
        pc_sales = pline_df.groupby("pc_key")["RMB 未税金额小计"].sum().sort_values(ascending=False)
        total_pc_sales = pc_sales.sum()

        pc_cumulative = 0.0
        head_pc_keys = []
        head_pc_eligible = 0
        head_pc_sales_sum = 0.0

        for pc_key, pc_sales_val in pc_sales.items():
            pc_cumulative += pc_sales_val
            head_pc_keys.append(pc_key)
            head_pc_sales_sum += pc_sales_val

            eff = pc_eff_months.get(pc_key, 0)
            if eff >= 6:
                head_pc_eligible += 1

            if total_pc_sales > 0 and pc_cumulative / total_pc_sales >= 0.70:
                break

        total_pc_combos = len(pc_sales)
        n_head_pc = len(head_pc_keys)
        head_pc_coverage = head_pc_sales_sum / total_pc_sales if total_pc_sales > 0 else 0.0

        pc_reasons = []
        # 规则: 至少有3个头部组合有效月数>=6
        # 或者头部组合覆盖销售额>=50%且至少1个组合有效月数>=6
        pc_eligible = False
        if n_head_pc == 0:
            pc_reasons.append("无SKU×客户组合")
        elif head_pc_eligible >= 3:
            pc_eligible = True
        elif head_pc_coverage >= 0.50 and head_pc_eligible >= 1:
            pc_eligible = True
        else:
            pc_reasons.append(
                f"仅{head_pc_eligible}/{n_head_pc}个头部组合有效月>=6 "
                f"(需>=3 或 头部覆盖>=50%且>=1)"
            )

        row["product_customer_eligible"] = pc_eligible
        row["product_customer_reason"] = (
            "; ".join(pc_reasons) if pc_reasons else
            f"OK ({head_pc_eligible}/{n_head_pc}头部组合有效月>=6, "
            f"头部覆盖={head_pc_coverage:.1%}, 共{total_pc_combos}组合)"
        )

        # ─── 7f. customer_tier ────────────────────────────────
        # 2024+ 客户类别Unknown销售额占比 <5%
        # 且 2024+ 非Unknown客户类别数 >=1
        mask_2024plus = pline_df["year"] >= 2024
        recent_2024_df = pline_df[mask_2024plus]
        total_2024_sales = recent_2024_df["RMB 未税金额小计"].sum()

        unknown_2024_sales = recent_2024_df[
            recent_2024_df["客户类别预测"] == "Unknown"
        ]["RMB 未税金额小计"].sum()
        unknown_2024_ratio = unknown_2024_sales / total_2024_sales if total_2024_sales > 0 else 0.0

        non_unknown_tiers_2024 = recent_2024_df[
            recent_2024_df["客户类别预测"] != "Unknown"
        ]["客户类别预测"].nunique()

        ct_reasons = []
        if unknown_2024_ratio >= 0.05:
            ct_reasons.append(f"2024+ Unknown销售额占比{unknown_2024_ratio:.1%}>=5%")
        if non_unknown_tiers_2024 < 1:
            ct_reasons.append(f"2024+ 非Unknown客户类别数={non_unknown_tiers_2024}<1")

        ct_eligible = (unknown_2024_ratio < 0.05) and (non_unknown_tiers_2024 >= 1)
        row["customer_tier_eligible"] = ct_eligible
        row["customer_tier_reason"] = (
            "; ".join(ct_reasons) if ct_reasons else
            f"OK (2024+ Unknown占比={unknown_2024_ratio:.1%}, "
            f"非Unknown类别={non_unknown_tiers_2024})"
        )

        # ─── 7g. 推荐层级候选 ─────────────────────────────────
        candidates = []
        if row["product_line_quarterly_eligible"]:
            candidates.append("product_line_quarterly")
        if row["product_line_monthly_eligible"]:
            candidates.append("product_line_monthly")
        if row["category_monthly_eligible"]:
            candidates.append("category_monthly")
        if row["sku_monthly_eligible"]:
            candidates.append("sku_monthly")
        if row["product_customer_eligible"]:
            candidates.append("product_customer")
        if row["customer_tier_eligible"]:
            candidates.append("customer_tier")
        row["recommended_hierarchy_candidates"] = ", ".join(candidates)

        results.append(row)

        # ─── 7h. 客户/SKU覆盖统计（用于coverage输出） ────────
        n_cust_pline = pline_df["预测客户名称"].nunique()
        n_sku_pline = pline_df["SKU预测键"].nunique()
        n_combos_pline = pline_df["pc_key"].nunique()
        n_eligible_combos = int((pc_eff_months >= 6).sum())

        # 客户fallback占比
        cust_from_backup = pline_df["预测客户名称_来源"].isin(["代理商/直供名称", "实际终端客户"]).sum()
        cust_unknown = (pline_df["预测客户名称"] == "未知终端客户").sum()
        cust_unknown_sales = pline_df[pline_df["预测客户名称"] == "未知终端客户"]["RMB 未税金额小计"].sum()

        coverage_rows.append({
            "产品线": pline,
            "总行数": total_rows_pline,
            "客户数": n_cust_pline,
            "SKU数": n_sku_pline,
            "SKU×客户组合数": n_combos_pline,
            "合格组合数(>=6月)": n_eligible_combos,
            "头部组合数": n_head_pc,
            "头部合格组合数": head_pc_eligible,
            "客户fallback行数": cust_from_backup,
            "客户fallback占比": cust_from_backup / total_rows_pline if total_rows_pline > 0 else 0.0,
            "未知终端客户行数": cust_unknown,
            "未知终端客户占比": cust_unknown / total_rows_pline if total_rows_pline > 0 else 0.0,
            "未知终端客户销售额": cust_unknown_sales,
            "未知终端客户销售额占比": cust_unknown_sales / total_pline_sales if total_pline_sales > 0 else 0.0,
        })

        # ─── 7i. 逐线状态打印 ─────────────────────────────────
        def tick(b: bool) -> str:
            return "Y" if b else "N"

        print(
            f"    {pline:<28s} {tick(row['product_line_quarterly_eligible']):>4s} "
            f"{tick(row['product_line_monthly_eligible']):>4s} "
            f"{tick(row['category_monthly_eligible']):>4s} "
            f"{tick(row['sku_monthly_eligible']):>4s} "
            f"{tick(row['product_customer_eligible']):>5s} "
            f"{tick(row['customer_tier_eligible']):>6s}"
        )

    # ── 8. 输出: 层级准入表 ──────────────────────────────────
    print(f"\n[8] 输出层级准入表...")
    out_cols = [
        "产品线",
        "product_line_quarterly_eligible", "product_line_quarterly_reason",
        "product_line_monthly_eligible", "product_line_monthly_reason",
        "category_monthly_eligible", "category_monthly_reason",
        "sku_monthly_eligible", "sku_monthly_reason",
        "product_customer_eligible", "product_customer_reason",
        "customer_tier_eligible", "customer_tier_reason",
        "recommended_hierarchy_candidates",
    ]
    out_df = pd.DataFrame(results, columns=out_cols)

    output_path1 = OUTPUT_DIR / "hierarchy_eligibility_by_pline_corrected.csv"
    out_df.to_csv(output_path1, index=False, encoding="utf-8-sig")
    log.add("08输出", "层级准入表",
            f"行数={len(out_df)}", str(output_path1), len(out_df))
    print(f"    → {output_path1} ({len(out_df)} 行)")

    # ── 9. 输出: 客户/SKU覆盖统计 ────────────────────────────
    print(f"\n[9] 输出客户/SKU覆盖统计...")
    coverage_df = pd.DataFrame(coverage_rows)
    output_path2 = OUTPUT_DIR / "customer_sku_coverage_by_pline.csv"
    coverage_df.to_csv(output_path2, index=False, encoding="utf-8-sig")
    log.add("09输出", "客户/SKU覆盖统计",
            f"行数={len(coverage_df)}", str(output_path2), len(coverage_df))
    print(f"    → {output_path2} ({len(coverage_df)} 行)")

    # ── 10. 输出: 字段使用验证 ───────────────────────────────
    print(f"\n[10] 输出字段使用验证...")

    # 定义时间段
    cutoff_2023_06 = pd.Period("2023-06", freq="M")
    cutoff_2024 = pd.Period("2024-01", freq="M")

    def compute_field_stats(sub_df: pd.DataFrame, label: str) -> dict:
        total = len(sub_df)
        if total == 0:
            return {"时间段": label, "总行数": 0}

        # 关键字段缺失/Unknown率
        pline_unknown = (sub_df["产品线键"] == "未分类").sum()
        cat_unknown = (sub_df["型号_产品品类"] == "未知品类").sum()
        sku_unknown = (sub_df["SKU预测键"] == "未知SKU").sum()
        cust_unknown = (sub_df["预测客户名称"] == "未知终端客户").sum()
        tier_unknown = (sub_df["客户类别预测"] == "Unknown").sum()

        # 客户fallback占比（使用来源字段）
        cust_from_agent = (sub_df["预测客户名称_来源"] == "代理商/直供名称").sum()
        cust_from_actual = (sub_df["预测客户名称_来源"] == "实际终端客户").sum()
        cust_from_fallback = cust_from_agent + cust_from_actual
        cust_direct = (sub_df["预测客户名称_来源"] == "终端客户简称").sum()

        # 销售额口径的Unknown占比
        total_sales = sub_df["RMB 未税金额小计"].sum()
        unknown_sku_sales = sub_df[sub_df["SKU预测键"] == "未知SKU"]["RMB 未税金额小计"].sum()
        unknown_cust_sales = sub_df[sub_df["预测客户名称"] == "未知终端客户"]["RMB 未税金额小计"].sum()
        unknown_tier_sales = sub_df[sub_df["客户类别预测"] == "Unknown"]["RMB 未税金额小计"].sum()

        return {
            "时间段": label,
            "总行数": total,
            "总销售额": total_sales,
            "产品线_未分类_行数": pline_unknown,
            "产品线_未分类_行占比": pline_unknown / total,
            "品类_未知品类_行数": cat_unknown,
            "品类_未知品类_行占比": cat_unknown / total,
            "SKU_未知SKU_行数": sku_unknown,
            "SKU_未知SKU_行占比": sku_unknown / total,
            "SKU_未知SKU_销售额占比": unknown_sku_sales / total_sales if total_sales > 0 else 0.0,
            "客户_未知终端客户_行数": cust_unknown,
            "客户_未知终端客户_行占比": cust_unknown / total,
            "客户_未知终端客户_销售额占比": unknown_cust_sales / total_sales if total_sales > 0 else 0.0,
            "客户_终端客户简称_行数": cust_direct,
            "客户_代理商fallback_行数": cust_from_agent,
            "客户_实际终端fallback_行数": cust_from_actual,
            "客户_fallback总行数": cust_from_fallback,
            "客户_fallback行占比": cust_from_fallback / total,
            "客户类别_Unknown_行数": tier_unknown,
            "客户类别_Unknown_行占比": tier_unknown / total,
            "客户类别_Unknown_销售额占比": unknown_tier_sales / total_sales if total_sales > 0 else 0.0,
        }

    global_stats = compute_field_stats(df, "全局")
    recent_202306 = df[df["month_key"] >= cutoff_2023_06]
    recent_202306_stats = compute_field_stats(recent_202306, "2023-06~最新")
    recent_2024 = df[df["month_key"] >= cutoff_2024]
    recent_2024_stats = compute_field_stats(recent_2024, "2024+")

    field_usage_df = pd.DataFrame([global_stats, recent_202306_stats, recent_2024_stats])
    output_path3 = OUTPUT_DIR / "field_usage_validation.csv"
    field_usage_df.to_csv(output_path3, index=False, encoding="utf-8-sig")
    log.add("10输出", "字段使用验证",
            f"时间段数={len(field_usage_df)}", str(output_path3), len(field_usage_df))
    print(f"    → {output_path3} ({len(field_usage_df)} 行)")

    # ── 11. 输出: 操作日志 ───────────────────────────────────
    print(f"\n[11] 输出操作日志...")
    log_df = log.to_frame()
    output_path4 = OUTPUT_DIR / "operation_log.csv"
    log_df.to_csv(output_path4, index=False, encoding="utf-8-sig")
    print(f"    → {output_path4} ({len(log_df)} 行)")

    # ── 12. 摘要 ─────────────────────────────────────────────
    print(f"\n{'='*80}")
    print("SUMMARY: Eligible product lines per hierarchy level")
    print(f"{'='*80}")
    print(f"Total product lines evaluated: {len(out_df)}")
    print()

    summary_map = {
        "product_line_quarterly_eligible": "Product Line Quarterly (always)",
        "product_line_monthly_eligible": "Product Line Monthly (>=18mo, zero<60%)",
        "category_monthly_eligible": "Category Monthly (>=2 cats, >=2 w/ >=6mo, unknown<20%)",
        "sku_monthly_eligible": "SKU Monthly (>=3 eligible, head>=70% sales)",
        "product_customer_eligible": "Product×Customer (>=3 head combos >=6mo OR coverage>=50% & >=1)",
        "customer_tier_eligible": "Customer Tier (2024+ Unknown<5%, non-Unknown tiers>=1)",
    }

    for col, desc in summary_map.items():
        eligible = out_df[col].sum()
        pct = eligible / len(out_df) * 100
        bar = "#" * int(pct / 5)
        print(f"  {desc}")
        print(f"    Eligible: {eligible}/{len(out_df)} ({pct:.0f}%) {bar}")
        if eligible < len(out_df):
            not_eligible = out_df[~out_df[col]]["产品线"].tolist()
            print(f"    Not eligible: {not_eligible}")
        print()

    # ── 13. 详细原因 ─────────────────────────────────────────
    print(f"{'='*80}")
    print("DETAILED REASONS (non-eligible)")
    print(f"{'='*80}")
    for _, row_data in out_df.iterrows():
        pl = row_data["产品线"]
        issues = []
        for col in ["product_line_monthly", "category_monthly", "sku_monthly",
                     "product_customer", "customer_tier"]:
            if not row_data[f"{col}_eligible"]:
                reason = row_data[f"{col}_reason"]
                issues.append(f"{col}: {reason}")
        if issues:
            print(f"\n  [{pl}]")
            for issue in issues:
                print(f"    {issue}")

    print(f"\n{'='*80}")
    print("EXPERIMENT 0.0.7 COMPLETE")
    print(f"{'='*80}")


if __name__ == "__main__":
    main()
