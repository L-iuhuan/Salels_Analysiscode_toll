# -*- coding: utf-8 -*-
"""客户维度滚动季度历史分析与预测（KA/AA客户）。

在原有产品线预测框架基础上适配：
- 分组字段改为  终端客户简称
- 只分析 KA + AA 客户（按终端客户名称_客户类别筛选）
- 保留全部原552种方法 + 新增3种HTML模板独有算法（月度季节指数/Croston/Ensemble）
- 单价使用客户级近3月加权均价 × 趋势因子（参照HTML模板）
- 输出到独立目录 output/quarterly_forecast_customer/
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from shared.data_cleaning import read_excel_auto
except Exception:
    def read_excel_auto(path, sheet_name=0, usecols=None, **kwargs):
        try:
            import python_calamine
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


RAW_FILE = PROJECT_ROOT / "data" / "所有的出货明细5.9.xlsx"
OUTPUT_DIR = PROJECT_ROOT / "output" / "quarterly_forecast_customer"

REQUIRED_COLS = [
    "发货日期", "型号_产品线（新）", "存货名称", "发货数量", "RMB 未税金额小计",
    "成本", "利润", "未税单价", "单位成本", "代理商/直供名称", "ERP订单号",
    "产品线", "产品系列", "型号", "存货编码", "实际终端客户", "终端名称",
    "终端客户简称", "终端客户名称_客户类别",
]

STANDARD_COLS = REQUIRED_COLS.copy()
OPTIONAL_COLS = ["未税单价", "单位成本", "产品线", "产品系列", "型号", "存货编码", "实际终端客户", "终端名称"]
CRITICAL_COLS = ["发货日期", "存货名称", "发货数量", "RMB 未税金额小计", "成本", "利润", "代理商/直供名称", "ERP订单号", "终端客户简称", "终端客户名称_客户类别"]
GROUP_COL = "终端客户简称"  # ★ 核心变更：客户维度分组
EPS = 1e-9


def resolve_path(path_value, default):
    if not path_value:
        return default
    p = Path(path_value)
    return p if p.is_absolute() else PROJECT_ROOT / p


def load_config(config_path):
    if not config_path:
        return {}
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def normalize_sheet_name(value):
    if value is None:
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return value


@dataclass(frozen=True)
class MethodSpec:
    方法ID: str
    方法名称: str
    方法族: str
    方法层级: str
    基础算法: str
    参数: Dict[str, object]
    金额口径: str


class OperationLog:
    def __init__(self) -> None:
        self.rows: List[Dict[str, object]] = []
        self.t0 = time.time()

    def add(self, step, op, result, file="", rows=None):
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

    def to_frame(self):
        return pd.DataFrame(self.rows)


def safe_div(a, b):
    if pd.isna(b) or abs(b) < EPS:
        return np.nan
    return a / b


def read_raw_data(path, log, sheet_name=0, field_map=None):
    field_map = field_map or {c: c for c in STANDARD_COLS}
    actual_to_std = {actual: std for std, actual in field_map.items() if actual and std in STANDARD_COLS}
    wanted_actual = set(actual_to_std.keys())

    df = read_excel_auto(path, sheet_name=sheet_name, usecols=lambda c: c in wanted_actual)
    df = df.rename(columns=actual_to_std)

    for c in OPTIONAL_COLS:
        if c not in df.columns:
            df[c] = pd.NA

    missing = [c for c in CRITICAL_COLS if c not in df.columns]
    if missing:
        configured = {k: v for k, v in field_map.items() if k in missing}
        raise ValueError(f"原始表缺少必需字段: {missing}；当前配置映射: {configured}")

    df = df[[c for c in STANDARD_COLS if c in df.columns]].copy()
    log.add("01读取", "按配置读取原始Excel必要字段", f"读取完成，工作表={sheet_name}，列数={len(df.columns)}", str(path), len(df))
    return df


def clean_and_map(df, log, customer_filter=None):
    """清洗 + KA/AA 筛选 + 客户简称分组准备"""
    before = len(df)
    df = df.copy()

    df["发货日期"] = pd.to_datetime(df["发货日期"], errors="coerce")
    numeric_cols = ["发货数量", "RMB 未税金额小计", "成本", "利润", "未税单价", "单位成本"]
    for c in numeric_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    for c in ["型号_产品线（新）", "存货名称", "代理商/直供名称", "ERP订单号", "产品线", "产品系列", "型号", "存货编码", "终端客户简称", "终端客户名称_客户类别"]:
        if c in df.columns:
            df[c] = df[c].astype("string").str.strip()

    # ★ KA/AA 筛选
    if customer_filter and customer_filter.get("enabled"):
        filter_field = customer_filter["field"]
        pattern = customer_filter["pattern"]
        if filter_field in df.columns:
            df = df[df[filter_field].str.contains(pattern, na=False)].copy()
            log.add("00筛选", f"按{filter_field}筛选KA/AA客户", f"筛选后行数={len(df)}")
        else:
            log.add("00筛选", f"筛选字段{filter_field}不存在，跳过筛选", f"行数={len(df)}")

    # 基础清洗
    invalid_date = df["发货日期"].isna().sum()
    non_pos_qty = (df["发货数量"].fillna(0) <= 0).sum()
    missing_product = df["存货名称"].isna().sum() + (df["存货名称"].fillna("").astype(str).str.strip() == "").sum()
    missing_cust = df[GROUP_COL].isna().sum() + (df[GROUP_COL].fillna("").astype(str).str.strip() == "").sum()

    df = df[df["发货日期"].notna()].copy()
    df = df[df["发货数量"].fillna(0) > 0].copy()
    df = df[df["存货名称"].notna() & (df["存货名称"].astype(str).str.strip() != "")].copy()
    df = df[df[GROUP_COL].notna() & (df[GROUP_COL].astype(str).str.strip() != "")].copy()
    for c in ["RMB 未税金额小计", "成本", "利润"]:
        df[c] = df[c].fillna(0)

    df["_月"] = df["发货日期"].dt.to_period("M")

    quality = pd.DataFrame([
        {"检查项": "原始行数", "数量": before},
        {"检查项": "发货日期缺失剔除", "数量": int(invalid_date)},
        {"检查项": "发货数量<=0剔除", "数量": int(non_pos_qty)},
        {"检查项": "存货名称缺失剔除", "数量": int(missing_product)},
        {"检查项": "客户简称缺失剔除", "数量": int(missing_cust)},
        {"检查项": "清洗后行数", "数量": len(df)},
        {"检查项": f"清洗后{GROUP_COL}数", "数量": df[GROUP_COL].nunique()},
    ])
    log.add("02清洗", "过滤无效数据并筛选KA/AA客户", f"清洗后行数={len(df)}，客户数={df[GROUP_COL].nunique()}", rows=len(df))

    mapping_diag = pd.DataFrame(columns=["发货日期", "存货名称", GROUP_COL])
    return df, quality, mapping_diag


def build_buckets(df, log):
    latest_month = df["_月"].max()
    bucket_rows: List[Dict[str, object]] = []
    for idx in range(12):
        end = latest_month - (11 - idx) * 3
        start = end - 2
        bucket_rows.append({"数据类型": "历史", "桶序号": idx + 1, "桶编号": f"H{idx+1:02d}", "桶开始月份": str(start), "桶结束月份": str(end), "开始Period": start, "结束Period": end})
    for idx in range(4):
        start = latest_month + idx * 3 + 1
        end = start + 2
        bucket_rows.append({"数据类型": "预测", "桶序号": idx + 1, "桶编号": f"F{idx+1:02d}", "桶开始月份": str(start), "桶结束月份": str(end), "开始Period": start, "结束Period": end})
    buckets = pd.DataFrame(bucket_rows)
    log.add("03分桶", "生成12个历史期和4个预测期", f"最新月份={latest_month}，历史起点={bucket_rows[0]['桶开始月份']}")
    return buckets, latest_month, bucket_rows


def add_bucket_id(df, bucket_rows):
    hist = [r for r in bucket_rows if r["数据类型"] == "历史"]
    df = df.copy()
    df["桶编号"] = pd.NA
    for r in hist:
        mask = df["_月"].between(r["开始Period"], r["结束Period"])
        df.loc[mask, "桶编号"] = r["桶编号"]
    return df[df["桶编号"].notna()].copy()


def aggregate_layers(df_hist, bucket_rows, log):
    dfb = add_bucket_id(df_hist, bucket_rows)

    def agg(group_cols):
        base = dfb.groupby(group_cols, dropna=False).agg(
            销售量=("发货数量", "sum"),
            销售额=("RMB 未税金额小计", "sum"),
            成本额=("成本", "sum"),
            毛利额=("利润", "sum"),
            产品数=("存货名称", "nunique"),
            客户数=("代理商/直供名称", "nunique"),
            订单数=("ERP订单号", "nunique"),
            明细行数=("发货数量", "size"),
        ).reset_index()
        base["毛利率"] = base["毛利额"] / base["销售额"].replace(0, np.nan)
        base["加权销售单价"] = base["销售额"] / base["销售量"].replace(0, np.nan)
        base["加权成本单价"] = base["成本额"] / base["销售量"].replace(0, np.nan)
        return base

    # ★ 客户级 + 客户×产品级（原脚本的产品线级→客户级）
    cust_bucket = agg([GROUP_COL, "桶编号"])
    cp_bucket = agg([GROUP_COL, "存货名称", "桶编号"])

    log.add("04聚合", "生成客户级/客户×产品级历史期聚合", f"客户桶={len(cust_bucket)}，客户×产品桶={len(cp_bucket)}")
    return cust_bucket, cp_bucket, dfb


def complete_panel(df, index_cols, bucket_ids, value_cols):
    keys = df[index_cols].drop_duplicates()
    buckets = pd.DataFrame({"桶编号": bucket_ids})
    panel = keys.merge(buckets, how="cross")
    panel = panel.merge(df[index_cols + ["桶编号"] + value_cols], on=index_cols + ["桶编号"], how="left")
    for c in value_cols:
        panel[c] = panel[c].fillna(0.0)
    return panel


# ====================================================================
# 预测算法 — 原12种 + 新增3种（月度季节指数 / Croston / Ensemble）
# ====================================================================

def _croston(values, horizon, alpha):
    """Croston间歇需求预测。拆分为需求发生和需求量两部分分别平滑。"""
    y = np.asarray(values, dtype=float)
    y = np.nan_to_num(y, nan=0.0, posinf=0.0, neginf=0.0)
    y = np.maximum(y, 0.0)
    if len(y) == 0:
        return np.zeros(horizon)
    # Z: demand size when demand occurs; X: inter-demand interval
    nonzero = y > 0
    if nonzero.sum() == 0:
        return np.zeros(horizon)
    sizes = y[nonzero]
    intervals = np.diff(np.where(nonzero)[0], prepend=-1)
    intervals[0] = 1  # first demand at position 0
    z_sm = sizes[0]
    x_sm = intervals[0]
    for i in range(1, len(sizes)):
        z_sm = alpha * sizes[i] + (1 - alpha) * z_sm
        x_sm = alpha * intervals[i] + (1 - alpha) * x_sm
    rate = z_sm / max(x_sm, 1)
    return np.repeat(rate, horizon)


def _monthly_seasonal(monthly_values, horizon_months, target_months, seasonal_window):
    """月度季节指数法：提取趋势→计算月季节指数→预测。"""
    y = np.asarray(monthly_values, dtype=float)
    y = np.nan_to_num(y, nan=0.0, posinf=0.0, neginf=0.0)
    y = np.maximum(y, 0.0)
    n = len(y)
    if n < 13:
        return np.repeat(np.mean(y[-3:]) if n >= 3 else 0, horizon_months)
    # 12月中心化移动平均提取趋势
    trend = np.full(n, np.nan)
    for i in range(6, n - 6):
        trend[i] = np.mean(y[i - 6:i + 6])
    # 填充首尾
    first_t = next((x for x in trend if not np.isnan(x)), np.mean(y))
    last_t = next((x for x in reversed(trend) if not np.isnan(x)), np.mean(y))
    for i in range(6):
        trend[i] = first_t
        trend[n - 1 - i] = last_t
    trend = np.where(np.isnan(trend), np.mean(y), trend)
    # 每月季节指数
    seasonal = {}
    for m in range(12):
        idx = [i for i in range(n) if i % 12 == m]
        ratios = [y[i] / max(trend[i], EPS) for i in idx if trend[i] > EPS]
        seasonal[m] = np.median(ratios) if ratios else 1.0
    # 去季节化近3月均值
    deseason = np.array([y[i] / max(seasonal[i % 12], EPS) for i in range(n)])
    base = np.mean(deseason[-min(3, n):])
    # 预测
    pred = np.zeros(horizon_months)
    for i in range(horizon_months):
        m = target_months[i] % 12
        pred[i] = base * seasonal.get(m, 1.0)
    return pred


def forecast_values(values, horizon, alg, params):
    y = np.asarray(values, dtype=float)
    y = np.nan_to_num(y, nan=0.0, posinf=0.0, neginf=0.0)
    if len(y) == 0:
        return np.zeros(horizon)
    y = np.maximum(y, 0.0)
    k = int(params.get("窗口", min(len(y), 4)))
    k = max(1, min(k, len(y)))
    tail = y[-k:]

    if alg == "最近值":
        pred = np.repeat(tail[-1], horizon)
    elif alg == "均值":
        pred = np.repeat(tail.mean(), horizon)
    elif alg == "中位数":
        pred = np.repeat(np.median(tail), horizon)
    elif alg == "线性加权均值":
        w = np.arange(1, k + 1, dtype=float)
        pred = np.repeat(float(np.dot(tail, w) / w.sum()), horizon)
    elif alg == "指数加权均值":
        alpha = float(params.get("alpha", 0.5))
        weights = np.array([(1 - alpha) ** i for i in range(k - 1, -1, -1)], dtype=float)
        pred = np.repeat(float(np.dot(tail, weights) / weights.sum()), horizon)
    elif alg == "线性趋势":
        x = np.arange(k, dtype=float)
        if k == 1 or np.allclose(tail, tail[0]):
            pred = np.repeat(tail[-1], horizon)
        else:
            slope, intercept = np.polyfit(x, tail, 1)
            future_x = np.arange(k, k + horizon, dtype=float)
            pred = intercept + slope * future_x
    elif alg == "对数线性趋势":
        x = np.arange(k, dtype=float)
        z = np.log1p(tail)
        if k == 1 or np.allclose(z, z[0]):
            pred = np.repeat(tail[-1], horizon)
        else:
            slope, intercept = np.polyfit(x, z, 1)
            future_x = np.arange(k, k + horizon, dtype=float)
            pred = np.expm1(intercept + slope * future_x)
    elif alg == "漂移":
        if k == 1:
            pred = np.repeat(tail[-1], horizon)
        else:
            drift = (tail[-1] - tail[0]) / max(k - 1, 1)
            pred = np.array([tail[-1] + drift * (i + 1) for i in range(horizon)])
    elif alg == "同比季节":
        seasonal_lag = int(params.get("季节滞后", 4))
        if len(y) >= seasonal_lag:
            base = [y[-seasonal_lag + (i % seasonal_lag)] for i in range(horizon)]
            growth_window = min(len(y), int(params.get("增长窗口", 4)))
            if len(y) >= seasonal_lag + growth_window and y[-seasonal_lag - growth_window:-seasonal_lag].sum() > 0:
                g = y[-growth_window:].sum() / y[-seasonal_lag - growth_window:-seasonal_lag].sum()
                g = min(max(g, 0.5), 1.8)
            else:
                g = 1.0
            pred = np.array(base) * g
        else:
            pred = np.repeat(tail.mean(), horizon)
    elif alg == "衰减趋势":
        if k == 1:
            pred = np.repeat(tail[-1], horizon)
        else:
            slope = (tail[-1] - tail[0]) / max(k - 1, 1)
            damp = float(params.get("衰减", 0.7))
            vals = []
            cur = tail[-1]
            for i in range(horizon):
                cur = cur + slope * (damp ** i)
                vals.append(cur)
            pred = np.array(vals)
    elif alg == "保守增长":
        growth = float(params.get("增长率", 0.03))
        base = tail.mean()
        pred = np.array([base * ((1 + growth) ** (i + 1)) for i in range(horizon)])
    elif alg == "保守衰减":
        decay = float(params.get("衰减率", 0.05))
        base = tail.mean()
        pred = np.array([base * ((1 - decay) ** (i + 1)) for i in range(horizon)])
    # ★★★ 新增3种算法 ★★★
    elif alg == "Croston":
        alpha = float(params.get("alpha", 0.2))
        pred = _croston(y, horizon, alpha)
    elif alg == "月度季节指数":
        # works on quarterly data by treating each quarter-level bucket as a data point
        # we use the y as is and predict horizon quarterly values
        sw = int(params.get("季节窗口", 36))
        n_months = len(y) * 3  # convert quarters to months approximately
        if n_months < 13:
            pred = np.repeat(tail.mean(), horizon)
        else:
            # Expand quarterly to monthly for seasonal decomposition
            monthly = np.repeat(y, 3)[:min(n_months, sw)]
            target_ms = [(len(y) * 3 + i) for i in range(horizon * 3)]
            mpred = _monthly_seasonal(monthly, horizon * 3, target_ms, sw)
            # Aggregate back to quarterly
            pred = np.array([mpred[i * 3:(i + 1) * 3].sum() for i in range(horizon)])
    elif alg == "组合中位数":
        # Ensemble: predict using 5 base methods, take median
        base_algs = ["最近值", "均值", "衰减趋势", "同比季节", "线性趋势"]
        base_params = [{"窗口": 1}, {"窗口": 4}, {"窗口": 6, "衰减": 0.7}, {"窗口": 12, "季节滞后": 4, "增长窗口": 4}, {"窗口": 8}]
        all_preds = []
        for ba, bp in zip(base_algs, base_params):
            all_preds.append(forecast_values(y, horizon, ba, bp))
        stacked = np.column_stack(all_preds)
        pred = np.median(stacked, axis=1)
    else:
        pred = np.repeat(tail.mean(), horizon)

    cap_mult = float(params.get("上限倍数", 3.0))
    cap_base = max(float(np.nanmax(y)), float(np.nanmean(y)) * 2, 1.0)
    return np.nan_to_num(np.maximum(pred, 0.0), nan=0.0, posinf=cap_base * cap_mult, neginf=0.0).clip(0, cap_base * cap_mult)


def build_method_specs():
    """构建完整方法池：原552 + 新增3种算法变体"""
    specs: List[MethodSpec] = []
    # ★ 客户维度层级（简化）
    layers = [
        ("客户", "客户级销量×客户加权价格", "预测客户总销量，按最近加权单价折算金额和成本"),
        ("客户产品", "客户×产品级销量×SKU最近价格", "预测客户×产品销量，用该产品最近单价折算后汇总"),
        ("客户级金额", "客户销售额直接预测", "直接预测客户总销售额"),
        ("客户产品级金额", "客户×产品销售额直接预测", "预测每个客户×产品销售额后汇总"),
    ]
    # 原12种算法
    algs: List[Tuple[str, str, List[Dict[str, object]]]] = [
        ("最近值", "基线", [{"窗口": 1}]),
        ("均值", "基线", [{"窗口": k} for k in [2, 3, 4, 6, 8, 10, 12]]),
        ("中位数", "稳健基线", [{"窗口": k} for k in [3, 4, 6, 8, 12]]),
        ("线性加权均值", "加权移动平均", [{"窗口": k} for k in [3, 4, 6, 8, 12]]),
        ("指数加权均值", "加权移动平均", [{"窗口": k, "alpha": a} for k in [3, 4, 6, 8, 12] for a in [0.2, 0.35, 0.5, 0.7, 0.85]]),
        ("线性趋势", "趋势", [{"窗口": k} for k in [4, 6, 8, 10, 12]]),
        ("对数线性趋势", "趋势", [{"窗口": k} for k in [4, 6, 8, 10, 12]]),
        ("漂移", "趋势", [{"窗口": k} for k in [3, 4, 6, 8, 12]]),
        ("同比季节", "季节", [{"窗口": 12, "季节滞后": 4, "增长窗口": k} for k in [2, 3, 4, 6]]),
        ("衰减趋势", "趋势", [{"窗口": k, "衰减": d} for k in [4, 6, 8, 12] for d in [0.4, 0.7, 0.9]]),
        ("保守增长", "业务规则", [{"窗口": k, "增长率": g} for k in [3, 4, 6] for g in [0.02, 0.05, 0.10]]),
        ("保守衰减", "业务规则", [{"窗口": k, "衰减率": d} for k in [3, 4, 6] for d in [0.02, 0.05, 0.10]]),
        # ★ 新增3种
        ("月度季节指数", "季节", [{"窗口": 12, "季节窗口": sw} for sw in [24, 36]]),
        ("Croston", "稀疏需求", [{"窗口": 12, "alpha": a} for a in [0.1, 0.2, 0.3]]),
        ("组合中位数", "集成", [{"窗口": 8}]),
    ]
    n = 1
    for layer, layer_name, amount_basis in layers:
        for alg, family, param_list in algs:
            for params in param_list:
                param_desc = ",".join(f"{k}={v}" for k, v in params.items())
                specs.append(MethodSpec(
                    方法ID=f"M{n:04d}",
                    方法名称=f"{layer_name}-{alg}({param_desc})",
                    方法族=family,
                    方法层级=layer,
                    基础算法=alg,
                    参数=params,
                    金额口径=amount_basis,
                ))
                n += 1
    return specs


# ★★★ 客户级单价模型（参照HTML模板） ★★★
def compute_customer_prices(cust_panel, bucket_ids, upto_idx):
    """对每条客户，近3月加权均价 × sqrt(近3月/前3月均价)，截断[0.8,1.15]"""
    train_buckets = bucket_ids[:upto_idx]
    prices = {}
    for cust, sub in cust_panel.groupby(GROUP_COL):
        sub = sub[sub["桶编号"].isin(train_buckets)]
        if len(sub) == 0:
            prices[cust] = {"销售单价": 0.0, "成本单价": 0.0, "单价来源": "无数据"}
            continue

        # 取最近桶和更早桶的数据
        recent_n = min(1, len(sub))  # 1个桶≈3个月
        earlier_n = min(2, len(sub) - recent_n) if len(sub) > recent_n else 0

        # 按桶排序
        sub_sorted = sub.sort_values("桶编号", ascending=False)
        recent = sub_sorted.head(recent_n)
        earlier = sub_sorted.iloc[recent_n:recent_n + earlier_n] if earlier_n > 0 else pd.DataFrame()

        qty_recent = recent["销售量"].sum()
        qty_earlier = earlier["销售量"].sum() if len(earlier) > 0 else 0

        if qty_recent > 0:
            asp_recent = recent["销售额"].sum() / qty_recent
            cost_recent = recent["成本额"].sum() / qty_recent
            source = "客户近1桶"
        else:
            # 回退到全训练期
            qty_all = sub["销售量"].sum()
            asp_recent = sub["销售额"].sum() / qty_all if qty_all > 0 else 0.0
            cost_recent = sub["成本额"].sum() / qty_all if qty_all > 0 else 0.0
            source = "客户全训练期回退"

        # 趋势因子：sqrt(近3月/前3月)
        if qty_earlier > 0 and qty_recent > 0:
            asp_earlier = earlier["销售额"].sum() / qty_earlier
            if asp_earlier > 0 and asp_recent > 0:
                ratio = asp_recent / asp_earlier
                factor = math.sqrt(max(ratio, 0.01))
                factor = min(max(factor, 0.8), 1.15)
            else:
                factor = 1.0
        else:
            factor = 1.0

        final_asp = asp_recent * factor
        final_cost = cost_recent * factor

        prices[cust] = {
            "销售单价": final_asp,
            "成本单价": final_cost,
            "单价来源": f"{source}×趋势因子{factor:.3f}",
        }
    return prices


def prepare_runtime_context(cust_panel, cp_panel, bucket_ids):
    """预计算序列和价格缓存（客户级 + 客户×产品级）"""
    ctx = {"cust_series": {}, "cp_series": {}, "prices": {}}

    for cust, sub in cust_panel.groupby(GROUP_COL):
        s = sub.set_index("桶编号").reindex(bucket_ids).fillna(0)
        ctx["cust_series"][cust] = {
            "销售量": s["销售量"].to_numpy(float),
            "销售额": s["销售额"].to_numpy(float),
            "成本额": s["成本额"].to_numpy(float),
            "毛利额": s["毛利额"].to_numpy(float),
        }

    for (cust, prod), sub in cp_panel.groupby([GROUP_COL, "存货名称"]):
        s = sub.set_index("桶编号").reindex(bucket_ids).fillna(0)
        ctx["cp_series"].setdefault(cust, []).append({
            "产品": prod,
            "销售量": s["销售量"].to_numpy(float),
            "销售额": s["销售额"].to_numpy(float),
            "成本额": s["成本额"].to_numpy(float),
        })

    for upto_idx in range(6, len(bucket_ids) + 1):
        ctx["prices"][upto_idx] = compute_customer_prices(cust_panel, bucket_ids, upto_idx)

    return ctx


def compute_prediction_for_method(spec, cust, horizon, upto_idx, bucket_ids, ctx):
    """为指定客户和方法计算预测（金额，销量，成本额）"""
    cs = ctx["cust_series"].get(cust, None)
    prices_at = ctx["prices"].get(upto_idx, {})
    price_info = prices_at.get(cust, {"销售单价": 0.0, "成本单价": 0.0})

    if cs is None:
        return np.zeros(horizon), np.zeros(horizon), np.zeros(horizon)

    if spec.方法层级 == "客户":
        qty_pred = forecast_values(cs["销售量"][:upto_idx], horizon, spec.基础算法, spec.参数)
        amount_pred = qty_pred * price_info["销售单价"]
        cost_pred = qty_pred * price_info["成本单价"]
        return amount_pred, qty_pred, cost_pred

    if spec.方法层级 == "客户级金额":
        amount_pred = forecast_values(cs["销售额"][:upto_idx], horizon, spec.基础算法, spec.参数)
        qty_pred = forecast_values(cs["销售量"][:upto_idx], horizon, spec.基础算法, spec.参数)
        cost_pred = qty_pred * price_info["成本单价"]
        return amount_pred, qty_pred, cost_pred

    if spec.方法层级 in ["客户产品", "客户产品级金额"]:
        amount_total = np.zeros(horizon)
        qty_total = np.zeros(horizon)
        cost_total = np.zeros(horizon)
        for item in ctx["cp_series"].get(cust, []):
            qty_pred = forecast_values(item["销售量"][:upto_idx], horizon, spec.基础算法, spec.参数)
            # 产品级价格：用该产品最近桶的实际加权价
            prod_price = item["销售额"][:upto_idx].sum() / max(item["销售量"][:upto_idx].sum(), EPS) if item["销售量"][:upto_idx].sum() > 0 else price_info["销售单价"]
            prod_cost = item["成本额"][:upto_idx].sum() / max(item["销售量"][:upto_idx].sum(), EPS) if item["销售量"][:upto_idx].sum() > 0 else price_info["成本单价"]
            if spec.方法层级 == "客户产品级金额":
                amount_pred = forecast_values(item["销售额"][:upto_idx], horizon, spec.基础算法, spec.参数)
            else:
                amount_pred = qty_pred * prod_price
            amount_total += amount_pred
            qty_total += qty_pred
            cost_total += qty_pred * prod_cost
        return amount_total, qty_total, cost_total

    raise ValueError(f"未知方法层级: {spec.方法层级}")


def metric_rows(actual_amount, pred_amount, actual_qty, pred_qty, actual_profit, pred_profit, actual_margin, pred_margin):
    amount_err = pred_amount - actual_amount
    qty_err = pred_qty - actual_qty
    profit_err = pred_profit - actual_profit
    return {
        "销售额误差": amount_err,
        "销售额绝对误差": abs(amount_err),
        "销售额APE": abs(amount_err) / max(abs(actual_amount), EPS),
        "销量误差": qty_err,
        "销量绝对误差": abs(qty_err),
        "销量APE": abs(qty_err) / max(abs(actual_qty), EPS),
        "毛利额误差": profit_err,
        "毛利额绝对误差": abs(profit_err),
        "毛利额APE": abs(profit_err) / max(abs(actual_profit), EPS),
        "毛利率绝对误差": abs(pred_margin - actual_margin) if np.isfinite(pred_margin) and np.isfinite(actual_margin) else np.nan,
    }


def backtest_and_select(specs, cust_panel, cp_panel, bucket_ids, ctx, log):
    custs = sorted(cust_panel[GROUP_COL].dropna().unique())
    detail_rows: List[Dict[str, object]] = []
    rank_rows: List[Dict[str, object]] = []
    folds = list(range(6, 12))
    total = len(custs) * len(specs)
    done = 0

    for cust in custs:
        actual_cust = cust_panel[cust_panel[GROUP_COL] == cust].set_index("桶编号").reindex(bucket_ids).fillna(0)
        for spec in specs:
            method_detail_start = len(detail_rows)
            for test_idx in folds:
                pred_amount, pred_qty, pred_cost = compute_prediction_for_method(spec, cust, 1, test_idx, bucket_ids, ctx)
                actual = actual_cust.iloc[test_idx]
                actual_amount = float(actual["销售额"])
                actual_qty = float(actual["销售量"])
                actual_profit = float(actual["毛利额"])
                actual_margin = safe_div(actual_profit, actual_amount)
                pa = float(pred_amount[0])
                pq = float(pred_qty[0])
                pcost = float(pred_cost[0])
                pprofit = pa - pcost
                pmargin = safe_div(pprofit, pa)
                m = metric_rows(actual_amount, pa, actual_qty, pq, actual_profit, pprofit, actual_margin, pmargin)
                detail_rows.append({
                    "方法ID": spec.方法ID,
                    "方法名称": spec.方法名称,
                    "方法族": spec.方法族,
                    "方法层级": spec.方法层级,
                    "金额口径": spec.金额口径,
                    "客户": cust,
                    "回测折次": f"BT{test_idx - 5:02d}",
                    "训练开始桶": bucket_ids[0],
                    "训练结束桶": bucket_ids[test_idx - 1],
                    "验证桶": bucket_ids[test_idx],
                    "实际销售额": actual_amount,
                    "预测销售额": pa,
                    "实际销售量": actual_qty,
                    "预测销售量": pq,
                    "实际毛利额": actual_profit,
                    "预测毛利额": pprofit,
                    "实际毛利率": actual_margin,
                    "预测毛利率": pmargin,
                    **m,
                })
            part = pd.DataFrame(detail_rows[method_detail_start:])
            actual_amount_sum = part["实际销售额"].abs().sum()
            actual_qty_sum = part["实际销售量"].abs().sum()
            actual_profit_sum = part["实际毛利额"].abs().sum()
            amount_wape = part["销售额绝对误差"].sum() / max(actual_amount_sum, EPS)
            qty_wape = part["销量绝对误差"].sum() / max(actual_qty_sum, EPS)
            profit_wape = part["毛利额绝对误差"].sum() / max(actual_profit_sum, EPS)
            amount_mape = min(part["销售额APE"].replace([np.inf, -np.inf], np.nan).dropna().mean(), 5.0)
            bias = part["销售额误差"].sum() / max(part["实际销售额"].sum(), EPS)
            margin_mae = part["毛利率绝对误差"].replace([np.inf, -np.inf], np.nan).dropna().mean()
            margin_mae_norm = 0 if pd.isna(margin_mae) else min(margin_mae, 1.0)
            stability = part["销售额APE"].replace([np.inf, -np.inf], np.nan).dropna().std()
            if pd.isna(stability):
                stability = 0.0
            score = 0.50 * amount_wape + 0.15 * amount_mape + 0.10 * abs(bias) + 0.10 * qty_wape + 0.10 * profit_wape + 0.05 * margin_mae_norm
            rank_rows.append({
                "客户": cust,
                "方法ID": spec.方法ID,
                "方法名称": spec.方法名称,
                "方法族": spec.方法族,
                "方法层级": spec.方法层级,
                "金额口径": spec.金额口径,
                "回测次数": len(part),
                "综合评分": score,
                "销售额WAPE": amount_wape,
                "销售额MAPE": amount_mape,
                "销售额偏差率": bias,
                "销量WAPE": qty_wape,
                "毛利额WAPE": profit_wape,
                "毛利率MAE": margin_mae,
                "稳定性评分": stability,
            })
            done += 1
        print(f"  回测完成: {cust} ({done}/{total})")

    detail = pd.DataFrame(detail_rows)
    ranking = pd.DataFrame(rank_rows)
    ranking = ranking.sort_values(["客户", "综合评分", "销售额WAPE", "稳定性评分"]).copy()
    ranking["排名"] = ranking.groupby("客户").cumcount() + 1
    ranking["是否最终选中"] = np.where(ranking["排名"] == 1, "是", "否")
    ranking["选择原因"] = np.where(ranking["排名"] == 1, "综合评分最低，销售额优先", "未选中")
    cols = ["客户", "排名"] + [c for c in ranking.columns if c not in ["客户", "排名"]]
    ranking = ranking[cols]
    log.add("05回测", "完成全部候选方法滚动回测并生成排行榜", f"方法数={len(specs)}，回测明细={len(detail)}，排行榜={len(ranking)}", rows=len(detail))
    return detail, ranking


def build_final_forecast(ranking, buckets, cust_panel, cp_panel, specs, bucket_ids, ctx, log):
    hist_meta = buckets[buckets["数据类型"] == "历史"][["数据类型", "桶编号", "桶开始月份", "桶结束月份"]]
    future_meta = buckets[buckets["数据类型"] == "预测"][["数据类型", "桶编号", "桶开始月份", "桶结束月份"]]
    hist = cust_panel.merge(hist_meta, on="桶编号", how="left")
    hist = hist.rename(columns={GROUP_COL: "客户"})
    hist["预测方法"] = ""
    hist["方法层级"] = ""
    hist["金额口径"] = "历史实际"
    metric_cols = ["综合评分", "销售额WAPE", "销售额MAPE", "销售额偏差率", "销量WAPE", "毛利额WAPE", "毛利率MAE"]
    for c in metric_cols:
        hist[c] = np.nan
    hist["预测置信等级"] = "历史实际"
    hist["备注"] = "历史实际"

    future_rows = []
    selected = ranking[ranking["是否最终选中"] == "是"].copy()
    for _, row in selected.iterrows():
        cust = row["客户"]
        spec = specs[row["方法ID"]]
        pred_amount, pred_qty, pred_cost = compute_prediction_for_method(spec, cust, 4, len(bucket_ids), bucket_ids, ctx)
        for i in range(4):
            meta = future_meta.iloc[i]
            amount = float(pred_amount[i])
            qty = float(pred_qty[i])
            cost = float(pred_cost[i])
            profit = amount - cost
            margin = safe_div(profit, amount)
            conf = "高" if row["销售额WAPE"] <= 0.2 else ("中" if row["销售额WAPE"] <= 0.45 else "低")
            future_rows.append({
                "客户": cust,
                "桶编号": meta["桶编号"],
                "销售量": qty,
                "销售额": amount,
                "成本额": cost,
                "毛利额": profit,
                "产品数": np.nan,
                "客户数": np.nan,
                "订单数": np.nan,
                "明细行数": np.nan,
                "毛利率": margin,
                "加权销售单价": safe_div(amount, qty),
                "加权成本单价": safe_div(cost, qty),
                "数据类型": "预测",
                "桶开始月份": meta["桶开始月份"],
                "桶结束月份": meta["桶结束月份"],
                "预测方法": row["方法名称"],
                "方法层级": row["方法层级"],
                "金额口径": row["金额口径"],
                "综合评分": row["综合评分"],
                "销售额WAPE": row["销售额WAPE"],
                "销售额MAPE": row["销售额MAPE"],
                "销售额偏差率": row["销售额偏差率"],
                "销量WAPE": row["销量WAPE"],
                "毛利额WAPE": row["毛利额WAPE"],
                "毛利率MAE": row["毛利率MAE"],
                "预测置信等级": conf,
                "备注": "未来预测；最终方法按客户独立选择",
            })
    future = pd.DataFrame(future_rows)

    for prefix, value_col, err_col in [
        ("销售额", "销售额", "销售额WAPE"),
        ("毛利额", "毛利额", "毛利额WAPE"),
        ("销售量", "销售量", "销量WAPE"),
    ]:
        future[f"{prefix}预测下限"] = np.nan
        future[f"{prefix}预测上限"] = np.nan
        for idx, r in future.iterrows():
            wape = r.get(err_col, r.get("销售额WAPE", 0.3))
            if pd.isna(wape):
                wape = 0.3
            band = min(max(float(wape), 0.05), 0.8)
            val = float(r[value_col]) if pd.notna(r[value_col]) else 0.0
            future.at[idx, f"{prefix}预测下限"] = max(0.0, val * (1 - band))
            future.at[idx, f"{prefix}预测上限"] = val * (1 + band)
    for c in ["销售额预测下限", "销售额预测上限", "毛利额预测下限", "毛利额预测上限", "销售量预测下限", "销售量预测上限"]:
        hist[c] = np.nan

    final_cols = [
        "数据类型", "桶编号", "桶开始月份", "桶结束月份", "客户",
        "销售额", "毛利额", "毛利率", "销售量", "成本额", "加权销售单价", "加权成本单价",
        "销售额预测下限", "销售额预测上限", "毛利额预测下限", "毛利额预测上限", "销售量预测下限", "销售量预测上限",
        "产品数", "客户数", "订单数", "明细行数", "预测方法", "方法层级", "金额口径",
        "综合评分", "销售额WAPE", "销售额MAPE", "销售额偏差率", "销量WAPE", "毛利额WAPE", "毛利率MAE",
        "预测置信等级", "备注",
    ]
    combined = pd.concat([hist[final_cols], future[final_cols]], ignore_index=True)
    combined["桶排序"] = combined["桶编号"].str.extract(r"(\d+)").astype(int)
    combined["类型排序"] = combined["数据类型"].map({"历史": 0, "预测": 1})
    combined = combined.sort_values(["客户", "类型排序", "桶排序"]).drop(columns=["类型排序", "桶排序"])
    log.add("06预测", "生成历史12期+未来4期合并主表", f"合并主表行数={len(combined)}", rows=len(combined))
    return combined


def build_customer_product_contrib(cp_panel, cust_panel, bucket_ids, log):
    """客户×产品级贡献表"""
    # 简单版：产品在客户中的销售额占比
    contrib = cp_panel.copy()
    cust_amount = contrib.groupby([GROUP_COL, "桶编号"])["销售额"].sum().rename("客户销售额").reset_index()
    contrib = contrib.merge(cust_amount, on=[GROUP_COL, "桶编号"], how="left")
    contrib["对客户销售额贡献率"] = contrib["销售额"] / contrib["客户销售额"].replace(0, np.nan)
    contrib = contrib.rename(columns={GROUP_COL: "客户", "存货名称": "产品"})
    log.add("07贡献", "生成客户×产品级历史贡献表", f"行数={len(contrib)}", rows=len(contrib))
    return contrib


def write_chart_html(combined, output_path, log):
    """生成基于Chart.js的交互式HTML图表（客户维度，内嵌库文件，离线可用）。"""
    chart_df = combined.copy()
    chart_df["期间"] = chart_df["桶开始月份"].astype(str) + "~" + chart_df["桶结束月份"].astype(str)
    records = chart_df.replace({np.nan: None}).to_dict(orient="records")
    customers = sorted(chart_df["客户"].dropna().unique().tolist())
    data_json = json.dumps(records, ensure_ascii=False)
    lines_json = json.dumps(customers, ensure_ascii=False)

    chartjs_path = Path(__file__).parent / "chartjs.min.js"
    if chartjs_path.exists():
        chartjs_code = chartjs_path.read_text(encoding="utf-8")
    else:
        chartjs_code = "console.error('Chart.js not found');"
        log.add("09图表", "警告：Chart.js库文件不存在", f"路径={chartjs_path}")

    template_path = Path(__file__).parent / "chart_template.html"
    if template_path.exists():
        html = template_path.read_text(encoding="utf-8")
    else:
        raise FileNotFoundError(f"图表模板文件不存在: {template_path}")

    html = html.replace("__CHARTJS_LIBRARY__", chartjs_code)
    html = html.replace("__DATA_JSON__", data_json)
    html = html.replace("__LINES_JSON__", lines_json)

    output_path.write_text(html, encoding="utf-8")
    log.add("09图表", "生成Chart.js交互式HTML客户预测图表", f"文件={output_path}")


def export_outputs(output_dir, combined, detail, ranking, product_contrib, diagnostics, mapping_diag, methods, log):
    output_dir.mkdir(parents=True, exist_ok=True)
    files = {
        "主表CSV": output_dir / "客户季度历史与预测.csv",
        "回测明细CSV": output_dir / "预测方法回测明细.csv",
        "排行榜CSV": output_dir / "预测方法排行榜.csv",
        "产品贡献CSV": output_dir / "产品级价格与预测贡献.csv",
        "诊断CSV": output_dir / "数据质量与映射诊断.csv",
        "方法清单CSV": output_dir / "候选预测方法清单.csv",
        "操作日志CSV": output_dir / "操作日志.csv",
        "HTML图表": output_dir / "客户季度预测图表.html",
        "Excel": output_dir / "客户季度历史与预测_含方法回测.xlsx",
    }
    method_df = pd.DataFrame([{
        "方法ID": m.方法ID, "方法名称": m.方法名称, "方法族": m.方法族, "方法层级": m.方法层级,
        "基础算法": m.基础算法, "参数": str(m.参数), "金额口径": m.金额口径,
    } for m in methods])
    diag_all = pd.concat([diagnostics.assign(诊断类型="数据质量"), mapping_diag.assign(诊断类型="映射")], ignore_index=True, sort=False)

    combined.to_csv(files["主表CSV"], index=False, encoding="utf-8-sig")
    detail.to_csv(files["回测明细CSV"], index=False, encoding="utf-8-sig")
    ranking.to_csv(files["排行榜CSV"], index=False, encoding="utf-8-sig")
    product_contrib.to_csv(files["产品贡献CSV"], index=False, encoding="utf-8-sig")
    diag_all.to_csv(files["诊断CSV"], index=False, encoding="utf-8-sig")
    method_df.to_csv(files["方法清单CSV"], index=False, encoding="utf-8-sig")
    log.to_frame().to_csv(files["操作日志CSV"], index=False, encoding="utf-8-sig")

    with pd.ExcelWriter(files["Excel"], engine="openpyxl") as writer:
        combined.to_excel(writer, sheet_name="历史预测合并主表", index=False)
        ranking.to_excel(writer, sheet_name="预测方法排行榜", index=False)
        detail.to_excel(writer, sheet_name="预测方法回测明细", index=False)
        product_contrib.to_excel(writer, sheet_name="产品级价格贡献", index=False)
        diag_all.to_excel(writer, sheet_name="数据质量与映射诊断", index=False)
        method_df.to_excel(writer, sheet_name="候选方法清单", index=False)
        log.to_frame().to_excel(writer, sheet_name="操作日志", index=False)

    write_chart_html(combined, files["HTML图表"], log)
    log.to_frame().to_csv(files["操作日志CSV"], index=False, encoding="utf-8-sig")
    log.add("08导出", "导出CSV、Excel和HTML结果文件", f"输出目录={output_dir}")
    return files


def run(data_path=RAW_FILE, output_dir=OUTPUT_DIR, fast=False, sheet_name=0, field_map=None, customer_filter=None, method_lock=None):
    log = OperationLog()
    df_raw = read_raw_data(data_path, log, sheet_name=sheet_name, field_map=field_map)
    df, diagnostics, mapping_diag = clean_and_map(df_raw, log, customer_filter=customer_filter)
    buckets, latest_month, bucket_rows = build_buckets(df, log)
    hist_start = bucket_rows[0]["开始Period"]
    hist_end = bucket_rows[11]["结束Period"]
    df_hist = df[df["_月"].between(hist_start, hist_end)].copy()

    cust_bucket, cp_bucket, dfb = aggregate_layers(df_hist, bucket_rows, log)
    bucket_ids = [f"H{i:02d}" for i in range(1, 13)]
    value_cols = ["销售量", "销售额", "成本额", "毛利额", "产品数", "客户数", "订单数", "明细行数", "毛利率", "加权销售单价", "加权成本单价"]
    cust_panel = complete_panel(cust_bucket, [GROUP_COL], bucket_ids, value_cols)
    cp_panel = complete_panel(cp_bucket, [GROUP_COL, "存货名称"], bucket_ids, value_cols)

    ctx = prepare_runtime_context(cust_panel, cp_panel, bucket_ids)
    log.add("05回测", "预计算客户/客户×产品序列与客户级价格缓存", "完成运行时缓存")

    methods = build_method_specs()
    if method_lock:
        log.add("05回测", "生成候选预测方法池", f"方法数={len(methods)}；锁定模式将跳过全量回测")
        detail = pd.DataFrame(columns=[
            "方法ID", "方法名称", "方法族", "方法层级", "金额口径", "客户", "回测折次",
            "训练开始桶", "训练结束桶", "验证桶", "实际销售额", "预测销售额", "实际销售量", "预测销售量",
            "实际毛利额", "预测毛利额", "实际毛利率", "预测毛利率", "销售额误差", "销售额绝对误差",
            "销售额APE", "销量误差", "销量绝对误差", "销量APE", "毛利额误差", "毛利额绝对误差", "毛利额APE", "毛利率绝对误差",
        ])
    else:
        if fast:
            methods = methods[:150]
            log.add("05回测", "启用fast模式限制候选方法数", f"方法数={len(methods)}")
        else:
            log.add("05回测", "生成候选预测方法池", f"方法数={len(methods)}")
        detail, ranking = backtest_and_select(methods, cust_panel, cp_panel, bucket_ids, ctx, log)
    method_map = {m.方法ID: m for m in methods}
    combined = build_final_forecast(ranking, buckets, cust_panel, cp_panel, method_map, bucket_ids, ctx, log)
    product_contrib = build_customer_product_contrib(cp_panel, cust_panel, bucket_ids, log)
    files = export_outputs(output_dir, combined, detail, ranking, product_contrib, diagnostics, mapping_diag, methods, log)
    return files


def parse_args():
    parser = argparse.ArgumentParser(description="客户维度滚动季度历史分析与未来4期预测（KA/AA客户）")
    parser.add_argument("--config", help="JSON配置文件路径")
    parser.add_argument("--data", default=None, help="原始出货明细Excel路径")
    parser.add_argument("--sheet", default=None, help="工作表名或序号")
    parser.add_argument("--output", default=None, help="输出目录")
    parser.add_argument("--method-lock", default=None, help="使用既有排行榜锁定方法")
    parser.add_argument("--fast", action="store_true", help="快速模式：仅运行前150个候选方法")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    cfg = load_config(resolve_path(args.config, Path()) if args.config else None)
    data_path = resolve_path(args.data or cfg.get("data_path"), RAW_FILE)
    output_dir = resolve_path(args.output or cfg.get("output_dir"), OUTPUT_DIR)
    sheet_name = normalize_sheet_name(args.sheet if args.sheet is not None else cfg.get("sheet_name", 0))
    field_map = cfg.get("field_map")
    customer_filter = cfg.get("customer_filter")
    method_lock = resolve_path(args.method_lock, Path()) if args.method_lock else None
    files = run(data_path, output_dir, fast=args.fast, sheet_name=sheet_name, field_map=field_map,
                customer_filter=customer_filter, method_lock=method_lock)
    print("\n输出文件:")
    for name, path in files.items():
        print(f"  {name}: {path}")
