# -*- coding: utf-8 -*-
"""
智数分析专家团 - 数据科学工程师赛奇（Sage）
长尾客户（MM/KM）季度销售预测系统 v4
============================================
- 使用终端客户名称(251个唯一客户)作为唯一标识
- 务实分层(适配极端长尾: 57%仅1季交易)
- 活跃客户: 回测选优(4折)
- 稀疏/休眠: 群体(Cohort)中位数基准
- 一次性: 低概率复购加权
"""

import pandas as pd
import numpy as np
from scipy import stats
from collections import defaultdict
import json
import warnings
import os
from datetime import datetime

warnings.filterwarnings('ignore')

DATA_PATH = r"C:/Users/45091/Desktop/工作文件/财务分析-5月（6.3）(1).xlsx"
OUTPUT_DIR = r"C:/Users/45091/Desktop/工作文件/longtail_forecast"

# 季度: Q1=2020Q1, Q25=2026Q1(最后完整), Q26=2026Q2(预测目标)
LAST_FULL_Q = 25
FORECAST_Q = 26
BT_TEST_QS = [24, 23, 22, 21]

os.makedirs(OUTPUT_DIR, exist_ok=True)
print(f"配置: LAST_FULL_Q={LAST_FULL_Q}, FORECAST_Q={FORECAST_Q}, BT={BT_TEST_QS}")


# ============================================================
# 1. 数据加载
# ============================================================
def load_data():
    print("\n" + "=" * 70 + "\n【1】数据加载\n" + "=" * 70)

    df = pd.read_excel(DATA_PATH, sheet_name='总表', engine='openpyxl',
                       usecols=['发货日期', '终端客户名称', '终端客户名称_客户类别',
                                'RMB 未税金额小计', '利润', '发货数量',
                                '产品系列', '细分市场'])

    df = df[df['终端客户名称_客户类别'].notna()].copy()
    df['客户类型'] = df['终端客户名称_客户类别'].str.extract(r'^(KA|AA|MM|KM)', expand=False)
    df = df[df['客户类型'].isin(['MM', 'KM'])].copy()
    df['发货日期'] = pd.to_datetime(df['发货日期'], errors='coerce')
    df = df.dropna(subset=['发货日期', '终端客户名称'])

    df['年份'] = df['发货日期'].dt.year
    df['季度内'] = (df['发货日期'].dt.month - 1) // 3 + 1
    df['季度号'] = (df['年份'] - 2020) * 4 + df['季度内']
    df['季度标签'] = df['年份'].astype(str) + '-Q' + df['季度内'].astype(str)

    print(f"  记录: {len(df):,}, 客户: {df['终端客户名称'].nunique()}")
    print(f"  季度: Q{df['季度号'].min()}-Q{df['季度号'].max()}")
    return df


# ============================================================
# 2. 季度聚合
# ============================================================
def aggregate(df):
    print("\n" + "=" * 70 + "\n【2】季度聚合\n" + "=" * 70)

    qdf = df.groupby(['终端客户名称', '客户类型', '季度号', '季度标签']).agg(
        销售额=('RMB 未税金额小计', 'sum'),
        利润=('利润', 'sum'),
        销量=('发货数量', 'sum'),
        主要系列=('产品系列', lambda x: x.mode().iloc[0] if len(x.mode()) > 0 else '未知'),
        主要市场=('细分市场', lambda x: x.mode().iloc[0] if len(x.mode()) > 0 else '未知'),
    ).reset_index()

    qdf['单价'] = np.where(qdf['销量'] != 0, qdf['销售额'] / qdf['销量'], 0)
    qdf['毛利率'] = np.where(qdf['销售额'] > 0, qdf['利润'] / qdf['销售额'], 0)

    print(f"  聚合: {len(qdf):,} 条, {qdf['终端客户名称'].nunique()} 客户")

    # 季度趋势
    qs = qdf.groupby('季度号').agg(
        总收入=('销售额', 'sum'), 客户数=('终端客户名称', 'nunique')
    ).sort_index()
    print("\n  近8季度趋势:")
    for q in range(19, 27):
        if q in qs.index:
            r = qs.loc[q]
            ql = f"{2020+(q-1)//4}-Q{(q-1)%4+1}"
            print(f"    Q{q}({ql}): {r['总收入']/10000:,.0f}万, {int(r['客户数'])}客户")
    return qdf


