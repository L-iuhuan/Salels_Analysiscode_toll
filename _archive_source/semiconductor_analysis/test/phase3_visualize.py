#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Phase 3：可视化图表生成（01-15）。

v2.0 — 全部图表从 Gold 层 CSV 直接读取，不再依赖 Phase 1 中间 pickle。

独立运行：
    python test/phase3_visualize.py                        # 全量生成
    python test/phase3_visualize.py --charts 1,3,5,6      # 仅指定图表
    python test/phase3_visualize.py --format png           # 格式(png/pdf/svg)
    python test/phase3_visualize.py --dpi 200              # 分辨率
"""

import sys, os, argparse
from datetime import datetime

_TEST_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_TEST_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import pandas as pd
import numpy as np

from test.conftest import (
    PROJECT_ROOT, DIAG_DIR, CHART_DIR,
    ensure_diag_dir, log, header,
)

GOLD_DIR = os.path.join(PROJECT_ROOT, "output", "gold")

# ============================================================
# 中文字体设置
# ============================================================
def _setup_chinese_font():
    import matplotlib
    import matplotlib.font_manager as fm

    font_candidates = [
        "C:\\Windows\\Fonts\\msyh.ttc",
        "C:\\Windows\\Fonts\\simhei.ttf",
        "C:\\Windows\\Fonts\\simsun.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttf",
        "/System/Library/Fonts/PingFang.ttc",
    ]
    for fp in font_candidates:
        if os.path.exists(fp):
            try:
                prop = fm.FontProperties(fname=fp)
                matplotlib.rcParams["font.family"] = prop.get_name()
                break
            except (OSError, RuntimeError):
                continue
    else:
        try:
            matplotlib.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
        except (ValueError, KeyError):
            pass
    matplotlib.rcParams["axes.unicode_minus"] = False


def _read_gold(filename):
    """读取 Gold 层 CSV，不存在返回空 DataFrame。"""
    path = os.path.join(GOLD_DIR, filename)
    if os.path.exists(path):
        return pd.read_csv(path, encoding="utf-8-sig")
    print(f"  [警告] Gold 文件不存在: {filename}")
    return pd.DataFrame()


# ============================================================
# 图表 01: 产品画像分布（水平条形图）
# ============================================================
def chart_01_product_portrait_dist(fmt="png", dpi=150):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    _setup_chinese_font()

    df = _read_gold("gold_product_portrait.csv")
    fig, ax = plt.subplots(figsize=(11, 7))
    fig.suptitle("产品生命周期画像分布", fontsize=15, fontweight="bold")

    if not df.empty and "当前画像" in df.columns:
        order = ["导入期", "成长期", "成熟期", "预警增长", "隐性衰退", "衰退期", "淘汰/长尾", "产品观察", "金牛/明星", "待观察"]
        counts = df["当前画像"].value_counts()
        counts = counts.reindex([k for k in order if k in counts.index])
        colors = plt.cm.RdYlGn(np.linspace(0.15, 0.85, len(counts)))
        bars = ax.barh(counts.index, counts.values, color=colors, edgecolor="white", height=0.6)
        for bar, val in zip(bars, counts.values):
            pct = val / len(df) * 100
            ax.text(bar.get_width() + 1, bar.get_y() + bar.get_height() / 2,
                    f"{val} ({pct:.1f}%)", ha="left", va="center", fontsize=9)
        ax.set_xlabel("产品数")
        ax.set_title(f"总计 {len(df)} 个有效产品画像", fontsize=10, color="gray")
    else:
        ax.text(0.5, 0.5, "无产品画像数据", ha="center", va="center", transform=ax.transAxes)

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    plt.tight_layout()
    path = os.path.join(CHART_DIR, f"01_product_portrait_dist.{fmt}")
    fig.savefig(path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return path


# ============================================================
# 图表 02: 客户生命周期分布（环形图）
# ============================================================
def chart_02_customer_lifecycle_donut(fmt="png", dpi=150):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    _setup_chinese_font()

    df = _read_gold("客户全景.csv")
    fig, ax = plt.subplots(figsize=(8.5, 7))
    fig.suptitle("客户生命周期阶段分布", fontsize=15, fontweight="bold")

    if not df.empty and "客户生命周期" in df.columns:
        counts = df["客户生命周期"].value_counts()
        colors = plt.cm.Set3(np.linspace(0.05, 0.95, len(counts)))
        wedges, texts, autotexts = ax.pie(
            counts.values, labels=counts.index, autopct="%1.1f%%",
            colors=colors, startangle=90, pctdistance=0.78,
            wedgeprops=dict(width=0.38, edgecolor="white"),
        )
        for at in autotexts:
            at.set_fontsize(9)
        ax.set_title(f"总计 {len(df)} 个客户", fontsize=10, color="gray")
    else:
        ax.text(0.5, 0.5, "无客户生命周期数据", ha="center", va="center", transform=ax.transAxes)

    plt.tight_layout()
    path = os.path.join(CHART_DIR, f"02_customer_lifecycle_donut.{fmt}")
    fig.savefig(path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return path


# ============================================================
# 图表 03: 客户等级分布（分组柱状图）
# ============================================================
def chart_03_customer_tier_bar(fmt="png", dpi=150):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    _setup_chinese_font()

    df = _read_gold("客户全景.csv")
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    fig.suptitle("客户等级与渠道分布", fontsize=15, fontweight="bold")

    if not df.empty:
        # 左：客户等级
        ax = axes[0]
        if "客户等级" in df.columns:
            counts = df["客户等级"].value_counts()
            tier_order = ["VIP", "A级", "B级", "C级", "未知"]
            counts = counts.reindex([t for t in tier_order if t in counts.index])
            colors = ["#E74C3C", "#F39C12", "#3498DB", "#95A5A6", "#BDC3C7"][:len(counts)]
            bars = ax.bar(counts.index, counts.values, color=colors, edgecolor="white", width=0.55)
            for bar, val in zip(bars, counts.values):
                ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 2,
                        str(val), ha="center", fontsize=11, fontweight="bold")
            ax.set_title("客户等级分布", fontsize=12)
        else:
            ax.text(0.5, 0.5, "无客户等级数据", ha="center", va="center", transform=ax.transAxes)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

        # 右：渠道类型
        ax = axes[1]
        if "渠道类型" in df.columns:
            ch_counts = df["渠道类型"].value_counts()
            ch_colors = plt.cm.Paired(np.linspace(0.1, 0.9, len(ch_counts)))
            bars = ax.bar(ch_counts.index, ch_counts.values, color=ch_colors, edgecolor="white", width=0.55)
            for bar, val in zip(bars, ch_counts.values):
                ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 2,
                        str(val), ha="center", fontsize=11, fontweight="bold")
            ax.set_title("渠道类型分布", fontsize=12)
        else:
            ax.text(0.5, 0.5, "无渠道数据", ha="center", va="center", transform=ax.transAxes)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
    else:
        for ax in axes:
            ax.text(0.5, 0.5, "无客户全景数据", ha="center", va="center", transform=ax.transAxes)

    plt.tight_layout()
    path = os.path.join(CHART_DIR, f"03_customer_tier_bar.{fmt}")
    fig.savefig(path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return path


# ============================================================
# 图表 04: 月度营收+订单双轴趋势（折线图）
# ============================================================
def chart_04_kpi_monthly_trend(fmt="png", dpi=150):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    _setup_chinese_font()

    df = _read_gold("gold_kpi_daily.csv")
    fig, ax1 = plt.subplots(figsize=(14, 6))
    fig.suptitle("月度营收与订单趋势", fontsize=15, fontweight="bold")

    if not df.empty and "日期" in df.columns:
        df["日期"] = pd.to_datetime(df["日期"])
        df["月份"] = df["日期"].dt.to_period("M")
        monthly = df.groupby("月份").agg(
            销售额=("销售额", "sum"),
            订单量=("订单数", "sum"),
        ).reset_index()
        monthly["月份_str"] = monthly["月份"].astype(str)
        x = range(len(monthly))

        # 营收柱状图
        rev_m = monthly["销售额"] / 1e4
        bars = ax1.bar(x, rev_m, color="#3498DB", alpha=0.55, label="月销售额(万元)", width=0.65)
        ax1.set_ylabel("销售额 (万元)", color="#3498DB", fontsize=11)
        ax1.tick_params(axis="y", labelcolor="#3498DB")

        # 订单量折线
        ax2 = ax1.twinx()
        ax2.plot(x, monthly["订单量"], color="#E74C3C", marker="o", linewidth=1.8, markersize=3, label="月订单量")
        ax2.set_ylabel("订单量", color="#E74C3C", fontsize=11)
        ax2.tick_params(axis="y", labelcolor="#E74C3C")

        # X轴标签
        tick_step = max(1, len(monthly) // 14)
        ax1.set_xticks([i for i in x if i % tick_step == 0])
        ax1.set_xticklabels([monthly["月份_str"].iloc[i] for i in x if i % tick_step == 0], rotation=45, fontsize=8)

        # 标注最新值
        latest = monthly.iloc[-1]
        ax1.annotate(f"{rev_m.iloc[-1]:.0f}万",
                     (x[-1], rev_m.iloc[-1]),
                     textcoords="offset points", xytext=(0, 12),
                     ha="center", fontsize=9, color="#3498DB", fontweight="bold")
        ax2.annotate(f"{latest['订单量']:.0f}单",
                     (x[-1], latest["订单量"]),
                     textcoords="offset points", xytext=(0, -16),
                     ha="center", fontsize=9, color="#E74C3C", fontweight="bold")

        lines1, labels1 = ax1.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left", fontsize=9)

        ax1.set_title(f"数据范围: {monthly['月份_str'].iloc[0]} ~ {monthly['月份_str'].iloc[-1]}  ({len(monthly)}个月)",
                      fontsize=10, color="gray")
    else:
        ax1.text(0.5, 0.5, "无KPI数据", ha="center", va="center", transform=ax1.transAxes)

    ax1.spines["top"].set_visible(False)
    ax1.grid(axis="y", alpha=0.25)
    plt.tight_layout()
    path = os.path.join(CHART_DIR, f"04_kpi_monthly_trend.{fmt}")
    fig.savefig(path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return path


# ============================================================
# 图表 05: 产品九宫格分类分布（堆叠条形）
# ============================================================
def chart_05_product_9grid_stacked(fmt="png", dpi=150):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    _setup_chinese_font()

    df = _read_gold("gold_product_portrait.csv")
    fig, ax = plt.subplots(figsize=(12, 7))
    fig.suptitle("产品九宫格画像 × 营收等级分布", fontsize=15, fontweight="bold")

    if not df.empty and "当前画像" in df.columns:
        # 按 当前画像 × 帕累托分类 交叉计数
        if "帕累托分类" in df.columns:
            cross = pd.crosstab(df["当前画像"], df["帕累托分类"])
        else:
            cross = pd.crosstab(df["当前画像"], pd.cut(
                df.get("近12月销售额", pd.Series([0]*len(df))).fillna(0),
                bins=[0, 1e4, 1e5, 1e6, float("inf")],
                labels=["<1万", "1-10万", "10-100万", ">100万"],
            ))

        img_order = ["导入期", "成长期", "成熟期", "预警增长", "隐性衰退", "衰退期", "淘汰/长尾", "产品观察", "金牛/明星"]
        cross = cross.reindex([k for k in img_order if k in cross.index])

        colors = ["#2ECC71", "#3498DB", "#F39C12", "#E74C3C"]
        bottom = np.zeros(len(cross))
        for i, col in enumerate(cross.columns):
            vals = cross[col].values
            ax.barh(cross.index, vals, left=bottom, color=colors[i % len(colors)],
                    label=str(col), edgecolor="white", height=0.6)
            for j, v in enumerate(vals):
                if v > 0:
                    ax.text(bottom[j] + v / 2, j, str(int(v)),
                            ha="center", va="center", fontsize=8, fontweight="bold")
            bottom += vals

        ax.legend(loc="lower right", fontsize=9, title="营收层级")
        ax.set_xlabel("产品数")
        ax.set_title(f"总计 {len(df)} 个有效产品", fontsize=10, color="gray")
    else:
        ax.text(0.5, 0.5, "无产品画像数据", ha="center", va="center", transform=ax.transAxes)

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    plt.tight_layout()
    path = os.path.join(CHART_DIR, f"05_product_9grid_stacked.{fmt}")
    fig.savefig(path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return path


# ============================================================
# 图表 06: 异常类型分布（水平条形 + 等级堆叠）
# ============================================================
def chart_06_anomaly_distribution(fmt="png", dpi=150):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    _setup_chinese_font()

    df = _read_gold("异常日志.csv")
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    fig.suptitle("异常检测分布", fontsize=15, fontweight="bold")

    if not df.empty and "异常类型" in df.columns:
        # 左：异常类型 × 等级堆叠
        ax = axes[0]
        cross = pd.crosstab(df["异常类型"], df["异常等级"])
        sev_order = ["高", "中", "低"]
        sev_colors = {"高": "#E74C3C", "中": "#F39C12", "低": "#3498DB"}
        cross = cross.reindex(columns=[s for s in sev_order if s in cross.columns])

        bottom = np.zeros(len(cross))
        for sev in cross.columns:
            vals = cross[sev].values
            ax.barh(cross.index, vals, left=bottom, color=sev_colors.get(sev, "#999"),
                    label=sev, edgecolor="white", height=0.55)
            for j, v in enumerate(vals):
                if v > 0:
                    ax.text(bottom[j] + v / 2, j, str(int(v)),
                            ha="center", va="center", fontsize=8, fontweight="bold")
            bottom += vals
        ax.legend(fontsize=9)
        ax.set_xlabel("异常条数")
        ax.set_title("按异常类型分布", fontsize=12)

        # 右：等级占比环形图
        ax = axes[1]
        sev_counts = df["异常等级"].value_counts()
        sev_counts = sev_counts.reindex([s for s in sev_order if s in sev_counts.index])
        pie_colors = [sev_colors.get(s, "#999") for s in sev_counts.index]
        wedges, texts, autotexts = ax.pie(
            sev_counts.values, labels=sev_counts.index, autopct="%1.1f%%",
            colors=pie_colors, startangle=90, pctdistance=0.75,
            wedgeprops=dict(width=0.35, edgecolor="white"),
        )
        for at in autotexts:
            at.set_fontsize(10)
        ax.set_title(f"总计 {len(df)} 条异常", fontsize=10, color="gray")
    else:
        for ax in axes:
            ax.text(0.5, 0.5, "无异常日志数据", ha="center", va="center", transform=ax.transAxes)

    for ax in axes:
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
    plt.tight_layout()
    path = os.path.join(CHART_DIR, f"06_anomaly_distribution.{fmt}")
    fig.savefig(path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return path


# ============================================================
# 图表 07: 客户价值散点矩阵（RFM-π 气泡图）
# ============================================================
def chart_07_customer_value_scatter(fmt="png", dpi=150):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    _setup_chinese_font()

    df = _read_gold("客户全景.csv")
    fig, ax = plt.subplots(figsize=(12, 8))
    fig.suptitle("客户价值矩阵：RFM-π 分 vs 营收 vs 毛利率", fontsize=15, fontweight="bold")

    if not df.empty and "近12月收入" in df.columns and "近12月毛利率" in df.columns:
        rev = df["近12月收入"].fillna(0)
        margin = df["近12月毛利率"].fillna(0)
        rfm_col = "RFMπ_综合分" if "RFMπ_综合分" in df.columns else None

        # 气泡大小=营收(对数缩放)
        sizes = np.clip(rev / rev.max() * 600, 8, 600)

        if rfm_col and rfm_col in df.columns:
            color_val = df[rfm_col].fillna(0)
            scatter = ax.scatter(rev, margin, s=sizes, c=color_val,
                                 cmap="RdYlGn", alpha=0.65, edgecolors="#333", linewidth=0.3)
            cbar = plt.colorbar(scatter, ax=ax)
            cbar.set_label("RFM-π 综合分", fontsize=10)
        else:
            # 按生命周期着色
            if "客户生命周期" in df.columns:
                stages = df["客户生命周期"].fillna("未知")
                stage_list = stages.unique()
                cmap = plt.cm.Set3(np.linspace(0, 1, len(stage_list)))
                for i, stage in enumerate(stage_list):
                    mask = stages == stage
                    ax.scatter(rev[mask], margin[mask], s=sizes[mask],
                               color=cmap[i], alpha=0.65, edgecolors="#333",
                               linewidth=0.3, label=stage)
                ax.legend(fontsize=8, loc="upper right", title="客户生命周期")
            else:
                ax.scatter(rev, margin, s=sizes, color="#3498DB", alpha=0.6,
                           edgecolors="#333", linewidth=0.3)

        # 标注头部客户
        top5 = rev.nlargest(5).index
        for idx in top5:
            name = str(df.loc[idx, "客户编号"])[:18]
            ax.annotate(name, (rev[idx], margin[idx]),
                        textcoords="offset points", xytext=(5, 5),
                        fontsize=7, alpha=0.85,
                        arrowprops=dict(arrowstyle="->", color="gray", lw=0.6))

        ax.set_xlabel("近12月收入 (元)", fontsize=11)
        ax.set_ylabel("近12月毛利率 (%)", fontsize=11)
        ax.set_xscale("log")
        ax.set_title(f"{len(df)} 个客户 | 气泡大小=收入规模", fontsize=10, color="gray")
    else:
        ax.text(0.5, 0.5, "缺少必要的客户数据列", ha="center", va="center", transform=ax.transAxes)

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(alpha=0.2)
    plt.tight_layout()
    path = os.path.join(CHART_DIR, f"07_customer_value_scatter.{fmt}")
    fig.savefig(path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return path


# ============================================================
# 图表 08: 价格离散度分布（箱线图 × 品类）
# ============================================================
def chart_08_price_dispersion_box(fmt="png", dpi=150):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    _setup_chinese_font()

    price_df = _read_gold("价格离散度.csv")
    # 尝试加载产品分类信息
    bridge_df = _read_gold("客户产品桥接.csv")

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    fig.suptitle("价格离散度分析", fontsize=15, fontweight="bold")

    if not price_df.empty:
        # 左：CV分布直方图
        ax = axes[0]
        if "变异系数(CV)" in price_df.columns:
            cv_vals = price_df["变异系数(CV)"].dropna()
            ax.hist(cv_vals, bins=30, color="#3498DB", edgecolor="white", alpha=0.75)
            ax.axvline(cv_vals.median(), color="#E74C3C", linestyle="--", linewidth=1.5,
                       label=f"中位数CV={cv_vals.median():.3f}")
            ax.axvline(cv_vals.quantile(0.75), color="#F39C12", linestyle=":", linewidth=1.5,
                       label=f"P75 CV={cv_vals.quantile(0.75):.3f}")
            ax.set_xlabel("价格变异系数 (CV)")
            ax.set_ylabel("产品品种数")
            ax.set_title(f"价格CV分布 ({len(cv_vals)}个品种)", fontsize=11)
            ax.legend(fontsize=9)
        else:
            ax.text(0.5, 0.5, "无CV数据", ha="center", va="center", transform=ax.transAxes)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

        # 右：CV分桶分布
        ax = axes[1]
        if "变异系数(CV)" in price_df.columns:
            cv_vals = price_df["变异系数(CV)"].dropna()
            buckets = pd.cut(cv_vals, bins=[0, 0.1, 0.2, 0.3, float("inf")],
                            labels=["CV<0.1(低)", "0.1-0.2(中低)", "0.2-0.3(中高)", "CV>0.3(高)"])
            bucket_counts = buckets.value_counts().sort_index()
            bucket_colors = ["#2ECC71", "#3498DB", "#F39C12", "#E74C3C"]
            bars = ax.bar(bucket_counts.index.astype(str), bucket_counts.values,
                         color=bucket_colors, edgecolor="white", width=0.5)
            for bar, val in zip(bars, bucket_counts.values):
                pct = val / len(cv_vals) * 100
                ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 2,
                        f"{val}\n({pct:.1f}%)", ha="center", fontsize=9, fontweight="bold")
            ax.set_title("价格CV分桶分布", fontsize=11)
            ax.set_ylabel("品种数")
        else:
            ax.text(0.5, 0.5, "无价格CV数据", ha="center", va="center", transform=ax.transAxes)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
    else:
        for ax in axes:
            ax.text(0.5, 0.5, "无价格离散度数据", ha="center", va="center", transform=ax.transAxes)

    plt.tight_layout()
    path = os.path.join(CHART_DIR, f"08_price_dispersion_box.{fmt}")
    fig.savefig(path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return path


# ============================================================
# 图表 09: 降价策略评估（水平气泡图）
# ============================================================
def chart_09_markdown_evaluation(fmt="png", dpi=150):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    _setup_chinese_font()

    df = _read_gold("降价策略试算.csv")
    fig, ax = plt.subplots(figsize=(12, 7))
    fig.suptitle("降价策略评估：降价幅度 vs 预期营收变化", fontsize=15, fontweight="bold")

    if not df.empty and "降价幅度" in df.columns and "营收变化" in df.columns:
        # 按产品聚合
        if "产品品种" in df.columns:
            prod_summary = df.groupby("产品品种").agg(
                平均降价幅度=("降价幅度", "mean"),
                预期营收变化=("营收变化", "sum"),
                条目数=("降价幅度", "count"),
            ).reset_index()
        else:
            prod_summary = df.copy()
            if "平均降价幅度" not in prod_summary.columns:
                prod_summary["平均降价幅度"] = 0.05
            if "预期营收变化" not in prod_summary.columns:
                prod_summary["预期营收变化"] = 0

        rev_change = prod_summary["预期营收变化"].fillna(0)
        markdown = prod_summary["平均降价幅度"].fillna(0)

        # 颜色：营收增长=绿，减少=红
        colors = np.where(rev_change > 0, "#2ECC71", "#E74C3C")
        sizes = np.clip(np.abs(rev_change) / max(np.abs(rev_change).max(), 1) * 400, 10, 400)

        ax.scatter(markdown * 100, rev_change, s=sizes, c=colors, alpha=0.55,
                   edgecolors="#333", linewidth=0.3)
        ax.axhline(0, color="gray", linestyle="--", linewidth=0.8, alpha=0.6)
        ax.set_xlabel("平均降价幅度 (%)", fontsize=11)
        ax.set_ylabel("预期营收变化 (元)", fontsize=11)
        ax.set_title(f"{len(prod_summary)} 个产品 × 降价策略试算", fontsize=10, color="gray")

        # 标注极端值
        top_gain = rev_change.nlargest(3)
        top_loss = rev_change.nsmallest(3)
        for idx in top_gain.index:
            name = str(prod_summary.loc[idx, "产品品种"] if "产品品种" in prod_summary.columns else idx)[:15]
            ax.annotate(name, (markdown[idx] * 100, rev_change[idx]),
                        textcoords="offset points", xytext=(5, 5),
                        fontsize=7, color="#2ECC71")
        for idx in top_loss.index:
            name = str(prod_summary.loc[idx, "产品品种"] if "产品品种" in prod_summary.columns else idx)[:15]
            ax.annotate(name, (markdown[idx] * 100, rev_change[idx]),
                        textcoords="offset points", xytext=(5, -12),
                        fontsize=7, color="#E74C3C")
    else:
        ax.text(0.5, 0.5, "无降价策略数据", ha="center", va="center", transform=ax.transAxes)

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(alpha=0.2)
    plt.tight_layout()
    path = os.path.join(CHART_DIR, f"09_markdown_evaluation.{fmt}")
    fig.savefig(path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return path


# ============================================================
# 图表 10: 集团对比雷达图
# ============================================================
def chart_10_group_radar(fmt="png", dpi=150):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    _setup_chinese_font()

    df = _read_gold("集团聚合.csv")
    fig, ax = plt.subplots(figsize=(10, 9), subplot_kw=dict(polar=True))
    fig.suptitle("集团多维对比", fontsize=15, fontweight="bold")

    if not df.empty and "集团名称" in df.columns and len(df) >= 2:
        dimensions = ["近12月收入", "近12月毛利", "订单数", "集团产品线覆盖", "集团活跃成员"]
        dims = [d for d in dimensions if d in df.columns]

        if len(dims) >= 3:
            # 归一化到 0-1
            norm_df = df.copy()
            for d in dims:
                mx = norm_df[d].max()
                norm_df[d] = norm_df[d] / mx if mx > 0 else 0

            angles = np.linspace(0, 2 * np.pi, len(dims), endpoint=False).tolist()
            angles += angles[:1]

            colors = plt.cm.tab10(np.linspace(0, 1, len(df)))
            for i, (_, row) in enumerate(norm_df.iterrows()):
                values = [row[d] for d in dims]
                values += values[:1]
                name = str(row["集团名称"])[:12]
                ax.fill(angles, values, alpha=0.08, color=colors[i])
                ax.plot(angles, values, "o-", linewidth=1.8, color=colors[i], label=name, markersize=4)

            ax.set_xticks(angles[:-1])
            ax.set_xticklabels(dims, fontsize=10)
            ax.set_yticklabels([])
            ax.legend(loc="upper right", bbox_to_anchor=(1.3, 1.1), fontsize=9)
            ax.set_title(f"{len(df)} 个集团 | {len(dims)} 维对比", fontsize=10, color="gray", pad=20)
    else:
        ax.text(0.5, 0.5, "集团数据不足（需要≥2个集团）", ha="center", va="center", transform=ax.transAxes)

    plt.tight_layout()
    path = os.path.join(CHART_DIR, f"10_group_radar.{fmt}")
    fig.savefig(path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return path


# ============================================================
# 图表 11: 客户组合健康度堆叠图
# ============================================================
def chart_11_portfolio_health_stacked(fmt="png", dpi=150):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    _setup_chinese_font()

    df = _read_gold("客户组合健康度.csv")
    fig, ax = plt.subplots(figsize=(14, 7))
    fig.suptitle("客户产品组合健康度 (Top 30 客户按风险品占比排序)", fontsize=15, fontweight="bold")

    if not df.empty and "客户编号" in df.columns:
        # 找画像占比列
        ratio_cols = [c for c in df.columns if c.endswith("_占比") or "占比" in c]
        if not ratio_cols:
            ratio_cols = [c for c in df.columns if c.endswith("_金额")]

        if ratio_cols:
            # 按风险品占比排序取 Top30
            risk_cols = [c for c in ratio_cols if any(k in c for k in ["衰退", "预警", "风险"])]
            if risk_cols:
                df["_风险品占比"] = df[risk_cols].sum(axis=1)
            else:
                df["_风险品占比"] = 0
            df_sorted = df.nlargest(30, "_风险品占比" if "_风险品占比" in df.columns else "总金额")

            bottom = np.zeros(len(df_sorted))
            img_colors = plt.cm.RdYlGn(np.linspace(0.1, 0.9, len(ratio_cols)))
            for i, col in enumerate(ratio_cols):
                vals = df_sorted[col].fillna(0).values
                clean_label = col.replace("_占比", "").replace("_金额", "")
                ax.barh(range(len(df_sorted)), vals, left=bottom,
                        color=img_colors[i % len(img_colors)],
                        label=clean_label, edgecolor="white", height=0.7)
                bottom += vals

            ax.set_yticks(range(len(df_sorted)))
            ax.set_yticklabels(df_sorted["客户编号"].astype(str).str[:20], fontsize=7)
            ax.set_xlabel("金额占比")
            ax.legend(loc="lower right", fontsize=7, ncol=2)
            ax.set_title(f"Top 30 客户 (按风险品金额占比)", fontsize=10, color="gray")
        else:
            ax.text(0.5, 0.5, "无画像占比数据", ha="center", va="center", transform=ax.transAxes)
    else:
        ax.text(0.5, 0.5, "无客户组合健康度数据", ha="center", va="center", transform=ax.transAxes)

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    plt.tight_layout()
    path = os.path.join(CHART_DIR, f"11_portfolio_health_stacked.{fmt}")
    fig.savefig(path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return path


# ============================================================
# 图表 12: 产品营收集中度（Pareto 图）
# ============================================================
def chart_12_product_pareto(fmt="png", dpi=150):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    _setup_chinese_font()

    df = _read_gold("gold_product_portrait.csv")
    fig, ax = plt.subplots(figsize=(12, 6))
    fig.suptitle("产品营收集中度 (Pareto 分析)", fontsize=15, fontweight="bold")

    rev_col = None
    for candidate in ["近12月销售额", "近12月营收", "近12月收入"]:
        if candidate in df.columns:
            rev_col = candidate
            break

    if not df.empty and rev_col and "产品名称" in df.columns:
        sorted_df = df.sort_values(rev_col, ascending=False, kind='stable').reset_index(drop=True)
        rev = sorted_df[rev_col].fillna(0)
        total = rev.sum()
        cumsum = rev.cumsum() / total * 100

        x = range(len(sorted_df))
        # 柱状图
        bars = ax.bar(x, rev.values, color="#3498DB", alpha=0.65, width=0.9)
        # 累计折线
        ax2 = ax.twinx()
        ax2.plot(x, cumsum.values, color="#E74C3C", linewidth=2, label="累计占比%")
        ax2.set_ylabel("累计营收占比 (%)", color="#E74C3C")
        ax2.tick_params(axis="y", labelcolor="#E74C3C")

        # 标注 Top5
        for i in range(min(5, len(sorted_df))):
            name = str(sorted_df["产品名称"].iloc[i])[:15]
            ax.annotate(f"{name}\n¥{rev[i]:,.0f}",
                        (i, rev[i]), textcoords="offset points",
                        xytext=(0, 8), ha="center", fontsize=7, color="#2C3E50")

        ax.set_xlabel("产品排名 (按营收降序)")
        ax.set_ylabel("营收 (元)")
        ax2.axhline(80, color="gray", linestyle="--", linewidth=0.8, alpha=0.7)
        ax2.text(len(sorted_df) * 0.95, 81, "80%线", fontsize=8, color="gray", ha="right")

        # 标注累计贡献
        n80 = (cumsum <= 80).sum()
        ax.set_title(f"总计 {len(sorted_df)} 个产品 | 前 {n80} 个贡献 80% 营收", fontsize=10, color="gray")
    else:
        ax.text(0.5, 0.5, "无产品营收数据", ha="center", va="center", transform=ax.transAxes)

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="y", alpha=0.2)
    plt.tight_layout()
    path = os.path.join(CHART_DIR, f"12_product_pareto.{fmt}")
    fig.savefig(path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return path


# ============================================================
# 图表 13: 客户月度趋势（TOP客户折线图）
# ============================================================
def chart_13_top_customer_trends(fmt="png", dpi=150):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    _setup_chinese_font()

    monthly = _read_gold("客户月度趋势.csv")
    portrait = _read_gold("客户全景.csv")

    fig, ax = plt.subplots(figsize=(14, 7))
    fig.suptitle("TOP 8 客户月度营收趋势", fontsize=15, fontweight="bold")

    if not monthly.empty and "客户编号" in monthly.columns:
        if "月份" in monthly.columns:
            monthly["月份"] = monthly["月份"].astype(str)

        # 找出 TOP 8 客户（按总营收）
        if not portrait.empty and "客户编号" in portrait.columns and "近12月收入" in portrait.columns:
            top_custs = portrait.nlargest(8, "近12月收入")["客户编号"].tolist()
        else:
            cust_total = monthly.groupby("客户编号")["月收入"].sum() if "月收入" in monthly.columns else None
            if cust_total is not None:
                top_custs = cust_total.nlargest(8).index.tolist()
            else:
                top_custs = monthly["客户编号"].unique()[:8]

        colors = plt.cm.tab10(np.linspace(0, 1, len(top_custs)))
        for i, cust in enumerate(top_custs):
            cust_data = monthly[monthly["客户编号"] == cust].copy()
            if "月份" in cust_data.columns:
                cust_data = cust_data.sort_values("月份", kind='stable')
            rev_col = "月收入"
            if rev_col not in cust_data.columns:
                continue
            x = range(len(cust_data))
            ax.plot(x, cust_data[rev_col].values, color=colors[i], linewidth=1.6,
                    marker="o", markersize=2, label=str(cust)[:18], alpha=0.85)

        ax.set_xlabel("交易月份序号")
        ax.set_ylabel("月销售额 (元)")
        ax.legend(fontsize=8, loc="upper left", ncol=2)
        ax.set_title(f"Top {len(top_custs)} 客户的月度销售额轨迹", fontsize=10, color="gray")
    else:
        ax.text(0.5, 0.5, "无客户月度趋势数据", ha="center", va="center", transform=ax.transAxes)

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(alpha=0.2)
    plt.tight_layout()
    path = os.path.join(CHART_DIR, f"13_top_customer_trends.{fmt}")
    fig.savefig(path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return path


# ============================================================
# 图表 14: 产品衰退风险分布（散点+风险等级着色）
# ============================================================
def chart_14_decline_risk_scatter(fmt="png", dpi=150):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    _setup_chinese_font()

    df = _read_gold("gold_product_portrait.csv")
    fig, ax = plt.subplots(figsize=(12, 7))
    fig.suptitle("产品衰退风险评估", fontsize=15, fontweight="bold")

    if not df.empty and "综合评分" in df.columns:
        risk_score = df["综合评分"].fillna(0)
        risk_level = df.get("综合风险等级", pd.Series(["未知"] * len(df)))

        # 营收/毛利作为Y轴
        rev_col = None
        for c in ["近12月销售额", "近12月营收", "近12月收入"]:
            if c in df.columns:
                rev_col = c
                break
        y_val = df[rev_col].fillna(0) if rev_col else np.arange(len(df))

        level_colors = {"低风险": "#2ECC71", "中风险": "#F39C12", "高风险": "#E74C3C", "极高风险": "#8E44AD"}
        for level in risk_level.unique():
            mask = risk_level == level
            ax.scatter(risk_score[mask], y_val[mask] if rev_col else y_val[mask],
                       color=level_colors.get(level, "#999"), alpha=0.6,
                       edgecolors="#333", linewidth=0.2, label=level, s=30)

        ax.set_xlabel("综合评分 (0-100)")
        ax.set_ylabel(rev_col if rev_col else "产品序号")
        if rev_col:
            ax.set_yscale("log")
        ax.legend(fontsize=9, title="风险等级")
        ax.set_title(f"{len(df)} 个产品 | 高风险={int((risk_level.isin(['高风险','极高风险'])).sum())} 个",
                     fontsize=10, color="gray")
    else:
        ax.text(0.5, 0.5, "无衰退风险数据", ha="center", va="center", transform=ax.transAxes)

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(alpha=0.2)
    plt.tight_layout()
    path = os.path.join(CHART_DIR, f"14_decline_risk_scatter.{fmt}")
    fig.savefig(path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return path


# ============================================================
# 图表 15: 毛利率 vs 营收增长率 四象限
# ============================================================
def chart_15_margin_growth_quadrant(fmt="png", dpi=150):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    _setup_chinese_font()

    df = _read_gold("gold_product_portrait.csv")
    fig, ax = plt.subplots(figsize=(11, 8))
    fig.suptitle("产品毛利率 vs 营收增长率 (四象限)", fontsize=15, fontweight="bold")

    margin_col = None
    for c in ["近12月毛利率%", "近12月毛利率", "历史平均毛利率%"]:
        if c in df.columns:
            margin_col = c
            break

    growth_col = None
    for c in ["近12月营收增长%", "营收增长率%", "近12月增长率%"]:
        if c in df.columns:
            growth_col = c
            break

    if not df.empty and margin_col and growth_col:
        margin = df[margin_col].fillna(0)
        growth = df[growth_col].fillna(0)

        # 裁剪异常值
        growth_clip = growth.clip(-200, 300)
        margin_clip = margin.clip(-50, 100)

        # 气泡大小=营收规模
        rev_col = None
        for c in ["近12月销售额", "近12月营收"]:
            if c in df.columns:
                rev_col = c
                break
        sizes = np.clip(df[rev_col].fillna(1) / df[rev_col].max() * 300, 5, 300) if rev_col else 20

        # 四象限着色
        median_margin = margin_clip.median()
        median_growth = growth_clip.median()

        # 按画像着色
        if "当前画像" in df.columns:
            portrait = df["当前画像"].fillna("未知")
            portrait_colors = {
                "导入期": "#3498DB", "成长期": "#2ECC71", "成熟期": "#1ABC9C",
                "预警增长": "#F39C12", "隐性衰退": "#E67E22", "衰退期": "#E74C3C",
                "金牛/明星": "#9B59B6", "淘汰/长尾": "#95A5A6", "产品观察": "#BDC3C7",
            }
            for img in portrait.unique():
                mask = portrait == img
                ax.scatter(growth_clip[mask], margin_clip[mask], s=sizes[mask] if rev_col else 20,
                           color=portrait_colors.get(img, "#999"), alpha=0.55,
                           edgecolors="#333", linewidth=0.2, label=img)
            ax.legend(fontsize=7, loc="upper right", ncol=2, title="产品画像")
        else:
            ax.scatter(growth_clip, margin_clip, s=sizes, color="#3498DB", alpha=0.5,
                       edgecolors="#333", linewidth=0.2)

        # 象限分割线
        ax.axhline(median_margin, color="gray", linestyle="--", linewidth=1, alpha=0.6)
        ax.axvline(median_growth, color="gray", linestyle="--", linewidth=1, alpha=0.6)

        # 象限标签
        ax.text(growth_clip.max() * 0.85, margin_clip.max() * 0.85, "高增长×高毛利\n(明星)",
                fontsize=9, color="#2ECC71", ha="center", alpha=0.8)
        ax.text(growth_clip.min() * 0.85, margin_clip.max() * 0.85, "低增长×高毛利\n(金牛)",
                fontsize=9, color="#3498DB", ha="center", alpha=0.8)
        ax.text(growth_clip.max() * 0.85, margin_clip.min() * 0.85, "高增长×低毛利\n(问题)",
                fontsize=9, color="#F39C12", ha="center", alpha=0.8)
        ax.text(growth_clip.min() * 0.85, margin_clip.min() * 0.85, "低增长×低毛利\n(瘦狗)",
                fontsize=9, color="#E74C3C", ha="center", alpha=0.8)

        ax.set_xlabel("营收增长率 (%)", fontsize=11)
        ax.set_ylabel("毛利率 (%)", fontsize=11)
        ax.set_title(f"{len(df)} 个产品 | 中线: 毛利率中位数={median_margin:.1f}%  增长率中位数={median_growth:.1f}%",
                     fontsize=10, color="gray")
    else:
        ax.text(0.5, 0.5, "缺少毛利率/增长率数据", ha="center", va="center", transform=ax.transAxes)

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(alpha=0.15)
    plt.tight_layout()
    path = os.path.join(CHART_DIR, f"15_margin_growth_quadrant.{fmt}")
    fig.savefig(path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return path


# ============================================================
# Phase 3 主函数
# ============================================================
CHART_REGISTRY = {
    "1": chart_01_product_portrait_dist,
    "2": chart_02_customer_lifecycle_donut,
    "3": chart_03_customer_tier_bar,
    "4": chart_04_kpi_monthly_trend,
    "5": chart_05_product_9grid_stacked,
    "6": chart_06_anomaly_distribution,
    "7": chart_07_customer_value_scatter,
    "8": chart_08_price_dispersion_box,
    "9": chart_09_markdown_evaluation,
    "10": chart_10_group_radar,
    "11": chart_11_portfolio_health_stacked,
    "12": chart_12_product_pareto,
    "13": chart_13_top_customer_trends,
    "14": chart_14_decline_risk_scatter,
    "15": chart_15_margin_growth_quadrant,
}

CHART_NAMES = {
    "1": "产品画像分布",
    "2": "客户生命周期分布",
    "3": "客户等级与渠道分布",
    "4": "月度营收+订单趋势",
    "5": "产品九宫格×营收分布",
    "6": "异常类型分布",
    "7": "客户价值矩阵",
    "8": "价格离散度分布",
    "9": "降价策略评估",
    "10": "集团多维对比",
    "11": "客户组合健康度",
    "12": "产品营收Pareto",
    "13": "TOP客户月度趋势",
    "14": "产品衰退风险评估",
    "15": "毛利率vs增长率四象限",
}


def run_phase3(charts="1,2,3,4,5,6,7,8,9,10,11,12,13,14,15", fmt="png", dpi=150, data=None):
    ensure_diag_dir()
    os.makedirs(CHART_DIR, exist_ok=True)

    selected = [c.strip() for c in charts.split(",") if c.strip() in CHART_REGISTRY]

    header(f"Phase 3：可视化图表生成 v2.0 ({len(selected)} 张, 来源: Gold CSV)")

    paths = []
    for chart_id in selected:
        func = CHART_REGISTRY[chart_id]
        name = CHART_NAMES.get(chart_id, chart_id)
        log(f"[图表 {chart_id}] {name}")
        try:
            path = func(fmt=fmt, dpi=dpi)
            paths.append(path)
            print(f"  [OK] {path}")
        except (ValueError, TypeError, OSError) as e:
            print(f"  [FAIL] {name}: {e}")
            import traceback
            traceback.print_exc()

    print(f"\n  完成: {len(paths)}/{len(selected)} 张图表 → {CHART_DIR}")
    return paths


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Phase 3：可视化图表生成 v2.0")
    parser.add_argument("--charts", type=str, default="1,2,3,4,5,6,7,8,9,10,11,12,13,14,15",
                        help="图表 ID，逗号分隔（默认全部）")
    parser.add_argument("--format", type=str, default="png", choices=["png", "pdf", "svg"],
                        help="输出格式（默认 png）")
    parser.add_argument("--dpi", type=int, default=150, help="图片分辨率（默认 150）")
    args = parser.parse_args()

    run_phase3(charts=args.charts, fmt=args.format, dpi=args.dpi)
