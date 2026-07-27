"""
P2-A: SimpleValidator 单元测试。

覆盖：
  - 通用检查：必填列、空值率、值范围、分类值
  - 阶段验证：raw / clean / silver / gold
  - 边界情况：空 DataFrame、NaN、极值
"""

import sys
import os
import pandas as pd
import numpy as np
import pytest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from data_pipeline.validator import SimpleValidator

v = SimpleValidator()


# ============================================================
# 通用检查
# ============================================================

class TestCheckRequiredColumns:
    def test_all_present(self):
        df = pd.DataFrame({"A": [1], "B": [2]})
        assert v.check_required_columns(df, ["A", "B"]) == []

    def test_missing_one(self):
        df = pd.DataFrame({"A": [1]})
        assert v.check_required_columns(df, ["A", "B"]) == ["B"]

    def test_all_missing(self):
        df = pd.DataFrame({"X": [1]})
        assert v.check_required_columns(df, ["A", "B"]) == ["A", "B"]


class TestCheckNullConstraint:
    def test_no_null(self):
        df = pd.DataFrame({"A": [1.0, 2.0]})
        assert v.check_null_constraint(df, ["A"]) == []

    def test_partial_null_under_threshold(self):
        df = pd.DataFrame({"A": [1.0, None, 2.0]})
        assert v.check_null_constraint(df, ["A"], max_null_pct=0.5) == []

    def test_null_above_threshold(self):
        df = pd.DataFrame({"A": [1.0, None, None, None]})
        issues = v.check_null_constraint(df, ["A"], max_null_pct=0.5)
        assert len(issues) == 1
        assert "null" in issues[0]

    def test_missing_column(self):
        df = pd.DataFrame({"A": [1]})
        issues = v.check_null_constraint(df, ["B"])
        assert "missing" in issues[0]


class TestCheckValueRange:
    def test_all_in_range(self):
        df = pd.DataFrame({"A": [1.0, 2.0, 3.0]})
        assert v.check_value_range(df, "A", lo=0, hi=10) == []

    def test_below_lo(self):
        df = pd.DataFrame({"A": [-1.0, 2.0]})
        issues = v.check_value_range(df, "A", lo=0)
        assert len(issues) == 1
        assert "below" in issues[0]

    def test_above_hi(self):
        df = pd.DataFrame({"A": [5.0, 15.0]})
        issues = v.check_value_range(df, "A", hi=10)
        assert len(issues) == 1
        assert "above" in issues[0]

    def test_missing_column(self):
        df = pd.DataFrame({"A": [1]})
        issues = v.check_value_range(df, "B", lo=0)
        assert "missing" in issues[0]


class TestCheckCategoryValues:
    def test_all_valid(self):
        df = pd.DataFrame({"A": ["x", "y"]})
        assert v.check_category_values(df, "A", ["x", "y"]) == []

    def test_invalid_found(self):
        df = pd.DataFrame({"A": ["x", "z"]})
        issues = v.check_category_values(df, "A", ["x", "y"])
        assert len(issues) == 1
        assert "invalid" in issues[0]

    def test_missing_column(self):
        df = pd.DataFrame({"A": [1]})
        issues = v.check_category_values(df, "B", ["x"])
        assert "missing" in issues[0]


# ============================================================
# 阶段验证
# ============================================================

class TestValidateRaw:
    def test_valid_raw(self):
        df = pd.DataFrame({
            "客户编号": ["C001"],
            "产品品种": ["P001"],
            "数量": [10],
            "金额": [1000.0],
            "发货日期": pd.to_datetime(["2025-01-15"]),
        })
        result = v.validate_raw(df)
        assert result["valid"] is True
        assert result["issues"] == []

    def test_missing_columns(self):
        df = pd.DataFrame({"客户编号": ["C001"]})
        result = v.validate_raw(df)
        assert result["valid"] is False
        assert len(result["issues"]) >= 1

    def test_negative_revenue(self):
        df = pd.DataFrame({
            "客户编号": ["C001"],
            "产品品种": ["P001"],
            "数量": [10],
            "金额": [-100.0],
            "发货日期": pd.to_datetime(["2025-01-15"]),
        })
        result = v.validate_raw(df)
        assert result["valid"] is False
        assert any("below" in i for i in result["issues"])

    def test_empty_df(self):
        df = pd.DataFrame()
        result = v.validate_raw(df)
        assert result["valid"] is False


