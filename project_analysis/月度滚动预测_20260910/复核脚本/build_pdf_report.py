# -*- coding: utf-8 -*-
"""生成三个数分层明细 PDF 报告：数据计算 + HTML 输出（随后 html2pdf 转换）"""
import sys
import pandas as pd
import numpy as np
sys.stdout.reconfigure(encoding='utf-8')

SILVER = r'E:\3-其他资料\数据分析\sales_analytics_platform\output\silver\silver_cleaned_rows.parquet'
OUT = r'E:\3-其他资料\数据分析\project_analysis\月度滚动预测_20260910'
HTML = r'E:\3-其他资料\数据分析\project_analysis\预测交付_分层明细_20260911.html'

F = 1.040  # E20 无偏因子
fut_months = ['2026-09','2026-10','2026-11','2026-12','2027-01','2027-02','2027-03','2027-04','2027-05','2026-06'.replace('2026-06','2027-06'),'2027-07','2027-08']

# --- 公司分月（修订后） ---
comp = pd.read_csv(OUT + r'\交付_公司分月.csv')
comp['基准万'] = comp['预测']/1e4
comp['无偏万'] = comp['无偏']/1e4

# --- silver 1-8月实际（线级/品类） ---
df = pd.read_parquet(SILVER, columns=['发货日期', '型号_产品线（新）', '型号_产品品类', '金额'])
df['月'] = pd.to_datetime(df['发货日期'], errors='coerce').dt.strftime('%Y-%m')
df = df.dropna(subset=['月'])
df['金额'] = pd.to_numeric(df['金额'], errors='coerce').fillna(0.0)
df = df[df['型号_产品线（新）'].astype(str).str.strip() != '']
act8_line = df[df['月'] <= '2026-08'].groupby('型号_产品线（新）')['金额'].sum()/1e4  # 2026 1-8月
act8_line = df[(df['月'] >= '2026-01') & (df['月'] <= '2026-08')].groupby('型号_产品线（新）')['金额'].sum()/1e4
act8_cat = df[(df['月'] >= '2026-01') & (df['月'] <= '2026-08')].groupby('型号_产品品类')['金额'].sum()/1e4

# --- 交付明细 CSV ---
line_fc = pd.read_csv(OUT + r'\交付_产品线.csv', index_col=0)
cat_fc = pd.read_csv(OUT + r'\交付_品类.csv', index_col=0)
for c in fut_months:
    line_fc[c] = pd.to_numeric(line_fc[c], errors='coerce')/1e4
    cat_fc[c] = pd.to_numeric(cat_fc[c], errors='coerce')/1e4

# --- 产品线三口径 ---
line_tbl = pd.DataFrame(index=line_fc.index)
line_tbl['选优方法'] = line_fc['选优方法']
line_tbl['1-8月实际'] = act8_line.reindex(line_tbl.index).fillna(0)
line_tbl['9-12月预测'] = line_fc[['2026-09','2026-10','2026-11','2026-12']].sum(axis=1)
line_tbl['2026全年'] = line_tbl['1-8月实际'] + line_tbl['9-12月预测']
line_tbl['未来6个月'] = line_fc[fut_months[:6]].sum(axis=1)
line_tbl['未来12个月'] = line_fc[fut_months].sum(axis=1)
line_tbl = line_tbl.sort_values('2026全年', ascending=False)
line_tbl['全年占比'] = line_tbl['2026全年']/line_tbl['2026全年'].sum()

# --- 品类三口径（Top15+其他 已在 CSV） ---
cat_tbl = pd.DataFrame(index=cat_fc.index)
cat_tbl['1-8月实际'] = act8_cat.reindex(cat_tbl.index).fillna(0)
cat_tbl['9-12月预测'] = cat_fc[['2026-09','2026-10','2026-11','2026-12']].sum(axis=1)
cat_tbl['2026全年'] = cat_tbl['1-8月实际'] + cat_tbl['9-12月预测']
cat_tbl['未来6个月'] = cat_fc[fut_months[:6]].sum(axis=1)
cat_tbl['未来12个月'] = cat_fc[fut_months].sum(axis=1)

