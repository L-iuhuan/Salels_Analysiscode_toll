#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试用例模板。

用于创建新的测试用例。复制此文件并按以下结构填写：

    1. 测试函数签名:
        def test_xxx(data: dict) -> TestCaseResult:

    2. 内部逻辑:
        - 从 data 字典读取中间件数据
        - 执行被测函数
        - 收集关键指标填入 tc.details
        - 设定 tc.status: "PASS"/"FAIL"/"SKIP"/"WARN"
        - 设定 tc.summary: 一句话结论

    3. 注册:
        在 phase2_validate.py 的 TEST_REGISTRY 和 TEST_NAMES 中添加。

示例见 phase2_validate.py 中的 TEST-A 至 TEST-F。
"""

import sys, os, time

TEST_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if TEST_DIR not in sys.path:
    sys.path.insert(0, os.path.dirname(TEST_DIR))

from test.conftest import (
    PROJECT_ROOT, DIAG_DIR,
    TestCaseResult, save_diag_csv,
)


def test_xxx(data: dict) -> TestCaseResult:
    """
    模板函数：复制并重命名为 test_<你的名称>。

    参数：
        data: Phase 1 中间件字典，包含：
            - df_clean: DataFrame    清洗后行级数据
            - prod_monthly: DataFrame 产品月度 Silver 表
            - cxp: DataFrame          客户×产品 Silver 表
            - cust_monthly: DataFrame 客户月度 Silver 表
            - has_new_flag: bool
            - has_in_silver: bool
            - latest_month: Period    最新月份
            - product_count: int
            - customer_count: int
            - profiling_result: DataFrame (Phase 2 写入)
            - cohort_result: DataFrame (Phase 2 写入)
            - customer_stages_result: DataFrame (Phase 2 写入)

    返回：
        TestCaseResult 对象
    """
    tc = TestCaseResult(id="TEST-X", name="测试用例中文名")

    try:
        # ── 1. 读取数据 ──
        df_clean = data.get("df_clean")
        prod_monthly = data.get("prod_monthly")

        if df_clean is None:
            tc.status = "FAIL"
            tc.summary = "缺少必要数据"
            return tc

        # ── 2. 执行测试 ──
        t0 = time.time()

        # TODO: 调用被测函数
        # from xxx import yyy
        # result = yyy(df_clean)

        elapsed = time.time() - t0

        # ── 3. 结果判断 ──
        # TODO: 设定通过条件
        tc.status = "PASS"  # 或 "FAIL" / "SKIP" / "WARN"
        tc.summary = f"执行完成（{elapsed:.1f}s）"
        tc.details = {
            "数据行数": len(df_clean),
            "执行时间": f"{elapsed:.1f}s",
            # TODO: 添加更多关键指标
        }

        # ── 4. 保存诊断 CSV（可选） ──
        # save_diag_csv(result, "xxx")

    except Exception as e:
        tc.status = "FAIL"
        tc.error = str(e)

    return tc


# ============================================================
# 注册须知
# ============================================================
# 在 phase2_validate.py 中添加：
#
#   from test.templates.test_case_template import test_xxx
#
#   TEST_REGISTRY["X"] = test_xxx
#   TEST_NAMES["X"] = "测试用例中文名"
#
# 然后在 run_all_tests.py 的默认 tests 参数中添加 "X"。
