# -*- coding: utf-8 -*-
r"""全套6张图表(A深蓝商务风) + 插入定稿docx替换占位符"""
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

OUT = r"C:\Users\910373\AppData\Local\Temp\opencode\build\chartsA"
os.makedirs(OUT, exist_ok=True)
DST = r"E:\3-其他资料\数据分析\2026年8月销售经营分析报告(定稿).docx"
AN = json.load(open(r"C:\Users\910373\AppData\Local\Temp\opencode\build\analysis2.json", encoding="utf-8"))

# ---- 风格A ----
C_TOT, C_POS, C_NEG, C_SEC = "#1F4E79", "#4472C4", "#B44A3C", "#8496A8"
TXT, SUB, GRID = "#1F1F1F", "#7F7F7F", "#D9D9D9"

def base_ax(ax, ygrid=True):
    ax.set_axisbelow(True)
    if ygrid:
        ax.grid(axis="y", color=GRID, linewidth=0.8)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color("#BFBFBF")
    ax.tick_params(colors="#404040", labelsize=10)

def title(ax, main, sub):
    ax.set_title(main, fontsize=14, color=TXT, fontweight="bold", loc="left", pad=22)
    ax.text(0, 1.045, sub, transform=ax.transAxes, fontsize=9.5, color=SUB)

def waterfall(fname, labels, values, totals, main, sub):
    fig, ax = plt.subplots(figsize=(11, 5.6), dpi=110)
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
    ax.set_ylim(0, ymax * 1.14); ax.set_yticks([])
    title(ax, main, sub)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, fname), facecolor="white", bbox_inches="tight")
    plt.close(fig)

# 图1 月度趋势双轴
def chart1():
    m = [f"{i}月" for i in range(1, 9)]
    rev = [8615, 5257, 6375, 8536, 6928, 7369, 7760, 6903]
    mg = [34.94, 33.22, 34.88, 34.77, 34.80, 32.63, 30.25, 30.68]
    fig, ax = plt.subplots(figsize=(11, 5.6), dpi=110)
    base_ax(ax)
    bars = ax.bar(m, rev, color=C_TOT, width=0.58, label="收入(万元)")
    for b, v in zip(bars, rev):
        ax.text(b.get_x() + b.get_width() / 2, v + 130, f"{v:,}", ha="center", fontsize=9.5, color=TXT)
    ax.set_ylim(0, 10200)
    ax.set_yticks([])
    ax2 = ax.twinx()
    ax2.plot(m, mg, color=C_NEG, marker="o", markersize=5.5, linewidth=2, label="毛利率(%)")
    for x, v in zip(m, mg):
        ax2.annotate(f"{v:.2f}", (x, v), textcoords="offset points", xytext=(0, 9),
                     ha="center", fontsize=9.5, color=C_NEG)
    ax2.set_ylim(28, 40)
    ax2.set_yticks([])
    for s in ("top", "left", "right"):
        ax2.spines[s].set_visible(False)
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc="upper right", frameon=False, fontsize=10)
    title(ax, "2026年月度收入与毛利率走势(1-8月)", "8月收入环比-11.0%年内首次回落,毛利率30.68%企稳回升 | 数据底表:R-报告补充R2")
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "fig1.png"), facecolor="white", bbox_inches="tight")
    plt.close(fig)

# 图2/图3 瀑布
chart1()
waterfall("fig2.png", ["去年8月可比毛利", "量效应", "价效应", "成本效应", "结构效应", "今年8月可比毛利"],
          [1989, 313, -470, -33, 70, 1868], [True, False, False, False, False, True],
          "8月同比毛利桥:可比毛利 1,989万 → 1,868万(万元)", "同比394个可比SKU,覆盖8月收入89%,价效应-470万为最大拖累 | 数据底表:R-报告补充R1")
waterfall("fig3.png", ["7月可比毛利", "量效应", "价效应", "成本效应", "结构效应", "8月可比毛利"],
          [2274, -461, 62, 8, 171, 2054], [True, False, False, False, False, True],
          "8月环比毛利桥:可比毛利 2,274万 → 2,054万(万元)", "环比444个可比SKU,覆盖96%,量效应-461万为唯一负贡献 | 数据底表:R-报告补充R1")