# --- 公司汇总 ---
S_fy = float(comp[comp['月'] <= '2026-12']['基准万'].sum()) + float(act8_line.sum())
S6 = float(comp['基准万'][:6].sum())
S12 = float(comp['基准万'].sum())
ytd = float(act8_line.sum())

def fmt(v):
    return '{:,.0f}'.format(v)

# --- 方法名通俗化映射（非专业人士可读） ---
METHOD_CN = {
    'naive': '上月延续（用最近一个月作预测）',
    'ma3': '近3个月平均',
    'ma6': '近6个月平均',
    'ma12': '近12个月平均',
    'snaive': '去年同月',
    'yoy_adj': '去年同月×近年增速',
    'trend6': '近6个月趋势外推',
    'trend12': '近12个月趋势外推',
}
def rule_cn(tag):
    if tag == 'ma6':
        return '近6个月平均'
    if tag.startswith('phase3中枢'):
        return '春节前月·三法取中（去年1月×近年增速 ／ 上年12月×节前冲量 ／ 2024年1月×两年复合增速）'
    if tag.startswith('cny02'):
        return '春节低谷月：前一月×0.53（4个同类春节年份的中位规律）'
    return tag

# ============ HTML ============
css = """
body { font-family: 'Microsoft YaHei','PingFang SC','Segoe UI',sans-serif; color:#1a1a2e; margin:0; padding:24px 28px; font-size:12.5px; }
h1 { font-size:22px; margin:0 0 4px; color:#0f2b46; }
h2 { font-size:15px; margin:22px 0 8px; color:#0f2b46; border-left:4px solid #2e6da4; padding-left:8px; }
.sub { color:#666; font-size:11.5px; margin-bottom:14px; }
.cards { display:flex; gap:12px; margin:14px 0 4px; }
.card { flex:1; border:1px solid #d5dde8; border-radius:8px; padding:12px 14px; background:#f7fafd; break-inside:avoid; }
.card .t { font-size:12px; color:#46617d; margin-bottom:6px; }
.card .v { font-size:21px; font-weight:700; color:#0f2b46; }
.card .v2 { font-size:12px; color:#2e6da4; margin-top:4px; }
.card .r { font-size:11px; color:#888; margin-top:3px; }
table { border-collapse:collapse; width:100%; margin-top:6px; }
th { background:#0f2b46; color:#fff; padding:6px 7px; font-size:11.5px; text-align:right; white-space:nowrap; }
th:first-child, td:first-child { text-align:left; }
td { border-bottom:1px solid #e3e9f0; padding:5px 7px; text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap; }
tr:nth-child(even) td { background:#f4f7fb; }
tr.total td { background:#eaf1f8; font-weight:700; border-top:2px solid #0f2b46; }
.note { background:#fff8e6; border:1px solid #f0dfa8; border-radius:6px; padding:10px 12px; font-size:11.5px; line-height:1.7; margin-top:8px; break-inside:avoid; }
ul { margin:6px 0 6px 18px; padding:0; line-height:1.75; }
b.k { color:#b3541e; }
.pct { color:#777; font-size:10.5px; }
"""

H = ['<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8"><style>%s</style></head><body>' % css]
H.append('<h1>销售预测交付 · 三个数分层明细</h1>')
H.append('<div class="sub">生成日期 2026-09-11 ｜ 数据截至 2026-08（含 2020-2026 长历史标定）｜ 口径：RMB 未税金额 ｜ 单位：万元</div>')

