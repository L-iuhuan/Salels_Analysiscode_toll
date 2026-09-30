# -*- coding: utf-8 -*-
"""charts_aug.py - 生成8月经营分析PPT所需的12张数据图."""
import sys, os, json
sys.stdout.reconfigure(encoding='utf-8')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(os.path.dirname(BASE), '05_过程数据')
CHARTS_DIR = os.path.join(BASE, 'charts')
os.makedirs(CHARTS_DIR, exist_ok=True)

# === 配色契约 ===
C_MAIN = '#00437C'
C_ORANGE = '#F18101'
C_GREEN = '#8FC31F'
C_CYAN = '#00A0E9'
C_TEAL = '#01ADA1'
C_NEG = '#C0504D'
C_GRAY = '#7F7F7F'
C_BG = '#F2F5F9'

FONT = 'HarmonyOS Sans SC'

def set_font():
    from matplotlib import rcParams
    rcParams['font.sans-serif'] = [FONT, 'Microsoft YaHei', 'SimHei']
    rcParams['axes.unicode_minus'] = False

set_font()


def load_json(name):
    """从05_过程数据读取json."""
    with open(os.path.join(DATA_DIR, name), encoding='utf-8') as f:
        return json.load(f)


def save(fig, name, dpi=150):
    path = os.path.join(CHARTS_DIR, name)
    fig.savefig(path, dpi=dpi, bbox_inches='tight', pad_inches=0.05)
    plt.close(fig)
    print(f'已生成 {name}')


def neg_color(v):
    return C_NEG if v < 0 else C_MAIN


def add_value_labels(ax, bars, fmt='{:.0f}', color='white', size=9):
    """在柱顶/底标数值，避免压叠."""
    for b in bars:
        h = b.get_height()
        y = b.get_y() + h
        va = 'bottom'
        if h < 0:
            y = b.get_y()
            va = 'top'
        ax.text(b.get_x() + b.get_width()/2, y, fmt.format(h),
                ha='center', va=va, fontsize=size, color=color, fontweight='bold')


def waterfall(ax, labels, values, title, unit='万元'):
    """绘制瀑布图：含连接线与合计柱."""
    n = len(labels)
    running = 0
    bottoms = []
    colors = []
    for i, v in enumerate(values):
        if i == n - 1:  # 合计柱
            bottoms.append(0)
            colors.append(C_ORANGE)
        else:
            bottoms.append(running)
            colors.append(C_MAIN if v >= 0 else C_NEG)
        running += v
    xs = np.arange(n)
    bars = ax.bar(xs, values, bottom=bottoms, color=colors, width=0.55, edgecolor='white')
    # 连接线
    running = 0
    for i in range(n - 1):
        if i > 0:
            ax.plot([i - 0.28, i + 0.28], [running, running], color=C_GRAY, lw=1, ls='--')
        running += values[i]
    # 数据标签
    for i, (b, v) in enumerate(zip(bars, values)):
        y = bottoms[i] + v
        va = 'bottom' if v >= 0 else 'top'
        ax.text(b.get_x() + b.get_width()/2, y, f'{v:+.0f}', ha='center', va=va,
                fontsize=10, color='white' if i == n-1 else 'black', fontweight='bold')
    ax.set_xticks(xs)
    ax.set_xticklabels(labels, fontsize=10)
    ax.set_ylabel(unit, fontsize=10)
    ax.set_title(title, fontsize=12, color=C_MAIN, fontweight='bold')
    ax.axhline(0, color=C_GRAY, lw=0.5)
    ax.grid(axis='y', linestyle='--', alpha=0.4)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.set_axisbelow(True)


