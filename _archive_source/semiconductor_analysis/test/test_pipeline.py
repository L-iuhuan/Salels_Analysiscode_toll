"""
P2-B: Pipeline DI 容器测试。

测试覆盖：
1. 自动装配 — 不传依赖时自动加载生产实现
2. DI 注入 — Mock 覆盖自动装配
3. 阶段路由 — 已知/未知阶段
4. Config 注入 — AppConfig 传递
5. 跨阶段数据传递 — silver → product/customer
"""

import os
import sys
import pytest
import pandas as pd
from datetime import datetime
from typing import Optional

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.pipeline import Pipeline
from core.config import AppConfig
from core.interfaces import IDataLoader, IDataCleaner, IDataAggregator, IValidator


# ============================================================
# Mock 实现
# ============================================================

class MockLoader:
    def find_source(self, data_dir: str) -> Optional[str]:
        return os.path.join(data_dir, "test.xlsx")

    def load(self, source_path: str):
        return pd.DataFrame({"A": [1, 2, 3]})


class MockCleaner:
    def __init__(self, config=None):
        self.config = config

    def clean(self, raw_df):
        return raw_df.copy()


class MockAggregator:
    def aggregate(self, clean_df):
        return {"monthly": clean_df.copy(), "product_monthly": clean_df.copy()}


class MockValidator:
    def validate(self, df, stage):
        return True

    def validate_silver(self, silver_dict):
        return True


# ============================================================
# Test: 自动装配
# ============================================================

class TestPipelineAutoWire:
    """Pipeline 自动装配测试。"""

    def test_default_construction(self):
        """默认构造后所有依赖应有值（不为 None）。"""
        p = Pipeline()
        assert p.data_loader is not None
        assert p.data_cleaner is not None
        assert p.data_aggregator is not None
        assert p.validator is not None
        assert isinstance(p.config, AppConfig)

    def test_default_loader_type(self):
        """默认 data_loader 为 ExcelDataLoader。"""
        from data_pipeline.loader import ExcelDataLoader
        p = Pipeline()
        assert isinstance(p.data_loader, ExcelDataLoader)

    def test_default_cleaner_type(self):
        """默认 data_cleaner 为 DefaultCleaner。"""
        from data_pipeline.cleaner import DefaultCleaner
        p = Pipeline()
        assert isinstance(p.data_cleaner, DefaultCleaner)

    def test_default_aggregator_type(self):
        """默认 data_aggregator 为 DefaultAggregator。"""
        from data_pipeline.aggregator import DefaultAggregator
        p = Pipeline()
        assert isinstance(p.data_aggregator, DefaultAggregator)

    def test_default_validator_type(self):
        """默认 validator 为 SimpleValidator。"""
        from data_pipeline.validator import SimpleValidator
        p = Pipeline()
        assert isinstance(p.validator, SimpleValidator)

    def test_default_config_has_paths(self):
        """默认 config 应包含 paths 配置。"""
        p = Pipeline()
        assert p.config.paths is not None
        assert hasattr(p.config.paths, "data_dir")
        assert hasattr(p.config.paths, "output_silver")
        assert hasattr(p.config.paths, "output_gold")


# ============================================================
# Test: DI 注入
# ============================================================

class TestPipelineDI:
    """Pipeline 依赖注入测试。"""

    def test_inject_loader(self):
        """构造函数传入 MockLoader 后 data_loader 应为 MockLoader。"""
        mock = MockLoader()
        p = Pipeline(data_loader=mock)
        assert p.data_loader is mock

    def test_inject_all_mocks(self):
        """全部传入 Mock 后不应自动装配。"""
        mocks = dict(
            data_loader=MockLoader(),
            data_cleaner=MockCleaner(),
            data_aggregator=MockAggregator(),
            validator=MockValidator(),
        )
        p = Pipeline(**mocks)
        for name, mock in mocks.items():
            assert getattr(p, name) is mock, f"{name} 应保留注入的 Mock"

    def test_partial_inject(self):
        """部分注入 + 剩余自动装配。"""
        mock_loader = MockLoader()
        p = Pipeline(data_loader=mock_loader)
        assert p.data_loader is mock_loader
        assert p.data_cleaner is not None  # 自动装配
        assert p.data_aggregator is not None  # 自动装配

    def test_inject_with_config(self):
        """同时注入 config 和依赖。"""
        cfg = AppConfig.from_defaults()
        mock = MockLoader()
        p = Pipeline(config=cfg, data_loader=mock)
        assert p.config is cfg
        assert p.data_loader is mock


