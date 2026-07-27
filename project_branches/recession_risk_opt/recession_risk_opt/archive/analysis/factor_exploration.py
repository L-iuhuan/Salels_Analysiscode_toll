"""
因子探索引擎 — 系统搜索可提升风险预测的新特征
=============================================
目标：从原始订单数据中发现新特征，验证其对衰退预测的增量贡献
"""
import os, sys, json, warnings
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import TimeSeriesSplit
from collections import defaultdict

warnings.filterwarnings('ignore')

PRJ = r'E:\3-其他资料\数据分析\semiconductor_analysis\recession_risk_opt'
SRC = r'E:\3-其他资料\数据分析\semiconductor_analysis\data\所有的出货明细5.9.xlsx'
sys.path.insert(0, r'E:\3-其他资料\数据分析\semiconductor_analysis')
sys.path.insert(0, PRJ)
os.chdir(PRJ)

# Load RiskScorer
exec(open('pipeline.py', encoding='utf-8').read().split('if __name__')[0])
with open('models/best_config.json','r',encoding='utf-8') as f:
    best_cfg = json.load(f)

# ===== 1. 加载原始数据 =====
from shared.data_cleaning import read_excel_auto, rename_erp_columns
from config.settings_product import PRODUCT_LIFECYCLE

thr = PRODUCT_LIFECYCLE
col_map = thr['col_map']
name_col = col_map.get('产品名称列','产品品种')
date_col = col_map.get('发货日期列','发货日期')
qty_col = col_map.get('销量列','数量')
rev_col = col_map.get('营收列','金额')
profit_col = col_map.get('利润列','利润')
cust_col = col_map.get('客户列','客户编号')
order_col = col_map.get('订单号列','客户订单号')

print('Loading raw data...')
df = read_excel_auto(SRC, sheet_name=0)
df = rename_erp_columns(df)
df[name_col] = df[name_col].astype(str).str.strip()
df[date_col] = pd.to_datetime(df[date_col], errors='coerce')
df[qty_col] = pd.to_numeric(df[qty_col], errors='coerce').fillna(0)
df[rev_col] = pd.to_numeric(df[rev_col], errors='coerce').fillna(0)
df[profit_col] = pd.to_numeric(df[profit_col], errors='coerce').fillna(0)
if order_col and order_col in df.columns:
    df[order_col] = df[order_col].astype(str).str.strip()
if cust_col and cust_col in df.columns:
    df[cust_col] = df[cust_col].astype(str).str.strip()

# Clean
df = df[df[qty_col] > 0].copy()
df = df[df[date_col] >= pd.Timestamp('2020-01-01')]
df = df.dropna(subset=[date_col])
df['_月'] = df[date_col].dt.to_period('M')
df['_毛利率'] = np.where(df[rev_col]>0, df[profit_col]/df[rev_col], np.nan)
df['_毛利率'] = df['_毛利率'].clip(-0.50, 0.75)

print(f'Raw data: {len(df)} rows, {df[name_col].nunique()} products, {df[cust_col].nunique() if cust_col in df.columns else "N/A"} customers')

# ===== 2. 构建产品月度聚合（带客户/订单细节） =====
all_months = sorted(df['_月'].unique())
products = sorted(df[name_col].unique())

# Pre-group for efficiency
pm_full = df.groupby([name_col, '_月']).agg(
    qty_sum=(qty_col, 'sum'),
    rev_pos=(rev_col, lambda x: x[x>0].sum()),
    profit_sum=(profit_col, 'sum'),
    order_count=(order_col if order_col in df.columns else qty_col, 'nunique'),
    cust_count=(cust_col if cust_col in df.columns else qty_col, 'nunique'),
).reset_index()
pm_full['rev_per_order'] = pm_full['rev_pos'] / pm_full['order_count'].replace(0, np.nan)
pm_full['qty_per_order'] = pm_full['qty_sum'] / pm_full['order_count'].replace(0, np.nan)

