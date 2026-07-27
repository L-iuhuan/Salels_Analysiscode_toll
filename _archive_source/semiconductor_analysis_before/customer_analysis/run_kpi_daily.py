"""
准实时KPI通道。

独立于月度批处理管道，只做基础聚合：
  - 每日销售额、数量、订单数
  - Top客户排名、Top产品排名
  - 本月累计

不依赖：产品画像、客户分层等月度分析结果。
"""

import os
import sys
import pandas as pd
import numpy as np
from datetime import datetime

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from shared.data_cleaning import filter_negative_qty

OUTPUT_GOLD = os.path.join(PROJECT_ROOT, "output", "gold")
DATA_DIR = os.path.join(PROJECT_ROOT, "data")


def build_kpi(source_path: str = None) -> pd.DataFrame:
    """构建每日KPI表。

    参数:
        source_path: 源文件路径。None时自动在data目录查找。

    返回:
        gold_kpi_daily DataFrame
    """
    os.makedirs(OUTPUT_GOLD, exist_ok=True)

    if source_path is None:
        xlsx_files = [f for f in os.listdir(DATA_DIR) if f.endswith(".xlsx")]
        if not xlsx_files:
            print("[KPI] 错误: data/ 目录下未找到数据文件")
            return pd.DataFrame()
        source_path = os.path.join(DATA_DIR, xlsx_files[0])

    print(f"[KPI] 读取数据: {source_path}")
    raw = pd.read_excel(source_path, sheet_name="销售明细", engine="openpyxl")
    raw["发货日期"] = pd.to_datetime(raw["发货日期"])
    raw = filter_negative_qty(raw, qty_col="数量")

    # 按日聚合
    daily = raw.groupby(raw["发货日期"].dt.date).agg(
        销售额=("金额", "sum"),
        数量=("数量", "sum"),
        订单数=("订单编号", "nunique") if "订单编号" in raw.columns else ("金额", "count"),
        客户数=("客户编号", "nunique"),
        品种数=("产品品种", "nunique"),
    ).reset_index()
    daily.columns = ["日期", "销售额", "数量", "订单数", "客户数", "品种数"]
    daily = daily.sort_values("日期")

    # 本月累计
    today = datetime.now().date()
    daily["本月累计销售额"] = daily[daily["日期"].apply(lambda x: x.month == today.month and x.year == today.year)]["销售额"].cumsum()
    daily["本月累计天数"] = range(1, len(daily) + 1)

    # Top客户（当日）
    top_cust = raw.groupby(raw["发货日期"].dt.date).apply(
        lambda g: g.groupby("客户编号")["金额"].sum().nlargest(5).to_dict(),
        include_groups=False,
    ).reset_index()
    top_cust.columns = ["日期", "Top5客户"]
    daily = daily.merge(top_cust, on="日期", how="left")

    # Top产品（当日）
    top_prod = raw.groupby(raw["发货日期"].dt.date).apply(
        lambda g: g.groupby("产品品种")["金额"].sum().nlargest(5).to_dict(),
        include_groups=False,
    ).reset_index()
    top_prod.columns = ["日期", "Top5产品"]
    daily = daily.merge(top_prod, on="日期", how="left")

    path = os.path.join(OUTPUT_GOLD, "gold_kpi_daily.csv")
    daily.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"[KPI] 已输出: {path} ({len(daily)} 行)")
    print(f"[KPI] 数据范围: {daily['日期'].min()} ~ {daily['日期'].max()}")
    return daily


def run(source_path: str = None):
    build_kpi(source_path)


if __name__ == "__main__":
    run()