H.append('<h2>一、三个数总览（公司口径）</h2>')
H.append('<div class="cards">')
H.append('<div class="card"><div class="t">2026 全年（1-8月实际 + 9-12月预测）</div><div class="v">%s 万</div><div class="v2">%.2f 亿 ｜ 无偏口径 %s 万（%.2f 亿）</div><div class="r">八成把握区间 [%s ~ %s] 万</div></div>' % (fmt(S_fy), S_fy/1e4, fmt((S_fy-ytd)*F+ytd), ((S_fy-ytd)*F+ytd)/1e4, fmt(86906), fmt(90662)))
H.append('<div class="card"><div class="t">未来 6 个月（2026-09 ~ 2027-02）</div><div class="v">%s 万</div><div class="v2">%.2f 亿 ｜ 无偏口径 %s 万（%.2f 亿）</div><div class="r">八成把握区间 [%s ~ %s] 万</div></div>' % (fmt(S6), S6/1e4, fmt(S6*F), S6*F/1e4, fmt(45193), fmt(49981)))
H.append('<div class="card"><div class="t">未来 12 个月（2026-09 ~ 2027-08）</div><div class="v">%s 万</div><div class="v2">%.2f 亿 ｜ 无偏口径 %s 万（%.2f 亿）</div><div class="r">八成把握区间 [%s ~ %s] 万</div></div>' % (fmt(S12), S12/1e4, fmt(S12*F), S12*F/1e4, fmt(91687), fmt(98396)))
H.append('</div>')
H.append('<div class="note"><b>本月修订（2026-09-11）：</b>利用新打通的 2020-2026 长历史数据，重新标定了春节月份的预测规则（此前只有 2 个春节样本，现有 6 个）。2027 年 1 月由 11,129 下调至 <b class="k">10,226 万</b>（三种算法取中间值，避免单一算法在高增长年份的高估），2027 年 2 月由 5,637 下调至 <b class="k">5,420 万</b>（按历史上 4 个"春节在 2 月"年份的低谷规律：前一个月的 53%）。6 个月/12 个月合计相应下修；<b>2026 全年预测不变</b>。</div>')

# 分月明细
H.append('<h2>二、公司口径分月（万元）</h2>')
H.append('<table><tr><th>月</th><th>基准</th><th>无偏口径</th><th>预测规则</th></tr>')
for _, r in comp.iterrows():
    H.append('<tr><td>%s</td><td>%s</td><td>%s</td><td style="text-align:left">%s</td></tr>' % (r['月'], fmt(r['基准万']), fmt(r['无偏万']), rule_cn(r['规则'])))
H.append('</table>')

# 产品线
H.append('<h2>三、产品线分层明细（万元；预测值已锚定公司口径）</h2>')
H.append('<table><tr><th>产品线</th><th>采用的算法</th><th>1-8月实际</th><th>9-12月预测</th><th>2026全年</th><th>全年占比</th><th>未来6个月</th><th>未来12个月</th></tr>')
for k, r in line_tbl.iterrows():
    H.append('<tr><td>%s</td><td style="text-align:left">%s</td><td>%s</td><td>%s</td><td><b>%s</b></td><td class="pct">%.1f%%</td><td><b>%s</b></td><td><b>%s</b></td></tr>' % (
        k, METHOD_CN.get(r['选优方法'], r['选优方法']), fmt(r['1-8月实际']), fmt(r['9-12月预测']), fmt(r['2026全年']), r['全年占比']*100, fmt(r['未来6个月']), fmt(r['未来12个月'])))
H.append('<tr class="total"><td>合计</td><td></td><td>%s</td><td>%s</td><td>%s</td><td class="pct">100%%</td><td>%s</td><td>%s</td></tr>' % (
    fmt(line_tbl['1-8月实际'].sum()), fmt(line_tbl['9-12月预测'].sum()), fmt(line_tbl['2026全年'].sum()), fmt(line_tbl['未来6个月'].sum()), fmt(line_tbl['未来12个月'].sum())))
H.append('</table>')
H.append('<div class="note">读表说明：规模越大的产品线预测越准——头部线（通用电源管理约占 %d%%）月度平均误差约 20%%，长尾小线误差 50%%-80%%；但由于分层结果会按比例对齐到公司总量，<b>各层级的合计始终等于公司口径总预测</b>，分层的意义在于看清结构占比，而非每层独立精度。新显示MLED驱动近 3 个月无出货（偶发脉冲式产品线），机械外推为 0，如需可结合业务判断调整。</div>' % (line_tbl['全年占比'].iloc[0]*100))

