"""
应用配置 — AppConfig 数据类。

从 config/settings.py 加载默认值（通过 from_defaults()），
支持 from_dict() 用于未来 YAML/JSON 配置。
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from pathlib import Path


@dataclass
class PathConfig:
    """路径配置。"""
    project_root: str = ""
    data_dir: str = ""
    output_silver: str = ""
    output_gold: str = ""
    output_report: str = ""

    @classmethod
    def from_root(cls, root: str) -> "PathConfig":
        return cls(
            project_root=root,
            data_dir=str(Path(root) / "data"),
            output_silver=str(Path(root) / "output" / "silver"),
            output_gold=str(Path(root) / "output" / "gold"),
            output_report=str(Path(root) / "output" / "report"),
        )


@dataclass
class CleanConfig:
    """清洗配置。"""
    winsor_lower: float = -0.50
    winsor_upper: float = 0.75
    sample_z_threshold: float = 2.0
    erp_col_map: Dict[str, str] = field(default_factory=dict)


@dataclass
class PricingConfig:
    """价格治理配置。"""
    days_per_month_estimate: float = 30.4375
    markup_price_ratio: float = 0.90
    markup_max_customer_share: float = 0.30
    markup_min_active_months: int = 6
    markdown_default_elasticity: float = -1.0
    markdown_discount_rates: List[float] = field(
        default_factory=lambda: [0.03, 0.05, 0.08, 0.10]
    )
    markdown_break_even_buffer: float = 1.2
    price_dispersion_cv_threshold: float = 0.30


@dataclass
class CustomerAnalysisWindow:
    """客户分析窗口配置。"""
    start_date: str = "2024-01-01"
    value_window_months: int = 12
    growth_window_months: int = 12
    growth_window_short: int = 6
    risk_window_months: int = 6
    active_window_months: int = 12


@dataclass
class ProductLifecycleConfig:
    """产品生命周期配置。"""
    data_start_date: str = "2020-01-01"
    incomplete_month_threshold_day: int = 25
    growth_accelerate: float = 0.15
    growth_flat_lower: float = -0.10
    new_product_months: int = 6
    exit_months: int = 12
    exit_min_age_months: int = 3
    risk_weights: Dict[str, float] = field(default_factory=lambda: {
        "毛利率趋势斜率": 0.411,
        "增速衰减": 0.236,
        "自比健康度": 0.353,
    })


@dataclass
class AppConfig:
    """应用总配置。"""
    paths: PathConfig = field(default_factory=PathConfig)
    clean: CleanConfig = field(default_factory=CleanConfig)
    pricing: PricingConfig = field(default_factory=PricingConfig)
    customer_window: CustomerAnalysisWindow = field(
        default_factory=CustomerAnalysisWindow
    )
    product: ProductLifecycleConfig = field(default_factory=ProductLifecycleConfig)
    skip_silver_if_exists: bool = True
    report_retention_count: int = 10
    run_stages: List[str] = field(
        default_factory=lambda: ["silver", "product", "customer", "kpi", "cross_ref"]
    )

    @classmethod
    def from_dict(cls, data: dict) -> "AppConfig":
        """从字典加载配置。"""
        return cls(
            paths=PathConfig(**data.get("paths", {})),
            clean=CleanConfig(**data.get("clean", {})),
            pricing=PricingConfig(**data.get("pricing", {})),
            customer_window=CustomerAnalysisWindow(
                **data.get("customer_window", {})
            ),
            product=ProductLifecycleConfig(**data.get("product", {})),
            skip_silver_if_exists=data.get("skip_silver_if_exists", True),
            report_retention_count=data.get("report_retention_count", 10),
            run_stages=data.get(
                "run_stages", ["silver", "product", "customer", "kpi", "cross_ref"]
            ),
        )

    @classmethod
    def from_defaults(cls) -> "AppConfig":
        """使用默认配置（向后兼容）。"""
        return cls()