# ============================================================
# 3. 客户分层
# ============================================================
def segment(qdf):
    print("\n" + "=" * 70 + "\n【3】客户分层\n" + "=" * 70)

    cs = qdf.groupby('终端客户名称').agg(
        客户类型=('客户类型', 'first'),
        最后季度=('季度号', 'max'),
        首次季度=('季度号', 'min'),
        季度数=('季度号', 'nunique'),
        总销售额=('销售额', 'sum'),
        总利润=('利润', 'sum'),
        总销量=('销量', 'sum'),
        主要系列=('主要系列', lambda x: x.mode().iloc[0] if len(x.mode()) > 0 else '未知'),
    ).reset_index()

    # 长尾分布: 142/251仅1季度, 需务实分层
    # 活跃: 最近4个季度(Q22+)有交易且季度数>=2 → 有足够数据做回测
    # 稀疏: 2+季度但最后交易在Q17-Q21(2024) → 用群体基准
    # 休眠: 最后交易在Q16及之前(2023及更早)
    # 一次性: 仅1个季度(无论何时)

    def classify(r):
        if r['季度数'] == 1:
            return '一次性'
        if r['最后季度'] >= 22 and r['季度数'] >= 2:
            return '活跃'
        if r['季度数'] >= 2 and r['最后季度'] >= 17:
            return '稀疏'
        return '休眠'

    cs['分层'] = cs.apply(classify, axis=1)

    for seg in ['活跃', '稀疏', '休眠', '一次性']:
        sub = cs[cs['分层'] == seg]
        mm = len(sub[sub['客户类型'] == 'MM'])
        km = len(sub[sub['客户类型'] == 'KM'])
        rev = sub['总销售额'].sum()
        print(f"  {seg}: {len(sub)} 客户 (MM:{mm}, KM:{km}), 历史收入 {rev/10000:,.0f}万")

    # 活跃客户的交易季度数
    active = cs[cs['分层'] == '活跃']
    if len(active) > 0:
        print(f"\n  活跃客户季度数: 均值={active['季度数'].mean():.1f}, "
              f"中位数={active['季度数'].median():.0f}, "
              f"min={active['季度数'].min()}, max={active['季度数'].max()}")
    return cs


# ============================================================
# 4. 方法库
# ============================================================

def m_seasonal(v, tq, tqs, tvs):
    for lag in [4, 8]:
        lq = tq - lag
        if lq in tqs:
            return f"同比季节(lag={lag})", tvs[list(tqs).index(lq)]
    return "同比季节(最近值)", tvs[-1] if tvs else 0

def m_moving_avg(v, tq, tqs, tvs):
    if not tvs: return "移动平均", 0
    bw, bs = 1, float('inf')
    for w in [1, 2, 3, 4]:
        if w + 1 <= len(tvs):
            p = np.mean(tvs[-(w+1):-1]); s = abs(p - tvs[-1])
            if s < bs: bs, bw = s, w
    return f"移动平均(w={bw})", np.mean(tvs[-bw:])

def m_median(v, tq, tqs, tvs):
    if not tvs: return "中位数", 0
    bw, bs = 2, float('inf')
    for w in [2, 3, 4]:
        if w + 1 <= len(tvs):
            p = np.median(tvs[-(w+1):-1]); s = abs(p - tvs[-1])
            if s < bs: bs, bw = s, w
    w = min(bw, len(tvs))
    return f"中位数(w={w})", np.median(tvs[-w:])

def m_ewma(v, tq, tqs, tvs):
    if not tvs: return "EWMA", 0
    n = len(tvs); ba, bs = 0.5, float('inf')
    for a in [0.3, 0.5, 0.7, 0.85]:
        if n >= 2:
            w = np.array([(1-a)**(n-2-i) for i in range(n-1)]); w /= w.sum()
            p = np.dot(w, tvs[:-1]); s = abs(p - tvs[-1])
            if s < bs: bs, ba = s, a
    w = np.array([(1-ba)**(n-1-i) for i in range(n)]); w /= w.sum()
    return f"EWMA(α={ba})", np.dot(w, tvs)