# 图4 四因子长周期
def chart4():
    ser = AN["D_四因子长周期"]
    months = [s["月"] for s in ser]
    q = [s["量"] for s in ser]
    st = [s["结构"] for s in ser]
    p = [s["价"] for s in ser]
    c = [s["成本"] for s in ser]
    fig, ax = plt.subplots(figsize=(12.5, 5.8), dpi=110)
    base_ax(ax)
    ax.axhline(0, color="#BFBFBF", linewidth=1)
    ax.plot(months, q, color=C_TOT, linewidth=2, label="量效应")
    ax.plot(months, st, color=C_POS, linewidth=1.8, label="结构效应")
    ax.plot(months, p, color=C_NEG, linewidth=1.8, label="价效应")
    ax.plot(months, c, color=C_SEC, linewidth=1.6, linestyle="--", label="成本效应")
    for tgt, note in (("2025-02", "价结构双正"), ("2026-08", "价结构双正")):
        if tgt in months:
            i = months.index(tgt)
            ax.axvspan(i - 0.35, i + 0.35, color="#EAF0F6", zorder=0)
            ax.annotate(note, (i, max(q[i], st[i], p[i], c[i]) + 120), ha="center",
                        fontsize=9, color=C_TOT,
                        xytext=(0, 14), textcoords="offset points")
    ax.set_xticks(range(len(months)))
    ax.set_xticklabels(months, rotation=45, fontsize=8, ha="right")
    ax.legend(loc="upper right", frameon=False, fontsize=10, ncol=4)
    ax.set_ylabel("万元", fontsize=10, color="#404040")
    title(ax, "毛利桥四因子月度序列(2024年2月-2026年8月,31个月)",
          "价效应31个月仅5次为正;阴影为两个'价结构双正'月(2025-02/2026-08) | 数据底表:R-报告补充R9")
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "fig4.png"), facecolor="white", bbox_inches="tight")
    plt.close(fig)

chart4()

# 图5 KA利润TOP 发散条形
def chart5():
    data = [("追觅", -505), ("中兴康讯", -333), ("小米集团", -222), ("长虹集团", -64), ("海信集团", -38),
            ("创维数字", 82), ("TPLINK", 84), ("大华集团", 87), ("海康威视", 323), ("石头", 331)]
    data = data[::-1]
    names = [d[0] for d in data]
    vals = [d[1] for d in data]
    fig, ax = plt.subplots(figsize=(10.5, 6), dpi=110)
    base_ax(ax, ygrid=False)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.axvline(0, color="#BFBFBF", linewidth=1)
    colors = [C_NEG if v < 0 else C_POS for v in vals]
    bars = ax.barh(names, vals, color=colors, height=0.62)
    span = max(vals) - min(vals)
    for b, v in zip(bars, vals):
        ax.text(v + (span * 0.012 if v >= 0 else -span * 0.012), b.get_y() + b.get_height() / 2,
                f"{v:+,}", va="center", ha="left" if v >= 0 else "right", fontsize=10, color=TXT)
    ax.set_xlim(min(vals) - span * 0.14, max(vals) + span * 0.14)
    ax.set_xticks([])
    title(ax, "KA客户利润同比变化TOP(1-8月,万元)",
          "拖累:追觅/中兴康讯/小米;对冲:石头/海康/大华 | 数据底表:R-报告补充R5")
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "fig5.png"), facecolor="white", bbox_inches="tight")
    plt.close(fig)

chart5()

