#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generate_v4.py — 产品生命周期全景看板 v4 HTML 生成器

功能：读取 run_v2.8.py 输出的 Excel 文件，生成与 product_dashboard_v4-演示.html
      完全一致的仪表盘 HTML（格式、颜色、布局、图表均相同）。

用法：
    python generate_v4.py <excel_path> [-o <output_path>]
    python generate_v4.py                          # 自动使用最新的 output_v2.8_*.xlsx
"""

import json
import math
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

# ============================================================
# 常量配置
# ============================================================
SCRIPT_DIR = Path(__file__).parent
TEMPLATE_FILE = SCRIPT_DIR / "dashboard" / "c_template.html"

# DATA.table 的 27 个字段（与 v4 前端 JS 完全一致）
TABLE_FIELDS = [
    "产品名称", "所属参照组", "帕累托分类", "当前画像", "管理层摘要",
    "销量动能", "盈利健康",
    "近12月销量", "前12月销量",
    "近12月增长率%", "前12月增长率%", "营收增长率%",
    "当月毛利率%", "近12月毛利率%", "前12月毛利率%", "毛利率同比变化(pp)",
    "毛利率趋势斜率%/月",
    "综合评分", "综合风险等级", "风险主导因子",
    "通用策略建议",
    "ASP趋势%/月", "ASP趋势方向", "营收-毛利综合判断",
    "客户集中度-前1大%", "客户集中度-前3大%", "订货波动性CV",
    "特情说明",
]

# 桑基图的 11 种画像类型（必须与前端 COLOR_MAP 保持一致）
PORTRAIT_TYPES = [
    "主动收缩", "健康扩张", "利润优化", "夕阳产品", "成长期",
    "新品观察", "清仓/偶发", "现金牛", "衰退期", "隐性衰退", "预警增长",
]

DECLINING_PORTRAITS = {"衰退期", "夕阳产品", "隐性衰退"}
GROWING_PORTRAITS = {"成长期", "健康扩张", "预警增长"}
HIGH_RISK_LABEL = "高风险"


# ============================================================
# 工具函数
# ============================================================
def safe_val(v):
    """将值转换为 JSON 安全的 Python 原生类型。"""
    if v is None:
        return None
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    if isinstance(v, np.integer):
        return int(v)
    if isinstance(v, np.floating):
        return float(v)
    if isinstance(v, np.bool_):
        return bool(v)
    if isinstance(v, np.ndarray):
        return v.tolist()
    return v


def mode_with_tiebreak(arr):
    """众数。平局时返回在数组中最先出现的值。"""
    counts = Counter(arr)
    max_count = max(counts.values()) if counts else 0
    for v in arr:
        if counts.get(v, 0) == max_count:
            return v
    return None


def find_sheet(xls, fragment):
    """根据名称片段查找工作表。"""
    for name in xls.sheet_names:
        if fragment in name:
            return name
    return None


def clean_col_names(df):
    """清理列名（去除首尾空格）。"""
    df.columns = [str(c).strip() if pd.notna(c) else c for c in df.columns]
    return df


# ============================================================
# 各 DATA 组件构建函数
# ============================================================
def build_table(df):
    """构建 DATA.table：产品明细列表。"""
    records = []
    for _, row in df.iterrows():
        rec = {}
        for field in TABLE_FIELDS:
            v = row.get(field)
            if pd.isna(v):
                rec[field] = None
            else:
                rec[field] = safe_val(v)
        # 默认值：空风险等级 → "暂无评分"
        if rec.get("综合风险等级") is None:
            rec["综合风险等级"] = "暂无评分"
        rec["数据不足"] = False
        records.append(rec)
    return records


def build_kpi(table, df_insufficient):
    """构建 DATA.kpi：汇总统计。"""
    total = len(table)

    high_risk = sum(1 for r in table if r.get("综合风险等级") == HIGH_RISK_LABEL)
    declining = sum(1 for r in table if r.get("当前画像") in DECLINING_PORTRAITS)
    growing = sum(1 for r in table if r.get("当前画像") in GROWING_PORTRAITS)

    # 销量加权平均毛利率
    gm_sum = 0.0
    sales_sum = 0.0
    for r in table:
        gm = r.get("近12月毛利率%")
        sales = r.get("近12月销量")
        if gm is not None and sales is not None:
            gm_sum += float(gm) * float(sales)
            sales_sum += float(sales)
    avg_gm = round(gm_sum / sales_sum, 1) if sales_sum else 0.0

    # 简单平均增长率
    growth_vals = []
    for r in table:
        g = r.get("近12月增长率%")
        if g is not None:
            growth_vals.append(float(g))
    avg_growth = round(sum(growth_vals) / len(growth_vals), 1) if growth_vals else 0.0

    # 数据不足产品数
    insufficient = len(df_insufficient) if df_insufficient is not None else 0

    return {
        "total_products": total,
        "high_risk": high_risk,
        "extreme_risk": 0,
        "avg_gm": avg_gm,
        "avg_growth": avg_growth,
        "declining": declining,
        "growing": growing,
        "data_insufficient": insufficient,
    }


def build_charts(table):
    """构建 DATA.charts：6 个预计算分布。"""
    def count_field(field):
        cnt = {}
        for r in table:
            v = r.get(field)
            if v:
                cnt[v] = cnt.get(v, 0) + 1
        return cnt

    return {
        "portrait": count_field("当前画像"),
        "risk": count_field("综合风险等级"),
        "pareto": count_field("帕累托分类"),
        "summary": count_field("管理层摘要"),
        "profit_health": count_field("盈利健康"),
        "momentum": count_field("销量动能"),
        "营收-毛利综合判断": count_field("营收-毛利综合判断"),
        "风险主导因子": count_field("风险主导因子"),
        "ASP趋势方向": count_field("ASP趋势方向"),
    }


def build_filters(table):
    """构建 DATA.filters：筛选下拉框的唯一值。"""
    unique = {}
    for key, field in [
        ("portrait", "当前画像"), ("risk", "综合风险等级"),
        ("pareto", "帕累托分类"), ("group", "所属参照组"),
        ("momentum", "销量动能"), ("profit", "盈利健康"),
        ("summary", "管理层摘要"),
    ]:
        vals = sorted(set(r.get(field) for r in table if r.get(field)))
        unique[key] = vals
    return unique


def build_scatter(df):
    """构建 DATA.scatter：气泡图数据。"""
    scatter = []
    for _, row in df.iterrows():
        x = safe_val(row.get("近12月毛利率%"))
        y = safe_val(row.get("近12月增长率%"))
        if x is None or y is None:
            continue
        scatter.append({
            "name": safe_val(row.get("产品名称")),
            "group": safe_val(row.get("所属参照组")),
            "x": float(x),
            "y": float(y),
            "z": float(safe_val(row.get("近12月销量")) or 0),
            "risk": safe_val(row.get("综合风险等级")),
            "portrait": safe_val(row.get("当前画像")),
            "gm_trend": safe_val(row.get("毛利率趋势斜率%/月")),
        })
    return scatter


def build_history(df):
    """构建 DATA.history：每个产品 12 个月的时间序列。

    历史快照列命名模式（由 run_v2.8.py 生成）：
       当前画像_t-1, ... 当前画像_t-12
       近12月毛利率%_t-1, ... 近12月毛利率%_t-12
       近12月销量_t-1, ... 近12月销量_t-12
    数组按 t-1 → t-12 顺序（最新优先）。
    """
    # 查找快照列
    hist_cols = {"portrait": [], "gm": [], "sales": []}

    for col in df.columns:
        col_str = str(col).strip()
        m = re.match(r"当前画像_t-(\d+)", col_str)
        if m:
            hist_cols["portrait"].append((int(m.group(1)), col_str))
            continue
        m = re.match(r"近12月毛利率%_t-(\d+)", col_str)
        if m:
            hist_cols["gm"].append((int(m.group(1)), col_str))
            continue
        m = re.match(r"近12月销量_t-(\d+)", col_str)
        if m:
            hist_cols["sales"].append((int(m.group(1)), col_str))
            continue

    # 按 t-N 排序（N 升序 = t-1 在 t-2 之前）
    for key in hist_cols:
        hist_cols[key].sort(key=lambda x: x[0])

    # 截取前 12 个时间点
    portrait_cols = [c for _, c in hist_cols["portrait"][:12]]
    gm_cols = [c for _, c in hist_cols["gm"][:12]]
    sales_cols = [c for _, c in hist_cols["sales"][:12]]

    history = {}
    for _, row in df.iterrows():
        name = str(row.get("产品名称", ""))
        if not name:
            continue

        portraits = []
        for pc in portrait_cols:
            v = row.get(pc)
            portraits.append(str(v) if pd.notna(v) and v else "")

        sales = []
        for sc in sales_cols:
            v = row.get(sc)
            try:
                sales.append(float(v) if pd.notna(v) else 0.0)
            except (ValueError, TypeError):
                sales.append(0.0)

        gm = []
        for gc in gm_cols:
            v = row.get(gc)
            try:
                gm.append(float(v) if pd.notna(v) else 0.0)
            except (ValueError, TypeError):
                gm.append(0.0)

        # 补齐到 12 个
        while len(portraits) < 12:
            portraits.append("")
        while len(sales) < 12:
            sales.append(0.0)
        while len(gm) < 12:
            gm.append(0.0)

        history[name] = {
            "portraits": portraits[:12],
            "sales": sales[:12],
            "gm": gm[:12],
        }

    return history


def build_sankey(table, history):
    """构建 DATA.sankey：画像季度迁移桑基图。

    将 12 个月的历史画像分为 4 个季度：
      - Q1（最旧）：indices 8-11（t-9 ~ t-12）
      - Q2：indices 4-7（t-5 ~ t-8）
      - Q3（最新历史）：indices 0-3（t-1 ~ t-4）
      - Q4：当前画像（来自表格）
    """
    quarter_modes = {}

    for r in table:
        name = r.get("产品名称")
        if not name:
            continue
        curr = r.get("当前画像")
        hist = history.get(name)
        if not hist or not hist.get("portraits"):
            continue

        pts = hist["portraits"]  # [t-1, t-2, ..., t-12]

        # 过滤空值。为保持和 demo 一致的平局裁决，每季度内按从旧到新排序。
        q1 = list(reversed([p for p in pts[8:12] if p]))
        q2 = list(reversed([p for p in pts[4:8] if p]))
        q3 = list(reversed([p for p in pts[0:4] if p]))

        qm = {}
        qm["Q1"] = mode_with_tiebreak(q1) if q1 else None
        qm["Q2"] = mode_with_tiebreak(q2) if q2 else None
        qm["Q3"] = mode_with_tiebreak(q3) if q3 else None
        qm["Q4"] = curr

        quarter_modes[name] = qm

    # 统计迁移
    transitions = {
        ("Q1", "Q2"): defaultdict(list),
        ("Q2", "Q3"): defaultdict(list),
        ("Q3", "Q4"): defaultdict(list),
    }

    for name, qm in quarter_modes.items():
        for (src_k, tgt_k), storage in transitions.items():
            src = qm.get(src_k)
            tgt = qm.get(tgt_k)
            if src and tgt:
                storage[(src, tgt)].append(name)

    # 构建节点
    nodes = []
    for q in ["Q1", "Q2", "Q3", "Q4"]:
        for p in PORTRAIT_TYPES:
            nodes.append({"name": f"{q}_{p}"})

    # 构建连线
    links = []
    for (src_q, tgt_q), storage in transitions.items():
        for (src_p, tgt_p), products in storage.items():
            links.append({
                "source": f"{src_q}_{src_p}",
                "target": f"{tgt_q}_{tgt_p}",
                "value": len(products),
                "products": products,
            })

    return {"nodes": nodes, "links": links}


def build_forecasts(df_forecast):
    """构建 DATA.forecasts：每个产品未来 3 月预测。"""
    forecasts = {}
    if df_forecast is None:
        return forecasts

    for _, row in df_forecast.iterrows():
        name = str(row.get("产品名称", ""))
        if not name:
            continue

        def get_float(col):
            v = row.get(col)
            if pd.notna(v):
                try:
                    return float(v)
                except (ValueError, TypeError):
                    return None
            return None

        def get_str(col):
            v = row.get(col)
            return str(v) if pd.notna(v) and v else None

        forecasts[name] = {
            "f1": get_float("预测第1月销量"),
            "f2": get_float("预测第2月销量"),
            "f3": get_float("预测第3月销量"),
            "trend": get_str("销量趋势预测"),
        }

    return forecasts


def build_rfm(df_rfm):
    """构建 DATA.rfm：客户类型分布。"""
    rfm = {}
    if df_rfm is None or "客户类型" not in df_rfm.columns:
        return rfm

    type_counts = df_rfm["客户类型"].value_counts()
    for k, v in type_counts.items():
        if pd.notna(k):
            rfm[str(k)] = int(v)
    return rfm


def build_graph(df_assoc):
    """构建 DATA.graph：产品关联网络（支持度 Top 50）。"""
    if df_assoc is None or df_assoc.empty:
        return {"nodes": [], "links": []}

    # 按支持度降序排列
    support_col = "支持度"
    if support_col in df_assoc.columns:
        df_sorted = df_assoc.sort_values(by=support_col, ascending=False)
    else:
        df_sorted = df_assoc

    top_50 = df_sorted.head(50).copy()

    links = []
    for _, row in top_50.iterrows():
        source = str(row.get("产品A", ""))
        target = str(row.get("产品B", ""))
        if not source or not target:
            continue

        support = safe_val(row.get("支持度"))
        confidence = safe_val(row.get("置信度(A->B)") or row.get(df_assoc.columns[3]))

        links.append({
            "source": source,
            "target": target,
            "support": round(float(support), 4) if support is not None else 0,
            "confidence": round(float(confidence), 4) if confidence is not None else 0,
        })

    # 计算度数
    degree = Counter()
    for link in links:
        degree[link["source"]] += 1
        degree[link["target"]] += 1

    # 构建节点
    nodes = []
    for name, value in degree.most_common():
        if value >= 8:
            size = 24
        elif value >= 6:
            size = 18
        elif value >= 4:
            size = 12
        else:
            size = 8
        nodes.append({"name": name, "value": value, "symbolSize": size})

    return {"nodes": nodes, "links": links}


# _build_pl_html 已废弃，恢复使用原始模板 c_template.html + __DATA_JSON__ 注入


# ============================================================
# 主生成函数
# ============================================================
def generate(excel_path, output_path=None):
    """从 Excel 生成 v4 仪表盘 HTML。"""
    excel_path = Path(excel_path)
    stem = excel_path.stem

    print(f"正在读取 Excel: {excel_path}")

    # 读取各工作表
    xls = pd.ExcelFile(excel_path)
    sheet_main = (find_sheet(xls, "产品快照表") or find_sheet(xls, "产品快照")
                  or xls.sheet_names[0])
    print(f"  主工作表: {sheet_main}")

    df_main = pd.read_excel(excel_path, sheet_name=sheet_main)
    df_main = clean_col_names(df_main)
    print(f"  行数: {len(df_main)}")

    # 其他工作表（按名称片段匹配）
    sheet_insufficient = find_sheet(xls, "数据不足")
    df_insufficient = (
        pd.read_excel(excel_path, sheet_name=sheet_insufficient)
        if sheet_insufficient else None
    )

    sheet_assoc = find_sheet(xls, "产品关联分析")
    df_assoc = (
        pd.read_excel(excel_path, sheet_name=sheet_assoc)
        if sheet_assoc else None
    )

    sheet_rfm = find_sheet(xls, "RFM")
    df_rfm = (
        pd.read_excel(excel_path, sheet_name=sheet_rfm)
        if sheet_rfm else None
    )

    # 提取数据月份
    data_month = ""
    if "最新数据月份" in df_main.columns:
        dm = df_main["最新数据月份"].dropna()
        if not dm.empty:
            data_month = str(dm.iloc[0])

    # --------------------------------------------------------
    # 历史数据：支持两种格式
    #   Format A — 主表含 t-1~t-12 快照列（134 列）
    #   Format B — 分离的"历史画像追踪"工作表
    sheet_history = find_sheet(xls, "历史画像追踪")
    has_history_cols = any(
        re.match(r"当前画像_t-\d+", str(c))
        for c in df_main.columns
    )
    if has_history_cols:
        df_history = df_main
    elif sheet_history:
        df_history = pd.read_excel(excel_path, sheet_name=sheet_history)
        df_history = clean_col_names(df_history)
        print(f"  历史数据来源: {sheet_history} ({len(df_history)} 行)")
    else:
        df_history = df_main
        print("  警告：未找到历史画像数据")

    # --------------------------------------------------------
    # 构建 DATA 各组件
    print("\n正在构建 DATA 组件...")

    table = build_table(df_main)
    history = build_history(df_history)
    kpi = build_kpi(table, df_insufficient)
    charts = build_charts(table)
    filters = build_filters(table)
    scatter = build_scatter(df_main)
    sankey = build_sankey(table, history)
    rfm = build_rfm(df_rfm)
    graph = build_graph(df_assoc)

    data = {
        "kpi": kpi,
        "charts": charts,
        "scatter": scatter,
        "sankey": sankey,
        "table": table,
        "filters": filters,
        "history": history,
        "rfm": rfm,
        "graph": graph,
    }

    # 打印统计
    print(f"  table: {len(table)} records")
    print(f"  history: {len(history)} products")
    print(f"  scatter: {len(scatter)} points")
    print(f"  sankey: {len(sankey['nodes'])} nodes, {len(sankey['links'])} links")
    print(f"  rfm: {len(rfm)} categories")
    print(f"  graph: {len(graph['nodes'])} nodes, {len(graph['links'])} links")
    print(f"  kpi: {kpi}")
    if data_month:
        print(f"  数据月份: {data_month}")

    # --------------------------------------------------------
    # 序列化为 JSON（含data_month）
    print("\n正在序列化 JSON...")
    if data_month:
        data["data_month"] = data_month
    data_json = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    print(f"  JSON 大小: {len(data_json):,} 字符")

    # --------------------------------------------------------
    # 读取原始模板并注入数据
    template_path = TEMPLATE_FILE
    if not template_path.exists():
        print(f"错误：找不到模板文件 {template_path}")
        sys.exit(1)

    print(f"正在读取模板: {template_path}")
    with open(template_path, "r", encoding="utf-8") as f:
        template = f.read()

    html = template.replace("__DATA_JSON__", data_json)

    # 替换模板中硬编码的数据月份
    if data_month:
        html = html.replace("数据月份: 2026-04", f"数据月份: {data_month}")

    # --------------------------------------------------------
    # 写入输出（默认输出到dashboard/product_lifecycle.html）
    if output_path is None:
        output_path = SCRIPT_DIR / "dashboard" / "product_lifecycle.html"
    output_path = Path(output_path)
    os.makedirs(output_path.parent, exist_ok=True)

    print(f"\n正在写入 HTML: {output_path}")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"完成！输出文件: {output_path}")
    print(f"  HTML 大小: {len(html):,} 字符")
    return output_path


# ============================================================
# 命令行入口
# ============================================================
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="产品生命周期全景看板 v4 HTML 生成器"
    )
    parser.add_argument(
        "excel", nargs="?",
        help="run_v2.8.py 输出的 Excel 文件路径"
    )
    parser.add_argument(
        "-o", "--output",
        help="输出 HTML 路径（可选，默认为 Excel 同名 _v4.html）"
    )

    if len(sys.argv) > 1:
        args = parser.parse_args()
        generate(args.excel, args.output)
    else:
        # 自动查找最新的产品报告Excel
        excel_files = sorted(
            list(SCRIPT_DIR.glob("output/report/产品生命周期报告_v4.0_*.xlsx"))
            + list(SCRIPT_DIR.glob("output_v2.8_*.xlsx"))
        )
        if excel_files:
            latest = excel_files[-1]
            print(f"自动选择: {latest}")
            generate(str(latest))
        else:
            print("未找到 Excel 文件。用法: python generate_v4.py <excel_path>")
            sys.exit(1)