def m_drift(v, tq, tqs, tvs):
    if len(tvs) < 2: return "漂移", tvs[-1] if tvs else 0
    d = (tvs[-1] - tvs[0]) / len(tvs)
    return "漂移", max(0, tvs[-1] + d)

def m_linear(v, tq, tqs, tvs):
    if len(tvs) < 2: return "线性趋势", tvs[-1] if tvs else 0
    x = np.arange(len(tvs))
    sl, ic, _, _, _ = stats.linregress(x, tvs)
    return "线性趋势", max(0, ic + sl * len(tvs))

def m_croston(v, tq, tqs, tvs):
    if not tvs or all(x <= 0 for x in tvs): return "Croston", 0
    a, z, p, gap = 0.2, None, 1, 0
    for val in tvs:
        gap += 1
        if val > 0:
            z = val if z is None else a*val + (1-a)*z
            p = max(gap,1) if z is None else a*gap + (1-a)*p
            gap = 0
    if z and p > 0: return "Croston", max(0, z/p)
    nz = [x for x in tvs if x > 0]
    return "Croston", max(0, np.mean(nz)) if nz else 0

def m_naive(v, tq, tqs, tvs):
    return "最近值", tvs[-1] if tvs else 0

def m_weighted_recent(v, tq, tqs, tvs):
    if not tvs: return "加权近期", 0
    n = min(3, len(tvs)); w = np.arange(1, n+1, dtype=float); w /= w.sum()
    return "加权近期", np.dot(w, tvs[-n:])

METHODS = [m_seasonal, m_moving_avg, m_median, m_ewma, m_drift,
           m_linear, m_croston, m_naive, m_weighted_recent]


# ============================================================
# 5. 回测引擎
# ============================================================
def backtest(series):
    qs = sorted(series.keys())
    vals = [series[q] for q in qs]
    results = defaultdict(lambda: [0.0, 0.0, 0])

    for tq in BT_TEST_QS:
        if tq not in qs: continue
        idx = qs.index(tq)
        if idx < 2: continue
        actual = vals[idx]
        if abs(actual) < 10: continue
        tqs = qs[:idx]; tvs = vals[:idx]
        for mf in METHODS:
            try:
                nm, pr = mf(tvs, tq, tqs, tvs)
                mae = abs(pr - actual)
                wape = min(mae / abs(actual), 5.0)
                results[nm][0] += wape; results[nm][1] += mae; results[nm][2] += 1
            except: continue

    return {nm: {'avg_wape': tw/cnt, 'avg_mae': tm/cnt, 'folds': cnt}
            for nm, (tw, tm, cnt) in results.items() if cnt > 0} or None


# ============================================================
# 6. 单价 & 毛利率
# ============================================================
def predict_price(cqdf):
    if cqdf is None or len(cqdf) == 0: return 0, 1.0
    s = cqdf.sort_values('季度号')
    rq = s['季度号'].max()
    r2 = s[s['季度号'] >= rq - 1]
    e2 = s[(s['季度号'] < rq - 1) & (s['季度号'] >= rq - 3)]
    if len(r2) == 0 or r2['销量'].sum() == 0: return 0, 1.0
    avg = r2['销售额'].sum() / r2['销量'].sum()
    rr = r2['销售额'].sum(); er = e2['销售额'].sum() if len(e2) > 0 else 0
    f = np.sqrt(rr/er) if er > 1 else 1.0
    return avg * np.clip(f, 0.8, 1.15), f

def predict_margin(cqdf):
    if cqdf is None or len(cqdf) == 0: return 0
    v = cqdf[cqdf['销售额'] > 0].sort_values('季度号')
    if len(v) == 0: return 0
    m = v['毛利率'].values; n = len(m); a = 0.4
    w = np.array([(1-a)**(n-1-i) for i in range(n)]); w /= w.sum()
    return np.clip(np.dot(w, m), -0.2, 0.8)