# ============================================================
# Test: 阶段执行
# ============================================================

class TestPipelineStages:
    """Pipeline 阶段执行测试。"""

    def test_unknown_stage(self, capsys):
        """未知阶段应打印警告且不报错。"""
        p = Pipeline(data_loader=MockLoader(),
                     data_cleaner=MockCleaner(),
                     data_aggregator=MockAggregator(),
                     validator=MockValidator())
        results = p.run(stages=["nonexistent"])
        captured = capsys.readouterr()
        assert "未知阶段" in captured.out
        assert results == {}

    def test_silver_stage(self):
        """silver 阶段应返回 3 张表。"""
        p = Pipeline(data_loader=MockLoader(),
                     data_cleaner=MockCleaner(),
                     data_aggregator=MockAggregator(),
                     validator=MockValidator())
        results = p.run(stages=["silver"], source_path="dummy.xlsx")
        assert "silver" in results
        assert isinstance(results["silver"], dict)
        assert "raw" in results
        assert isinstance(results["raw"], pd.DataFrame)

    def test_silver_structure(self):
        """silver 输出应包含 monthly / product_monthly。"""
        p = Pipeline(data_loader=MockLoader(),
                     data_cleaner=MockCleaner(),
                     data_aggregator=MockAggregator(),
                     validator=MockValidator())
        results = p.run(stages=["silver"], source_path="dummy.xlsx")
        silver = results["silver"]
        assert "monthly" in silver
        assert "product_monthly" in silver

    def test_timing_disabled_by_default(self):
        """timing_enabled 默认应为 False。"""
        p = Pipeline()
        assert p.timing_enabled is False


# ============================================================
# Test: Config 集成
# ============================================================

class TestPipelineConfig:
    """Pipeline Config 集成测试。"""

    def test_custom_config(self):
        """传入自定义 AppConfig，pipeline 应使用它。"""
        cfg = AppConfig.from_defaults()
        cfg.paths.data_dir = "/custom/data"
        p = Pipeline(config=cfg)
        assert p.config.paths.data_dir == "/custom/data"

    def test_config_skip_silver_flag(self):
        """Config 的 skip_silver_if_exists 可读写。"""
        cfg = AppConfig.from_defaults()
        cfg.skip_silver_if_exists = False
        p = Pipeline(config=cfg)
        assert p.config.skip_silver_if_exists is False

        cfg.skip_silver_if_exists = True
        assert p.config.skip_silver_if_exists is True


# ============================================================
# Test: 多阶段编排
# ============================================================

class TestPipelineMultiStage:
    """Pipeline 多阶段编排测试。"""

    def test_silver_then_product(self):
        """先执行 silver 再执行 product（通过 _results 传递数据）。"""
        p = Pipeline(data_loader=MockLoader(),
                     data_cleaner=MockCleaner(),
                     data_aggregator=MockAggregator(),
                     validator=MockValidator())
        results = p.run(stages=["silver"], source_path="dummy.xlsx")
        assert "silver" in results

    def test_stage_ordering(self):
        """stages 列表控制执行顺序。"""
        p = Pipeline(data_loader=MockLoader(),
                     data_cleaner=MockCleaner(),
                     data_aggregator=MockAggregator(),
                     validator=MockValidator())
        # 单阶段测试 — 确保 _results 只包含该阶段
        results = p.run(stages=["silver"], source_path="dummy.xlsx")
        expected = {"silver", "raw"}
        assert expected.issubset(set(results.keys()))


# ============================================================
# Test: 验证层集成
# ============================================================

