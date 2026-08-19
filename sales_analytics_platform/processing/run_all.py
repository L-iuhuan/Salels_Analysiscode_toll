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

import warnings
import os
import sys
import json
import time
import hashlib
import argparse
import importlib.util
import subprocess
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Optional

# ── 抑制已知的良性警告（第三方库数值问题 / pandas 版本迁移） ──
warnings.filterwarnings("ignore", category=FutureWarning, message=".*observed=False.*")
warnings.filterwarnings("ignore", category=FutureWarning, message=".*Downcasting object dtype.*")
warnings.filterwarnings("ignore", message=".*Maximum Likelihood optimization failed.*")
warnings.filterwarnings("ignore", message=".*divide by zero.*")
warnings.filterwarnings("ignore", message=".*invalid value encountered.*")

# 随机种子通过配置控制（仅在需要可复现性时设置）
# 默认不设置全局种子，避免影响依赖numpy的其他模块
# 如需复现：在 config/settings.py 中设置 RANDOM_SEED = 42


# ============================================================
# 路径设置
# ============================================================

PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from config.settings import (
    DATA_DIR, OUTPUT_DIR, OUTPUT_SILVER, OUTPUT_GOLD, OUTPUT_REPORT,
    RUN_STAGES, SKIP_SILVER_IF_EXISTS, COL_MAP, ERP_COL_MAP,
    DATA_SHEET_NAME,
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


def _silver_checksum_path() -> str:
    """Silver缓存校验和文件路径。"""
    return os.path.join(OUTPUT_SILVER, ".silver_checksum")


# 影响 Silver 产出的核心文件（T3/BLOCKER-4：三级指纹——settings*.py + 关键代码 + 源Excel身份）
# 刻意不哈希全部源码：开发期修改 dashboard/ 等不影响 silver 缓存的代码不应使缓存失效。
_SILVER_HASH_FILES = [
    "config/settings.py",
    "config/settings_product.py",
    "config/settings_customer.py",
    "shared/data_cleaning.py",
    "customer_analysis/run_pipeline.py",
    "product_lifecycle/run.py",
]
_SILVER_EXCEL_HASH_HEAD = 8 * 1024 * 1024  # 源Excel内容前8MB的sha256


def _compute_silver_config_hash(source_path: str = None) -> str:
    """对影响Silver输出的核心配置+代码+源Excel身份计算哈希。

    批次①（T3/BLOCKER-4）：在 settings.py + data_cleaning.py 基础上，
    扩展到 settings_product.py / settings_customer.py / run_pipeline.py /
    product_lifecycle/run.py，并加入源Excel身份（文件名+大小+mtime+内容前8MB sha256）。
    任一输入变化都会使缓存失效，避免"改配置→下月跑→仍用旧口径"的静默错误。
    """
    hash_src = []
    base_dir = os.path.dirname(__file__)
    for rel in _SILVER_HASH_FILES:
        p = os.path.join(base_dir, rel)
        if os.path.exists(p):
            with open(p, "rb") as f:
                content = f.read()
            # 行尾归一化：先把 b'\r\n' 归一为 b'\n' 再参与哈希，
            # 避免 git autocrlf 造成 LF/CRLF 落盘差异导致无谓的 silver 缓存失效
            # （源 Excel 为二进制，不在此归一化范围）。
            content = content.replace(b"\r\n", b"\n")
            hash_src.append(content)
    # 源Excel身份：文件名 + 大小 + mtime + 内容前8MB
    if source_path and os.path.exists(source_path):
        st = os.stat(source_path)
        hash_src.append(
            f"{os.path.basename(source_path)}|{st.st_size}|{st.st_mtime}".encode("utf-8")
        )
        with open(source_path, "rb") as f:
            hash_src.append(f.read(_SILVER_EXCEL_HASH_HEAD))
    return hashlib.sha256(b"".join(hash_src)).hexdigest()


def _save_silver_checksum(source_path: str = None):
    """Silver生成完成后保存配置校验和。"""
    checksum = _compute_silver_config_hash(source_path)
    with open(_silver_checksum_path(), "w", encoding="utf-8") as f:
        json.dump({
            "checksum": checksum,
            "files": list(_SILVER_HASH_FILES) + ["源Excel(名+大小+mtime+内容前8MB sha256)"],
        }, f)


def _silver_cache_valid(source_path: str = None) -> bool:
    """检查Silver缓存是否仍有效（配置/代码/源Excel未变）。"""
    cs_path = _silver_checksum_path()
    if not os.path.exists(cs_path):
        return False
    try:
        with open(cs_path, "r", encoding="utf-8") as f:
            saved = json.load(f)
        current = _compute_silver_config_hash(source_path)
        return saved.get("checksum") == current
    except (json.JSONDecodeError, KeyError, OSError):
        return False


def find_source_data(data_path: str = None) -> str:
    """定位源数据文件。"""
    if data_path and os.path.exists(data_path):
        return data_path
    xlsx_files = [f for f in os.listdir(DATA_DIR) if f.endswith(".xlsx") and not f.startswith("~$")]
    if xlsx_files:
        return os.path.join(DATA_DIR, xlsx_files[0])
    return ""


def stage_silver(source_path: str) -> tuple:
    """阶段：共享数据管道。

    返回:
        (success, raw_data, cust_info) — success为bool，raw_data/cust_info为DataFrame或None
    """
    print(f"\n{'=' * 60}")
    print(f"阶段: silver — 共享数据管道")
    print("[STAGE 1/6] 数据清洗 silver", flush=True)
    print(f"{'=' * 60}")
    _t0 = time.time()

    # 检查缓存有效性
    silver_files = ["silver_customer_monthly.csv", "silver_product_monthly.csv", "silver_customer_x_product.csv"]
    if SKIP_SILVER_IF_EXISTS:
        all_exist = all(os.path.exists(os.path.join(OUTPUT_SILVER, f)) for f in silver_files)
        if all_exist:
            if _silver_cache_valid(source_path):
                print("  Silver层缓存有效，跳过（设置 SKIP_SILVER_IF_EXISTS=False 或修改配置强制重算）")
                return True, None, None
            else:
                print("  Silver层配置已变更，缓存失效，重新生成...")

    from shared.data_cleaning import (
        filter_negative_qty, winsorize_margins, monthly_aggregate_double_pass,
        rename_erp_columns, validate_required_columns, read_excel_auto,
        build_cust_info,
    )
    from data_pipeline.validator import SimpleValidator
    _validator = SimpleValidator()

    print(f"  读取: {source_path}")
    raw = read_excel_auto(source_path, sheet_name=DATA_SHEET_NAME)
    _validator.validate_raw(raw)  # V1: 源数据验证

    raw = rename_erp_columns(raw)
    print(f"  原始行数: {len(raw)}")

    # ── 从raw提取客户属性（客户信息表不存在时，统一用 build_cust_info() 从ERP列构建）──
    cust_info = None
    try:
        cust_info = read_excel_auto(source_path, sheet_name="客户信息表")
        raw = raw.merge(cust_info[["客户编号", "渠道类型", "客户等级", "所属区域"]], on="客户编号", how="left")
    except (ValueError, FileNotFoundError, KeyError):
        # 客户信息表不存在 → 统一用 build_cust_info() 从ERP数据列构建 cust_info
        # （批次① T2/P0-1：与缓存路径共用同一构建函数，保证两条路径客户属性一致；
        #   含客户编号 fillna("未知客户") 与 客户类别列名归一）
        cust_info = build_cust_info(raw)
        # 保留 raw 上的默认渠道/等级列（silver_cleaned_rows 列口径，基线锁定）
        raw["渠道类型"] = "未知"
        raw["客户等级"] = "未知"
        if cust_info is not None:
            print(f"  从ERP列构建客户信息: {len(cust_info)} 条（渠道+类别+等级）")
        else:
            print("  从ERP列构建客户信息: 无可用客户属性列")

    # 确保利润裁剪列存在（不做钳制，保留真实毛利率）
    if '_利润_裁剪' not in raw.columns:
        raw['_毛利率'] = raw['利润'] / raw['金额'].replace(0, float('nan'))
        raw['_利润_裁剪'] = raw['利润']  # 不做钳制

    null_cust = raw["客户编号"].isna().sum()
    if null_cust > 0:
        raw["客户编号"] = raw["客户编号"].fillna("未知客户")
        print(f"  客户编号空值填充: {null_cust} 行 -> 未知客户")

    silver = monthly_aggregate_double_pass(raw)
    _validator.validate_silver(silver)

    # 产品线列传递：将产品一级分类 + 型号_产品品类 带入 customer_x_product（用于品类分析）
    prod_col = COL_MAP.get("product_name", "产品品种")
    for cat_col in ["产品一级分类", "型号_产品品类", "型号_产品线（新）", "产品品类"]:
        if cat_col in raw.columns:
            prod_to_line = raw[[prod_col, cat_col]].drop_duplicates()
            silver["customer_x_product"] = silver["customer_x_product"].merge(
                prod_to_line, on=prod_col, how="left"
            )

    for key, df in silver.items():
        path = os.path.join(OUTPUT_SILVER, f"silver_{key}.csv")
        df.to_csv(path, index=False, encoding="utf-8-sig")
        print(f"  输出: {path} ({len(df)} 行)")

    # 保存清洗后行级数据（供v2.8使用）
    raw.to_csv(os.path.join(OUTPUT_SILVER, "silver_cleaned_rows.csv"), index=False, encoding="utf-8-sig")
    print(f"  清洗行级数据: {len(raw)} 行")

    # 保存校验和（标记缓存有效；T3：指纹含配置+关键代码+源Excel身份）
    _save_silver_checksum(source_path)

    print(f"  [时间] silver 阶段: {time.time() - _t0:.1f}s")
    return True, raw, cust_info


def stage_product(source_path: str) -> bool:
    """阶段：产品生命周期分析。"""
    print(f"\n{'=' * 60}")
    print(f"阶段: product — 产品生命周期分析")
    print("[STAGE 2/6] 产品生命周期", flush=True)
    print(f"{'=' * 60}")
    _t0 = time.time()

    from product_lifecycle.run import run as run_product
    result = run_product(source_path=source_path, skip_silver=True)
    return bool(result)


def stage_customer(source_path: str, raw_data: pd.DataFrame = None, cust_info: pd.DataFrame = None) -> bool:
    """阶段：客户销售分析。"""
    print(f"\n{'=' * 60}")
    print(f"阶段: customer — 客户销售分析")
    print("[STAGE 3/6] 客户分析", flush=True)
    print(f"{'=' * 60}")

    from customer_analysis.run_pipeline import run as run_customer
    result = run_customer(
        source_path=source_path,
        skip_silver=True,
        raw_data=raw_data,
        cust_info_data=cust_info,
    )
    return len(result) > 0


def stage_kpi(source_path: str, raw_data: pd.DataFrame = None) -> bool:
    """阶段：准实时KPI。"""
    print(f"\n{'=' * 60}")
    print(f"阶段: kpi — 准实时KPI")
    print("[STAGE 4/6] 准实时KPI", flush=True)
    print(f"{'=' * 60}")

    from customer_analysis.run_kpi_daily import run as run_kpi
    run_kpi(source_path=source_path, raw_df=raw_data)
    return True


def stage_cross_ref(source_path: str = None) -> bool:
    """阶段：交叉关联。"""
    print(f"\n{'=' * 60}")
    print(f"阶段: cross_ref — 交叉关联")
    print("[STAGE 5/6] 交叉关联", flush=True)
    print(f"{'=' * 60}")

    from cross_reference.run_cross_ref import run as run_cross
    result = run_cross()
    return len(result) > 0


# ============================================================
# 阶段关键产物校验（宪法 S4：缺关键产物 → 非零退出并阻断下游）
# ============================================================

# 各阶段关键产物（相对 output/ 目录；存在且非空视为通过）
_STAGE_ARTIFACTS = {
    "silver": [
        os.path.join("silver", "silver_cleaned_rows.csv"),
        os.path.join("silver", "silver_customer_monthly.csv"),
        os.path.join("silver", "silver_product_monthly.csv"),
        os.path.join("silver", "silver_customer_x_product.csv"),
    ],
    "product": [
        os.path.join("gold", "gold_product_portrait.csv"),
    ],
    "customer": [
        os.path.join("gold", "客户全景.csv"),
    ],
    "kpi": [
        os.path.join("gold", "gold_kpi_daily.csv"),
    ],
    "cross_ref": [
        os.path.join("gold", "cross_customer_portfolio_health.csv"),
    ],
}


def _verify_stage_artifacts(stage: str) -> list:
    """校验阶段关键产物文件存在且非空，返回缺失/空文件相对路径列表。"""
    missing = []
    for rel in _STAGE_ARTIFACTS.get(stage, []):
        p = os.path.join(OUTPUT_DIR, rel)
        if not (os.path.exists(p) and os.path.getsize(p) > 0):
            missing.append(rel)
    return missing


# ============================================================
# 自动依赖安装
# ============================================================

REQUIRED = [
    "pandas", "numpy", "openpyxl", "statsmodels",
    "chinese_calendar", "rapidfuzz", "matplotlib",
    "sklearn",  # scikit-learn's import name is "sklearn"
]
# Note: python-calamine is optional (gives 5-10x speedup), not in required list


def _auto_install_deps():
    """检查必需依赖，缺失时自动从 requirements.txt 安装。"""
    missing = []
    for pkg in REQUIRED:
        if importlib.util.find_spec(pkg) is None:
            missing.append(pkg)

    if missing:
        req_path = os.path.join(PROJECT_ROOT, "requirements.txt")
        print(f"[自动安装] 检测到缺失依赖: {', '.join(missing)}")
        print(f"[自动安装] 正在安装: pip install -r requirements.txt")
        try:
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "-r", req_path]
            )
            print(f"[自动安装] 依赖安装完成")
        except Exception as e:
            print(f"[自动安装] 警告: 依赖安装失败 ({e})，请手动执行: "
                  f"pip install -r requirements.txt")


