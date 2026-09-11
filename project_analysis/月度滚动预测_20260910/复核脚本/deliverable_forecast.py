# -*- coding: utf-8 -*-
"""预测交付：2026 收官（9-12月+全年）+ 未来 6/12 个月 + 产品线/品类预测
口径：冠军 combo_phase（非春节月 ma6 递归；2027-01 相位参照 2026-01×trailing YoY；2027-02 wd3 估算）
     + 可选 E20 无偏因子 ×1.040；线/品类 = 分线选优（expanding）+ 锚定到公司口径
注：2027 假期安排未公布——2027-01/02 为估算（假设：春节 2/5-2/12，调休按惯例），已在报告中标注。
"""
import sys
import numpy as np
import pandas as pd
from datetime import date, timedelta
import chinese_calendar as cc
sys.stdout.reconfigure(encoding='utf-8')

SILVER = r'E:\3-其他资料\数据分析\sales_analytics_platform\output\silver\silver_cleaned_rows.parquet'
OUT = r'E:\3-其他资料\数据分析\project_analysis\月度滚动预测_20260910'
REPORT = r'E:\3-其他资料\数据分析\project_analysis\预测交付_2026收官与6-12个月_20260910.md'

df = pd.read_parquet(SILVER, columns=['发货日期', '型号_产品线（新）', '金额', '型号_产品品类'])
df['月'] = pd.to_datetime(df['发货日期'], errors='coerce').dt.strftime('%Y-%m')
df = df.dropna(subset=['月'])
df = df[df['型号_产品线（新）'].astype(str).str.strip() != '']
df['金额'] = pd.to_numeric(df['金额'], errors='coerce').fillna(0.0)

ts = df.groupby('月')['金额'].sum().sort_index()
months_all = list(ts.index)
pv = df.groupby(['月', '型号_产品线（新）'])['金额'].sum().unstack(fill_value=0.0).sort_index()
cat_col = '型号_产品品类'
cat = df.groupby(['月', cat_col])['金额'].sum().unstack(fill_value=0.0).sort_index()

METHODS = ['naive', 'ma3', 'ma6', 'ma12', 'snaive', 'yoy_adj', 'trend6', 'trend12']
def predict_one(v, method):
    n = len(v)
    if method == 'naive':
        return float(v[-1])
    if method.startswith('ma'):
        k = int(method[2:])
        return float(v[-k:].mean()) if n >= k else float(v.mean())
    if method == 'snaive':
        return float(v[-12]) if n >= 12 else float(v.mean())
    if method == 'yoy_adj':
        base = float(v[-12]) if n >= 12 else float(v.mean())
        den = float(v[-24:-12].sum())
        g = (float(v[-12:].sum()) / den) if (n >= 24 and den > 1e5) else 1.0
        return base * g
    if method.startswith('trend'):
        k = int(method[5:])
        y = np.asarray(v[-k:], dtype=float)
        x = np.arange(len(y))
        if len(y) >= 3 and y.std() > 0:
            sl, ic = np.polyfit(x, y, 1)
            return max(0.0, float(ic + sl * len(y)))
        return float(y.mean())
    raise ValueError(method)

def wape_series(v, method, targets):
    errs = acts = 0.0
    for t in targets:
        i = months_all.index(t)
        if i < 12:
            continue
        p = predict_one(v[:i], method)
        errs += abs(p - v[i]); acts += v[i]
    return errs / acts if acts > 0 else np.inf

def select_method(v):
    targets = [m for m in months_all if '2025-01' <= m <= '2026-08']
    scores = {m: wape_series(v, m, targets) for m in METHODS}
    return min(scores, key=lambda m: (scores[m], METHODS.index(m)))

def forecast_steps(hist, method, steps):
    h = list(hist); out = []
    for _ in range(steps):
        p = predict_one(np.array(h), method)
        out.append(p); h.append(p)
    return out

def workdays(y, m):
    """工作日数：优先 chinese_calendar；2027 未覆盖时按惯例回退（春节 2/5-2/12，元旦 1/1-1/3）"""
    try:
        d = date(y, m, 1); n = 0
        while d.month == m:
            if cc.is_workday(d):
                n += 1
            d += timedelta(days=1)
        return n, 'lib'
    except Exception:
        hol = set()
        if (y, m) == (2027, 1):
            hol = {date(2027, 1, 1), date(2027, 1, 2), date(2027, 1, 3)}
        elif (y, m) == (2027, 2):
            hol = {date(2027, 2, d) for d in range(5, 13)}
        d = date(y, m, 1); n = 0
        while d.month == m:
            if d.weekday() < 5 and d not in hol:
                n += 1
            d += timedelta(days=1)
        return n, 'fallback'