def chart_p04_mom():
    # 来源：recompute.json 桥_环比_2026_08_vs_2026_07
    rec = load_json('recompute.json')
    b = rec['桥_环比_2026_08_vs_2026_07']
    labels = ['量效应', '结构效应', '价效应', '成本效应', '净变动']
    values = [b['量4'], b['结构4'], b['价'], b['成本'], b['dGP']]
    fig, ax = plt.subplots(figsize=(12.5, 6.3))
    waterfall(ax, labels, values, '毛利桥环比分解（8月 vs 7月）')
    save(fig, 'p04_waterfall_mom.png')


def chart_p04_yoy():
    # 来源：recompute.json 桥_同比_2026_08_vs_2025_08
    rec = load_json('recompute.json')
    b = rec['桥_同比_2026_08_vs_2025_08']
    labels = ['量效应', '结构效应', '价效应', '成本效应', '净变动']
    values = [b['量4'], b['结构4'], b['价'], b['成本'], b['dGP']]
    fig, ax = plt.subplots(figsize=(6, 4))
    waterfall(ax, labels, values, '毛利桥同比分解（8月 vs 去年8月）')
    save(fig, 'p04_waterfall_yoy.png')


def chart_p06_longcycle():
    # 来源：analysis2.json D_四因子长周期（31个月）
    data = load_json('analysis2.json')
    series = data['D_四因子长周期']
    months = [s['月'] for s in series]
    vol = [s['量'] for s in series]
    price = [s['价'] for s in series]
    margin = [s['毛利率'] * 100 for s in series]
    fig, ax1 = plt.subplots(figsize=(12.5, 6.3))
    x = np.arange(len(months))
    ax1.plot(x, vol, color=C_MAIN, lw=2, label='量效应（万元）')
    ax1.plot(x, price, color=C_ORANGE, lw=2, label='价效应（万元）')
    ax1.set_ylabel('万元', fontsize=10)
    ax1.set_xticks(x[::3])
    ax1.set_xticklabels(months[::3], fontsize=9, rotation=45)
    ax1.grid(axis='y', linestyle='--', alpha=0.4)
    ax1.legend(loc='upper left', fontsize=9)
    ax2 = ax1.twinx()
    ax2.plot(x, margin, color=C_GREEN, lw=2, linestyle='--', label='毛利率（%）')
    ax2.set_ylabel('毛利率 %', fontsize=10)
    ax2.legend(loc='upper right', fontsize=9)
    # 阴影标双正月（价>0 且 结构>0）
    for s in series:
        if s['价'] > 0 and s['结构'] > 0:
            idx = months.index(s['月'])
            ax1.axvspan(idx - 0.4, idx + 0.4, color=C_MAIN, alpha=0.12)
            ax1.text(idx, max(vol + price) * 0.92, s['月'], ha='center', fontsize=9,
                     color=C_MAIN, fontweight='bold')
    ax1.set_title('毛利桥长周期走势（31个月）', fontsize=13, color=C_MAIN, fontweight='bold')
    ax1.spines['top'].set_visible(False)
    fig.tight_layout()
    save(fig, 'p06_longcycle.png')


def chart_p07_ka_mm():
    # 来源：report_data.json cls KA/MM dpft
    data = load_json('report_data.json')
    cls = data['cls']
    labels = ['KA', 'MM']
    vals = [round(cls['KA']['dpft'] / 10000, 1), round(cls['MM']['dpft'] / 10000, 1)]
    colors = [C_NEG, C_GREEN]
    fig, ax = plt.subplots(figsize=(6, 4))
    bars = ax.barh(labels, vals, color=colors, height=0.5)
    for b, v in zip(bars, vals):
        ax.text(v, b.get_y() + b.get_height()/2, f'{v:+.0f}万',
                va='center', ha='left' if v >= 0 else 'right', fontsize=11,
                color='black', fontweight='bold')
    ax.set_xlabel('利润同比增量（万元）', fontsize=10)
    ax.set_title('客户分群利润增量贡献', fontsize=12, color=C_MAIN, fontweight='bold')
    ax.axvline(0, color=C_GRAY, lw=0.5)
    ax.grid(axis='x', linestyle='--', alpha=0.4)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    fig.tight_layout()
    save(fig, 'p07_ka_mm.png')


