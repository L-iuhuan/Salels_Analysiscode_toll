"""
客户销售分析管道 — 编排层。

执行流程:
  1. 读取源数据 → 共享清洗（负销量过滤、Winsorization）
  2. 双通道月度聚合（Silver层）
  3. 计算客户全景指标（10维度）
  4. 机会/风险评分, RFM-π评分, 定价建议, 行动建议
  5. 引用产品生命周期画像（交叉关联）
  6. 输出Gold层多表报告

各步骤实现在子模块中，此文件仅做编排。
"""

import os
import sys
import time
import pandas as pd

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from shared.data_cleaning import read_excel_auto, rename_erp_columns, SILVER_DTYPE_CUSTOMER_MONTHLY, SILVER_DTYPE_PRODUCT_MONTHLY, SILVER_DTYPE_CUSTOMER_X_PRODUCT
from customer_analysis.silver import build_silver_layer
from customer_analysis.portrait import calc_customer_portrait
from customer_analysis.gold import generate_gold_tables
from customer_analysis.report import save_gold_tables

DATA_DIR = os.path.join(PROJECT_ROOT, "data")
OUTPUT_SILVER = os.path.join(PROJECT_ROOT, "output", "silver")
OUTPUT_GOLD = os.path.join(PROJECT_ROOT, "output", "gold")
OUTPUT_REPORT = os.path.join(PROJECT_ROOT, "output", "report")
PRODUCT_GOLD_PATH = os.path.join(OUTPUT_GOLD, "gold_product_portrait.csv")


