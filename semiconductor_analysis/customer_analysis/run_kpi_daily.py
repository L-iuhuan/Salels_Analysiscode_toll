"""
准实时KPI通道 — 单独入口，独立于主管道运行。

【注意】此模块有独立的 Excel 读取路径和清洗逻辑，与主管道不共享 Silver 层数据。
在 run_all.py 中通过 stage_kpi() 调用，但不会影响 product/customer 管道的输出。
如果修改了主管道的清洗逻辑（如 ERP_COL_MAP 或 Winsorization 参数），
需同步更新此模块以保持一致性。
"""

import os
import sys
import pandas as pd
import numpy as np

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from shared.data_cleaning import filter_negative_qty, rename_erp_columns, read_excel_auto
from config.settings import ERP_COL_MAP

OUTPUT_GOLD = os.path.join(PROJECT_ROOT, "output", "gold")
DATA_DIR = os.path.join(PROJECT_ROOT, "data")


def build_kpi(source_path: str = None, raw_df: pd.DataFrame = None) -> pd.DataFrame:
    """构建每日KPI表。

    参数:
        source_path: 源文件路径。None时自动在data目录查找。
        raw_df: 预加载的DataFrame（可选，避免重读Excel）

    返回:
        gold_kpi_daily DataFrame
    """
    os.makedirs(OUTPUT_GOLD, exist_ok=True)

    if raw_df is not None:
        raw = raw_df.copy()
        print(f"[KPI] 使用预加载数据 ({len(raw)} 行)")
        # 预加载数据已重命名列，移除原始ERP列避免重复rename
        # 只移除映射到不同列名的ERP原始列（如 代理商/直供名称→客户编号）
        # 跳过 self-mapping 列（如 发货日期→发货日期）
        _erp_originals = [k for k, v in ERP_COL_MAP.items() if k != v and k in raw.columns]
        raw = raw.drop(columns=_erp_originals, errors="ignore")
    else:
        if source_path is None:
            xlsx_files = [f for f in os.listdir(DATA_DIR) if f.endswith(".xlsx")]
            if not xlsx_files:
                print("[KPI] 错误: data/ 目录下未找到数据文件")
                return pd.DataFrame()
            source_path = os.path.join(DATA_DIR, xlsx_files[0])

        print(f"[KPI] 读取数据: {source_path}")
        raw = read_excel_auto(source_path, sheet_name=0)
        raw = rename_erp_columns(raw)
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
    daily = daily.sort_values("日期", kind='stable')

    # 本月累计（基于数据最大日期，而非系统时钟）
    latest_date = daily["日期"].max()
    month_mask = daily["日期"].apply(lambda x: x.month == latest_date.month and x.year == latest_date.year)
    daily["本月累计销售额"] = daily.loc[month_mask, "销售额"].cumsum()
    daily["本月累计天数"] = (daily["日期"].apply(lambda d: d.day) * month_mask.values.astype(int))

    # Top客户（当日）— 格式化为 "客户名(金额)" 字符串
        # Top客户（当日）— 单次groupby + head(5) 替代嵌套apply
    daily_cust_rev = raw.groupby([raw["发货日期"].dt.date, "客户编号"])["金额"].sum().reset_index()
    top_cust = (
        daily_cust_rev.sort_values(["发货日期", "金额"], ascending=[True, False], kind='stable')
        .groupby("发货日期", sort=False)
        .head(5)
    )
    top_cust_agg = top_cust.groupby("发货日期", sort=False).apply(
        lambda g: "; ".join(f"{r['客户编号']}({r['金额']:.0f})" for _, r in g.iterrows()),
        include_groups=False,
    ).reset_index()
    top_cust_agg.columns = ["日期", "Top5客户"]
    daily = daily.merge(top_cust_agg, on="日期", how="left")

    # Top产品（当日）
    daily_prod_rev = raw.groupby([raw["发货日期"].dt.date, "产品品种"])["金额"].sum().reset_index()
    top_prod = (
        daily_prod_rev.sort_values(["发货日期", "金额"], ascending=[True, False], kind='stable')
        .groupby("发货日期", sort=False)
        .head(5)
    )
    top_prod_agg = top_prod.groupby("发货日期", sort=False).apply(
        lambda g: "; ".join(f"{r['产品品种']}({r['金额']:.0f})" for _, r in g.iterrows()),
        include_groups=False,
    ).reset_index()
    top_prod_agg.columns = ["日期", "Top5产品"]
    daily = daily.merge(top_prod_agg, on="日期", how="left")

    path = os.path.join(OUTPUT_GOLD, "gold_kpi_daily.csv")
    daily.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"[KPI] 已输出: {path} ({len(daily)} 行)")
    print(f"[KPI] 数据范围: {daily['日期'].min()} ~ {daily['日期'].max()}")
    return daily


def run(source_path: str = None, raw_df: pd.DataFrame = None):
    build_kpi(source_path, raw_df=raw_df)


if __name__ == "__main__":
    run()
