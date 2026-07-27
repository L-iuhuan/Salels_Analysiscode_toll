"""
Excel 报告生成 + 统一 Gold 输出层。

P1-C: save_gold_tables() 是唯一写入入口，gold.py 不再直接写 CSV。
P2-D: 实现委托给 reports.gold_exporter.GoldExporter，保持 backward compat。

用法（向后兼容）:
    from customer_analysis.report import save_gold_tables
    report_path = save_gold_tables(gold_dict)
"""

import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from reports.gold_exporter import GoldExporter, GOLD_CSV_MAP, OUTPUT_GOLD, OUTPUT_REPORT

# 向后兼容：保留旧函数签名
def save_gold_tables(gold: dict, output_dir: str = None) -> str:
    """统一写 Gold 字典到 CSV 文件 + 生成格式化 Excel 报告。

    P2-D: 委托给 GoldExporter。

    参数:
        gold: generate_gold_tables() 返回的 {表名: DataFrame} 字典
        output_dir: CSV 输出目录（默认 output/gold/）

    返回:
        str: Excel 报告文件路径
    """
    exporter = GoldExporter()
    return exporter.save(gold, output_dir)
