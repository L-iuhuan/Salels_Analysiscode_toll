# -*- coding: utf-8 -*-
"""
实验 1.0: 预测层级与时间粒度对比（严格版，v1.4测试方案对齐）

假设：不同产品线适合不同预测层级和时间粒度；不能一刀切使用"产品线×3个月期"。

对比方案（严格按测试方案）：
  a. 产品线×季度 —— 当前基线/季度序列
  b. 产品线×月度→季度汇总 —— 先预测月度总量，再汇总为经营期
  c. 产品品类×月度→产品线汇总 —— 中层结构预测（品类键=型号_产品品类，缺失归未知品类）
  d. SKU×月度→产品线汇总 —— SKU级bottom-up（SKU键=SKU预测键/存货编码fallback存货名称）

算法池说明：
  - 使用与基线同源的 forecast_values 简单算法池（最近值/均值/中位数/线性加权/
    指数加权/线性趋势/对数趋势/漂移/同比季节/衰减趋势/保守增长/保守衰减）。
  - 若需要完整方法池（含销量×ASP等），成本过高，本实验仅对比层级效应。

产出（在 output/ 下）：
  - hierarchy_granularity_comparison.csv
  - hierarchy_granularity_holdout.csv
  - hierarchy_low_confidence_flags.csv
  - hierarchy_granularity_summary.csv
  - hierarchy_granularity_recommendation.csv
  - operation_log.csv
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from quarterly_forecast_package.run_quarterly_forecast import (
    read_raw_data,
    clean_and_map,
    build_buckets,
    add_bucket_id,
    forecast_values,
    OperationLog,
    weighted_mode,
    safe_div,
    EPS,
    MethodSpec,
    aggregate_layers,
    complete_panel,
)

# ---- 实验配置 ----
EXPERIMENT_NAME = "exp_1.0_hierarchy_granularity"
EXPERIMENT_DIR = Path(__file__).parent
OUTPUT_DIR = EXPERIMENT_DIR / "output"

HIERARCHY_ELIGIBILITY_PATH = (
    PROJECT_ROOT / "experiment_log/08_exp_0.0.6_hierarchy_eligibility/output/"
    "hierarchy_eligibility_by_pline.csv"
)

# 产品线分层标签 (A/B/C)
PLINE_CLASS = {
    "通用电源管理": "A",
    "POE电源管理": "A",
    "充电与控制电源管理": "A",
    "有刷直流电机驱动": "A",
    "步进电机驱动": "A",
    "硬件锂电保护": "A",
    "磁传感": "A",
    "车规电机驱动": "B",
    "车规电源管理": "B",
    "dTOF模组": "B",
    "电脑&计算电源管理": "B",
    "音频功放": "B",
    "新显示MLED驱动": "C",
    "无刷直流电机驱动": "C",
    "未分类": "C",
    "电源模组": "C",
    "电机驱动": "C",
    "PMIC": "C",
}

# 对比方案定义
SCHEMES = {
    "产品线×季度": {
        "id": "pline_quarterly",
        "type": "quarterly",
        "group_cols": ["型号_产品线（新）"],
        "description": "当前基线：产品线级别直接3个月期预测",
    },
    "产品线×月度→季度汇总": {
        "id": "pline_monthly",
        "type": "monthly_to_quarterly",
        "group_cols": ["型号_产品线（新）"],
        "description": "产品线级别月度预测，汇总为季度",
        "eligibility_col": "product_line_monthly_eligible",
    },
    "产品品类×月度→产品线汇总": {
        "id": "category_monthly",
        "type": "monthly_to_quarterly",
        "group_cols": ["型号_产品线（新）", "品类键"],
        "description": "品类级别月度预测，按产品线汇总",
        "eligibility_col": "category_monthly_eligible",
    },
    "SKU×月度→产品线汇总": {
        "id": "sku_monthly",
        "type": "monthly_to_quarterly",
        "group_cols": ["型号_产品线（新）", "SKU预测键"],
        "description": "SKU级别月度预测，按产品线汇总",
        "eligibility_col": "sku_monthly_eligible",
    },
}

# 算法池（与基线 forecast_values 同源）
ALGORITHM_POOL = [
    {"基础算法": "最近值", "参数": {"窗口": 1}},
    {"基础算法": "均值", "参数": {"窗口": 4}},
    {"基础算法": "均值", "参数": {"窗口": 6}},
    {"基础算法": "均值", "参数": {"窗口": 8}},
    {"基础算法": "均值", "参数": {"窗口": 12}},
    {"基础算法": "中位数", "参数": {"窗口": 4}},
    {"基础算法": "中位数", "参数": {"窗口": 6}},
    {"基础算法": "中位数", "参数": {"窗口": 8}},
    {"基础算法": "线性加权均值", "参数": {"窗口": 4}},
    {"基础算法": "线性加权均值", "参数": {"窗口": 6}},
    {"基础算法": "线性加权均值", "参数": {"窗口": 8}},
    {"基础算法": "指数加权均值", "参数": {"窗口": 4, "alpha": 0.5}},
    {"基础算法": "指数加权均值", "参数": {"窗口": 6, "alpha": 0.5}},
    {"基础算法": "指数加权均值", "参数": {"窗口": 8, "alpha": 0.5}},
    {"基础算法": "线性趋势", "参数": {"窗口": 6}},
    {"基础算法": "线性趋势", "参数": {"窗口": 8}},
    {"基础算法": "漂移", "参数": {"窗口": 4}},
    {"基础算法": "漂移", "参数": {"窗口": 6}},
    {"基础算法": "同比季节", "参数": {"窗口": 12, "季节滞后": 4, "增长窗口": 4}},
    {"基础算法": "衰减趋势", "参数": {"窗口": 6, "衰减": 0.7}},
    {"基础算法": "保守增长", "参数": {"窗口": 4, "增长率": 0.05}},
    {"基础算法": "保守衰减", "参数": {"窗口": 4, "衰减率": 0.05}},
]


def load_eligibility(path: Path) -> pd.DataFrame:
    """加载层级准入表。"""
    if not path.exists():
        print(f"⚠ 层级准入表不存在: {path}，将允许所有层级。")
        return pd.DataFrame()
    return pd.read_csv(path)


def check_eligible(eligibility: pd.DataFrame, pline: str, scheme_key: str) -> bool:
    """检查产品线是否允许使用指定方案。"""
    if eligibility.empty:
        return True
    row = eligibility[eligibility["产品线"] == pline]
    if row.empty:
        return scheme_key == "pline_quarterly"  # 未知产品线只允许基线
    col = SCHEMES[scheme_key].get("eligibility_col")
    if col is None:
        return True  # 基线总是允许
    val = row.iloc[0].get(col, False)
    if isinstance(val, str):
        return val.strip().lower() == "true"
    return bool(val)


def aggregate_monthly_series(df: pd.DataFrame, group_cols: List[str]) -> pd.DataFrame:
    """按指定列和月度聚合销量/销售额序列。"""
    base = df.groupby(group_cols + ["_月"], dropna=False).agg(
        销售量=("发货数量", "sum"),
        销售额=("RMB 未税金额小计", "sum"),
    ).reset_index()
    base["_月"] = base["_月"].astype(str)
    return base


def build_monthly_panel(monthly_df: pd.DataFrame, group_cols: List[str]) -> pd.DataFrame:
    """将月度聚合数据展开为完整面板（所有组合 × 所有月份）。"""
    months = sorted(monthly_df["_月"].unique())
    keys = monthly_df[group_cols].drop_duplicates()
    panel = keys.merge(pd.DataFrame({"_月": months}), how="cross")
    panel = panel.merge(monthly_df, on=group_cols + ["_月"], how="left")
    panel["销售量"] = panel["销售量"].fillna(0.0)
    panel["销售额"] = panel["销售额"].fillna(0.0)
    return panel


def monthly_to_quarterly_series(monthly_values: np.ndarray, months: int = 36) -> np.ndarray:
    """将月度序列转换为季度序列（每3个月求和）。返回12个季度值。"""
    quarterly = []
    for i in range(12):
        start = months - 36 + i * 3
        end = start + 3
        chunk = monthly_values[max(0, start):min(len(monthly_values), end)]
        quarterly.append(chunk.sum() if len(chunk) > 0 else 0.0)
    return np.array(quarterly)


def backtest_scheme_quarterly(
    line_panel: pd.DataFrame,
    pline: str,
    bucket_ids: List[str],
    log: OperationLog,
) -> List[Dict]:
    """
    方案a：产品线×季度回测。
    使用12个季度桶，6折滚动回测（折H07-H12），预测 horizon=1。
    """
    line_data = line_panel[line_panel["型号_产品线（新）"] == pline].set_index("桶编号").reindex(bucket_ids).fillna(0)
    actual_amounts = line_data["销售额"].to_numpy(float)
    actual_qtys = line_data["销售量"].to_numpy(float)

    rows = []
    for test_idx in range(6, 12):
        train = actual_amounts[:test_idx]
        actual = actual_amounts[test_idx]
        for alg_spec in ALGORITHM_POOL:
            pred = forecast_values(train, 1, alg_spec["基础算法"], alg_spec["参数"])
            pa = float(pred[0])
            err = pa - actual
            ape = abs(err) / max(abs(actual), EPS)
            rows.append({
                "产品线": pline,
                "方案": "产品线×季度",
                "方案ID": "pline_quarterly",
                "回测折次": f"BT{test_idx-5:02d}",
                "算法": alg_spec["基础算法"],
                "参数": str(alg_spec["参数"]),
                "实际销售额": actual,
                "预测销售额": pa,
                "销售额误差": err,
                "销售额绝对误差": abs(err),
                "销售额APE": ape,
            })
    return rows


def backtest_scheme_monthly_to_quarterly(
    monthly_panel: pd.DataFrame,
    pline: str,
    scheme_name: str,
    scheme_id: str,
    group_cols: List[str],
    log: OperationLog,
) -> List[Dict]:
    """
    方案b/c/d：月度→季度汇总回测。
    在月度面板上做6折滚动回测，预测 horizon=3，汇总为季度后计算WAPE。
    """
    # 该产品线的月度面板
    sub = monthly_panel[monthly_panel["型号_产品线（新）"] == pline].copy()
    months = sorted(sub["_月"].unique())
    if len(months) < 12:
        return []  # 数据不足

    # 获取组键（不含产品线）
    inner_cols = [c for c in group_cols if c != "型号_产品线（新）"]

    # 构建产品线级月度销售额实际值（用于计算季度WAPE）
    pline_monthly = sub.groupby("_月").agg(
        销售量=("销售量", "sum"),
        销售额=("销售额", "sum"),
    ).reindex(months).fillna(0)
    pline_monthly_amounts = pline_monthly["销售额"].to_numpy(float)

    # 6折：每月度用前N个月训练，预测后3个月
    # 折1: train=月1..18, predict=月19..21 → 对应Q7
    # 折2: train=月1..21, predict=月22..24 → 对应Q8
    # ...
    # 折6: train=月1..33, predict=月34..36 → 对应Q12
    fold_start_months = [18, 21, 24, 27, 30, 33]

    rows = []
    for fold_i, train_end in enumerate(fold_start_months):
        if train_end > len(months):
            continue
        test_idx = fold_i + 6  # Q7-Q12

        # 对每个组键分别预测
        pred_monthly_total = np.zeros(3)

        if inner_cols:
            keys = sub[inner_cols].drop_duplicates()
            for _, key_row in keys.iterrows():
                key_mask = np.ones(len(sub), dtype=bool)
                for col in inner_cols:
                    key_mask &= (sub[col] == key_row[col])
                g = sub[key_mask].set_index("_月").reindex(months).fillna(0)
                g_amounts = g["销售额"].to_numpy(float)[:train_end]

                if g_amounts.sum() <= 0:
                    continue

                best_pred = None
                best_wape = float("inf")
                for alg_spec in ALGORITHM_POOL:
                    pred3 = forecast_values(g_amounts, 3, alg_spec["基础算法"], alg_spec["参数"])
                    # 用训练期最后几个月的WAPE选择最优方法（简化为最近3月的拟合）
                    if len(g_amounts) >= 6:
                        fit_pred = forecast_values(g_amounts[:-3], 3, alg_spec["基础算法"], alg_spec["参数"])
                        fit_actual = g_amounts[-3:]
                        fit_wape = np.sum(np.abs(fit_pred - fit_actual)) / max(np.sum(np.abs(fit_actual)), EPS)
                        if fit_wape < best_wape:
                            best_wape = fit_wape
                            best_pred = pred3
                    else:
                        if best_pred is None:
                            best_pred = pred3

                if best_pred is None:
                    best_pred = forecast_values(g_amounts, 3, "均值", {"窗口": 4})
                pred_monthly_total += np.nan_to_num(best_pred, nan=0.0)
        else:
            # 产品线级月度直接预测
            train_amounts = pline_monthly_amounts[:train_end]
            best_pred = None
            best_wape = float("inf")
            for alg_spec in ALGORITHM_POOL:
                pred3 = forecast_values(train_amounts, 3, alg_spec["基础算法"], alg_spec["参数"])
                if len(train_amounts) >= 6:
                    fit_pred = forecast_values(train_amounts[:-3], 3, alg_spec["基础算法"], alg_spec["参数"])
                    fit_actual = train_amounts[-3:]
                    fit_wape = np.sum(np.abs(fit_pred - fit_actual)) / max(np.sum(np.abs(fit_actual)), EPS)
                    if fit_wape < best_wape:
                        best_wape = fit_wape
                        best_pred = pred3
                else:
                    if best_pred is None:
                        best_pred = pred3
            if best_pred is None:
                best_pred = forecast_values(train_amounts, 3, "均值", {"窗口": 4})
            pred_monthly_total = np.nan_to_num(best_pred, nan=0.0)

        # 季度汇总：预测的3个月之和
        pred_quarterly = pred_monthly_total.sum()
        actual_quarterly = pline_monthly_amounts[train_end:train_end + 3].sum()

        err = pred_quarterly - actual_quarterly
        ape = abs(err) / max(abs(actual_quarterly), EPS)

        rows.append({
            "产品线": pline,
            "方案": scheme_name,
            "方案ID": scheme_id,
            "回测折次": f"BT{test_idx:02d}",
            "算法": "最优_拟合选择",
            "参数": "月度→季度汇总",
            "实际销售额": actual_quarterly,
            "预测销售额": pred_quarterly,
            "销售额误差": err,
            "销售额绝对误差": abs(err),
            "销售额APE": ape,
        })

    return rows


def compute_scheme_metrics(detail_rows: pd.DataFrame, scheme_id: str, pline: str) -> Dict:
    """计算某产品线×某方案的指标。"""
    part = detail_rows[
        (detail_rows["产品线"] == pline) & (detail_rows["方案ID"] == scheme_id)
    ]
    if part.empty:
        return {
            "产品线": pline,
            "方案ID": scheme_id,
            "回测次数": 0,
            "CV_WAPE": np.nan,
            "CV_Bias": np.nan,
            "BT04_06_WAPE": np.nan,
        }

    actual_sum = part["实际销售额"].abs().sum()
    error_sum = part["销售额绝对误差"].sum()
    wape = error_sum / max(actual_sum, EPS)
    bias = part["销售额误差"].sum() / max(part["实际销售额"].sum(), EPS)

    # BT04-BT06 近似 holdout
    holdout = part[part["回测折次"].isin(["BT04", "BT05", "BT06"])]
    if not holdout.empty:
        h_actual = holdout["实际销售额"].abs().sum()
        h_error = holdout["销售额绝对误差"].sum()
        h_wape = h_error / max(h_actual, EPS)
    else:
        h_wape = np.nan

    return {
        "产品线": pline,
        "方案ID": scheme_id,
        "回测次数": len(part),
        "CV_WAPE": wape,
        "CV_Bias": bias,
        "BT04_06_WAPE": h_wape,
    }


def run_experiment(
    data_path: Path,
    output_dir: Path,
    sheet_name="总表",
    field_map: Optional[Dict[str, str]] = None,
) -> Dict[str, pd.DataFrame]:
    """运行实验1.0：层级与时间粒度对比。"""
    log = OperationLog()
    output_dir.mkdir(parents=True, exist_ok=True)

    # ---- 默认字段映射 ----
    if field_map is None:
        field_map = {
            "发货日期": "发货日期",
            "型号_产品线（新）": "型号_产品线（新）",
            "存货名称": "存货名称",
            "发货数量": "发货数量",
            "RMB 未税金额小计": "RMB 未税金额小计",
            "成本": "总成本",
            "利润": "利润",
            "未税单价": "未税单价",
            "单位成本": "单位成本",
            "终端客户简称": "终端客户简称",
            "代理商/直供名称": "代理商/直供名称",
            "实际终端客户": "实际终端客户",
            "终端客户名称_客户类别": "终端客户名称_客户类别",
            "ERP订单号": "ERP订单号",
            "产品线": "产品线",
            "产品系列": "产品系列",
            "型号": "型号",
            "存货编码": "存货编码",
            "型号_产品品类": "型号_产品品类",
            "终端名称": "终端名称",
        }

    # ---- 步骤1: 读取和清洗 ----
    log.add("01准备", "读取原始数据", f"数据路径={data_path}")
    df_raw = read_raw_data(data_path, log, sheet_name=sheet_name, field_map=field_map)
    df, diagnostics, mapping_diag = clean_and_map(df_raw, log)

    # ---- 步骤2: 品类键处理 ----
    if "型号_产品品类" in df.columns:
        df["品类键"] = df["型号_产品品类"].astype(str).str.strip()
        df.loc[df["品类键"].isna() | (df["品类键"] == ""), "品类键"] = "未知品类"
    else:
        df["品类键"] = "未知品类"
        log.add("02品类", "型号_产品品类列缺失", "全部归为'未知品类'")

    # ---- 步骤3: 构建基础时间桶 ----
    buckets, latest_month, history_ends, bucket_rows = build_buckets(df, log)
    hist_start = bucket_rows[0]["开始Period"]
    hist_end = bucket_rows[11]["结束Period"]
    df_hist = df[df["_月"].between(hist_start, hist_end)].copy()
    bucket_ids = [f"H{i:02d}" for i in range(1, 13)]

    # ---- 步骤4: 季度基线面板 ----
    line_bucket, product_bucket, pc_bucket, dfb = aggregate_layers(df_hist, bucket_rows, log)
    value_cols = ["销售量", "销售额", "成本额", "毛利额", "产品数", "客户数", "订单数", "明细行数", "毛利率", "加权销售单价", "加权成本单价"]
    line_panel = complete_panel(line_bucket, ["型号_产品线（新）"], bucket_ids, value_cols)

    lines = sorted(line_panel["型号_产品线（新）"].dropna().unique())
    log.add("03基线", f"季度基线面板就绪", f"产品线数={len(lines)}")

    # ---- 步骤5: 月度面板构建 ----
    # 构建月度序列（最近36个月）
    months_all = sorted(df_hist["_月"].astype(str).unique())

    # 产品线×月度面板
    pline_monthly = aggregate_monthly_series(df_hist, ["型号_产品线（新）"])
    pline_monthly_panel = build_monthly_panel(pline_monthly, ["型号_产品线（新）"])

    # 品类×月度面板
    cat_monthly = aggregate_monthly_series(df_hist, ["型号_产品线（新）", "品类键"])
    cat_monthly_panel = build_monthly_panel(cat_monthly, ["型号_产品线（新）", "品类键"])

    # SKU×月度面板
    sku_monthly = aggregate_monthly_series(df_hist, ["型号_产品线（新）", "SKU预测键"])
    sku_monthly_panel = build_monthly_panel(sku_monthly, ["型号_产品线（新）", "SKU预测键"])

    log.add("04月度", "月度面板就绪",
            f"月数={len(months_all)}，产品线月={len(pline_monthly_panel)}，品类月={len(cat_monthly_panel)}，SKU月={len(sku_monthly_panel)}")

    # ---- 步骤6: 加载层级准入 ----
    eligibility = load_eligibility(HIERARCHY_ELIGIBILITY_PATH)
    log.add("05准入", "加载层级准入表", f"准入表行数={len(eligibility)}")

    # ---- 步骤7: 全量回测 ----
    all_detail_rows: List[Dict] = []

    for pline in lines:
        pline_class = PLINE_CLASS.get(pline, "C")
        log.add("06回测", f"处理产品线: {pline} (分层={pline_class})", "")

        # 方案a: 产品线×季度 (基线)
        rows_a = backtest_scheme_quarterly(line_panel, pline, bucket_ids, log)
        all_detail_rows.extend(rows_a)

        # 方案b: 产品线×月度→季度汇总
        if check_eligible(eligibility, pline, "产品线×月度→季度汇总"):
            rows_b = backtest_scheme_monthly_to_quarterly(
                pline_monthly_panel, pline,
                "产品线×月度→季度汇总", "pline_monthly",
                ["型号_产品线（新）"], log,
            )
            all_detail_rows.extend(rows_b)
        else:
            log.add("06回测", f"  {pline}: 产品线×月度 不满足准入条件，跳过", "")

        # 方案c: 产品品类×月度→产品线汇总
        if check_eligible(eligibility, pline, "产品品类×月度→产品线汇总"):
            rows_c = backtest_scheme_monthly_to_quarterly(
                cat_monthly_panel, pline,
                "产品品类×月度→产品线汇总", "category_monthly",
                ["型号_产品线（新）", "品类键"], log,
            )
            all_detail_rows.extend(rows_c)
        else:
            log.add("06回测", f"  {pline}: 品类×月度 不满足准入条件，跳过", "")

        # 方案d: SKU×月度→产品线汇总
        if check_eligible(eligibility, pline, "SKU×月度→产品线汇总"):
            rows_d = backtest_scheme_monthly_to_quarterly(
                sku_monthly_panel, pline,
                "SKU×月度→产品线汇总", "sku_monthly",
                ["型号_产品线（新）", "SKU预测键"], log,
            )
            all_detail_rows.extend(rows_d)
        else:
            log.add("06回测", f"  {pline}: SKU×月度 不满足准入条件，跳过", "")

    detail = pd.DataFrame(all_detail_rows)
    log.add("07回测完成", f"回测完成", f"总明细行数={len(detail)}")

    # ---- 步骤8: 计算各方案指标 ----
    scheme_ids = ["pline_quarterly", "pline_monthly", "category_monthly", "sku_monthly"]
    scheme_names = {
        "pline_quarterly": "产品线×季度",
        "pline_monthly": "产品线×月度→季度汇总",
        "category_monthly": "产品品类×月度→产品线汇总",
        "sku_monthly": "SKU×月度→产品线汇总",
    }

    comparison_rows = []
    holdout_rows = []
    flag_rows = []

    for pline in lines:
        pline_class = PLINE_CLASS.get(pline, "C")
        baseline_metrics = None

        for sid in scheme_ids:
            metrics = compute_scheme_metrics(detail, sid, pline)
            if metrics["回测次数"] == 0:
                continue
            if sid == "pline_quarterly":
                baseline_metrics = metrics

            comparison_rows.append({
                "产品线": pline,
                "产品线分层": pline_class,
                "方案": scheme_names[sid],
                "方案ID": sid,
                "回测次数": metrics["回测次数"],
                "CV_WAPE": metrics["CV_WAPE"],
                "CV_Bias": metrics["CV_Bias"],
                "BT04_06_WAPE": metrics["BT04_06_WAPE"],
            })

            holdout_rows.append({
                "产品线": pline,
                "产品线分层": pline_class,
                "方案": scheme_names[sid],
                "方案ID": sid,
                "CV_WAPE": metrics["CV_WAPE"],
                "BT04_06_WAPE": metrics["BT04_06_WAPE"],
                "WAPE差异": (metrics["BT04_06_WAPE"] - metrics["CV_WAPE"])
                if not (np.isnan(metrics["BT04_06_WAPE"]) or np.isnan(metrics["CV_WAPE"]))
                else np.nan,
            })

        # 低置信度标记
        if pline_class == "C" and baseline_metrics is not None:
            wape = baseline_metrics["CV_WAPE"]
            if not np.isnan(wape) and wape > 0.35:
                flag_rows.append({
                    "产品线": pline,
                    "产品线分层": pline_class,
                    "标记类型": "低置信度",
                    "标记原因": f"C类产品线基线WAPE={wape:.1%} > 35%",
                    "建议": "标记低置信度，不承诺精确点预测",
                })

    comparison_df = pd.DataFrame(comparison_rows)
    holdout_df = pd.DataFrame(holdout_rows)
    flag_df = pd.DataFrame(flag_rows)

    # ---- 步骤9: 汇总统计 ----
    summary_rows = []
    for sid in scheme_ids:
        sub = comparison_df[comparison_df["方案ID"] == sid]
        if sub.empty:
            continue
        summary_rows.append({
            "方案": scheme_names[sid],
            "方案ID": sid,
            "产品线数": len(sub),
            "CV_WAPE_均值": sub["CV_WAPE"].mean(),
            "CV_WAPE_中位数": sub["CV_WAPE"].median(),
            "BT04_06_WAPE_均值": sub["BT04_06_WAPE"].mean(),
            "A类_CV_WAPE": sub[sub["产品线分层"] == "A"]["CV_WAPE"].mean(),
            "B类_CV_WAPE": sub[sub["产品线分层"] == "B"]["CV_WAPE"].mean(),
            "C类_CV_WAPE": sub[sub["产品线分层"] == "C"]["CV_WAPE"].mean(),
        })
    summary_df = pd.DataFrame(summary_rows)

    # ---- 步骤10: 推荐最优方案 ----
    recommendation_rows = []
    for pline in lines:
        pline_data = comparison_df[comparison_df["产品线"] == pline].copy()
        if pline_data.empty:
            continue

        pline_data = pline_data.sort_values("CV_WAPE")
        best = pline_data.iloc[0]
        baseline = pline_data[pline_data["方案ID"] == "pline_quarterly"]
        baseline_row = baseline.iloc[0] if not baseline.empty else None

        rec = {
            "产品线": pline,
            "产品线分层": PLINE_CLASS.get(pline, "C"),
            "推荐方案": best["方案"],
            "推荐CV_WAPE": best["CV_WAPE"],
            "基线CV_WAPE": baseline_row["CV_WAPE"] if baseline_row is not None else np.nan,
            "WAPE改善": (baseline_row["CV_WAPE"] - best["CV_WAPE"])
            if baseline_row is not None and not pd.isna(baseline_row["CV_WAPE"])
            else np.nan,
            "CV_Bias": best["CV_Bias"],
            "BT04_06_WAPE": best["BT04_06_WAPE"],
        }

        # 判断是否推荐非基线方案
        if baseline_row is not None and best["方案ID"] != "pline_quarterly":
            wape_imp = baseline_row["CV_WAPE"] - best["CV_WAPE"]
            bias_ok = abs(best["CV_Bias"]) <= abs(baseline_row["CV_Bias"]) + 0.05 if not pd.isna(best["CV_Bias"]) else True
            holdout_ok = (
                pd.isna(best["BT04_06_WAPE"]) or pd.isna(baseline_row["BT04_06_WAPE"]) or
                best["BT04_06_WAPE"] - baseline_row["BT04_06_WAPE"] <= 0.02
            )
            if wape_imp >= 0.01 and bias_ok and holdout_ok:
                rec["推荐理由"] = f"WAPE改善{wape_imp:.1%}，Bias受控，holdout未恶化"
                rec["是否推荐"] = "是"
            else:
                rec["推荐理由"] = "基准方案更优或改善不足"
                rec["是否推荐"] = "否"
                rec["推荐方案"] = "产品线×季度"
        else:
            rec["推荐理由"] = "基准方案最优"
            rec["是否推荐"] = "是" if best["方案ID"] == "pline_quarterly" else "否"

        recommendation_rows.append(rec)

    recommendation_df = pd.DataFrame(recommendation_rows)

    # ---- 步骤11: 导出 ----
    comparison_df.to_csv(output_dir / "hierarchy_granularity_comparison.csv", index=False, encoding="utf-8-sig")
    holdout_df.to_csv(output_dir / "hierarchy_granularity_holdout.csv", index=False, encoding="utf-8-sig")
    flag_df.to_csv(output_dir / "hierarchy_low_confidence_flags.csv", index=False, encoding="utf-8-sig")
    summary_df.to_csv(output_dir / "hierarchy_granularity_summary.csv", index=False, encoding="utf-8-sig")
    recommendation_df.to_csv(output_dir / "hierarchy_granularity_recommendation.csv", index=False, encoding="utf-8-sig")
    log.to_frame().to_csv(output_dir / "operation_log.csv", index=False, encoding="utf-8-sig")

    log.add("08导出", "导出实验结果", f"输出目录={output_dir}")

    return {
        "comparison": comparison_df,
        "holdout": holdout_df,
        "flags": flag_df,
        "summary": summary_df,
        "recommendation": recommendation_df,
        "detail": detail,
        "log": log.to_frame(),
    }


def main():
    """主函数。"""
    import argparse

    parser = argparse.ArgumentParser(description="实验1.0: 层级与时间粒度对比（严格版）")
    parser.add_argument("--data", default=str(PROJECT_ROOT / "data" / "财务分析-5月（6.3）.xlsx"), help="原始数据路径")
    parser.add_argument("--output", default=str(OUTPUT_DIR), help="输出目录")
    parser.add_argument("--sheet", default="总表", help="工作表名或序号")
    args = parser.parse_args()

    data_path = Path(args.data)
    output_dir = Path(args.output)
    sheet_name = args.sheet

    print(f"实验 1.0: 预测层级与时间粒度对比（严格版 v1.4对齐）")
    print(f"数据路径: {data_path}")
    print(f"输出目录: {output_dir}")
    print(f"工作表: {sheet_name}")
    print()

    start_time = time.time()
    results = run_experiment(data_path, output_dir, sheet_name=sheet_name)
    elapsed = time.time() - start_time

    print(f"\n实验完成！耗时: {elapsed:.1f}秒")
    print(f"\n输出文件:")
    for name in ["comparison", "holdout", "flags", "summary", "recommendation"]:
        f = output_dir / f"hierarchy_granularity_{name}.csv"
        print(f"  {name}: {f}")


if __name__ == "__main__":
    main()
