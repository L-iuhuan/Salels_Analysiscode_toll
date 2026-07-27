"""
Excel/CSV 数据加载器 — ExcelDataLoader。

封装 shared/data_cleaning.py 的 read_excel_auto 和 run_all.py 的 find_source_data。
"""

import os
import pandas as pd
from typing import Optional

from shared.data_cleaning import read_excel_auto


class ExcelDataLoader:
    """Excel/CSV 数据加载器。"""

    def load(self, path: str, **kwargs) -> pd.DataFrame:
        """加载数据文件。"""
        sheet_name = kwargs.get("sheet_name", 0)
        return read_excel_auto(path, sheet_name=sheet_name)

    def find_source(self, data_dir: str) -> str:
        """在目录中查找第一个 .xlsx 文件。"""
        if not os.path.isdir(data_dir):
            return ""
        xlsx_files = [f for f in os.listdir(data_dir) if f.endswith(".xlsx")]
        if not xlsx_files:
            return ""
        return os.path.join(data_dir, xlsx_files[0])

    def load_cust_info(self, path: str) -> Optional[pd.DataFrame]:
        """加载客户信息表（可选 sheet）。"""
        try:
            return read_excel_auto(path, sheet_name="客户信息表")
        except (ValueError, FileNotFoundError, KeyError):
            return None