class TestValidateClean:
    def test_valid_clean(self):
        df = pd.DataFrame({
            "客户编号": ["C001"],
            "产品品种": ["P001"],
            "数量": [10],
            "金额": [1000.0],
            "利润": [300.0],
            "发货日期": pd.to_datetime(["2025-01-15"]),
            "_毛利率": [0.30],
        })
        result = v.validate_clean(df)
        assert result["valid"] is True

    def test_margin_out_of_range_hi(self):
        df = pd.DataFrame({
            "客户编号": ["C001"],
            "产品品种": ["P001"],
            "数量": [10],
            "金额": [1000.0],
            "利润": [300.0],
            "发货日期": pd.to_datetime(["2025-01-15"]),
            "_毛利率": [0.80],
        })
        result = v.validate_clean(df)
        assert result["valid"] is False
        assert any("above" in i for i in result["issues"])

    def test_margin_out_of_range_lo(self):
        df = pd.DataFrame({
            "客户编号": ["C001"],
            "产品品种": ["P001"],
            "数量": [10],
            "金额": [1000.0],
            "利润": [300.0],
            "发货日期": pd.to_datetime(["2025-01-15"]),
            "_毛利率": [-0.60],
        })
        result = v.validate_clean(df)
        assert result["valid"] is False
        assert any("below" in i for i in result["issues"])

    def test_negative_qty(self):
        df = pd.DataFrame({
            "客户编号": ["C001"],
            "产品品种": ["P001"],
            "数量": [-5],
            "金额": [1000.0],
            "利润": [300.0],
            "发货日期": pd.to_datetime(["2025-01-15"]),
            "_毛利率": [0.30],
        })
        result = v.validate_clean(df)
        assert result["valid"] is False
        assert any("below" in i for i in result["issues"])


class TestValidateSilver:
    def test_valid_silver(self):
        silver = {
            "customer_monthly": pd.DataFrame({
                "_月": pd.to_datetime(["2025-01-01"]),
                "rev_sum": [1000.0],
                "qty_sum": [100],
            }),
            "product_monthly": pd.DataFrame({
                "_月": pd.to_datetime(["2025-01-01"]),
                "rev_sum": [2000.0],
                "qty_sum": [200],
            }),
            "customer_x_product": pd.DataFrame({
                "_月": pd.to_datetime(["2025-01-01"]),
                "rev_sum": [500.0],
                "qty_sum": [50],
            }),
        }
        result = v.validate_silver(silver)
        assert result["valid"] is True

    def test_missing_column(self):
        silver = {
            "customer_monthly": pd.DataFrame({"rev_sum": [1000.0]}),
        }
        result = v.validate_silver(silver)
        assert result["valid"] is False

    def test_negative_rev_sum(self):
        silver = {
            "customer_monthly": pd.DataFrame({
                "_月": pd.to_datetime(["2025-01-01"]),
                "rev_sum": [-100.0],
                "qty_sum": [100],
            }),
        }
        result = v.validate_silver(silver)
        assert result["valid"] is False


class TestValidateGold:
    def test_valid_gold(self):
        df = pd.DataFrame({
            "客户编号": ["C001"],
            "风险得分": [50],
            "机会得分": [75],
            "渠道类型": ["代理"],
        })
        result = v.validate_gold(df, label="test")
        assert result["valid"] is True

    def test_score_out_of_range(self):
        df = pd.DataFrame({
            "风险得分": [-5],
            "机会分值": [150],
        })
        result = v.validate_gold(df)
        assert result["valid"] is False
        assert len(result["issues"]) == 2

    def test_empty_dataframe(self):
        df = pd.DataFrame()
        result = v.validate_gold(df)
        assert result["valid"] is False
        assert any("empty" in i for i in result["issues"])


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