# ---------- 公司口径：逐月延伸到 2027-08 ----------
hist = list(ts.values.astype(float))
hist_months = list(months_all)
future = []
def extend_one(month):
    y, m = int(month[:4]), month[5:7]
    if m == '01':
        g = float(sum(hist[-12:])) / max(float(sum(hist[-24:-12])), 1.0)
        pred = float(hist[hist_months.index('2026-01')]) * g   # 参照最近同相位月（2026-01，pre）×trailing YoY
        tag = 'phase(参照2026-01×%.3f)' % g
    elif m == '02':
        wd, src = workdays(y, int(m))
        wd3m, _ = workdays(y, int(m)-1 if int(m) > 1 else 12)
        rate = float(sum(hist[-3:])) / max(sum([workdays(int(mm[:4]), int(mm[5:7]))[0] for mm in hist_months[-3:]]), 1)
        pred = rate * wd
        tag = 'wd3(工作日%d,%s)' % (wd, src)
    else:
        pred = float(np.mean(hist[-6:]))
        tag = 'ma6'
    future.append({'月': month, '预测': pred, '规则': tag})
    hist.append(pred); hist_months.append(month)

for mm in ['2026-09', '2026-10', '2026-11', '2026-12', '2027-01', '2027-02', '2027-03', '2027-04',
           '2027-05', '2027-06', '2027-07', '2027-08']:
    extend_one(mm)
fut = pd.DataFrame(future)
F = 1.040  # E20 中位因子（无偏口径）
fut['无偏'] = fut['预测'] * F

# 区间（比率池，20 折冠军）
e12 = pd.read_csv(OUT + r'\E12b_量价集成_对比.csv')
pool = (e12['实际'] / e12['combo_volxasp']).values
q10, q90 = np.percentile(pool, [10, 90])
ytd = float(ts.loc['2026-01':'2026-08'].sum())

def interval(preds):
    S = float(np.sum(preds))
    lo_c, hi_c = S*q10, S*q90
    rng = np.random.default_rng(42)
    sims = np.array([sum(p * rng.choice(pool) for p in preds) for _ in range(4000)])
    lo_i, hi_i = np.percentile(sims, [10, 90])
    return S, lo_c, hi_c, lo_i, hi_i

S4 = interval(fut[fut['月'] <= '2026-12']['预测'].values)
S6 = interval(fut[fut['月'] <= '2027-02']['预测'].values)
S12 = interval(fut['预测'].values)

# ---------- 产品线 / 品类：选优 + 锚定 ----------
def detail_forecast(pivot, topn=None):
    sel = {}
    for k in pivot.columns:
        sel[k] = select_method(pivot[k].values.astype(float))
    rows = {}
    for k in pivot.columns:
        v = pivot[k].values.astype(float)
        f = forecast_steps(v, sel[k], 12)
        rows[k] = f
    det = pd.DataFrame(rows, index=fut['月']).T   # 行=线/品类, 列=月份
    anchor = dict(zip(fut['月'], fut['预测']))
    out = {}
    for t in det.columns:
        raw_sum = float(det[t].sum())
        out[t] = det[t] * (anchor[t] / raw_sum)
    out = pd.DataFrame(out)
    out.insert(0, '选优方法', pd.Series(sel))
    return out

line_fc = detail_forecast(pv)
cat_fc_all = detail_forecast(cat)
cat_rank = cat.loc['2026-01':'2026-08'].sum().sort_values(ascending=False)
TOPN = 15
keep = list(cat_rank.head(TOPN).index)
cat_fc = cat_fc_all.loc[[c for c in cat_fc_all.index if c in keep]]
cat_other = cat_fc_all.loc[[c for c in cat_fc_all.index if c not in keep]].sum()
cat_other.name = '其他(%d类)' % (len(cat_fc_all) - TOPN)

# ---------- 输出报告 ----------
L = []
L.append('# 预测交付 · 2026 收官与未来 6/12 个月（2026-09-10）')
L.append('')
L.append('> 口径：冠军 combo_phase（非春节月 ma6 递归；2027-01 相位参照 2026-01×trailing YoY；2027-02 工作日法估算）；')
L.append('> 线/品类 = 分线选优（expanding）+ 锚定到公司口径；无偏口径 = ×1.040（E20 中位因子）。')
L.append('> **注：2027 年假期安排未公布**——2027-01/02 为估算（假设春节 2/5-2/12），属参考值。')
L.append('')
L.append('## 一、公司口径：分月预测（万元）')
L.append('')
L.append('| 月 | 基准 | 无偏口径 | 规则 |')
L.append('|---|---|---|---|')
for _, r in fut.iterrows():
    L.append('| %s | %,.0f | %,.0f | %s |'.replace(',', '') % (r['月'], r['预测']/1e4, r['无偏']/1e4, r['规则']))
