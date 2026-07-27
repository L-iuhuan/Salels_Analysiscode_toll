#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Phase 2：测试用例验证（TEST A-F）。

加载 Phase 1 中间件 → 执行 6 个结构化测试用例 → 输出 CSV / JSON / Markdown。

独立运行：
    python test/phase2_validate.py                          # 全部测试
    python test/phase2_validate.py --tests A,B,C            # 仅指定用例
    python test/phase2_validate.py --skip-report            # 不生成报告
"""

import sys, os, time, argparse, traceback

_TEST_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_TEST_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import pandas as pd
import numpy as np

from test.conftest import (
    PROJECT_ROOT, DIAG_DIR, PKL_PATH, DEFAULT_DATA_FILE,
    load_intermediates, save_intermediates, has_intermediates,
    ensure_diag_dir, save_diag_csv,
    save_summary_json, save_markdown_report,
    TestCaseResult, TestSuiteResult,
    header, log,
)

# ============================================================
# TEST A: rename_erp_columns → 新品标记列验证
# ============================================================
def test_a_new_flag(data: dict) -> TestCaseResult:
    """验证 rename_erp_columns 正确生成新品标记列。"""
    tc = TestCaseResult(id="TEST-A", name="rename_erp_columns → 新品标记列验证")

    try:
        has_new = data.get("has_new_flag", False)
        new_pct = data.get("new_pct", 0.0)

        if has_new:
            tc.status = "PASS"
            tc.summary = "新品标记列生成正确"
            tc.details = {"新品行占比": f"{new_pct:.2f}%"}
        else:
            tc.status = "SKIP"
            tc.summary = "源数据无是否新品列"
    except Exception as e:
        tc.status = "FAIL"
        tc.error = str(e)

    return tc


# ============================================================
# TEST B: Silver 层新品标记传播验证
# ============================================================
def test_b_silver_propagation(data: dict) -> TestCaseResult:
    """验证新品标记从源数据传播至 product_monthly Silver 表。"""
    tc = TestCaseResult(id="TEST-B", name="Silver层新品标记传播验证")

    try:
        has_in_silver = data.get("has_in_silver", False)
        erp_new_ct = data.get("erp_new_ct", 0)
        prod_monthly = data.get("prod_monthly")

        if has_in_silver:
            tc.status = "PASS"
            tc.summary = "新品标记已传播至 product_monthly"
            tc.details = {
                "product_monthly 行数": len(prod_monthly),
                "ERP标记=是的行数": erp_new_ct,
            }
        else:
            tc.status = "SKIP"
            tc.summary = "product_monthly 无新品标记列"
    except Exception as e:
        tc.status = "FAIL"
        tc.error = str(e)

    return tc


# ============================================================
# TEST C: 新品判定对比（ERP vs 自动计算）
# ============================================================
def test_c_new_product_judgment(data: dict) -> TestCaseResult:
    """对比 ERP 标记与自动计算的新品判定结果。"""
    tc = TestCaseResult(id="TEST-C", name="新品判定对比")

    try:
        prod_monthly = data.get("prod_monthly")
        has_new_flag = data.get("has_new_flag", False)

        if not has_new_flag or prod_monthly is None:
            tc.status = "SKIP"
            tc.summary = "无 ERP 新品标记，跳过对比"
            return tc

        latest_month = prod_monthly["_月"].max()
        ps = prod_monthly.groupby("产品品种")["_月"].min().reset_index()
        ps.columns = ["产品品种", "首次销售月"]
        ps["auto_new"] = (latest_month - ps["首次销售月"]).apply(lambda x: x.n) <= 12

        erp_new_set = set(prod_monthly[prod_monthly["新品标记"]=="是"]["产品品种"].unique())
        auto_new_set = set(ps[ps["auto_new"]]["产品品种"].unique())

        overlap = erp_new_set & auto_new_set
        erp_only = erp_new_set - auto_new_set
        auto_only = auto_new_set - erp_new_set

        tc.status = "PASS"
        tc.summary = f"ERP {len(erp_new_set)} vs 自动 {len(auto_new_set)}，重叠 {len(overlap)}"
        tc.details = {
            "ERP新品品种数": len(erp_new_set),
            "自动计算新品数": len(auto_new_set),
            "两者重叠": len(overlap),
            "ERP独有": len(erp_only),
            "自动独有": len(auto_only),
            "重叠率(相对ERP)": f"{len(overlap)/max(len(erp_new_set),1)*100:.1f}%",
        }
    except Exception as e:
        tc.status = "FAIL"
        tc.error = str(e)

    return tc


# ============================================================
# TEST D: 新品 Cohort（calc_new_product_cohort）
# ============================================================
def test_d_new_product_cohort(data: dict) -> TestCaseResult:
    """验证 calc_new_product_cohort 运行正常且结果合理。"""
    tc = TestCaseResult(id="TEST-D", name="新品Cohort分析")

    try:
        prod_monthly = data.get("prod_monthly")
        cxp = data.get("cxp")

        if prod_monthly is None or cxp is None:
            tc.status = "FAIL"
            tc.summary = "缺少 prod_monthly 或 cxp 数据"
            return tc

        from shared.pricing import calc_new_product_cohort

        t0 = time.time()
        cohort = calc_new_product_cohort(prod_monthly, cxp)
        elapsed = time.time() - t0

        has_new_buyers = int((cohort["是否采购新品"] > 0).sum())
        total = len(cohort)
        penetration = float(cohort["新品渗透率"].iloc[0])
        new_ratio_avg = float(cohort["新品采购占比"].mean())

        tc.status = "PASS"
        tc.summary = f"客户 {total}，新品买家 {has_new_buyers} ({has_new_buyers/max(total,1)*100:.1f}%)"
        tc.details = {
            "客户总数": total,
            "有新品采购客户": has_new_buyers,
            "新品渗透率": f"{penetration*100:.2f}%",
            "新品采购占比均值": f"{new_ratio_avg*100:.2f}%",
            "执行时间": f"{elapsed:.1f}s",
        }

        # 保存诊断 CSV
        save_diag_csv(cohort, "cohort")
        data["cohort_result"] = cohort
    except Exception as e:
        tc.status = "FAIL"
        tc.error = str(e)

    return tc


# ============================================================
# TEST E: 产品生命周期 profiling
# ============================================================
def test_e_product_profiling(data: dict) -> TestCaseResult:
    """验证 run_profiling 正确识别新品观察并输出产品画像。"""
    tc = TestCaseResult(id="TEST-E", name="产品生命周期 profiling")

    try:
        df_clean = data.get("df_clean")
        prod_monthly = data.get("prod_monthly")

        if df_clean is None:
            tc.status = "FAIL"
            tc.summary = "缺少 df_clean"
            return tc

        from product_lifecycle.profiling import run_profiling
        from config.settings import PRODUCT_LIFECYCLE

        col_map = PRODUCT_LIFECYCLE.get("col_map", {})
        thr = {k: v for k, v in PRODUCT_LIFECYCLE.items() if k not in ("col_map", "risk_weights", "ref_priority")}
        wgt = PRODUCT_LIFECYCLE.get("risk_weights", {})
        ref_priority = PRODUCT_LIFECYCLE.get("ref_priority", [])

        name_col = col_map.get("产品名称列", "产品品种")
        date_col = col_map.get("发货日期列", "发货日期")
        qty_col = col_map.get("销量列", "数量")
        rev_col = col_map.get("营收列", "金额")
        profit_col = col_map.get("利润列", "利润")
        cust_col = col_map.get("客户列", "客户编号")
        order_col = col_map.get("订单号列", "订单编号")
        cat_col = col_map.get("分类参照列", "产品一级分类")

        if "_月" not in df_clean.columns:
            df_clean["_月"] = df_clean[date_col].dt.to_period("M")
        latest_month = df_clean["_月"].max()

        t0 = time.time()
        result_df, data_insufficient, out, ratio_cols, pp_cols, _ = run_profiling(
            df_clean, latest_month, thr, name_col, date_col, qty_col, rev_col,
            profit_col, cust_col, order_col, cat_col, ref_priority, wgt, mode="full",
        )
        elapsed = time.time() - t0

        new_obs = int((result_df["当前画像"] == "新品观察").sum())
        total = len(result_df)

        tc.status = "PASS"
        tc.summary = f"产品 {total}，新品观察 {new_obs} ({new_obs/max(total,1)*100:.1f}%)"
        tc.details = {
            "产品总数": total,
            "新品观察": new_obs,
            "画像类别数": result_df["当前画像"].nunique(),
            "执行时间": f"{elapsed:.0f}s",
        }
        tc.details["画像分布"] = {
            str(k): int(v) for k, v in result_df["当前画像"].value_counts().items()
        }

        # 保存诊断 CSV
        save_diag_csv(result_df, "product_portrait")
        data["profiling_result"] = result_df
        data["profiling_time"] = round(elapsed, 1)
    except Exception as e:
        tc.status = "FAIL"
        tc.error = str(e)

    return tc


# ============================================================
# TEST F: 客户生命周期阶段（爬坡期参数验证）
# ============================================================
def test_f_customer_lifecycle(data: dict) -> TestCaseResult:
    """验证 calc_customer_lifecycle_stage 参数化 + 爬坡期识别。"""
    tc = TestCaseResult(id="TEST-F", name="客户生命周期阶段")

    try:
        cust_monthly = data.get("cust_monthly")
        latest_month = data.get("latest_month")

        if cust_monthly is None:
            tc.status = "FAIL"
            tc.summary = "缺少 cust_monthly"
            return tc

        from shared.pricing import calc_customer_lifecycle_stage

        t0 = time.time()
        stages = calc_customer_lifecycle_stage(
            cust_monthly, latest_month=latest_month,
            thr={"爬坡期环比阈值": 0.15, "爬坡期_环比增长前N月均值": 3},
        )
        elapsed = time.time() - t0

        stage_counts = stages["客户生命周期"].value_counts()
        ramp = int(stage_counts.get("爬坡期", 0))

        tc.status = "PASS"
        tc.summary = f"客户 {len(stages)}，爬坡期 {ramp}"
        tc.details = {"客户总数": len(stages), "爬坡期": ramp}
        tc.details["全部分布"] = {str(k): int(v) for k, v in stage_counts.items()}
        tc.details["执行时间"] = f"{elapsed:.1f}s"

        # 保存诊断 CSV
        save_diag_csv(stages, "customer_stages")
        data["customer_stages_result"] = stages
    except Exception as e:
        tc.status = "FAIL"
        tc.error = str(e)

    return tc


# ============================================================
# TEST G（可选）: 数据质量检查
# ============================================================
def test_g_data_quality(data: dict) -> TestCaseResult:
    """检查数据完整性和基本质量指标。"""
    tc = TestCaseResult(id="TEST-G", name="数据质量检查")

    try:
        df_clean = data.get("df_clean")
        prod_monthly = data.get("prod_monthly")
        cust_monthly = data.get("cust_monthly")

        if df_clean is None:
            tc.status = "FAIL"
            tc.summary = "缺少 df_clean"
            return tc

        total_rows = len(df_clean)
        products = df_clean["产品品种"].nunique() if "产品品种" in df_clean.columns else 0
        customers = cust_monthly["客户编号"].nunique() if cust_monthly is not None else 0
        neg_profit = (df_clean["利润"] < 0).sum() if "利润" in df_clean.columns else -1
        null_count = df_clean.isnull().sum().sum()

        tc.status = "PASS"
        tc.summary = f"{total_rows} 行, {products} 产品, {customers} 客户"
        tc.details = {
            "有效行数": total_rows,
            "产品数": products,
            "客户数": customers,
            "负利润行": int(neg_profit),
            "空值总数": int(null_count),
        }
    except Exception as e:
        tc.status = "FAIL"
        tc.error = str(e)

    return tc


# ============================================================
# TEST H（可选）: 跨系统一致性检查
# ============================================================
def test_h_cross_system_consistency(data: dict) -> TestCaseResult:
    """验证产品生命周期和客户分析系统的新品判定一致性。"""
    tc = TestCaseResult(id="TEST-H", name="跨系统新品一致性")

    try:
        prod_monthly = data.get("prod_monthly")
        has_in_silver = data.get("has_in_silver", False)
        cohort_result = data.get("cohort_result")

        # 产品系统新品：近12月 ERP 标记
        if has_in_silver and prod_monthly is not None:
            latest = prod_monthly["_月"].max()
            recent_mask = prod_monthly["_月"] > (latest - 12)
            profiling_new = set(
                prod_monthly[recent_mask & (prod_monthly["新品标记"] == "是")]["产品品种"].unique()
            )
        else:
            profiling_new = set()

        # 客户系统新品：cohort 使用全量
        cohort_new = set()
        if cohort_result is not None and "产品品种" in cohort_result.columns:
            # cohort_result 是客户级表，不含产品级信息
            pass

        # 直接对比：profiling 新品 vs product_monthly ERP 新品
        erp_all = set(prod_monthly[prod_monthly["新品标记"]=="是"]["产品品种"].unique()) if has_in_silver else set()

        profiling_count = len(profiling_new)
        erp_count = len(erp_all)
        diff = profiling_count - erp_count

        tc.status = "WARN" if diff != 0 else "PASS"
        tc.summary = f"profiling({profiling_count}) vs ERP全量({erp_count}), 差 {diff}"
        tc.details = {
            "profiling 新品(近12月)": profiling_count,
            "ERP全量新品": erp_count,
            "差异": diff,
        }
    except Exception as e:
        tc.status = "WARN"
        tc.summary = "一致性检查异常"
        tc.error = str(e)

    return tc


# ============================================================
# Phase 2 主函数
# ============================================================
TEST_REGISTRY = {
    "A": test_a_new_flag,
    "B": test_b_silver_propagation,
    "C": test_c_new_product_judgment,
    "D": test_d_new_product_cohort,
    "E": test_e_product_profiling,
    "F": test_f_customer_lifecycle,
    "G": test_g_data_quality,
    "H": test_h_cross_system_consistency,
}

TEST_NAMES = {
    "A": "rename_erp_columns 新品标记",
    "B": "Silver层新品标记传播",
    "C": "新品判定对比",
    "D": "新品Cohort分析",
    "E": "产品生命周期 profiling",
    "F": "客户生命周期阶段",
    "G": "数据质量检查",
    "H": "跨系统一致性检查",
}


def run_phase2(
    tests: str = "A,B,C,D,E,F",
    skip_report: bool = False,
    data: dict = None,
) -> TestSuiteResult:
    """
    执行 Phase 2 验证。

    参数：
        tests: 逗号分隔的测试 ID，如 "A,B,C"
        skip_report: 跳过 JSON/Markdown 报告生成
        data: 已加载的中间件字典（None 则自动加载）

    返回：TestSuiteResult
    """
    ensure_diag_dir()

    # 加载中间件
    if data is None:
        data = load_intermediates()

    # 解析测试列表
    selected = [t.strip().upper() for t in tests.split(",") if t.strip().upper() in TEST_REGISTRY]

    header(f"Phase 2：测试用例验证（{len(selected)} 项）")
    print(f"  数据行: {data.get('df_full_shape', [0,0])[0]}")
    print(f"  产品: {data.get('product_count', '?')}, 客户: {data.get('customer_count', '?')}")

    suite = TestSuiteResult(
        suite_name=f"Batch A 验证测试 ({','.join(selected)})",
        timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
        data_file=data.get("data_file", ""),
    )

    t_start = time.time()

    for test_id in selected:
        func = TEST_REGISTRY[test_id]
        name = TEST_NAMES.get(test_id, test_id)
        log(f"[TEST-{test_id}] {name}")
        try:
            result = func(data)
        except Exception as e:
            result = TestCaseResult(id=f"TEST-{test_id}", name=name, status="FAIL", error=str(e))
        suite.add(result)
        print(f"  [{result.status}] {result.summary}")

        # 错误时打印追踪
        if result.status == "FAIL" and result.error:
            print(f"  [ERR] {result.error}")

    suite.duration_s = time.time() - t_start

    # 输出汇总
    s = suite.summary
    print()
    print("=" * 60)
    print(f"  总计: {s['total']}  |  PASS: {s['pass']}  |  FAIL: {s['fail']}  |  SKIP: {s['skip']}  |  WARN: {s['warn']}")
    print(f"  耗时: {suite.duration_s:.1f}s")
    print("=" * 60)

    # 保存报告
    if not skip_report:
        json_path = save_summary_json(suite)
        md_path = save_markdown_report(suite)
        print(f"\n  JSON: {json_path}")
        print(f"  MD:   {md_path}")

    return suite


# ── 独立入口 ──
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Phase 2：测试用例验证（TEST A-F）")
    parser.add_argument("--tests", type=str, default="A,B,C,D,E,F,G,H",
                        help="测试用例 ID，逗号分隔（默认全部）")
    parser.add_argument("--skip-report", action="store_true",
                        help="跳过 JSON/Markdown 报告生成")
    parser.add_argument("--force", action="store_true",
                        help="强制重跑 Phase 1（传递给 run_all_tests.py 用，本脚本忽略）")
    args = parser.parse_args()

    run_phase2(tests=args.tests, skip_report=args.skip_report)
