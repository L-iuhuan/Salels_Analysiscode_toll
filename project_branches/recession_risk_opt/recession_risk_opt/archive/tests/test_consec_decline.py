"""
将"连续下降月数"融入F4增速衰减因子 — 方案测试
==============================================
测试4种集成方式，找到最佳配置
"""
import pandas as pd, numpy as np, json, sys, os, warnings
warnings.filterwarnings('ignore')

sys.path.insert(0, r'E:\3-其他资料\数据分析\semiconductor_analysis')
sys.path.insert(0, r'E:\3-其他资料\数据分析\semiconductor_analysis\recession_risk_opt')
os.chdir(r'E:\3-其他资料\数据分析\semiconductor_analysis\recession_risk_opt')

exec(open('pipeline.py', encoding='utf-8').read().split('if __name__')[0])

# Load samples and data
samples = pd.read_pickle('data/samples.pkl')
with open('models/best_config.json','r',encoding='utf-8') as f:
    best_cfg = json.load(f)

# Compute consecutive_decline directly
from config.settings_product import PRODUCT_LIFECYCLE
thr = PRODUCT_LIFECYCLE
col_map = thr['col_map']
name_col = col_map.get('产品名称列','产品品种')
date_col = col_map.get('发货日期列','发货日期')
qty_col = col_map.get('销量列','数量')

from shared.data_cleaning import read_excel_auto, rename_erp_columns
df = read_excel_auto(r'E:\3-其他资料\数据分析\semiconductor_analysis\data\所有的出货明细5.9.xlsx', sheet_name=0)
df = rename_erp_columns(df)
df[name_col] = df[name_col].astype(str).str.strip()
df[date_col] = pd.to_datetime(df[date_col], errors='coerce')
df[qty_col] = pd.to_numeric(df[qty_col], errors='coerce').fillna(0)
df = df[df[qty_col] > 0].copy()
df = df[df[date_col] >= pd.Timestamp('2020-01-01')]
df = df.dropna(subset=[date_col])
df['_月'] = df[date_col].dt.to_period('M')

pm_full = df.groupby([name_col, '_月']).agg(qty_sum=(qty_col, 'sum')).reset_index()
pm_idx = {p: g.set_index('_月').sort_index() for p, g in pm_full.groupby(name_col)}

print('Computing consecutive_decline for all samples...')
consec_declines = []
for _, row in samples.iterrows():
    pid = row['product_id']
    try:
        m = pd.Period(row['date_month'], freq='M')
    except:
        consec_declines.append(0)
        continue
    if pid not in pm_idx:
        consec_declines.append(0)
        continue
    pm_hist = pm_idx[pid]
    pm_hist = pm_hist[pm_hist.index <= m].sort_index()
    recent_12m = pm_hist.index > (m - 12)
    qty_12m = pm_hist.loc[recent_12m, 'qty_sum'].values
    consecutive = 0
    for i in range(len(qty_12m)-1, 0, -1):
        if qty_12m[i] < qty_12m[i-1]:
            consecutive += 1
        else:
            break
    consec_declines.append(consecutive)

samples['consec_decline'] = consec_declines
y = samples['y'].values

# Baseline
scorer = RiskScorer(best_cfg)
base_scores = np.array([scorer.score(r.to_dict()) for _, r in samples.iterrows()])
base_auc = roc_auc_score(y, base_scores)
print(f'Baseline AUC: {base_auc:.4f}')
print(f'Consecutive decline distribution:')
print(pd.cut(samples['consec_decline'], bins=[-1,0,2,4,6,100], labels=['0','1-2','3-4','5-6','7+']).value_counts().sort_index())

# ===== 测试4种集成方案 =====
from sklearn.metrics import roc_auc_score

