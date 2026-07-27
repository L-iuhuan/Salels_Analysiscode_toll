"""
Pipeline — 半导体分析管线依赖注入容器（P2-B）。

所有依赖通过构造函数注入，而不是在模块内部直接 import。
默认使用生产实现，测试中可注入 Mock。

Usage:
    config = AppConfig.from_defaults()
    pipeline = Pipeline(config=config)
    pipeline.run(stages=["silver", "product"])
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from core.interfaces import (
    IDataLoader, IDataCleaner, IDataAggregator, ISilverBuilder,
    IAnalyzer, IScorer, IGoldGenerator, IReporter, IValidator,
    IStageClassifier, IVolatilityCalculator, IProfitEstimator,
    IAnomalyDetector, IActionEngine,
)
from core.config import AppConfig


@dataclass
class Pipeline:
    """半导体分析管线 — 依赖注入容器。

    所有依赖默认为 None，在 __post_init__ 中自动装配生产实现。
    测试时可传入 Mock 覆盖任意依赖。
    """
    config: AppConfig = field(default_factory=AppConfig.from_defaults)

    # 可注入的依赖
    data_loader: Optional[IDataLoader] = None
    data_cleaner: Optional[IDataCleaner] = None
    data_aggregator: Optional[IDataAggregator] = None
    silver_builder: Optional[ISilverBuilder] = None
    product_analyzer: Optional[IAnalyzer] = None
    customer_analyzer: Optional[IAnalyzer] = None
    scorer: Optional[IScorer] = None
    gold_generator: Optional[IGoldGenerator] = None
    reporter: Optional[IReporter] = None
    validator: Optional[IValidator] = None

    # P3: B2B v2 模块依赖
    stage_classifier: Optional[IStageClassifier] = None
    volatility_calculator: Optional[IVolatilityCalculator] = None
    profit_estimator: Optional[IProfitEstimator] = None
    anomaly_detector: Optional[IAnomalyDetector] = None
    action_engine: Optional[IActionEngine] = None

    timing_enabled: bool = False

    # 运行状态
    _results: Dict[str, Any] = field(default_factory=dict, repr=False)

    def __post_init__(self):
        """自动装配默认实现。"""
        if self.data_loader is None:
            from data_pipeline.loader import ExcelDataLoader
            self.data_loader = ExcelDataLoader()
        if self.data_cleaner is None:
            from data_pipeline.cleaner import DefaultCleaner
            self.data_cleaner = DefaultCleaner(self.config)
        if self.data_aggregator is None:
            from data_pipeline.aggregator import DefaultAggregator
            self.data_aggregator = DefaultAggregator()

        if self.validator is None:
            from data_pipeline.validator import SimpleValidator
            self.validator = SimpleValidator()

        # P3: B2B v2 模块 — 延迟装配（按需加载）
        self._lazy_init("stage_classifier",
                        "analysis.b2b_adapters", "JourneyClassifierAdapter")
        self._lazy_init("volatility_calculator",
                        "analysis.b2b_adapters", "VolatilityCalculatorAdapter")
        self._lazy_init("profit_estimator",
                        "analysis.b2b_adapters", "ProfitEstimatorAdapter")
        self._lazy_init("anomaly_detector",
                        "analysis.b2b_adapters", "AnomalyDetectorAdapter")
        self._lazy_init("action_engine",
                        "analysis.b2b_adapters", "ActionEngineAdapter")

    def _lazy_init(self, attr: str, module: str, class_name: str):
        """延迟导入并设置依赖。"""
        if getattr(self, attr) is not None:
            return
        import importlib
        mod = importlib.import_module(module)
        cls = getattr(mod, class_name)
        setattr(self, attr, cls())

    def run(self, stages: Optional[List[str]] = None,
            source_path: Optional[str] = None) -> Dict[str, Any]:
        """执行管线。"""
        stages = stages or self.config.run_stages
        self._results = {}

        for stage in stages:
            stage_fn = getattr(self, f"_run_{stage}", None)
            if stage_fn is None:
                print(f"  [Pipeline] 未知阶段 '{stage}'，跳过")
                continue
            print(f"\n{'=' * 60}")
            print(f"[Pipeline] 阶段: {stage}")
            print(f"{'=' * 60}")
            stage_fn(source_path=source_path)

        return self._results

    def _run_silver(self, source_path: str = None, **kwargs):
        """Silver 层构建阶段。"""
        if source_path is None:
            source_path = self.data_loader.find_source(
                self.config.paths.data_dir
            )

        raw = self.data_loader.load(source_path)

        cleaned = self.data_cleaner.clean(raw)
        # 修复5: clean() 已完成 ERP 列名重命名，此时验证列名正确
        self.validator.validate(cleaned, "raw")
        self.validator.validate(cleaned, "clean")

        silver = self.data_aggregator.aggregate(cleaned)
        self.validator.validate_silver(silver)

        self._results["silver"] = silver
        self._results["raw"] = raw
        print(f"  [Pipeline] Silver 层构建完成: {len(silver)} 张表")

    def _run_product(self, **kwargs):
        """产品生命周期分析阶段。"""
        from product_lifecycle.run import run_analysis

        silver = self._results.get("silver")
        if silver is None:
            print("  [Pipeline] 产品分析需要先执行 silver 阶段")
            return

        result = run_analysis(
            "via_pipeline",
            df=self._results.get("raw")
        )
        self._results["product"] = result
        print(f"  [Pipeline] 产品分析完成")

    def _run_customer(self, **kwargs):
        """客户销售分析阶段。

        修复1+2: 将 run_customer() 返回的 gold_tables 提取到
        _results["gold"] 和 _results["customer_portrait"]，
        供 _run_gold / _run_scoring 使用。
        """
        from customer_analysis.run_pipeline import run as run_customer

        silver = self._results.get("silver")
        if silver is None:
            print("  [Pipeline] 客户分析需要先执行 silver 阶段")
            return

        result = run_customer(
            "via_pipeline",
            skip_silver=True,
            raw_data=self._results.get("raw"),
            cust_info_data=self._results.get("cust_info"),
        )
        self._results["customer"] = result

        # 提取 gold_tables 供下游阶段使用
        gold_tables = result.get("gold_tables", {})
        if gold_tables:
            self._results["gold"] = gold_tables
            # 客户全景 = 评分后的 portrait，供给 _run_scoring 使用
            if "客户全景" in gold_tables:
                self._results["customer_portrait"] = gold_tables["客户全景"]
        print(f"  [Pipeline] 客户分析完成 ({result.get('customer_count', 0)} 个客户, "
              f"{len(gold_tables)} 张 gold 表)")

    def _run_kpi(self, **kwargs):
        """准实时 KPI 阶段。"""
        from customer_analysis.run_kpi_daily import run as run_kpi
        run_kpi("via_pipeline", raw_df=self._results.get("raw"))
        self._results["kpi"] = True

    def _run_gold(self, **kwargs):
        """Gold 层输出阶段 — 写入 CSV + 格式化 Excel。

        修复1: 如果 _run_customer 已生成 gold 表，直接导出；
        否则尝试从 silver + customer_portrait 生成 gold 表后再导出。
        不再把 silver 数据当 gold_dict 使用。
        """
        from reports.gold_exporter import GoldExporter

        gold_dict = self._results.get("gold")
        if gold_dict is None:
            # 尝试从 silver + portrait 生成 gold 表
            silver = self._results.get("silver")
            customer_df = self._results.get("customer_portrait")
            if silver is not None and customer_df is not None:
                from customer_analysis.gold import generate_gold_tables
                gold_dict = generate_gold_tables(customer_df, silver)
                self._results["gold"] = gold_dict
                print(f"  [Pipeline] Gold 表生成: {len(gold_dict)} 张")

        if gold_dict is None:
            print("  [Pipeline] Gold 生成需要先执行 silver + customer 阶段")
            return

        exporter = GoldExporter()
        report_path = exporter.save(gold_dict, output_dir=self.config.paths.output_gold)
        self._results["report"] = report_path
        print(f"  [Pipeline] Gold 输出完成: {report_path}")

    def _run_scoring(self, **kwargs):
        """B2B v2 评分阶段 — 旅程分类 + 波动性 + 利润估算 + 异常检测 + 行动建议。

        P3: 使用 analysis.b2b_adapters 中的适配器，
        可通过 Pipeline DI 注入 Mock 进行单元测试。

        修复4: 如果 customer 阶段已执行（评分已在 generate_gold_tables 中完成），则跳过。
        """
        if self._results.get("customer"):
            print("  [Pipeline] 评分阶段已在 customer 阶段完成，跳过")
            return

        from config.settings import (
            CUSTOMER_JOURNEY_THRESHOLDS, VOLATILITY_METRICS, ESTIMATED_COST,
        )

        silver = self._results.get("silver")
        customer_df = self._results.get("customer_portrait")
        if silver is None or customer_df is None:
            print("  [Pipeline] 评分阶段需要先执行 silver + customer 阶段")
            return

        cust_monthly = silver.get("customer_monthly")
        if cust_monthly is not None and len(cust_monthly) > 0:
            # 1. 旅程阶段分类
            channel_map = None
            if "渠道类型" in customer_df.columns:
                channel_map = dict(zip(
                    customer_df["客户编号"], customer_df["渠道类型"],
                ))
            journey = self.stage_classifier.classify(
                cust_monthly, CUSTOMER_JOURNEY_THRESHOLDS,
                channel_map=channel_map,
            )
            customer_df = customer_df.merge(journey, on="客户编号", how="left")
            print(f"  [Pipeline] 旅程分类完成")

            # 2. 波动性指标
            volatility = self.volatility_calculator.batch_calculate(
                cust_monthly, VOLATILITY_METRICS,
            )
            customer_df = customer_df.merge(volatility, on="客户编号", how="left")
            print(f"  [Pipeline] 波动性计算完成")

        # 3. 真实利润估算
        profit = self.profit_estimator.batch_estimate(customer_df, ESTIMATED_COST)
        customer_df = customer_df.merge(profit, on="客户编号", how="left")
        print(f"  [Pipeline] 利润估算完成")

        # 4. 异常检测
        try:
            anomaly_log = self.anomaly_detector.detect(customer_df, silver)
            self._results["anomaly_log"] = anomaly_log
            print(f"  [Pipeline] 异常检测完成 ({len(anomaly_log)} 条)")
        except Exception as e:
            print(f"  [Pipeline] 异常检测跳过: {e}")
            anomaly_log = None

        # 5. 行动建议
        try:
            actions = self.action_engine.suggest(
                customer_df, anomaly_log=anomaly_log, silver=silver,
            )
            self._results["actions"] = actions
            print(f"  [Pipeline] 行动建议完成")
        except Exception as e:
            print(f"  [Pipeline] 行动建议跳过: {e}")

        self._results["customer_portrait"] = customer_df

    def _run_cross_ref(self, **kwargs):
        """交叉关联阶段。"""
        from cross_reference.run_cross_ref import run as run_cross
        result = run_cross()
        self._results["cross_ref"] = result
