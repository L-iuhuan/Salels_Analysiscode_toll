# -*- coding: utf-8 -*-
"""charts_aug2.py - 8月PPT图表重制版（7月风格公约 + PPTD媒体文件名契约）.

公约（来源=7月charts脚本实测）：
- dpi=200, savefig bbox='tight' pad=0.1
- 数据标签9.5-10.5pt / 轴刻度9-10pt / 图例8.5pt / 图内标题11-13pt
- clean_ax去顶右边框, 仅浅灰横向虚线网格
- 配色 C_PRIMARY #00437C / C_ACCENT #F18101 / C_POSITIVE #8FC31F / C_CYAN #00A0E9
  / C_GRAY #595959 / C_LIGHT #727171 / 负值 #C52828
数据全部来自已核对的 05_过程数据 json（同 charts_aug.py v1），无新取数。
"""
import json
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import rcParams

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(os.path.dirname(BASE), "05_过程数据")
OUT_DIR = os.path.join(BASE, "pptd", "media")
os.makedirs(OUT_DIR, exist_ok=True)

C_PRIMARY = "#00437C"
C_ACCENT = "#F18101"
C_POSITIVE = "#8FC31F"
C_CYAN = "#00A0E9"
C_GRAY = "#595959"
C_LIGHT = "#727171"
C_NEG = "#C52828"

rcParams["font.sans-serif"] = ["HarmonyOS Sans SC", "Microsoft YaHei", "SimHei"]
rcParams["axes.unicode_minus"] = False


def load_json(name):
    with open(os.path.join(DATA_DIR, name), encoding="utf-8") as f:
        return json.load(f)


def save(fig, name):
    path = os.path.join(OUT_DIR, name)
    fig.savefig(path, dpi=200, bbox_inches="tight", pad_inches=0.1)
    plt.close(fig)
    print(f"OK {name}")


def clean_ax(ax, ygrid=True, xgrid=False):
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    if ygrid:
        ax.grid(axis="y", linestyle="--", alpha=0.35, lw=0.6)
    if xgrid:
        ax.grid(axis="x", linestyle="--", alpha=0.35, lw=0.6)
    ax.set_axisbelow(True)
    ax.tick_params(labelsize=9.5)


def waterfall(ax, labels, values, title):
    """瀑布图：增量柱+合计柱+累积连接线，标签在柱外。"""
    n = len(values)
    deltas, total = values[:-1], values[-1]
    xs = np.arange(n)
    bottoms = []
    cum = 0.0
    for v in deltas:
        bottoms.append(cum)
        cum += v
    bottoms.append(0.0)
    colors = [C_PRIMARY if v >= 0 else C_NEG for v in deltas] + [C_ACCENT]
    bars = ax.bar(xs, values, bottom=bottoms, color=colors, width=0.56,
                  edgecolor="white", lw=0.5)
    # 连接线：柱i右缘→柱i+1左缘，位于累积水平
    level = 0.0
    for i, v in enumerate(deltas):
        level += v
        ax.plot([i + 0.28, i + 1 - 0.28], [level, level],
                color=C_GRAY, lw=0.8, ls="--", zorder=1)
    # 标签（柱外）
    for i, (b, v) in enumerate(zip(bars, values)):
        top = bottoms[i] + v
        if v >= 0:
            y, va = top + 2, "bottom"
        else:
            y, va = top - 2, "top"
        ax.text(b.get_x() + b.get_width() / 2, y, f"{v:+.0f}",
                ha="center", va=va, fontsize=9.5, fontweight="bold",
                color=C_ACCENT if i == n - 1 else "#262626")
    ax.axhline(0, color=C_GRAY, lw=0.6)
    ax.set_xticks(xs)
    ax.set_xticklabels(labels, fontsize=9.5)
    ax.set_ylabel("万元", fontsize=9.5, color=C_LIGHT)
    ax.set_title(title, fontsize=11.5, color=C_PRIMARY, fontweight="bold", pad=8)
    tops = [bottoms[k] + values[k] for k in range(n)]
    lo = min(0, min(tops), min(bottoms)) * 1.2 - 10
    hi = max(0, max(tops), max(bottoms)) * 1.2 + 10
    ax.set_ylim(lo, hi)
    clean_ax(ax)


def chart_p04a():
    b = load_json("recompute.json")["桥_环比_2026_08_vs_2026_07"]
    vals = [b["量4"], b["结构4"], b["价"], b["成本"], b["dGP"]]
    fig, ax = plt.subplots(figsize=(5.5, 3.9))
    waterfall(ax, ["量效应", "结构效应", "价效应", "成本效应", "净变动"], vals,
              "环比毛利桥：量效应是唯一负贡献")
    save(fig, "p04a_waterfall_mom.png")