# ============================================================
# 7. 群体基准
# ============================================================
def build_cohorts(qdf, cs):
    print("\n" + "=" * 70 + "\n【4】群体(Cohort)基准\n" + "=" * 70)

    cs2 = cs.copy()
    cs2['体量档'] = pd.cut(cs2['总销售额'],
                            bins=[-1, 10000, 100000, 1000000, 1e18],
                            labels=['微额', '小额', '中额', '大额'])
    qdf2 = qdf.merge(cs2[['终端客户名称', '体量档']], on='终端客户名称', how='left')
    pos = qdf2[qdf2['销售额'] > 0]

    cohort = pos.groupby(['客户类型', '体量档']).agg(
        季度中位数=('销售额', 'median'),
        季度均值=('销售额', 'mean'),
        样本数=('销售额', 'count'),
    ).reset_index()

    print(f"  群体数: {len(cohort)}")
    for _, r in cohort.iterrows():
        print(f"    {r['客户类型']}/{r['体量档']}: 中位数={r['季度中位数']:,.0f}, "
              f"均值={r['季度均值']:,.0f}, n={int(r['样本数'])}")

    lookup = {}
    for _, r in cohort.iterrows():
        lookup[(r['客户类型'], r['体量档'])] = r['季度中位数']

    tier_map = dict(zip(cs2['终端客户名称'], cs2['体量档']))
    return lookup, tier_map, cs2