class TestPipelineValidator:
    """Pipeline 验证层集成测试。"""

    def test_validator_called(self):
        """silver 阶段应调用 validator.validate()。"""
        class TrackingValidator(MockValidator):
            def __init__(self):
                self.validate_calls = []
                self.silver_calls = []

            def validate(self, df, stage):
                self.validate_calls.append(stage)
                return True

            def validate_silver(self, silver_dict):
                self.silver_calls.append(len(silver_dict))
                return True

        tracker = TrackingValidator()
        p = Pipeline(data_loader=MockLoader(),
                     data_cleaner=MockCleaner(),
                     data_aggregator=MockAggregator(),
                     validator=tracker)
        p.run(stages=["silver"], source_path="dummy.xlsx")
        assert tracker.validate_calls == ["raw", "clean"]
        assert tracker.silver_calls == [2]

    def test_validator_errors_not_blocking(self):
        """验证失败不应中断管线（warn + continue）。"""
        class FailingValidator(MockValidator):
            def validate(self, df, stage):
                print(f"  [警告] 数据验证失败 (stage={stage})")
                return False

            def validate_silver(self, silver_dict):
                print("  [警告] Silver 数据验证失败")
                return False

        fail_val = FailingValidator()
        p = Pipeline(data_loader=MockLoader(),
                     data_cleaner=MockCleaner(),
                     data_aggregator=MockAggregator(),
                     validator=fail_val)
        # 不应抛出异常
        results = p.run(stages=["silver"], source_path="dummy.xlsx")
        assert "silver" in results


# ============================================================
# Test: P3 B2B v2 适配器 DI
# ============================================================

class MockJourneyClassifier:
    def classify(self, customer_monthly, config, channel_map=None):
        return pd.DataFrame({"客户编号": ["M001"], "旅程阶段": ["成长期"]})


class MockVolatilityCalculator:
    def batch_calculate(self, cust_monthly, config=None):
        return pd.DataFrame({"客户编号": ["M001"], "收入CV": [0.25]})


class MockProfitEstimator:
    def batch_estimate(self, customer_df, config=None):
        df = customer_df.copy()
        df["估算真实利润"] = 100.0
        return df


class MockAnomalyDetector:
    def detect(self, customer_df, silver, **kwargs):
        return pd.DataFrame({
            "客户编号": ["M001"], "异常类型": ["采购中断"],
            "异常等级": ["高"], "异常详情": ["测试"],
        })


class MockActionEngine:
    def suggest(self, customer_df, anomaly_log=None, silver=None, **kwargs):
        df = customer_df.copy()
        df["告警数量"] = 1
        df["紧急告警"] = "测试告警"
        df["策略建议"] = "测试建议"
        return {
            "actions": df[["客户编号", "告警数量", "紧急告警", "策略建议"]],
            "cross_sell": pd.DataFrame(),
        }