def chart_p04b():
    b = load_json("recompute.json")["桥_同比_2026_08_vs_2025_08"]
    vals = [b["量4"], b["结构4"], b["价"], b["成本"], b["dGP"]]
    fig, ax = plt.subplots(figsize=(5.5, 3.9))
    waterfall(ax, ["量效应", "结构效应", "价效应", "成本效应", "净变动"], vals,
              "同比毛利桥：价效应是主拖累")
    save(fig, "p04b_waterfall_yoy.png")


def chart_p06():
    series = load_json("analysis2.json")["D_四因子长周期"]
    months = [s["月"] for s in series]
    vol = [s["量"] for s in series]
    price = [s["价"] for s in series]
    margin = [s["毛利率"] * 100 for s in series]
    x = np.arange(len(months))
    fig, ax1 = plt.subplots(figsize=(10, 2.7))
    ax1.plot(x, vol, color=C_PRIMARY, lw=1.8, label="量效应(万)")
    ax1.plot(x, price, color=C_ACCENT, lw=1.8, label="价效应(万)")
    ax1.set_ylabel("万元", fontsize=9.5, color=C_LIGHT)
    ax1.set_xticks(x[::3])
    ax1.set_xticklabels(months[::3], fontsize=9, rotation=0)
    ax1.axhline(0, color=C_GRAY, lw=0.5)
    ax1.legend(loc="upper left", fontsize=8.5, ncol=2, frameon=False)
    ax2 = ax1.twinx()
    ax2.plot(x, margin, color=C_POSITIVE, lw=1.6, ls="--", label="毛利率(%)")
    ax2.set_ylabel("毛利率%", fontsize=9.5, color=C_LIGHT)
    ax2.legend(loc="upper right", fontsize=8.5, frameon=False)
    ax2.spines["top"].set_visible(False)
    ax2.tick_params(labelsize=9)
    top_ref = max(vol + price)
    for s in series:
        if s["价"] > 0 and s["结构"] > 0:
            idx = months.index(s["月"])
            ax1.axvspan(idx - 0.4, idx + 0.4, color=C_PRIMARY, alpha=0.12)
            ax1.text(idx, top_ref * 1.02, s["月"], ha="center", fontsize=9,
                     color=C_PRIMARY, fontweight="bold")
    ax1.set_title("31个月长周期：量主导波动，本月价+结构双正（2025-02以来首次）",
                  fontsize=12, color=C_PRIMARY, fontweight="bold", pad=8)
    ax1.spines["top"].set_visible(False)
    ax1.tick_params(labelsize=9)
    ax1.grid(axis="y", linestyle="--", alpha=0.35, lw=0.6)
    ax1.set_axisbelow(True)
    fig.tight_layout()
    save(fig, "p06_longcycle.png")


def chart_p07():
    cls = load_json("report_data.json")["cls"]
    ka = round(cls["KA"]["dpft"] / 10000, 1)
    mm = round(cls["MM"]["dpft"] / 10000, 1)
    fig, ax = plt.subplots(figsize=(5.5, 3.9))
    bars = ax.barh(["KA", "MM"], [ka, mm], color=[C_NEG, C_POSITIVE], height=0.45)
    for b, v in zip(bars, [ka, mm]):
        ax.text(v + (60 if v >= 0 else -60), b.get_y() + b.get_height() / 2,
                f"{v:+.0f}万", va="center",
                ha="left" if v >= 0 else "right",
                fontsize=10.5, fontweight="bold", color="#262626")
    ax.text(mm * 0.55, 1, "占利润增量93%", va="center", ha="center",
            fontsize=9.5, color="white", fontweight="bold")
    ax.axvline(0, color=C_GRAY, lw=0.6)
    ax.set_xlim(ka - 500, mm + 700)
    ax.set_xlabel("利润同比增量（万元）", fontsize=9.5, color=C_LIGHT)
    ax.set_title("客户分群：MM贡献增量93%，KA零增长", fontsize=11.5,
                 color=C_PRIMARY, fontweight="bold", pad=8)
    clean_ax(ax, ygrid=False, xgrid=True)
    fig.tight_layout()
    save(fig, "p07_ka_mm.png")