# ============================================================
# 8. 主预测
# ============================================================
def predict_all(qdf, cs, cohort_lookup, tier_map):
    print("\n" + "=" * 70 + "\n【5】预测执行\n" + "=" * 70)

    cust_series = {}
    cust_qdfs = {}
    for cid, grp in qdf.groupby('终端客户名称'):
        cust_series[cid] = dict(zip(grp['季度号'], grp['销售额']))
        cust_qdfs[cid] = grp.copy()

    pred_recs, method_recs, hist_recs = [], [], []
    bt_ok, bt_fail = 0, 0

    for i, (_, row) in enumerate(cs.iterrows()):
        cid = row['终端客户名称']
        ctype = row['客户类型']
        seg = row['分层']
        series = cust_series.get(cid, {})
        cqdf = cust_qdfs.get(cid, pd.DataFrame())
        tier = tier_map.get(cid, '小额')

        if (i+1) % 50 == 0: print(f"  进度: {i+1}/{len(cs)}")

        # 历史
        for q in sorted(series.keys()):
            hist_recs.append({
                '客户名称': cid, '客户类型': ctype,
                '季度': q, '季度标签': f"{2020+(q-1)//4}-Q{(q-1)%4+1}",
                '实际销售额': series[q], '预测销售额': np.nan, '是否为预测': 0,
            })

        pv, pl, pu = 0, 0, 0
        bm = "N/A"; bw = np.nan; conf = "低"; qoq = np.nan
        pp, _ = predict_price(cqdf)
        pm = predict_margin(cqdf)
        ltq = max(series.keys()) if series else 0
        htx = len([q for q in series if series[q] > 0])
        hrev = sum(series.values())
        ltstr = f"{2020+(ltq-1)//4}-{((ltq-1)%4)*3+1:02d}" if ltq > 0 else "N/A"

        cohort_med = cohort_lookup.get((ctype, tier), 0)

        if seg == '一次性':
            # 1季度历史 → 低概率复购
            reactivate_prob = 0.05 if ltq >= 17 else 0.02
            pv = cohort_med * reactivate_prob
            bm = f"群体中位数×{reactivate_prob*100:.0f}%复购"
            bw = 1.0
            pl = 0; pu = cohort_med * reactivate_prob * 3

        elif seg == '休眠':
            silence = LAST_FULL_Q - ltq
            rp = max(0.02, 0.15 - silence * 0.01)
            pv = cohort_med * rp
            bm = f"群体中位数×{rp*100:.0f}%复购"
            bw = 1.0
            pl = 0; pu = cohort_med * rp * 3

        elif seg == '稀疏':
            nz = [v for v in series.values() if v > 0]
            if len(nz) >= 2:
                _, cpred = m_croston(list(series.values()), FORECAST_Q,
                                     sorted(series.keys()),
                                     [series[q] for q in sorted(series.keys())])
                pv = 0.5 * cpred + 0.5 * cohort_med
                bm = "Croston×50%+群体×50%"
            elif len(nz) == 1:
                pv = 0.5 * nz[0] + 0.5 * cohort_med * 0.3
                bm = "历史×50%+群体×30%(单季)"
            else:
                pv = cohort_med * 0.3
                bm = "群体中位数×30%"
            bw = 0.8
            pl = pv * 0.2; pu = pv * 1.8

        elif seg == '活跃':
            bt = backtest(series)
            qs_s = sorted(series.keys())
            va = [series[q] for q in qs_s]

            if bt and len(bt) >= 2:
                bt_ok += 1
                ranked = sorted(bt.items(), key=lambda x: x[1]['avg_wape'])
                for rank, (mn, met) in enumerate(ranked, 1):
                    method_recs.append({
                        '客户名称': cid, '客户类型': ctype,
                        '排名': rank, '方法名称': mn,
                        '回测WAPE(%)': round(met['avg_wape']*100, 2),
                        '回测MAE': round(met['avg_mae'], 2),
                        '回测折数': met['folds'],
                    })
                bn, bmet = ranked[0]
                bw = bmet['avg_wape']
                bm = bn

                found = False
                for mf in METHODS:
                    try:
                        nm, pr = mf(va, FORECAST_Q, qs_s, va)
                        if nm == bn: pv = max(0, pr); found = True; break
                    except: continue
                if not found:
                    pv = max(0, np.median(va[-4:])) if len(va) >= 4 else max(0, np.mean(va))

                if bw <= 0.30: conf = "高"
                elif bw <= 0.60: conf = "中"
                else: conf = "低"

                pl = pv * max(0, 1-bw); pu = pv * (1+bw)
            else:
                bt_fail += 1
                nz = [v for v in series.values() if v > 0]
                if len(nz) >= 2:
                    pv = 0.5 * np.median(nz[-3:]) + 0.5 * cohort_med
                    bm = "中位数×50%+群体×50%(回测不足)"
                else:
                    pv = cohort_med * 0.5
                    bm = "群体中位数×50%(回测不足)"
                bw = 0.7; conf = "低"
                pl = pv * 0.3; pu = pv * 1.7

        pl = max(0, pl); pu = max(pl, pu)

        pq = series.get(LAST_FULL_Q, 0)
        if pq > 1: qoq = (pv / pq - 1) * 100
        pp_profit = pv * pm
        pq_qty = pv / pp if pp > 1e-6 else 0

        pred_recs.append({
            '客户名称': cid, '客户类型': ctype, '客户分层': seg,
            'Q预测值(万元)': round(pv/10000, 2),
            '预测区间下限(万元)': round(pl/10000, 2),
            '预测区间上限(万元)': round(pu/10000, 2),
            '预测毛利(万元)': round(pp_profit/10000, 2),
            '预测毛利率(%)': round(pm*100, 2),
            '预测销量': round(pq_qty),
            '预测单价': round(pp, 4),
            '回测WAPE(%)': round(bw*100, 2) if not np.isnan(bw) else None,
            '置信度': conf,
            '最优方法名称': bm,
            '环比增长率(%)': round(qoq, 2) if not np.isnan(qoq) else None,
            '最后交易日期': ltstr,
            '历史交易次数': htx,
            '历史总销售额(万元)': round(hrev/10000, 2),
            '主要系列': cqdf['主要系列'].mode().iloc[0] if len(cqdf) > 0 and '主要系列' in cqdf.columns else '未知',
            '体量档': tier,
        })

        hist_recs.append({
            '客户名称': cid, '客户类型': ctype,
            '季度': FORECAST_Q,
            '季度标签': f"{2020+(FORECAST_Q-1)//4}-Q{(FORECAST_Q-1)%4+1}",
            '实际销售额': np.nan, '预测销售额': pv, '是否为预测': 1,
        })

    print(f"\n  活跃回测成功: {bt_ok}, 失败: {bt_fail}")
    print(f"  总计: {len(pred_recs)} 客户, {len(method_recs)} 方法排名, {len(hist_recs)} 历史")
    return pred_recs, method_recs, hist_recs


