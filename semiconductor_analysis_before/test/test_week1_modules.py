"""
Week 1 单元测试: 客户旅程阶段 (Task 1), 波动性指标 (Task 5), 真实利润估算 (Task 6).

运行方式:
    python -m pytest test/test_week1_modules.py -v
    python test/test_week1_modules.py              # 直接运行
"""

import sys, os, unittest, warnings
warnings.filterwarnings("ignore")

_TEST_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(_TEST_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import pandas as pd
import numpy as np

from src.journey.stage_classifier import classify_customer_journey_stage
from src.behavior.volatility import calc_volatility_metrics, batch_calc_volatility
from src.profitability.true_profit_estimator import estimate_true_profit, batch_estimate_true_profit

# ── 默认配置 ──────────────────────────────────────────────────
DEFAULT_JOURNEY_CONFIG = {
    "onboarding_max_months": 6,
    "onboarding_max_orders": 3,
    "growth_growth_threshold": 0.30,
    "growth_frequency_surge_ratio": 2.0,
    "maturity_cv_threshold": 0.3,
    "maturity_revenue_rank_pct": 0.3,
    "decline_decline_threshold": 0.20,
    "decline_consecutive_months": 2,
    "churn_days": 90,
    "reactivation_window_days": 180,
}

DEFAULT_VOLATILITY_CONFIG = {
    "stable_cv_threshold": 0.3,
    "stable_zero_month_ratio": 0.10,
    "moderate_cv_threshold": 0.6,
    "moderate_zero_month_ratio": 0.20,
}

DEFAULT_COST_CONFIG = {
    "order_processing_cost": 50.0,
    "logistics_cost_rate": 0.02,
    "aftersales_cost_ratio": 0.30,
    "capital_cost_annual_rate": 0.06,
}


# ================================================================
# Task 1: 客户旅程阶段分类器
# ================================================================

class TestJourneyStageClassifier(unittest.TestCase):

    def _make_monthly(self, cid, revs, months_offset=None, order_counts=None):
        """Helper: revenue series → customer monthly DataFrame."""
        n = len(revs)
        if months_offset is None:
            months_offset = list(range(n))
        dates = [pd.Period(f"2024-{1 + i:02d}", freq="M") for i in months_offset]
        if order_counts is None:
            order_counts = [max(1, min(r // 2000, 5)) for r in revs]
        return pd.DataFrame({
            "客户编号": [cid] * n,
            "_月": dates,
            "rev_sum": revs,
            "qty_sum": [r * 2 for r in revs],
            "order_count": order_counts,
        })

    def test_normal_maturity(self):
        """稳定高收入→成熟期 (CV<0.3, top 30%)"""
        revs = [10000, 10500, 10200, 10800, 10300, 10700, 10100, 10400, 10600, 10200, 10500, 10300]
        df = self._make_monthly("C001", revs)
        out = classify_customer_journey_stage(df, DEFAULT_JOURNEY_CONFIG)
        self.assertEqual(len(out), 1)
        self.assertEqual(out.at[0, "客户旅程阶段"], "成熟期")

    def test_normal_growth(self):
        """近6月增长≥30%→成长期"""
        revs = [1000] * 6 + [2000] * 6  # 近6月 vs 前6月 +100%
        df = self._make_monthly("C002", revs)
        out = classify_customer_journey_stage(df, DEFAULT_JOURNEY_CONFIG)
        self.assertEqual(len(out), 1)
        self.assertEqual(out.at[0, "客户旅程阶段"], "成长期")

    def test_normal_onboarding(self):
        """新客户低频次→导入期"""
        revs = [5000, 6000, 3000]
        # order_count 之和必须 <= onboarding_max_orders(=3)
        df = self._make_monthly("C003", revs, months_offset=[0, 1, 2], order_counts=[1, 1, 1])
        out = classify_customer_journey_stage(df, DEFAULT_JOURNEY_CONFIG)
        self.assertEqual(len(out), 1)
        self.assertEqual(out.at[0, "客户旅程阶段"], "导入期")

    def test_normal_churn(self):
        """距上次交易>90天且近6月无交易→流失期"""
        # C004 数据止于 2024-03，用 C099 将全局最新推到 2024-12
        # → 距上次 9 个月 > 3, 近6月 (7-12月) 无 C004 交易 → 流失期
        revs = [5000] * 3  # 1月~3月
        df = self._make_monthly("C004", revs, months_offset=[0, 1, 2])
        dummy = self._make_monthly("C099", [1000], months_offset=[11])
        df = pd.concat([df, dummy], ignore_index=True)
        out = classify_customer_journey_stage(df, DEFAULT_JOURNEY_CONFIG)
        c004 = out[out["客户编号"] == "C004"]
        self.assertEqual(len(c004), 1)
        self.assertEqual(c004.iloc[0]["客户旅程阶段"], "流失期")

    def test_normal_decline(self):
        """连续下滑≥2月且跌幅≥20%→衰退期"""
        # 近6月：10000, 8000, 6400, 5000, 4000, 3000 → 逐月下跌, 跌幅>20%
        revs = [20000] * 6 + [10000, 8000, 6400, 5000, 4000, 3000]
        df = self._make_monthly("C005", revs)
        out = classify_customer_journey_stage(df, DEFAULT_JOURNEY_CONFIG)
        self.assertEqual(len(out), 1)
        self.assertEqual(out.at[0, "客户旅程阶段"], "衰退期")

    def test_normal_reactivation(self):
        """有中断后恢复交易→激活期"""
        # 前3月有交易(1-3月) → 中断7个月 → 近1月有交易(11月)
        # 使用不连续的月份索引产生 >6 个月的真实间隔
        revs = [5000, 6000, 4000, 7000]
        months_offset = [0, 1, 2, 11]  # 1月/2月/3月 → 中断 → 12月
        order_counts = [3, 3, 2, 3]
        df = self._make_monthly("C006", revs, months_offset=months_offset, order_counts=order_counts)
        out = classify_customer_journey_stage(df, DEFAULT_JOURNEY_CONFIG)
        self.assertEqual(out.iloc[0]["客户旅程阶段"], "激活期")

    def test_empty_dataframe(self):
        """空DataFrame→空结果"""
        df = pd.DataFrame(columns=["客户编号", "_月", "rev_sum", "qty_sum", "order_count"])
        out = classify_customer_journey_stage(df, DEFAULT_JOURNEY_CONFIG)
        self.assertTrue(len(out) == 0)

    def test_single_point(self):
        """单月数据低频次→导入期（首次交易≤6月+订单数≤3）"""
        df = self._make_monthly("C007", [5000], months_offset=[0], order_counts=[1])
        out = classify_customer_journey_stage(df, DEFAULT_JOURNEY_CONFIG)
        self.assertEqual(len(out), 1)
        self.assertEqual(out.at[0, "客户旅程阶段"], "导入期")

    def test_non_period_date(self):
        """date_col非Period类型→自动转换"""
        df = self._make_monthly("C008", [10000, 10500, 10200])
        df["_月"] = df["_月"].astype(str)  # 转为字符串
        out = classify_customer_journey_stage(df, DEFAULT_JOURNEY_CONFIG)
        self.assertEqual(len(out), 1)

    def test_output_columns(self):
        """确认输出列齐全"""
        revs = [10000, 10500, 10200, 10800, 10300, 10700]
        df = self._make_monthly("C009", revs)
        out = classify_customer_journey_stage(df, DEFAULT_JOURNEY_CONFIG)
        expected_cols = {
            "客户编号", "客户旅程阶段", "阶段持续月数", "阶段转换次数",
            "首次交易日期", "距上次采购天数", "近6月交易额环比增长率", "近12月交易额CV",
        }
        self.assertTrue(expected_cols.issubset(set(out.columns)))

    def test_channel_map_changes_maturity(self):
        """渠道分组后，低营收渠道的top客户可获成熟期"""
        # C001(10000*12), C002(1000*12) → channel A
        # C003(5000*12) → channel B (global top 30% ≈ 42000 threshold)
        # Global: C003 recent6=30000 < 42000 → stable
        # Channel B (only C003): threshold=30000 → C003 stays mature
        df = self._make_monthly("C001", [10000] * 12)
        df = pd.concat([df, self._make_monthly("C002", [1000] * 12)], ignore_index=True)
        df = pd.concat([df, self._make_monthly("C003", [5000] * 12)], ignore_index=True)

        channel_map = {"C001": "A", "C002": "A", "C003": "B"}

        out_with = classify_customer_journey_stage(df, DEFAULT_JOURNEY_CONFIG, channel_map=channel_map)
        out_without = classify_customer_journey_stage(df, DEFAULT_JOURNEY_CONFIG)

        c003_with = out_with[out_with["客户编号"] == "C003"].iloc[0]["客户旅程阶段"]
        c003_without = out_without[out_without["客户编号"] == "C003"].iloc[0]["客户旅程阶段"]

        self.assertEqual(c003_with, "成熟期",
                         "channel_map下C003是B渠道唯一正营收客户，应保留成熟期")
        self.assertEqual(c003_without, "稳定期",
                         "无channel_map时C003低于全局70%百分位，应降级为稳定期")


# ================================================================
# Task 5: 采购波动性指标
# ================================================================

class TestVolatilityMetrics(unittest.TestCase):

    def test_stable_series(self):
        """CV<0.3, 零月<10%→高稳定"""
        s = pd.Series([100, 105, 102, 108, 103, 107, 101, 104, 106, 102, 105, 103],
                      index=pd.period_range("2024-01", periods=12, freq="M"))
        out = calc_volatility_metrics(s)
        self.assertEqual(out["稳定性等级"], "高稳定")
        self.assertLess(out["收入CV"], 0.3)

    def test_moderate_series(self):
        """CV<0.6, 零月<20%→中等稳定"""
        # CV ≈ 0.34, 零月占比 = 1/12 ≈ 8.3%
        vals = [100, 80, 120, 90, 110, 85, 115, 95, 105, 0, 100, 90]
        s = pd.Series(vals, index=pd.period_range("2024-01", periods=12, freq="M"))
        out = calc_volatility_metrics(s)
        self.assertEqual(out["稳定性等级"], "中等稳定")

    def test_volatile_series(self):
        """高波动→高波动"""
        vals = [100, 0, 0, 0, 200, 0, 0, 0, 50, 0, 0, 0]
        s = pd.Series(vals, index=pd.period_range("2024-01", periods=12, freq="M"))
        out = calc_volatility_metrics(s)
        self.assertEqual(out["稳定性等级"], "高波动")

    def test_empty_series(self):
        """空序列→高波动"""
        s = pd.Series([], dtype=float)
        out = calc_volatility_metrics(s)
        self.assertEqual(out["稳定性等级"], "高波动")
        self.assertEqual(out["收入CV"], 0)
        self.assertEqual(out["零采购月占比"], 1)

    def test_single_point(self):
        """单点→R²=0"""
        s = pd.Series([100], index=pd.period_range("2024-01", periods=1, freq="M"))
        out = calc_volatility_metrics(s)
        self.assertEqual(out["趋势R²"], 0)
        self.assertIn(out["稳定性等级"], ["高稳定", "中等稳定", "高波动"])

    def test_two_points(self):
        """两点→R²=0"""
        s = pd.Series([100, 50], index=pd.period_range("2024-01", periods=2, freq="M"))
        out = calc_volatility_metrics(s)
        self.assertEqual(out["趋势R²"], 0)
        self.assertGreater(out["最大单月跌幅"], 0)

    def test_all_zeros(self):
        """全零→高波动"""
        s = pd.Series([0, 0, 0], index=pd.period_range("2024-01", periods=3, freq="M"))
        out = calc_volatility_metrics(s)
        self.assertEqual(out["稳定性等级"], "高波动")
        self.assertEqual(out["零采购月占比"], 1.0)

    def test_config_override(self):
        """自定义阈值"""
        vals = [100, 110, 105, 115, 108, 112]
        s = pd.Series(vals, index=pd.period_range("2024-01", periods=6, freq="M"))
        # 放宽阈值 → 应判定为高稳定
        cfg = {"stable_cv_threshold": 0.5, "stable_zero_month_ratio": 0.5}
        out = calc_volatility_metrics(s, cfg)
        self.assertEqual(out["稳定性等级"], "高稳定")

    def test_batch_empty(self):
        """批量空DataFrame→空结果"""
        out = batch_calc_volatility(pd.DataFrame())
        self.assertTrue(len(out) == 0)

    def test_batch_normal(self):
        """批量正常数据"""
        rows = []
        for cid in ["C001", "C002"]:
            for m in range(6):
                rows.append({"客户编号": cid, "_月": pd.Period(f"2024-{1+m:02d}", freq="M"),
                             "rev_sum": 1000 + m * 100, "qty_sum": 500, "order_count": 2})
        df = pd.DataFrame(rows)
        out = batch_calc_volatility(df)
        self.assertEqual(len(out), 2)
        self.assertIn("收入CV", out.columns)
        self.assertIn("稳定性等级", out.columns)


# ================================================================
# Task 6: 估算真实利润贡献度
# ================================================================

class TestTrueProfitEstimator(unittest.TestCase):

    def test_high_profit(self):
        """高毛利→高利润"""
        row = {"近12月毛利": 500000, "近12月收入": 1000000, "近12月数量": 5000,
               "订单数": 50, "退货金额": 10000, "应收账款": 200000, "客户等级": "A"}
        out = estimate_true_profit(row, DEFAULT_COST_CONFIG)
        self.assertEqual(out["利润等级"], "高利润")
        self.assertGreater(out["估算真实利润率"], 15)

    def test_loss(self):
        """低毛利高成本→亏损"""
        row = {"近12月毛利": 1000, "近12月收入": 50000, "近12月数量": 5000,
               "订单数": 50}
        out = estimate_true_profit(row, DEFAULT_COST_CONFIG)
        self.assertEqual(out["利润等级"], "亏损")

    def test_margin(self):
        """微利"""
        row = {"近12月毛利": 20000, "近12月收入": 200000, "近12月数量": 1000,
               "订单数": 20}
        out = estimate_true_profit(row, DEFAULT_COST_CONFIG)
        self.assertEqual(out["利润等级"], "微利")

    def test_missing_optional_fields(self):
        """缺省字段→不报错"""
        row = {"近12月毛利": 100000, "近12月收入": 500000, "近12月数量": 2000}
        out = estimate_true_profit(row, DEFAULT_COST_CONFIG)
        self.assertIn(out["利润等级"], ["高利润", "微利", "亏损"])
        self.assertIn("估算真实利润", out)
        self.assertIn("订单处理成本", out)

    def test_empty_dataframe_batch(self):
        """批量空→空结果"""
        out = batch_estimate_true_profit(pd.DataFrame())
        self.assertTrue(len(out) == 0)

    def test_batch_normal(self):
        """批量正常数据"""
        rows = [
            {"客户编号": "C001", "近12月毛利": 500000, "近12月收入": 1000000,
             "近12月数量": 5000, "订单数": 50, "客户等级": "A"},
            {"客户编号": "C002", "近12月毛利": 5000, "近12月收入": 100000,
             "近12月数量": 5000, "订单数": 50, "客户等级": "B"},
        ]
        df = pd.DataFrame(rows)
        out = batch_estimate_true_profit(df, DEFAULT_COST_CONFIG)
        self.assertEqual(len(out), 2)
        self.assertIn("估算真实利润", out.columns)
        self.assertIn("利润等级", out.columns)

    def test_output_columns(self):
        """确认输出列齐全"""
        row = {"近12月毛利": 500000, "近12月收入": 1000000, "近12月数量": 5000}
        out = estimate_true_profit(row, DEFAULT_COST_CONFIG)
        expected = {"近12月毛利", "估算真实利润", "估算真实利润率", "利润等级",
                    "订单处理成本", "物流成本", "售后成本", "资金占用成本"}
        self.assertTrue(expected.issubset(set(out.keys())))


if __name__ == "__main__":
    unittest.main()