def run(
    source_path: str = None,
    product_portrait_path: str = None,
    col_map: dict = None,
    skip_silver: bool = False,
    customer_master_path: str = None,
    raw_data: pd.DataFrame = None,
    cust_info_data: pd.DataFrame = None,
) -> dict:
    """执行完整客户分析管道。

    参数:
        source_path: 源Excel文件路径
        product_portrait_path: 产品画像CSV路径（用于桥接）
        col_map: 列名映射字典
        skip_silver: 是否跳过Silver构建（从CSV加载）
        customer_master_path: 终端客户主数据文件路径（可选）

    返回:
        dict: {"gold_tables": {...}, "report_xlsx": str, "customer_count": int}
    """
    _t0 = time.time()
    os.makedirs(OUTPUT_SILVER, exist_ok=True)
    os.makedirs(OUTPUT_GOLD, exist_ok=True)
    os.makedirs(OUTPUT_REPORT, exist_ok=True)

    if skip_silver:
        silver = {}
        _dtype_map = {
            "customer_monthly": SILVER_DTYPE_CUSTOMER_MONTHLY,
            "customer_x_product": SILVER_DTYPE_CUSTOMER_X_PRODUCT,
            "product_monthly": SILVER_DTYPE_PRODUCT_MONTHLY,
        }
        for key in ["customer_monthly", "customer_x_product", "product_monthly"]:
            fpath = os.path.join(OUTPUT_SILVER, f"silver_{key}.csv")
            df = pd.read_csv(fpath, encoding="utf-8-sig", dtype=_dtype_map.get(key, {}))
            df["_月"] = pd.PeriodIndex(df["_月"], freq="M")
            df = rename_erp_columns(df)
            silver[key] = df

        print(f"  Silver层从CSV加载 ({len(silver['customer_monthly'])} 客户月记录)")
        latest_month = silver["product_monthly"]["_月"].max()

        # 从源数据加载原始列用于渠道推导（skip_silver 时 raw_data 不会自动构建）
        if raw_data is None:
            raw_data = None
            if source_path is None:
                xlsx_files = [f for f in os.listdir(DATA_DIR) if f.endswith(".xlsx") and not f.startswith("~$")]
                if xlsx_files:
                    source_path = os.path.join(DATA_DIR, xlsx_files[0])
            if source_path:
                raw_temp = read_excel_auto(source_path, sheet_name=0)
                _keep_cols = ["代理商/直供名称", "实际终端客户", "销售部门", "实际业务员"]
                raw_data = raw_temp[[c for c in _keep_cols if c in raw_temp.columns]].copy()
                if "代理商/直供名称" in raw_data.columns and "客户编号" not in raw_data.columns:
                    raw_data["客户编号"] = raw_data["代理商/直供名称"]
                print(f"  渠道推导数据从源文件加载 ({len(raw_data)} 行)")
        else:
            print(f"  渠道推导数据使用预加载DataFrame ({len(raw_data)} 行)")
    else:
        if source_path is None:
            xlsx_files = [f for f in os.listdir(DATA_DIR) if f.endswith(".xlsx") and not f.startswith("~$")]
            if not xlsx_files:
                return {}
            source_path = os.path.join(DATA_DIR, xlsx_files[0])

        raw_temp = read_excel_auto(source_path, sheet_name=0)
        if col_map:
            date_col = col_map.get("发货日期列", "发货日期")
        else:
            date_col = "发货日期"
        raw_temp[date_col] = pd.to_datetime(raw_temp[date_col], errors='coerce')
        na_dates = raw_temp[date_col].isna().sum()
        if na_dates > 0:
            print(f"  [警告] {na_dates} 行日期解析失败，已过滤")
            raw_temp = raw_temp.dropna(subset=[date_col])

        silver = build_silver_layer(source_path, col_map, incomplete_month_threshold_day=25)
        latest_month = silver["product_monthly"]["_月"].max()
        # 保留原始数据（仅必需列）用于客户属性回退映射和渠道推导
        if raw_data is None:
            _keep_cols = ["代理商/直供名称", "实际终端客户", "销售部门", "实际业务员"]
            raw_data = raw_temp[[c for c in _keep_cols if c in raw_temp.columns]].copy()
        if raw_data is not None:
            # 添加"客户编号"别名（=代理商/直供名称），供属性回退映射使用
            if "代理商/直供名称" in raw_data.columns and "客户编号" not in raw_data.columns:
                raw_data["客户编号"] = raw_data["代理商/直供名称"]

    _t1 = time.time()
    print(f"  [时间] 客户数据准备+Silver加载: {_t1 - _t0:.1f}s")

    # 自动查找终端客户主数据（如未指定）
    if customer_master_path is None:
        master_files = [f for f in os.listdir(DATA_DIR) if "终端" in f and f.endswith(".xlsx") and not f.startswith("~$")]
        if master_files:
            customer_master_path = os.path.join(DATA_DIR, master_files[0])
            print(f"  自动检测终端客户主数据: {customer_master_path}")

    customer_df = calc_customer_portrait(silver, source_path, latest_month, raw_data, cust_info_df=cust_info_data)

    # 终端客户主数据整合（可选）
    if customer_master_path:
        try:
            from customer_analysis.customer_master import load_customer_master, enrich_customer_portrait
            master = load_customer_master(customer_master_path)
            prev_count = len(customer_df)
            customer_df = enrich_customer_portrait(customer_df, master)
            print(f"  终端客户主数据整合: 新增 {len(customer_df.columns) - len(customer_df.drop(columns=[c for c in customer_df.columns if c.startswith('终端')], errors='ignore').columns)} 列")
        except (ValueError, KeyError, FileNotFoundError) as e:
            print(f"  [警告] 终端客户主数据整合失败: {e}")

        # 渠道类型三级降级：CRM优先 -> 交易推导 -> 未知
        if "_CRM渠道类型" in customer_df.columns:
            from_crm = customer_df["_CRM渠道类型"].notna()
            n_overwrite = from_crm.sum()
            customer_df.loc[from_crm, "渠道类型"] = customer_df.loc[from_crm, "_CRM渠道类型"]
            if n_overwrite > 0:
                print(f"  渠道类型(CRM): {n_overwrite} 客户来自CRM映射")

    # 交易数据推导渠道类型（CRM未覆盖的客户）
    still_unknown = customer_df["渠道类型"].isna() | (customer_df["渠道类型"] == "未知")
    if still_unknown.any() and raw_data is not None:
        from customer_analysis.portrait import _derive_channel
        for idx in customer_df.index[still_unknown]:
            cid = customer_df.loc[idx, "客户编号"]
            ch = _derive_channel(cid, raw_data)
            if ch != "未知":
                customer_df.loc[idx, "渠道类型"] = ch
        n_trade = still_unknown.sum() - (customer_df["渠道类型"].isna() | (customer_df["渠道类型"] == "未知")).sum()
        if n_trade > 0:
            print(f"  渠道类型(交易): {n_trade} 客户来自交易数据推导")

    _t2 = time.time()
    print(f"  [时间] 客户全景画像: {_t2 - _t1:.1f}s ({len(customer_df)}个客户)")

    if product_portrait_path is None:
        product_portrait_path = PRODUCT_GOLD_PATH
    gold = generate_gold_tables(customer_df, silver, product_portrait_path)
    _t3 = time.time()
    print(f"  [时间] Gold表生成: {_t3 - _t2:.1f}s")

    report_path = save_gold_tables(gold)
    _t4 = time.time()
    print(f"  [时间] Excel报告: {_t4 - _t3:.1f}s")
    print(f"  [时间] 客户分析总计: {_t4 - _t0:.1f}s")

    result = {
        "gold_tables": gold,
        "report_xlsx": report_path,
        "customer_count": len(customer_df),
    }

    return result


if __name__ == "__main__":
    run()
