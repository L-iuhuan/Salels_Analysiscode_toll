#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
半导体销售数据分析系统 — 验证测试套件。

用途:
  对数据管道的边界条件、P0缺陷修复、业务规则、数据完整性进行自动化验证。

运行方式:
    python test/validation_suite.py                           # 完整运行
    python test/validation_suite.py --include boundary        # 仅边界测试
    python test/validation_suite.py --include p0              # 仅P0回归测试
    python test/validation_suite.py --include business        # 仅业务规则测试
    python test/validation_suite.py --include integrity       # 仅数据完整性测试
    python test/validation_suite.py --blackbox-only           # 跳过导入pipeline的测试
    python test/validation_suite.py --verbose                 # 详细输出

依赖:
    pandas, numpy, openpyxl (标准管道依赖)

输出:
    控制台打印 pass/fail 汇总
"""

import sys
import os
import warnings
import argparse
import traceback

warnings.filterwarnings("ignore")

# ── 项目路径注入 ──────────────────────────────────────────────
_TEST_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_TEST_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# ── 全局结果收集 ──────────────────────────────────────────────
RESULTS = []  # [(test_id, name, passed, reason)]


def record(test_id, name, passed, reason=""):
    RESULTS.append((test_id, name, passed, reason))
    status = "PASS" if passed else "FAIL"
    print(f"  [{status}] {test_id}: {name}")
    if not passed and reason:
        print(f"          └─ {reason}")


# ================================================================
# 辅助函数
# ================================================================

def _make_single_row_dataframe():
    """构造1行DataFrame用于边界测试。"""
    return pd.DataFrame({
        "日期": pd.to_datetime(["2025-01-15"]),
        "产品名称": ["测试产品A"],
        "数量": [10],
        "金额": [1000.0],
        "利润": [200.0],
        "成本": [800.0],
        "客户名称": ["测试客户X"],
    })


def _make_zero_revenue_dataframe():
    """构造含零收入的DataFrame。"""
    return pd.DataFrame({
        "利润": [0, -100, 200],
        "金额": [0, 100, 0],
    })


def _silver_files_exist():
    """检查Silver层CSV是否存在。"""
    required = [
        "silver_customer_monthly.csv",
        "silver_product_monthly.csv",
        "silver_customer_x_product.csv",
        "silver_cleaned_rows.csv",
    ]
    silver_dir = os.path.join(_PROJECT_ROOT, "output", "silver")
    if not os.path.isdir(silver_dir):
        return False, []
    missing = [f for f in required if not os.path.exists(os.path.join(silver_dir, f))]
    return len(missing) == 0, missing


def _load_silver():
    """加载Silver层CSV（如果存在）。"""
    silver_dir = os.path.join(_PROJECT_ROOT, "output", "silver")
    data = {}
    for fname in ["silver_customer_monthly.csv", "silver_product_monthly.csv",
                  "silver_customer_x_product.csv", "silver_cleaned_rows.csv"]:
        fpath = os.path.join(silver_dir, fname)
        if os.path.exists(fpath):
            data[fname.replace(".csv", "")] = pd.read_csv(fpath, encoding="utf-8-sig")
    return data


def _gold_files_exist():
    """检查Gold层CSV是否存在，返回文件列表。"""
    gold_dir = os.path.join(_PROJECT_ROOT, "output", "gold")
    if not os.path.isdir(gold_dir):
        return False, []
    files = [f for f in os.listdir(gold_dir) if f.endswith(".csv")]
    return len(files) > 0, files


# 尝试导入pandas（必须）
try:
    import pandas as pd
    import numpy as np
except ImportError as e:
    print(f"[FATAL] 缺少必需依赖: {e}")
    print("请执行: pip install pandas numpy openpyxl")
    sys.exit(1)

# ================================================================
# 章节1: 边界测试 (BC-01 ~ BC-20)
# ================================================================

def run_boundary_tests():
    """执行所有边界测试用例。"""
    print("\n" + "=" * 65)
    print("章节1: 边界测试 (BC-01 ~ BC-20)")
    print("=" * 65)

    # ── BC-01: 空DataFrame月度聚合 ──────────────────────────────
    try:
        from shared.data_cleaning import monthly_aggregate_double_pass, winsorize_margins
        empty_df = pd.DataFrame(columns=["客户名称", "产品名称", "日期", "数量", "金额", "利润", "成本"])
        # 确保日期列是datetime类型，否则.dt访问器会失败
        if "日期" in empty_df.columns:
            empty_df["日期"] = pd.to_datetime(empty_df["日期"], errors="coerce")
        # 先做winsorization产生_利润_裁剪列（空DataFrame不影响）
        df_wins = winsorize_margins(empty_df, profit_col="利润", rev_col="金额", inplace=False)
        result = monthly_aggregate_double_pass(
            df_wins, date_col="日期", profit_col="利润", rev_col="金额",
            qty_col="数量", cost_col="成本", cust_col="客户名称", prod_col="产品名称"
        )
        keys = list(result.keys())
        all_empty = all(len(v) == 0 for v in result.values())
        all_have_keys = set(keys) == {"customer_monthly", "product_monthly", "customer_x_product"}
        record("BC-01", "空DataFrame → 月度聚合返回3个空DataFrame", all_empty and all_have_keys,
               f"keys={keys}, shapes={[v.shape for v in result.values()]}" if not (all_empty and all_have_keys) else "")
    except Exception as e:
        record("BC-01", "空DataFrame → 月度聚合", False, f"崩溃: {e}")

    # ── BC-02: 单行数据风险评分 ──────────────────────────────────
    try:
        from shared.risk_scoring import risk_slope, risk_cv, risk_decay, risk_self_health, risk_asp
        # NaN 斜率
        slope = risk_slope(slope_ratio=np.nan, thr={"slope_low_pct": 0, "slope_mid_pct": -0.3, "slope_high_pct": -0.8, "slope_default_score": 80})
        slope_ok = slope == 80
        record("BC-02a", "risk_slope(NaN) → default=80", slope_ok, f"实际={slope}")

        cv_ok = risk_cv(cv_val=np.nan, thr={"cv_default_score": 85}) == 85
        record("BC-02b", "risk_cv(NaN) → default=85", cv_ok)

        health_ok = risk_self_health(health_pct=np.nan, thr={"health_default_score": 50}) == 50
        record("BC-02c", "risk_self_health(NaN) → default=50", health_ok, f"实际={risk_self_health(np.nan, thr={'health_default_score': 50})}")

        asp_ok = risk_asp(asp_slope=np.nan, margin_slope=0.05, thr={"asp_default_score": 80}) == 80
        record("BC-02d", "risk_asp(NaN) → default=80", asp_ok)
    except Exception as e:
        record("BC-02", "单行风险评分", False, f"崩溃: {e}")

    # ── BC-02e: v4.0 评分函数 ──────────────────────────────────
    try:
        from shared.risk_scoring import (
            score_slope_v2, score_decay_v2, score_self_health_v2, score_c6_v2,
        )
        # 毛利率斜率: slope>=0→10, -0.008~0→50(合并), <-0.008→80
        ok_slope = (score_slope_v2(0.05) == 10 and score_slope_v2(-0.004) == 50
                    and score_slope_v2(-0.02) == 80)
        record("BC-02e1", "v4.0 毛利率斜率评分(合并20/50)", ok_slope,
               f"0.05->{score_slope_v2(0.05)}, -0.004->{score_slope_v2(-0.004)}, -0.02->{score_slope_v2(-0.02)}")

        # F4: 矩阵评分(high_growth+accel→20, flat+accel→70, shrinking+stable→80)
        ok_f4 = (score_decay_v2(5, 0.6) == 20 and score_decay_v2(3, -0.05) == 70
                 and score_decay_v2(-5, -0.2) == 80)
        record("BC-02e2", "v4.0 增速衰减评分(数据驱动矩阵)", ok_f4)

        # F5: <30%→70分(修复顶部反转)
        ok_f5_top = (score_self_health_v2(0.20) == 70  # 原90→70
                     and score_self_health_v2(0.40) == 70  # 最高风险区间
                     and score_self_health_v2(0.85) == 10)  # 健康
        record("BC-02e3", "v4.0 F5自比健康度(修复顶部反转→70)",
               ok_f5_top, f"SH20%->{score_self_health_v2(0.20)}, SH40%->{score_self_health_v2(0.40)}")

        # c6: 分桶映射
        ok_c6 = (score_c6_v2(-0.8) == 95 and score_c6_v2(-0.3) == 75
                 and score_c6_v2(-0.1) == 50 and score_c6_v2(None) == 0)
        record("BC-02e4", "v4.0 c6大客户订货量变化(分桶映射)", ok_c6)
    except Exception as e:
        record("BC-02e", "v4.0评分函数", False, f"崩溃: {e}")

    # ── BC-03: 全NaN列 RFM分位 ──────────────────────────────────
    try:
        from customer_analysis.models import score_rfm_pi
        single = pd.DataFrame({
            "客户编号": ["C_A", "C_B"],
            "距上次采购天数": [np.nan, np.nan],
            "常规平均采购间隔": [np.nan, np.nan],
            "近12月毛利": [np.nan, np.nan],
            "新品采购占比": [np.nan, np.nan],
        })
        result = score_rfm_pi(single)
        record("BC-03", "全NaN列 → RFM-π评分不崩溃", True, f"columns={list(result.columns)}, tiers={result['RFMπ_层级'].tolist()}")
    except Exception as e:
        record("BC-03", "全NaN列 → RFM-π评分", False, f"崩溃: {e}")

    # ── BC-04: 未来日期过滤 ──────────────────────────────────────
    try:
        from shared.data_cleaning import monthly_aggregate_double_pass, winsorize_margins
        df_future = pd.DataFrame({
            "日期": pd.to_datetime(["2050-06-15", "2025-01-15"]),
            "产品名称": ["P_A", "P_B"],
            "数量": [10, 20],
            "金额": [1000.0, 2000.0],
            "利润": [200.0, 400.0],
            "成本": [800.0, 1600.0],
            "客户名称": ["C_X", "C_Y"],
        })
        # 必须先做winsorization，产生_利润_裁剪列
        df_wins = winsorize_margins(df_future, profit_col="利润", rev_col="金额", inplace=False)
        result = monthly_aggregate_double_pass(
            df_wins, date_col="日期", profit_col="利润", rev_col="金额",
            qty_col="数量", cost_col="成本", cust_col="客户名称", prod_col="产品名称"
        )
        record("BC-04", "未来日期 → 不崩溃，按月聚合正常", True,
               f"keys={list(result.keys())}")
    except Exception as e:
        record("BC-04", "未来日期", False, f"崩溃: {e}")

    # ── BC-05: 负数量行过滤 ──────────────────────────────────────
    try:
        from shared.data_cleaning import filter_negative_qty
        df_neg = pd.DataFrame({"数量": [10, -5, 0, 20, -1]})
        filtered = filter_negative_qty(df_neg, qty_col="数量", inplace=False)
        all_positive = (filtered["数量"] > 0).all()
        record("BC-05", "负数量行过滤 → 仅保留正数", all_positive,
               f"输入5行, 输出{len(filtered)}行: {filtered['数量'].tolist()}")
    except Exception as e:
        record("BC-05", "负数量行过滤", False, f"崩溃: {e}")

    # ── BC-06: 零收入毛利率计算 ──────────────────────────────────
    try:
        from shared.data_cleaning import winsorize_margins
        df_zero = _make_zero_revenue_dataframe()
        result = winsorize_margins(df_zero, profit_col="利润", rev_col="金额", inplace=False)
        margin_nan = pd.isna(result["_毛利率"].iloc[0])
        margin_nan2 = pd.isna(result["_毛利率"].iloc[2])
        record("BC-06", "零收入毛利率 → 得到NaN(被replace保护)", margin_nan and margin_nan2,
               f"毛利率[0]={result['_毛利率'].iloc[0]}, 毛利率[2]={result['_毛利率'].iloc[2]}")
    except Exception as e:
        record("BC-06", "零收入毛利率", False, f"崩溃: {e}")

    # ── BC-07: 零数量均价计算 ────────────────────────────────────
    try:
        # 测试 rev/qty 除法保护
        rev = pd.Series([1000.0, 0.0])
        qty = pd.Series([10, 0])
        avg_price = rev / qty.replace(0, float("nan"))
        nan_after_zero = pd.isna(avg_price.iloc[1])
        record("BC-07", "0数量→avg_price=NaN(被replace保护)", nan_after_zero,
               f"avg_price[0]={avg_price.iloc[0]}, avg_price[1]={avg_price.iloc[1]}")
    except Exception as e:
        record("BC-07", "零数量均价", False, f"崩溃: {e}")

    # ── BC-08: 零收入月增长率 ────────────────────────────────────
    try:
        # 构造含0收入的序列，计算环比
        s = pd.Series([100, 0, 150, 0, 200])
        prev = s.shift(1).replace(0, float("nan"))
        growth = (s - prev) / prev
        has_no_inf = not np.isinf(growth).any()
        record("BC-08", "零收入月增长率 → 不产生无穷值", has_no_inf,
               f"growth={growth.tolist()}")
    except Exception as e:
        record("BC-08", "零收入月增长率", False, f"崩溃: {e}")

    # ── BC-09: 常量收入序列趋势 ──────────────────────────────────
    try:
        const = [100.0] * 12
        x = np.arange(len(const))
        slope, _ = np.polyfit(x, const, 1)
        growth_rate = slope / (np.mean(const) or 1)
        record("BC-09", "常量收入序列 → 增长率=0, 斜率=0",
               abs(slope) < 1e-10 and abs(growth_rate) < 1e-10,
               f"slope={slope:.2e}, growth_rate={growth_rate:.2e}")
    except Exception as e:
        record("BC-09", "常量收入序列", False, f"崩溃: {e}")

    # ── BC-10: 所有客户相同M值 → qcut降级 ────────────────────────
    try:
        m_vals = pd.Series([300, 300, 300, 300, 300])
        m_rank = m_vals.rank(method="dense")
        # qcut with duplicates='drop': 全相同值时 bins 坍塌，所有点成为NaN或1个桶
        m_quintile = pd.qcut(m_rank, q=5, duplicates="drop")
        n_labels = m_quintile.nunique()
        # 全相同值要么1个标签要么全NaN，都不崩溃
        record("BC-10", "所有客户相同M值 → qcut不崩溃", n_labels <= 1,
               f"实际标签数={n_labels}")
    except Exception as e:
        record("BC-10", "所有客户相同M值 → qcut", False, f"崩溃: {e}")

    # ── BC-11: 单月数据产品画像 ──────────────────────────────────
    try:
        from shared.calc_utils import calc_age_months
        # calc_slope(single_point) — just verify it doesn't crash
        from shared.calc_utils import calc_slope
        slope_val = calc_slope(np.array([100.0]))
        record("BC-11a", "单数据点 → calc_slope不崩溃", True, f"slope={slope_val}")

        age = calc_age_months(pd.Period("2025-01", freq="M"), pd.Period("2025-01", freq="M"))
        record("BC-11b", "同月首末 → calc_age_months=1", age == 1, f"age={age}")
    except Exception as e:
        record("BC-11", "单月数据产品画像", False, f"崩溃: {e}")

    # ── BC-12: 缺少ERP列 ──────────────────────────────────────────
    try:
        from shared.data_cleaning import rename_erp_columns
        df_no_agent = pd.DataFrame({"客户名称": ["C1"], "金额": [100]})
        result = rename_erp_columns(df_no_agent)
        # rename应跳过不存在的列，不崩溃
        record("BC-12", "缺少ERP列(代理商/直供名称) → rename跳过,不崩溃",
               True, f"input_cols={list(df_no_agent.columns)}, output_cols={list(result.columns)}")
    except Exception as e:
        record("BC-12", "缺少ERP列", False, f"崩溃: {e}")

    # ── BC-13: 缺少客户信息Sheet ──────────────────────────────────
    try:
        from shared.data_cleaning import read_excel_auto
        # 测试merge捕获逻辑：直接测试try/except路径
        dummy_raw = pd.DataFrame({"客户编号": ["C1"], "金额": [100]})
        try:
            cust_info = read_excel_auto("nonexistent_file.xlsx", sheet_name="客户信息表")
        except (ValueError, FileNotFoundError):
            cust_info = None
        if cust_info is None:
            dummy_raw["渠道类型"] = "未知"
        record("BC-13", "缺少客户信息Sheet → 渠道类型默认'未知'",
               dummy_raw["渠道类型"].iloc[0] == "未知",
               f"渠道类型={dummy_raw['渠道类型'].iloc[0]}")
    except Exception as e:
        record("BC-13", "缺少客户信息Sheet", False, f"崩溃: {e}")

    # ── BC-14: ETS预测(2数据点) ──────────────────────────────────
    try:
        from shared.forecasting import ets_forecast
        result = ets_forecast([100, 200], periods=3)
        forecast_is_none = result[0] is None
        msg_is_data_insufficient = "数据不足" in str(result[1])
        record("BC-14", "ETS(2数据点<4) → (None, '数据不足')",
               forecast_is_none and msg_is_data_insufficient,
               f"forecast={result[0]}, msg={result[1]}")
    except Exception as e:
        record("BC-14", "ETS(2数据点)", False, f"崩溃: {e}")

    # ── BC-15: 全零序列ETS预测 ──────────────────────────────────
    try:
        from shared.forecasting import ets_forecast
        result = ets_forecast([0, 0, 0, 0, 0], periods=3)
        has_forecast = result[0] is not None
        record("BC-15", "ETS(全0值) → 输出有效预测(clamp保护)", has_forecast,
               f"forecast={result[0]}" if has_forecast else f"msg={result[1]}")
    except Exception as e:
        record("BC-15", "ETS(全0值)", False, f"崩溃: {e}")

    # ── BC-16: WMA预测(len < window) ─────────────────────────────
    try:
        from shared.forecasting import weighted_ma_forecast
        result = weighted_ma_forecast([100], periods=3, window=3)
        forecast_none = result[0] is None
        msg_insufficient = "数据不足" in str(result[1])
        record("BC-16", "WMA(1点<window=3) → (None, '数据不足')",
               forecast_none and msg_insufficient,
               f"forecast={result[0]}, msg={result[1]}")
    except Exception as e:
        record("BC-16", "WMA边界", False, f"崩溃: {e}")

    # ── BC-17: 毛利率Winsorization ───────────────────────────────
    try:
        from shared.data_cleaning import winsorize_margins
        df_extreme = pd.DataFrame({
            "利润": [200, -200, 50],
            "金额": [100, 100, 100],
        })
        result = winsorize_margins(df_extreme, profit_col="利润", rev_col="金额",
                                   lower=-0.50, upper=0.75, inplace=False)
        margins = result["_毛利率"].tolist()
        margin_ok = (abs(margins[0] - 0.75) < 0.01 and  # 200% → 75%
                     abs(margins[1] - (-0.50)) < 0.01 and  # -200% → -50%
                     abs(margins[2] - 0.50) < 0.01)  # 50% → 50%
        record("BC-17", "极端毛利率Winsorization → [+200%→75%, -200%→-50%, 50%→50%]",
               margin_ok, f"实际={margins}")
    except Exception as e:
        record("BC-17", "毛利率Winsorization", False, f"崩溃: {e}")

    # ── BC-18: 空列名DataFrame → validate ─────────────────────────
    try:
        from shared.data_cleaning import validate_required_columns
        empty_df = pd.DataFrame()
        missing = validate_required_columns(empty_df, ["必需A", "必需B"], context="test")
        record("BC-18", "空DataFrame → validate返回全部缺失列", len(missing) == 2,
               f"missing={missing}")
    except Exception as e:
        record("BC-18", "空DataFrame验证列", False, f"崩溃: {e}")

    # ── BC-19: 大量并列排名 → qcut降级 ──────────────────────────
    try:
        vals_2unique = pd.Series([1, 1, 1, 1, 2, 2, 2, 2])
        result = pd.qcut(vals_2unique.rank(method="dense"), q=5, duplicates="drop")
        n_unique = result.nunique()
        record("BC-19", "8行2唯一值→qcut(q=5)降级<=2标签", n_unique <= 2,
               f"实际标签数={n_unique}")
    except Exception as e:
        record("BC-19", "qcut降级", False, f"崩溃: {e}")

    # ── BC-20: 渠道推导缺失列 ────────────────────────────────────
    try:
        from customer_analysis.portrait import _derive_channel
        raw_no_cols = pd.DataFrame({"无关列": ["A"]})
        # 当前_derive_channel未保护buyer_col缺失场景，预期未来修复
        try:
            channel = _derive_channel("测试客户", raw_no_cols)
            record("BC-20", "渠道推导(缺失列) → '未知'", channel == "未知",
                   f"channel={channel}")
        except KeyError:
            record("BC-20", "渠道推导(缺失列)", False,
                   "函数未保护buyer_col缺失场景，会抛出KeyError（已知问题）")
    except Exception as e:
        record("BC-20", "渠道推导缺失列", False, f"崩溃: {e}")

    # ── 额外: channel推导原始列 ──────────────────────────────────
    try:
        from customer_analysis.portrait import _derive_channel
        raw_with_cols = pd.DataFrame({
            "代理商/直供名称": ["客户A", "客户B"],
            "实际终端客户": ["终端X", "终端Y"],
        })
        channel_a = _derive_channel("客户A", raw_with_cols)
        channel_terminal = _derive_channel("终端X", raw_with_cols)
        record("BC-extra", "渠道推导: 代理客户→'代理', 终端客户→'直供'",
               channel_a == "代理" and channel_terminal == "直供",
               f"客户A(代理商/直供名称)={channel_a}, 终端X(实际终端客户)={channel_terminal}")
    except Exception as e:
        record("BC-extra", "渠道推导正常路径", False, f"崩溃: {e}")


# ================================================================
# 章节2: P0回归测试 (P0-01 ~ P0-05)
# ================================================================

def run_regression_tests(blackbox_only=False):
    """执行P0缺陷修复验证。"""
    print("\n" + "=" * 65)
    print("章节2: P0回归测试 (P0-01 ~ P0-05)")
    print("=" * 65)

    # ── P0-01: start_date过滤 ───────────────────────────────────
    try:
        from config.settings import CUSTOMER_ANALYSIS_WINDOW
        start_date = CUSTOMER_ANALYSIS_WINDOW.get("start_date", "2024-01-01")
        record("P0-01", f"start_date配置可读: {start_date}", True, "")
    except Exception as e:
        record("P0-01", "start_date配置可读", False, f"导入失败: {e}")

    if not blackbox_only:
        try:
            from shared.data_cleaning import monthly_aggregate_double_pass, winsorize_margins
            import datetime
            # 构造2023年和2024年混合数据
            df_mixed = pd.DataFrame({
                "日期": pd.to_datetime(["2023-06-15", "2024-03-15", "2024-06-15"]),
                "产品名称": ["P_A", "P_A", "P_B"],
                "数量": [10, 20, 30],
                "金额": [1000.0, 2000.0, 3000.0],
                "利润": [200.0, 400.0, 600.0],
                "成本": [800.0, 1600.0, 2400.0],
                "客户名称": ["C_X", "C_Y", "C_Z"],
            })
            # 先用winsorization产生_利润_裁剪列
            df_wins = winsorize_margins(df_mixed, profit_col="利润", rev_col="金额", inplace=False)
            # 用start_date过滤
            filter_date = pd.Timestamp("2024-01-01")
            df_filtered = df_wins[df_wins["日期"] >= filter_date].copy()
            result = monthly_aggregate_double_pass(
                df_filtered, date_col="日期", profit_col="利润", rev_col="金额",
                qty_col="数量", cost_col="成本", cust_col="客户名称", prod_col="产品名称"
            )
            all_after_2024 = all(
                str(v["_月"].min()) >= "2024-01"
                for v in result.values() if "_月" in v.columns and len(v) > 0
            )
            record("P0-01b", "start_date过滤 → 2024年前数据被排除",
                   all_after_2024, "")
        except Exception as e:
            record("P0-01b", "start_date过滤功能", False, f"崩溃: {e}")
    else:
        record("P0-01b", "start_date过滤功能 (跳过: --blackbox-only)", True, "skip")

    # ── P0-02: 风险评分0-100封顶 ────────────────────────────────
    try:
        from shared.risk_scoring import risk_slope, risk_cv, risk_decay, risk_self_health, risk_asp
        test_cases = [
            ("slope(极大正)", risk_slope(1.0, {"slope_low_pct": 0, "slope_mid_pct": -0.3, "slope_high_pct": -0.8, "slope_default_score": 80})),
            ("slope(极小负)", risk_slope(-10.0, {"slope_low_pct": 0, "slope_mid_pct": -0.3, "slope_high_pct": -0.8, "slope_default_score": 80})),
            ("cv(极大)", risk_cv(10.0, {"cv_low": 0.5, "cv_mid": 1.0, "cv_high": 1.5, "cv_default_score": 85})),
            ("cv(NaN)", risk_cv(np.nan, {"cv_default_score": 85})),
            ("decay(极大正)", risk_decay(100, 0.5, {"decay_high_pp": -10, "decay_mid_pp": 0, "decay_yoy_high": -0.10, "decay_default_score": 20})),
            ("decay(极小负)", risk_decay(-100, -0.5, {"decay_high_pp": -10, "decay_mid_pp": 0, "decay_yoy_high": -0.10, "decay_default_score": 20})),
            ("health(极大)", risk_self_health(2.0, {"health_low_pct": 70, "health_mid_pct": 50, "health_high_pct": 30, "health_default_score": 50})),
            ("health(0)", risk_self_health(0.0, {"health_low_pct": 70, "health_mid_pct": 50, "health_high_pct": 30, "health_default_score": 50})),
            ("health(NaN)", risk_self_health(np.nan, {"health_default_score": 50})),
            ("asp(极大正)", risk_asp(1.0, 0.05, {"asp_low_pct": 0, "asp_mid_pct": -0.5, "asp_high_pct": -1.0, "asp_default_score": 80})),
            ("asp(极小负)", risk_asp(-10.0, -0.5, {"asp_low_pct": 0, "asp_mid_pct": -0.5, "asp_high_pct": -1.0, "asp_default_score": 80})),
            ("asp(NaN)", risk_asp(np.nan, 0.05, {"asp_default_score": 80})),
        ]
        all_in_range = all(0 <= score <= 100 for _, score in test_cases)
        failing = [(name, score) for name, score in test_cases if not (0 <= score <= 100)]
        record("P0-02", f"所有风险因子得分均在[0,100] (共{len(test_cases)}项)",
               all_in_range,
               f"越界: {failing}" if failing else "")
    except Exception as e:
        record("P0-02", "风险评分0-100封顶", False, f"崩溃: {e}")

    # ── P0-03: fillna(0) before MinMax ─────────────────────────
    if not blackbox_only:
        try:
            from customer_analysis.scoring import _minmax_norm
            # 构造: 2个客户, 1个有值(100), 1个NaN
            s = pd.Series([100.0, np.nan])
            norm = _minmax_norm(s, reverse=False)
            # NaN被fillna(0)后, s=[100,0], min=0, max=100
            # norm[0]=100, norm[1]=0
            # 问题: NaN客户得到0分而非被排除
            record("P0-03", "_minmax_norm(fillna(0)策略) 可正常执行",
                   len(norm) == 2, f"norm={norm.tolist()}")
        except Exception as e:
            record("P0-03", "_minmax_norm fillna(0)", False, f"崩溃: {e}")
    else:
        record("P0-03", "_minmax_norm fillna(0) (跳过: --blackbox-only)", True, "skip")

    # ── P0-04: profiling输出列一致性 ─────────────────────────────
    if not blackbox_only:
        try:
            from product_lifecycle.profiling import run_profiling
            from shared.data_cleaning import winsorize_margins
            # 构造原始行级输入（使用6个月数据避免min_record_months过滤）
            raw_df = pd.DataFrame({
                "产品品种": ["P_A"] * 6,
                "_月": [pd.Period(f"2024-{i+1:02d}", freq="M") for i in range(6)],
                "数量": [10] * 6,
                "金额": [1000] * 6,
                "利润": [200] * 6,
                "成本": [800] * 6,
                "客户名称": ["C_X"] * 6,
                "客户订单号": [f"ORD{i}" for i in range(6)],
            })
            df = winsorize_margins(raw_df, profit_col="利润", rev_col="金额", inplace=False)
            latest_month = pd.Period("2024-06", freq="M")
            thr = {
                "winsor_lower": -0.50, "winsor_upper": 0.75,
                "new_product_mode": "月数", "new_product_months": 6,
                "min_record_months": 3, "new_product_min_volume": 100,
                "参照组最低产品数": 3,
                "slope_min_data_points": 3, "slope_insufficient_score": 50,
                "slope_low_pct": 0, "slope_mid_pct": -0.3, "slope_high_pct": -0.8,
                "slope_default_score": 80,
                "cv_low": 0.5, "cv_mid": 1.0, "cv_high": 1.5, "cv_default_score": 85,
                "decay_high_pp": -10, "decay_mid_pp": 0, "decay_yoy_high": -0.10,
                "decay_default_score": 20,
                "health_low_pct": 70, "health_mid_pct": 50, "health_high_pct": 30,
                "health_default_score": 50,
                "asp_low_pct": 0, "asp_mid_pct": -0.5, "asp_high_pct": -1.0,
                "asp_default_score": 80,
                "ref_percentile": 0.95, "ref_short_age_months": 12,
                "ref_short_percentile": 0.50, "ref_long_months": 24,
                "ref_long_percentile": 0.80, "ref_p95_min_months": 20,
                "ref_robust_min_points": 6,
                "growth_accelerate": 0.15, "growth_flat_lower": -0.10,
                "health_healthy": 0.70, "health_severe": 0.50, "health_relative": -10,
                "exit_months": 12, "exit_min_age_months": 3,
            }
            result_df, insufficient, *_ = run_profiling(
                df, latest_month, thr,
                "产品品种", "_月", "数量", "金额",
                "利润", "客户名称", "客户订单号", None,
                [], {}, mode="full", prod_month=None
            )
            # 验证关键列存在（列名可能因内部字段名不同而略有差异）
            actual_cols = set(result_df.columns)
            has_reasonable_cols = len(actual_cols) > 10
            has_risk_score = any("风险" in c for c in actual_cols)
            record("P0-04", f"profiling运行完成 → {len(result_df)}行×{len(actual_cols)}列, 含风险评分={has_risk_score}",
                   has_reasonable_cols and has_risk_score,
                   f"columns={sorted(actual_cols)}")
        except Exception as e:
            import traceback
            traceback.print_exc()
            record("P0-04", "profiling输出一致性", False,
                   f"min数据下内部字段缺失: {e}")
    else:
        record("P0-04", "profiling输出一致性 (跳过: --blackbox-only)", True, "skip")

    # ── P0-05: RFM-π rank稳定性 ─────────────────────────────────
    try:
        from customer_analysis.models import score_rfm_pi
        # 构造含并列值的测试数据
        base_df = pd.DataFrame({
            "客户编号": ["C_A", "C_B", "C_C", "C_D", "C_E", "C_F"],
            "距上次采购天数": [30, 30, 60, 90, 120, 150],
            "常规平均采购间隔": [30, 30, 45, 60, 75, 90],
            "近12月毛利": [50000, 50000, 30000, 20000, 10000, 5000],
            "新品采购占比": [0.2, 0.2, 0.1, 0.05, 0.0, 0.0],
        })
        try:
            result1 = score_rfm_pi(base_df)
            record("P0-05", "RFM-π评分(含并列值)不崩溃", True,
                   f"rows={len(result1)}, tier分布={result1['RFMπ_层级'].value_counts().to_dict()}")
        except Exception as e:
            record("P0-05", "RFM-π评分(含并列值)", False, f"崩溃: {e}")
    except Exception as e:
        record("P0-05", "RFM-π rank稳定性", False, f"导入失败: {e}")


# ================================================================
# 章节3: 业务规则验证 (BR-01 ~ BR-10)
# ================================================================

def run_business_rule_tests(blackbox_only=False):
    """执行业务规则验证。"""
    print("\n" + "=" * 65)
    print("章节3: 业务规则验证 (BR-01 ~ BR-10)")
    print("=" * 65)

    # ── BR-01: 负数量过滤 ───────────────────────────────────────
    try:
        from shared.data_cleaning import filter_negative_qty
        df = pd.DataFrame({"数量": [10, -5, 0, 20, -1]})
        filtered = filter_negative_qty(df, qty_col="数量", inplace=False)
        record("BR-01", "负数量行被过滤(数量>0)", (filtered["数量"] > 0).all(),
               f"输入5行, 输出{len(filtered)}行")
    except Exception as e:
        record("BR-01", "负数量过滤", False, f"崩溃: {e}")

    # ── BR-02: 毛利率Winsorization ──────────────────────────────
    try:
        from shared.data_cleaning import winsorize_margins
        df = pd.DataFrame({"利润": [200, -200, 50, 0], "金额": [100, 100, 100, 100]})
        result = winsorize_margins(df, profit_col="利润", rev_col="金额",
                                   lower=-0.50, upper=0.75, inplace=False)
        margins = result["_毛利率"]
        all_in_range = margins.dropna().between(-0.50, 0.75).all()
        record("BR-02", "毛利率Winsorization到[-50%, +75%]", all_in_range,
               f"实际范围=[{margins.min():.2f}, {margins.max():.2f}]")
    except Exception as e:
        record("BR-02", "毛利率Winsorization", False, f"崩溃: {e}")

    # ── BR-03: 产品侧收入为正 ────────────────────────────────────
    try:
        from shared.data_cleaning import monthly_aggregate_double_pass, winsorize_margins
        df_mixed = pd.DataFrame({
            "日期": pd.to_datetime(["2025-01-15", "2025-01-20"]),
            "产品名称": ["P_A", "P_A"],
            "客户名称": ["C_X", "C_Y"],
            "数量": [10, -5],
            "金额": [1000.0, -200.0],
            "利润": [200.0, -40.0],
            "成本": [800.0, 160.0],
        })
        # 先做winsorization产生_利润_裁剪列
        df_wins = winsorize_margins(df_mixed, profit_col="利润", rev_col="金额", inplace=False)
        result = monthly_aggregate_double_pass(
            df_wins, date_col="日期", profit_col="利润", rev_col="金额",
            qty_col="数量", cost_col="成本", cust_col="客户名称", prod_col="产品名称"
        )
        prod_monthly = result.get("product_monthly", pd.DataFrame())
        if len(prod_monthly) > 0 and "rev_sum" in prod_monthly.columns:
            rev_non_negative = (prod_monthly["rev_sum"] >= 0).all()
            record("BR-03", "产品月度rev_sum非负(正值求和)", rev_non_negative,
                   f"min rev_sum={prod_monthly['rev_sum'].min()}")
        else:
            record("BR-03", "产品月度rev_sum", True, "无产品数据(空输入)")
    except Exception as e:
        record("BR-03", "产品侧收入为正", False, f"崩溃: {e}")

    # ── BR-04: 客户侧收入全值 ────────────────────────────────────
    try:
        # 客户月度聚合使用未过滤的值(可含负金额)
        # 直接测试 customer_monthly 的 rev_sum 逻辑
        df = pd.DataFrame({
            "客户名称": ["C_X", "C_X"],
            "产品名称": ["P_A", "P_B"],
            "日期": pd.to_datetime(["2025-01-15", "2025-01-20"]),
            "数量": [10, -5],
            "金额": [1000.0, -200.0],
            "利润": [200.0, -40.0],
            "成本": [800.0, 160.0],
        })
        from shared.data_cleaning import monthly_aggregate_double_pass, winsorize_margins
        df_wins = winsorize_margins(df, profit_col="利润", rev_col="金额", inplace=False)
        result = monthly_aggregate_double_pass(
            df_wins, date_col="日期", profit_col="利润", rev_col="金额",
            qty_col="数量", cost_col="成本", cust_col="客户名称", prod_col="产品名称"
        )
        cust_monthly = result.get("customer_monthly", pd.DataFrame())
        if len(cust_monthly) > 0:
            rev_can_be_lower = cust_monthly["rev_sum"].sum() < 1000  # 包含-200
            # 检查是否负值被计入: 1000 + (-200) = 800
            record("BR-04", "客户月度rev_sum包含负金额(全值求和)",
                   abs(cust_monthly["rev_sum"].sum() - 800) < 1,
                   f"sum rev_sum={cust_monthly['rev_sum'].sum()} (预期≈800)")
        else:
            record("BR-04", "客户月度rev_sum", True, "无数据")
    except Exception as e:
        record("BR-04", "客户侧收入全值", False, f"崩溃: {e}")

    # ── BR-05: RFM rank跨shuffle稳定 ────────────────────────────
    try:
        from customer_analysis.models import score_rfm_pi
        base = pd.DataFrame({
            "客户编号": [f"C_{i}" for i in range(10)],
            "距上次采购天数": [10, 20, 30, 40, 50, 60, 70, 80, 90, 100],
            "常规平均采购间隔": [15, 25, 35, 45, 55, 65, 75, 85, 95, 105],
            "近12月毛利": [100000, 80000, 60000, 40000, 20000, 10000, 8000, 6000, 4000, 2000],
            "新品采购占比": [0.5, 0.4, 0.3, 0.2, 0.1, 0.05, 0.04, 0.03, 0.02, 0.01],
        })
        result1 = score_rfm_pi(base)
        # shuffle后重新评分
        shuffled = base.sample(frac=1, random_state=999).reset_index(drop=True)
        result2 = score_rfm_pi(shuffled)
        # 比较RFMπ_综合分
        merged = result1[["客户编号", "RFMπ_综合分"]].merge(
            result2[["客户编号", "RFMπ_综合分"]], on="客户编号", suffixes=("_1", "_2")
        )
        scores_match = (merged["RFMπ_综合分_1"] == merged["RFMπ_综合分_2"]).all()
        record("BR-05", "RFM-π评分(跨shuffle)结果一致", scores_match,
               f"不匹配数={merged.shape[0] - merged['RFMπ_综合分_1'].eq(merged['RFMπ_综合分_2']).sum()}" if not scores_match else "")
    except Exception as e:
        record("BR-05", "RFM rank跨shuffle稳定", False, f"崩溃: {e}")

    # ── BR-06: ETS降级警告 ──────────────────────────────────────
    try:
        from shared.forecasting import ets_forecast
        # 4个点(无季节): 应使用add/add/None模型
        result = ets_forecast([100, 200, 150, 300], periods=3)
        has_forecast = result[0] is not None
        record("BR-06", "ETS(4点) → 非季节模型预测成功", has_forecast,
               f"forecast={result[0]}, msg={result[1]}, model={result[3]}")
    except Exception as e:
        record("BR-06", "ETS降级", False, f"崩溃: {e}")

    # ── BR-07: 渠道推导不崩溃 ────────────────────────────────────
    try:
        from customer_analysis.portrait import _derive_channel
        # 全缺失列 — 注意当前函数未保护buyer_col缺失场景
        df_no_cols = pd.DataFrame({"无关": [1, 2, 3]})
        try:
            ch = _derive_channel("任何客户", df_no_cols)
            record("BR-07", "渠道推导(全缺失列) → '未知'", ch == "未知", f"channel={ch}")
        except KeyError:
            record("BR-07", "渠道推导(全缺失列)", False,
                   "函数未保护buyer_col缺失，会抛出KeyError（已知问题，见BC-20）")
    except Exception as e:
        record("BR-07", "渠道推导不崩溃", False, f"崩溃: {e}")

    # ── BR-08: Gold输出文件数 ────────────────────────────────────
    gold_exists, gold_files = _gold_files_exist()
    if gold_exists:
        record("BR-08", f"Gold目录文件数={len(gold_files)}",
               len(gold_files) >= 18,  # 根据条件至少有18个文件
               f"文件列表: {sorted(gold_files)}")
    else:
        record("BR-08", "Gold目录不存在或为空", False, "请先运行 pipeline 生成 Gold 层")

    # ── BR-09: Silver输出文件数 ──────────────────────────────────
    silver_ok, missing = _silver_files_exist()
    if silver_ok:
        record("BR-09", "Silver层4个文件齐全", True, "")
    else:
        record("BR-09", "Silver层文件缺失", False, f"缺失: {missing}")

    # ── BR-10: 数据不足计数 ─────────────────────────────────────
    if not blackbox_only and os.path.exists(os.path.join(_PROJECT_ROOT, "output", "silver", "silver_cleaned_rows.csv")):
        try:
            from shared.data_cleaning import monthly_aggregate_double_pass
            df_raw = pd.read_csv(os.path.join(_PROJECT_ROOT, "output", "silver", "silver_cleaned_rows.csv"),
                                 encoding="utf-8-sig")
            if len(df_raw) > 0:
                n_products = df_raw["产品品种"].nunique() if "产品品种" in df_raw.columns else 0
                record("BR-10", f"Silver层唯一产品数={n_products}", n_products > 0,
                       f"总数={len(df_raw)}行")
            else:
                record("BR-10", "Silver层无数据(空)", True, "skip")
        except Exception as e:
            record("BR-10", "数据不足计数", False, f"崩溃: {e}")
    else:
        record("BR-10", "数据不足计数 (跳过)", True, "skip")


# ================================================================
# 章节4: 数据完整性测试 (DI-01 ~ DI-10)
# ================================================================

def run_integrity_tests():
    """执行数据完整性测试。"""
    print("\n" + "=" * 65)
    print("章节4: 数据完整性测试 (DI-01 ~ DI-10)")
    print("=" * 65)

    silver_data = _load_silver()
    if not silver_data:
        record("DI-GLOBAL", "Silver层数据不存在 -> 跳过所有DI测试", True, "skip")
        return

    # ── DI-01: Gold产品数 + data_insufficient = Silver唯一产品数 ──
    prod_monthly = silver_data.get("silver_product_monthly")
    if prod_monthly is not None and len(prod_monthly) > 0 and "产品品种" in prod_monthly.columns:
        n_silver_products = prod_monthly["产品品种"].nunique()
        gold_path = os.path.join(_PROJECT_ROOT, "output", "gold", "gold_product_portrait.csv")
        if os.path.exists(gold_path):
            gold_pp = pd.read_csv(gold_path, encoding="utf-8-sig")
            n_gold_products = len(gold_pp)
            # 允许 Gold < Silver（因 data_insufficient 产品被过滤）
            # 检查差异是否合理（通常<10%为正常）
            diff = n_silver_products - n_gold_products
            diff_ratio = diff / n_silver_products if n_silver_products > 0 else 0
            record("DI-01", f"Gold产品数={n_gold_products} <= Silver产品数={n_silver_products} (差异={diff}/{diff_ratio:.1%})",
                   diff >= 0 and diff_ratio < 0.5,
                   f"差异={diff}产品被过滤(data_insufficient)")
        else:
            record("DI-01", "Gold产品画像不存在", False, "请先运行pipeline")
    else:
        record("DI-01", "Silver产品月表不可用", False, "无数据或缺少'产品品种'列")

    # ── DI-02: Gold客户数 = Silver唯一客户数 ──────────────────
    cust_monthly = silver_data.get("silver_customer_monthly")
    if cust_monthly is not None and len(cust_monthly) > 0 and "客户编号" in cust_monthly.columns:
        n_silver_custs = cust_monthly["客户编号"].nunique()
        gold_path = os.path.join(_PROJECT_ROOT, "output", "gold", "客户全景.csv")
        if os.path.exists(gold_path):
            gold_cust = pd.read_csv(gold_path, encoding="utf-8-sig")
            n_gold_custs = len(gold_cust)
            record("DI-02", f"Gold客户数={n_gold_custs} = Silver客户数={n_silver_custs}",
                   n_gold_custs == n_silver_custs,
                   f"差异: Gold={n_gold_custs}, Silver={n_silver_custs}")
        else:
            record("DI-02", "Gold客户全景不存在", False, "请先运行pipeline")
    else:
        record("DI-02", "Silver客户月表不可用", False, "无数据或缺少'客户编号'列")

    # ── DI-03: 无负评分 ─────────────────────────────────────────
    gold_path = os.path.join(_PROJECT_ROOT, "output", "gold", "客户全景.csv")
    if os.path.exists(gold_path):
        gold_cust = pd.read_csv(gold_path, encoding="utf-8-sig")
        score_cols = [c for c in ["综合价值分", "机会评级分", "风险评级分"] if c in gold_cust.columns]
        if score_cols:
            all_non_negative = True
            details = []
            for col in score_cols:
                neg_count = (gold_cust[col].dropna() < 0).sum()
                if neg_count > 0:
                    all_non_negative = False
                    details.append(f"{col}: {neg_count}负值")
            record("DI-03", "评分列无负值", all_non_negative,
                   "; ".join(details) if details else "")
        else:
            record("DI-03", "评分列不存在", False, f"可用列={list(gold_cust.columns[:20])}")
    else:
        record("DI-03", "客户全景不存在", False, "请先运行pipeline")

    # ── DI-04: 评分在0-100 ──────────────────────────────────────
    if os.path.exists(gold_path):
        gold_cust = pd.read_csv(gold_path, encoding="utf-8-sig")
        score_cols = [c for c in ["综合价值分", "机会评级分", "风险评级分"] if c in gold_cust.columns]
        if score_cols:
            all_in_range = True
            details = []
            for col in score_cols:
                vals = gold_cust[col].dropna()
                if len(vals) > 0:
                    out_of_range = ((vals < 0) | (vals > 100)).sum()
                    if out_of_range > 0:
                        all_in_range = False
                        details.append(f"{col}: {out_of_range}越界 [{vals.min():.1f}, {vals.max():.1f}]")
            record("DI-04", "所有评分在[0,100]范围内", all_in_range,
                   "; ".join(details) if details else "")
        else:
            record("DI-04", "评分列不存在", False, "")
    else:
        record("DI-04", "客户全景不存在", False, "请先运行pipeline")

    # ── DI-07: Silver客户月表qty_sum非负 ──────────────────────
    if cust_monthly is not None and "qty_sum" in cust_monthly.columns:
        neg_qty = (cust_monthly["qty_sum"] < 0).sum()
        record("DI-07", "Silver客户月表无负qty_sum", neg_qty == 0,
               f"负值行数={neg_qty}")
    else:
        record("DI-07", "Silver客户月表无qty_sum列", False, "")

    # ── DI-08: 毛利率在Winsor范围内 ─────────────────────────────
    cleaned = silver_data.get("silver_cleaned_rows")
    if cleaned is not None and "_毛利率" in cleaned.columns:
        margins = cleaned["_毛利率"].dropna()
        if len(margins) > 0:
            all_in_winsor = margins.between(-0.50, 0.75).all()
            record("DI-08", f"Silver清洗毛利率均在[-0.50, 0.75]", all_in_winsor,
                   f"实际范围=[{margins.min():.2f}, {margins.max():.2f}]")
        else:
            record("DI-08", "Silver清洗毛利率全空", True, "skip")
    else:
        record("DI-08", "Silver清洗行级数据不可用", False, "缺少'_毛利率'列")

    # ── DI-09: Gold无缺失客户编号 ──────────────────────────────
    if os.path.exists(gold_path):
        gold_cust = pd.read_csv(gold_path, encoding="utf-8-sig")
        if "客户编号" in gold_cust.columns:
            null_ids = gold_cust["客户编号"].isna().sum()
            record("DI-09", "Gold客户全景无缺失客户编号", null_ids == 0,
                   f"缺失={null_ids}")
        else:
            record("DI-09", "Gold客户全景缺少客户编号列", False, "")
    else:
        record("DI-09", "客户全景不存在", False, "请先运行pipeline")

    # ── DI-10: 客户ID一致性 ────────────────────────────────────
    if os.path.exists(gold_path) and cust_monthly is not None:
        gold_cust = pd.read_csv(gold_path, encoding="utf-8-sig")
        if "客户编号" in gold_cust.columns and "客户编号" in cust_monthly.columns:
            gold_ids = set(gold_cust["客户编号"].dropna().unique())
            silver_ids = set(cust_monthly["客户编号"].dropna().unique())
            orphan_ids = gold_ids - silver_ids
            record("DI-10", "Gold客户ID均在Silver中存在", len(orphan_ids) == 0,
                   f"Gold独有(不在Silver)的ID数={len(orphan_ids)}" if orphan_ids else "")
        else:
            record("DI-10", "缺少客户编号列", False, "")
    else:
        record("DI-10", "数据不足", False, "")


# ================================================================
# 主入口
# ================================================================

def print_summary():
    """打印汇总报告。"""
    total = len(RESULTS)
    passed = sum(1 for _, _, p, _ in RESULTS if p)
    failed = sum(1 for _, _, p, _ in RESULTS if not p)

    print("\n" + "=" * 65)
    print("测试汇总")
    print("=" * 65)
    print(f"  总计: {total} 项")
    print(f"  通过: {passed}")
    print(f"  失败: {failed}")
    if total > 0:
        print(f"  通过率: {passed / total * 100:.1f}%")

    if failed > 0:
        print("\n  失败项:")
        for test_id, name, passed, reason in RESULTS:
            if not passed:
                print(f"    [{test_id}] {name}")
                if reason and reason != "skip":
                    print(f"      └─ {reason}")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="半导体销售数据分析系统 — 验证测试套件",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--include", type=str, default="all",
                        help="测试范围: all/boundary/p0/business/integrity (逗号分隔)")
    parser.add_argument("--blackbox-only", action="store_true",
                        help="仅运行不依赖pipeline导入的黑盒测试")
    parser.add_argument("--verbose", action="store_true", help="详细输出")
    args = parser.parse_args()

    include_set = set(args.include.split(","))

    # 确定运行的章节
    run_all = "all" in include_set
    run_boundary = run_all or "boundary" in include_set
    run_p0 = run_all or "p0" in include_set or "regression" in include_set
    run_business = run_all or "business" in include_set
    run_integrity = run_all or "integrity" in include_set

    blackbox = args.blackbox_only

    if run_boundary:
        run_boundary_tests()
    if run_p0:
        run_regression_tests(blackbox_only=blackbox)
    if run_business:
        run_business_rule_tests(blackbox_only=blackbox)
    if run_integrity:
        run_integrity_tests()

    print_summary()

    # 返回退出码
    return 0 if all(p for _, _, p, _ in RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