# ============================================================
# 9. 聚类
# ============================================================
def add_clusters(pred_recs, qdf):
    print("\n" + "=" * 70 + "\n【6】聚类\n" + "=" * 70)
    try:
        from sklearn.preprocessing import StandardScaler
        from sklearn.cluster import KMeans
    except ImportError:
        for r in pred_recs: r['聚类标签'] = 'N/A'
        return pred_recs

    active = [r for r in pred_recs if r['客户分层'] == '活跃']
    if len(active) < 6:
        for r in pred_recs: r['聚类标签'] = 'N/A'
        return pred_recs

    feats, names = [], []
    for r in active:
        cid = r['客户名称']
        cqdf = qdf[qdf['终端客户名称'] == cid].sort_values('季度号')
        sv = cqdf['销售额'].values
        ms = np.mean(sv) if len(sv) > 0 else 0
        cv = np.std(sv)/np.mean(sv) if len(sv) > 1 and np.mean(sv) > 0 else 0
        sl = stats.linregress(np.arange(len(sv)), sv)[0] if len(sv) >= 2 else 0
        feats.append([np.log1p(ms), cv, sl/max(ms,1), len(sv)])
        names.append(cid)

    X = StandardScaler().fit_transform(np.array(feats))
    k = min(4, len(active))
    labels = KMeans(n_clusters=k, random_state=42, n_init=10).fit_predict(X)
    cm = [np.mean([feats[i][0] for i in range(len(labels)) if labels[i]==c]) for c in range(k)]
    order = np.argsort(cm)
    lnames = ['小型客户','中小型客户','中型客户','大型客户'][:k]
    remap = {order[i]: lnames[i] for i in range(k)}
    cmap = {names[i]: remap[labels[i]] for i in range(len(names))}
    for r in pred_recs: r['聚类标签'] = cmap.get(r['客户名称'], 'N/A')
    for c in range(k):
        print(f"  {remap[c]}: {sum(1 for l in labels if l==c)} 客户")
    return pred_recs


# ============================================================
# 10. 输出
# ============================================================
def output(pred_recs, method_recs, hist_recs):
    print("\n" + "=" * 70 + "\n【7】输出\n" + "=" * 70)

    pdf = pd.DataFrame(pred_recs)
    pdf.to_csv(os.path.join(OUTPUT_DIR, '长尾客户预测总表.csv'), index=False, encoding='utf-8-sig')
    print(f"  [OK] 长尾客户预测总表.csv ({len(pdf)} 行)")

    hdf = pd.DataFrame(hist_recs)
    hdf.to_csv(os.path.join(OUTPUT_DIR, '长尾客户季度历史与预测.csv'), index=False, encoding='utf-8-sig')
    print(f"  [OK] 长尾客户季度历史与预测.csv ({len(hdf)} 行)")

    mdf = pd.DataFrame(method_recs)
    mdf.to_csv(os.path.join(OUTPUT_DIR, '预测方法选优结果.csv'), index=False, encoding='utf-8-sig')
    print(f"  [OK] 预测方法选优结果.csv ({len(mdf)} 行)")

    s = build_summary(pred_recs)
    with open(os.path.join(OUTPUT_DIR, '长尾预测摘要.json'), 'w', encoding='utf-8') as f:
        json.dump(s, f, ensure_ascii=False, indent=2)
    print(f"  [OK] 长尾预测摘要.json")
    return pdf, s


