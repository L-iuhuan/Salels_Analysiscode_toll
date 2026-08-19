"""
数据清洗器 — DefaultCleaner。

封装 shared/data_cleaning.py 的清洗函数。
"""

import pandas as pd
from typing import List

from shared.data_cleaning import (
    rename_erp_columns, filter_negative_qty, winsorize_margins,
)


class DefaultCleaner:
    """默认数据清洗器。"""

    def __init__(self, config=None):
        self._config = config

    def clean(self, df: pd.DataFrame) -> pd.DataFrame:
        """执行标准清洗流程：列重命名 → 负销量过滤 → Winsorization。"""
        df = rename_erp_columns(df)
        # 从 config 或默认值获取数量列名
        qty_col = "数量"
        if self._config and hasattr(self._config, "clean"):
            erp_map = getattr(self._config.clean, "erp_col_map", {})
            qty_col = erp_map.get("quantity", "数量")
        df = filter_negative_qty(df, qty_col=qty_col)
        df = winsorize_margins(df)
        return df

    def validate(self, df: pd.DataFrame) -> list:
        """检查必要列是否存在。"""
        required = ["客户编号", "产品品种", "数量", "金额", "发货日期"]
        return [c for c in required if c not in df.columns]