# ============================================================
# 主函数
# ============================================================

def main():
    _auto_install_deps()

    parser = argparse.ArgumentParser(description="半导体销售数据分析统一运行平台")
    parser.add_argument("--data", type=str, default=None, help="源数据Excel文件路径")
    parser.add_argument("--stage", type=str, default=",".join(RUN_STAGES),
                        help=f"要执行的阶段（逗号分隔），可选: {','.join(RUN_STAGES)}")
    parser.add_argument("--skip-product", action="store_true", help="跳过产品生命周期分析")
    parser.add_argument("--skip-customer", action="store_true", help="跳过客户分析")
    parser.add_argument("--force-silver", action="store_true", help="强制重算Silver层")
    parser.add_argument("--pipeline", action="store_true", help="使用 Pipeline DI 容器执行（P2-B）")

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

    # --- P2-B: Pipeline DI 容器模式 ---
    if args.pipeline:
        from core.pipeline import Pipeline
        from core.config import AppConfig

        config = AppConfig.from_defaults()
        config.skip_silver_if_exists = not args.force_silver

        pipeline = Pipeline(config=config)

        if args.skip_product:
            stages = [s for s in args.stage.split(",") if s != "product"]
        elif args.skip_customer:
            stages = [s for s in args.stage.split(",") if s != "customer"]
        else:
            stages = [s.strip() for s in args.stage.split(",")]

        results = pipeline.run(stages=stages, source_path=source_path)
        print(f"\n{'=' * 60}")
        print(f"Pipeline 执行完成")
        print(f"{'=' * 60}")
        print(f"已执行阶段: {list(results.keys())}")
        return

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

    # 缓存数据避免重复读取Excel
    _cached_raw = None
    _cached_cust_info = None

    executed = []
    for stage in stages:
        if stage not in stage_map:
            print(f"  [警告] 未知阶段 '{stage}'，跳过")
            continue
        if stage == "silver":
            success, _cached_raw, _cached_cust_info = stage_silver(source_path)
        elif stage == "customer":
            success = stage_customer(source_path, raw_data=_cached_raw, cust_info=_cached_cust_info)
        elif stage == "kpi":
            success = stage_kpi(source_path, raw_data=_cached_raw)
        else:
            success = stage_map[stage](source_path)
        if success:
            executed.append(stage)
        elif stage == "silver":
            print(f"\n{'='*60}")
            print(f"[致命] Silver 层构建失败，后续阶段无法执行")
            print(f"  请检查: 1) ERP_COL_MAP 配置  2) 数据文件列名  3) data/目录下是否有.xlsx文件")
            print(f"{'='*60}")
            sys.exit(1)
        else:
            print(f"  [警告] 阶段 '{stage}' 未产生完整输出，继续执行下一阶段")

        # 关键产物校验（宪法 S4：缺关键产物 → 非零退出并阻断下游，不继续后续 stage）
        missing = _verify_stage_artifacts(stage)
        if missing:
            print(f"\n{'='*60}")
            print(f"[致命] 阶段 '{stage}' 关键产物缺失或为空: {missing}")
            print(f"  已停止后续阶段（S4：阶段失败必须非零退出并阻断下游）")
            print(f"{'='*60}")
            sys.exit(1)

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
