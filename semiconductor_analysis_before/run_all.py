"""
半导体分析统一运行入口。

按序执行各分析阶段：
  silver    → 共享数据清洗和月度聚合
  product   → 产品生命周期分析（调用v2.8）
  customer  → 客户销售分析
  kpi       → 准实时KPI通道
  cross_ref → 交叉关联（两系统数据融合）

用法：
  python run_all.py                              # 全部执行
  python run_all.py --stage silver,customer      # 仅执行指定阶段
  python run_all.py --skip-product               # 跳过产品阶段
  python run_all.py --data 数据文件路径.xlsx      # 指定源数据
"""

import os
import sys
import argparse
import pandas as pd
from datetime import datetime


# ============================================================
# 路径设置
# ============================================================

PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from config.settings import (
    DATA_DIR, OUTPUT_SILVER, OUTPUT_GOLD, OUTPUT_REPORT,
    RUN_STAGES, SKIP_SILVER_IF_EXISTS,
)


def print_banner():
    print("""
╔══════════════════════════════════════════════════════╗
║      半导体销售数据分析 · 统一运行平台              ║
║      产品生命周期 + 客户分析 + 交叉关联             ║
╚══════════════════════════════════════════════════════╝
    """)


def ensure_dirs():
    for d in [DATA_DIR, OUTPUT_SILVER, OUTPUT_GOLD, OUTPUT_REPORT]:
        os.makedirs(d, exist_ok=True)


def find_source_data(data_path: str = None) -> str:
    """定位源数据文件。"""
    if data_path and os.path.exists(data_path):
        return data_path
    xlsx_files = [f for f in os.listdir(DATA_DIR) if f.endswith(".xlsx")]
    if xlsx_files:
        return os.path.join(DATA_DIR, xlsx_files[0])
    return ""


def stage_silver(source_path: str) -> bool:
    """阶段：共享数据管道。"""
    print(f"\n{'=' * 60}")
    print(f"阶段: silver — 共享数据管道")
    print(f"{'=' * 60}")

    # 检查是否已存在
    silver_files = ["silver_customer_monthly.csv", "silver_product_monthly.csv", "silver_customer_x_product.csv"]
    if SKIP_SILVER_IF_EXISTS:
        all_exist = all(os.path.exists(os.path.join(OUTPUT_SILVER, f)) for f in silver_files)
        if all_exist:
            print("  Silver层已存在，跳过（设置 SKIP_SILVER_IF_EXISTS=False 强制重算）")
            return True

    from shared.data_cleaning import (
        filter_negative_qty, winsorize_margins, monthly_aggregate_double_pass,
        rename_erp_columns,
    )

    print(f"  读取: {source_path}")
    raw = pd.read_excel(source_path, sheet_name=0, engine="openpyxl")
    raw = rename_erp_columns(raw)
    print(f"  原始行数: {len(raw)}")
    raw = filter_negative_qty(raw, qty_col="数量")
    raw = winsorize_margins(raw)

    # 客户信息表合并
    try:
        ci = pd.read_excel(source_path, sheet_name="客户信息表", engine="openpyxl")
        raw = raw.merge(ci[["客户编号", "渠道类型", "客户等级", "所属区域"]], on="客户编号", how="left")
    except Exception:
        raw["渠道类型"] = "未知"

    silver = monthly_aggregate_double_pass(raw)

    for key, df in silver.items():
        path = os.path.join(OUTPUT_SILVER, f"silver_{key}.csv")
        df.to_csv(path, index=False, encoding="utf-8-sig")
        print(f"  输出: {path} ({len(df)} 行)")

    # 保存清洗后行级数据（供v2.8使用）
    raw.to_csv(os.path.join(OUTPUT_SILVER, "silver_cleaned_rows.csv"), index=False, encoding="utf-8-sig")
    print(f"  清洗行级数据: {len(raw)} 行")
    return True


