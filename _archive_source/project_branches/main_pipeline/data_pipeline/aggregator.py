"""
数据聚合器 — DefaultAggregator。

封装 shared/data_cleaning.py 的 monthly_aggregate_double_pass。
"""

import pandas as pd
from typing import Dict

from shared.data_cleaning import monthly_aggregate_double_pass


class DefaultAggregator:
    """默认月度聚合器。"""

    def aggregate(self, df: pd.DataFrame) -> Dict[str, pd.DataFrame]:
        """执行双通道月度聚合，返回 {customer_monthly, product_monthly, customer_x_product}。"""
        return monthly_aggregate_double_pass(df)