# Load existing samples for baseline
samples = pd.read_pickle('data/samples.pkl')

# Build product-indexed dict
pm_idx = {p: g.set_index('_月').sort_index() for p, g in pm_full.groupby(name_col)}

# For customer-level features, precompute customer-month
if cust_col in df.columns:
    print('Building customer-product features...')
    cp = df.groupby([name_col, '_月', cust_col]).agg(
        cust_qty=(qty_col, 'sum'),
        cust_rev=(rev_col, lambda x: x[x>0].sum()),
    ).reset_index()
    cp_idx = {p: g for p, g in cp.groupby(name_col)}

# ===== 3. 候选新特征计算函数 =====

def calc_new_features(pm_data, cp_data, latest_month, product_name):
    """对给定产品+月份计算所有候选新特征"""
    f = {}
    pm_hist = pm_data[pm_data.index <= latest_month].sort_index()
    if len(pm_hist) < 6:
        return f

    recent_3m = pm_hist.index > (latest_month - 3)
    recent_6m = pm_hist.index > (latest_month - 6)
    recent_12m = pm_hist.index > (latest_month - 12)
    prior_12m = (pm_hist.index <= (latest_month - 12)) & (pm_hist.index > (latest_month - 24))

    # ---- A. 订单层面特征 ----
    # A1: 近3月订单数趋势 (订单数是否在减少)
    orders_recent = pm_hist.loc[recent_3m, 'order_count'].values
    orders_prior3 = pm_hist.loc[(pm_hist.index <= (latest_month - 3)) & (pm_hist.index > (latest_month - 6)), 'order_count'].values
    if len(orders_recent) >= 2 and len(orders_prior3) >= 2:
        f['order_count_trend'] = (orders_recent.mean() - orders_prior3.mean()) / max(orders_prior3.mean(), 1)
    else:
        f['order_count_trend'] = 0

    # A2: 单均金额趋势 (客单价变化)
    rev_per_order_recent = pm_hist.loc[recent_3m, 'rev_per_order'].dropna().values
    rev_per_order_prior = pm_hist.loc[(pm_hist.index <= (latest_month - 3)) & (pm_hist.index > (latest_month - 6)), 'rev_per_order'].dropna().values
    if len(rev_per_order_recent) >= 2 and len(rev_per_order_prior) >= 2 and rev_per_order_prior.mean() > 0:
        f['avg_order_value_trend'] = (rev_per_order_recent.mean() - rev_per_order_prior.mean()) / rev_per_order_prior.mean()
    else:
        f['avg_order_value_trend'] = 0

    # A3: 零订单月数（近12月中有几个月无订单）
    orders_12m = pm_hist.loc[recent_12m, 'order_count'].values
    f['zero_order_months_12m'] = (orders_12m == 0).sum() / max(len(orders_12m), 1)

    # A4: 月均客户数趋势
    if 'cust_count' in pm_hist.columns:
        cust_recent = pm_hist.loc[recent_3m, 'cust_count'].values
        cust_prior = pm_hist.loc[(pm_hist.index <= (latest_month - 3)) & (pm_hist.index > (latest_month - 6)), 'cust_count'].values
        if len(cust_recent) >= 2 and len(cust_prior) >= 2 and cust_prior.mean() > 0:
            f['cust_count_trend'] = (cust_recent.mean() - cust_prior.mean()) / cust_prior.mean()
        else:
            f['cust_count_trend'] = 0

    # ---- B. 客户集中度动态 ----
    if cp_data is not None:
        cp_12m = cp_data[(cp_data['_月'] > (latest_month - 12)) & (cp_data['_月'] <= latest_month)]
        cp_prior12 = cp_data[(cp_data['_月'] > (latest_month - 24)) & (cp_data['_月'] <= (latest_month - 12))]

        if len(cp_12m) > 0:
            cust_totals = cp_12m.groupby(cust_col)['cust_rev'].sum().sort_values(ascending=False)
            total_rev = cust_totals.sum()
            if total_rev > 0:
                # B1: 当前Top1集中度
                f['top1_conc'] = cust_totals.iloc[0] / total_rev if len(cust_totals) > 0 else 0
                # B2: Top3集中度
                f['top3_conc'] = cust_totals.iloc[:3].sum() / total_rev if len(cust_totals) >= 3 else (cust_totals.sum() / total_rev)
                # B3: 有效客户数
                f['active_cust_count'] = len(cust_totals)

            # B4: 客户流失信号 (前一时期有过但本期消失的客户)
            if len(cp_prior12) > 0:
                prior_custs = set(cp_prior12[cust_col].unique())
                recent_custs = set(cp_12m[cust_col].unique())
                lost_custs = prior_custs - recent_custs
                f['lost_cust_count'] = len(lost_custs)
                f['cust_churn_ratio'] = len(lost_custs) / max(len(prior_custs), 1)
            else:
                f['lost_cust_count'] = 0
                f['cust_churn_ratio'] = 0

    # ---- C. 销量波动结构（不仅CV，还有模式） ----
    qty_12m = pm_hist.loc[recent_12m, 'qty_sum'].values
    if len(qty_12m) >= 6 and qty_12m.sum() > 0:
        # C1: 近3月占比（越集中越危险：代表最近销售依赖少数月份）
        qty_3m_sum = pm_hist.loc[recent_3m, 'qty_sum'].sum()
        f['qty_3m_ratio'] = qty_3m_sum / max(qty_12m.sum(), 1)
        # C2: 最大值月份占比
        f['qty_max_month_ratio'] = qty_12m.max() / max(qty_12m.sum(), 1)
        # C3: 销量负值月数比（销量为零的月份比例）
        f['qty_zero_ratio'] = (qty_12m == 0).sum() / max(len(qty_12m), 1)
        # C4: 销量下降的连续月数
        diffs = np.diff(qty_12m)
        if len(diffs) > 0:
            f['consecutive_decline'] = max(1, sum(1 for d in diffs if d < 0))
        else:
            f['consecutive_decline'] = 0

    # ---- D. 利润率加速度（二阶导） ----
    margin_12m = pm_hist.loc[recent_12m, 'profit_sum'].values / pm_hist.loc[recent_12m, 'rev_pos'].replace(0, np.nan).values
    margin_12m = np.nan_to_num(margin_12m, 0)
    if len(margin_12m) >= 6:
        # 前半段和后半段斜率
        half = len(margin_12m) // 2
        x1, m1 = np.arange(half), margin_12m[:half]
        x2, m2 = np.arange(len(margin_12m)-half), margin_12m[half:]
        try:
            slope1 = np.polyfit(x1, m1, 1)[0] if len(m1) >= 3 else 0
            slope2 = np.polyfit(x2, m2, 1)[0] if len(m2) >= 3 else 0
        except:
            slope1, slope2 = 0, 0
        # D1: 利润率加速度 (后半段斜率 - 前半段斜率)
        f['margin_acceleration'] = slope2 - slope1

    # ---- E. 增长质量（增速的可持续性） ----
    qty_monthly = pm_hist.loc[recent_12m, 'qty_sum'].values
    if len(qty_monthly) >= 6:
        # E1: 增长稳定性（最近6月的增长率标准差，越小越好）
        growth_rates = []
        for i in range(1, len(qty_monthly)):
            if qty_monthly[i-1] > 0:
                growth_rates.append((qty_monthly[i] - qty_monthly[i-1]) / qty_monthly[i-1])
        f['growth_stability'] = np.std(growth_rates) if growth_rates else 0
        # E2: 正向增长月数比
        f['positive_growth_ratio'] = sum(1 for g in growth_rates if g > 0) / max(len(growth_rates), 1)

    # ---- F. 季节性异常 ----
    if len(qty_monthly) >= 13:
        # F1: 最近一月 vs 去年同期
        if qty_monthly[-13] > 0:
            f['yoy_current'] = (qty_monthly[-1] - qty_monthly[-13]) / qty_monthly[-13]
        else:
            f['yoy_current'] = 0
    else:
        f['yoy_current'] = 0

    return f


