# -*- coding: utf-8 -*-
"""
实验 1.2: 移动平均窗口自适应优化
创建: 2026-06-15

假设: 现有系统固定窗口(12桶)，但不同产品线的最优窗口不同。
     通过回测自动选择每产品线的最优窗口，可以降低WAPE。

范围: 全部17条产品线
方法: 简单移动平均(均值)，窗口自适应 [3, 4, 6, 12]
回测: BT01-BT06 扩展窗口，horizon=1季度
层级: 产品线级 (暂不实现产品级变体)

成功标准:
  - 金额加权WAPE < 对照组(窗口=12)
  - 产品线平均WAPE不恶化>1pp
  - 窗口选择稳定(多折一致)

输出:
  - output/window_comparison_detail.csv   每线每窗口每折的预测值
  - output/window_selection.csv           每线最优窗口、评分、稳定性标记
  - output/window_performance_comparison.csv 对照组vs实验组WAPE对比
  - output/window_optimization_recommendation.csv 推荐策略、成功标准判定
  - output/operation_log.csv
"""

from __future__ import annotations

import sys
import time
from collections import Counter
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
BACKTEST_FOLDS = 6  # BT01-BT06
HORIZON = 1  # 1 quarter ahead

# ── window candidates ──
WINDOW_CANDIDATES = [3, 4, 6, 12]
CONTROL_WINDOW = 12

