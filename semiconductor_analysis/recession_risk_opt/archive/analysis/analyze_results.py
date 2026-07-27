import pandas as pd, numpy as np, json, sys, os
sys.path.insert(0, r'E:\3-其他资料\数据分析\semiconductor_analysis')
sys.path.insert(0, r'E:\3-其他资料\数据分析\semiconductor_analysis\recession_risk_opt')
os.chdir(r'E:\3-其他资料\数据分析\semiconductor_analysis\recession_risk_opt')

df = pd.read_pickle('data/samples.pkl')

# Reload RiskScorer
exec(open('pipeline.py', encoding='utf-8').read().split('if __name__')[0])
with open('models/best_config.json','r',encoding='utf-8') as f:
    best_cfg = json.load(f)

opt_scorer = RiskScorer(best_cfg)
def_scorer = RiskScorer()

# Compute scores
opt_scores = np.array([opt_scorer.score(r.to_dict()) for _,r in df.iterrows()])
def_scores = np.array([def_scorer.score(r.to_dict()) for _,r in df.iterrows()])
df['opt_score'] = opt_scores
df['def_score'] = def_scores

def get_level(s, cuts):
    if s <= cuts[0]: return 'low'
    elif s <= cuts[1]: return 'mid'
    elif s <= cuts[2]: return 'high'
    else: return 'extreme'

df['opt_level'] = [get_level(s, best_cfg['cut_points']) for s in opt_scores]
df['def_level'] = [get_level(s, [25,50,75]) for s in def_scores]

print('=== Risk distribution (old) ===')
print(df['def_level'].value_counts().to_string())
print()
print('=== Risk distribution (new) ===')
print(df['opt_level'].value_counts().to_string())

warn_thresh = 25
df['opt_warn'] = opt_scores > warn_thresh
df['def_warn'] = def_scores > 50

def_warn_pct = df['def_warn'].mean() * 100
opt_warn_pct = df['opt_warn'].mean() * 100
print()
print(f'Old warning rate (>50): {df["def_warn"].sum()} ({def_warn_pct:.1f}%)')
print(f'New warning rate (>25): {df["opt_warn"].sum()} ({opt_warn_pct:.1f}%)')

print()
print('=== Risk score by portrait ===')
print(df.groupby('portrait')['opt_score'].agg(['mean','std','count']).sort_values('mean', ascending=False).round(1).to_string())

df['correct_warn'] = (df['opt_warn'] == True) & (df['y'] == 1)
df['correct_safe'] = (df['opt_warn'] == False) & (df['y'] == 0)
df['miss'] = (df['opt_warn'] == False) & (df['y'] == 1)
df['false_alarm'] = (df['opt_warn'] == True) & (df['y'] == 0)
df['old_miss'] = (df['def_warn'] == False) & (df['y'] == 1)
df['old_false'] = (df['def_warn'] == True) & (df['y'] == 0)

print()
print('=== Prediction accuracy ===')
print(f'Correct warn (hit): {df["correct_warn"].sum()}')
print(f'Correct safe: {df["correct_safe"].sum()}')
print(f'Miss (old): {df["old_miss"].sum()}')
print(f'Miss (new): {df["miss"].sum()}')
print(f'False alarm (old): {df["old_false"].sum()}')
print(f'False alarm (new): {df["false_alarm"].sum()}')

# Hit examples
print()
print('=== Top 5 hit examples (correctly warned) ===')
hits = df[df['correct_warn']].sort_values('opt_score', ascending=False).head(5)
for _, r in hits.iterrows():
    pid = str(r['product_id'])[:25]
    print(f"  Product:{pid}  Month:{r['date_month']}  Portrait:{r['portrait']}  Score:{r['opt_score']:.0f}  Growth:{r.get('growth_rate',0)*100:.0f}%  SelfHealth:{r.get('self_health',0)*100:.0f}%")

# Miss examples
print()
print('=== Top 3 miss examples (new model missed) ===')
misses = df[df['miss']].sort_values('opt_score', ascending=True).head(3)
for _, r in misses.iterrows():
    pid = str(r['product_id'])[:25]
    print(f"  Product:{pid}  Month:{r['date_month']}  Portrait:{r['portrait']}  Score:{r['opt_score']:.0f}  Growth:{r.get('growth_rate',0)*100:.0f}%")

# Old miss examples 
print()
print('=== Top 3 old misses that new model caught ===')
was_missed = df[(df['old_miss']==True) & (df['opt_warn']==True)].sort_values('opt_score', ascending=False).head(3)
for _, r in was_missed.iterrows():
    pid = str(r['product_id'])[:25]
    print(f"  Product:{pid}  Month:{r['date_month']}  OldScore:{r['def_score']:.0f}  NewScore:{r['opt_score']:.0f}  Portrait:{r['portrait']}")

# Decline products
print()
print('=== Decline products (portrait=shuai tui qi) ===')
decline = df[df['portrait'] == '衰退期']
if len(decline) > 0:
    print(f'Samples: {len(decline)}')
    print(f'Avg score: {decline["opt_score"].mean():.1f}')
    print(f'Actual decline rate: {decline["y"].mean()*100:.1f}%')
    print(f'Warned: {decline["opt_warn"].mean()*100:.1f}%')

print()
print('=== Healthy products ===')
healthy = df[df['portrait'].isin(['健康扩张','成长期','利润优化'])]
if len(healthy) > 0:
    print(f'Samples: {len(healthy)}')
    print(f'Avg score: {healthy["opt_score"].mean():.1f}')
    print(f'Actual decline rate: {healthy["y"].mean()*100:.1f}%')
    print(f'Warned: {healthy["opt_warn"].mean()*100:.1f}%')

# Monthly trend (first few and last few)
print()
print('=== Monthly trend (sample) ===')
df['_ts'] = pd.to_datetime(df['date_month'].astype(str).str[:7]+'-01')
monthly = df.groupby(df['_ts'].dt.to_period('M')).agg(
    n=('y','count'), actual_rate=('y','mean'), warn_rate=('opt_warn','mean'),
    opt_score_mean=('opt_score','mean')
).sort_index()
print(monthly.iloc[::4].to_string())

# Summary
print()
print('=== KEY SUMMARY ===')
print(f'Samples: {len(df)}, Products: {df["product_id"].nunique()}')
print(f'Actual decline rate: {df["y"].mean()*100:.1f}%')
print(f'Old AUC: 0.5026, New AUC: 0.5321 (+{0.5321-0.5026:.4f})')
print(f'Old miss count: {df["old_miss"].sum()}, New miss count: {df["miss"].sum()} (reduced by {df["old_miss"].sum()-df["miss"].sum()})')
print(f'Most risky portrait: {df.groupby("portrait")["opt_score"].mean().idxmax()} ({df.groupby("portrait")["opt_score"].mean().max():.1f})')
print(f'Safest portrait: {df.groupby("portrait")["opt_score"].mean().idxmin()} ({df.groupby("portrait")["opt_score"].mean().min():.1f})')