HEDGE_GROUPS = [
    ("p08a_hbridge.png", "H桥BDC：客户间转移", "需求还在，换了客户承接",
     [("追觅", "H桥BDC-高压36V以上<3A"), ("小米集团", "H桥BDC-高压36V以上<3A"),
      ("石头", "H桥BDC-高压36V以上<3A")]),
    ("p08b_dcdc18v.png", "DCDC-18V：全负无对冲", "品类级失血",
     [("中兴康讯", "DCDC-18V-降压2~4A"), ("TPLINK", "DCDC-18V-降压2~4A"),
      ("共进", "DCDC-18V-降压2~4A"), ("兆驰", "DCDC-18V-降压2~4A"),
      ("创维数字", "DCDC-18V-降压2~4A")]),
    ("p08c_pse.png", "PSE：全线共振", "品类级红利",
     [("海康威视", "PSE"), ("大华集团", "PSE"), ("中兴康讯", "PSE")]),
]


def chart_p08():
    mat = load_json("analysis2.json")["C_同类对冲矩阵"]
    for fname, title, sub, pairs in HEDGE_GROUPS:
        labels, vals = [], []
        for cust, cat in pairs:
            found = [r for r in mat[cust] if r["品类"] == cat]
            vals.append(found[0]["增量"] if found else 0)
            labels.append(cust.replace("集团", "").replace("威视", ""))
        colors = [C_NEG if v < 0 else C_POSITIVE for v in vals]
        fig, ax = plt.subplots(figsize=(2.7, 3.9))
        bars = ax.barh(labels[::-1], vals[::-1], color=colors[::-1], height=0.5)
        span = max(abs(v) for v in vals)
        for b, v in zip(bars, vals[::-1]):
            ax.text(v + (span * 0.04 if v >= 0 else -span * 0.04),
                    b.get_y() + b.get_height() / 2, f"{v:+.0f}",
                    va="center", ha="left" if v >= 0 else "right",
                    fontsize=9, fontweight="bold", color="#262626")
        ax.axvline(0, color=C_GRAY, lw=0.6)
        ax.set_xlim(-span * 1.45, span * 1.45)
        ax.set_xlabel("万元", fontsize=9, color=C_LIGHT)
        ax.set_title(f"{title}\n{sub}", fontsize=11, color=C_PRIMARY,
                     fontweight="bold", pad=6)
        clean_ax(ax, ygrid=False, xgrid=True)
        fig.tight_layout()
        save(fig, fname)


def chart_p09():
    d = load_json("analysis2.json")["A_中兴康讯月度"]
    months = ["6月", "7月", "8月"]
    vals = [d[f"2026-0{m}"]["利润万"] for m in ["6", "7", "8"]]
    fig, ax = plt.subplots(figsize=(5.5, 3.9))
    bars = ax.bar(months, vals, color=C_NEG, width=0.45)
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v - 2, f"{v:.0f}",
                ha="center", va="top", fontsize=10.5, fontweight="bold",
                color="#262626")
    ax.axhline(0, color=C_GRAY, lw=0.6)
    ax.set_ylim(min(vals) * 1.35, 8)
    ax.set_ylabel("万元", fontsize=9.5, color=C_LIGHT)
    ax.set_title("中兴康讯：6-8月连亏且逐月扩大", fontsize=11.5,
                 color=C_PRIMARY, fontweight="bold", pad=8)
    clean_ax(ax)
    fig.tight_layout()
    save(fig, "p09_zte_trend.png")


def chart_p10():
    rows = load_json("report_data.json")["cost_up"]
    labels, vals = [], []
    for r in rows:
        labels.append(r[0].replace("DCDC-18V-降压2~4A", "DCDC-18V")
                      .replace("车规有刷多路栅驱", "车规栅驱"))
        vals.append(r[2])
    labels.append("STI3452HFI")
    vals.append(6.1)
    order = np.argsort(vals)
    labels = [labels[i] for i in order]
    vals = [vals[i] for i in order]
    colors = [C_NEG if v < 0 else C_POSITIVE for v in vals]
    fig, ax = plt.subplots(figsize=(5.5, 3.9))
    bars = ax.barh(labels, vals, color=colors, height=0.5)
    span = max(abs(v) for v in vals)
    for b, v in zip(bars, vals):
        ax.text(v + (span * 0.04 if v >= 0 else -span * 0.04),
                b.get_y() + b.get_height() / 2, f"{v:+.0f}",
                va="center", ha="left" if v >= 0 else "right",
                fontsize=9.5, fontweight="bold", color="#262626")
    if "DCDC-18V" in labels:
        i = labels.index("DCDC-18V")
        ax.text(-span * 0.98, i, "7月为-58万，减亏中", fontsize=8.5,
                va="center", ha="left", color=C_LIGHT)
    ax.axvline(0, color=C_GRAY, lw=0.6)
    ax.set_xlim(-span * 1.6, span * 1.6)
    ax.set_xlabel("环比成本效应（万元，正=成本下降增利）", fontsize=9,
                  color=C_LIGHT)
    ax.set_title("成本效应：压力品类换防，STI3452HFI转正", fontsize=11.5,
                 color=C_PRIMARY, fontweight="bold", pad=8)
    clean_ax(ax, ygrid=False, xgrid=True)
    fig.tight_layout()
    save(fig, "p10_cost_shift.png")