def chart_p08_hedge():
    # 来源：analysis2.json C_同类对冲矩阵
    data = load_json('analysis2.json')
    mat = data['C_同类对冲矩阵']
    fig, axes = plt.subplots(1, 3, figsize=(12.5, 6.3), sharex=True)
    groups = [
        ('H桥BDC·客户间转移', [('追觅', 'H桥BDC-高压36V以上<3A'),
                               ('小米集团', 'H桥BDC-高压36V以上<3A'),
                               ('石头', 'H桥BDC-高压36V以上<3A')]),
        ('DCDC-18V·五客户全负', [('中兴康讯', 'DCDC-18V-降压2~4A'),
                                ('TPLINK', 'DCDC-18V-降压2~4A'),
                                ('共进', 'DCDC-18V-降压2~4A'),
                                ('兆驰', 'DCDC-18V-降压2~4A'),
                                ('创维数字', 'DCDC-18V-降压2~4A')]),
        ('PSE·全线共振', [('海康威视', 'PSE'), ('大华集团', 'PSE'), ('中兴康讯', 'PSE')]),
    ]
    for ax, (title, pairs) in zip(axes, groups):
        labels = []
        vals = []
        for cust, cat in pairs:
            found = [r for r in mat[cust] if r['品类'] == cat]
            v = found[0]['增量'] if found else 0
            labels.append(cust.replace('集团', ''))
            vals.append(v)
        colors = [C_GREEN if v >= 0 else C_NEG for v in vals]
        bars = ax.barh(labels, vals, color=colors, height=0.5)
        for b, v in zip(bars, vals):
            ax.text(v, b.get_y() + b.get_height()/2, f'{v:+.0f}',
                    va='center', ha='left' if v >= 0 else 'right', fontsize=9,
                    color='black', fontweight='bold')
        ax.set_title(title, fontsize=11, color=C_MAIN, fontweight='bold')
        ax.axvline(0, color=C_GRAY, lw=0.5)
        ax.set_xlabel('万元', fontsize=9)
        ax.grid(axis='x', linestyle='--', alpha=0.3)
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
    fig.tight_layout()
    save(fig, 'p08_hedge_matrix.png')


def chart_p09_zte():
    # 来源：analysis2.json A_中兴康讯月度
    data = load_json('analysis2.json')
    months = ['6月', '7月', '8月']
    vals = [data['A_中兴康讯月度'][f'2026-0{m}']['利润万'] for m in ['6', '7', '8']]
    fig, ax = plt.subplots(figsize=(6, 4))
    bars = ax.bar(months, vals, color=C_NEG, width=0.5)
    add_value_labels(ax, bars, fmt='{:.0f}', color='black', size=10)
    ax.set_ylabel('利润（万元）', fontsize=10)
    ax.set_title('中兴康讯月度利润连亏扩大', fontsize=12, color=C_MAIN, fontweight='bold')
    ax.axhline(0, color=C_GRAY, lw=0.5)
    ax.grid(axis='y', linestyle='--', alpha=0.4)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    fig.tight_layout()
    save(fig, 'p09_zte_trend.png')


def chart_p10_cost():
    # 来源：report_data.json cost_up + cost_sku.json STI3453FI
    data = load_json('report_data.json')
    rows = data['cost_up']
    labels = [r[0].replace('DCDC-18V-降压2~4A', 'DCDC-18V')
                  .replace('车规有刷多路栅驱', '车规有刷栅驱') for r in rows]
    vals = [r[2] for r in rows]
    fig, ax = plt.subplots(figsize=(6, 4))
    colors = [C_NEG if v < 0 else C_GREEN for v in vals]
    bars = ax.barh(labels, vals, color=colors, height=0.5)
    for b, v in zip(bars, vals):
        ax.text(v, b.get_y() + b.get_height()/2, f'{v:+.0f}万',
                va='center', ha='left' if v >= 0 else 'right', fontsize=10,
                color='black', fontweight='bold')
    ax.set_xlabel('成本效应（万元）', fontsize=10)
    ax.set_title('品类成本效应（8月 vs 7月）', fontsize=12, color=C_MAIN, fontweight='bold')
    ax.axvline(0, color=C_GRAY, lw=0.5)
    ax.grid(axis='x', linestyle='--', alpha=0.4)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    fig.tight_layout()
    save(fig, 'p10_cost_shift.png')


