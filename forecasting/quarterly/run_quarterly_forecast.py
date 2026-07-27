# -*- coding: utf-8 -*-
"""产品线滚动季度历史分析与预测。

直接读取原始出货明细 Excel，生成：
- 产品线历史12个3个月桶 + 未来4个3个月桶的合并长表
- 每一种候选方法的回测明细
- 每条产品线的方法排行榜与最终选择
- 数据质量、产品线映射、产品级价格诊断

设计重点：
- 不依赖 silver/gold 中间层
- 输出字段使用中文
- 产品线缺失优先按“存货名称”历史众数回填
- 预测方法按销售额表现为主进行综合评分
- 销售额预测优先使用产品/SKU级最近桶加权单价，避免产品线均价掩盖结构差异
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
except Exception:  # pragma: no cover - standalone fallback
    def read_excel_auto(path, sheet_name=0, usecols=None, **kwargs):
        """Standalone fallback: prefer calamine for speed, handle callable usecols."""
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
OUTPUT_DIR = PROJECT_ROOT / "output" / "quarterly_forecast"

REQUIRED_COLS = [
    "发货日期", "型号_产品线（新）", "存货名称", "发货数量", "RMB 未税金额小计",
    "成本", "利润", "未税单价", "单位成本", "终端客户简称", "ERP订单号",
    "产品线", "产品系列", "型号", "存货编码", "实际终端客户", "终端名称",
    "代理商/直供名称", "终端客户名称_客户类别",
]

STANDARD_COLS = REQUIRED_COLS.copy()
OPTIONAL_COLS = ["未税单价", "单位成本", "产品线", "产品系列", "型号", "存货编码", "实际终端客户", "终端名称", "代理商/直供名称", "终端客户名称_客户类别"]
CRITICAL_COLS = ["发货日期", "型号_产品线（新）", "存货名称", "发货数量", "RMB 未税金额小计", "成本", "利润", "终端客户简称", "ERP订单号"]
EPS = 1e-9


def resolve_path(path_value: str | Path | None, default: Path) -> Path:
    if not path_value:
        return default
    p = Path(path_value)
    return p if p.is_absolute() else PROJECT_ROOT / p


def load_config(config_path: Optional[Path]) -> Dict[str, object]:
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

    def add(self, 步骤: str, 操作: str, 结果: str, 文件: str = "", 行数: Optional[int] = None) -> None:
        self.rows.append({
            "时间": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
            "耗时秒": round(time.time() - self.t0, 2),
            "步骤": 步骤,
            "操作": 操作,
            "结果": 结果,
            "文件": 文件,
            "行数": 行数,
        })
        print(f"[{步骤}] {操作} -> {结果}")

    def to_frame(self) -> pd.DataFrame:
        return pd.DataFrame(self.rows)


def safe_div(a, b):
    if pd.isna(b) or abs(b) < EPS:
        return np.nan
    return a / b


def weighted_mode(s: pd.Series) -> object:
    s = s.dropna()
    s = s[s.astype(str).str.strip() != ""]
    if len(s) == 0:
        return np.nan
    return s.value_counts().index[0]


def read_raw_data(path: Path, log: OperationLog, sheet_name=0, field_map: Optional[Dict[str, str]] = None) -> pd.DataFrame:
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


def clean_and_map(df: pd.DataFrame, log: OperationLog) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    before = len(df)
    df = df.copy()

    df["发货日期"] = pd.to_datetime(df["发货日期"], errors="coerce")
    numeric_cols = ["发货数量", "RMB 未税金额小计", "成本", "利润", "未税单价", "单位成本"]
    for c in numeric_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    for c in ["型号_产品线（新）", "存货名称", "终端客户简称", "ERP订单号", "产品线", "产品系列", "型号", "存货编码", "代理商/直供名称", "实际终端客户", "终端客户名称_客户类别"]:
        if c in df.columns:
            df[c] = df[c].astype("string").str.strip()

    df["_原始产品线"] = df["型号_产品线（新）"]
    invalid_date = df["发货日期"].isna().sum()
    non_pos_qty = (df["发货数量"].fillna(0) <= 0).sum()
    missing_product = df["存货名称"].isna().sum() + (df["存货名称"].fillna("").astype(str).str.strip() == "").sum()

    df = df[df["发货日期"].notna()].copy()
    df = df[df["发货数量"].fillna(0) > 0].copy()
    df = df[df["存货名称"].notna() & (df["存货名称"].astype(str).str.strip() != "")].copy()
    for c in ["RMB 未税金额小计", "成本", "利润"]:
        df[c] = df[c].fillna(0)

    non_empty = df[df["型号_产品线（新）"].notna() & (df["型号_产品线（新）"].astype(str).str.strip() != "")]
    product_line_counts = (
        non_empty.groupby(["存货名称", "型号_产品线（新）"])
        .size().reset_index(name="出现次数")
        .sort_values(["存货名称", "出现次数"], ascending=[True, False])
    )
    product_map = product_line_counts.drop_duplicates("存货名称").set_index("存货名称")["型号_产品线（新）"].to_dict()

    conflict = product_line_counts.groupby("存货名称").agg(
        候选产品线数=("型号_产品线（新）", "nunique"),
        候选明细=("型号_产品线（新）", lambda x: " | ".join(x.astype(str).tolist()[:10])),
        出现次数明细=("出现次数", lambda x: " | ".join(map(str, x.tolist()[:10]))),
    ).reset_index()
    conflict = conflict[conflict["候选产品线数"] > 1].copy()

    missing_mask = df["型号_产品线（新）"].isna() | (df["型号_产品线（新）"].astype(str).str.strip() == "")
    df["产品线回填来源"] = "原始非空"
    df.loc[missing_mask, "型号_产品线（新）"] = df.loc[missing_mask, "存货名称"].map(product_map)
    df.loc[missing_mask & df["型号_产品线（新）"].notna(), "产品线回填来源"] = "按存货名称回填"
    still_missing = df["型号_产品线（新）"].isna() | (df["型号_产品线（新）"].astype(str).str.strip() == "")
    df.loc[still_missing, "型号_产品线（新）"] = "未分类"
    df.loc[still_missing, "产品线回填来源"] = "未分类兜底"

    df["_月"] = df["发货日期"].dt.to_period("M")

    # ---- 派生标准客户名称：预测客户名称 ----
    # 优先 终端客户简称 → 代理商/直供名称 → 实际终端客户 → 未知终端客户
    df["预测客户名称_来源"] = "终端客户简称"
    df["预测客户名称"] = df["终端客户简称"].astype(str).str.strip()
    mask_nan = df["预测客户名称"].isna() | (df["预测客户名称"] == "")
    backup1 = df["代理商/直供名称"] if "代理商/直供名称" in df.columns else pd.Series(pd.NA, index=df.index)
    df.loc[mask_nan, "预测客户名称"] = backup1.loc[mask_nan].astype(str).str.strip()
    df.loc[mask_nan & df["预测客户名称"].notna() & (df["预测客户名称"] != ""), "预测客户名称_来源"] = "代理商/直供名称"
    mask_nan2 = df["预测客户名称"].isna() | (df["预测客户名称"] == "")
    backup2 = df["实际终端客户"] if "实际终端客户" in df.columns else pd.Series(pd.NA, index=df.index)
    df.loc[mask_nan2, "预测客户名称"] = backup2.loc[mask_nan2].astype(str).str.strip()
    df.loc[mask_nan2 & df["预测客户名称"].notna() & (df["预测客户名称"] != ""), "预测客户名称_来源"] = "实际终端客户"
    mask_nan3 = df["预测客户名称"].isna() | (df["预测客户名称"] == "")
    df.loc[mask_nan3, "预测客户名称"] = "未知终端客户"
    df.loc[mask_nan3, "预测客户名称_来源"] = "兜底_未知终端客户"

    # ---- 派生标准SKU建模键：SKU预测键 ----
    # 优先 存货编码 → 存货名称
    df["SKU预测键_来源"] = "存货编码"
    df["SKU预测键"] = df["存货编码"].astype(str).str.strip()
    mask_sku = df["SKU预测键"].isna() | (df["SKU预测键"] == "")
    df.loc[mask_sku, "SKU预测键"] = df.loc[mask_sku, "存货名称"].astype(str).str.strip()
    df.loc[mask_sku & df["SKU预测键"].notna() & (df["SKU预测键"] != ""), "SKU预测键_来源"] = "存货名称"

    mapping_diag = df.loc[missing_mask | still_missing, ["发货日期", "存货名称", "_原始产品线", "型号_产品线（新）", "产品线回填来源"]].copy()
    quality = pd.DataFrame([
        {"检查项": "原始行数", "数量": before},
        {"检查项": "发货日期缺失剔除", "数量": int(invalid_date)},
        {"检查项": "发货数量<=0剔除", "数量": int(non_pos_qty)},
        {"检查项": "存货名称缺失剔除", "数量": int(missing_product)},
        {"检查项": "清洗后行数", "数量": len(df)},
        {"检查项": "清洗后产品线数", "数量": df["型号_产品线（新）"].nunique()},
        {"检查项": "产品线缺失回填/兜底行数", "数量": int((mapping_diag["产品线回填来源"] != "原始非空").sum()) if len(mapping_diag) else 0},
        {"检查项": "存货名称多产品线冲突数", "数量": len(conflict)},
    ])
    log.add("02清洗", "过滤非正数量并按存货名称回填产品线", f"清洗后行数={len(df)}，产品线数={df['型号_产品线（新）'].nunique()}", 行数=len(df))
    return df, pd.concat([quality, conflict], ignore_index=True, sort=False), mapping_diag


def build_buckets(df: pd.DataFrame, log: OperationLog) -> Tuple[pd.DataFrame, pd.Period, List[pd.Period], List[Dict[str, object]]]:
    latest_month = df["_月"].max()
    bucket_rows: List[Dict[str, object]] = []
    history_ends = []
    for idx in range(12):
        end = latest_month - (11 - idx) * 3
        start = end - 2
        history_ends.append(end)
        bucket_rows.append({"数据类型": "历史", "桶序号": idx + 1, "桶编号": f"H{idx+1:02d}", "桶开始月份": str(start), "桶结束月份": str(end), "开始Period": start, "结束Period": end})
    for idx in range(4):
        start = latest_month + idx * 3 + 1
        end = start + 2
        bucket_rows.append({"数据类型": "预测", "桶序号": idx + 1, "桶编号": f"F{idx+1:02d}", "桶开始月份": str(start), "桶结束月份": str(end), "开始Period": start, "结束Period": end})
    buckets = pd.DataFrame(bucket_rows)
    log.add("03分桶", "生成12个历史期和4个预测期", f"最新月份={latest_month}，历史起点={bucket_rows[0]['桶开始月份']}")
    return buckets, latest_month, history_ends, bucket_rows


def add_bucket_id(df: pd.DataFrame, bucket_rows: List[Dict[str, object]]) -> pd.DataFrame:
    hist = [r for r in bucket_rows if r["数据类型"] == "历史"]
    df = df.copy()
    df["桶编号"] = pd.NA
    for r in hist:
        mask = df["_月"].between(r["开始Period"], r["结束Period"])
        df.loc[mask, "桶编号"] = r["桶编号"]
    return df[df["桶编号"].notna()].copy()


def aggregate_layers(df_hist: pd.DataFrame, bucket_rows: List[Dict[str, object]], log: OperationLog):
    dfb = add_bucket_id(df_hist, bucket_rows)

    def agg(group_cols: List[str]) -> pd.DataFrame:
        base = dfb.groupby(group_cols, dropna=False).agg(
            销售量=("发货数量", "sum"),
            销售额=("RMB 未税金额小计", "sum"),
            成本额=("成本", "sum"),
            毛利额=("利润", "sum"),
            产品数=("SKU预测键", "nunique"),
            客户数=("预测客户名称", "nunique"),
            订单数=("ERP订单号", "nunique"),
            明细行数=("发货数量", "size"),
        ).reset_index()
        base["毛利率"] = base["毛利额"] / base["销售额"].replace(0, np.nan)
        base["加权销售单价"] = base["销售额"] / base["销售量"].replace(0, np.nan)
        base["加权成本单价"] = base["成本额"] / base["销售量"].replace(0, np.nan)
        return base

    line_bucket = agg(["型号_产品线（新）", "桶编号"])
    # SKU层级：用 SKU预测键 建模，同时保留 存货名称 为展示字段
    product_bucket = agg(["型号_产品线（新）", "SKU预测键", "桶编号"])
    # 回填存货名称展示名
    prod_name_map = dfb.groupby(["型号_产品线（新）", "SKU预测键"])["存货名称"].agg(weighted_mode).reset_index()
    prod_name_map.columns = ["型号_产品线（新）", "SKU预测键", "存货名称_展示"]
    product_bucket = product_bucket.merge(prod_name_map, on=["型号_产品线（新）", "SKU预测键"], how="left")
    # 产品×客户层级：用 预测客户名称 和 SKU预测键
    pc_bucket = agg(["型号_产品线（新）", "SKU预测键", "预测客户名称", "桶编号"])
    # 回填存货名称展示名到pc_bucket
    pc_bucket = pc_bucket.merge(prod_name_map, on=["型号_产品线（新）", "SKU预测键"], how="left")

    log.add("04聚合", "生成产品线/产品(SKU预测键)/产品×客户(预测客户名称)历史期聚合",
            f"产品线桶={len(line_bucket)}，产品桶={len(product_bucket)}，产品客户桶={len(pc_bucket)}")
    return line_bucket, product_bucket, pc_bucket, dfb


def complete_panel(df: pd.DataFrame, index_cols: List[str], bucket_ids: List[str], value_cols: List[str]) -> pd.DataFrame:
    keys = df[index_cols].drop_duplicates()
    buckets = pd.DataFrame({"桶编号": bucket_ids})
    panel = keys.merge(buckets, how="cross")
    panel = panel.merge(df[index_cols + ["桶编号"] + value_cols], on=index_cols + ["桶编号"], how="left")
    for c in value_cols:
        panel[c] = panel[c].fillna(0.0)
    return panel


def make_series_dict(panel: pd.DataFrame, key_cols: List[str], bucket_ids: List[str], value_col: str) -> Dict[Tuple, np.ndarray]:
    out = {}
    for key, g in panel.groupby(key_cols, dropna=False):
        if not isinstance(key, tuple):
            key = (key,)
        s = g.set_index("桶编号").reindex(bucket_ids)[value_col].fillna(0.0).to_numpy(dtype=float)
        out[key] = s
    return out


def forecast_values(values: np.ndarray, horizon: int, alg: str, params: Dict[str, object]) -> np.ndarray:
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
            if len(y) >= seasonal_lag + growth_window and y[-seasonal_lag-growth_window:-seasonal_lag].sum() > 0:
                g = y[-growth_window:].sum() / y[-seasonal_lag-growth_window:-seasonal_lag].sum()
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
    else:
        pred = np.repeat(tail.mean(), horizon)

    cap_mult = float(params.get("上限倍数", 3.0))
    cap_base = max(float(np.nanmax(y)), float(np.nanmean(y)) * 2, 1.0)
    return np.nan_to_num(np.maximum(pred, 0.0), nan=0.0, posinf=cap_base * cap_mult, neginf=0.0).clip(0, cap_base * cap_mult)


def build_method_specs() -> List[MethodSpec]:
    specs: List[MethodSpec] = []
    layers = [
        ("产品线", "产品线级销量×产品组合ASP", "按产品线预测销量，并按最近产品结构拆分到SKU单价后汇总"),
        ("产品", "产品级销量×SKU最近ASP", "预测每个产品销量×该产品最近加权单价后汇总"),
        ("产品×客户", "产品客户级销量×SKU最近ASP", "预测产品×客户销量×该产品最近加权单价后汇总"),
        ("产品级金额", "产品级销售额直接预测", "预测每个产品销售额后汇总"),
        ("产品客户级金额", "产品客户级销售额直接预测", "预测每个产品×客户销售额后汇总"),
        ("产品线级金额", "产品线销售额直接预测", "直接预测产品线销售额"),
    ]
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


def recent_product_prices(product_panel: pd.DataFrame, product_lines: pd.DataFrame, bucket_ids: List[str], upto_idx: int) -> pd.DataFrame:
    """按训练截止桶计算产品级最近加权单价/成本单价，带回退。使用SKU预测键作为产品标识。"""
    train_buckets = bucket_ids[:upto_idx]
    rows = []
    keys = product_panel[["型号_产品线（新）", "SKU预测键"]].drop_duplicates()
    latest_bucket = train_buckets[-1]
    for _, r in keys.iterrows():
        line = r["型号_产品线（新）"]
        sku_key = r["SKU预测键"]
        sub = product_panel[(product_panel["型号_产品线（新）"] == line) & (product_panel["SKU预测键"] == sku_key) & (product_panel["桶编号"].isin(train_buckets))]
        price = cost = np.nan
        source = "无"
        for win in [1, 2, 4, len(train_buckets)]:
            use = train_buckets[-win:]
            ss = sub[sub["桶编号"].isin(use)]
            qty = ss["销售量"].sum()
            if qty > 0:
                price = ss["销售额"].sum() / qty
                cost = ss["成本额"].sum() / qty
                source = f"产品最近{win}桶"
                break
        if not np.isfinite(price) or not np.isfinite(cost):
            line_sub = product_lines[(product_lines["型号_产品线（新）"] == line) & (product_lines["桶编号"].isin(train_buckets[-4:]))]
            qty = line_sub["销售量"].sum()
            if qty > 0:
                price = line_sub["销售额"].sum() / qty
                cost = line_sub["成本额"].sum() / qty
                source = "产品线最近4桶回退"
        if not np.isfinite(price) or not np.isfinite(cost):
            all_sub = product_lines[product_lines["桶编号"].isin(train_buckets[-4:])]
            qty = all_sub["销售量"].sum()
            price = all_sub["销售额"].sum() / qty if qty > 0 else 0
            cost = all_sub["成本额"].sum() / qty if qty > 0 else 0
            source = "全局最近4桶回退"
        rows.append({"型号_产品线（新）": line, "SKU预测键": sku_key, "销售单价": price, "成本单价": cost, "单价来源": source, "训练截止桶": latest_bucket})
    return pd.DataFrame(rows)


def latest_mix(line_product_panel: pd.DataFrame, line: str, train_buckets: List[str], horizon: int, line_qty_pred: np.ndarray, prices: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """产品线级销量预测按最近产品销售结构分摊，再用SKU单价计算金额/成本。使用SKU预测键。"""
    sub = line_product_panel[(line_product_panel["型号_产品线（新）"] == line) & (line_product_panel["桶编号"].isin(train_buckets[-4:]))]
    if sub.empty:
        return line_qty_pred, line_qty_pred * 0, line_qty_pred * 0
    mix = sub.groupby("SKU预测键")["销售量"].sum()
    if mix.sum() <= 0:
        mix = pd.Series(1.0, index=sub["SKU预测键"].drop_duplicates())
    mix = mix / mix.sum()
    pmap = prices[prices["型号_产品线（新）"] == line].set_index("SKU预测键")[["销售单价", "成本单价"]]
    avg_price = 0.0
    avg_cost = 0.0
    for sku_key, share in mix.items():
        if sku_key in pmap.index:
            avg_price += share * float(pmap.loc[sku_key, "销售单价"])
            avg_cost += share * float(pmap.loc[sku_key, "成本单价"])
    amount = line_qty_pred * avg_price
    cost = line_qty_pred * avg_cost
    return line_qty_pred, amount, cost


def prepare_runtime_context(
    line_panel: pd.DataFrame,
    product_panel: pd.DataFrame,
    pc_panel: pd.DataFrame,
    bucket_ids: List[str],
) -> Dict[str, object]:
    """预计算序列和价格，避免回测内反复groupby。"""
    line_series = {}
    for line, sub in line_panel.groupby("型号_产品线（新）", dropna=False):
        s = sub.set_index("桶编号").reindex(bucket_ids).fillna(0)
        line_series[line] = {
            "销售量": s["销售量"].to_numpy(float),
            "销售额": s["销售额"].to_numpy(float),
            "成本额": s["成本额"].to_numpy(float),
            "毛利额": s["毛利额"].to_numpy(float),
        }

    product_series: Dict[str, List[Dict[str, object]]] = {}
    for (line, sku_key), sub in product_panel.groupby(["型号_产品线（新）", "SKU预测键"], dropna=False):
        s = sub.set_index("桶编号").reindex(bucket_ids).fillna(0)
        product_series.setdefault(line, []).append({
            "产品": sku_key,        # SKU预测键 作为建模标识
            "销售量": s["销售量"].to_numpy(float),
            "销售额": s["销售额"].to_numpy(float),
            "成本额": s["成本额"].to_numpy(float),
        })

    pc_series: Dict[str, List[Dict[str, object]]] = {}
    for (line, sku_key, cust_name), sub in pc_panel.groupby(["型号_产品线（新）", "SKU预测键", "预测客户名称"], dropna=False):
        s = sub.set_index("桶编号").reindex(bucket_ids).fillna(0)
        pc_series.setdefault(line, []).append({
            "产品": sku_key,        # SKU预测键 作为建模标识
            "客户": cust_name,       # 预测客户名称
            "销售量": s["销售量"].to_numpy(float),
            "销售额": s["销售额"].to_numpy(float),
            "成本额": s["成本额"].to_numpy(float),
        })

    line_price = {}
    product_price = {}
    product_mix = {}
    for upto_idx in range(6, len(bucket_ids) + 1):
        train_slice = slice(0, upto_idx)
        line_price[upto_idx] = {}
        product_price[upto_idx] = {}
        product_mix[upto_idx] = {}
        for line, seq in line_series.items():
            qty = seq["销售量"][max(0, upto_idx - 4):upto_idx].sum()
            line_price[upto_idx][line] = {
                "销售单价": seq["销售额"][max(0, upto_idx - 4):upto_idx].sum() / qty if qty > 0 else 0.0,
                "成本单价": seq["成本额"][max(0, upto_idx - 4):upto_idx].sum() / qty if qty > 0 else 0.0,
            }
            mix_items = []
            for item in product_series.get(line, []):
                pqty_recent = item["销售量"][max(0, upto_idx - 4):upto_idx].sum()
                pqty_all = item["销售量"][train_slice].sum()
                chosen_qty = pqty_recent if pqty_recent > 0 else pqty_all
                if chosen_qty > 0:
                    recent_qty = item["销售量"][max(0, upto_idx - 1):upto_idx].sum()
                    if recent_qty > 0:
                        price_qty_slice = slice(max(0, upto_idx - 1), upto_idx)
                        source = "产品最近1桶"
                    elif item["销售量"][max(0, upto_idx - 2):upto_idx].sum() > 0:
                        price_qty_slice = slice(max(0, upto_idx - 2), upto_idx)
                        source = "产品最近2桶"
                    elif item["销售量"][max(0, upto_idx - 4):upto_idx].sum() > 0:
                        price_qty_slice = slice(max(0, upto_idx - 4), upto_idx)
                        source = "产品最近4桶"
                    else:
                        price_qty_slice = train_slice
                        source = "产品全训练期"
                    q = item["销售量"][price_qty_slice].sum()
                    if q > 0:
                        price = item["销售额"][price_qty_slice].sum() / q
                        cost = item["成本额"][price_qty_slice].sum() / q
                    else:
                        price = line_price[upto_idx][line]["销售单价"]
                        cost = line_price[upto_idx][line]["成本单价"]
                        source = "产品线回退"
                    product_price[upto_idx][(line, item["产品"])] = {"销售单价": price, "成本单价": cost, "单价来源": source}
                    mix_items.append((item["产品"], chosen_qty))
            total_mix_qty = sum(v for _, v in mix_items)
            product_mix[upto_idx][line] = [(prod, qty / total_mix_qty) for prod, qty in mix_items] if total_mix_qty > 0 else []

    return {
        "line_series": line_series,
        "product_series": product_series,
        "pc_series": pc_series,
        "line_price": line_price,
        "product_price": product_price,
        "product_mix": product_mix,
    }


def compute_prediction_for_method(
    spec: MethodSpec,
    line: str,
    horizon: int,
    upto_idx: int,
    bucket_ids: List[str],
    ctx: Dict[str, object],
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    line_series = ctx["line_series"]
    product_series = ctx["product_series"]
    pc_series = ctx["pc_series"]
    product_price = ctx["product_price"][upto_idx]
    product_mix = ctx["product_mix"][upto_idx]
    line_price = ctx["line_price"][upto_idx]

    if spec.方法层级 == "产品线":
        seq = line_series[line]
        qty_pred = forecast_values(seq["销售量"][:upto_idx], horizon, spec.基础算法, spec.参数)
        avg_price = 0.0
        avg_cost = 0.0
        for prod, share in product_mix.get(line, []):
            p = product_price.get((line, prod), line_price[line])
            avg_price += share * p["销售单价"]
            avg_cost += share * p["成本单价"]
        if avg_price <= 0:
            avg_price = line_price[line]["销售单价"]
            avg_cost = line_price[line]["成本单价"]
        return qty_pred * avg_price, qty_pred, qty_pred * avg_cost

    if spec.方法层级 == "产品线级金额":
        seq = line_series[line]
        amount_pred = forecast_values(seq["销售额"][:upto_idx], horizon, spec.基础算法, spec.参数)
        qty_pred = forecast_values(seq["销售量"][:upto_idx], horizon, spec.基础算法, spec.参数)
        return amount_pred, qty_pred, qty_pred * line_price[line]["成本单价"]

    if spec.方法层级 in ["产品", "产品级金额"]:
        amount_total = np.zeros(horizon)
        qty_total = np.zeros(horizon)
        cost_total = np.zeros(horizon)
        for item in product_series.get(line, []):
            qty_pred = forecast_values(item["销售量"][:upto_idx], horizon, spec.基础算法, spec.参数)
            p = product_price.get((line, item["产品"]), line_price[line])
            if spec.方法层级 == "产品级金额":
                amount_pred = forecast_values(item["销售额"][:upto_idx], horizon, spec.基础算法, spec.参数)
            else:
                amount_pred = qty_pred * p["销售单价"]
            amount_total += amount_pred
            qty_total += qty_pred
            cost_total += qty_pred * p["成本单价"]
        return amount_total, qty_total, cost_total

    if spec.方法层级 in ["产品×客户", "产品客户级金额"]:
        amount_total = np.zeros(horizon)
        qty_total = np.zeros(horizon)
        cost_total = np.zeros(horizon)
        for item in pc_series.get(line, []):
            qty_pred = forecast_values(item["销售量"][:upto_idx], horizon, spec.基础算法, spec.参数)
            p = product_price.get((line, item["产品"]), line_price[line])
            if spec.方法层级 == "产品客户级金额":
                amount_pred = forecast_values(item["销售额"][:upto_idx], horizon, spec.基础算法, spec.参数)
            else:
                amount_pred = qty_pred * p["销售单价"]
            amount_total += amount_pred
            qty_total += qty_pred
            cost_total += qty_pred * p["成本单价"]
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


def backtest_and_select(
    specs: List[MethodSpec],
    line_panel: pd.DataFrame,
    product_panel: pd.DataFrame,
    pc_panel: pd.DataFrame,
    bucket_ids: List[str],
    ctx: Dict[str, object],
    log: OperationLog,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    lines = sorted(line_panel["型号_产品线（新）"].dropna().unique())
    detail_rows: List[Dict[str, object]] = []
    rank_rows: List[Dict[str, object]] = []
    folds = list(range(6, 12))  # H01~H06 -> H07, ... H01~H11 -> H12
    total = len(lines) * len(specs)
    done = 0

    for line in lines:
        actual_line = line_panel[line_panel["型号_产品线（新）"] == line].set_index("桶编号").reindex(bucket_ids).fillna(0)
        for spec in specs:
            method_detail_start = len(detail_rows)
            for test_idx in folds:
                pred_amount, pred_qty, pred_cost = compute_prediction_for_method(
                    spec, line, 1, test_idx, bucket_ids, ctx
                )
                actual = actual_line.iloc[test_idx]
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
                    "产品线": line,
                    "回测折次": f"BT{test_idx-5:02d}",
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
                "产品线": line,
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
        print(f"  回测完成: {line} ({done}/{total})")

    detail = pd.DataFrame(detail_rows)
    ranking = pd.DataFrame(rank_rows)
    ranking = ranking.sort_values(["产品线", "综合评分", "销售额WAPE", "稳定性评分"]).copy()
    ranking["排名"] = ranking.groupby("产品线").cumcount() + 1
    ranking["是否最终选中"] = np.where(ranking["排名"] == 1, "是", "否")
    ranking["选择原因"] = np.where(ranking["排名"] == 1, "综合评分最低，销售额优先", "未选中")
    cols = ["产品线", "排名"] + [c for c in ranking.columns if c not in ["产品线", "排名"]]
    ranking = ranking[cols]
    log.add("05回测", "完成全部候选方法滚动回测并生成排行榜", f"方法数={len(specs)}，回测明细={len(detail)}，排行榜={len(ranking)}", 行数=len(detail))
    return detail, ranking


def load_locked_ranking(lock_path: Path, line_panel: pd.DataFrame, methods: List[MethodSpec], log: OperationLog) -> pd.DataFrame:
    """按既有排行榜锁定方法，跳过全量回测。"""
    locked = pd.read_csv(lock_path)
    if "是否最终选中" in locked.columns:
        selected = locked[locked["是否最终选中"].astype(str) == "是"].copy()
    elif "排名" in locked.columns:
        selected = locked[pd.to_numeric(locked["排名"], errors="coerce") == 1].copy()
    else:
        selected = locked.drop_duplicates("产品线").copy()

    method_map = {m.方法ID: m for m in methods}
    current_lines = sorted(line_panel["型号_产品线（新）"].dropna().unique())
    rows = []
    selected_by_line = selected.set_index("产品线", drop=False)
    default_method = methods[0]
    for line in current_lines:
        if line in selected_by_line.index:
            r = selected_by_line.loc[line]
            if isinstance(r, pd.DataFrame):
                r = r.iloc[0]
            method_id = str(r.get("方法ID", default_method.方法ID))
            if method_id not in method_map:
                method_id = default_method.方法ID
            spec = method_map[method_id]
            row = r.to_dict()
            row.update({
                "产品线": line,
                "排名": 1,
                "方法ID": method_id,
                "方法名称": spec.方法名称,
                "方法族": spec.方法族,
                "方法层级": spec.方法层级,
                "金额口径": spec.金额口径,
                "是否最终选中": "是",
                "选择原因": f"按排行榜锁定: {lock_path.name}",
            })
            for c, v in {"综合评分": np.nan, "销售额WAPE": 0.3, "销售额MAPE": np.nan, "销售额偏差率": 0.0, "销量WAPE": 0.3, "毛利额WAPE": 0.3, "毛利率MAE": np.nan, "稳定性评分": np.nan, "回测次数": 0}.items():
                row.setdefault(c, v)
            rows.append(row)
        else:
            rows.append({
                "产品线": line,
                "排名": 1,
                "方法ID": default_method.方法ID,
                "方法名称": default_method.方法名称,
                "方法族": default_method.方法族,
                "方法层级": default_method.方法层级,
                "金额口径": default_method.金额口径,
                "回测次数": 0,
                "综合评分": np.nan,
                "销售额WAPE": 0.3,
                "销售额MAPE": np.nan,
                "销售额偏差率": 0.0,
                "销量WAPE": 0.3,
                "毛利额WAPE": 0.3,
                "毛利率MAE": np.nan,
                "稳定性评分": np.nan,
                "是否最终选中": "是",
                "选择原因": "锁定排行榜无该产品线，使用默认最近值方法兜底",
            })
    ranking = pd.DataFrame(rows)
    log.add("05锁定", "按既有排行榜锁定预测方法并跳过全量回测", f"锁定文件={lock_path}，产品线={len(ranking)}", 行数=len(ranking))
    return ranking


def build_final_forecast(
    ranking: pd.DataFrame,
    buckets: pd.DataFrame,
    line_panel: pd.DataFrame,
    product_panel: pd.DataFrame,
    pc_panel: pd.DataFrame,
    specs: Dict[str, MethodSpec],
    bucket_ids: List[str],
    ctx: Dict[str, object],
    log: OperationLog,
) -> pd.DataFrame:
    hist_meta = buckets[buckets["数据类型"] == "历史"][["数据类型", "桶编号", "桶开始月份", "桶结束月份"]]
    future_meta = buckets[buckets["数据类型"] == "预测"][["数据类型", "桶编号", "桶开始月份", "桶结束月份"]]
    hist = line_panel.merge(hist_meta, on="桶编号", how="left")
    hist = hist.rename(columns={"型号_产品线（新）": "产品线"})
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
        line = row["产品线"]
        spec = specs[row["方法ID"]]
        pred_amount, pred_qty, pred_cost = compute_prediction_for_method(
            spec, line, 4, len(bucket_ids), bucket_ids, ctx
        )
        for i in range(4):
            meta = future_meta.iloc[i]
            amount = float(pred_amount[i])
            qty = float(pred_qty[i])
            cost = float(pred_cost[i])
            profit = amount - cost
            margin = safe_div(profit, amount)
            conf = "高" if row["销售额WAPE"] <= 0.2 else ("中" if row["销售额WAPE"] <= 0.45 else "低")
            future_rows.append({
                "产品线": line,
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
                "备注": "未来预测；最终方法按产品线独立选择",
            })
    future = pd.DataFrame(future_rows)
    combined_metrics = pd.concat([
        hist[["产品线", "桶编号", "销售额", "毛利额", "销售量"]].assign(数据类型="历史"),
        future[["产品线", "桶编号", "销售额", "毛利额", "销售量"]].assign(数据类型="预测"),
    ], ignore_index=True)

    for prefix, value_col, err_col in [
        ("销售额", "销售额", "销售额WAPE"),
        ("毛利额", "毛利额", "毛利额WAPE"),
        ("销售量", "销售量", "销量WAPE"),
    ]:
        future[f"{prefix}预测下限"] = np.nan
        future[f"{prefix}预测上限"] = np.nan
        for idx, r in future.iterrows():
            wape = r.get(err_col)
            if pd.isna(wape):
                wape = r.get("销售额WAPE", 0.3)
            band = min(max(float(wape), 0.05), 0.8)
            val = float(r[value_col]) if pd.notna(r[value_col]) else 0.0
            future.at[idx, f"{prefix}预测下限"] = max(0.0, val * (1 - band))
            future.at[idx, f"{prefix}预测上限"] = val * (1 + band)
    for c in ["销售额预测下限", "销售额预测上限", "毛利额预测下限", "毛利额预测上限", "销售量预测下限", "销售量预测上限"]:
        hist[c] = np.nan

    final_cols = [
        "数据类型", "桶编号", "桶开始月份", "桶结束月份", "产品线",
        "销售额", "毛利额", "毛利率", "销售量", "成本额", "加权销售单价", "加权成本单价",
        "销售额预测下限", "销售额预测上限", "毛利额预测下限", "毛利额预测上限", "销售量预测下限", "销售量预测上限",
        "产品数", "客户数", "订单数", "明细行数", "预测方法", "方法层级", "金额口径",
        "综合评分", "销售额WAPE", "销售额MAPE", "销售额偏差率", "销量WAPE", "毛利额WAPE", "毛利率MAE",
        "预测置信等级", "备注",
    ]
    combined = pd.concat([hist[final_cols], future[final_cols]], ignore_index=True)
    combined["桶排序"] = combined["桶编号"].str.extract(r"(\d+)").astype(int)
    combined["类型排序"] = combined["数据类型"].map({"历史": 0, "预测": 1})
    combined = combined.sort_values(["产品线", "类型排序", "桶排序"]).drop(columns=["类型排序", "桶排序"])
    log.add("06预测", "生成历史12期+未来4期合并主表", f"合并主表行数={len(combined)}", 行数=len(combined))
    return combined


def build_product_price_contrib(product_panel: pd.DataFrame, line_panel: pd.DataFrame, bucket_ids: List[str], log: OperationLog) -> pd.DataFrame:
    prices = recent_product_prices(product_panel, line_panel, bucket_ids, len(bucket_ids))
    contrib = product_panel.merge(prices, on=["型号_产品线（新）", "SKU预测键"], how="left")
    line_amount = contrib.groupby(["型号_产品线（新）", "桶编号"])["销售额"].sum().rename("产品线销售额").reset_index()
    contrib = contrib.merge(line_amount, on=["型号_产品线（新）", "桶编号"], how="left")
    contrib["对产品线销售额贡献率"] = contrib["销售额"] / contrib["产品线销售额"].replace(0, np.nan)
    contrib = contrib.rename(columns={
        "型号_产品线（新）": "产品线",
        "SKU预测键": "产品建模键",
        "销售单价": "最近桶销售单价",
        "成本单价": "最近桶成本单价",
    })
    log.add("07贡献", "生成产品级(SKU预测键)价格与历史贡献表", f"行数={len(contrib)}", 行数=len(contrib))
    return contrib


def write_chart_html(combined: pd.DataFrame, output_path: Path, log: OperationLog) -> None:
    """生成基于Chart.js的交互式HTML图表（内嵌库文件，离线可用）。"""
    chart_df = combined.copy()
    chart_df["期间"] = chart_df["桶开始月份"].astype(str) + "~" + chart_df["桶结束月份"].astype(str)
    records = chart_df.replace({np.nan: None}).to_dict(orient="records")
    product_lines = sorted(chart_df["产品线"].dropna().unique().tolist())
    data_json = json.dumps(records, ensure_ascii=False)
    lines_json = json.dumps(product_lines, ensure_ascii=False)

    # 读取Chart.js库
    chartjs_path = Path(__file__).parent / "chartjs.min.js"
    if chartjs_path.exists():
        chartjs_code = chartjs_path.read_text(encoding="utf-8")
    else:
        chartjs_code = "console.error('Chart.js not found');"
        log.add("09图表", "警告：Chart.js库文件不存在", f"路径={chartjs_path}")

    # 读取模板
    template_path = Path(__file__).parent / "chart_template.html"
    if template_path.exists():
        html = template_path.read_text(encoding="utf-8")
    else:
        raise FileNotFoundError(f"图表模板文件不存在: {template_path}")

    # 替换占位符
    html = html.replace("__CHARTJS_LIBRARY__", chartjs_code)
    html = html.replace("__DATA_JSON__", data_json)
    html = html.replace("__LINES_JSON__", lines_json)

    output_path.write_text(html, encoding="utf-8")
    log.add("09图表", "生成Chart.js交互式HTML预测图表", f"文件={output_path}")


def export_outputs(
    output_dir: Path,
    combined: pd.DataFrame,
    detail: pd.DataFrame,
    ranking: pd.DataFrame,
    product_contrib: pd.DataFrame,
    diagnostics: pd.DataFrame,
    mapping_diag: pd.DataFrame,
    methods: List[MethodSpec],
    log: OperationLog,
) -> Dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    files = {
        "主表CSV": output_dir / "产品线季度历史与预测.csv",
        "回测明细CSV": output_dir / "预测方法回测明细.csv",
        "排行榜CSV": output_dir / "预测方法排行榜.csv",
        "产品贡献CSV": output_dir / "产品级价格与预测贡献.csv",
        "诊断CSV": output_dir / "数据质量与映射诊断.csv",
        "方法清单CSV": output_dir / "候选预测方法清单.csv",
        "操作日志CSV": output_dir / "操作日志.csv",
        "HTML图表": output_dir / "产品线季度预测图表.html",
        "Excel": output_dir / "产品线季度历史与预测_含方法回测.xlsx",
    }
    method_df = pd.DataFrame([{
        "方法ID": m.方法ID, "方法名称": m.方法名称, "方法族": m.方法族, "方法层级": m.方法层级,
        "基础算法": m.基础算法, "参数": str(m.参数), "金额口径": m.金额口径,
    } for m in methods])
    diag_all = pd.concat([diagnostics.assign(诊断类型="数据质量/冲突"), mapping_diag.assign(诊断类型="产品线回填")], ignore_index=True, sort=False)

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


def run(
    data_path: Path = RAW_FILE,
    output_dir: Path = OUTPUT_DIR,
    fast: bool = False,
    sheet_name=0,
    field_map: Optional[Dict[str, str]] = None,
    method_lock: Optional[Path] = None,
) -> Dict[str, Path]:
    log = OperationLog()
    df_raw = read_raw_data(data_path, log, sheet_name=sheet_name, field_map=field_map)
    df, diagnostics, mapping_diag = clean_and_map(df_raw, log)
    buckets, latest_month, history_ends, bucket_rows = build_buckets(df, log)
    hist_start = bucket_rows[0]["开始Period"]
    hist_end = bucket_rows[11]["结束Period"]
    df_hist = df[df["_月"].between(hist_start, hist_end)].copy()

    line_bucket, product_bucket, pc_bucket, dfb = aggregate_layers(df_hist, bucket_rows, log)
    bucket_ids = [f"H{i:02d}" for i in range(1, 13)]
    value_cols = ["销售量", "销售额", "成本额", "毛利额", "产品数", "客户数", "订单数", "明细行数", "毛利率", "加权销售单价", "加权成本单价"]
    line_panel = complete_panel(line_bucket, ["型号_产品线（新）"], bucket_ids, value_cols)
    product_panel = complete_panel(product_bucket, ["型号_产品线（新）", "SKU预测键"], bucket_ids, value_cols)
    pc_panel = complete_panel(pc_bucket, ["型号_产品线（新）", "SKU预测键", "预测客户名称"], bucket_ids, value_cols)

    ctx = prepare_runtime_context(line_panel, product_panel, pc_panel, bucket_ids)
    log.add("05回测", "预计算产品线/产品/产品客户序列与产品级价格", "完成运行时缓存")

    methods = build_method_specs()
    if method_lock:
        log.add("05回测", "生成候选预测方法池", f"方法数={len(methods)}；锁定模式将跳过全量回测")
        ranking = load_locked_ranking(method_lock, line_panel, methods, log)
        detail = pd.DataFrame(columns=[
            "方法ID", "方法名称", "方法族", "方法层级", "金额口径", "产品线", "回测折次",
            "训练开始桶", "训练结束桶", "验证桶", "实际销售额", "预测销售额", "实际销售量", "预测销售量",
            "实际毛利额", "预测毛利额", "实际毛利率", "预测毛利率", "销售额误差", "销售额绝对误差",
            "销售额APE", "销量误差", "销量绝对误差", "销量APE", "毛利额误差", "毛利额绝对误差", "毛利额APE", "毛利率绝对误差",
        ])
    else:
        if fast:
            methods = methods[:120]
            log.add("05回测", "启用fast模式限制候选方法数", f"方法数={len(methods)}")
        else:
            log.add("05回测", "生成候选预测方法池", f"方法数={len(methods)}")
        detail, ranking = backtest_and_select(methods, line_panel, product_panel, pc_panel, bucket_ids, ctx, log)
    method_map = {m.方法ID: m for m in methods}
    combined = build_final_forecast(ranking, buckets, line_panel, product_panel, pc_panel, method_map, bucket_ids, ctx, log)
    product_contrib = build_product_price_contrib(product_panel, line_panel, bucket_ids, log)
    files = export_outputs(output_dir, combined, detail, ranking, product_contrib, diagnostics, mapping_diag, methods, log)
    return files


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="产品线滚动季度历史分析与未来4期预测")
    parser.add_argument("--config", help="JSON配置文件路径，可配置数据文件、工作表名和字段名映射")
    parser.add_argument("--data", default=None, help="原始出货明细Excel路径；优先级高于配置文件")
    parser.add_argument("--sheet", default=None, help="工作表名或序号；优先级高于配置文件")
    parser.add_argument("--output", default=None, help="输出目录；优先级高于配置文件")
    parser.add_argument("--method-lock", default=None, help="使用既有预测方法排行榜锁定方法，跳过全量回测")
    parser.add_argument("--fast", action="store_true", help="快速模式：仅运行前120个候选方法；锁定模式下无效")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    cfg = load_config(resolve_path(args.config, Path()) if args.config else None)
    data_path = resolve_path(args.data or cfg.get("data_path"), RAW_FILE)
    output_dir = resolve_path(args.output or cfg.get("output_dir"), OUTPUT_DIR)
    sheet_name = normalize_sheet_name(args.sheet if args.sheet is not None else cfg.get("sheet_name", 0))
    field_map = cfg.get("field_map")
    method_lock = resolve_path(args.method_lock, Path()) if args.method_lock else None
    files = run(data_path, output_dir, fast=args.fast, sheet_name=sheet_name, field_map=field_map, method_lock=method_lock)
    print("\n输出文件:")
    for name, path in files.items():
        print(f"  {name}: {path}")
