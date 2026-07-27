"""
半导体分析管线 — Protocol 接口定义（P2-B）。

所有接口使用 typing.Protocol 实现结构子类型（duck typing），
不要求显式继承，只要对象具有匹配的方法签名即符合接口。
"""

from typing import Protocol, Dict, Any, Optional, List, Union
import pandas as pd


# ─── 数据加载 ───

class IDataLoader(Protocol):
    """数据加载器接口。"""
    def load(self, path: str, **kwargs) -> pd.DataFrame: ...
    def find_source(self, data_dir: str) -> str: ...


# ─── 数据清洗 ───

class IDataCleaner(Protocol):
    """数据清洗器接口。"""
    def clean(self, df: pd.DataFrame) -> pd.DataFrame: ...
    def validate(self, df: pd.DataFrame) -> list: ...


# ─── 数据聚合 ───

class IDataAggregator(Protocol):
    """数据聚合器接口。"""
    def aggregate(self, df: pd.DataFrame) -> Dict[str, pd.DataFrame]: ...


# ─── Silver 层构建 ───

class ISilverBuilder(Protocol):
    """Silver 层构建器接口。"""
    def build(self, source_path: str) -> Dict[str, Any]: ...


# ─── 分析器 ───

class IAnalyzer(Protocol):
    """分析器接口。"""
    def analyze(self, data: Dict[str, pd.DataFrame], config: Any = None) -> Any: ...


# ─── 评分器 ───

class IScorer(Protocol):
    """评分器接口。"""
    def score(self, portrait: pd.DataFrame) -> pd.DataFrame: ...


# ─── Gold 层生成 ───

class IGoldGenerator(Protocol):
    """Gold 层生成器接口。"""
    def generate(self, portrait: pd.DataFrame, silver: Optional[Dict] = None, **deps) -> Dict[str, pd.DataFrame]: ...


# ─── 报告生成 ───

class IReporter(Protocol):
    """报告生成器接口。"""
    def generate(self, gold: Dict[str, pd.DataFrame]) -> str: ...


# ─── 验证器 ───

class IValidator(Protocol):
    """数据验证器接口。"""
    def validate(self, df: pd.DataFrame, stage: str) -> Dict[str, Any]: ...


# ─── P3: B2B v2 模块接口 ───

class IStageClassifier(Protocol):
    """客户旅程阶段分类器接口。"""
    def classify(self, customer_monthly: pd.DataFrame, config: dict,
                 channel_map: Optional[dict] = None) -> pd.DataFrame: ...


class IVolatilityCalculator(Protocol):
    """采购波动性计算器接口。"""
    def batch_calculate(self, cust_monthly: pd.DataFrame,
                        config: Optional[dict] = None) -> pd.DataFrame: ...


class IProfitEstimator(Protocol):
    """真实利润估算器接口。"""
    def batch_estimate(self, customer_df: pd.DataFrame,
                       config: Optional[dict] = None) -> pd.DataFrame: ...


class IAnomalyDetector(Protocol):
    """异常检测器接口。"""
    def detect(self, customer_df: pd.DataFrame, silver: dict,
               **kwargs) -> pd.DataFrame: ...


class IActionEngine(Protocol):
    """行动建议引擎接口。"""
    def suggest(self, customer_df: pd.DataFrame,
                anomaly_log: Optional[pd.DataFrame] = None,
                silver: Optional[dict] = None,
                **kwargs) -> Dict[str, pd.DataFrame]: ...