# ── baseline corrected methods ──
BASELINE_SELECTED_PATH = (
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
    log.add(
        "01读取", "读取原始Excel",
        f"读取完成，工作表={SHEET_NAME}，列数={len(df.columns)}，rows={len(df)}",
        str(DATA_FILE), len(df)
    )
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
    log.add(
        "02清洗", "字段清洗与派生",
        f"清洗前rows={before}，清洗后rows={after}，产品线数={df['型号_产品线（新）'].nunique()}，"
        f"无效日期行={invalid_date}",
        rows=after
    )
    return df


# ═══════════════════════════════════════════════════════════════
# 3. Build quarterly buckets (product line level, sales amount)
# ═══════════════════════════════════════════════════════════════
def build_quarterly_series(
    df: pd.DataFrame,
    log: OperationLog
) -> Tuple[pd.DataFrame, pd.Period, List[str], List[str]]:
    """
    Build quarterly time series for ALL product lines.
    Returns:
      - panel_df: columns [产品线, 桶编号, 销售额, 销售量]
      - latest_month: latest month in data
      - bucket_ids: list of H01-H12 bucket ids
      - all_lines: sorted list of all product lines
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

    # assign bucket to all rows
    df["桶编号"] = pd.NA
    for bi in bucket_info:
        mask = df["_月"].between(bi["开始Period"], bi["结束Period"])
        df.loc[mask, "桶编号"] = bi["桶编号"]
    df_bucketed = df[df["桶编号"].notna()].copy()

    # aggregate to product line × bucket
    agg = df_bucketed.groupby(["型号_产品线（新）", "桶编号"], dropna=False).agg(
        销售额=("RMB 未税金额小计", "sum"),
        销售量=("发货数量", "sum"),
    ).reset_index()
    agg.rename(columns={"型号_产品线（新）": "产品线"}, inplace=True)

    all_lines = sorted(agg["产品线"].unique().tolist())

    # complete panel (all lines × all buckets)
    keys = agg[["产品线"]].drop_duplicates()
    buckets_df = pd.DataFrame({"桶编号": bucket_ids})
    panel = keys.merge(buckets_df, how="cross")
    panel = panel.merge(agg, on=["产品线", "桶编号"], how="left")
    for c in ["销售额", "销售量"]:
        panel[c] = panel[c].fillna(0.0)

    log.add(
        "03分桶", "构建12个季度桶",
        f"最新月份={latest_month}，产品线数={len(all_lines)}，桶数={len(bucket_ids)}，"
        f"panel rows={len(panel)}",
        rows=len(panel)
    )
    return panel, latest_month, bucket_ids, all_lines


# ═══════════════════════════════════════════════════════════════
# 4. Simple Moving Average forecast
# ═══════════════════════════════════════════════════════════════
def moving_average_forecast(y_train: np.ndarray, window: int, horizon: int = 1) -> np.ndarray:
    """
    Simple moving average forecast using mean of last `window` values.

    Args:
        y_train: array, training sequence
        window: int, window size
        horizon: int, forecast horizon (number of periods ahead)

    Returns:
        forecast: array of length `horizon`, all values = mean of last window
    """
    y = np.maximum(np.nan_to_num(y_train, nan=0.0, posinf=0.0, neginf=0.0), 0.0)
    if len(y) == 0:
        return np.zeros(horizon)
    w = max(1, min(window, len(y)))
    tail = y[-w:]
    pred = tail.mean()
    return np.repeat(pred, horizon)


# ═══════════════════════════════════════════════════════════════
# 5. Run BT01-BT06 backtest for one product line × window
# ═══════════════════════════════════════════════════════════════
def backtest_one_line_window(
    sales: np.ndarray,
    bucket_ids: List[str],
    window: int,
    pline: str,
) -> List[Dict]:
    """
    Run BT01-BT06 backtest for a single product line with a single window.

    BT01: train H01-H06 → predict H07 (test_idx=6)
    BT02: train H01-H07 → predict H08 (test_idx=7)
    ...
    BT06: train H01-H11 → predict H12 (test_idx=11)

    Returns list of dicts, one per fold.
    """
    rows = []
    for fold_idx in range(BACKTEST_FOLDS):
        train_end_idx = 6 + fold_idx  # H07=6, H08=7, ..., H12=11
        test_idx = train_end_idx

        y_train = sales[:train_end_idx]
        y_actual = sales[test_idx]

        pred = moving_average_forecast(y_train, window, HORIZON)
        pred_val = float(pred[0])

        error = pred_val - y_actual
        ape = abs(error) / max(abs(y_actual), EPS) if abs(y_actual) > EPS else (
            0.0 if abs(error) < EPS else float("inf")
        )

        rows.append({
            "产品线": pline,
            "窗口": window,
            "回测折次": f"BT{fold_idx + 1:02d}",
            "训练期长度": train_end_idx,
            "预测桶": bucket_ids[test_idx],
            "实际销售额": round(y_actual, 2),
            "预测销售额": round(pred_val, 2),
            "误差": round(error, 2),
            "APE": round(ape, 6),
        })
    return rows


# ═══════════════════════════════════════════════════════════════
# 6. Run all backtests: control (w=12) + experiment (w in [3,4,6,12])
# ═══════════════════════════════════════════════════════════════
def run_all_backtests(
    panel: pd.DataFrame,
    bucket_ids: List[str],
    product_lines: List[str],
    log: OperationLog
) -> pd.DataFrame:
    """
    Run backtest for every product line × every window candidate.
    Returns a detail DataFrame with all fold-level results.
    """
    all_detail_rows = []
    n_lines = len(product_lines)
    n_windows = len(WINDOW_CANDIDATES)

    for i, pline in enumerate(product_lines):
        g = panel[panel["产品线"] == pline]
        sales = g.set_index("桶编号").reindex(bucket_ids)["销售额"].fillna(0.0).values

        for window in WINDOW_CANDIDATES:
            fold_rows = backtest_one_line_window(sales, bucket_ids, window, pline)
            all_detail_rows.extend(fold_rows)

        if (i + 1) % 5 == 0 or (i + 1) == n_lines:
            print(f"  回测进度: {i + 1}/{n_lines} 产品线完成")

    detail = pd.DataFrame(all_detail_rows)
    log.add(
        "04回测", f"运行全部回测：{n_lines}产品线 × {n_windows}窗口 × {BACKTEST_FOLDS}折",
        f"明细rows={len(detail)}",
        rows=len(detail)
    )
    return detail


# ═══════════════════════════════════════════════════════════════
# 7. Compute per-window CV_WAPE and per-fold best window
# ═══════════════════════════════════════════════════════════════
# ── helper: filter zero-actual samples for WAPE ──
def _agg_window_group(group: pd.DataFrame) -> pd.Series:
    """Aggregate a single product line × window group.
    CV_WAPE and BT04_06_WAPE filter out zero-actual samples (修复WAPE计算).
    """
    valid_mask = group["实际销售额"].abs() > EPS
    valid = group[valid_mask]
    n_valid = len(valid)

    cv_wape = valid["APE"].mean() if n_valid > 0 else float("inf")

    if n_valid >= 3:
        bt_wape = valid["APE"].tail(3).mean()
    elif n_valid > 0:
        bt_wape = valid["APE"].mean()
    else:
        bt_wape = float("inf")

    return pd.Series({
        "CV_WAPE": cv_wape,
        "BT04_06_WAPE": bt_wape,
        "总绝对误差": group["误差"].abs().sum(),
        "总实际值": group["实际销售额"].sum(),
        "总预测值": group["预测销售额"].sum(),
        "总偏差": group["误差"].sum(),
    })


def compute_window_metrics(
    detail: pd.DataFrame,
    product_lines: List[str],
    log: OperationLog
) -> pd.DataFrame:
    """
    For each product line × window, compute:
      - CV_WAPE: mean APE across 6 folds
      - BT04_06_WAPE: mean APE across BT04-BT06
      - 总绝对误差, 总实际值, 总预测值
      - Per-fold best window for stability check

    Returns a DataFrame with per-line-per-window metrics.
    """
    if detail.empty:
        return pd.DataFrame()

    # Aggregate to product line × window (零值自动过滤)
    agg = detail.groupby(["产品线", "窗口"], dropna=False).apply(_agg_window_group).reset_index()

    # Bias = sum(error) / sum(actual)
    agg["Bias"] = agg["总偏差"] / agg["总实际值"].replace(0, np.nan)
    agg["Bias"] = agg["Bias"].fillna(0.0)

    for col in ["CV_WAPE", "BT04_06_WAPE", "Bias"]:
        agg[col] = agg[col].round(6)

    log.add(
        "05窗口指标", "计算每产品线×窗口的CV_WAPE等指标(零值已过滤)",
        f"产品线数={agg['产品线'].nunique()}，窗口数={agg['窗口'].nunique()}",
        rows=len(agg)
    )
    return agg


# ═══════════════════════════════════════════════════════════════
# 8. Select optimal window per product line with stability check
# ═══════════════════════════════════════════════════════════════
def select_optimal_windows(
    detail: pd.DataFrame,
    window_metrics: pd.DataFrame,
    product_lines: List[str],
    baseline_wape_map: Dict[str, float],
    log: OperationLog
) -> pd.DataFrame:
    """
    For each product line:
      1. Find the window with minimum CV_WAPE
      2. If tie, prefer longer window
      3. Check stability: per-fold best window consistency
      4. Classify A/B/C based on baseline WAPE

    Returns DataFrame: [产品线, 最优窗口, CV_WAPE, BT04_06_WAPE, Bias,
                         各窗口CV_WAPE, 稳定性, 不稳定原因, 产品分层]
    """
    if window_metrics.empty:
        return pd.DataFrame()

    rows = []
    for pline in product_lines:
        wm = window_metrics[window_metrics["产品线"] == pline].copy()
        if wm.empty:
            continue

        # ── per-window CV_WAPE ──
        window_wape = {}
        for _, row in wm.iterrows():
            window_wape[int(row["窗口"])] = float(row["CV_WAPE"])

        # ── select best window by min CV_WAPE, tie-break: longer window ──
        sorted_windows = sorted(WINDOW_CANDIDATES, key=lambda w: (window_wape.get(w, float("inf")), -w))
        best_window = sorted_windows[0]
        best_wape = window_wape[best_window]

        # ── per-fold best window (for stability check) ──
        line_detail = detail[detail["产品线"] == pline].copy()
        fold_best_windows = []
        for fold_idx in range(BACKTEST_FOLDS):
            fold_name = f"BT{fold_idx + 1:02d}"
            fold_data = line_detail[line_detail["回测折次"] == fold_name].copy()
            if fold_data.empty:
                continue
            # best window for this fold (min APE)
            best_row = fold_data.loc[fold_data["APE"].idxmin()]
            fold_best_windows.append(int(best_row["窗口"]))

        # ── stability check ──
        is_stable = True
        unstable_reason = ""
        if len(fold_best_windows) >= 3:
            counter = Counter(fold_best_windows)
            most_common_window, most_common_count = counter.most_common(1)[0]
            stability_ratio = most_common_count / len(fold_best_windows)
            if stability_ratio < 0.67:  # less than 2/3 agreement
                is_stable = False
                unstable_reason = (
                    f"窗口选择不一致: {dict(counter)}, 最频窗口={most_common_window}"
                    f"({most_common_count}/{len(fold_best_windows)}折)"
                    f", 全局最优={best_window}"
                )
            elif most_common_window != best_window:
                # 最频窗口与全局最优不同
                is_stable = False
                unstable_reason = (
                    f"全局最优窗口({best_window})与最频窗口({most_common_window})不一致, "
                    f"各折最优: {fold_best_windows}"
                )

        # ── product class ──
        bl_wape = baseline_wape_map.get(pline, float("inf"))
        if bl_wape < 0.20:
            pclass = "A"
        elif bl_wape < 0.35:
            pclass = "B"
        else:
            pclass = "C"

        # ── build row ──
        row_data = {
            "产品线": pline,
            "产品分层": pclass,
            "最优窗口": best_window,
            "CV_WAPE": round(best_wape, 6),
            "BT04_06_WAPE": round(float(wm[wm["窗口"] == best_window]["BT04_06_WAPE"].values[0]), 6),
            "Bias": round(float(wm[wm["窗口"] == best_window]["Bias"].values[0]), 6),
            "WAPE_窗口3": round(window_wape.get(3, float("nan")), 6),
            "WAPE_窗口4": round(window_wape.get(4, float("nan")), 6),
            "WAPE_窗口6": round(window_wape.get(6, float("nan")), 6),
            "WAPE_窗口12": round(window_wape.get(12, float("nan")), 6),
            "各折最优窗口": str(fold_best_windows),
            "是否稳定": is_stable,
            "不稳定原因": unstable_reason,
            "基线WAPE": round(bl_wape if bl_wape != float("inf") else float("nan"), 6),
        }
        rows.append(row_data)

    selection = pd.DataFrame(rows)
    n_stable = selection["是否稳定"].sum()
    n_unstable = len(selection) - n_stable
    log.add(
        "06窗口选择", "为每条产品线选择最优窗口",
        f"产品线数={len(selection)}，稳定={n_stable}，不稳定={n_unstable}",
        rows=len(selection)
    )

    if n_unstable > 0:
        unstable_lines = selection[~selection["是否稳定"]]["产品线"].tolist()
        print(f"  WARNING: 窗口选择不稳定产品线: {unstable_lines}")

    return selection


# ═══════════════════════════════════════════════════════════════
# 9. Compute performance comparison: control vs experiment
# ═══════════════════════════════════════════════════════════════
def compute_performance_comparison(
    detail: pd.DataFrame,
    window_selection: pd.DataFrame,
    product_lines: List[str],
    log: OperationLog
) -> pd.DataFrame:
    """
    Compare control (window=12) vs experiment (adaptive window) at product line level.
    Computes:
      - 金额加权WAPE
      - 产品线简单平均WAPE
      - BT04_06金额加权WAPE
    """
    if detail.empty or window_selection.empty:
        return pd.DataFrame()

    # ── helper: compute filtered WAPE for a detail subset ──
    def _filtered_wape(sub_detail: pd.DataFrame) -> Tuple[float, float]:
        """Compute CV_WAPE and BT04_06_WAPE, filtering zero-actual samples."""
        valid = sub_detail[sub_detail["实际销售额"].abs() > EPS]
        n = len(valid)
        if n == 0:
            return float("inf"), float("inf")
        cv = float(valid["APE"].mean())
        bt = float(valid["APE"].tail(3).mean()) if n >= 3 else float(valid["APE"].mean())
        return cv, bt

    # ── control: aggregate detail for window=12 per line ──
    control_detail = detail[detail["窗口"] == CONTROL_WINDOW].copy()
    # Per-line control aggregation (zero-actual filtered for WAPE)
    control_agg = control_detail.groupby("产品线").agg(
        对照组_总绝对误差=("误差", lambda x: np.sum(np.abs(x))),
        对照组_总实际值=("实际销售额", "sum"),
        对照组_总偏差=("误差", "sum"),
    ).reset_index()
    # Add filtered WAPE per line
    ctrl_wape_map = {}
    ctrl_bt_wape_map = {}
    for pline, g in control_detail.groupby("产品线"):
        ctrl_wape_map[pline], ctrl_bt_wape_map[pline] = _filtered_wape(g)
    control_agg["对照组_CV_WAPE"] = control_agg["产品线"].map(ctrl_wape_map)
    control_agg["对照组_BT04_06_WAPE"] = control_agg["产品线"].map(ctrl_bt_wape_map)
    control_agg["对照组_Bias"] = control_agg["对照组_总偏差"] / control_agg["对照组_总实际值"].replace(0, np.nan)
    control_agg["对照组_Bias"] = control_agg["对照组_Bias"].fillna(0.0)

    # ── experiment: aggregate detail for selected window per line ──
    best_window_map = window_selection.set_index("产品线")["最优窗口"].to_dict()
    experiment_rows = []
    experiment_detail_rows = []  # for amount-weighted WAPE
    for pline in product_lines:
        best_w = best_window_map.get(pline, CONTROL_WINDOW)
        exp_data = detail[(detail["产品线"] == pline) & (detail["窗口"] == best_w)].copy()
        if exp_data.empty:
            continue

        cv_wape, bt_wape = _filtered_wape(exp_data)

        experiment_rows.append({
            "产品线": pline,
            "实验组窗口": best_w,
            "实验组_CV_WAPE": cv_wape,
            "实验组_BT04_06_WAPE": bt_wape,
            "实验组_总绝对误差": float(np.sum(np.abs(exp_data["误差"].values))),
            "实验组_总实际值": float(exp_data["实际销售额"].sum()),
            "实验组_总偏差": float(exp_data["误差"].sum()),
        })
        # Collect valid fold rows for amount-weighted WAPE
        exp_valid = exp_data[exp_data["实际销售额"].abs() > EPS]
        if len(exp_valid) > 0:
            experiment_detail_rows.append(exp_valid)
    experiment_agg = pd.DataFrame(experiment_rows)
    experiment_agg["实验组_Bias"] = experiment_agg["实验组_总偏差"] / experiment_agg["实验组_总实际值"].replace(0, np.nan)
    experiment_agg["实验组_Bias"] = experiment_agg["实验组_Bias"].fillna(0.0)

    # ── merge ──
    comparison = control_agg.merge(experiment_agg, on="产品线", how="outer")

    # ── compute deltas ──
    comparison["WAPE改善_pp"] = (
        comparison["对照组_CV_WAPE"] - comparison["实验组_CV_WAPE"]
    )
    comparison["BT04_06_WAPE改善_pp"] = (
        comparison["对照组_BT04_06_WAPE"] - comparison["实验组_BT04_06_WAPE"]
    )

    for c in ["WAPE改善_pp", "BT04_06_WAPE改善_pp"]:
        comparison[c] = comparison[c].round(6)

    # ── summary statistics ──
    # Amount-weighted WAPE (修复: sum(|error|)/sum(|actual|), 过滤零值)
    # Control: compute from fold-level valid rows
    control_valid = control_detail[control_detail["实际销售额"].abs() > EPS]
    if len(control_valid) > 0:
        total_error_ctrl = control_valid["误差"].abs().sum()
        total_actual_ctrl = control_valid["实际销售额"].abs().sum()
        aw_wape_control = total_error_ctrl / total_actual_ctrl if total_actual_ctrl > EPS else float("nan")
    else:
        aw_wape_control = float("nan")

    # BT04-06 amount-weighted WAPE for control
    control_bt_valid = control_valid[control_valid["回测折次"].isin(["BT04", "BT05", "BT06"])]
    if len(control_bt_valid) > 0:
        total_error_ctrl_bt = control_bt_valid["误差"].abs().sum()
        total_actual_ctrl_bt = control_bt_valid["实际销售额"].abs().sum()
        aw_wape_bt_control = total_error_ctrl_bt / total_actual_ctrl_bt if total_actual_ctrl_bt > EPS else float("nan")
    else:
        aw_wape_bt_control = float("nan")

    # Experiment: compute from collected valid rows
    if experiment_detail_rows:
        exp_valid_all = pd.concat(experiment_detail_rows, ignore_index=True)
        total_error_exp = exp_valid_all["误差"].abs().sum()
        total_actual_exp = exp_valid_all["实际销售额"].abs().sum()
        aw_wape_exp = total_error_exp / total_actual_exp if total_actual_exp > EPS else float("nan")
    else:
        aw_wape_exp = float("nan")

    # BT04-06 amount-weighted WAPE for experiment
    if experiment_detail_rows:
        exp_valid_all_bt = pd.concat(experiment_detail_rows, ignore_index=True)
        exp_valid_all_bt = exp_valid_all_bt[exp_valid_all_bt["回测折次"].isin(["BT04", "BT05", "BT06"])]
        if len(exp_valid_all_bt) > 0:
            total_error_exp_bt = exp_valid_all_bt["误差"].abs().sum()
            total_actual_exp_bt = exp_valid_all_bt["实际销售额"].abs().sum()
            aw_wape_bt_exp = total_error_exp_bt / total_actual_exp_bt if total_actual_exp_bt > EPS else float("nan")
        else:
            aw_wape_bt_exp = float("nan")
    else:
        aw_wape_bt_exp = float("nan")

    # Simple average WAPE (per-line mean, already filtered)
    simple_avg_control = float(comparison["对照组_CV_WAPE"].replace([float("inf"), -float("inf")], float("nan")).mean())
    simple_avg_exp = float(comparison["实验组_CV_WAPE"].replace([float("inf"), -float("inf")], float("nan")).mean())
    simple_avg_bt_control = float(comparison["对照组_BT04_06_WAPE"].replace([float("inf"), -float("inf")], float("nan")).mean())
    simple_avg_bt_exp = float(comparison["实验组_BT04_06_WAPE"].replace([float("inf"), -float("inf")], float("nan")).mean())

    log.add(
        "07性能对比", "计算对照组vs实验组WAPE对比(零值已过滤)",
        f"金额加权WAPE: 对照={aw_wape_control:.6f}, 实验={aw_wape_exp:.6f}, "
        f"改善={aw_wape_control - aw_wape_exp:.6f} | "
        f"简单平均WAPE: 对照={simple_avg_control:.6f}, 实验={simple_avg_exp:.6f}",
        rows=len(comparison)
    )

    # Store summary stats as attributes on the comparison df
    comparison.attrs["金额加权WAPE_对照组"] = round(aw_wape_control, 6) if not np.isnan(aw_wape_control) else float("nan")
    comparison.attrs["金额加权WAPE_实验组"] = round(aw_wape_exp, 6) if not np.isnan(aw_wape_exp) else float("nan")
    comparison.attrs["金额加权WAPE_改善"] = round(aw_wape_control - aw_wape_exp, 6) if not (np.isnan(aw_wape_control) or np.isnan(aw_wape_exp)) else float("nan")
    comparison.attrs["BT04_06金额加权WAPE_对照组"] = round(aw_wape_bt_control, 6) if not np.isnan(aw_wape_bt_control) else float("nan")
    comparison.attrs["BT04_06金额加权WAPE_实验组"] = round(aw_wape_bt_exp, 6) if not np.isnan(aw_wape_bt_exp) else float("nan")
    comparison.attrs["BT04_06金额加权WAPE_改善"] = round(aw_wape_bt_control - aw_wape_bt_exp, 6) if not (np.isnan(aw_wape_bt_control) or np.isnan(aw_wape_bt_exp)) else float("nan")
    comparison.attrs["简单平均WAPE_对照组"] = round(simple_avg_control, 6) if not np.isnan(simple_avg_control) else float("nan")
    comparison.attrs["简单平均WAPE_实验组"] = round(simple_avg_exp, 6) if not np.isnan(simple_avg_exp) else float("nan")
    comparison.attrs["简单平均WAPE_改善"] = round(simple_avg_control - simple_avg_exp, 6) if not (np.isnan(simple_avg_control) or np.isnan(simple_avg_exp)) else float("nan")
    comparison.attrs["简单平均BT_WAPE_对照组"] = round(simple_avg_bt_control, 6) if not np.isnan(simple_avg_bt_control) else float("nan")
    comparison.attrs["简单平均BT_WAPE_实验组"] = round(simple_avg_bt_exp, 6) if not np.isnan(simple_avg_bt_exp) else float("nan")

    return comparison


# ═══════════════════════════════════════════════════════════════
# 10. Generate recommendation with success criteria check
# ═══════════════════════════════════════════════════════════════
def generate_recommendation(
    window_selection: pd.DataFrame,
    performance_comparison: pd.DataFrame,
    log: OperationLog
) -> pd.DataFrame:
    """
    Check success criteria and generate recommendation.
    Returns DataFrame with recommendation rows.

    Success criteria:
      1. 金额加权WAPE < 对照组
      2. 产品线平均WAPE不恶化>1pp (i.e., 实验组平均WAPE <= 对照组平均WAPE + 0.01)
    """
    attrs = performance_comparison.attrs

    aw_control = attrs.get("金额加权WAPE_对照组", float("nan"))
    aw_exp = attrs.get("金额加权WAPE_实验组", float("nan"))
    aw_improve = attrs.get("金额加权WAPE_改善", float("nan"))

    sa_control = attrs.get("简单平均WAPE_对照组", float("nan"))
    sa_exp = attrs.get("简单平均WAPE_实验组", float("nan"))
    sa_improve = attrs.get("简单平均WAPE_改善", float("nan"))

    bt_aw_control = attrs.get("BT04_06金额加权WAPE_对照组", float("nan"))
    bt_aw_exp = attrs.get("BT04_06金额加权WAPE_实验组", float("nan"))
    bt_aw_improve = attrs.get("BT04_06金额加权WAPE_改善", float("nan"))

    # ── check criteria ──
    criterion_1_pass = (not np.isnan(aw_improve)) and aw_improve > 0
    criterion_2_pass = (not np.isnan(sa_improve)) and sa_improve >= -0.01  # not worsen > 1pp

    # ── overall success ──
    if criterion_1_pass and criterion_2_pass:
        overall_result = "通过"
        strategy = "全局推荐：自适应窗口优于固定12窗口，建议在所有产品线启用自适应窗口策略。"
    elif criterion_1_pass and not criterion_2_pass:
        overall_result = "部分通过(头部线局部策略)"
        strategy = (
            "金额加权改善但产品线平均恶化>1pp，仅建议在高金额权重头部产品线启用自适应窗口，"
            "长尾产品线保持固定12窗口。"
        )
    elif not criterion_1_pass and not criterion_2_pass:
        overall_result = "未通过"
        strategy = "自适应窗口未能优于固定12窗口，建议维持现有固定12窗口策略。"
    else:
        overall_result = "部分通过(仅简单平均改善)"
        strategy = "金额加权未改善但产品线简单平均改善，建议进一步分析头部产品线的窗口选择。"

    # ── window preference by class ──
    if "产品分层" in window_selection.columns:
        class_pref = window_selection.groupby("产品分层").agg(
            平均最优窗口=("最优窗口", "mean"),
            中位数最优窗口=("最优窗口", "median"),
            线数=("产品线", "count"),
        ).reset_index()
        class_pref_str = "; ".join(
            f"{row['产品分层']}类(avg={row['平均最优窗口']:.1f}, n={row['线数']})"
            for _, row in class_pref.iterrows()
        )
    else:
        class_pref_str = "无分层数据"

    # ── stability summary ──
    n_stable = int(window_selection["是否稳定"].sum()) if "是否稳定" in window_selection.columns else 0
    n_total = len(window_selection)
    stability_str = f"{n_stable}/{n_total}条产品线窗口选择稳定"

    rec_rows = [
        {
            "指标": "金额加权WAPE_对照组",
            "值": round(aw_control, 6),
            "判定": "",
            "说明": "固定窗口=12",
        },
        {
            "指标": "金额加权WAPE_实验组",
            "值": round(aw_exp, 6),
            "判定": "",
            "说明": "自适应窗口",
        },
        {
            "指标": "金额加权WAPE_改善",
            "值": round(aw_improve, 6),
            "判定": "通过" if criterion_1_pass else "未通过",
            "说明": "改善>0即通过" if criterion_1_pass else "未改善",
        },
        {
            "指标": "简单平均WAPE_对照组",
            "值": round(sa_control, 6),
            "判定": "",
            "说明": "固定窗口=12，17线简单平均",
        },
        {
            "指标": "简单平均WAPE_实验组",
            "值": round(sa_exp, 6),
            "判定": "",
            "说明": "自适应窗口，17线简单平均",
        },
        {
            "指标": "简单平均WAPE_改善",
            "值": round(sa_improve, 6),
            "判定": "通过" if criterion_2_pass else "未通过",
            "说明": "不恶化>1pp即通过" if criterion_2_pass else f"恶化{(abs(sa_improve) * 100):.1f}pp > 1pp阈值",
        },
        {
            "指标": "BT04_06金额加权WAPE_对照组",
            "值": round(bt_aw_control, 6),
            "判定": "",
            "说明": "Holdout期对照",
        },
        {
            "指标": "BT04_06金额加权WAPE_实验组",
            "值": round(bt_aw_exp, 6),
            "判定": "",
            "说明": "Holdout期实验",
        },
        {
            "指标": "BT04_06金额加权WAPE_改善",
            "值": round(bt_aw_improve, 6),
            "判定": "",
            "说明": "",
        },
        {
            "指标": "窗口选择稳定性",
            "值": stability_str,
            "判定": "稳定" if n_stable >= n_total * 0.7 else "需关注",
            "说明": f"稳定比例={n_stable / max(n_total, 1):.1%}",
        },
        {
            "指标": "A/B/C类窗口偏好",
            "值": class_pref_str,
            "判定": "",
            "说明": "各类产品线平均最优窗口",
        },
        {
            "指标": "全局判定",
            "值": overall_result,
            "判定": "",
            "说明": strategy,
        },
    ]

    recommendation = pd.DataFrame(rec_rows)

    log.add(
        "08推荐", "生成推荐策略和成功标准判定",
        f"全局判定={overall_result}，标准1={'通过' if criterion_1_pass else '未通过'}，"
        f"标准2={'通过' if criterion_2_pass else '未通过'}",
        rows=len(recommendation)
    )

    return recommendation


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════
def main():
    print("=" * 80)
    print("EXPERIMENT 1.2: Window Optimization for Moving Average")
    print("=" * 80)
    t_start = time.time()

    log = OperationLog()

    # ── Step 1: Read raw data ──
    print("\n[Step 1] Reading raw data...")
    df_raw = read_raw_data(log)

    # ── Step 2: Clean and derive fields ──
    print("\n[Step 2] Cleaning and deriving fields per field_spec_locked...")
    df_clean = clean_and_derive(df_raw, log)

    # ── Step 3: Build quarterly series ──
    print("\n[Step 3] Building quarterly series...")
    panel, latest_month, bucket_ids, all_lines = build_quarterly_series(df_clean, log)
    print(f"  Latest month: {latest_month}")
    print(f"  Buckets: {bucket_ids}")
    print(f"  Product lines ({len(all_lines)}): {all_lines}")

    # ── Step 4: Load baseline corrected selected methods ──
    print("\n[Step 4] Loading baseline corrected selected methods...")
    if not BASELINE_SELECTED_PATH.exists():
        print(f"  WARNING: 基线方法文件不存在: {BASELINE_SELECTED_PATH}，将使用默认分类")
        baseline_selected = pd.DataFrame(columns=["产品线", "销售额WAPE"])
        baseline_wape_map = {}
    else:
        baseline_selected = pd.read_csv(BASELINE_SELECTED_PATH)
        baseline_wape_map = baseline_selected.set_index("产品线")["销售额WAPE"].to_dict()
        log.add(
            "03基线", "加载修正版0.2基线最佳方法",
            f"基线产品线数={len(baseline_selected)}，WAPE范围="
            f"[{min(baseline_wape_map.values()):.4f}, {max(baseline_wape_map.values()):.4f}]",
            str(BASELINE_SELECTED_PATH), len(baseline_selected)
        )
        print(f"  Loaded {len(baseline_selected)} product lines with baseline WAPE")

    # ── Step 5: Run all backtests ──
    print("\n[Step 5] Running BT01-BT06 backtests for all windows...")
    detail = run_all_backtests(panel, bucket_ids, all_lines, log)

    # ── Step 6: Compute window metrics ──
    print("\n[Step 6] Computing window metrics...")
    window_metrics = compute_window_metrics(detail, all_lines, log)

    # ── Step 7: Select optimal windows ──
    print("\n[Step 7] Selecting optimal windows per product line...")
    window_selection = select_optimal_windows(
        detail, window_metrics, all_lines, baseline_wape_map, log
    )
    if not window_selection.empty:
        print(f"\n  Window distribution:")
        for w in WINDOW_CANDIDATES:
            count = (window_selection["最优窗口"] == w).sum()
            print(f"    窗口={w}: {count} lines")
        print(f"\n  Class preference:")
        if "产品分层" in window_selection.columns:
            for pclass in ["A", "B", "C"]:
                subset = window_selection[window_selection["产品分层"] == pclass]
                if len(subset) > 0:
                    avg_w = subset["最优窗口"].mean()
                    print(f"    {pclass}类 (n={len(subset)}): avg window={avg_w:.1f}")

    # ── Step 8: Compute performance comparison ──
    print("\n[Step 8] Computing performance comparison...")
    performance_comparison = compute_performance_comparison(
        detail, window_selection, all_lines, log
    )
    attrs = performance_comparison.attrs
    print(f"\n  {'='*60}")
    print(f"  金额加权WAPE:  对照={attrs['金额加权WAPE_对照组']:.6f}, "
          f"实验={attrs['金额加权WAPE_实验组']:.6f}, "
          f"改善={attrs['金额加权WAPE_改善']:.6f}")
    print(f"  简单平均WAPE:  对照={attrs['简单平均WAPE_对照组']:.6f}, "
          f"实验={attrs['简单平均WAPE_实验组']:.6f}, "
          f"改善={attrs['简单平均WAPE_改善']:.6f}")
    print(f"  BT04-06金额加权WAPE: 对照={attrs['BT04_06金额加权WAPE_对照组']:.6f}, "
          f"实验={attrs['BT04_06金额加权WAPE_实验组']:.6f}")
    print(f"  {'='*60}")

    # ── Step 9: Generate recommendation ──
    print("\n[Step 9] Generating recommendation...")
    recommendation = generate_recommendation(
        window_selection, performance_comparison, log
    )
    print(f"\n  {recommendation[recommendation['指标']=='全局判定']['值'].values[0]}")
    print(f"  {recommendation[recommendation['指标']=='全局判定']['说明'].values[0]}")

    # ── Step 10: Write outputs ──
    print("\n[Step 10] Writing outputs...")

    # 10a. window_comparison_detail.csv
    detail.to_csv(
        OUTPUT_DIR / "window_comparison_detail.csv",
        index=False, encoding="utf-8-sig"
    )
    print(f"  OK window_comparison_detail.csv ({len(detail)} rows)")

    # 10b. window_selection.csv
    window_selection.to_csv(
        OUTPUT_DIR / "window_selection.csv",
        index=False, encoding="utf-8-sig"
    )
    print(f"  OK window_selection.csv ({len(window_selection)} rows)")

    # 10c. window_performance_comparison.csv
    performance_comparison.to_csv(
        OUTPUT_DIR / "window_performance_comparison.csv",
        index=False, encoding="utf-8-sig"
    )
    print(f"  OK window_performance_comparison.csv ({len(performance_comparison)} rows)")

    # 10d. window_optimization_recommendation.csv
    recommendation.to_csv(
        OUTPUT_DIR / "window_optimization_recommendation.csv",
        index=False, encoding="utf-8-sig"
    )
    print(f"  OK window_optimization_recommendation.csv ({len(recommendation)} rows)")

    # 10e. operation_log.csv
    log.to_frame().to_csv(
        OUTPUT_DIR / "operation_log.csv",
        index=False, encoding="utf-8-sig"
    )
    print(f"  OK operation_log.csv ({len(log.rows)} rows)")

    log.add("09输出", "写入全部CSV", f"输出目录={OUTPUT_DIR}")

    elapsed = time.time() - t_start
    print(f"\n{'='*80}")
    print(f"EXPERIMENT 1.2 COMPLETE (elapsed: {elapsed:.1f}s)")
    print(f"{'='*80}")

    return panel, detail, window_metrics, window_selection, performance_comparison, recommendation


if __name__ == "__main__":
    main()