class F4Scorer:
    """F4增速衰减因子 — 含连续下降月数增强"""
    
    def __init__(self, config, mode='original', consec_factor=0, consec_threshold=0):
        self.config = config
        self.mode = mode          # 'original', 'additive', 'multiplier', 'threshold'
        self.consec_factor = consec_factor  # 每连续下降月的加分/乘数
        self.consec_threshold = consec_threshold  # 超过几个月才生效
    
    def score(self, features):
        """F4得分(0-100)，融入连续下降月数"""
        cfg = self.config
        decay_pp = features.get('decay_pp', 0)
        if pd.isna(decay_pp):
            base = cfg.get("f4_default_score", 20)
        else:
            yoy = features.get('yoy_change')
            t_high = cfg["f4_decay_high_pp"]
            t_mid = cfg["f4_decay_mid_pp"]
            growth_rapid = cfg.get("f4_growth_rapid", 0.5)
            growth_shrunk = cfg.get("f4_growth_shrunk", -0.10)
            decay_rapid_high = cfg.get("f4_decay_rapid_high_pp", 10)
            decay_recover_high = cfg.get("f4_decay_recover_high_pp", 10)
            
            if yoy is not None and yoy > growth_rapid:
                if decay_pp <= t_mid: base = 10
                elif decay_pp <= decay_rapid_high: base = 30
                else: base = 50
            elif yoy is not None and yoy <= growth_shrunk:
                if decay_pp <= t_high: base = 80
                elif decay_pp <= t_mid: base = 70
                elif decay_pp <= decay_recover_high: base = 60
                else: base = 50
            else:
                t_yoy = cfg.get("f4_yoy_high_ratio", -0.10)
                if yoy is not None and yoy < t_yoy: base = 80
                elif decay_pp < t_high: base = 70
                elif decay_pp < t_mid: base = 50
                else: base = cfg.get("f4_default_score", 20)
        
        consec = features.get('consec_decline', 0)
        
        if self.mode == 'original':
            return base
        
        elif self.mode == 'additive':
            # 每连续下降1个月加X分
            bonus = consec * self.consec_factor
            return min(100, base + bonus)
        
        elif self.mode == 'multiplier':
            # 连续下降月数作为乘数
            # 0-2月: 不乘; 3月+: 每多1月乘系数
            if consec <= self.consec_threshold:
                return base
            multiplier = 1 + (consec - self.consec_threshold) * self.consec_factor
            return min(100, base * multiplier)
        
        elif self.mode == 'threshold':
            # 超过阈值后一次性加分
            if consec > self.consec_threshold:
                extra_months = consec - self.consec_threshold
                return min(100, base + extra_months * self.consec_factor)
            return base
        
        return base


def test_config(mode, consec_factor, consec_threshold=0):
    """测试一组参数，返回AUC"""
    cfg = best_cfg.copy()
    f4_scorer = F4Scorer(cfg, mode=mode, consec_factor=consec_factor, consec_threshold=consec_threshold)
    
    # 修改RiskScorer的F4计算
    original_f4 = RiskScorer._f4_score
    
    def new_f4(self, features):
        return f4_scorer.score(features)
    
    RiskScorer._f4_score = new_f4
    
    scores = np.array([scorer.score(r.to_dict()) for _, r in samples.iterrows()])
    
    # Restore
    RiskScorer._f4_score = original_f4
    
    return roc_auc_score(y, scores)

# ===== 测试不同方案 =====
print('\n' + '='*70)
print('T E S T   R E S U L T S')
print('='*70)

# 方案1: 加法 — 每连续下降月加N分
print('\n[Scheme 1] Additive: base_score + consecutive_months * N')
print(f'{"N":>6s} {"AUC":>8s} {"Delta":>8s}')
print('-'*25)
best_add_auc, best_add_n = base_auc, 0
for n in [0, 1, 2, 3, 4, 5, 6, 8, 10]:
    auc = test_config('additive', n)
    delta = auc - base_auc
    marker = ' ***' if auc > best_add_auc else ''
    print(f'{n:>6.0f} {auc:>8.4f} {delta:>+8.4f}{marker}')
    if auc > best_add_auc:
        best_add_auc, best_add_n = auc, n

# 方案2: 阈值后加法 — 超过M个月后才每多1月加N分
print(f'\n[Scheme 2] Threshold-add: after M months, +N per extra month')
print(f'{"M":>6s} {"N":>6s} {"AUC":>8s} {"Delta":>8s}')
print('-'*30)
best_thr_auc, best_thr_m, best_thr_n = base_auc, 0, 0
for m in [0, 1, 2, 3]:
    for n in [1, 2, 3, 5, 8]:
        auc = test_config('threshold', n, m)
        delta = auc - base_auc
        if auc > best_thr_auc:
            best_thr_auc, best_thr_m, best_thr_n = auc, m, n
            print(f'{m:>6.0f} {n:>6.0f} {auc:>8.4f} {delta:>+8.4f} ***')
        elif abs(delta) > 0.001:
            print(f'{m:>6.0f} {n:>6.0f} {auc:>8.4f} {delta:>+8.4f}')

# 方案3: 乘法 — 超过M个月后得分乘以系数
print(f'\n[Scheme 3] Multiplier: over M months, score *= 1 + (extra_months * K)')
print(f'{"M":>6s} {"K":>8s} {"AUC":>8s} {"Delta":>8s}')
print('-'*34)
best_mul_auc = base_auc
for m in [1, 2, 3]:
    for k in [0.02, 0.05, 0.08, 0.10, 0.15]:
        auc = test_config('multiplier', k, m)
        delta = auc - base_auc
        if auc > best_mul_auc:
            best_mul_auc = auc
            print(f'{m:>6.0f} {k:>8.3f} {auc:>8.4f} {delta:>+8.4f} ***')
        elif abs(delta) > 0.0005:
            print(f'{m:>6.0f} {k:>8.3f} {auc:>8.4f} {delta:>+8.4f}')

