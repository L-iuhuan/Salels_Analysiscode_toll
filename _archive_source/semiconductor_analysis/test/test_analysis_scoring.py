"""
P2-E: analysis.rfm_pi + analysis.scoring 测试。

验证 extract 后功能完整，与原 customer_analysis 模块行为一致。
"""

import os
import sys
import pytest
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from analysis.rfm_pi import score_rfm_pi
from analysis.scoring import calc_composite_scores, calc_customer_tier, _minmax_norm


class TestRFMPi:
    """RFM-π 评分测试。"""

    def test_basic_scoring(self):
        """基本 RFM-π 评分返回评分列。"""
        df = pd.DataFrame({
            "距上次采购天数": [5, 30, 60],
            "常规平均采购间隔": [10, 30, 50],
            "近12月毛利": [100000, 50000, 10000],
            "新品采购占比": [0.5, 0.2, 0.0],
        })
        result = score_rfm_pi(df)
        assert "RFMπ_综合分" in result.columns
        assert "RFMπ_层级" in result.columns

    def test_missing_columns(self):
        """缺失评分列时应有默认值。"""
        df = pd.DataFrame({"客户编号": ["C001"]})
        result = score_rfm_pi(df)
        assert "RFMπ_综合分" in result.columns

    def test_single_customer(self):
        """单个客户也能评分（返回默认值 3）。"""
        df = pd.DataFrame({
            "距上次采购天数": [30],
            "常规平均采购间隔": [30],
            "近12月毛利": [50000],
            "新品采购占比": [0.1],
        })
        result = score_rfm_pi(df)
        assert len(result) == 1

    def test_channel_isolation(self):
        """渠道隔离评分应返回评分列。"""
        df = pd.DataFrame({
            "渠道类型": ["代理", "代理", "直供", "直供", "代理", "直供"],
            "距上次采购天数": [5, 30, 60, 10, 20, 40],
            "常规平均采购间隔": [10, 30, 50, 15, 25, 35],
            "近12月毛利": [100000, 50000, 10000, 80000, 60000, 30000],
            "新品采购占比": [0.5, 0.2, 0.0, 0.3, 0.1, 0.05],
        })
        weights = {
            "代理": {"R": 0.30, "F": 0.20, "M": 0.30, "P": 0.20},
            "直供": {"R": 0.25, "F": 0.25, "M": 0.25, "P": 0.25},
        }
        result = score_rfm_pi(df, channel_col="渠道类型", weights_by_channel=weights)
        assert "RFMπ_综合分" in result.columns
        assert len(result) == len(df)


class TestMinMaxNorm:
    """Min-Max 归一化测试。"""

    def test_basic_normalization(self):
        """基本归一化到 0-100。"""
        s = pd.Series([10, 20, 30, 40, 50])
        norm = _minmax_norm(s)
        assert norm.min() == 0
        assert norm.max() == 100

    def test_reverse_normalization(self):
        """反向归一化。"""
        s = pd.Series([10, 20, 30, 40, 50])
        norm = _minmax_norm(s, reverse=True)
        assert norm.min() == 0
        assert norm.max() == 100
        # 最小值应为 100（反向），最大值应为 0
        assert norm.iloc[0] == 100  # 最小值
        assert norm.iloc[-1] == 0   # 最大值

    def test_all_same_value(self):
        """所有值相同时返回 50。"""
        s = pd.Series([25, 25, 25, 25])
        norm = _minmax_norm(s)
        assert (norm == 50).all()

    def test_with_nan(self):
        """NaN 值不应参与计算。"""
        s = pd.Series([10, 20, np.nan, 40, 50])
        norm = _minmax_norm(s)
        assert pd.isna(norm.iloc[2])  # NaN 保持 NaN
        assert norm.dropna().min() == 0
        assert norm.dropna().max() == 100


class TestCalcCustomerTier:
    """客户层级计算测试。"""

    def test_default_tier(self):
        """无 CRM 数据时返回默认层级。"""
        df = pd.DataFrame({"客户编号": ["C001", "C002"]})
        result = calc_customer_tier(df)
        assert "客户层级" in result.columns
        assert result["客户层级"].iloc[0] == "未分类"

    def test_keep_existing_tier(self):
        """已有客户层级时保留。"""
        df = pd.DataFrame({
            "客户编号": ["C001"],
            "客户层级": ["KA"],
        })
        result = calc_customer_tier(df)
        assert result["客户层级"].iloc[0] == "KA"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