# 品类
H.append('<h2>四、品类分层明细（万元；Top15 + 其他，已锚定公司口径）</h2>')
H.append('<table><tr><th>品类</th><th>1-8月实际</th><th>9-12月预测</th><th>2026全年</th><th>未来6个月</th><th>未来12个月</th></tr>')
for k, r in cat_tbl.iterrows():
    H.append('<tr><td>%s</td><td>%s</td><td>%s</td><td><b>%s</b></td><td><b>%s</b></td><td><b>%s</b></td></tr>' % (
        k, fmt(r['1-8月实际']), fmt(r['9-12月预测']), fmt(r['2026全年']), fmt(r['未来6个月']), fmt(r['未来12个月'])))
H.append('<tr class="total"><td>合计</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>' % (
    fmt(cat_tbl['1-8月实际'].sum()), fmt(cat_tbl['9-12月预测'].sum()), fmt(cat_tbl['2026全年'].sum()), fmt(cat_tbl['未来6个月'].sum()), fmt(cat_tbl['未来12个月'].sum())))
H.append('</table>')

# 方法说明
H.append('<h2>五、预测方法说明（通俗版）</h2>')
H.append('<ul>'
 '<li><b>整体思路：先定总量，再往下分。</b>先预测全公司每月总销售额；产品线、品类再各自独立预测，最后按比例调整，使各层加起来严格等于公司总量——所以大数稳、小数参考结构即可。</li>'
 '<li><b>平时月份怎么算：</b>用最近 6 个月的平均值向前滚动。这一规则是用 2022-2026 年共 56 个月逐月模拟回测选出的最稳方案（月平均误差约 7%%）。</li>'
 '<li><b>春节月份单独处理：</b>春节月出货受放假影响大，用普通平均会严重高估。改用过去 6 个春节年份的实际规律：节前一个月通常比正常月多约 17%%（客户提前备货）；春节假期所在月约为上一个月的 53%%。2027 年春节在 2 月 6 日，故 1 月按"节前备货月"、2 月按"低谷月"处理。</li>'
 '<li><b>为什么有两列数（基准 / 无偏）：</b>回测发现模型整体会系统性低估约 6%%（因为公司近两年在增长，而平均法天然滞后）。"无偏口径"= 基准 ×1.04 修正这一低估。日常跟进用基准值，定目标、报计划建议用无偏值。</li>'
 '<li><b>单价波动未单独预测：</b>默认售价延续最近水平（回测显示单独预测价格对总精度提升很小）。<b>若近期有已知涨价/降价/汇率大变动，请在此基数上人工加减。</b></li>'
 '<li><b>客户维度不下分：</b>试过按客户逐个预测再汇总，误差反而更大（小客户噪声多），故客户层面不做进本表；客户结构分析请见月度经营看板。</li>'
 '<li><b>数据基础：</b>ERP 出货明细 2020 年 1 月至 2026 年 8 月（80 个月，不含税人民币口径）；2024 年之前数据来自已冻结的历史总表，与现行口径逐月核对一致。</li>'
 '</ul>')
H.append('<div class="sub" style="margin-top:14px">数据源：ERP 出货明细（2020-01 ~ 2026-08，金额=RMB 未税口径）｜ 方法细节见《预测能力提升规划备忘》（E1-E23 全实验记录）｜ 生成脚本：复核脚本/build_pdf_report.py</div>')
H.append('</body></html>')

with open(HTML, 'w', encoding='utf-8') as f:
    f.write('\n'.join(H))
print('HTML 已生成: %s' % HTML)
print('公司汇总校验: FY=%s 6M=%s 12M=%s' % (fmt(S_fy), fmt(S6), fmt(S12)))
print('产品线合计: FY=%s 6M=%s 12M=%s' % (fmt(line_tbl['2026全年'].sum()), fmt(line_tbl['未来6个月'].sum()), fmt(line_tbl['未来12个月'].sum())))
print('品类合计:   FY=%s 6M=%s 12M=%s' % (fmt(cat_tbl['2026全年'].sum()), fmt(cat_tbl['未来6个月'].sum()), fmt(cat_tbl['未来12个月'].sum())))