def chart_p11():
    s = load_json("analysis3.json")["A_音频功放月度"]
    months = [k.replace("2025-", "25/").replace("2026-", "26/") for k in s]
    vals = [v["毛利率"] * 100 for v in s.values()]
    fig, ax = plt.subplots(figsize=(5.5, 3.9))
    ax.plot(range(len(months)), vals, color=C_ACCENT, lw=2.2, marker="o",
            markersize=3.5)
    ax.fill_between(range(len(months)), vals, alpha=0.12, color=C_ACCENT)
    idx_jan, idx_aug = months.index("26/01"), months.index("26/08")
    ax.annotate(f"{vals[idx_jan]:.1f}%", xy=(idx_jan, vals[idx_jan]),
                xytext=(idx_jan, vals[idx_jan] + 5), fontsize=10,
                color=C_PRIMARY, fontweight="bold",
                arrowprops=dict(arrowstyle="->", color=C_PRIMARY, lw=0.8))
    ax.annotate(f"{vals[idx_aug]:.1f}%", xy=(idx_aug, vals[idx_aug]),
                xytext=(idx_aug - 1, vals[idx_aug] + 6), fontsize=10,
                color=C_NEG, fontweight="bold",
                arrowprops=dict(arrowstyle="->", color=C_NEG, lw=0.8))
    ax.set_ylim(0, 50)
    ax.set_ylabel("毛利率%", fontsize=9.5, color=C_LIGHT)
    ticks = list(range(0, len(months), 3))
    ax.set_xticks(ticks)
    ax.set_xticklabels([months[i] for i in ticks], fontsize=9)
    ax.set_title("音频功放毛利率：1月40%→8月7.4%", fontsize=11.5,
                 color=C_PRIMARY, fontweight="bold", pad=8)
    clean_ax(ax)
    fig.tight_layout()
    save(fig, "p11_audio_cliff.png")


def chart_p12():
    rows = load_json("report_data.json")["dom_top"]
    labels = [r["name"] for r in rows]
    jan = [r["m_jan"] * 100 for r in rows]
    cur = [r["m_cur"] * 100 for r in rows]
    x = np.arange(len(labels))
    w = 0.36
    fig, ax = plt.subplots(figsize=(5.5, 3.9))
    b1 = ax.bar(x - w / 2, jan, w, label="1月毛利率", color=C_PRIMARY)
    b2 = ax.bar(x + w / 2, cur, w, label="8月毛利率", color=C_ACCENT)
    for bars in (b1, b2):
        for b in bars:
            h = b.get_height()
            ax.text(b.get_x() + b.get_width() / 2, h + 1.2, f"{h:.0f}",
                    ha="center", va="bottom", fontsize=9, color="#262626")
    ax.set_ylabel("毛利率%", fontsize=9.5, color=C_LIGHT)
    ax.set_title("应用领域毛利率（1月→8月）：网通收缩最大", fontsize=11.5,
                 color=C_PRIMARY, fontweight="bold", pad=8)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=9)
    ax.legend(fontsize=8.5, frameon=False, loc="upper right")
    ax.set_ylim(0, max(jan + cur) * 1.25)
    clean_ax(ax)
    fig.tight_layout()
    save(fig, "p12_domain.png")


