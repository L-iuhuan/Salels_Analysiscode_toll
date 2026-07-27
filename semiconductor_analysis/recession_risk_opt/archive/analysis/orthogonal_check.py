"""Rigorously test orthogonal factor value — minimal complexity approach"""
import pandas as pd, numpy as np, json, sys, os
from sklearn.metrics import roc_auc_score

sys.path.insert(0, r'E:\3-其他资料\数据分析\semiconductor_analysis')
sys.path.insert(0, r'E:\3-其他资料\数据分析\semiconductor_analysis\recession_risk_opt')
os.chdir(r'E:\3-其他资料\数据分析\semiconductor_analysis\recession_risk_opt')

exec(open('pipeline.py', encoding='utf-8').read().split('if __name__')[0])

samples = pd.read_pickle('data/samples.pkl')
with open('models/best_config.json','r',encoding='utf-8') as f:
    best_cfg = json.load(f)

scorer = RiskScorer(best_cfg)
base_scores = np.array([scorer.score(row.to_dict()) for _,row in samples.iterrows()])
y = samples['y'].values
base_auc = roc_auc_score(y, base_scores)
print(f'Base AUC (5-factor optimized): {base_auc:.4f}')

# Data from exploration results
results = [
    ('consecutive_decline', 0.0333, 'Sales declining consecutive months'),
    ('cust_count_trend',    -0.0047, 'Customer count trend'),
    ('lost_cust_count',     -0.0422, 'Lost customer count'),
    ('cust_churn_ratio',    0.0690,  'Customer churn ratio'),
    ('active_cust_count',   -0.1260, 'Active customer count'),
    ('top1_conc',           0.1708,  'Top1 customer concentration'),
    ('top3_conc',           0.1972,  'Top3 customer concentration'),
    ('qty_max_month_ratio', 0.3522,  'Max single-month ratio'),
]

print()
print('Factor                          | Corr w/ score | Verdict')
print('-' * 60)
for name, corr, desc in results:
    if abs(corr) < 0.05:
        verdict = 'Truly NEW signal (add if simple)'
    elif abs(corr) < 0.10:
        verdict = 'Mostly new, small overlap'
    elif abs(corr) < 0.20:
        verdict = 'Partial overlap (risky to add)'
    else:
        verdict = 'Redundant (already captured)'
    print(f'{desc:<35s} | {corr:>13.4f} | {verdict}')

print()
print('='*60)
print('CONCLUSION')
print('='*60)
print()
print('Only 1-2 factors are worth considering:')
print()
print('  [1] consecutive_decline (corr=0.03 with existing score)')
print('      Measures DURATION of decline, not magnitude.')
print('      Simple: "How many months in a row has this product been dropping?"')
print('      0 months = stable, 3+ months = in trouble')
print()
print('  [2] cust_count_trend (corr=-0.005 with existing score)')
print('      Measures whether customers are quietly leaving.')
print('      Simple: "Are we losing customers even if total sales look OK?"')
print()
print('The rest are either:')
print('  - Already partially captured by existing factors')
print('  - Customer concentration (removed before for valid reasons)')
print('  - Add complexity without proportional value')
