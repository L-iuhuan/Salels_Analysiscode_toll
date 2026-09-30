# -*- coding: utf-8 -*-
r"""图表风格样张: 同一张环比毛利桥瀑布图 × 3种专业风格"""
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei"]
plt.rcParams["axes.unicode_minus"] = False

OUT = r"E:\3-其他资料\数据分析\图表样式样张"
os.makedirs(OUT, exist_ok=True)

labels = ["7月可比毛利", "量效应", "价效应", "成本效应", "结构效应", "8月可比毛利"]
values = [2274, -461, 62, 8, 171, 2054]
totals = [True, False, False, False, False, True]

def draw(style):
    fig, ax = plt.subplots(figsize=(11, 5.6), dpi=110)
    cum = 0.0
    bottoms, heights, colors = [], [], []
    for v, t in zip(values, totals):
        if t:
            bottoms.append(0); heights.append(v)
            cum = v
        else:
            if v >= 0:
                bottoms.append(cum); heights.append(v); cum += v
            else:
                cum += v; bottoms.append(cum); heights.append(-v)
        colors.append(None)
    if style == "A":  # 深蓝商务
        C_TOT, C_POS, C_NEG = "#1F4E79", "#4472C4", "#B44A3C"
        for i, (v, t) in enumerate(zip(values, totals)):
            colors[i] = C_TOT if t else (C_POS if v >= 0 else C_NEG)
        ax.set_axisbelow(True)
        ax.grid(axis="y", color="#D9D9D9", linewidth=0.8)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        for s in ("left", "bottom"):
            ax.spines[s].set_color("#BFBFBF")
        ax.tick_params(colors="#404040", labelsize=10)
        title_c, sub_c = "#1F1F1F", "#7F7F7F"
    elif style == "B":  # 经济学人风
        C_TOT, C_POS, C_NEG = "#5B6770", "#006BA2", "#DB444B"
        for i, (v, t) in enumerate(zip(values, totals)):
            colors[i] = C_TOT if t else (C_POS if v >= 0 else C_NEG)
        ax.set_axisbelow(True)
        ax.grid(axis="y", color="#DBDBDB", linewidth=0.7)
        for s in ("top", "right", "left"):
            ax.spines[s].set_visible(False)
        ax.spines["bottom"].set_color("#1A1A1A")
        ax.tick_params(colors="#1A1A1A", labelsize=10, length=0)
        ax.set_facecolor("#F6F6F4")
        fig.patch.set_facecolor("#F6F6F4")
        title_c, sub_c = "#1A1A1A", "#5B6770"
    else:  # C 黑白极简+橙强调
        C_TOT, C_POS, C_NEG = "#404040", "#9CA3AF", "#E8833A"
        for i, (v, t) in enumerate(zip(values, totals)):
            colors[i] = C_TOT if t else (C_NEG if v < 0 else C_POS)
        ax.grid(False)
        for s in ("top", "right", "left"):
            ax.spines[s].set_visible(False)
        ax.spines["bottom"].set_color("#D4D4D4")
        ax.tick_params(colors="#737373", labelsize=10, length=0)
        title_c, sub_c = "#171717", "#737373"

    xs = range(len(labels))
    ax.bar(xs, heights, bottom=bottoms, color=colors, width=0.62)
    # 连接线
    running = 0.0
    prev_top = None
    for i, (v, t) in enumerate(zip(values, totals)):
        if t:
            top = v
        else:
            top = bottoms[i] + heights[i] if v >= 0 else bottoms[i]
        if prev_top is not None:
            ax.plot([i - 1 + 0.31, i - 0.31], [prev_top, prev_top], color="#BFBFBF", linewidth=0.9, linestyle="-")
        prev_top = top
    # 数据标签
    ymax = max(b + h for b, h in zip(bottoms, heights))
    for i, (b, h, v) in enumerate(zip(bottoms, heights, values)):
        ax.text(i, b + h + ymax * 0.025, f"{v:+,}" if not totals[i] else f"{v:,}",
                ha="center", va="bottom", fontsize=10.5,
                color="#1F1F1F" if style != "C" else "#171717",
                fontweight="bold" if totals[i] else "normal")
    ax.set_xticks(list(xs))
    ax.set_xticklabels(labels, fontsize=10.5)
    ax.set_ylim(0, ymax * 1.14)
    ax.set_yticks([])
    t = ax.set_title("8月环比毛利桥:可比毛利 2,274万 → 2,054万(万元)", fontsize=14, color=title_c,
                     fontweight="bold", loc="left", pad=30 if style == "B" else 22)
    ax.text(0, 1.045, "可比444个SKU,覆盖8月收入96% | 数据底表:R-报告补充R1",
            transform=ax.transAxes, fontsize=9.5, color=sub_c)
    if style == "B":
        ax.add_patch(plt.Rectangle((0, 1.10), 0.055, 0.055, transform=ax.transAxes, color="#E3120B", clip_on=False))
    fig.tight_layout()
    fn = os.path.join(OUT, f"样式{style}_{'深蓝商务' if style == 'A' else '经济学人风' if style == 'B' else '黑白极简橙强调'}.png")
    fig.savefig(fn, facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)
    return fn

files = [draw(s) for s in ("A", "B", "C")]
open(os.path.join(OUT, "说明.txt"), "w", encoding="utf-8").write(
    "三套图表风格样张(同一张环比毛利桥数据):\n"
    "A 深蓝商务.png —— 咨询报告风:深蓝主色+蓝正红负,浅灰横向网格,全套六图统一用色\n"
    "B 经济学人风.png —— 红色标记+浅灰底,无边框,正蓝负红,杂志质感\n"
    "C 黑白极简橙强调.png —— 炭灰主色+橙色仅标负值/风险项,无网格无Y轴,最简\n\n"
    "选定后所有6张图(月度趋势/同比瀑布/环比瀑布/四因子长周期/KA利润TOP/量效应解剖)将统一按该风格制作。")
for f in files:
    print("OK", f)
print("SAMPLES_DONE")