L.append('')
L.append('## 二、汇总（万元 / 亿元）')
L.append('')
L.append('| 口径 | 基准（万元） | 80%区间（全相关，万元） | 80%区间（独立，万元） | 无偏口径（万元） |')
L.append('|---|---|---|---|---|')
for name, (S, lo, hi, loi, hii), add_ytd in [
        ('2026 全年（1-8月实际 + 9-12月）', S4, ytd),
        ('未来 6 个月（2026-09 ~ 2027-02）', S6, 0.0),
        ('未来 12 个月（2026-09 ~ 2027-08）', S12, 0.0)]:
    L.append('| %s | %,.0f（%.2f亿） | [%,.0f, %,.0f] | [%,.0f, %,.0f] | %,.0f（%.2f亿） |'.replace(',', '') % (
        name, (S+add_ytd)/1e4, (S+add_ytd)/1e8, (lo+add_ytd)/1e4, (hi+add_ytd)/1e4,
        (loi+add_ytd)/1e4, (hii+add_ytd)/1e4, (S*F+add_ytd)/1e4, (S*F+add_ytd)/1e8))
L.append('')
L.append('## 三、产品线预测（万元；已锚定公司口径）')
L.append('')
hdr = '| 产品线 | 选优方法 | ' + ' | '.join(fut['月'][:4]) + ' | 9-12月合计 | 6个月合计 | 12个月合计 |'
L.append(hdr)
L.append('|---' * (3 + 4 + 3) + '|')
for k, r in line_fc.iterrows():
    vals = [r[m]/1e4 for m in fut['月'][:4]]
    L.append('| %s | %s | %.0f | %.0f | %.0f | %.0f | %.0f | %.0f | %.0f |' % (
        k, r['选优方法'], vals[0], vals[1], vals[2], vals[3],
        sum(r[m] for m in fut['月'][:4])/1e4, sum(r[m] for m in fut['月'][:6])/1e4, sum(r[m] for m in fut['月'])/1e4))
L.append('')
L.append('> 注：新显示MLED驱动近3月无出货（偶发脉冲线，历史脉冲月约 25 万），机械外推为 0——如需可结合业务判断调整。')
L.append('')
L.append('## 四、品类预测（万元；Top%d，已锚定公司口径）' % TOPN)
L.append('')
L.append('| 品类 | 9-12月合计 | 6个月合计 | 12个月合计 |')
L.append('|---|---|---|---|')
for k, r in cat_fc.iterrows():
    L.append('| %s | %.0f | %.0f | %.0f |' % (k, sum(r[m] for m in fut['月'][:4])/1e4,
                                              sum(r[m] for m in fut['月'][:6])/1e4, sum(r[m] for m in fut['月'])/1e4))
ro = cat_other
L.append('| %s | %.0f | %.0f | %.0f |' % (ro.name, sum(ro[m] for m in fut['月'][:4])/1e4,
                                          sum(ro[m] for m in fut['月'][:6])/1e4, sum(ro[m] for m in fut['月'])/1e4))
L.append('')
L.append('---')
L.append('*生成：预测交付脚本（复核脚本/deliverable_forecast.py）；方法细节见《预测能力提升规划备忘》。*')

with open(REPORT, 'w', encoding='utf-8') as f:
    f.write('\n'.join(L))
fut.to_csv(OUT + r'\交付_公司分月.csv', index=False, encoding='utf-8-sig')
line_fc.to_csv(OUT + r'\交付_产品线.csv', encoding='utf-8-sig')
cat_fc.to_csv(OUT + r'\交付_品类.csv', encoding='utf-8-sig')

print('=== 公司口径分月（万元）===')
for _, r in fut.iterrows():
    print('%s 基准 %,.0f | 无偏 %,.0f | %s'.replace(',', '') % (r['月'], r['预测']/1e4, r['无偏']/1e4, r['规则']))
print()
print('2026全年: 基准 %,.0f万（%.2f亿）[区间 %,.0f~%,.0f万] | 无偏 %,.0f万（%.2f亿）'.replace(',', '') % (
    (S4[0]+ytd)/1e4, (S4[0]+ytd)/1e8, (S4[1]+ytd)/1e4, (S4[2]+ytd)/1e4, (S4[0]*F+ytd)/1e4, (S4[0]*F+ytd)/1e8))
print('未来6个月: 基准 %,.0f万（%.2f亿）| 无偏 %,.0f万 [独立区间 %,.0f~%,.0f万]'.replace(',', '') % (
    S6[0]/1e4, S6[0]/1e8, S6[0]*F/1e4, S6[3]/1e4, S6[4]/1e4))
print('未来12个月: 基准 %,.0f万（%.2f亿）| 无偏 %,.0f万 [独立区间 %,.0f~%,.0f万]'.replace(',', '') % (
    S12[0]/1e4, S12[0]/1e8, S12[0]*F/1e4, S12[3]/1e4, S12[4]/1e4))
print()
print('品类数: %d（展示 Top%d + 其他）' % (len(cat_fc_all), TOPN))
print('报告已存: ' + REPORT)
