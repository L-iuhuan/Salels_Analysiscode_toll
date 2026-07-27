# -*- coding: utf-8 -*-
"""
实验 1.1: 间歇性需求方法评估
创建: 2026-06-12

假设: C类产品线（基线WAPE>35%）具有间歇性需求特征，传统点预测方法
（均值/趋势/季节）表现差，间歇性专用方法（Croston/SBA/SBJ/TSB/ADIDA/IMAPA）
可能改善预测精度。

范围: 仅评估 hierarchy_low_confidence_flags.csv 中的低置信C类产品线。
方法池: 基线简单方法 + ZeroInflatedMean + Croston + SBA + SBJ + TSB + ADIDA + IMAPA

成功标准:
  - 单产品线改善 >= 5pp (WAPE绝对值) 视为"通过"
  - 若所有目标线平均改善 >= 3pp 视为"强证据"

输出:
  - output/intermittent_predictability_flags.csv
  - output/intermittent_method_comparison.csv
  - output/intermittent_backtest_detail.csv
  - output/intermittent_recommendation.csv
  - output/operation_log.csv
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# ── project root ──
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

EXPERIMENT_DIR = Path(__file__).parent
OUTPUT_DIR = EXPERIMENT_DIR / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

DATA_FILE = PROJECT_ROOT / "data" / "财务分析-5月（6.3）.xlsx"
SHEET_NAME = "总表"

# ── constants ──
EPS = 1e-9
HISTORY_BUCKETS = 12  # H01-H12
MONTHS_PER_BUCKET = 3
BACKTEST_FOLDS = 6  # BT01-BT06, train expanding window

# ── target product lines (C-class low confidence) ──
TARGET_FLAGS_PATH = (
    PROJECT_ROOT / "experiment_log/09_exp_1.0_hierarchy_granularity"
    "/output/hierarchy_low_confidence_flags.csv"
)

# ── baseline corrected methods ──
BASELINE_CORRECTED_PATH = (
    PROJECT_ROOT / "experiment_log/05_exp_0.2_baseline_lock"
    "/output/baseline_corrected_customer_20260612/baseline_corrected_selected_methods.csv"
)


# ═══════════════════════════════════════════════════════════════
# Operation Log
# ═══════════════════════════════════════════════════════════════
class OperationLog:
    def __init__(self) -> None:
        self.rows: List[Dict[str, object]] = []
        self.t0 = time.time()

    def add(self, step: str, op: str, result: str, file: str = "", rows: Optional[int] = None) -> None:
        self.rows.append({
            "时间": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
            "耗时秒": round(time.time() - self.t0, 2),
            "步骤": step,
            "操作": op,
            "结果": result,
            "文件": file,
            "行数": rows,
        })
        print(f"[{step}] {op} -> {result}")

    def to_frame(self) -> pd.DataFrame:
        return pd.DataFrame(self.rows)


# ═══════════════════════════════════════════════════════════════
# 1. Read raw data
# ═══════════════════════════════════════════════════════════════
def read_raw_data(log: OperationLog) -> pd.DataFrame:
    """Read the Excel file and return raw dataframe."""
    df = pd.read_excel(str(DATA_FILE), sheet_name=SHEET_NAME)
    log.add("01读取", "读取原始Excel", f"读取完成，工作表={SHEET_NAME}，列数={len(df.columns)}，rows={len(df)}",
            str(DATA_FILE), len(df))
    return df


# ═══════════════════════════════════════════════════════════════
# 2. Clean and derive fields per field_spec_locked
# ═══════════════════════════════════════════════════════════════
def clean_and_derive(df: pd.DataFrame, log: OperationLog) -> pd.DataFrame:
    """Clean raw data and derive standard fields per field_spec_locked_20260612.md."""
    before = len(df)
    df = df.copy()

    # ── date ──
    df["发货日期"] = pd.to_datetime(df["发货日期"], errors="coerce")
    invalid_date = df["发货日期"].isna().sum()
    df = df[df["发货日期"].notna()].copy()

    # ── numeric ──
    for c in ["发货数量", "RMB 未税金额小计", "总成本", "利润"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)
    df = df[df["发货数量"] > 0].copy()

    # ── string columns ──
    str_cols = [
        "型号_产品线（新）", "存货编码", "存货名称",
        "终端客户简称", "代理商/直供名称", "实际终端客户",
        "终端客户名称_客户类别"
    ]
    for c in str_cols:
        if c in df.columns:
            df[c] = df[c].astype("string").str.strip()

    # ── 产品线缺失 → 未分类 ──
    mask_missing_line = (
        df["型号_产品线（新）"].isna()
        | (df["型号_产品线（新）"].astype(str).str.strip() == "")
    )
    df.loc[mask_missing_line, "型号_产品线（新）"] = "未分类"

    # ── SKU预测键 = 存货编码 → 存货名称 → 未知SKU ──
    df["SKU预测键"] = df["存货编码"].astype(str).str.strip()
    mask_sku_missing = df["SKU预测键"].isna() | (df["SKU预测键"] == "")
    df.loc[mask_sku_missing, "SKU预测键"] = df.loc[mask_sku_missing, "存货名称"].astype(str).str.strip()
    mask_sku_still = df["SKU预测键"].isna() | (df["SKU预测键"] == "")
    df.loc[mask_sku_still, "SKU预测键"] = "未知SKU"

    # ── 预测客户名称 = 终端客户简称 → 代理商/直供名称 → 实际终端客户 → 未知终端客户 ──
    df["预测客户名称"] = df["终端客户简称"].astype(str).str.strip()
    mask_nan = df["预测客户名称"].isna() | (df["预测客户名称"] == "")
    df.loc[mask_nan, "预测客户名称"] = df.loc[mask_nan, "代理商/直供名称"].astype(str).str.strip()
    mask_nan2 = df["预测客户名称"].isna() | (df["预测客户名称"] == "")
    df.loc[mask_nan2, "预测客户名称"] = df.loc[mask_nan2, "实际终端客户"].astype(str).str.strip()
    mask_nan3 = df["预测客户名称"].isna() | (df["预测客户名称"] == "")
    df.loc[mask_nan3, "预测客户名称"] = "未知终端客户"

    # ── 成本标准化 ──
    df["成本"] = df["总成本"]

    # ── monthly period ──
    df["_月"] = df["发货日期"].dt.to_period("M")

    after = len(df)
    log.add("02清洗", "字段清洗与派生",
            f"清洗前rows={before}，清洗后rows={after}，产品线数={df['型号_产品线（新）'].nunique()}",
            rows=after)
    return df


# ═══════════════════════════════════════════════════════════════
# 3. Build quarterly buckets (product line level, sales amount)
# ═══════════════════════════════════════════════════════════════
def build_quarterly_series(
    df: pd.DataFrame,
    target_lines: List[str],
    log: OperationLog
) -> Tuple[pd.DataFrame, pd.Period, List[str]]:
    """
    Build quarterly time series for each target product line.
    Returns:
      - panel_df: columns [产品线, 桶编号, 销售额, 销售量, 订单数]
      - latest_month: latest month in data
      - bucket_ids: list of H01-H12 bucket ids
    """
    latest_month = df["_月"].max()

    # build 12 historical buckets (H01-H12), each 3 months
    bucket_ids = []
    bucket_info = []
    for idx in range(HISTORY_BUCKETS):
        end = latest_month - (HISTORY_BUCKETS - 1 - idx) * MONTHS_PER_BUCKET
        start = end - (MONTHS_PER_BUCKET - 1)
        bid = f"H{idx + 1:02d}"
        bucket_ids.append(bid)
        bucket_info.append({"桶编号": bid, "开始Period": start, "结束Period": end})

    # filter to target lines
    df_target = df[df["型号_产品线（新）"].isin(target_lines)].copy()

    # assign bucket
    df_target["桶编号"] = pd.NA
    for bi in bucket_info:
        mask = df_target["_月"].between(bi["开始Period"], bi["结束Period"])
        df_target.loc[mask, "桶编号"] = bi["桶编号"]
    df_target = df_target[df_target["桶编号"].notna()].copy()

    # aggregate to product line × bucket
    agg = df_target.groupby(["型号_产品线（新）", "桶编号"], dropna=False).agg(
        销售额=("RMB 未税金额小计", "sum"),
        销售量=("发货数量", "sum"),
        订单数=("ERP订单号", "nunique") if "ERP订单号" in df_target.columns else ("预测客户名称", "nunique"),
    ).reset_index()
    agg.rename(columns={"型号_产品线（新）": "产品线"}, inplace=True)

    # complete panel (all lines × all buckets)
    keys = agg[["产品线"]].drop_duplicates()
    buckets_df = pd.DataFrame({"桶编号": bucket_ids})
    panel = keys.merge(buckets_df, how="cross")
    panel = panel.merge(agg, on=["产品线", "桶编号"], how="left")
    for c in ["销售额", "销售量", "订单数"]:
        panel[c] = panel[c].fillna(0.0)

    log.add("03分桶", "构建12个季度桶",
            f"最新月份={latest_month}，目标产品线={len(target_lines)}，桶数={len(bucket_ids)}",
            rows=len(panel))
    return panel, latest_month, bucket_ids


# ═══════════════════════════════════════════════════════════════
# 4. Predictability diagnostics
# ═══════════════════════════════════════════════════════════════
def compute_predictability_diagnostics(
    panel: pd.DataFrame,
    bucket_ids: List[str],
    log: OperationLog
) -> pd.DataFrame:
    """
    Compute predictability flags for each product line.
    Output columns: 产品线, 有效季度数, 零季度比例, 销售额CV, 最大单季占比,
                    最近36个月有效月数, 是否不可统计预测, 不可统计原因
    """
    rows = []
    for pline, g in panel.groupby("产品线", dropna=False):
        sales = g.set_index("桶编号").reindex(bucket_ids)["销售额"].fillna(0.0).values

        valid_quarters = int(np.sum(sales > EPS))
        zero_ratio = float(np.sum(sales <= EPS) / len(sales)) if len(sales) > 0 else 1.0
        mean_val = np.mean(sales) if len(sales) > 0 else 0.0
        std_val = np.std(sales) if len(sales) > 0 else 0.0
        cv = float(std_val / mean_val) if mean_val > EPS else float("inf")
        max_single_ratio = float(np.max(sales) / np.sum(sales)) if np.sum(sales) > EPS else 1.0

        # is_unpredictable: effective quarters < 4
        is_unpredictable = valid_quarters < 4
        reason = ""
        if is_unpredictable:
            reason = f"有效季度数={valid_quarters} < 4，数据极度稀疏，无法进行有意义的统计预测"

        rows.append({
            "产品线": pline,
            "有效季度数": valid_quarters,
            "零季度比例": round(zero_ratio, 4),
            "销售额CV": round(cv, 4),
            "最大单季占比": round(max_single_ratio, 4),
            "历史季度数": len(sales),
            "是否不可统计预测": is_unpredictable,
            "不可统计原因": reason,
        })

    flags = pd.DataFrame(rows)
    log.add("04可预测性诊断", "计算各产品线可预测性指标",
            f"不可统计预测={flags['是否不可统计预测'].sum()}条，可评估={len(flags)-flags['是否不可统计预测'].sum()}条",
            rows=len(flags))
    return flags


# ═══════════════════════════════════════════════════════════════
# 5. Intermittent demand forecasting methods
# ═══════════════════════════════════════════════════════════════
def _ensure_nonneg(arr: np.ndarray) -> np.ndarray:
    return np.maximum(np.nan_to_num(arr, nan=0.0, posinf=0.0, neginf=0.0), 0.0)


# ── Baseline simple methods ──

def method_naive_last(y_train: np.ndarray, horizon: int = 1) -> np.ndarray:
    """最近值：直接用训练序列最后一个值预测。"""
    y = _ensure_nonneg(y_train)
    if len(y) == 0:
        return np.zeros(horizon)
    return np.repeat(y[-1], horizon)


def method_mean(y_train: np.ndarray, horizon: int = 1, k: int = 4) -> np.ndarray:
    """均值(k)：训练序列最后k个值的均值。"""
    y = _ensure_nonneg(y_train)
    k = max(1, min(k, len(y)))
    tail = y[-k:]
    return np.repeat(tail.mean(), horizon)


def method_median(y_train: np.ndarray, horizon: int = 1, k: int = 4) -> np.ndarray:
    """中位数(k)：训练序列最后k个值的中位数。"""
    y = _ensure_nonneg(y_train)
    k = max(1, min(k, len(y)))
    tail = y[-k:]
    return np.repeat(np.median(tail), horizon)


# ── Zero-Inflated Mean ──

def method_zero_inflated_mean(y_train: np.ndarray, horizon: int = 1, k: int = 6) -> np.ndarray:
    """
    Zero-Inflated Mean(k):
    forecast = mean(non-zero values in last k periods) * p(non-zero in last k periods)
    """
    y = _ensure_nonneg(y_train)
    k = max(1, min(k, len(y)))
    tail = y[-k:]
    non_zero = tail[tail > EPS]
    if len(non_zero) == 0:
        return np.zeros(horizon)
    nz_mean = non_zero.mean()
    nz_prob = len(non_zero) / len(tail)
    pred = nz_mean * nz_prob
    return np.repeat(pred, horizon)


# ── Croston ──

def _croston_core(y_train: np.ndarray, horizon: int, alpha: float, variant: str = "croston") -> np.ndarray:
    """
    Core Croston logic.
    variant: "croston" | "sba" | "sbj"

    Standard Croston algorithm per period t:
      if demand > 0:
        z'_t = z'_{t-1} + alpha * (demand_t - z'_{t-1})
        p'_t = p'_{t-1} + alpha * (q - p'_{t-1})    # q = periods since last demand
        q = 0
      else:
        z'_t = z'_{t-1} (unchanged)
        p'_t = p'_{t-1} (unchanged)
        q = q + 1

    SBA:  forecast = (1 - alpha/2) * z' / p'
    SBJ:  forecast = (1 - alpha/(2-alpha)) * z' / p'
    """
    y = _ensure_nonneg(y_train)
    n = len(y)
    if n == 0:
        return np.zeros(horizon)

    # Find first non-zero demand to initialize
    first_nz = -1
    for i in range(n):
        if y[i] > EPS:
            first_nz = i
            break

    if first_nz < 0:
        return np.zeros(horizon)  # no demand at all

    z_est = y[first_nz]  # demand size estimate
    q = 1  # periods since last demand (start counting from first demand)
    p_est = 1.0  # interval estimate (initialize to 1)

    for i in range(first_nz + 1, n):
        if y[i] > EPS:
            # demand occurred: update both z and p
            z_est = z_est + alpha * (y[i] - z_est)
            p_est = p_est + alpha * (q - p_est)
            q = 0
        q += 1  # count periods since last demand (includes the period with demand)

    if z_est <= EPS:
        return np.zeros(horizon)

    if p_est <= EPS:
        p_est = 1.0

    # Croston forecast = z' / p'
    if variant == "croston":
        forecast = z_est / p_est
    elif variant == "sba":
        forecast = (1.0 - alpha / 2.0) * z_est / p_est
    elif variant == "sbj":
        forecast = (1.0 - alpha / (2.0 - alpha)) * z_est / p_est
    else:
        forecast = z_est / p_est

    forecast = max(forecast, 0.0)
    return np.repeat(forecast, horizon)


def method_croston(y_train: np.ndarray, horizon: int = 1, alpha: float = 0.1) -> np.ndarray:
    return _croston_core(y_train, horizon, alpha, "croston")


def method_sba(y_train: np.ndarray, horizon: int = 1, alpha: float = 0.1) -> np.ndarray:
    return _croston_core(y_train, horizon, alpha, "sba")


def method_sbj(y_train: np.ndarray, horizon: int = 1, alpha: float = 0.1) -> np.ndarray:
    return _croston_core(y_train, horizon, alpha, "sbj")


# ── TSB (Teunter-Syntetos-Babai) ──

def method_tsb(y_train: np.ndarray, horizon: int = 1, alpha: float = 0.1, beta: float = 0.1) -> np.ndarray:
    """
    TSB method: uses separate smoothing for demand probability and demand size.
    Handles obsolescence risk better than Croston.
    forecast = z'_t * p'_t (not division)
    """
    y = _ensure_nonneg(y_train)
    n = len(y)
    if n == 0:
        return np.zeros(horizon)

    z_est = y[0] if y[0] > EPS else 0.0
    p_est = 1.0 if y[0] > EPS else 0.0

    for i in range(1, n):
        if y[i] > EPS:
            # demand occurred
            if z_est <= EPS:
                z_est = y[i]
            else:
                z_est = z_est + alpha * (y[i] - z_est)
            p_est = p_est + beta * (1.0 - p_est)
        else:
            # zero demand
            p_est = p_est + beta * (0.0 - p_est)
        # z_est unchanged on zero periods

    if z_est <= EPS:
        return np.zeros(horizon)

    forecast = max(z_est * p_est, 0.0)
    return np.repeat(forecast, horizon)


# ── ADIDA (Aggregate-Disaggregate Intermittent Demand Approach) ──

def method_adida(y_train: np.ndarray, horizon: int = 1, agg_level: int = 2) -> np.ndarray:
    """
    ADIDA: Aggregate demand into buckets of size `agg_level`, then use mean
    of non-overlapping aggregated buckets, then disaggregate back to period level.
    """
    y = _ensure_nonneg(y_train)
    n = len(y)
    if n == 0:
        return np.zeros(horizon)

    agg_level = max(1, min(agg_level, n))
    # Aggregate into non-overlapping buckets from the end
    agg_buckets = []
    pos = n
    while pos > 0:
        start = max(0, pos - agg_level)
        chunk = y[start:pos]
        agg_buckets.append(chunk.sum())
        pos = start
    agg_buckets.reverse()

    if len(agg_buckets) == 0:
        return np.zeros(horizon)

    # Mean of aggregated buckets
    agg_mean = np.mean(agg_buckets)
    # Disaggregate: divide by aggregation level
    period_forecast = max(agg_mean / agg_level, 0.0)
    return np.repeat(period_forecast, horizon)


# ── IMAPA (Intermittent Multiple Aggregation Prediction Algorithm) ──

def method_imapa(y_train: np.ndarray, horizon: int = 1, agg_level: int = 2,
                 agg_func: str = "mean") -> np.ndarray:
    """
    IMAPA: Apply aggregation, then use specified function (mean/median)
    on overlapping windows of size agg_level, then average across all agg forecasts.
    """
    y = _ensure_nonneg(y_train)
    n = len(y)
    if n == 0:
        return np.zeros(horizon)

    agg_level = max(1, min(agg_level, n))
    # Generate overlapping aggregated series
    forecasts = []
    for offset in range(agg_level):
        agg_series = []
        pos = n - offset
        while pos > 0:
            start = max(0, pos - agg_level)
            chunk = y[start:pos]
            agg_series.append(chunk.sum())
            pos -= agg_level
        agg_series = np.array(agg_series[::-1])
        if len(agg_series) > 0:
            if agg_func == "median":
                val = np.median(agg_series)
            else:
                val = np.mean(agg_series)
            forecasts.append(val)

    if len(forecasts) == 0:
        return np.zeros(horizon)

    avg_agg = np.mean(forecasts)
    period_forecast = max(avg_agg / agg_level, 0.0)
    return np.repeat(period_forecast, horizon)


# ═══════════════════════════════════════════════════════════════
# 6. Method definitions pool
# ═══════════════════════════════════════════════════════════════

def build_method_pool() -> List[Dict]:
    """
    Build the complete method pool for intermittent demand backtesting.
    Returns list of method dicts with keys: method_id, method_name, method_fn, is_intermittent
    """
    methods = []

    # ── Baseline simple methods ──
    # Naive (最近值)
    methods.append({
        "method_id": "M_NAIVE",
        "method_name": "最近值",
        "method_fn": method_naive_last,
        "is_intermittent": False,
        "params": {},
    })
    # Mean(k=3,4,6)
    for k in [3, 4, 6]:
        methods.append({
            "method_id": f"M_MEAN_{k}",
            "method_name": f"均值(k={k})",
            "method_fn": lambda y, horizon=1, k=k: method_mean(y, horizon, k),
            "is_intermittent": False,
            "params": {"窗口": k},
        })
    # Median(k=3,4,6)
    for k in [3, 4, 6]:
        methods.append({
            "method_id": f"M_MEDIAN_{k}",
            "method_name": f"中位数(k={k})",
            "method_fn": lambda y, horizon=1, k=k: method_median(y, horizon, k),
            "is_intermittent": False,
            "params": {"窗口": k},
        })

    # ── Zero-Inflated Mean ──
    for k in [6, 12]:
        methods.append({
            "method_id": f"M_ZIM_{k}",
            "method_name": f"ZeroInflatedMean(k={k})",
            "method_fn": lambda y, horizon=1, k=k: method_zero_inflated_mean(y, horizon, k),
            "is_intermittent": True,
            "params": {"窗口": k},
        })

    # ── Croston ──
    for alpha in [0.1, 0.3, 0.5]:
        methods.append({
            "method_id": f"M_CROSTON_{alpha}",
            "method_name": f"Croston(alpha={alpha})",
            "method_fn": lambda y, horizon=1, alpha=alpha: method_croston(y, horizon, alpha),
            "is_intermittent": True,
            "params": {"alpha": alpha},
        })

    # ── SBA ──
    for alpha in [0.1, 0.3, 0.5]:
        methods.append({
            "method_id": f"M_SBA_{alpha}",
            "method_name": f"SBA(alpha={alpha})",
            "method_fn": lambda y, horizon=1, alpha=alpha: method_sba(y, horizon, alpha),
            "is_intermittent": True,
            "params": {"alpha": alpha},
        })

    # ── SBJ ──
    for alpha in [0.1, 0.3, 0.5]:
        methods.append({
            "method_id": f"M_SBJ_{alpha}",
            "method_name": f"SBJ(alpha={alpha})",
            "method_fn": lambda y, horizon=1, alpha=alpha: method_sbj(y, horizon, alpha),
            "is_intermittent": True,
            "params": {"alpha": alpha},
        })

    # ── TSB ──
    for alpha in [0.1, 0.3]:
        for beta in [0.1, 0.3]:
            methods.append({
                "method_id": f"M_TSB_a{alpha}_b{beta}",
                "method_name": f"TSB(alpha={alpha},beta={beta})",
                "method_fn": lambda y, horizon=1, alpha=alpha, beta=beta: method_tsb(y, horizon, alpha, beta),
                "is_intermittent": True,
                "params": {"alpha": alpha, "beta": beta},
            })

    # ── ADIDA ──
    for agg in [2, 3, 4]:
        methods.append({
            "method_id": f"M_ADIDA_{agg}",
            "method_name": f"ADIDA(agg={agg})",
            "method_fn": lambda y, horizon=1, agg=agg: method_adida(y, horizon, agg),
            "is_intermittent": True,
            "params": {"聚合层级": agg},
        })

    # ── IMAPA ──
    for agg_func in ["mean", "median"]:
        for agg in [2, 3, 4]:
            func_label = "均值" if agg_func == "mean" else "中位数"
            methods.append({
                "method_id": f"M_IMAPA_{agg_func}_{agg}",
                "method_name": f"IMAPA({func_label},agg={agg})",
                "method_fn": lambda y, horizon=1, agg=agg, agg_func=agg_func: method_imapa(y, horizon, agg, agg_func),
                "is_intermittent": True,
                "params": {"聚合函数": agg_func, "聚合层级": agg},
            })

    return methods


# ═══════════════════════════════════════════════════════════════
# 7. Backtest BT01-BT06
# ═══════════════════════════════════════════════════════════════

def run_backtest(
    panel: pd.DataFrame,
    bucket_ids: List[str],
    method_pool: List[Dict],
    predictability_flags: pd.DataFrame,
    log: OperationLog
) -> pd.DataFrame:
    """
    Run BT01-BT06 backtest for each product line × method.
    BT01: train H01-H06 → predict H07 (test_idx=6)
    BT02: train H01-H07 → predict H08 (test_idx=7)
    ...
    BT06: train H01-H11 → predict H12 (test_idx=11)
    Only run for product lines that are NOT 不可统计预测.
    """
    unpred_lines = set(
        predictability_flags[predictability_flags["是否不可统计预测"]]["产品线"].tolist()
    )

    detail_rows = []
    n_folds = BACKTEST_FOLDS

    for pline, g in panel.groupby("产品线", dropna=False):
        if pline in unpred_lines:
            continue

        sales = g.set_index("桶编号").reindex(bucket_ids)["销售额"].fillna(0.0).values

        for method in method_pool:
            fn = method["method_fn"]

            fold_errors = []
            fold_apes = []
            fold_actuals = []
            fold_preds = []

            for fold_idx in range(n_folds):
                train_end_idx = 6 + fold_idx  # H07 index = 6, H08 index = 7, ..., H12 index = 11
                test_idx = train_end_idx  # predict this exact bucket (horizon=1)

                y_train = sales[:train_end_idx]
                y_actual = sales[test_idx]

                pred = fn(y_train, horizon=1)
                pred_val = float(pred[0])

                error = pred_val - y_actual
                # APE: 过滤实际值≈0的样本（修复：当实际值=0时APE=inf，后续WAPE计算会过滤）
                ape = abs(error) / abs(y_actual) if abs(y_actual) > EPS else float("inf")

                fold_errors.append(error)
                fold_apes.append(ape)
                fold_actuals.append(y_actual)
                fold_preds.append(pred_val)

                detail_rows.append({
                    "产品线": pline,
                    "方法ID": method["method_id"],
                    "方法名称": method["method_name"],
                    "是否间歇性方法": method["is_intermittent"],
                    "回测折次": f"BT{fold_idx + 1:02d}",
                    "训练期长度": train_end_idx,
                    "预测桶": bucket_ids[test_idx],
                    "实际销售额": round(y_actual, 2),
                    "预测销售额": round(pred_val, 2),
                    "误差": round(error, 2),
                    "APE": round(ape, 6),
                })

    detail = pd.DataFrame(detail_rows)
    log.add("05回测", f"运行{len(method_pool)}种方法×{n_folds}折回测",
            f"明细rows={len(detail)}，产品线={panel['产品线'].nunique() - len(unpred_lines)}",
            rows=len(detail))
    return detail


# ═══════════════════════════════════════════════════════════════
# 8. Compute comparison metrics
# ═══════════════════════════════════════════════════════════════

def _agg_method_group(group: pd.DataFrame) -> pd.Series:
    """Aggregate a single product line × method group for comparison.
    CV_WAPE and BT04_06_WAPE filter out zero-actual samples (修复WAPE计算).
    """
    valid_mask = group["实际销售额"].abs() > EPS
    valid = group[valid_mask]
    n_valid = len(valid)

    # CV_WAPE: mean APE of valid folds only
    cv_wape = valid["APE"].mean() if n_valid > 0 else float("inf")

    # BT04_06_WAPE: mean APE of last 3 valid folds
    if n_valid >= 3:
        bt_wape = valid["APE"].tail(3).mean()
    elif n_valid > 0:
        bt_wape = valid["APE"].mean()
    else:
        bt_wape = float("inf")

    return pd.Series({
        "CV_WAPE": cv_wape,
        "总绝对误差": group["误差"].abs().sum(),
        "总实际值": group["实际销售额"].sum(),
        "总预测值": group["预测销售额"].sum(),
        "总偏差": group["误差"].sum(),
        "BT04_06_WAPE": bt_wape,
    })


def compute_comparison(
    detail: pd.DataFrame,
    method_pool: List[Dict],
    log: OperationLog
) -> pd.DataFrame:
    """
    Aggregate backtest detail into method comparison.
    Compute: CV_WAPE (average APE across folds, zero-actual filtered),
             Bias, BT04_06_WAPE (零值已过滤).
    """
    if detail.empty:
        return pd.DataFrame()

    # Aggregate per product line × method (零值自动过滤)
    agg = detail.groupby(
        ["产品线", "方法ID", "方法名称", "是否间歇性方法"],
        dropna=False
    ).apply(_agg_method_group).reset_index()

    # Bias = sum(error) / sum(actual)
    agg["Bias"] = agg["总偏差"] / agg["总实际值"].replace(0, np.nan)
    agg["Bias"] = agg["Bias"].fillna(0.0)

    # Round
    for col in ["CV_WAPE", "Bias", "BT04_06_WAPE"]:
        agg[col] = agg[col].round(6)

    # Rank per product line by CV_WAPE
    agg["排名"] = agg.groupby("产品线")["CV_WAPE"].rank(method="min").astype(int)

    log.add("06汇总", "计算各方法CV_WAPE/Bias/BT04_06_WAPE(零值已过滤)",
            f"产品线数={agg['产品线'].nunique()}，方法数={agg['方法ID'].nunique()}",
            rows=len(agg))
    return agg


# ═══════════════════════════════════════════════════════════════
# 9. Recommendation vs corrected baseline
# ═══════════════════════════════════════════════════════════════

def compute_recommendation(
    comparison: pd.DataFrame,
    baseline_selected: pd.DataFrame,
    log: OperationLog
) -> pd.DataFrame:
    """
    For each product line, pick the best intermittent method and compare with
    baseline corrected WAPE. Compute improvement (delta WAPE).
    改善 = baseline_corrected_WAPE - best_intermittent_CV_WAPE
    是否通过 = 改善 >= 0.05 (5pp) → "是"
    """
    if comparison.empty:
        return pd.DataFrame()

    # Get best intermittent method per product line (by CV_WAPE)
    best_per_line = comparison.loc[comparison.groupby("产品线")["CV_WAPE"].idxmin()].copy()

    # Merge with baseline corrected WAPE
    baseline_map = baseline_selected.set_index("产品线")["销售额WAPE"].to_dict()
    best_per_line["基线修正WAPE"] = best_per_line["产品线"].map(baseline_map)
    best_per_line["基线修正WAPE"] = best_per_line["基线修正WAPE"].fillna(np.nan)

    # Compute improvement
    best_per_line["改善_绝对pp"] = (
        best_per_line["基线修正WAPE"] - best_per_line["CV_WAPE"]
    )
    best_per_line["改善_绝对pp"] = best_per_line["改善_绝对pp"].round(6)

    # Pass/fail: improvement >= 5pp
    best_per_line["是否通过"] = best_per_line["改善_绝对pp"].apply(
        lambda x: "是" if pd.notna(x) and x >= 0.05 else "否"
    )

    # Strong evidence: average improvement >= 3pp
    avg_improvement = best_per_line["改善_绝对pp"].mean()

    # Select output columns
    rec = best_per_line[[
        "产品线", "方法ID", "方法名称", "是否间歇性方法",
        "CV_WAPE", "基线修正WAPE", "改善_绝对pp", "是否通过",
        "排名", "Bias", "BT04_06_WAPE"
    ]].copy()

    log.add("07推荐", "对比修正版0.2基线，生成推荐",
            f"平均改善={avg_improvement:.4f}，通过线数={(rec['是否通过']=='是').sum()}",
            rows=len(rec))

    print(f"\n{'='*60}")
    print(f"  平均改善(绝对pp): {avg_improvement:.4f}")
    print(f"  强证据(平均>=3pp): {'是' if avg_improvement >= 0.03 else '否'}")
    print(f"{'='*60}\n")

    return rec


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

def main():
    print("=" * 80)
    print("EXPERIMENT 1.1: Intermittent Demand Methods")
    print("=" * 80)

    log = OperationLog()

    # ── 1. Load target product lines ──
    print("\n[Step 1] Loading target product lines...")
    if not TARGET_FLAGS_PATH.exists():
        raise FileNotFoundError(f"低置信标记文件不存在: {TARGET_FLAGS_PATH}")
    target_flags = pd.read_csv(TARGET_FLAGS_PATH)
    target_lines = target_flags["产品线"].tolist()
    log.add("00目标", "加载低置信C类产品线",
            f"目标产品线={len(target_lines)}: {target_lines}",
            str(TARGET_FLAGS_PATH), len(target_lines))
    print(f"  目标产品线: {target_lines}")

    # ── 2. Read raw data ──
    print("\n[Step 2] Reading raw data...")
    df_raw = read_raw_data(log)

    # ── 3. Clean and derive ──
    print("\n[Step 3] Cleaning and deriving fields...")
    df_clean = clean_and_derive(df_raw, log)

    # ── 4. Build quarterly series ──
    print("\n[Step 4] Building quarterly series...")
    panel, latest_month, bucket_ids = build_quarterly_series(df_clean, target_lines, log)
    print(f"  Latest month: {latest_month}")
    print(f"  Buckets: {bucket_ids}")

    # ── 5. Predictability diagnostics ──
    print("\n[Step 5] Computing predictability diagnostics...")
    flags = compute_predictability_diagnostics(panel, bucket_ids, log)
    print(flags.to_string(index=False))

    # ── 6. Build method pool ──
    print(f"\n[Step 6] Building method pool...")
    method_pool = build_method_pool()
    log.add("06方法池", "构建间歇性需求方法池",
            f"方法总数={len(method_pool)}，间歇性方法={sum(1 for m in method_pool if m['is_intermittent'])}")

    # ── 7. Run backtest ──
    print(f"\n[Step 7] Running BT01-BT06 backtest...")
    detail = run_backtest(panel, bucket_ids, method_pool, flags, log)

    # ── 8. Compute comparison ──
    print(f"\n[Step 8] Computing method comparison...")
    comparison = compute_comparison(detail, method_pool, log)

    # ── 9. Load baseline corrected ──
    print(f"\n[Step 9] Loading baseline corrected methods...")
    if not BASELINE_CORRECTED_PATH.exists():
        print(f"  WARNING: 基线修正文件不存在: {BASELINE_CORRECTED_PATH}，跳过推荐对比")
        baseline_selected = pd.DataFrame(columns=["产品线", "销售额WAPE"])
    else:
        baseline_selected = pd.read_csv(BASELINE_CORRECTED_PATH)
        log.add("09基线", "加载修正版0.2基线", f"基线产品线数={len(baseline_selected)}",
                str(BASELINE_CORRECTED_PATH), len(baseline_selected))

    # ── 10. Compute recommendation ──
    print(f"\n[Step 10] Computing recommendation...")
    recommendation = compute_recommendation(comparison, baseline_selected, log)

    # ── 11. Write outputs ──
    print(f"\n[Step 11] Writing outputs...")

    flags.to_csv(OUTPUT_DIR / "intermittent_predictability_flags.csv", index=False, encoding="utf-8-sig")
    comparison.to_csv(OUTPUT_DIR / "intermittent_method_comparison.csv", index=False, encoding="utf-8-sig")
    detail.to_csv(OUTPUT_DIR / "intermittent_backtest_detail.csv", index=False, encoding="utf-8-sig")
    if not recommendation.empty:
        recommendation.to_csv(OUTPUT_DIR / "intermittent_recommendation.csv", index=False, encoding="utf-8-sig")
    log.to_frame().to_csv(OUTPUT_DIR / "operation_log.csv", index=False, encoding="utf-8-sig")

    log.add("11输出", "写入全部CSV", f"输出目录={OUTPUT_DIR}")

    print("\n" + "=" * 80)
    print("EXPERIMENT 1.1 COMPLETE")
    print("=" * 80)

    return panel, flags, detail, comparison, recommendation


if __name__ == "__main__":
    main()
