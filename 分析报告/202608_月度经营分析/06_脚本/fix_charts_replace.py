# -*- coding: utf-8 -*-
r"""图表修复v2: 去掉灰色小标题(与主标题重叠) + 图1折线标签白底衬 + 重插入docx"""
import json
import os
import time
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pythoncom
import pywintypes
import win32com.client as win32

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei"]
plt.rcParams["axes.unicode_minus"] = False

OUT = r"C:\Users\910373\AppData\Local\Temp\opencode\build\chartsA2"
os.makedirs(OUT, exist_ok=True)
DST = r"E:\3-其他资料\数据分析\2026年8月销售经营分析报告(定稿).docx"
AN = json.load(open(r"C:\Users\910373\AppData\Local\Temp\opencode\build\analysis2.json", encoding="utf-8"))

C_TOT, C_POS, C_NEG, C_SEC = "#1F4E79", "#4472C4", "#B44A3C", "#8496A8"
TXT, GRID = "#1F1F1F", "#D9D9D9"

def base_ax(ax, ygrid=True):
    ax.set_axisbelow(True)
    if ygrid:
        ax.grid(axis="y", color=GRID, linewidth=0.8)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color("#BFBFBF")
    ax.tick_params(colors="#404040", labelsize=10)

def title(ax, main):
    ax.set_title(main, fontsize=14, color=TXT, fontweight="bold", loc="left", pad=12)

def waterfall(fname, labels, values, totals, main):
    fig, ax = plt.subplots(figsize=(11, 5.4), dpi=110)
    base_ax(ax)
    cum = 0.0
    bottoms, heights, colors = [], [], []
    for v, t in zip(values, totals):
        if t:
            bottoms.append(0); heights.append(v); cum = v
        else:
            if v >= 0:
                bottoms.append(cum); heights.append(v); cum += v
            else:
                cum += v; bottoms.append(cum); heights.append(-v)
        colors.append(C_TOT if t else (C_POS if v >= 0 else C_NEG))
    xs = range(len(labels))
    ax.bar(xs, heights, bottom=bottoms, color=colors, width=0.62)
    prev = None
    for i, (v, t) in enumerate(zip(values, totals)):
        top = v if t else (bottoms[i] + heights[i] if v >= 0 else bottoms[i])
        if prev is not None:
            ax.plot([i - 1 + 0.31, i - 0.31], [prev, prev], color="#BFBFBF", linewidth=0.9)
        prev = top
    ymax = max(b + h for b, h in zip(bottoms, heights))
    for i, (b, h, v, t) in enumerate(zip(bottoms, heights, values, totals)):
        ax.text(i, b + h + ymax * 0.025, (f"{v:,}" if t else f"{v:+,}"), ha="center", va="bottom",
                fontsize=10.5, color=TXT, fontweight="bold" if t else "normal")
    ax.set_xticks(list(xs)); ax.set_xticklabels(labels, fontsize=10.5)
    ax.set_ylim(0, ymax * 1.12); ax.set_yticks([])
    title(ax, main)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, fname), facecolor="white", bbox_inches="tight")
    plt.close(fig)

def chart1():
    m = [f"{i}月" for i in range(1, 9)]
    rev = [8615, 5257, 6375, 8536, 6928, 7369, 7760, 6903]
    mg = [34.94, 33.22, 34.88, 34.77, 34.80, 32.63, 30.25, 30.68]
    fig, ax = plt.subplots(figsize=(11, 5.4), dpi=110)
    base_ax(ax)
    bars = ax.bar(m, rev, color=C_TOT, width=0.58, label="收入(万元)")
    for b, v in zip(bars, rev):
        ax.text(b.get_x() + b.get_width() / 2, v + 130, f"{v:,}", ha="center", fontsize=9.5, color=TXT)
    ax.set_ylim(0, 10200)
    ax.set_yticks([])
    ax2 = ax.twinx()
    ax2.plot(m, mg, color=C_NEG, marker="o", markersize=5.5, linewidth=2, label="毛利率(%)", zorder=5)
    for x, v in zip(m, mg):
        ax2.annotate(f"{v:.2f}", (x, v), textcoords="offset points", xytext=(0, 10),
                     ha="center", fontsize=9.5, color=C_NEG, fontweight="bold", zorder=6,
                     bbox=dict(boxstyle="round,pad=0.18", facecolor="white", edgecolor="none", alpha=0.9))
    ax2.set_ylim(28, 40)
    ax2.set_yticks([])
    for s in ("top", "left", "right"):
        ax2.spines[s].set_visible(False)
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc="upper right", frameon=False, fontsize=10)
    title(ax, "2026年月度收入与毛利率走势(1-8月)")
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "fig1.png"), facecolor="white", bbox_inches="tight")
    plt.close(fig)

chart1()
waterfall("fig2.png", ["去年8月可比毛利", "量效应", "价效应", "成本效应", "结构效应", "今年8月可比毛利"],
          [1989, 313, -470, -33, 70, 1868], [True, False, False, False, False, True],
          "8月同比毛利桥:可比毛利 1,989万 → 1,868万(万元)")
waterfall("fig3.png", ["7月可比毛利", "量效应", "价效应", "成本效应", "结构效应", "8月可比毛利"],
          [2274, -461, 62, 8, 171, 2054], [True, False, False, False, False, True],
          "8月环比毛利桥:可比毛利 2,274万 → 2,054万(万元)")

