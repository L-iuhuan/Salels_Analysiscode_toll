"""
P2-D: Gold 层辅助表构建器测试。

测试覆盖:
    1. build_customer_product_bridge — 桥接表构建
    2. build_portfolio_health — 组合健康度表
    3. build_product_association — 产品关联规则
"""

import os
import sys
import pytest
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from analysis.gold_builders import (
    build_customer_product_bridge,
    build_portfolio_health,
    build_product_association,
)


@pytest.fixture
def silver_with_cxp():
    """含 customer_x_product 的 Silver 字典。"""
    cxp = pd.DataFrame({
        "客户编号": ["C001", "C001", "C002", "C002"],
        "产品品种": ["PU-1", "PU-2", "PU-1", "PU-3"],
        "rev_sum": [100.0, 200.0, 150.0, 50.0],
        "_月": pd.PeriodIndex(["202401", "202401", "202402", "202402"], freq="M"),
    })
    return {
        "customer_x_product": cxp,
        "customer_monthly": pd.DataFrame(),
        "product_monthly": pd.DataFrame(),
    }


@pytest.fixture
def silver_insufficient():
    """数据不足的 Silver 字典。"""
    return {
        "customer_x_product": pd.DataFrame({
            "客户编号": ["C001"],
            "产品品种": ["PU-1"],
            "rev_sum": [100.0],
            "_月": pd.PeriodIndex(["202401"], freq="M"),
        }),
    }


# ============================================================
# Test: build_customer_product_bridge
# ============================================================

class TestBuildBridge:
    """客户×产品桥接表构建测试。"""

    def test_bridge_without_portrait(self, silver_with_cxp):
        """无产品画像时返回原始复制。"""
        result = build_customer_product_bridge(silver_with_cxp)
        expected_cols = ["客户编号", "产品品种", "rev_sum", "_月"]
        for c in expected_cols:
            assert c in result.columns

    def test_bridge_returns_dataframe(self, silver_with_cxp):
        """返回类型为 DataFrame。"""
        result = build_customer_product_bridge(silver_with_cxp)
        assert isinstance(result, pd.DataFrame)

    def test_bridge_preserves_cxp_rows(self, silver_with_cxp):
        """行数与原始 customer_x_product 一致。"""
        result = build_customer_product_bridge(silver_with_cxp)
        assert len(result) == len(silver_with_cxp["customer_x_product"])


# ============================================================
# Test: build_portfolio_health
# ============================================================

class TestBuildPortfolioHealth:
    """客户组合健康度表构建测试。"""

    def test_no_portrait_column(self):
        """无当前画像列时返回空 DataFrame。"""
        cp = pd.DataFrame({"客户编号": ["C001"], "rev_sum": [100.0]})
        result = build_portfolio_health(cp)
        assert isinstance(result, pd.DataFrame)
        assert len(result) == 0

    def test_single_customer(self):
        """单个客户的基础聚合。"""
        cp = pd.DataFrame({
            "客户编号": ["C001", "C001"],
            "产品品种": ["PU-1", "PU-2"],
            "rev_sum": [100.0, 200.0],
            "当前画像": ["成长期", "现金牛"],
        })
        result = build_portfolio_health(cp)
        assert len(result) == 1
        assert result.iloc[0]["客户编号"] == "C001"
        assert result.iloc[0]["总品种数"] == 2
        assert result.iloc[0]["总金额"] == 300.0

    def test_decay_risk_ratio(self):
        """衰退风险品金额占比计算。"""
        cp = pd.DataFrame({
            "客户编号": ["C001", "C001", "C001", "C001"],
            "产品品种": ["PU-1", "PU-2", "PU-3", "PU-4"],
            "rev_sum": [100.0, 200.0, 50.0, 50.0],
            "当前画像": ["成长期", "现金牛", "衰退期", "隐性衰退"],
        })
        result = build_portfolio_health(cp)
        # 衰退金额 = 50 + 50 = 100, 总金额 = 400, 占比 = 0.25
        assert pytest.approx(result.iloc[0]["衰退风险品金额占比"], 0.01) == 0.25

    def test_all_growth_only(self):
        """全部成长期 → 衰退金额占比为 0。"""
        cp = pd.DataFrame({
            "客户编号": ["C001"],
            "产品品种": ["PU-1"],
            "rev_sum": [100.0],
            "当前画像": ["成长期"],
        })
        result = build_portfolio_health(cp)
        assert result.iloc[0]["衰退风险品金额占比"] == 0.0


# ============================================================
# Test: build_product_association
# ============================================================

class TestBuildProductAssociation:
    """产品关联分析构建测试。"""

    def test_insufficient_data(self, silver_insufficient):
        """<100 行时应返回空 DataFrame。"""
        result = build_product_association(silver_insufficient)
        assert isinstance(result, pd.DataFrame)
        assert len(result) == 0

    def test_sufficient_data_dtypes(self):
        """足够数据时返回正确类型的列。"""
        n = 120
        cxp = pd.DataFrame({
            "客户编号": [f"C{i % 10:03d}" for i in range(n)],
            "产品品种": [f"PU-{i % 5 + 1}" for i in range(n)],
            "rev_sum": [100.0 + i for i in range(n)],
            "_月": pd.PeriodIndex(
                [f"2024{(i % 12) + 1:02d}" for i in range(n)], freq="M"
            ),
        })
        silver = {"customer_x_product": cxp}
        result = build_product_association(silver, assoc_thresholds={
            "assoc_min_support": 0.01,
            "assoc_min_confidence": 0.01,
        })
        if len(result) > 0:
            expected = {"产品A", "产品B", "支持度", "置信度", "提升度"}
            assert expected.issubset(set(result.columns))


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
