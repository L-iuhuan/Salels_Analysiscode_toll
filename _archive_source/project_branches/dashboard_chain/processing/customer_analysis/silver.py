"""
客户分析 Silver 层构建。

从原始Excel读取数据，经共享清洗和月度聚合，
输出3张 Silver 聚合表。实现已委托给 shared.data_cleaning 统一函数。
"""

import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from shared.data_cleaning import build_silver_layer as _build_silver_layer
from config.settings import CUSTOMER_ANALYSIS_WINDOW

OUTPUT_SILVER = os.path.join(PROJECT_ROOT, "output", "silver")


def build_silver_layer(source_path: str, col_map: dict = None) -> dict:
    """从源数据构建 Silver 层（代理到 shared 统一实现）。

    参数:
        source_path: 源Excel文件路径
        col_map: 列名映射字典（可选）

    返回:
        dict: {"customer_monthly": DataFrame, "product_monthly": DataFrame,
               "customer_x_product": DataFrame}
    """
    print("[客户·共享管道] 构建Silver层")

    return _build_silver_layer(
        source_path,
        col_map=col_map,
        date_filter_start=CUSTOMER_ANALYSIS_WINDOW.get("start_date"),
        cat_col_propagation=True,       # 客户管道需要产品一级分类在桥接表
        save_cleaned_rows=False,        # 客户管道不复用行级数据
    )