def chart_p11_audio():
    # 来源：analysis3.json A_音频功放月度
    data = load_json('analysis3.json')
    s = data['A_音频功放月度']
    months = [k.replace('2025-', '25/').replace('2026-', '26/') for k in s.keys()]
    vals = [v['毛利率'] * 100 for v in s.values()]
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.plot(months, vals, color=C_ORANGE, lw=2.5, marker='o', markersize=4)
    ax.fill_between(months, vals, alpha=0.15, color=C_ORANGE)
    ax.set_ylabel('毛利率 %', fontsize=10)
    ax.set_title('音频功放毛利率月度走势', fontsize=12, color=C_MAIN, fontweight='bold')
    ax.set_ylim(0, 50)
    ax.grid(axis='y', linestyle='--', alpha=0.4)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.set_xticks(months[::3])
    ax.set_xticklabels(months[::3], fontsize=9)
    # 标注 2026-01(40%) 与 2026-08(7.4%)
    idx_jan = months.index('26/01')
    idx_aug = months.index('26/08')
    ax.annotate(f'{vals[idx_jan]:.1f}%', xy=(idx_jan, vals[idx_jan]),
                xytext=(idx_jan, vals[idx_jan] + 4),
                fontsize=9, color=C_MAIN, fontweight='bold',
                arrowprops=dict(arrowstyle='->', color=C_MAIN, lw=0.8))
    ax.annotate(f'{vals[idx_aug]:.1f}%', xy=(idx_aug, vals[idx_aug]),
                xytext=(idx_aug, vals[idx_aug] + 4),
                fontsize=9, color=C_NEG, fontweight='bold',
                arrowprops=dict(arrowstyle='->', color=C_NEG, lw=0.8))
    fig.tight_layout()
    save(fig, 'p11_audio_cliff.png')


def chart_p12_domain():
    # 来源：report_data.json dom_top（m_jan/m_cur 视为领域毛利率）
    data = load_json('report_data.json')
    rows = data['dom_top']
    labels = [r['name'] for r in rows]
    jan = [r['m_jan'] * 100 for r in rows]
    cur = [r['m_cur'] * 100 for r in rows]
    x = np.arange(len(labels))
    width = 0.35
    fig, ax = plt.subplots(figsize=(6, 4))
    bars1 = ax.bar(x - width/2, jan, width, label='1月毛利率', color=C_MAIN)
    bars2 = ax.bar(x + width/2, cur, width, label='8月毛利率', color=C_ORANGE)
    for bars in (bars1, bars2):
        for b in bars:
            h = b.get_height()
            ax.text(b.get_x() + b.get_width()/2, h + 1, f'{h:.0f}%',
                    ha='center', va='bottom', fontsize=8, color='black')
    ax.set_ylabel('毛利率 %', fontsize=10)
    ax.set_title('应用领域毛利率变化', fontsize=12, color=C_MAIN, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=9)
    ax.legend(fontsize=9)
    ax.grid(axis='y', linestyle='--', alpha=0.4)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    fig.tight_layout()
    save(fig, 'p12_domain_stack.png')


