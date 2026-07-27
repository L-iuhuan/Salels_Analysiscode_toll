# -*- coding: utf-8 -*-
"""
实验 1.2: 区间预测（Quantile Forecasting）
创建: 2026-06-12

假设: 点预测无法充分表达低置信度预测的不确定性。通过提供预测区间（50%/80%分位数），可以：
  1. 量化预测不确定性，为决策提供风险评估
  2. 区间覆盖率可以验证预测质量，比单一WAPE更全面
  3. 对低置信度产品线，区间预测比强行点预测更有业务价值

范围: 全部17条产品线（包括低置信C类线）
方法池: ExpSmooth / LinearTrend / HistoricAverage / SeasonalNaive（均通过Bootstrap残差重采样生成分位数）
分位数: 10% / 25% / 75% / 90%（对应80%/50%置信区间）
回测: BT01-BT06 扩展窗口，horizon=1季度

成功标准:
  - 覆盖率偏差 < 5%（80%置信区间实际覆盖率在75%-85%之间）
  - 区间宽度合理（平均宽度 < 实际值标准差的2倍）
  - 低置信C类线区间预测质量优于盲目点预测

输出:
  - output/quantile_backtest_detail.csv
  - output/quantile_coverage_metrics.csv
  - output/quantile_recommendation.csv
  - output/operation_log.csv
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats

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
BACKTEST_FOLDS = 6  # BT01-BT06
N_BOOTSTRAP = 500  # bootstrap resamples for quantile estimation

# ── target quantiles ──
QUANTILES = [0.10, 0.25, 0.75, 0.90]  # 80% and 50% confidence intervals

# ── low-confidence C-class product lines ──
LOW_CONFIDENCE_LINES = [
    "新显示MLED驱动",
    "无刷直流电机驱动",
    "未分类",
    "电源模组",
]

# ── baseline corrected methods ──
BASELINE_PATH = (
    PROJECT_ROOT / "experiment_log/05_exp_0.2_baseline_lock"
    "/output/baseline_corrected_customer_20260612/baseline_corrected_selected_methods.csv"
)

# ── field spec ──
FIELD_SPEC_PATH = PROJECT_ROOT / "experiment_log/00_master/field_spec_locked_20260612.md"


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
    log.add("01读取", "读取原始Excel",
            f"读取完成，工作表={SHEET_NAME}，列数={len(df.columns)}，rows={len(df)}",
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
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
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

    # ── 产品线缺失归未分类 ──
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
    df["成本"] = df["总成本"] if "总成本" in df.columns else 0.0

    # ── monthly period ──
    df["_月"] = df["发货日期"].dt.to_period("M")

    after = len(df)
    log.add("02清洗", "字段清洗与派生",
            f"清洗前rows={before}，清洗后rows={after}，无效日期={invalid_date}，产品线数={df['型号_产品线（新）'].nunique()}",
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
      - panel_df: columns [产品线, 桶编号, 销售额, 销售量]
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
    ).reset_index()
    agg.rename(columns={"型号_产品线（新）": "产品线"}, inplace=True)

    # complete panel (all lines × all buckets)
    keys = agg[["产品线"]].drop_duplicates()
    buckets_df = pd.DataFrame({"桶编号": bucket_ids})
    panel = keys.merge(buckets_df, how="cross")
    panel = panel.merge(agg, on=["产品线", "桶编号"], how="left")
    for c in ["销售额", "销售量"]:
        panel[c] = panel[c].fillna(0.0)

    log.add("03分桶", "构建12个季度桶",
            f"最新月份={latest_month}，目标产品线={len(target_lines)}，桶数={len(bucket_ids)}",
            rows=len(panel))
    return panel, latest_month, bucket_ids


# ═══════════════════════════════════════════════════════════════
# 4. Helper: ensure non-negative array
# ═══════════════════════════════════════════════════════════════
def _ensure_nonneg(arr: np.ndarray) -> np.ndarray:
    return np.maximum(np.nan_to_num(arr, nan=0.0, posinf=0.0, neginf=0.0), 0.0)


# ═══════════════════════════════════════════════════════════════
# 5. Bootstrap residual quantile helper
# ═══════════════════════════════════════════════════════════════
def bootstrap_residual_quantiles(
    y_train: np.ndarray,
    point_pred: float,
    n_bootstrap: int = N_BOOTSTRAP,
    quantiles: List[float] = None
) -> Dict[float, float]:
    """
    Given training series and a point prediction, bootstrap residuals
    to generate quantile predictions.

    Args:
        y_train: training series (non-negative)
        point_pred: single point prediction for horizon=1
        n_bootstrap: number of bootstrap resamples
        quantiles: list of quantile levels (e.g. [0.10, 0.25, 0.75, 0.90])

    Returns:
        dict mapping quantile level to predicted value
    """
    if quantiles is None:
        quantiles = QUANTILES

    y = _ensure_nonneg(y_train)
    n = len(y)

    if n == 0:
        return {q: max(point_pred, 0.0) for q in quantiles}

    # Compute fitted values for residuals
    # For methods without explicit fitted values, use simple mean or trend
    if n >= 2:
        # use linear trend for fitted values
        x = np.arange(n)
        coeffs = np.polyfit(x, y, 1) if n >= 3 else np.polyfit(x, y, 1)
        fitted = np.polyval(coeffs, x)
        fitted = _ensure_nonneg(fitted)
    else:
        fitted = np.repeat(np.mean(y), n)

    residuals = y - fitted

    # Bootstrap
    bootstrap_preds = []
    for _ in range(n_bootstrap):
        sampled_resid = np.random.choice(residuals, size=1, replace=True)
        bootstrap_pred = point_pred + sampled_resid[0]
        bootstrap_pred = max(bootstrap_pred, 0.0)
        bootstrap_preds.append(bootstrap_pred)

    bootstrap_preds = np.array(bootstrap_preds)

    # Compute quantiles
    result = {}
    for q in quantiles:
        result[q] = float(np.percentile(bootstrap_preds, q * 100))

    return result


# ═══════════════════════════════════════════════════════════════
# 6. Point prediction methods (baseline for quantile extension)
# ═══════════════════════════════════════════════════════════════

def _linear_trend_point(y_train: np.ndarray, horizon: int = 1) -> np.ndarray:
    """Linear trend: fit y ~ t, predict forward."""
    y = _ensure_nonneg(y_train)
    n = len(y)
    if n == 0:
        return np.zeros(horizon)
    if n == 1:
        return np.repeat(y[0], horizon)
    x = np.arange(n)
    coeffs = np.polyfit(x, y, deg=min(2, n - 1))  # deg ≤ n-1
    preds = np.polyval(coeffs, np.arange(n, n + horizon))
    return _ensure_nonneg(preds)


def _exp_smooth_point(y_train: np.ndarray, horizon: int = 1) -> np.ndarray:
    """
    Exponential smoothing point forecast using statsmodels.
    Falls back to simple mean if statsmodels unavailable or insufficient data.
    """
    y = _ensure_nonneg(y_train)
    n = len(y)
    if n == 0:
        return np.zeros(horizon)
    if n <= 2:
        return _linear_trend_point(y_train, horizon)

    try:
        from statsmodels.tsa.holtwinters import SimpleExpSmoothing
        # Simple exponential smoothing
        model = SimpleExpSmoothing(y).fit(optimized=True)
        pred_val = model.forecast(horizon)
        return _ensure_nonneg(np.array(pred_val))
    except Exception:
        # fallback to linear trend
        return _linear_trend_point(y_train, horizon)


def _historic_average_point(y_train: np.ndarray, horizon: int = 1, window: int = None) -> np.ndarray:
    """Historical average: mean of last `window` values, or all if window is None."""
    y = _ensure_nonneg(y_train)
    n = len(y)
    if n == 0:
        return np.zeros(horizon)
    if window is not None:
        y = y[-min(window, n):]
    pred = np.mean(y) if len(y) > 0 else 0.0
    return np.repeat(pred, horizon)


def _seasonal_naive_point(y_train: np.ndarray, horizon: int = 1, k: int = 4) -> np.ndarray:
    """
    Seasonal naive: average of the last k values.
    For sparse series with many zeros, this provides a conservative estimate.
    """
    y = _ensure_nonneg(y_train)
    n = len(y)
    if n == 0:
        return np.zeros(horizon)
    k = min(k, n)
    tail = y[-k:]
    pred = np.mean(tail) if len(tail) > 0 else 0.0
    return np.repeat(pred, horizon)


# ═══════════════════════════════════════════════════════════════
# 7. Method pool definition
# ═══════════════════════════════════════════════════════════════
def build_method_pool() -> List[Dict]:
    """
    Build the complete quantile prediction method pool.
    Each method has:
      - method_id: unique identifier
      - method_name: human-readable name
      - point_fn: function(y_train, horizon) -> point prediction array
      - quantile_fn: function(y_train, horizon, point_pred) -> quantile dict (optional override)
    """
    methods = []

    methods.append({
        "method_id": "Q_ExpSmooth",
        "method_name": "ExpSmooth分位数",
        "point_fn": _exp_smooth_point,
        "category": "stats",
    })

    methods.append({
        "method_id": "Q_LinearTrend",
        "method_name": "LinearTrend分位数",
        "point_fn": _linear_trend_point,
        "category": "stats",
    })

    methods.append({
        "method_id": "Q_HistAvg",
        "method_name": "HistoricAverage分位数",
        "point_fn": _historic_average_point,
        "category": "stats",
    })

    methods.append({
        "method_id": "Q_SeasNaive",
        "method_name": "SeasonalNaive分位数",
        "point_fn": _seasonal_naive_point,
        "category": "stats",
    })

    return methods


# ═══════════════════════════════════════════════════════════════
# 8. Run backtest BT01-BT06
# ═══════════════════════════════════════════════════════════════
def run_backtest(
    panel: pd.DataFrame,
    bucket_ids: List[str],
    method_pool: List[Dict],
    log: OperationLog
) -> pd.DataFrame:
    """
    Run BT01-BT06 backtest for each product line × method.
    For each fold, generate point prediction + quantile predictions (10%/25%/75%/90%).
    """
    detail_rows = []
    n_folds = BACKTEST_FOLDS
    total_lines = panel["产品线"].nunique()

    for pline, g in panel.groupby("产品线", dropna=False):
        sales = g.set_index("桶编号").reindex(bucket_ids)["销售额"].fillna(0.0).values

        for method in method_pool:
            point_fn = method["point_fn"]

            for fold_idx in range(n_folds):
                train_end_idx = 6 + fold_idx  # H07=6, H08=7, ..., H12=11
                test_idx = train_end_idx

                y_train = sales[:train_end_idx]
                y_actual = sales[test_idx]

                # Point prediction
                point_pred = float(point_fn(y_train, horizon=1)[0])

                # Bootstrap quantile prediction
                quantile_preds = bootstrap_residual_quantiles(
                    y_train, point_pred, n_bootstrap=N_BOOTSTRAP, quantiles=QUANTILES
                )

                # Check if actual falls within each interval
                in_80 = (y_actual >= quantile_preds[0.10]) and (y_actual <= quantile_preds[0.90])
                in_50 = (y_actual >= quantile_preds[0.25]) and (y_actual <= quantile_preds[0.75])

                # Pinball loss for each quantile
                pinball = {}
                for q in QUANTILES:
                    error = y_actual - quantile_preds[q]
                    pinball[q] = float(max(q * error, (q - 1) * error))

                detail_rows.append({
                    "产品线": pline,
                    "方法ID": method["method_id"],
                    "方法名称": method["method_name"],
                    "回测折次": f"BT{fold_idx + 1:02d}",
                    "训练期长度": train_end_idx,
                    "预测桶": bucket_ids[test_idx],
                    "实际销售额": round(y_actual, 2),
                    "点预测": round(point_pred, 2),
                    "q0.10": round(quantile_preds[0.10], 2),
                    "q0.25": round(quantile_preds[0.25], 2),
                    "q0.75": round(quantile_preds[0.75], 2),
                    "q0.90": round(quantile_preds[0.90], 2),
                    "区间80_下界": round(quantile_preds[0.10], 2),
                    "区间80_上界": round(quantile_preds[0.90], 2),
                    "区间50_下界": round(quantile_preds[0.25], 2),
                    "区间50_上界": round(quantile_preds[0.75], 2),
                    "是否在80区间内": in_80,
                    "是否在50区间内": in_50,
                    "Pinball_q0.10": round(pinball[0.10], 6),
                    "Pinball_q0.25": round(pinball[0.25], 6),
                    "Pinball_q0.75": round(pinball[0.75], 6),
                    "Pinball_q0.90": round(pinball[0.90], 6),
                })

    detail = pd.DataFrame(detail_rows)
    log.add("05回测", f"运行{len(method_pool)}种方法×{n_folds}折回测",
            f"明细rows={len(detail)}，产品线数={total_lines}",
            rows=len(detail))
    return detail


# ═══════════════════════════════════════════════════════════════
# 9. Compute coverage metrics
# ═══════════════════════════════════════════════════════════════
def compute_coverage_metrics(
    detail: pd.DataFrame,
    method_pool: List[Dict],
    log: OperationLog
) -> pd.DataFrame:
    """
    Aggregate backtest detail into coverage metrics per product line × method.

    Metrics:
      - 80%覆盖率: actual in [q10, q90] proportion
      - 80%覆盖偏差: 80%覆盖率 - 0.80
      - 50%覆盖率: actual in [q25, q75] proportion
      - 50%覆盖偏差: 50%覆盖率 - 0.50
      - 区间80_平均宽度: mean(q90 - q10)
      - 区间50_平均宽度: mean(q75 - q25)
      - 标准化宽度80: mean(q90 - q10) / mean(|actual|)
      - 标准化宽度50: mean(q75 - q25) / mean(|actual|)
      - 分位数损失: mean of all pinball losses
    """
    if detail.empty:
        return pd.DataFrame()

    # Use dictionary form for aggregation to avoid identifier-starting-with-digit issue
    agg = detail.groupby(["产品线", "方法ID", "方法名称"]).agg(**{
        "折数": ("回测折次", "nunique"),
        "_cov80": ("是否在80区间内", "mean"),
        "_cov50": ("是否在50区间内", "mean"),
        "_width80": ("区间80_上界", lambda x: np.mean(x - detail.loc[x.index, "区间80_下界"])),
        "_width50": ("区间50_上界", lambda x: np.mean(x - detail.loc[x.index, "区间50_下界"])),
        "实际绝对值均值": ("实际销售额", lambda x: np.mean(np.abs(x))),
        "实际标准差": ("实际销售额", "std"),
        "Pinball_total": ("Pinball_q0.10", lambda x: (
            detail.loc[x.index, "Pinball_q0.10"].mean()
            + detail.loc[x.index, "Pinball_q0.25"].mean()
            + detail.loc[x.index, "Pinball_q0.75"].mean()
            + detail.loc[x.index, "Pinball_q0.90"].mean()
        ) / 4.0),
        "点预测WAPE": ("实际销售额", lambda x: np.mean(np.abs(
            detail.loc[x.index, "点预测"] - x
        ) / np.maximum(np.abs(x), EPS))),
    }).reset_index()

    # Rename internal keys to proper column names
    agg.rename(columns={
        "_cov80": "80覆盖率",
        "_cov50": "50覆盖率",
        "_width80": "区间80_平均宽度",
        "_width50": "区间50_平均宽度",
    }, inplace=True)

    # Round key metrics
    agg["80覆盖率"] = agg["80覆盖率"].round(6)
    agg["50覆盖率"] = agg["50覆盖率"].round(6)

    # Coverage bias
    agg["80覆盖偏差"] = (agg["80覆盖率"] - 0.80).round(6)
    agg["50覆盖偏差"] = (agg["50覆盖率"] - 0.50).round(6)

    # Interval widths
    agg["区间80_平均宽度"] = agg["区间80_平均宽度"].round(2)
    agg["区间50_平均宽度"] = agg["区间50_平均宽度"].round(2)

    # Normalized width
    agg["标准化宽度80"] = (agg["区间80_平均宽度"] / agg["实际绝对值均值"].replace(0, np.nan)).round(4)
    agg["标准化宽度50"] = (agg["区间50_平均宽度"] / agg["实际绝对值均值"].replace(0, np.nan)).round(4)

    # Quantile loss
    agg["分位数损失"] = agg["Pinball_total"].round(6)

    # Point WAPE
    agg["点预测WAPE"] = agg["点预测WAPE"].round(6)

    # Rank per product line by 80覆盖偏差 (absolute value, smaller is better)
    agg["覆盖偏差_abs80"] = agg["80覆盖偏差"].abs()
    agg["排名_覆盖"] = agg.groupby("产品线")["覆盖偏差_abs80"].rank(method="min").astype(int)

    # Rank by quantile loss
    agg["排名_分位数损失"] = agg.groupby("产品线")["分位数损失"].rank(method="min").astype(int)

    # Composite score: weighted combination of coverage accuracy and interval width
    # Lower is better
    agg["综合得分"] = (
        agg["覆盖偏差_abs80"] * 0.4
        + agg["标准化宽度80"].fillna(10) * 0.3
        + agg["分位数损失"].fillna(10) * 0.3
    ).round(6)

    log.add("06评估", "计算区间覆盖指标",
            f"产品线数={agg['产品线'].nunique()}，方法数={agg['方法ID'].nunique()}",
            rows=len(agg))
    return agg


# ═══════════════════════════════════════════════════════════════
# 10. Generate recommendation
# ═══════════════════════════════════════════════════════════════
def compute_recommendation(
    metrics: pd.DataFrame,
    baseline_selected: pd.DataFrame,
    log: OperationLog
) -> pd.DataFrame:
    """
    For each product line:
      - Select best interval method (by 综合得分, lower better)
      - Compare with baseline WAPE
      - Assess coverage quality
      - Mark pass/fail based on coverage bias < 5%
    """
    if metrics.empty:
        return pd.DataFrame()

    # Best method per product line by composite score
    best_idx = metrics.groupby("产品线")["综合得分"].idxmin()
    best_per_line = metrics.loc[best_idx].copy()

    # Merge baseline WAPE
    baseline_map = baseline_selected.set_index("产品线")["销售额WAPE"].to_dict() if "销售额WAPE" in baseline_selected.columns else {}
    best_per_line["基线WAPE"] = best_per_line["产品线"].map(baseline_map)
    best_per_line["基线WAPE"] = best_per_line["基线WAPE"].fillna(np.nan)

    # Coverage quality assessment
    def assess_coverage(row: pd.Series) -> str:
        bias80 = abs(row["80覆盖偏差"])
        bias50 = abs(row["50覆盖偏差"])
        if bias80 < 0.05 and bias50 < 0.05:
            return "优秀-覆盖偏差<5%"
        elif bias80 < 0.10 and bias50 < 0.10:
            return "良好-覆盖偏差<10%"
        elif bias80 < 0.15:
            return "一般-覆盖偏差<15%"
        else:
            return "较差-覆盖偏差>=15%"

    best_per_line["覆盖质量"] = best_per_line.apply(assess_coverage, axis=1)

    # Interval width assessment
    def assess_width(row: pd.Series) -> str:
        nw80 = row["标准化宽度80"]
        if pd.isna(nw80):
            return "无法评估"
        if nw80 < 1.0:
            return "合理-宽度<均值"
        elif nw80 < 2.0:
            return "较宽-宽度<2倍均值"
        else:
            return "过宽-宽度>=2倍均值"

    best_per_line["区间宽度评价"] = best_per_line.apply(assess_width, axis=1)

    # Pass/Fail: coverage bias < 5% for 80% CI
    best_per_line["是否通过"] = best_per_line["80覆盖偏差"].abs().apply(
        lambda x: "是" if pd.notna(x) and x < 0.05 else "否"
    )

    # Low confidence line business value assessment
    def biz_value(row: pd.Series) -> str:
        pline = row["产品线"]
        if pline not in LOW_CONFIDENCE_LINES:
            return "N/A-非低置信线"
        bias80 = abs(row["80覆盖偏差"])
        if row["是否通过"] == "是":
            return "高-区间预测有效替代点预测"
        elif bias80 < 0.10:
            return "中-区间预测有一定参考价值"
        else:
            return "低-区间预测质量不足，建议关注数据质量"

    best_per_line["业务价值"] = best_per_line.apply(biz_value, axis=1)

    # vs baseline comparison
    best_per_line["vs基线WAPE_pp"] = (
        best_per_line["基线WAPE"] - best_per_line["点预测WAPE"]
    ).round(6)

    # Select output columns
    rec = best_per_line[[
        "产品线", "方法ID", "方法名称",
        "80覆盖率", "80覆盖偏差", "50覆盖率", "50覆盖偏差",
        "区间80_平均宽度", "区间50_平均宽度",
        "标准化宽度80", "标准化宽度50",
        "分位数损失", "点预测WAPE", "基线WAPE", "vs基线WAPE_pp",
        "覆盖质量", "区间宽度评价", "是否通过", "业务价值",
        "综合得分",
    ]].copy()

    # Summary stats
    pass_count = (rec["是否通过"] == "是").sum()
    low_conf_pass = rec[rec["产品线"].isin(LOW_CONFIDENCE_LINES)]["是否通过"].eq("是").sum()
    avg_bias80 = rec["80覆盖偏差"].abs().mean()

    log.add("07推荐", "生成区间方法推荐",
            f"通过线数={pass_count}/{len(rec)}，低置信通过={low_conf_pass}/4，平均80覆盖偏差={avg_bias80:.4f}",
            rows=len(rec))

    print(f"\n{'='*60}")
    print(f"  区间预测推荐摘要:")
    print(f"  通过线数: {pass_count}/{len(rec)}")
    print(f"  低置信线通过: {low_conf_pass}/4")
    print(f"  平均80覆盖偏差: {avg_bias80:.4f}")
    print(f"  强证据: {'是' if pass_count >= 10 else '否'} (>=10条线通过)")
    print(f"{'='*60}\n")

    return rec


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════
def main():
    print("=" * 80)
    print("EXPERIMENT 1.2: Quantile Forecasting (Interval Prediction)")
    print("=" * 80)

    log = OperationLog()

    # ── 0. Verify field spec exists ──
    print("\n[Step 0] Verifying field spec...")
    if FIELD_SPEC_PATH.exists():
        log.add("00口径", "读取字段口径文档",
                f"字段口径已锁定: {FIELD_SPEC_PATH.name}",
                str(FIELD_SPEC_PATH))
        print(f"  字段口径: {FIELD_SPEC_PATH.name}")
    else:
        log.add("00口径", "字段口径文档缺失",
                "WARNING: field_spec_locked_20260612.md 不存在",
                str(FIELD_SPEC_PATH))

    # ── 1. Read raw data ──
    print("\n[Step 1] Reading raw data...")
    df_raw = read_raw_data(log)

    # ── 2. Clean and derive ──
    print("\n[Step 2] Cleaning and deriving fields...")
    df_clean = clean_and_derive(df_raw, log)

    # ── 3. Get all 17 product lines ──
    print("\n[Step 3] Determining product lines...")
    all_lines = sorted(df_clean["型号_产品线（新）"].dropna().unique().tolist())
    log.add("03产品线", "获取全部产品线",
            f"产品线数={len(all_lines)}: {all_lines}",
            rows=len(all_lines))
    print(f"  全部产品线({len(all_lines)}): {all_lines}")
    print(f"  低置信C类线: {LOW_CONFIDENCE_LINES}")

    # ── 4. Build quarterly series ──
    print("\n[Step 4] Building quarterly series...")
    panel, latest_month, bucket_ids = build_quarterly_series(df_clean, all_lines, log)
    print(f"  Latest month: {latest_month}")
    print(f"  Buckets: {bucket_ids}")

    # ── 5. Build method pool ──
    print(f"\n[Step 5] Building method pool...")
    method_pool = build_method_pool()
    log.add("05方法池", "构建分位数预测方法池",
            f"方法总数={len(method_pool)}: {[m['method_id'] for m in method_pool]}")

    # ── 6. Run backtest ──
    print(f"\n[Step 6] Running BT01-BT06 backtest (this may take a while)...")
    detail = run_backtest(panel, bucket_ids, method_pool, log)

    # ── 7. Compute coverage metrics ──
    print(f"\n[Step 7] Computing coverage metrics...")
    metrics = compute_coverage_metrics(detail, method_pool, log)

    # ── 8. Load baseline corrected ──
    print(f"\n[Step 8] Loading baseline corrected methods...")
    if BASELINE_PATH.exists():
        baseline_selected = pd.read_csv(str(BASELINE_PATH), encoding="utf-8-sig")
        log.add("08基线", "加载修正版0.2基线",
                f"基线产品线数={len(baseline_selected)}",
                str(BASELINE_PATH), len(baseline_selected))
        print(f"  基线产品线数: {len(baseline_selected)}")
        print(f"  基线WAPE范围: {baseline_selected['销售额WAPE'].min():.4f} ~ {baseline_selected['销售额WAPE'].max():.4f}")
    else:
        print(f"  WARNING: 基线文件不存在: {BASELINE_PATH}，跳过vs基线对比")
        baseline_selected = pd.DataFrame(columns=["产品线", "销售额WAPE"])
        log.add("08基线", "基线文件缺失",
                "WARNING: baseline_corrected_selected_methods.csv 不存在",
                str(BASELINE_PATH))

    # ── 9. Compute recommendation ──
    print(f"\n[Step 9] Computing recommendation...")
    recommendation = compute_recommendation(metrics, baseline_selected, log)

    # ── 10. Write outputs ──
    print(f"\n[Step 10] Writing outputs...")

    detail.to_csv(
        OUTPUT_DIR / "quantile_backtest_detail.csv",
        index=False, encoding="utf-8-sig"
    )
    metrics.to_csv(
        OUTPUT_DIR / "quantile_coverage_metrics.csv",
        index=False, encoding="utf-8-sig"
    )
    if not recommendation.empty:
        recommendation.to_csv(
            OUTPUT_DIR / "quantile_recommendation.csv",
            index=False, encoding="utf-8-sig"
        )
    log.to_frame().to_csv(
        OUTPUT_DIR / "operation_log.csv",
        index=False, encoding="utf-8-sig"
    )

    log.add("10输出", "写入全部CSV",
            f"输出目录={OUTPUT_DIR}",
            rows=None)

    # ── 11. Print summary ──
    print("\n" + "=" * 80)
    print("EXPERIMENT 1.2 COMPLETE")
    print(f"  Output directory: {OUTPUT_DIR}")
    print("=" * 80)

    # Print key findings
    if not recommendation.empty:
        print("\n--- 低置信C类线评估 ---")
        low_conf_rec = recommendation[recommendation["产品线"].isin(LOW_CONFIDENCE_LINES)]
        if not low_conf_rec.empty:
            for _, row in low_conf_rec.iterrows():
                print(f"  {row['产品线']}: "
                      f"方法={row['方法ID']}, "
                      f"80覆盖={row['80覆盖率']:.2%}, "
                      f"偏差={row['80覆盖偏差']:.2%}, "
                      f"通过={row['是否通过']}, "
                      f"业务价值={row['业务价值']}")

        print("\n--- 全部产品线推荐方法 ---")
        for _, row in recommendation.iterrows():
            print(f"  {row['产品线']:20s} | {row['方法ID']:15s} | "
                  f"80覆盖={row['80覆盖率']:.2%} | "
                  f"宽度={row['标准化宽度80']:.2f} | "
                  f"通过={row['是否通过']}")

    return panel, detail, metrics, recommendation


if __name__ == "__main__":
    main()