def chart4():
    ser = AN["D_四因子长周期"]
    months = [s["月"] for s in ser]
    q = [s["量"] for s in ser]
    st = [s["结构"] for s in ser]
    p_ = [s["价"] for s in ser]
    c = [s["成本"] for s in ser]
    fig, ax = plt.subplots(figsize=(12.5, 5.6), dpi=110)
    base_ax(ax)
    ax.axhline(0, color="#BFBFBF", linewidth=1)
    ax.plot(months, q, color=C_TOT, linewidth=2, label="量效应")
    ax.plot(months, st, color=C_POS, linewidth=1.8, label="结构效应")
    ax.plot(months, p_, color=C_NEG, linewidth=1.8, label="价效应")
    ax.plot(months, c, color=C_SEC, linewidth=1.6, linestyle="--", label="成本效应")
    for tgt in ("2025-02", "2026-08"):
        if tgt in months:
            i = months.index(tgt)
            ax.axvspan(i - 0.35, i + 0.35, color="#EAF0F6", zorder=0)
    ax.set_xticks(range(len(months)))
    ax.set_xticklabels(months, rotation=45, fontsize=8, ha="right")
    ax.legend(loc="upper right", frameon=False, fontsize=10, ncol=4)
    ax.set_ylabel("万元", fontsize=10, color="#404040")
    title(ax, "毛利桥四因子月度序列(2024年2月-2026年8月,阴影=价结构双正月)")
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "fig4.png"), facecolor="white", bbox_inches="tight")
    plt.close(fig)

chart4()

def chart5():
    data = [("追觅", -505), ("中兴康讯", -333), ("小米集团", -222), ("长虹集团", -64), ("海信集团", -38),
            ("创维数字", 82), ("TPLINK", 84), ("大华集团", 87), ("海康威视", 323), ("石头", 331)][::-1]
    names = [d[0] for d in data]
    vals = [d[1] for d in data]
    fig, ax = plt.subplots(figsize=(10.5, 6), dpi=110)
    base_ax(ax, ygrid=False)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.axvline(0, color="#BFBFBF", linewidth=1)
    bars = ax.barh(names, vals, color=[C_NEG if v < 0 else C_POS for v in vals], height=0.62)
    span = max(vals) - min(vals)
    for b, v in zip(bars, vals):
        ax.text(v + (span * 0.012 if v >= 0 else -span * 0.012), b.get_y() + b.get_height() / 2,
                f"{v:+,}", va="center", ha="left" if v >= 0 else "right", fontsize=10, color=TXT)
    ax.set_xlim(min(vals) - span * 0.14, max(vals) + span * 0.14)
    ax.set_xticks([])
    title(ax, "KA客户利润同比变化TOP(1-8月,万元)")
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "fig5.png"), facecolor="white", bbox_inches="tight")
    plt.close(fig)

chart5()

def chart6():
    data = [("DCDC-5V-降压1~3A", -303), ("DCDC-18V-降压2~4A", -263), ("POE-PD协议及隔离DC-DC", -162),
            ("USB单通道/多通道", -82), ("车规H桥驱动-中小功率", -61),
            ("车规有刷多路栅驱", 52), ("DCDC-30V/40V降压", 53), ("PSE", 88)][::-1]
    names = [d[0] for d in data]
    vals = [d[1] for d in data]
    fig, ax = plt.subplots(figsize=(10.5, 6), dpi=110)
    base_ax(ax, ygrid=False)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.axvline(0, color="#BFBFBF", linewidth=1)
    bars = ax.barh(names, vals, color=[C_NEG if v < 0 else C_POS for v in vals], height=0.6)
    span = max(vals) - min(vals)
    for b, v in zip(bars, vals):
        ax.text(v + (span * 0.012 if v >= 0 else -span * 0.012), b.get_y() + b.get_height() / 2,
                f"{v:+,}", va="center", ha="left" if v >= 0 else "right", fontsize=10, color=TXT)
    ax.set_xlim(min(vals) - span * 0.15, max(vals) + span * 0.15)
    ax.set_xticks([])
    title(ax, "量效应解剖:8月vs7月品类收入环比变动(万元,全口径)")
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "fig6.png"), facecolor="white", bbox_inches="tight")
    plt.close(fig)

chart6()
print("CHARTS_FIXED")

# ---- 替换docx中的6张图 ----
def with_retry(fn, *a, **k):
    last = None
    for i in range(12):
        try:
            return fn(*a, **k)
        except pywintypes.com_error as e:
            if e.hresult in (-2147418111, -2147417846) and i < 11:
                last = e
                time.sleep(1.5)
                continue
            raise
    raise last

LOG = []
pythoncom.CoInitialize()
word = None
try:
    word = win32.DispatchEx("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0
    doc = with_retry(lambda: word.Documents.Open(DST))
    n = with_retry(lambda: doc.InlineShapes.Count)
    LOG.append(f"images before: {n}")
    for k in range(n, 0, -1):
        shp = with_retry(lambda: doc.InlineShapes(k))
        start = with_retry(lambda: shp.Range.Start)
        with_retry(lambda: shp.Delete())
        rng = with_retry(lambda: doc.Range(start, start))
        pic = with_retry(lambda: doc.InlineShapes.AddPicture(os.path.join(OUT, f"fig{k}.png"), False, True, rng.Duplicate))
        with_retry(lambda: pic.__setattr__("Width", 440))
        LOG.append(f"replaced fig{k}")
    n2 = with_retry(lambda: doc.InlineShapes.Count)
    with_retry(lambda: doc.Save())
    with_retry(lambda: doc.Close(False))
    LOG.append(f"images after: {n2}")
finally:
    if word is not None:
        try:
            word.Quit()
        except Exception:
            pass
    pythoncom.CoUninitialize()
open(r"C:\Users\910373\AppData\Local\Temp\opencode\build\replace_log.txt", "w", encoding="utf-8").write("\n".join(str(x) for x in LOG))
print("REPLACE_DONE")
