#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
回退策略脚本。

当数据条件变化（无新品标记列、数据量不足、列名不一致等）时，
自动检测并选择合适策略，确保测试不因数据异常而中断。

每种策略的接口：
    detect(data: dict) -> bool    # 是否触发该策略
    apply(data: dict) -> dict     # 执行策略，返回修补后的数据

调用方式：
    from test.fallback import apply_all_fallbacks
    data = apply_all_fallbacks(data)
"""

import sys, os

_TEST_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_TEST_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import pandas as pd
import numpy as np
from test.conftest import log, has_intermediates, load_intermediates


# ============================================================
# F1: 源数据无新品标记列 → 用自动计算回退
# ============================================================
class FallbackNoNewFlag:
    """源数据不含是否新品列时，用自动计算（近12月首次销售）回退。"""

    id = "F1"
    name = "无新品标记 → 自动计算回退"

    @staticmethod
    def detect(data: dict) -> bool:
        return not data.get("has_new_flag", False)

    @staticmethod
    def apply(data: dict) -> dict:
        log(f"[回退 {FallbackNoNewFlag.id}] {FallbackNoNewFlag.name}")
        prod_monthly = data.get("prod_monthly")
        if prod_monthly is None:
            print("  无法回退：缺少 prod_monthly")
            return data

        latest_month = prod_monthly["_月"].max()
        ps = prod_monthly.groupby("产品品种")["_月"].min().reset_index()
        ps.columns = ["产品品种", "首次销售月"]
        ps["新品标记"] = (latest_month - ps["首次销售月"]).apply(lambda x: x.n) <= 12

        # 将回退标记写回 prod_monthly
        new_map = ps.set_index("产品品种")["新品标记"].to_dict()
        prod_monthly["新品标记"] = prod_monthly["产品品种"].map(new_map).fillna(False)
        prod_monthly["新品标记"] = prod_monthly["新品标记"].replace({True: "是", False: None})

        data["has_in_silver"] = True
        data["has_new_flag"] = True
        data["erp_new_ct"] = int((prod_monthly["新品标记"] == "是").sum())
        data["_fallback_F1_applied"] = True
        print(f"  [OK] 自动计算新品: {data['erp_new_ct']} 行")
        return data


# ============================================================
# F2: 产品画像列名不一致 → 自适应列名映射
# ============================================================
class FallbackColumnMapping:
    """产品/客户列名与默认值不一致时，尝试自适应映射。"""

    id = "F2"
    name = "列名不一致 → 自适应映射"

    # 常见列名变体
    COLUMN_ALIASES = {
        "产品品种": ["产品品种", "存货名称", "产品名称", "物料名称", "产品", "product"],
        "客户编号": ["客户编号", "代理商/直供名称", "客户名称", "客户", "customer"],
        "发货日期": ["发货日期", "日期", "交易日期", "订单日期", "date"],
        "数量": ["数量", "销量", "qty", "Qty", "quantity"],
        "金额": ["金额", "营收", "收入", "销售额", "revenue", "amount"],
        "利润": ["利润", "毛利", "毛利率金额", "profit"],
        "新品标记": ["新品标记", "是否新品", "是否新产品", "is_new"],
    }

    @staticmethod
    def detect(data: dict) -> bool:
        df_clean = data.get("df_clean")
        if df_clean is None:
            return False
        # 检查关键列是否存在
        for standard, aliases in FallbackColumnMapping.COLUMN_ALIASES.items():
            if standard not in df_clean.columns:
                # 检查是否有任何别名匹配
                if not any(a in df_clean.columns for a in aliases):
                    return True  # 存在缺失列
        return False

    @staticmethod
    def apply(data: dict) -> dict:
        log(f"[回退 {FallbackColumnMapping.id}] {FallbackColumnMapping.name}")
        df_clean = data.get("df_clean")
        if df_clean is None:
            return data

        mapping = {}
        for standard, aliases in FallbackColumnMapping.COLUMN_ALIASES.items():
            if standard in df_clean.columns:
                continue
            for alias in aliases:
                if alias in df_clean.columns and alias != standard:
                    mapping[alias] = standard
                    break

        if mapping:
            df_clean = df_clean.rename(columns=mapping)
            data["df_clean"] = df_clean
            data["_fallback_F2_applied"] = True
            print(f"  列映射: {mapping}")

        return data


# ============================================================
# F3: 数据量不足 → 放宽 min_record_months
# ============================================================
class FallbackDataInsufficient:
    """产品画像数据不足导致大量产品被排除时，放宽最低月数要求。"""

    id = "F3"
    name = "数据不足 → 放宽最低月数"

    @staticmethod
    def detect(data: dict) -> bool:
        profiling = data.get("profiling_result")
        total_products = data.get("product_count", 0)
        if profiling is None or total_products == 0:
            return False
        processed = len(profiling)
        excluded = total_products - processed
        # 超过 30% 产品被排除时触发
        return excluded > total_products * 0.3

    @staticmethod
    def apply(data: dict) -> dict:
        log(f"[回退 {FallbackDataInsufficient.id}] {FallbackDataInsufficient.name}")
        # 标记触发
        data["_fallback_F3_detected"] = True
        print("  [WARN] 超过30%产品被排除，建议降低 min_record_months")
        return data


# ============================================================
# F4: 空值处理 → 中位数填充关键数值列
# ============================================================
class FallbackNullValues:
    """关键数值列空值过多时，用中位数填充。"""

    id = "F4"
    name = "空值过多 → 中位数填充"

    NULL_THRESHOLD = 0.1  # 10% 以上空值时触发

    # 需要填充的关键列
    KEY_NUMERIC_COLS = ["距上次采购天数", "常规平均采购间隔", "近12月毛利", "新品采购占比"]

    @staticmethod
    def detect(data: dict) -> bool:
        df_clean = data.get("df_clean")
        if df_clean is None:
            return False
        for col in FallbackNullValues.KEY_NUMERIC_COLS:
            if col in df_clean.columns:
                null_ratio = df_clean[col].isnull().mean()
                if null_ratio > FallbackNullValues.NULL_THRESHOLD:
                    return True
        return False

    @staticmethod
    def apply(data: dict) -> dict:
        log(f"[回退 {FallbackNullValues.id}] {FallbackNullValues.name}")
        df_clean = data.get("df_clean")
        if df_clean is None:
            return data

        filled = []
        for col in FallbackNullValues.KEY_NUMERIC_COLS:
            if col in df_clean.columns:
                null_ratio = df_clean[col].isnull().mean()
                if null_ratio > FallbackNullValues.NULL_THRESHOLD:
                    median_val = df_clean[col].median()
                    df_clean[col] = df_clean[col].fillna(median_val)
                    filled.append(f"{col}({null_ratio:.0%}→中位数{median_val:.1f})")

        data["df_clean"] = df_clean
        data["_fallback_F4_applied"] = True
        if filled:
            print(f"  已填充: {', '.join(filled)}")
        return data


# ============================================================
# F5: 图表 matplotlib 不可用 → 跳过可视化
# ============================================================
class FallbackNoMatplotlib:
    """matplotlib 未安装时，跳过 Phase 3。"""

    id = "F5"
    name = "matplotlib 不可用 → 跳过图表"

    @staticmethod
    def detect(data: dict) -> bool:
        try:
            import matplotlib
            return False
        except ImportError:
            return True

    @staticmethod
    def apply(data: dict) -> dict:
        log(f"[回退 {FallbackNoMatplotlib.id}] {FallbackNoMatplotlib.name}")
        data["_fallback_F5_applied"] = True
        data["_skip_phase3"] = True
        print("  [OK] 已标记跳过 Phase 3（可视化）")
        return data


# ============================================================
# 回退策略注册 & 执行
# ============================================================
FALLBACK_REGISTRY = [
    FallbackNoMatplotlib,      # F5: 先检查环境依赖
    FallbackNoNewFlag,         # F1: 无新品标记
    FallbackColumnMapping,     # F2: 列名不一致
    FallbackDataInsufficient,  # F3: 数据不足
    FallbackNullValues,        # F4: 空值过多
]


def apply_all_fallbacks(data: dict, verbose: bool = True) -> dict:
    """
    按优先级顺序应用所有回退策略。

    参数：
        data:    中间件数据字典
        verbose: 是否打印日志

    返回：修补后的数据字典
    """
    if verbose:
        log("回退策略检查")
    for strategy in FALLBACK_REGISTRY:
        try:
            if strategy.detect(data):
                if verbose:
                    print(f"  [DETECT] {strategy.name}")
                data = strategy.apply(data)
            else:
                if verbose:
                    print(f"  [OK] {strategy.name}: 无需回退")
        except (ValueError, KeyError, AttributeError) as e:
            if verbose:
                print(f"  [WARN] {strategy.name}: 检测异常 {e}")
    return data


def detect_fallbacks(data: dict) -> list:
    """仅检测哪些策略会触发，不执行。"""
    triggered = []
    for strategy in FALLBACK_REGISTRY:
        try:
            if strategy.detect(data):
                triggered.append(strategy.id)
        except (ValueError, KeyError, AttributeError):
            pass
    return triggered


# ── 独立入口 ──
if __name__ == "__main__":
    print("=" * 60)
    print("  回退策略检测（dry-run）")
    print("=" * 60)
    print()

    try:
        from test.conftest import has_intermediates, load_intermediates
        if has_intermediates():
            data = load_intermediates()
            triggered = detect_fallbacks(data)
            if triggered:
                print(f"  会触发的策略: {triggered}")
            else:
                print("  [OK] 无需回退")
        else:
            print("  [WARN] 中间件不存在，请先运行 phase1_load.py")
    except (ValueError, KeyError, AttributeError) as e:
        print(f"  [ERR] {e}")