# ===== 4. 为样本集计算新特征 =====
print('\nComputing new features for all samples...')
new_features = []
skipped = 0
for idx, row in samples.iterrows():
    pid = row['product_id']
    month_str = row['date_month']
    try:
        m = pd.Period(month_str, freq='M')
    except:
        skipped += 1
        continue

    if pid not in pm_idx:
        skipped += 1
        continue

    cp_d = cp_idx.get(pid) if cp_idx else None
    feats = calc_new_features(pm_idx[pid], cp_d, m, pid)
    feats['_sample_idx'] = idx
    new_features.append(feats)

print(f'Computed features for {len(new_features)} samples (skipped {skipped})')

# Merge into samples
new_feat_df = pd.DataFrame(new_features)
new_feat_df = new_feat_df.set_index('_sample_idx')
samples_aug = samples.join(new_feat_df)
samples_aug = samples_aug.fillna(0)

# ===== 5. 验证每个新特征的预测能力 =====
scorer = RiskScorer(best_cfg)
y_true = samples_aug['y'].values
base_scores = []
for _, row in samples_aug.iterrows():
    base_scores.append(scorer.score(row.to_dict()))
base_scores = np.array(base_scores)
base_auc = roc_auc_score(y_true, base_scores)
print(f'\nBaseline AUC (5-factor model): {base_auc:.4f}')