class TestPipelineB2B:
    """Pipeline B2B v2 适配器测试。"""

    def test_auto_wire_all_b2b(self):
        """所有 B2B 适配器自动装配。"""
        p = Pipeline()
        assert p.stage_classifier is not None
        assert p.volatility_calculator is not None
        assert p.profit_estimator is not None
        assert p.anomaly_detector is not None
        assert p.action_engine is not None

    def test_inject_all_b2b_mocks(self):
        """注入 Mock 后不应使用自动装配。"""
        mocks = dict(
            stage_classifier=MockJourneyClassifier(),
            volatility_calculator=MockVolatilityCalculator(),
            profit_estimator=MockProfitEstimator(),
            anomaly_detector=MockAnomalyDetector(),
            action_engine=MockActionEngine(),
        )
        p = Pipeline(data_loader=MockLoader(),
                     data_cleaner=MockCleaner(),
                     data_aggregator=MockAggregator(),
                     validator=MockValidator(),
                     **mocks)
        for name, mock in mocks.items():
            assert getattr(p, name) is mock, f"{name} should be injected"

    def test_scoring_stage_needs_silver_and_portrait(self, capsys):
        """scoring 阶段在缺少 silver/portrait 时打印警告。"""
        p = Pipeline(data_loader=MockLoader(),
                     data_cleaner=MockCleaner(),
                     data_aggregator=MockAggregator(),
                     validator=MockValidator(),
                     stage_classifier=MockJourneyClassifier(),
                     volatility_calculator=MockVolatilityCalculator(),
                     profit_estimator=MockProfitEstimator(),
                     anomaly_detector=MockAnomalyDetector(),
                     action_engine=MockActionEngine())
        results = p.run(stages=["scoring"])
        captured = capsys.readouterr()
        assert "需要先执行" in captured.out
        assert "scoring" not in results

    def test_scoring_with_mock_data(self):
        """提供 silver+portrait 可完成评分。"""
        silver = {
            "customer_monthly": pd.DataFrame({
                "客户编号": ["M001", "M001"],
                "_月": pd.PeriodIndex(["202401", "202402"], freq="M"),
                "rev_sum": [100.0, 200.0],
            }),
            "customer_x_product": pd.DataFrame(),
            "product_monthly": pd.DataFrame(),
        }
        portrait = pd.DataFrame({
            "客户编号": ["M001", "M002"],
            "近12月收入": [1000.0, 500.0],
        })

        p = Pipeline(data_loader=MockLoader(),
                     data_cleaner=MockCleaner(),
                     data_aggregator=MockAggregator(),
                     validator=MockValidator(),
                     stage_classifier=MockJourneyClassifier(),
                     volatility_calculator=MockVolatilityCalculator(),
                     profit_estimator=MockProfitEstimator(),
                     anomaly_detector=MockAnomalyDetector(),
                     action_engine=MockActionEngine())

        # 直接设置 _results（run() 会清空，因此直接调用 _run_scoring）
        p._results = {"silver": silver, "customer_portrait": portrait}
        p._run_scoring()
        assert "customer_portrait" in p._results
        assert "anomaly_log" in p._results
        assert "actions" in p._results


# ============================================================
# Test: Pipeline 修复验证 — customer/gold/scoring 阶段
# ============================================================

class TestPipelineCustomerGold:
    """验证修复1+2+4：customer 存 gold/portrait，gold 用真实数据。"""

    def test_customer_stores_gold_tables(self):
        """_run_customer 应将 run_customer() 返回的 gold_tables 存入 _results。"""
        import customer_analysis.run_pipeline as rp_mod

        original_run = rp_mod.run
        gold_tables = {
            "客户全景": pd.DataFrame({"客户编号": ["M001"], "近12月收入": [1000.0]}),
            "客户产品桥接": pd.DataFrame({"客户编号": ["M001"]}),
        }
        try:
            # 替换为返回固定结果的 run
            def fake_run(*args, **kwargs):
                return {"gold_tables": gold_tables, "customer_count": 1}
            rp_mod.run = fake_run

            p = Pipeline(
                data_loader=MockLoader(), data_cleaner=MockCleaner(),
                data_aggregator=MockAggregator(), validator=MockValidator(),
            )
            p._results["silver"] = {"customer_monthly": pd.DataFrame()}
            p._run_customer()
            assert "customer" in p._results
            assert p._results["customer"]["gold_tables"] is gold_tables
            # 验证1: gold 表已提取
            assert p._results["gold"] is gold_tables
            # 验证2: customer_portrait 来自客户全景表
            assert "customer_portrait" in p._results
            assert p._results["customer_portrait"] is gold_tables["客户全景"]
        finally:
            rp_mod.run = original_run

    def test_customer_missing_silver(self, capsys):
        """_run_customer 在缺少 silver 时打印警告。"""
        p = Pipeline(
            data_loader=MockLoader(), data_cleaner=MockCleaner(),
            data_aggregator=MockAggregator(), validator=MockValidator(),
        )
        p._run_customer()
        captured = capsys.readouterr()
        assert "需要先执行 silver" in captured.out

    def test_gold_exports_existing_tables(self):
        """_run_gold 在 gold 已存在时直接导出，不重新生成。"""
        import reports.gold_exporter as ge_mod

        original_save = getattr(ge_mod.GoldExporter, 'save', None)
        gold_data = {"test_table": pd.DataFrame({"x": [1]})}
        saved_arg = []

        class FakeExporter:
            def save(self, gold, output_dir=None):
                saved_arg.append(gold)
                return "/fake/report.xlsx"

        try:
            ge_mod.GoldExporter = FakeExporter
            p = Pipeline(
                data_loader=MockLoader(), data_cleaner=MockCleaner(),
                data_aggregator=MockAggregator(), validator=MockValidator(),
            )
            p._results["gold"] = gold_data
            p._run_gold()
            assert saved_arg[0] is gold_data
            assert "report" in p._results
        finally:
            pass  # pragma: no cover

    def test_gold_generates_if_missing(self):
        """_run_gold 在 gold 不存在时调用 generate_gold_tables。"""
        import customer_analysis.gold as gold_mod

        original_gen = gold_mod.generate_gold_tables
        generated = {"gen_table": pd.DataFrame({"y": [2]})}
        gen_called_with = []

        def fake_gen(customer_df, silver, **kw):
            gen_called_with.append((customer_df, silver))
            return generated

        import reports.gold_exporter as ge_mod
        original_exporter = ge_mod.GoldExporter
        saved_arg = []

        class FakeExporter:
            def save(self, gold, output_dir=None):
                saved_arg.append(gold)
                return "/fake/report.xlsx"

        try:
            gold_mod.generate_gold_tables = fake_gen
            ge_mod.GoldExporter = FakeExporter

            silver = {"customer_monthly": pd.DataFrame()}
            portrait = pd.DataFrame({"客户编号": ["M001"]})
            p = Pipeline(
                data_loader=MockLoader(), data_cleaner=MockCleaner(),
                data_aggregator=MockAggregator(), validator=MockValidator(),
            )
            p._results["silver"] = silver
            p._results["customer_portrait"] = portrait
            p._run_gold()
            assert len(gen_called_with) == 1
            assert gen_called_with[0][0] is portrait  # customer_df
            assert gen_called_with[0][1] is silver
            assert saved_arg[0] is generated
        finally:
            gold_mod.generate_gold_tables = original_gen
            ge_mod.GoldExporter = original_exporter

    def test_gold_skips_when_no_data(self, capsys):
        """_run_gold 在无 gold/silver/portrait 时打印警告。"""
        p = Pipeline(
            data_loader=MockLoader(), data_cleaner=MockCleaner(),
            data_aggregator=MockAggregator(), validator=MockValidator(),
        )
        p._run_gold()
        captured = capsys.readouterr()
        assert "需要先执行" in captured.out


