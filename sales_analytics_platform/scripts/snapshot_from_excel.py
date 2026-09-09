#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
月度 Excel → data_warehouse 明文快照。

用法：
  python scripts\snapshot_from_excel.py                    # 默认转 data/ 里最新的 .xlsx
  python scripts\snapshot_from_excel.py --data data\财务分析-8月.xlsx
  python scripts\snapshot_from_excel.py --warehouse D:\\data_warehouse

行为：
  - 读取 Excel（加密文件自动走 COM 兼容通道）
  - 按 data_warehouse/<YYYYMM>/erp_snapshot.parquet 落明文快照
  - 同步写 manifest.json（源文件身份、读取审计、列合计）
  - 不覆盖不同源文件的同名周期快照（与 write_erp_snapshot 一致）
"""

import argparse
import os
import sys
import time

# 本脚本在包根 scripts/ 下，需要引用 processing/shared 模块
_PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PROC = os.path.join(_PKG, "processing")
if _PROC not in sys.path:
    sys.path.insert(0, _PROC)

from shared.data_cleaning import read_excel_auto, _WAREHOUSE_ROOT  # noqa: E402
from shared.excel_com import write_erp_snapshot  # noqa: E402
from config.settings import DATA_SHEET_NAME  # noqa: E402


def _latest_excel(data_dir: str) -> str:
    if not os.path.isdir(data_dir):
        raise FileNotFoundError(f"数据源目录不存在: {data_dir}")
    files = [f for f in os.listdir(data_dir)
             if f.endswith(".xlsx") and not f.startswith("~$")]
    if not files:
        raise FileNotFoundError(f"{data_dir} 下未找到 .xlsx 文件")
    latest = max(files, key=lambda n: os.path.getmtime(os.path.join(data_dir, n)))
    return os.path.join(data_dir, latest)


def main():
    parser = argparse.ArgumentParser(description="月度 Excel 转 data_warehouse 明文快照")
    parser.add_argument("--data", default=None,
                        help="源 Excel 路径（默认取 data/ 目录最新 .xlsx）")
    parser.add_argument("--warehouse", default=_WAREHOUSE_ROOT,
                        help="快照仓根目录（默认 data_warehouse/）")
    args = parser.parse_args()

    source = args.data if args.data else _latest_excel(os.path.join(_PKG, "data"))
    if not os.path.isfile(source):
        print(f"[错误] 源文件不存在: {source}")
        sys.exit(1)

    print(f"[快照] 读取源文件: {source}")
    t0 = time.perf_counter()
    df = read_excel_auto(source, sheet_name=DATA_SHEET_NAME)
    read_seconds = time.perf_counter() - t0
    print(f"[快照] 读取完成: {len(df)} 行 × {len(df.columns)} 列，耗时 {read_seconds:.1f}s")

    pq_path = write_erp_snapshot(df, source, args.warehouse, DATA_SHEET_NAME,
                                 read_seconds=read_seconds)
    if pq_path:
        print(f"[快照] 已生成: {pq_path}")
    else:
        print("[快照] 目标周期已存在其他源文件快照，本次未覆盖")


if __name__ == "__main__":
    main()
