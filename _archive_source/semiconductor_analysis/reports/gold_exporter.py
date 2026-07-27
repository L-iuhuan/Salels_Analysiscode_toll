"""
Gold 层表写入器 — CSV + 格式化 Excel 报告。

P2-D: 从 customer_analysis/report.py 提取，与客户分析解耦。

依赖:
    - pandas, numpy, xlsxwriter
    - config.settings.REPORT_RETENTION_COUNT

用法:
    exporter = GoldExporter()
    excel_path = exporter.save(gold_dict, output_dir="output/gold")
"""

import os
import sys
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Optional, Dict

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from config.settings import REPORT_RETENTION_COUNT


# Gold 表 → CSV 文件名映射（按 generate_gold_tables() 内部键名）
GOLD_CSV_MAP = {
    "异常日志": "异常日志.csv",
    "交叉销售建议": "交叉销售建议.csv",
    "客户产品桥接": "客户产品桥接.csv",
    "客户组合健康度": "客户组合健康度.csv",
    "客户全景": "客户全景.csv",
    "集团聚合": "集团聚合.csv",
    "价格离散度": "价格离散度.csv",
    "SKU生命周期": "SKU生命周期.csv",
    "品类接受度": "品类接受度.csv",
    "提价机会": "提价机会.csv",
    "降价策略试算": "降价策略试算.csv",
    "跨客户价格差异": "跨客户价格差异.csv",
    "渠道价格对比": "渠道价格对比.csv",
    "业务员定价偏离": "业务员定价偏离.csv",
    "市场细分价格": "市场细分价格.csv",
    "客户月度趋势": "客户月度趋势.csv",
    "品类迁移": "品类迁移.csv",
    "客户预测": "客户预测.csv",
    "产品关联分析": "产品关联分析.csv",
}

OUTPUT_GOLD = os.path.join(PROJECT_ROOT, "output", "gold")
OUTPUT_REPORT = os.path.join(PROJECT_ROOT, "output", "report")


