"""
P2-D: GoldExporter 测试。

测试覆盖:
    1. CSV 文件写入
    2. 预警行索引计算
    3. 清理旧报告
    4. Excel 报告路径返回
"""

import os
import sys
import pytest
import pandas as pd
import numpy as np
import tempfile
import shutil
from datetime import datetime, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from reports.gold_exporter import GoldExporter, GOLD_CSV_MAP


@pytest.fixture
def temp_output(tmp_path):
    """临时输出目录。"""
    return str(tmp_path / "gold")


@pytest.fixture
def sample_gold():
    """测试用 Gold 字典。"""
    return {
        "客户全景": pd.DataFrame({
            "客户编号": ["C001", "C002", "C003", "C004"],
            "风险评级": ["低", "高", "极高", "低"],
            "客户生命周期": ["成长期", "衰退期", "休眠期", "成长期"],
            "采购中断预警": [False, True, False, False],
            "近12月收入": [1000, 500, 200, 800],
        }),
        "异常日志": pd.DataFrame({
            "客户编号": ["C003"],
            "异常等级": ["高"],
            "异常描述": ["采购中断"],
        }),
        "SKU生命周期": pd.DataFrame({
            "产品品种": ["PU-1", "PU-2"],
            "生命周期": ["成长期", "衰退期"],
        }),
    }


# ============================================================
# Test: CSV 写入
# ============================================================

class TestCSVOutput:
    """CSV 写入测试。"""

    def test_writes_csv_files(self, sample_gold, temp_output):
        """写入 CSV 文件到指定目录。"""
        exporter = GoldExporter()
        exporter.save(sample_gold, output_dir=temp_output)
        csv_path = os.path.join(temp_output, "客户全景.csv")
        assert os.path.exists(csv_path)

    def test_csv_has_data(self, sample_gold, temp_output):
        """写入的 CSV 可读回并含有数据。"""
        exporter = GoldExporter()
        exporter.save(sample_gold, output_dir=temp_output)
        csv_path = os.path.join(temp_output, "客户全景.csv")
        df = pd.read_csv(csv_path, encoding="utf-8-sig")
        assert len(df) == 4
        assert "客户编号" in df.columns

    def test_skip_empty_table(self, temp_output):
        """空表不应写入 CSV。"""
        gold = {"客户全景": pd.DataFrame()}
        exporter = GoldExporter()
        exporter.save(gold, output_dir=temp_output)
        csv_path = os.path.join(temp_output, "客户全景.csv")
        assert not os.path.exists(csv_path)

    def test_only_writes_known_tables(self, temp_output):
        """未在 GOLD_CSV_MAP 中的表不会写入。"""
        gold = {"未知表": pd.DataFrame({"x": [1]})}
        exporter = GoldExporter()
        exporter.save(gold, output_dir=temp_output)
        assert len(os.listdir(temp_output)) == 0


# ============================================================
# Test: 预警行
# ============================================================

class TestWarningIndices:
    """预警行索引计算测试。"""

    def test_high_risk_warning(self):
        """风险评级为高应触发预警。"""
        gold = {
            "客户全景": pd.DataFrame({
                "风险评级": ["高"],
            }),
        }
        exporter = GoldExporter()
        indices = exporter._calc_warning_indices(gold)
        assert 0 in indices

    def test_no_warning(self):
        """无警告标记时返回空集合。"""
        gold = {
            "客户全景": pd.DataFrame({
                "风险评级": ["低"],
                "采购中断预警": [False],
                "强依赖标记": [False],
                "客户生命周期": ["成长期"],
            }),
        }
        exporter = GoldExporter()
        indices = exporter._calc_warning_indices(gold)
        assert indices == set()

    def test_churn_warning_true_value(self):
        """采购中断预警=是 应触发预警。"""
        gold = {
            "客户全景": pd.DataFrame({
                "采购中断预警": ["是"],
            }),
        }
        exporter = GoldExporter()
        indices = exporter._calc_warning_indices(gold)
        assert 0 in indices

    def test_lifecycle_warning(self):
        """生命周期=衰退期 应触发预警。"""
        gold = {
            "客户全景": pd.DataFrame({
                "客户生命周期": ["衰退期"],
            }),
        }
        exporter = GoldExporter()
        indices = exporter._calc_warning_indices(gold)
        assert 0 in indices


# ============================================================
# Test: 报告路径
# ============================================================

class TestReportPath:
    """Excel 报告路径测试。"""

    def test_returns_string_path(self, sample_gold, temp_output, monkeypatch):
        """save 返回字符串路径（monkeypatch 打开开关，走完整 Excel 路径）。"""
        from config.settings import EXCEL_REPORT
        monkeypatch.setitem(EXCEL_REPORT, "customer_enabled", True)  # 批次⑦默认关闭,测试显式打开覆盖导出路径
        exporter = GoldExporter()
        path = exporter.save(sample_gold, output_dir=temp_output)
        assert isinstance(path, str)
        assert path.endswith(".xlsx")

    def test_returns_none_when_disabled(self, sample_gold, temp_output, monkeypatch):
        """批次⑦默认关闭时 save 返回 None（不写 Excel 只写 CSV）。"""
        from config.settings import EXCEL_REPORT
        monkeypatch.setitem(EXCEL_REPORT, "customer_enabled", False)
        exporter = GoldExporter()
        path = exporter.save(sample_gold, output_dir=temp_output)
        assert path is None


# ============================================================
# Test: 保留计数
# ============================================================

class TestRetention:
    """旧报告清理测试。"""

    def test_cleanup_leaves_recent(self, temp_output, monkeypatch):
        """清理后保留最新 report_retention_count 个。"""
        from reports.gold_exporter import OUTPUT_REPORT
        monkeypatch.setattr("reports.gold_exporter.OUTPUT_REPORT", temp_output)

        # 创建 5 个旧 .xlsx 文件
        os.makedirs(temp_output, exist_ok=True)
        for i in range(5):
            fpath = os.path.join(temp_output, f"old_{i}.xlsx")
            with open(fpath, "w") as f:
                f.write("dummy")

        exporter = GoldExporter(retention_count=3)
        exporter._cleanup_old_reports()

        remaining = [f for f in os.listdir(temp_output) if f.endswith(".xlsx")]
        assert len(remaining) <= 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