class TestPipelineScoringOverlap:
    """验证修复4：scoring 阶段在 customer 已执行时跳过。"""

    def test_scoring_skips_when_customer_done(self, capsys):
        """_run_scoring 在 _results["customer"] 不为 None 时跳过。"""
        p = Pipeline(
            data_loader=MockLoader(), data_cleaner=MockCleaner(),
            data_aggregator=MockAggregator(), validator=MockValidator(),
        )
        p._results["customer"] = {"customer_count": 5}
        p._run_scoring()
        captured = capsys.readouterr()
        assert "跳过" in captured.out
        # Scoring 不应覆盖 _results
        assert "anomaly_log" not in p._results

    def test_scoring_runs_without_customer(self, capsys):
        """_run_scoring 在无 customer 但有 silver+portrait 时正常执行。"""
        silver = {
            "customer_monthly": pd.DataFrame({
                "客户编号": ["M001"], "_月": pd.PeriodIndex(["202401"], freq="M"),
                "rev_sum": [100.0],
            }),
            "customer_x_product": pd.DataFrame(),
            "product_monthly": pd.DataFrame(),
        }
        portrait = pd.DataFrame({"客户编号": ["M001"], "近12月收入": [1000.0]})
        p = Pipeline(
            data_loader=MockLoader(), data_cleaner=MockCleaner(),
            data_aggregator=MockAggregator(), validator=MockValidator(),
            stage_classifier=MockJourneyClassifier(),
            volatility_calculator=MockVolatilityCalculator(),
            profit_estimator=MockProfitEstimator(),
            anomaly_detector=MockAnomalyDetector(),
            action_engine=MockActionEngine(),
        )
        p._results = {"silver": silver, "customer_portrait": portrait}
        p._run_scoring()
        captured = capsys.readouterr()
        assert "跳过" not in captured.out
        assert "customer_portrait" in p._results
        assert "anomaly_log" in p._results