def stage_product(source_path: str) -> bool:
    """阶段：产品生命周期分析。"""
    print(f"\n{'=' * 60}")
    print(f"阶段: product — 产品生命周期分析")
    print(f"{'=' * 60}")

    from product_lifecycle.run import run as run_product
    result = run_product(source_path=source_path, skip_silver=True)
    return bool(result)


def stage_customer(source_path: str) -> bool:
    """阶段：客户销售分析。"""
    print(f"\n{'=' * 60}")
    print(f"阶段: customer — 客户销售分析")
    print(f"{'=' * 60}")

    from customer_analysis.run_pipeline import run as run_customer
    result = run_customer(source_path=source_path)
    return len(result) > 0


def stage_kpi(source_path: str) -> bool:
    """阶段：准实时KPI。"""
    print(f"\n{'=' * 60}")
    print(f"阶段: kpi — 准实时KPI")
    print(f"{'=' * 60}")

    from customer_analysis.run_kpi_daily import run as run_kpi
    run_kpi(source_path=source_path)
    return True


def stage_cross_ref() -> bool:
    """阶段：交叉关联。"""
    print(f"\n{'=' * 60}")
    print(f"阶段: cross_ref — 交叉关联")
    print(f"{'=' * 60}")

    from cross_reference.run_cross_ref import run as run_cross
    result = run_cross()
    return len(result) > 0


# ============================================================
# 主函数
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="半导体销售数据分析统一运行平台")
    parser.add_argument("--data", type=str, default=None, help="源数据Excel文件路径")
    parser.add_argument("--stage", type=str, default=",".join(RUN_STAGES),
                        help=f"要执行的阶段（逗号分隔），可选: {','.join(RUN_STAGES)}")
    parser.add_argument("--skip-product", action="store_true", help="跳过产品生命周期分析")
    parser.add_argument("--skip-customer", action="store_true", help="跳过客户分析")
    parser.add_argument("--force-silver", action="store_true", help="强制重算Silver层")

    args = parser.parse_args()

    print_banner()
    print(f"运行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    ensure_dirs()

    # 定位源数据
    source_path = find_source_data(args.data)
    if not source_path:
        print("[错误] 未找到源数据文件。请将数据放入 data/ 目录或通过 --data 指定。")
        sys.exit(1)
    print(f"源数据: {source_path}")

    # 确定执行阶段
    if args.skip_product:
        stages = [s for s in args.stage.split(",") if s != "product"]
    elif args.skip_customer:
        stages = [s for s in args.stage.split(",") if s != "customer"]
    else:
        stages = [s.strip() for s in args.stage.split(",")]

    # 如果强制重算Silver，先删除已有文件
    if args.force_silver:
        for f in os.listdir(OUTPUT_SILVER):
            os.remove(os.path.join(OUTPUT_SILVER, f))
        print("  Silver层缓存已清除")

    # 分阶段执行
    stage_map = {
        "silver": stage_silver,
        "product": stage_product,
        "customer": stage_customer,
        "kpi": stage_kpi,
        "cross_ref": stage_cross_ref,
    }

    executed = []
    for stage in stages:
        if stage not in stage_map:
            print(f"  [警告] 未知阶段 '{stage}'，跳过")
            continue
        success = stage_map[stage](source_path)
        if success:
            executed.append(stage)
        else:
            print(f"  [警告] 阶段 '{stage}' 未产生完整输出，继续执行下一阶段")

    # 打印汇总
    print(f"\n{'=' * 60}")
    print(f"执行完成")
    print(f"{'=' * 60}")
    print(f"已执行阶段: {', '.join(executed)}")
    print(f"\n输出目录:")
    print(f"  Silver层: {OUTPUT_SILVER}")
    print(f"  Gold层:   {OUTPUT_GOLD}")
    print(f"  报告:     {OUTPUT_REPORT}")
    print(f"\nGold层文件（可导入BI工具）:")
    if os.path.exists(OUTPUT_GOLD):
        for f in sorted(os.listdir(OUTPUT_GOLD)):
            size = os.path.getsize(os.path.join(OUTPUT_GOLD, f))
            print(f"  {f} ({size / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