# Test each new feature's standalone AUC
print('\n=== Standalone predictive power of new features ===')
print(f'{"Feature":<35s} {"Standalone AUC":>14s} {"Corr w/ y":>10s} {"Corr w/ score":>14s}')
print('-' * 75)

feature_results = []
for col in new_feat_df.columns:
    vals = samples_aug[col].fillna(0).values
    if np.std(vals) == 0:
        continue
    try:
        auc = roc_auc_score(y_true, vals)
    except:
        auc = 0.5
    corr_y = np.corrcoef(vals, y_true)[0, 1] if np.std(vals) > 0 else 0
    corr_score = np.corrcoef(vals, base_scores)[0, 1] if np.std(vals) > 0 else 0

    flag = ' ***' if abs(corr_y) > 0.05 else (' **' if abs(corr_y) > 0.03 else '')
    feature_results.append({
        'feature': col, 'auc': auc, 'corr_y': corr_y, 'corr_score': corr_score
    })

# Sort by predictive power
feature_results.sort(key=lambda x: abs(x['corr_y']), reverse=True)

for fr in feature_results:
    flag = ' ***' if abs(fr['corr_y']) > 0.05 else (' **' if abs(fr['corr_y']) > 0.03 else '')
    print(f'{fr["feature"]:<35s} {fr["auc"]:>14.4f} {fr["corr_y"]:>10.4f} {fr["corr_score"]:>14.4f}{flag}')

# ===== 6. 增量AUC测试: 逐步加入Top新特征 =====
print('\n=== Incremental AUC: Adding top features to base model ===')
print(f'{"Features added":<50s} {"AUC":>8s} {"Delta":>8s}')
print('-' * 68)

tscv = TimeSeriesSplit(n_splits=5)
n = len(samples_aug)

# Time-order the data
samples_aug['_ts'] = pd.to_datetime(samples_aug['date_month'].astype(str).str[:7] + '-01')
samples_aug = samples_aug.sort_values('_ts').reset_index(drop=True)
y_sorted = samples_aug['y'].values

def cv_auc_with_features(feature_names):
    X = samples_aug[feature_names].fillna(0).values
    aucs = []
    for train_idx, val_idx in tscv.split(X):
        X_train, X_val = X[train_idx], X[val_idx]
        y_train, y_val = y_sorted[train_idx], y_sorted[val_idx]
        # Simple logistic regression to test incremental value
        from sklearn.linear_model import LogisticRegression
        lr = LogisticRegression(max_iter=5000, C=0.1)
        lr.fit(X_train, y_train)
        try:
            probs = lr.predict_proba(X_val)[:, 1]
            aucs.append(roc_auc_score(y_val, probs))
        except:
            aucs.append(0.5)
    return np.mean(aucs)