def chart_p14():
    bands = load_json("report_data.json")["bands"][:-1]
    labels = [b[0] for b in bands]
    sku_counts = [b[1] for b in bands]
    margins = [b[3] * 100 for b in bands]
    x = np.arange(len(labels))
    fig, ax1 = plt.subplots(figsize=(5.5, 3.9))
    bars = ax1.bar(x, sku_counts, color=C_CYAN, width=0.5, label="SKU数")
    for b in bars:
        ax1.text(b.get_x() + b.get_width() / 2, b.get_height() + 1.5,
                 f"{int(b.get_height())}", ha="center", va="bottom",
                 fontsize=10, color="#262626", fontweight="bold")
    ax1.set_ylabel("SKU数（个）", fontsize=9.5, color=C_CYAN)
    ax1.set_ylim(0, max(sku_counts) * 1.3)
    ax1.tick_params(axis="y", labelsize=9, colors=C_CYAN)
    ax2 = ax1.twinx()
    ax2.plot(x, margins, color=C_ACCENT, lw=2, marker="o", label="档内毛利率")
    ax2.set_ylabel("档内毛利率%", fontsize=9.5, color=C_ACCENT)
    ax2.set_ylim(0, max(margins) * 1.3)
    ax2.tick_params(axis="y", labelsize=9, colors=C_ACCENT)
    ax2.spines["top"].set_visible(False)
    ax1.set_xticks(x)
    ax1.set_xticklabels(labels, fontsize=8.5)
    h1, l1 = ax1.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax1.legend(h1 + h2, l1 + l2, fontsize=8.5, frameon=False,
               loc="upper center", ncol=2)
    ax1.set_title("新品SKU毛利分档：占比19.8%，仅10个负毛利", fontsize=11.5,
                  color=C_PRIMARY, fontweight="bold", pad=8)
    clean_ax(ax1)
    fig.tight_layout()
    save(fig, "p14_new.png")


def chart_p15():
    row = load_json("report_data.json")["sku_var"][0]
    # 列: [0标签,1客户数,2新增SKU,3流失SKU,4净增,5新增收入,6新增利润,7流失收入,8流失利润]
    groups = [("新增", row[5], C_POSITIVE, row[6]), ("流失", -row[7], C_NEG, -row[8])]
    labels = [g[0] for g in groups]
    rev = [g[1] for g in groups]
    pft = [g[3] for g in groups]
    x = np.arange(2)
    w = 0.32
    fig, ax = plt.subplots(figsize=(5.5, 3.9))
    b1 = ax.bar(x - w / 2, rev, w, label="收入(万)", color=[C_PRIMARY, C_LIGHT])
    b2 = ax.bar(x + w / 2, pft, w, label="利润(万)", color=[C_POSITIVE, C_NEG])
    for bars in (b1, b2):
        for b in bars:
            h = b.get_height()
            ax.text(b.get_x() + b.get_width() / 2,
                    h + (30 if h >= 0 else -30), f"{h:+.0f}",
                    ha="center", va="bottom" if h >= 0 else "top",
                    fontsize=9.5, fontweight="bold", color="#262626")
    ax.axhline(0, color=C_GRAY, lw=0.6)
    ax.set_xticks(x)
    ax.set_xticklabels(["新增SKU", "流失SKU"], fontsize=10)
    ax.set_ylabel("万元", fontsize=9.5, color=C_LIGHT)
    ax.legend(fontsize=8.5, frameon=False, loc="upper right")
    lo = min(min(pft), min(rev)) * 1.4
    hi = max(max(pft), max(rev)) * 1.25
    ax.set_ylim(lo, hi)
    ax.set_title("KA+AA进出账：净增85个SKU，净影响+762万", fontsize=11.5,
                 color=C_PRIMARY, fontweight="bold", pad=8)
    clean_ax(ax)
    fig.tight_layout()
    save(fig, "p15_sku_inout.png")


def chart_p16():
    fig, ax = plt.subplots(figsize=(2.8, 2.8))
    total, orange = 30, 12
    cols, rows = 6, 5
    for i in range(total):
        r, c = divmod(i, cols)
        color = C_ACCENT if i < orange else C_PRIMARY
        ax.scatter(c, rows - 1 - r, s=260, c=color, zorder=3,
                   edgecolors="white", linewidths=1.2)
    ax.set_xlim(-0.6, cols - 0.4)
    ax.set_ylim(-0.6, rows - 0.4)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title("PSE渗透：TOP30大客户\n12家未渗透", fontsize=11,
                 color=C_PRIMARY, fontweight="bold", pad=8)
    ax.text(2.5, -0.45, "橙=未渗透12  蓝=已渗透18", fontsize=8.5,
            ha="center", color=C_GRAY)
    fig.tight_layout()
    save(fig, "p16_pse_dots.png")


if __name__ == "__main__":
    chart_p04a()
    chart_p04b()
    chart_p06()
    chart_p07()
    chart_p08()
    chart_p09()
    chart_p10()
    chart_p11()
    chart_p12()
    chart_p14()
    chart_p15()
    chart_p16()
    print("\n全部14张图表生成完成 -> pptd/media/")