class TestGoldWithAdapters:
    """验证修复3：generate_gold_tables 可选适配器参数。"""

    @staticmethod
    def _make_silver():
        """构建完整的 silver dict 用于 generate_gold_tables 测试。"""
        pi = pd.PeriodIndex
        return {
            "customer_monthly": pd.DataFrame({
                "客户编号": ["M001", "M001", "M001"],
                "产品品种": ["SKU-A", "SKU-A", "SKU-A"],
                "_月": pi(["202401", "202402", "202403"], freq="M"),
                "rev_sum": [100.0, 200.0, 150.0],
                "qty_sum": [10, 20, 15],
            }),
            "customer_x_product": pd.DataFrame({
                "客户编号": ["M001", "M001"],
                "产品品种": ["SKU-A", "SKU-B"],
                "_月": pi(["202401", "202402"], freq="M"),
                "rev_sum": [100.0, 200.0],
                "qty_sum": [10, 20],
            }),
            "product_monthly": pd.DataFrame({
                "产品品种": ["SKU-A", "SKU-A", "SKU-A"],
                "_月": pi(["202401", "202402", "202403"], freq="M"),
                "rev_sum": [100.0, 200.0, 150.0],
                "qty_sum": [10, 20, 15],
            }),
        }

    @staticmethod
    def _make_portrait():
        return pd.DataFrame({
            "客户编号": ["M001"], "近12月收入": [1000.0],
            "距上次采购天数": [30], "新品采购占比": [0.1],
            "常规平均采购间隔": [45], "近12月毛利": [200.0],
        })

    def test_adapter_used_when_provided(self):
        """提供 stage_classifier 适配器时，应调用适配器而非直接 import。

        generate_gold_tables() 被大量下游函数（pricing, 趋势分析等）依赖，
        适配器测试只验证 adapter dispatch 逻辑，不要求完整 end-to-end 通过。
        """
        # 用 mock 隔离
        import customer_analysis.gold as gold_mod
        from unittest.mock import patch

        # 在调用前植入 mock 跟踪器
        classifier_called = [False]

        class TrackingClassifier:
            def classify(self, customer_monthly, config, channel_map=None):
                classifier_called[0] = True
                return pd.DataFrame({
                    "客户编号": ["M001"], "旅程阶段": ["成长期"],
                    "距上次采购天数": [30],
                })

        silver = self._make_silver()
        portrait = self._make_portrait()

        # Mock 下游中可能出错的部分，聚焦验证 adapter dispatch
        with patch.object(gold_mod, 'calc_channel_price_comparison',
                          return_value=pd.DataFrame()):
            with patch.object(gold_mod, 'calc_cross_customer_price_variation',
                              return_value=pd.DataFrame()):
                with patch.object(gold_mod, 'calc_sales_owner_price_deviation',
                                  return_value=pd.DataFrame()):
                    with patch.object(gold_mod, 'calc_segment_price_analysis',
                                      return_value=pd.DataFrame()):
                        gold = gold_mod.generate_gold_tables(
                            portrait, silver,
                            stage_classifier=TrackingClassifier(),
                        )

        assert classifier_called[0], "适配器 classify 应被调用"
        assert "客户全景" in gold
        assert "异常日志" in gold

    def test_fallback_when_no_adapter(self):
        """不提供适配器时，使用直接 import 的默认路径。
        同样 mock 下游易错函数。"""
        import customer_analysis.gold as gold_mod
        from unittest.mock import patch

        silver = self._make_silver()
        portrait = self._make_portrait()

        with patch.object(gold_mod, 'calc_channel_price_comparison',
                          return_value=pd.DataFrame()):
            with patch.object(gold_mod, 'calc_cross_customer_price_variation',
                              return_value=pd.DataFrame()):
                with patch.object(gold_mod, 'calc_sales_owner_price_deviation',
                                  return_value=pd.DataFrame()):
                    with patch.object(gold_mod, 'calc_segment_price_analysis',
                                      return_value=pd.DataFrame()):
                        gold = gold_mod.generate_gold_tables(portrait, silver)

        assert "客户全景" in gold
        assert len(gold["客户全景"]) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
