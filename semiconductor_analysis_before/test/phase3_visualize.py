#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Phase 3：可视化图表生成（01-05）。

加载 Phase 1 中间件 → 生成 5 张诊断图表 → 保存至 charts/。

独立运行：
    python test/phase3_visualize.py                          # 全量生成
    python test/phase3_visualize.py --charts 1,3,5           # 仅指定图表
    python test/phase3_visualize.py --format png             # 格式(png/pdf/svg)
    python test/phase3_visualize.py --dpi 200                # 分辨率
"""

import sys, os, time, argparse
from datetime import datetime

_TEST_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_TEST_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import pandas as pd
import numpy as np

from test.conftest import (
    PROJECT_ROOT, DIAG_DIR, CHART_DIR, PKL_PATH,
    load_intermediates, has_intermediates,
    ensure_diag_dir, log, header,
)

# ============================================================
# 图表 01: ERP vs 自动计算新品对比（柱状图）
# ============================================================
def chart_01_new_product_comparison(data: dict, fmt: str = "png", dpi: int = 150) -> str:
    """ERP 标记 vs 自动计算的新品品种数对比。"""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.font_manager as fm

    _setup_chinese_font()

    prod_monthly = data.get("prod_monthly")
    has_new_flag = data.get("has_new_flag", False)

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    fig.suptitle("新品判定对比：ERP 标记 vs 自动计算", fontsize=14, fontweight="bold")

    if has_new_flag and prod_monthly is not None:
        latest_month = prod_monthly["_月"].max()
        ps = prod_monthly.groupby("产品品种")["_月"].min().reset_index()
        ps.columns = ["产品品种", "首次销售月"]
        ps["auto_new"] = (latest_month - ps["首次销售月"]).apply(lambda x: x.n) <= 12

        erp_set = set(prod_monthly[prod_monthly["新品标记"]=="是"]["产品品种"].unique())
        auto_set = set(ps[ps["auto_new"]]["产品品种"].unique())

        ax = axes[0]
        labels = ["ERP标记", "自动计算", "两者重叠"]
        values = [len(erp_set), len(auto_set), len(erp_set & auto_set)]
        colors = ["#E74C3C", "#3498DB", "#2ECC71"]
        bars = ax.bar(labels, values, color=colors, width=0.5, edgecolor="white")
        for bar, val in zip(bars, values):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1,
                    str(val), ha="center", va="bottom", fontsize=11, fontweight="bold")
        ax.set_ylabel("品种数")
        ax.set_title("新品品种数对比", fontsize=12)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

        ax = axes[1]
        erp_only = len(erp_set - auto_set)
        auto_only = len(auto_set - erp_set)
        overlap = len(erp_set & auto_set)
        wedges, texts, autotexts = ax.pie(
            [erp_only, auto_only, overlap],
            labels=["ERP独有", "自动独有", "重叠"],
            autopct="%1.1f%%",
            colors=["#E74C3C", "#3498DB", "#2ECC71"],
            startangle=90,
        )
        ax.set_title("新品集重叠分布", fontsize=12)
    else:
        axes[0].text(0.5, 0.5, "源数据无新品标记列", ha="center", va="center", transform=axes[0].transAxes)

    plt.tight_layout()
    path = os.path.join(CHART_DIR, f"01_new_product_comparison.{fmt}")
    fig.savefig(path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return path


# ============================================================
# 图表 02: 产品画像分布（水平条形图）
# ============================================================
def chart_02_product_portrait_dist(data: dict, fmt: str = "png", dpi: int = 150) -> str:
    """产品九宫格画像分布。"""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    _setup_chinese_font()

    profiling_result = data.get("profiling_result")

    fig, ax = plt.subplots(figsize=(10, 6))
    fig.suptitle("产品生命周期画像分布", fontsize=14, fontweight="bold")

    if profiling_result is not None and "当前画像" in profiling_result.columns:
        counts = profiling_result["当前画像"].value_counts()
        colors = plt.cm.Set2(np.linspace(0, 1, len(counts)))
        bars = ax.barh(counts.index, counts.values, color=colors, edgecolor="white")
        for bar, val in zip(bars, counts.values):
            pct = val / len(profiling_result) * 100
            ax.text(bar.get_width() + 1, bar.get_y() + bar.get_height()/2,
                    f"{val} ({pct:.1f}%)", ha="left", va="center", fontsize=9)
        ax.set_xlabel("产品数")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
    else:
        ax.text(0.5, 0.5, "无画像数据（请先运行 Phase 2 TEST-E）", ha="center", va="center", transform=ax.transAxes)

    plt.tight_layout()
    path = os.path.join(CHART_DIR, f"02_product_portrait_dist.{fmt}")
    fig.savefig(path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return path


# ============================================================
# 图表 03: 客户生命周期饼图
# ============================================================
def chart_03_customer_lifecycle_pie(data: dict, fmt: str = "png", dpi: int = 150) -> str:
    """客户生命周期阶段分布（环形图）。"""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    _setup_chinese_font()

    stages_result = data.get("customer_stages_result")

    fig, ax = plt.subplots(figsize=(8, 6))
    fig.suptitle("客户生命周期阶段分布", fontsize=14, fontweight="bold")

    if stages_result is not None and "客户生命周期" in stages_result.columns:
        counts = stages_result["客户生命周期"].value_counts()
        colors = plt.cm.Set3(np.linspace(0, 1, len(counts)))
        wedges, texts, autotexts = ax.pie(
            counts.values, labels=counts.index, autopct="%1.1f%%",
            colors=colors, startangle=90, pctdistance=0.75,
            wedgeprops=dict(width=0.4, edgecolor="white"),
        )
        ax.set_title(f"总计 {len(stages_result)} 客户", fontsize=10)
    else:
        ax.text(0.5, 0.5, "无生命周期数据（请先运行 Phase 2 TEST-F）", ha="center", va="center", transform=ax.transAxes)

    plt.tight_layout()
    path = os.path.join(CHART_DIR, f"03_customer_lifecycle_pie.{fmt}")
    fig.savefig(path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return path


# ============================================================
# 图表 04: 新品渗透分析（散点/柱状图）
# ============================================================
def chart_04_new_product_penetration(data: dict, fmt: str = "png", dpi: int = 150) -> str:
    """新品采购占比分布。"""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    _setup_chinese_font()

    cohort_result = data.get("cohort_result")

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    fig.suptitle("新品渗透分析", fontsize=14, fontweight="bold")

    if cohort_result is not None:
        # 左：是否采购新品饼图
        ax = axes[0]
        has = int((cohort_result["是否采购新品"] > 0).sum())
        no = len(cohort_result) - has
        ax.pie([has, no], labels=["采购新品", "未采购新品"],
               autopct="%1.1f%%", colors=["#2ECC71", "#E74C3C"],
               startangle=90, wedgeprops=dict(edgecolor="white"))
        ax.set_title("新品采购客户占比", fontsize=11)

        # 右：新品采购占比直方图
        ax = axes[1]
        ratios = cohort_result["新品采购占比"].dropna() * 100
        ax.hist(ratios, bins=20, color="#3498DB", edgecolor="white", alpha=0.7)
        ax.axvline(ratios.median(), color="#E74C3C", linestyle="--", label=f"中位数 {ratios.median():.1f}%")
        ax.set_xlabel("新品采购占比 (%)")
        ax.set_ylabel("客户数")
        ax.set_title("新品采购占比分布", fontsize=11)
        ax.legend()
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
    else:
        for ax in axes:
            ax.text(0.5, 0.5, "无 Cohort 数据（请先运行 Phase 2 TEST-D）", ha="center", va="center", transform=ax.transAxes)

    plt.tight_layout()
    path = os.path.join(CHART_DIR, f"04_new_product_penetration.{fmt}")
    fig.savefig(path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return path


# ============================================================
# 图表 05: 月度新品趋势（折线图）
# ============================================================
def chart_05_new_product_monthly_trend(data: dict, fmt: str = "png", dpi: int = 150) -> str:
    """月度新品采购趋势。"""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    _setup_chinese_font()

    df_clean = data.get("df_clean")
    has_new_flag = data.get("has_new_flag", False)

    fig, ax = plt.subplots(figsize=(12, 5))
    fig.suptitle("月度新品采购趋势", fontsize=14, fontweight="bold")

    if df_clean is not None and has_new_flag and "是否新品" in df_clean.columns:
        # 按月聚合新品比例
        date_col = data.get("date_col", "发货日期")
        if "_月" not in df_clean.columns:
            df_clean["_月"] = df_clean[date_col].dt.to_period("M")

        monthly = df_clean.groupby("_月").agg(
            总行数=("数量", "sum"),
            新品行数=("是否新品", lambda x: (x == "是").sum()),
        )
        monthly["新品占比"] = monthly["新品行数"] / monthly["总行数"] * 100

        idx = monthly.index.astype(str)
        ax.plot(idx, monthly["新品占比"], marker="o", color="#3498DB", linewidth=1.5, markersize=3)
        ax.fill_between(range(len(idx)), monthly["新品占比"], alpha=0.1, color="#3498DB")

        # 标注最近3月
        for i in range(max(0, len(idx)-3), len(idx)):
            ax.annotate(f"{monthly['新品占比'].iloc[i]:.1f}%",
                        (i, monthly["新品占比"].iloc[i]),
                        textcoords="offset points", xytext=(0, 10),
                        ha="center", fontsize=8, color="#E74C3C")

        ax.set_ylabel("新品行数占比 (%)")
        ax.set_xlabel("月份")
        ax.set_xticks(range(0, len(idx), max(1, len(idx)//12)))
        ax.set_xticklabels([idx[i] for i in range(0, len(idx), max(1, len(idx)//12))], rotation=45)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.grid(axis="y", alpha=0.3)
    else:
        ax.text(0.5, 0.5, "无新品标记数据", ha="center", va="center", transform=ax.transAxes)

    plt.tight_layout()
    path = os.path.join(CHART_DIR, f"05_new_product_monthly_trend.{fmt}")
    fig.savefig(path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return path


# ============================================================
# 中文字体设置
# ============================================================
def _setup_chinese_font():
    """尝试设置中文字体，避免 matplotlib 缺字。"""
    import matplotlib
    import matplotlib.font_manager as fm
    import warnings

    # 尝试常见中文字体路径
    font_candidates = [
        "C:\\Windows\\Fonts\\msyh.ttc",           # 微软雅黑
        "C:\\Windows\\Fonts\\simhei.ttf",          # 黑体
        "C:\\Windows\\Fonts\\simsun.ttc",          # 宋体
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttf",   # Linux
        "/System/Library/Fonts/PingFang.ttc",      # macOS
    ]

    font_set = False
    for fp in font_candidates:
        if os.path.exists(fp):
            try:
                prop = fm.FontProperties(fname=fp)
                font_name = prop.get_name()
                matplotlib.rcParams["font.family"] = font_name
                font_set = True
                break
            except Exception:
                continue

    if not font_set:
        try:
            matplotlib.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
        except Exception:
            pass
    matplotlib.rcParams["axes.unicode_minus"] = False


# ============================================================
# Phase 3 主函数
# ============================================================
CHART_REGISTRY = {
    "1": chart_01_new_product_comparison,
    "2": chart_02_product_portrait_dist,
    "3": chart_03_customer_lifecycle_pie,
    "4": chart_04_new_product_penetration,
    "5": chart_05_new_product_monthly_trend,
}

CHART_NAMES = {
    "1": "ERP vs 自动计算新品对比",
    "2": "产品画像分布",
    "3": "客户生命周期饼图",
    "4": "新品渗透分析",
    "5": "月度新品趋势",
}


def run_phase3(
    charts: str = "1,2,3,4,5",
    fmt: str = "png",
    dpi: int = 150,
    data: dict = None,
) -> list:
    """
    执行 Phase 3：生成图表。

    参数：
        charts: 逗号分隔的图表 ID
        fmt:  输出格式 (png/pdf/svg)
        dpi:  分辨率
        data: 中间件数据

    返回：图表文件路径列表
    """
    ensure_diag_dir()

    if data is None:
        data = load_intermediates()

    selected = [c.strip() for c in charts.split(",") if c.strip() in CHART_REGISTRY]

    header(f"Phase 3：可视化图表生成（{len(selected)} 张）")

    paths = []
    for chart_id in selected:
        func = CHART_REGISTRY[chart_id]
        name = CHART_NAMES.get(chart_id, chart_id)
        log(f"[图表 {chart_id}] {name}")
        try:
            path = func(data, fmt=fmt, dpi=dpi)
            paths.append(path)
            print(f"  [OK] {path}")
        except Exception as e:
            print(f"  [FAIL] {name}: {e}")
            import traceback
            traceback.print_exc()

    print(f"\n  完成: {len(paths)}/{len(selected)} 张图表")
    return paths


# ── 独立入口 ──
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Phase 3：可视化图表生成")
    parser.add_argument("--charts", type=str, default="1,2,3,4,5",
                        help="图表 ID，逗号分隔（默认全部）")
    parser.add_argument("--format", type=str, default="png",
                        choices=["png", "pdf", "svg"],
                        help="输出格式（默认 png）")
    parser.add_argument("--dpi", type=int, default=150,
                        help="图片分辨率（默认 150）")
    args = parser.parse_args()

    run_phase3(charts=args.charts, fmt=args.format, dpi=args.dpi)