class GoldExporter:
    """Gold 层表写入器。

    将 Gold 字典写入 CSV 文件 + 格式化 Excel 报告（蓝色表头、预警行红色标记）。
    """

    def __init__(self, csv_map: Optional[Dict[str, str]] = None,
                 retention_count: int = None):
        self.csv_map = csv_map or GOLD_CSV_MAP
        self.retention_count = retention_count or REPORT_RETENTION_COUNT

    def save(self, gold: dict, output_dir: str = None) -> str:
        """统一写 Gold 字典到 CSV 文件 + 生成格式化 Excel 报告。

        参数:
            gold: {表名: DataFrame} 字典
            output_dir: CSV 输出目录（默认 output/gold/）

        返回:
            str: Excel 报告文件路径
        """
        out_dir = output_dir or OUTPUT_GOLD
        os.makedirs(out_dir, exist_ok=True)

        # 写 CSV
        for table_name, csv_name in self.csv_map.items():
            df = gold.get(table_name)
            if df is not None and len(df) > 0:
                path = os.path.join(out_dir, csv_name)
                df.to_csv(path, index=False, encoding="utf-8-sig")

        # 写 Excel
        return self._write_excel_report(gold)

    def _write_excel_report(self, gold: dict) -> str:
        """将 Gold 层表写入格式化 Excel 报告。

        参数:
            gold: Gold 字典

        返回:
            str: Excel 文件路径
        """
        import xlsxwriter

        os.makedirs(OUTPUT_REPORT, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = os.path.join(OUTPUT_REPORT, f"客户分析报告_v1.1_{timestamp}.xlsx")

        workbook = xlsxwriter.Workbook(report_path, {'strings_to_numbers': False})

        # 样式定义
        header_fmt = workbook.add_format({
            'bold': True, 'font_color': 'white', 'bg_color': '#1E3A8A',
            'align': 'center', 'valign': 'vcenter', 'text_wrap': True,
            'font_name': 'Microsoft YaHei', 'font_size': 10,
            'border': 1,
        })
        num_fmt = workbook.add_format({'num_format': '#,##0.00', 'border': 1})
        text_fmt = workbook.add_format({'border': 1})
        warn_fmt = workbook.add_format({
            'bg_color': '#FEE2E2', 'num_format': '#,##0.00', 'border': 1,
        })
        good_fmt = workbook.add_format({
            'bg_color': '#DCFCE7', 'num_format': '#,##0.00', 'border': 1,
        })
        warn_header_fmt = workbook.add_format({
            'bold': True, 'font_color': 'white', 'bg_color': '#DC2626',
            'align': 'center', 'valign': 'vcenter', 'text_wrap': True,
            'font_name': 'Microsoft YaHei', 'font_size': 10,
            'border': 1,
        })

        # 预警行索引
        warn_indices = self._calc_warning_indices(gold)

        for sheet_name, df in gold.items():
            clean_name = sheet_name[:31]
            if clean_name in ("异常日志", "交叉销售建议"):
                continue
            worksheet = workbook.add_worksheet(clean_name)
            worksheet.freeze_panes(1, 0)

            col_widths = []
            for col_idx, col_name in enumerate(df.columns):
                worksheet.write(0, col_idx, col_name, header_fmt)
                max_len = len(str(col_name))

                for row_idx, val in enumerate(df[col_name]):
                    r = row_idx + 1
                    if isinstance(val, (list, np.ndarray, pd.Series)):
                        worksheet.write_string(r, col_idx, str(val), text_fmt)
                    elif pd.isna(val):
                        worksheet.write_blank(r, col_idx, None, text_fmt)
                    elif isinstance(val, (int, float, complex)):
                        rounded = round(float(val), 2)
                        cell_fmt = num_fmt
                        if sheet_name == "客户全景" and r - 1 in warn_indices:
                            cell_fmt = warn_fmt
                        worksheet.write_number(r, col_idx, rounded, cell_fmt)
                        col_len = len(f"{rounded:,.2f}")
                    else:
                        worksheet.write_string(r, col_idx, str(val), text_fmt)
                        col_len = len(str(val))
                    max_len = max(max_len, col_len)

                col_widths.append(min(max_len + 4, 30))

            for col_idx, w in enumerate(col_widths):
                worksheet.set_column(col_idx, col_idx, w)

        # 预警清单
        self._write_warning_sheet(workbook, gold, warn_indices, warn_header_fmt, warn_fmt)
        # 异常日志 Sheet
        self._write_anomaly_sheet(workbook, gold, warn_header_fmt, warn_fmt)
        # 交叉销售建议 Sheet
        self._write_cross_sell_sheet(workbook, gold)

        workbook.close()
        print(f"  Excel写入: {report_path}")

        self._cleanup_old_reports()

        return report_path

    # ---- 内部辅助 ----

    def _calc_warning_indices(self, gold: dict) -> set:
        """从客户全景表计算需要标记的预警行索引。"""
        warn_indices = set()
        if "客户全景" not in gold:
            return warn_indices
        profile = gold["客户全景"]
        warn_mask = pd.Series(False, index=profile.index)
        if "风险评级" in profile.columns:
            warn_mask |= profile["风险评级"].isin(["极高", "高"])
        if "采购中断预警" in profile.columns:
            warn_mask |= profile["采购中断预警"].astype(str).str.lower().isin(["是", "true", "1"])
        if "强依赖标记" in profile.columns:
            warn_mask |= profile["强依赖标记"].astype(str).str.lower().isin(["是", "true", "1"])
        if "客户生命周期" in profile.columns:
            warn_mask |= profile["客户生命周期"].isin(["衰退期", "休眠期", "流失期"])
        warn_indices = set(profile.index[warn_mask].to_list())
        return warn_indices

    def _write_warning_sheet(self, workbook, gold: dict, warn_indices: set,
                              warn_header_fmt, warn_fmt):
        """写入预警清单 Sheet。"""
        if not warn_indices or "客户全景" not in gold:
            return
        profile = gold["客户全景"]
        key_cols = [
            c for c in [
                "客户编号", "客户等级", "渠道类型", "风险等级", "机会等级",
                "客户生命周期", "采购中断预警", "强依赖标记", "行动建议",
            ] if c in profile.columns
        ]
        warning_df = (
            profile.loc[sorted(warn_indices), key_cols]
            if key_cols else profile.loc[sorted(warn_indices)]
        )
        warn_ws = workbook.add_worksheet("预警清单")
        warn_ws.freeze_panes(1, 0)
        for col_idx, col_name in enumerate(warning_df.columns):
            warn_ws.write(0, col_idx, col_name, warn_header_fmt)
            for row_idx, val in enumerate(warning_df[col_name]):
                r = row_idx + 1
                if pd.isna(val):
                    warn_ws.write_blank(r, col_idx, None, warn_fmt)
                elif isinstance(val, (int, float)):
                    warn_ws.write_number(r, col_idx, round(float(val), 2), warn_fmt)
                else:
                    warn_ws.write_string(r, col_idx, str(val), warn_fmt)

    def _write_anomaly_sheet(self, workbook, gold: dict, warn_header_fmt, warn_fmt):
        """写入异常日志 Sheet（按严重等级排序）。"""
        if "异常日志" not in gold or len(gold["异常日志"]) == 0:
            return
        anomaly_df = gold["异常日志"]
        anom_ws = workbook.add_worksheet("异常日志")
        anom_ws.freeze_panes(1, 0)
        severity_order = {"高": 0, "中": 1, "低": 2}
        if "异常等级" in anomaly_df.columns:
            anomaly_df = anomaly_df.copy()
            anomaly_df["_sort"] = anomaly_df["异常等级"].map(severity_order).fillna(3)
            anomaly_df = anomaly_df.sort_values("_sort", kind='stable').drop(columns=["_sort"])
        for col_idx, col_name in enumerate(anomaly_df.columns):
            anom_ws.write(0, col_idx, col_name, warn_header_fmt)
            for row_idx, val in enumerate(anomaly_df[col_name]):
                r = row_idx + 1
                if pd.isna(val):
                    anom_ws.write_blank(r, col_idx, None, warn_fmt)
                elif isinstance(val, (int, float)):
                    anom_ws.write_number(r, col_idx, round(float(val), 2), warn_fmt)
                else:
                    anom_ws.write_string(r, col_idx, str(val), warn_fmt)

    def _write_cross_sell_sheet(self, workbook, gold: dict):
        """写入交叉销售建议 Sheet。"""
        if "交叉销售建议" not in gold or len(gold["交叉销售建议"]) == 0:
            return
        cs_df = gold["交叉销售建议"]
        cs_ws = workbook.add_worksheet("交叉销售建议")
        cs_ws.freeze_panes(1, 0)
        cs_header_fmt = workbook.add_format({
            'bold': True, 'font_color': 'white', 'bg_color': '#059669',
            'align': 'center', 'valign': 'vcenter', 'text_wrap': True,
            'font_name': 'Microsoft YaHei', 'font_size': 10,
            'border': 1,
        })
        cs_cell_fmt = workbook.add_format({'border': 1, 'text_wrap': True})
        for col_idx, col_name in enumerate(cs_df.columns):
            cs_ws.write(0, col_idx, col_name, cs_header_fmt)
            for row_idx, val in enumerate(cs_df[col_name]):
                r = row_idx + 1
                if pd.isna(val):
                    cs_ws.write_blank(r, col_idx, None, cs_cell_fmt)
                elif isinstance(val, (int, float)):
                    cs_ws.write_number(r, col_idx, round(float(val), 2), cs_cell_fmt)
                else:
                    cs_ws.write_string(r, col_idx, str(val), cs_cell_fmt)

    def _cleanup_old_reports(self):
        """清理旧报告：只保留最近 N 个。"""
        if not os.path.isdir(OUTPUT_REPORT):
            return
        report_files = sorted(
            [os.path.join(OUTPUT_REPORT, f) for f in os.listdir(OUTPUT_REPORT)
             if f.endswith(".xlsx")],
            key=os.path.getctime,
        )
        for old in report_files[:-self.retention_count]:
            try:
                os.remove(old)
                print(f"  清理旧报告: {os.path.basename(old)}")
            except OSError:
                pass