def build_summary(pred_recs):
    pdf = pd.DataFrame(pred_recs)
    s = {
        '生成时间': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        '预测配置': {
            '预测目标季度': f'Q{FORECAST_Q} ({2020+(FORECAST_Q-1)//4}-Q{(FORECAST_Q-1)%4+1})',
            '回测测试季度': [f'Q{q} ({2020+(q-1)//4}-Q{(q-1)%4+1})' for q in BT_TEST_QS],
        },
        '数据说明': {
            'MM_KM客户总数': len(pdf),
            'MM客户数': int((pdf['客户类型']=='MM').sum()),
            'KM客户数': int((pdf['客户类型']=='KM').sum()),
            '参考KA_Q13预测(万元)': 6429,
            '参考AA_Q13预测(万元)': 2028,
        },
        '按客户类型': {},
        '按分层': {},
        '总体预测': {},
        'Top10预测收入客户': [],
        '置信度分布': {},
        '方法使用分布': {},
    }

    for ct in ['MM', 'KM']:
        sub = pdf[pdf['客户类型'] == ct]
        wv = sub['回测WAPE(%)'].dropna()
        s['按客户类型'][ct] = {
            '客户数': len(sub),
            '预测总收入(万元)': round(sub['Q预测值(万元)'].sum(), 2),
            '预测总利润(万元)': round(sub['预测毛利(万元)'].sum(), 2),
            '平均WAPE(%)': round(float(wv.mean()), 2) if len(wv) > 0 else None,
        }
    for seg in ['活跃', '稀疏', '休眠', '一次性']:
        sub = pdf[pdf['客户分层'] == seg]
        s['按分层'][seg] = {
            '客户数': len(sub),
            '预测总收入(万元)': round(sub['Q预测值(万元)'].sum(), 2),
            '预测总利润(万元)': round(sub['预测毛利(万元)'].sum(), 2),
        }
    s['总体预测'] = {
        '预测总收入(万元)': round(pdf['Q预测值(万元)'].sum(), 2),
        '预测总利润(万元)': round(pdf['预测毛利(万元)'].sum(), 2),
        '预测总销量': int(pdf['预测销量'].sum()),
        '非零预测客户数': int((pdf['Q预测值(万元)'] > 0).sum()),
    }
    top = pdf.nlargest(10, 'Q预测值(万元)')[['客户名称','客户类型','客户分层','Q预测值(万元)','最优方法名称','置信度']]
    s['Top10预测收入客户'] = top.to_dict('records')
    for c in ['高','中','低']:
        n = int((pdf['置信度']==c).sum())
        s['置信度分布'][c] = f"{n} ({n/len(pdf)*100:.1f}%)"
    s['方法使用分布'] = {k: int(v) for k,v in pdf['最优方法名称'].value_counts().to_dict().items()}
    return s


# ============================================================
def main():
    print("\n" + "=" * 70)
    print("  长尾客户(MM/KM)季度销售预测系统 v4")
    print("  智数分析专家团 · 数据科学工程师 赛奇(Sage)")
    print("=" * 70)

    df_raw = load_data()
    qdf = aggregate(df_raw)
    cs = segment(qdf)
    cohort_lookup, tier_map, cs_tier = build_cohorts(qdf, cs)
    pred_recs, method_recs, hist_recs = predict_all(qdf, cs, cohort_lookup, tier_map)
    pred_recs = add_clusters(pred_recs, qdf)
    pred_df, summary = output(pred_recs, method_recs, hist_recs)

    print("\n" + "=" * 70 + "\n【预测摘要】\n" + "=" * 70)
    print(f"  目标: Q{FORECAST_Q} = {2020+(FORECAST_Q-1)//4}-Q{(FORECAST_Q-1)%4+1}")
    print(f"  客户: {len(pred_df)} (非零: {summary['总体预测']['非零预测客户数']})")
    print(f"  总收入: {summary['总体预测']['预测总收入(万元)']:,.2f} 万元")
    print(f"  总利润: {summary['总体预测']['预测总利润(万元)']:,.2f} 万元")
    for ct in ['MM', 'KM']:
        i = summary['按客户类型'][ct]
        print(f"  {ct}: {i['客户数']}客户, {i['预测总收入(万元)']:,.2f}万元, WAPE={i['平均WAPE(%)']}")
    for seg in ['活跃','稀疏','休眠','一次性']:
        i = summary['按分层'][seg]
        print(f"  {seg}: {i['客户数']}客户, {i['预测总收入(万元)']:,.2f}万元")
    print(f"  置信度: {summary['置信度分布']}")
    print(f"\n  参考: KA Q13=6,429万 | AA Q13=2,028万")
    print(f"  长尾: {summary['总体预测']['预测总收入(万元)']:,.2f} 万元")
    print(f"\n  输出: {OUTPUT_DIR}")
    print("=" * 70 + "\nDONE")

if __name__ == '__main__':
    main()
