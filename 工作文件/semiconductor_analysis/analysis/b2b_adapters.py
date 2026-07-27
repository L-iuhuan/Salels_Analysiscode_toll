"""
B2B v2 模块适配器 — 实现 core.interfaces 的 Protocol 接口。

P3: 每个适配器封装一个 b2b_v2 子模块的入口函数，
使其可通过 Pipeline DI 容器注入。

用法:
    from analysis.b2b_adapters import JourneyClassifierAdapter
    classifier = JourneyClassifierAdapter()
    result = classifier.classify(cust_monthly, config)
"""

from typing import Optional, Dict
import pandas as pd


class JourneyClassifierAdapter:
    """客户旅程阶段分类器适配器。"""

    def classify(self, customer_monthly: pd.DataFrame, config: dict,
                 channel_map: Optional[dict] = None) -> pd.DataFrame:
        """调用 b2b_v2.journey.stage_classifier.classify_customer_journey_stage。"""
        from b2b_v2.journey.stage_classifier import classify_customer_journey_stage
        return classify_customer_journey_stage(
            customer_monthly, config, channel_map=channel_map,
        )


class VolatilityCalculatorAdapter:
    """采购波动性计算器适配器。"""

    def batch_calculate(self, cust_monthly: pd.DataFrame,
                        config: Optional[dict] = None) -> pd.DataFrame:
        """调用 b2b_v2.behavior.volatility.batch_calc_volatility。"""
        from b2b_v2.behavior.volatility import batch_calc_volatility
        return batch_calc_volatility(cust_monthly, config)


class ProfitEstimatorAdapter:
    """真实利润估算器适配器。"""

    def batch_estimate(self, customer_df: pd.DataFrame,
                       config: Optional[dict] = None) -> pd.DataFrame:
        """调用 b2b_v2.profitability.true_profit_estimator.batch_estimate_true_profit。"""
        from b2b_v2.profitability.true_profit_estimator import batch_estimate_true_profit
        return batch_estimate_true_profit(customer_df, config)


class AnomalyDetectorAdapter:
    """异常检测器适配器。"""

    def detect(self, customer_df: pd.DataFrame, silver: dict,
               **kwargs) -> pd.DataFrame:
        """调用 b2b_v2.anomaly.run.run_anomaly_detection。"""
        from b2b_v2.anomaly.run import run_anomaly_detection
        return run_anomaly_detection(
            customer_df, silver,
            inv_aging=kwargs.get("inv_aging"),
            customer_inv_risk=kwargs.get("customer_inv_risk"),
        )


class ActionEngineAdapter:
    """行动建议引擎适配器。"""

    def suggest(self, customer_df: pd.DataFrame,
                anomaly_log: Optional[pd.DataFrame] = None,
                silver: Optional[dict] = None,
                **kwargs) -> Dict[str, pd.DataFrame]:
        """调用 b2b_v2.actions.run.run_action_suggestions。"""
        from b2b_v2.actions.run import run_action_suggestions
        return run_action_suggestions(
            customer_df, anomaly_log=anomaly_log, silver=silver,
            inv_aging=kwargs.get("inv_aging"),
            product_portrait=kwargs.get("product_portrait"),
            product_assoc=kwargs.get("product_assoc"),
        )