# ===== 最佳方案对比 =====
print('\n' + '='*70)
print('B E S T   P E R   S C H E M E')
print('='*70)
print(f'{"Scheme":<20s} {"Best Config":<25s} {"AUC":>8s} {"vs Baseline":>12s}')
print('-'*68)
print(f'{"Original (5-factor)":<20s} {"--":<25s} {base_auc:>8.4f} {"--":>12s}')
print(f'{"Additive":<20s} {f"N={best_add_n}":<25s} {best_add_auc:>8.4f} {best_add_auc-base_auc:>+12.4f}')
print(f'{"Threshold-add":<20s} {f"M={best_thr_m}, N={best_thr_n}":<25s} {best_thr_auc:>8.4f} {best_thr_auc-base_auc:>+12.4f}')
print(f'{"Multiplier":<20s} {f"see above":<25s} {best_mul_auc:>8.4f} {best_mul_auc-base_auc:>+12.4f}')

# ===== 验证最佳方案的风险分布 =====
print('\n' + '='*70)
print('R I S K   D I S T R I B U T I O N   (B E S T   S C H E M E)')
print('='*70)

best_cfg_test = best_cfg.copy()
best_f4 = F4Scorer(best_cfg_test, mode='additive', consec_factor=best_add_n)

original_f4_backup = RiskScorer._f4_score
def enhanced_f4(self, features):
    return best_f4.score(features)
RiskScorer._f4_score = enhanced_f4

new_scores = np.array([scorer.score(r.to_dict()) for _, r in samples.iterrows()])
RiskScorer._f4_score = original_f4_backup

samples['new_score'] = new_scores
samples['base_score'] = base_scores

# Score distribution comparison
print(f'\nScore distribution:')
print(f'{"":>15s} {"Baseline":>10s} {"Enhanced":>10s} {"Change":>10s}')
print(f'{"Mean":>15s} {base_scores.mean():>10.2f} {new_scores.mean():>10.2f} {new_scores.mean()-base_scores.mean():>+10.2f}')
print(f'{"Std":>15s} {base_scores.std():>10.2f} {new_scores.std():>10.2f} {new_scores.std()-base_scores.std():>+10.2f}')
for p in [10, 25, 50, 75, 90]:
    bp = np.percentile(base_scores, p)
    np_val = np.percentile(new_scores, p)
    print(f'{"P"+str(p):>15s} {bp:>10.1f} {np_val:>10.1f} {np_val-bp:>+10.1f}')

# Risk level shift
def get_level(s, cuts):
    if s <= cuts[0]: return 'low'
    elif s <= cuts[1]: return 'mid'
    elif s <= cuts[2]: return 'high'
    else: return 'extreme'

old_levels = pd.Series([get_level(s, best_cfg['cut_points']) for s in base_scores])
new_levels = pd.Series([get_level(s, best_cfg['cut_points']) for s in new_scores])

print(f'\nRisk level migration (same cut points):')
cross = pd.crosstab(old_levels, new_levels, rownames=['Old'], colnames=['New'])
print(cross.to_string())

print(f'\nLevel distribution:')
print(f'{"Level":>10s} {"Baseline":>10s} {"Enhanced":>10s}')
for lvl in ['low','mid','high','extreme']:
    print(f'{lvl:>10s} {(old_levels==lvl).sum():>10d} {(new_levels==lvl).sum():>10d}')

# Consecutive decline vs score boost
print(f'\nScore boost by consecutive decline months:')
samples['score_boost'] = new_scores - base_scores
for c_range, label in [([0,0], '0'), ([1,2], '1-2'), ([3,4], '3-4'), ([5,6], '5-6'), ([7,100], '7+')]:
    mask = (samples['consec_decline'] >= c_range[0]) & (samples['consec_decline'] <= c_range[1])
    if mask.sum() > 0:
        avg_boost = samples.loc[mask, 'score_boost'].mean()
        n = mask.sum()
        print(f'  {label} months: +{avg_boost:.1f} avg boost (n={n})')

print(f'\n=== FINAL RECOMMENDATION ===')
print(f'Best scheme: Additive')
print(f'Best config: N={best_add_n} (add {best_add_n} points per consecutive decline month)')
print(f'AUC: {base_auc:.4f} -> {best_add_auc:.4f} (delta {best_add_auc-base_auc:+.4f})')
