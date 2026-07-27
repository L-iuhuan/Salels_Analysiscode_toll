#!/usr/bin/env python
"""
Phase 1：加载 & Silver 构建。

读取源 Excel → ERP 列名映射 → 数据清洗 → 双通道月度聚合 → 保存中间件(pickle)。

独立运行：
    python test/phase1_load.py                        # 默认数据文件
    python test/phase1_load.py --file path/to/data.xlsx  # 指定文件
    python test/phase1_load.py --force                   # 强制重新加载（忽略缓存）
    python test/phase1_load.py --skip-save               # 仅演练，不保存

Phase 2/3 通过 conftest.load_intermediates() 复用此阶段的输出。
"""

import sys, os, time, argparse

# ── 确保 test/ 下可直接运行 ──
_TEST_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_TEST_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from test.conftest import (
    PROJECT_ROOT, DIAG_DIR, PKL_PATH, DEFAULT_DATA_FILE,
    save_intermediates, has_intermediates, ensure_diag_dir, log, header,
)
import pandas as pd


def run_phase1(data_file: str = None, force: bool = False, skip_save: bool = False) -> dict:
    """
    执行 Phase 1：加载 → 清洗 → Silver → 保存中间件。

    返回中间数据字典（含 df_clean, prod_monthly, cxp, cust_monthly 等）。
    """
    if data_file is None:
        data_file = DEFAULT_DATA_FILE
    ensure_diag_dir()

    # ── 缓存检查 ──
    if has_intermediates() and not force:
        log(f"[Phase 1] 缓存存在: {PKL_PATH}  (使用 --force 重新加载)")
        from test.conftest import load_intermediates
        return load_intermediates()

    header(f"Phase 1：加载 & Silver 构建")
    print(f"  数据文件: {data_file}")
    print(f"  强制重新加载: {force}")
    t_start = time.time()

    # 1. 加载源数据
    log("步骤 1/5：读入源数据")
    from shared.data_cleaning import read_excel_auto
    df_full = read_excel_auto(data_file, sheet_name=0)
    print(f"  行数: {len(df_full)}, 列数: {len(df_full.columns)}")
    date_col = _detect_date_col(df_full)
    print(f"  日期列: {date_col}")

    # 2. ERP 列名映射
    log("步骤 2/5：ERP 列名映射")
    from shared.data_cleaning import rename_erp_columns
    df = rename_erp_columns(df_full.copy())
    has_new_flag = "新品标记" in df.columns
    new_pct = (df["新品标记"] == "是").mean() * 100 if has_new_flag else 0
    print(f"  含新品标记: {has_new_flag}" + (f", 新品行占比: {new_pct:.2f}%" if has_new_flag else ""))

    # 3. 数据清洗
    log("步骤 3/5：过滤负销量 + Winsorization")
    from shared.data_cleaning import filter_negative_qty, winsorize_margins
    df_clean = filter_negative_qty(df.copy())
    df_clean = winsorize_margins(df_clean)
    removed = len(df) - len(df_clean)
    print(f"  清洗剔除: {removed} 行 ({removed/max(len(df),1)*100:.1f}%)")

    # 4. 双通道月度聚合 → Silver
    log("步骤 4/5：双通道月度聚合 → Silver")
    from shared.data_cleaning import monthly_aggregate_double_pass
    silver = monthly_aggregate_double_pass(df_clean)
    prod_monthly = silver["product_monthly"]
    cxp = silver["customer_x_product"]
    cust_monthly = silver["customer_monthly"]
    has_in_silver = "新品标记" in prod_monthly.columns
    erp_new_ct = int((prod_monthly["新品标记"] == "是").sum()) if has_in_silver else 0
    print(f"  product_monthly: {prod_monthly.shape}")
    print(f"  customer_x_product: {cxp.shape}")
    print(f"  customer_monthly: {cust_monthly.shape}")
    print(f"  新品标记传播: {has_in_silver}" + (f", ERP标记行: {erp_new_ct}" if has_in_silver else ""))

    # 5. 统计信息
    latest_month = prod_monthly["_月"].max()
    product_count = df_full["存货名称"].nunique() if "存货名称" in df_full.columns else prod_monthly["产品品种"].nunique()
    customer_count = df_full["代理商/直供名称"].nunique() if "代理商/直供名称" in df_full.columns else cust_monthly["客户编号"].nunique()

    # ── 组装中间件 ──
    to_save = {
        "data_file": data_file,
        "df_full_shape": df_full.shape,
        "has_new_flag": has_new_flag,
        "new_pct": new_pct,
        "df_clean": df_clean,
        "prod_monthly": prod_monthly,
        "cxp": cxp,
        "cust_monthly": cust_monthly,
        "has_in_silver": has_in_silver,
        "erp_new_ct": erp_new_ct,
        "latest_month": latest_month,
        "product_count": product_count,
        "customer_count": customer_count,
        "date_col": date_col,
        "date_range": (
            str(df_full[date_col].min()) if date_col else "",
            str(df_full[date_col].max()) if date_col else "",
        ),
    }

    elapsed = time.time() - t_start
    to_save["phase1_elapsed"] = round(elapsed, 1)
    print(f"\n  [时间] Phase 1 耗时: {elapsed:.1f}s")

    # ── 保存 ──
    if skip_save:
        log("[Phase 1] --skip-save 模式，不保存中间件")
    else:
        save_intermediates(to_save)
        log(f"[Phase 1] 中间件已保存: {PKL_PATH}")

    return to_save


def _detect_date_col(df: pd.DataFrame) -> str:
    """自动检测日期列。"""
    for col in ["发货日期", "日期", "交易日期"]:
        if col in df.columns:
            return col
    # 回退：找第一个 datetime 列
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            return col
    return ""


# ── 独立入口 ──
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Phase 1：加载 & Silver 构建")
    parser.add_argument("--file", type=str, default=None, help="数据文件路径")
    parser.add_argument("--force", action="store_true", help="强制重新加载（忽略缓存）")
    parser.add_argument("--skip-save", action="store_true", help="仅演练，不保存中间件")
    args = parser.parse_args()

    run_phase1(data_file=args.file, force=args.force, skip_save=args.skip_save)
