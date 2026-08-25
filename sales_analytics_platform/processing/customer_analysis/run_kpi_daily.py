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

from shared.data_cleaning import (
    filter_negative_qty, rename_erp_columns, read_excel_auto, load_silver_table,
)
# [批次⑤ 缺陷A修复] 输出/输入目录统一从 config.settings 引入（指向包根 output/ 与 data/）
from config.settings import ERP_COL_MAP, OUTPUT_GOLD, OUTPUT_SILVER, DATA_DIR


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
        # 批次② 车道C 评估结论（缓存路径加速）：raw_df=None 分支优先读共享 Silver 行级数据
        # silver_cleaned_rows（存在同名 .parquet 且不早于 CSV 时读 parquet，快 3-5 倍），
        # 替代重读 230MB 原始 Excel（约30-60s）。
        # 已验证：cleaned_rows 与本分支原 Excel 直读在 客户数/销售额/数量 等逐值一致
        # （销售额仅 1e-16 级 float 舍入噪声，远低于 1e-6 容差），gold_kpi_daily.csv 零漂移；
        # cleaned_rows 已含 rename + 客户编号 fillna("未知客户")（批次① P0-1 同源口径），
        # 下方仍防御性补一次 fillna 保证与 force 路径一致。
        silver_rows_path = os.path.join(OUTPUT_SILVER, "silver_cleaned_rows.csv")
        if os.path.exists(silver_rows_path):
            print("[KPI] 从 silver_cleaned_rows 加载（跳过 230MB Excel 读取）")
            raw = load_silver_table(silver_rows_path, low_memory=False)
        else:
            # 无共享 Silver 产物（罕见）时回退原始 Excel 直读（原逻辑）
            if source_path is None:
                xlsx_files = [f for f in os.listdir(DATA_DIR) if f.endswith(".xlsx")]
                if not xlsx_files:
                    print("[KPI] 错误: data/ 目录下未找到数据文件")
                    return pd.DataFrame()
                # mtime 最新（与 run_chain.find_raw_excel / run_all.find_source_data 同口径；字母序会在多月度文件并存时取错）
                source_path = os.path.join(DATA_DIR, max(xlsx_files, key=lambda n: os.path.getmtime(os.path.join(DATA_DIR, n))))
            from config.settings import DATA_SHEET_NAME
            print(f"[KPI] 读取数据: {source_path} (sheet={DATA_SHEET_NAME})")
            raw = read_excel_auto(source_path, sheet_name=DATA_SHEET_NAME)
            raw = rename_erp_columns(raw)
        # 防御性 fillna（cleaned_rows 通常已填充；Excel 直读时必需），批次① P0-1 同源口径
        if "客户编号" in raw.columns:
            null_cust = raw["客户编号"].isna().sum()
            if null_cust > 0:
                raw["客户编号"] = raw["客户编号"].fillna("未知客户")
                print(f"  客户编号空值填充: {null_cust} 行 -> 未知客户")
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