# Just base score
base_auc_cv = cv_auc_with_features(['risk_score'])
print(f'{"Base (risk_score only)":<50s} {base_auc_cv:>8.4f} {"--":>8s}')

# Top new features (by absolute corr with y, excluding those highly corr with base score)
top_new = [fr for fr in feature_results if abs(fr['corr_score']) < 0.5]
top_new = top_new[:10]

added = ['risk_score']
for fr in top_new[:8]:
    feat_name = fr['feature']
    added.append(feat_name)
    auc_new = cv_auc_with_features(added)
    delta = auc_new - base_auc_cv
    label = f'+ {feat_name}'
    print(f'{label:<50s} {auc_new:>8.4f} {delta:>+8.4f}')

# ===== 7. 综合评分：用所有新特征的Logistic回归 =====
print('\n=== Full model with all new features ===')
all_feat_cols = ['risk_score'] + [fr['feature'] for fr in top_new[:8]]
full_auc = cv_auc_with_features(all_feat_cols)
print(f'Risk score + {len(all_feat_cols)-1} new features: AUC = {full_auc:.4f} (delta {full_auc-base_auc_cv:+.4f})')

# ===== 8. Feature importance (from a logistic regression on full data) =====
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

X_full = samples_aug[all_feat_cols].fillna(0).values
scaler = StandardScaler()
X_scaled = scaler.fit_transform(X_full)
lr_full = LogisticRegression(max_iter=5000, C=0.1)
lr_full.fit(X_scaled, y_sorted)

print('\n=== Feature importance (standardized coefficients) ===')
print(f'{"Feature":<35s} {"Coefficient":>12s} {"Abs Impact":>10s}')
print('-' * 58)
coefs = list(zip(all_feat_cols, lr_full.coef_[0]))
coefs.sort(key=lambda x: abs(x[1]), reverse=True)
for name, coef in coefs:
    print(f'{name:<35s} {coef:>12.4f} {abs(coef):>10.4f}')

# ===== 9. 推荐总结 =====
print('\n' + '='*70)
print('                    推荐方案总结')
print('='*70)

print('\n【立即可实现的新因子】(从现有数据就能算)')
print('-' * 50)
implementable = []
for fr in feature_results:
    if abs(fr['corr_y']) > 0.03 and abs(fr['corr_score']) < 0.5:
        direction = '正向' if fr['corr_y'] > 0 else '反向'
        implementable.append(fr)
        print(f'  {fr["feature"]}: 与衰退相关性={fr["corr_y"]:.4f} ({direction}), 与现有得分相关性={fr["corr_score"]:.4f}')

print(f'\n  共 {len(implementable)} 个可立即实现的新因子')
if implementable:
    added_auc_gain = full_auc - base_auc_cv
    print(f'  预计AUC提升: {added_auc_gain:+.4f} (从{base_auc_cv:.4f}到{full_auc:.4f})')

print('\n【需要新数据才能计算的】(建议获取)')
print('-' * 50)
print('  1. 库存数据: 库存周转天数、呆滞库存占比 → 可识别"被动衰退"(库存积压+销量下降)')
print('  2. 竞品价格: 同品类市场价格 → 判断价格战是被动还是主动')
print('  3. 客户采购计划: 客户未来采购意向/合同 → 区分"暂时低谷"和"永久流失"')
print('  4. 产品生命周期标记: ERP中的EOL/停产标记 → 直接识别主动退市')
print('  5. 销售拜访记录: 销售跟进频率 → 投入不足 vs 需求透支')
print('  6. 产品质量/退货数据: 退货率、客诉 → 产品力下降的信号')
