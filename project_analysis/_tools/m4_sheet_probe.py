# -*- coding: utf-8 -*-
"""M4 前置: 核对 xlsx 各候选主表的行数与日期范围, 定位"当前主表"""
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from python_calamine import CalamineWorkbook
import datetime

FILES = {
    "5月(①)": r"E:\3-其他资料\数据分析\semiconductor_analysis\data\财务分析-5月（6.3）.xlsx",
    "6月(平台)": r"E:\3-其他资料\数据分析\sales_analytics_platform\data\财务分析-6月（7.6）.xlsx",
}
SHEETS = ["总表", "24-26"]

for tag, path in FILES.items():
    print(f"\n===== {tag} =====")
    wb = CalamineWorkbook.from_path(path)
    names = wb.sheet_names
    for sn in SHEETS:
        if sn not in names:
            print(f"  [{sn}] 不存在")
            continue
        sh = wb.get_sheet_by_name(sn)
        rows = list(sh.to_python())
        if not rows:
            print(f"  [{sn}] 空表")
            continue
        headers = [str(h) if h else "" for h in rows[0]]
        dcol = next((i for i, h in enumerate(headers) if "日期" in h), None)
        n = len(rows) - 1
        info = f"  [{sn}] {n} 行, {len(headers)} 列"
        if dcol is not None:
            dmin = dmax = None
            for r in rows[1:]:
                v = r[dcol]
                if isinstance(v, (datetime.datetime, datetime.date)):
                    dmin = v if dmin is None or v < dmin else dmin
                    dmax = v if dmax is None or v > dmax else dmax
            info += f", 日期[{headers[dcol]}]: {dmin} ~ {dmax}"
        print(info)