def chart_p14_new():
    # 来源：report_data.json bands（新品SKU毛利分档）
    data = load_json('report_data.json')
    bands = data['bands'][:-1]  # 去掉合计
    labels = [b[0] for b in bands]
    sku_counts = [b[1] for b in bands]
    margins = [b[3] * 100 for b in bands]
    fig, ax1 = plt.subplots(figsize=(6, 4))
    x = np.arange(len(labels))
    bars = ax1.bar(x, sku_counts, color=C_CYAN, width=0.5, label='SKU数')
    ax1.set_ylabel('SKU数', fontsize=10)
    ax1.set_xticks(x)
    ax1.set_xticklabels(labels, fontsize=8, rotation=15)
    ax2 = ax1.twinx()
    ax2.plot(x, margins, color=C_ORANGE, lw=2, marker='o', label='档内毛利率')
    ax2.set_ylabel('档内毛利率 %', fontsize=10)
    for b in bars:
        ax1.text(b.get_x() + b.get_width()/2, b.get_height() + 1, f'{int(b.get_height())}',
                ha='center', va='bottom', fontsize=9, color='black')
    fig.legend(loc='upper right', bbox_to_anchor=(0.9, 0.9), fontsize=9)
    ax1.set_title('新品SKU毛利分档', fontsize=12, color=C_MAIN, fontweight='bold')
    ax1.grid(axis='y', linestyle='--', alpha=0.4)
    ax1.spines['top'].set_visible(False)
    fig.tight_layout()
    save(fig, 'p14_new_product.png')


def chart_p15_sku():
    # 来源：report_data.json sku_var（KA+AA合计）
    data = load_json('report_data.json')
    row = data['sku_var'][0]  # KA+AA合计
    # 列：客户数,新增SKU,流失SKU,净增减,新增收入,新增利润,流失收入,流失利润
    labels = ['新增收入', '流失收入', '新增利润', '流失利润']
    vals = [row[4], -row[6], row[5], -row[7]]
    fig, ax = plt.subplots(figsize=(6, 4))
    colors = [C_GREEN, C_NEG, C_CYAN, C_ORANGE]
    bars = ax.bar(labels, vals, color=colors, width=0.5)
    add_value_labels(ax, bars, fmt='{:.0f}', color='black', size=10)
    ax.set_ylabel('万元', fontsize=10)
    ax.set_title('KA+AA SKU进出账（近12月 vs 前12月）', fontsize=12, color=C_MAIN, fontweight='bold')
    ax.axhline(0, color=C_GRAY, lw=0.5)
    ax.grid(axis='y', linestyle='--', alpha=0.4)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    fig.tight_layout()
    save(fig, 'p15_sku_inout.png')


def chart_p16_pse():
    # 来源：analysis3.json D_渗透矩阵 PSE TOP30未渗透数量=12
    fig, ax = plt.subplots(figsize=(6, 4))
    n_total = 30
    n_orange = 12
    rows, cols = 3, 10
    for i in range(n_total):
        r, c = divmod(i, cols)
        color = C_ORANGE if i < n_orange else C_GRAY
        ax.scatter(c, rows - 1 - r, s=200, c=color, zorder=3, edgecolors='white')
    ax.set_xlim(-0.5, cols - 0.5)
    ax.set_ylim(-0.5, rows - 0.5)
    ax.axis('off')
    ax.set_title('PSE 在TOP30大客户中的渗透情况（未渗透12家）', fontsize=12, color=C_MAIN, fontweight='bold')
    ax.text(cols - 0.5, -0.7, '橙色=未渗透客户', fontsize=10, color=C_ORANGE, ha='right')
    ax.text(cols - 0.5, -1.1, '灰色=已渗透客户', fontsize=10, color=C_GRAY, ha='right')
    fig.tight_layout()
    save(fig, 'p16_pse_dots.png')


if __name__ == '__main__':
    chart_p04_mom()
    chart_p04_yoy()
    chart_p06_longcycle()
    chart_p07_ka_mm()
    chart_p08_hedge()
    chart_p09_zte()
    chart_p10_cost()
    chart_p11_audio()
    chart_p12_domain()
    chart_p14_new()
    chart_p15_sku()
    chart_p16_pse()
    print('\n全部12张图表生成完成')