# 图6 量效应解剖 品类条形
def chart6():
    data = [("DCDC-5V-降压1~3A", -303), ("DCDC-18V-降压2~4A", -263), ("POE-PD协议及隔离DC-DC", -162),
            ("USB单通道/多通道", -82), ("车规H桥驱动-中小功率", -61),
            ("车规有刷多路栅驱", 52), ("DCDC-30V/40V降压", 53), ("PSE", 88)]
    data = data[::-1]
    names = [d[0] for d in data]
    vals = [d[1] for d in data]
    fig, ax = plt.subplots(figsize=(10.5, 6), dpi=110)
    base_ax(ax, ygrid=False)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.axvline(0, color="#BFBFBF", linewidth=1)
    colors = [C_NEG if v < 0 else C_POS for v in vals]
    bars = ax.barh(names, vals, color=colors, height=0.6)
    span = max(vals) - min(vals)
    for b, v in zip(bars, vals):
        ax.text(v + (span * 0.012 if v >= 0 else -span * 0.012), b.get_y() + b.get_height() / 2,
                f"{v:+,}", va="center", ha="left" if v >= 0 else "right", fontsize=10, color=TXT)
    ax.set_xlim(min(vals) - span * 0.15, max(vals) + span * 0.15)
    ax.set_xticks([])
    title(ax, "量效应解剖:8月vs7月品类收入环比变动(万元,全口径)",
          "降幅集中DCDC-5V/18V与POE-PD协议脉冲消退;PSE/30V·40V逆势放量 | 数据底表:R-报告补充R10")
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "fig6.png"), facecolor="white", bbox_inches="tight")
    plt.close(fig)

chart6()
print("CHARTS_A_DONE")

# ---- 插入Word ----
CAPS = {
    1: ("fig1.png", "图1 2026年月度收入与毛利率走势(数据底表:R-报告补充R2)"),
    2: ("fig2.png", "图2 8月同比毛利桥瀑布(数据底表:R-报告补充R1)"),
    3: ("fig3.png", "图3 8月环比毛利桥瀑布(数据底表:R-报告补充R1)"),
    4: ("fig4.png", "图4 毛利桥四因子月度序列,2024-02至2026-08(数据底表:R-报告补充R9)"),
    5: ("fig5.png", "图5 KA客户利润同比变化TOP(数据底表:R-报告补充R5)"),
    6: ("fig6.png", "图6 量效应解剖:品类收入环比变动(数据底表:R-报告补充R10)"),
}

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
    done = set()
    for _pass in range(6):
        np_ = with_retry(lambda: doc.Paragraphs.Count)
        hit = None
        for i in range(1, np_ + 1):
            p = with_retry(lambda: doc.Paragraphs(i))
            t = with_retry(lambda: p.Range.Text).replace("\r", "").replace("\x07", "").strip()
            if t.startswith("【图") and t not in done:
                hit = (i, p, t)
                break
        if not hit:
            break
        i, p, t = hit
        no = int(t[2])
        fname, cap = CAPS[no]
        rng = p.Range
        with_retry(lambda: rng.__setattr__("Text", cap + "\r"))
        capr = with_retry(lambda: doc.Paragraphs(i).Range)
        with_retry(lambda: capr.Font.__setattr__("Size", 9))
        with_retry(lambda: capr.Font.__setattr__("NameFarEast", "宋体"))
        with_retry(lambda: capr.Font.__setattr__("Color", 4210752))
        with_retry(lambda: capr.ParagraphFormat.__setattr__("Alignment", 1))
        startr = with_retry(lambda: doc.Paragraphs(i).Range)
        with_retry(lambda: startr.Collapse(1))
        pic = with_retry(lambda: doc.InlineShapes.AddPicture(os.path.join(OUT, fname), False, True, startr.Duplicate))
        with_retry(lambda: pic.__setattr__("Width", 440))
        # 图片与图注之间换行
        with_retry(lambda: pic.Range.InsertAfter("\r") if False else None) if False else None
        done.add(t)
        LOG.append(f"inserted 图{no}")
    nimg = with_retry(lambda: doc.InlineShapes.Count)
    nrev = with_retry(lambda: doc.Revisions.Count)
    with_retry(lambda: doc.Save())
    with_retry(lambda: doc.Close(False))
    LOG.append(f"[DONE] images={nimg} revisions={nrev} inserted={len(done)}")
finally:
    if word is not None:
        try:
            word.Quit()
        except Exception:
            pass
    pythoncom.CoUninitialize()
open(r"C:\Users\910373\AppData\Local\Temp\opencode\build\insert_log.txt", "w", encoding="utf-8").write("\n".join(str(x) for x in LOG))
print("INSERT_DONE")
