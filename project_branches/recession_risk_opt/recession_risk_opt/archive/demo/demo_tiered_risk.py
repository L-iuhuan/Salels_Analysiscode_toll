"""
风险分层解读方案 — 解决"警报太多"和"不知道为什么报警"两个问题
"""
import pandas as pd, numpy as np, json, sys, os
sys.path.insert(0, r'E:\3-其他资料\数据分析\semiconductor_analysis')
sys.path.insert(0, r'E:\3-其他资料\数据分析\semiconductor_analysis\recession_risk_opt')
os.chdir(r'E:\3-其他资料\数据分析\semiconductor_analysis\recession_risk_opt')

df = pd.read_pickle('data/samples.pkl')
exec(open('pipeline.py', encoding='utf-8').read().split('if __name__')[0])

with open('models/best_config.json','r',encoding='utf-8') as f:
    best_cfg = json.load(f)

scorer = RiskScorer(best_cfg)

# ===== 为所有样本打分，并提取每个因子的明细 =====
records = []
for _, row in df.iterrows():
    f = row.to_dict()
    w_adj, f_scores = scorer._compute_unreliable_weights(f)
    total = scorer.score(f)
    
    r = {
        'product_id': f['product_id'],
        'date_month': f['date_month'],
        'portrait': f['portrait'],
        'y': f['y'],
        'total_score': total,
        'growth_rate': f.get('growth_rate', 0) * 100,
        'decay_pp': f.get('decay_pp', 0),
        'self_health': f.get('self_health', 0) * 100,
        'slope_ratio': f.get('slope_ratio', 0) * 100,
        'cv': f.get('cv', 0),
        'asp_slope': f.get('asp_slope', 0) * 100,
    }
    # 各因子贡献 = 得分 × 权重 (对总分的贡献)
    for k, wk in w_adj.items():
        fs = f_scores.get(k, 0)
        r[f'{k}_score'] = fs
        r[f'{k}_contrib'] = round(fs * wk, 1)
    records.append(r)

detail = pd.DataFrame(records)

# ===== 设计多层风险分级 =====
# 用得分分布的自然断点（而不是一刀切）
p25 = np.percentile(detail['total_score'], 25)
p50 = np.percentile(detail['total_score'], 50)
p75 = np.percentile(detail['total_score'], 75)
p90 = np.percentile(detail['total_score'], 90)

print(f'Score distribution: P25={p25:.1f}, P50={p50:.1f}, P75={p75:.1f}, P90={p90:.1f}')

def classify_tier(score, portrait):
    """多层风险分级：用得分+画像联合判定"""
    # 衰退期自动提一级
    if portrait == '衰退期':
        score_adj = score + 10
    elif portrait in ['隐性衰退','预警增长']:
        score_adj = score + 5
    elif portrait in ['夕阳产品']:
        score_adj = score + 3
    else:
        score_adj = score
    
    if score_adj >= 50:
        return 'action', '处置'     # 红色：需要立即行动
    elif score_adj >= 38:
        return 'warning', '预警'    # 橙色：本周内关注
    elif score_adj >= 28:
        return 'watch', '关注'      # 黄色：每月例行检查
    else:
        return 'normal', '正常'     # 绿色：无需特殊关注

detail['tier_code'] = [classify_tier(s, p)[0] for s, p in zip(detail['total_score'], detail['portrait'])]
detail['tier_label'] = [classify_tier(s, p)[1] for s, p in zip(detail['total_score'], detail['portrait'])]

# ===== 因子归因解读引擎 =====
def generate_explanation(row):
    """基于因子贡献度生成白话解读"""
    parts = []
    
    score = row['total_score']
    portrait = row['portrait']
    
    # 找出贡献最大的因子
    factors = {
        'f1': ('毛利率斜率', row.get('f1_score', 0), row.get('f1_contrib', 0),
               f"近12月毛利率以{row.get('slope_ratio', 0):+.2f}%/月的速度{'下降' if row.get('slope_ratio', 0) < 0 else '上升'}"),
        'f3': ('订货波动', row.get('f3_score', 0), row.get('f3_contrib', 0),
               f"订货量波动程度CV={row.get('cv', 0):.2f}{'，波动较大' if row.get('cv', 0) > 0.5 else '，较为稳定'}"),
        'f4': ('增速衰减', row.get('f4_score', 0), row.get('f4_contrib', 0),
               f"近3月增速比近12月增速{'衰减了' if row.get('decay_pp', 0) < 0 else '加速了'}{abs(row.get('decay_pp', 0)):.0f}个百分点"),
        'f5': ('盈利健康', row.get('f5_score', 0), row.get('f5_contrib', 0),
               f"当前毛利率仅达到历史峰值的{row.get('self_health', 0):.0f}%"),
        'f6': ('ASP趋势', row.get('f6_score', 0), row.get('f6_contrib', 0),
               f"均价以{row.get('asp_slope', 0):+.2f}%/月的趋势{'下行' if row.get('asp_slope', 0) < 0 else '平稳'}"),
    }
    
    # 按贡献排序
    ranked = sorted(factors.items(), key=lambda x: x[1][2], reverse=True)
    
    # 画像背景
    portrait_desc = {
        '成长期': '产品处于量利齐升的成长期',
        '健康扩张': '产品规模在扩大但利润率需关注',
        '预警增长': '销量增长掩盖了利润恶化——这是一个危险信号',
        '现金牛': '产品稳定贡献利润',
        '利润优化': '规模稳定，盈利能力健康',
        '隐性衰退': '表面上稳定，实际上利润正在被侵蚀',
        '主动收缩': '销量下降但利润好转，可能是主动清退低毛利客户',
        '夕阳产品': '需求正在消退',
        '衰退期': '产品量利双跌，已进入衰退通道',
    }
    
    parts.append(f"【画像】{portrait_desc.get(portrait, portrait)}")
    
    # 主导风险因子
    top1 = ranked[0]
    top2 = ranked[1] if len(ranked) > 1 else None
    top1_name, top1_score, top1_contrib, top1_desc = top1[1]
    
    if top1_score >= 70:
        severity = "严重"
    elif top1_score >= 40:
        severity = "明显"
    else:
        severity = "轻微"
    
    parts.append(f"【主要问题】{top1_name}存在{severity}异常：{top1_desc}")
    
    if top2 and top2[1][1] >= 50:
        parts.append(f"【次要问题】{top2[1][0]}也存在一定压力：{top2[1][3]}")
    
    # 方向性指示
    growth = row.get('growth_rate', 0)
    decay = row.get('decay_pp', 0)
    
    if decay < -10 and growth < 0:
        parts.append("【趋势】增速正在加速恶化，预计未来60天销量可能继续下滑")
    elif decay < -5:
        parts.append("【趋势】近期增速出现衰减迹象，需密切关注后续走势")
    elif growth > 50:
        parts.append("【趋势】当前高速增长，短期内衰退风险可控，但需防范增速自然回落")
    
    # 建议
    suggestions = []
    if top1_name == '盈利健康' and top1_score >= 60:
        suggestions.append("核查成本结构，评估是否有降价促销或原材料上涨")
    if top1_name == '增速衰减' and top1_score >= 60:
        suggestions.append("与销售确认客户需求是否变化，评估是否需要促销激活")
    if top1_name == '毛利率斜率' and top1_score >= 60:
        suggestions.append("分析降价原因：是主动降价抢市场，还是被迫跟进竞争对手")
    if top1_name == '订货波动' and top1_score >= 60:
        suggestions.append("检查客户集中度，确认是否有大客户流失或采购周期变化")
    if portrait == '衰退期':
        suggestions.append("评估是否安排退市计划或迭代替代型号")
    
    if suggestions:
        parts.append(f"【建议】{'；'.join(suggestions)}")
    
    return '\n'.join(parts)

# ===== 演示：各风险等级的样例 =====
print('\n' + '='*70)
print('                       各风险等级典型产品示例')
print('='*70)

for tier_label, color in [('处置', '[RED]'), ('预警', '[ORG]'), ('关注', '[YLW]'), ('正常', '[GRN]')]:
    tier_df = detail[detail['tier_label'] == tier_label]
    if len(tier_df) == 0:
        continue
    
    print(f'\n{color} {tier_label}等级 ({len(tier_df)}个观测点, {len(tier_df)/len(detail)*100:.1f}%)')
    print('-' * 50)
    
    # 找3个有代表性的
    samples = tier_df.sort_values('total_score', ascending=False).head(3)
    for _, row in samples.iterrows():
        explanation = generate_explanation(row)
        pid = str(row['product_id'])[:30]
        print(f'  产品: {pid}')
        print(f'  时间: {row["date_month"]} | 画像: {row["portrait"]} | 得分: {row["total_score"]:.0f}')
        print(f'  实际{"衰退" if row["y"]==1 else "正常"}')
        for line in explanation.split('\n'):
            print(f'  {line}')
        print()

# ===== 汇总统计 =====
print('\n' + '='*70)
print('                       风险分级汇总')
print('='*70)

tier_summary = detail.groupby('tier_label').agg(
    观测点数=('total_score', 'count'),
    占比=('total_score', lambda x: f'{len(x)/len(detail)*100:.1f}%'),
    平均得分=('total_score', 'mean'),
    实际衰退率=('y', lambda x: f'{x.mean()*100:.1f}%'),
).reindex(['处置', '预警', '关注', '正常'])

print(tier_summary.to_string())

# ===== 各等级的主导因子分析 =====
print('\n' + '='*70)
print('                  各风险等级的主导因子分布')
print('='*70)

for tier in ['处置', '预警', '关注']:
    tier_df = detail[detail['tier_label'] == tier]
    if len(tier_df) == 0:
        continue
    
    # 找每个样本贡献最大的因子
    factor_cols = ['f1_contrib','f3_contrib','f4_contrib','f5_contrib','f6_contrib']
    factor_names = ['毛利率斜率','订货波动','增速衰减','盈利健康','ASP趋势']
    
    dominant = []
    for _, row in tier_df.iterrows():
        max_f = max(factor_cols, key=lambda c: row[c])
        dominant.append(factor_names[factor_cols.index(max_f)])
    
    print(f'\n{tier}等级 ({len(tier_df)}个) 主导因子分布:')
    dom_series = pd.Series(dominant).value_counts()
    for k, v in dom_series.items():
        print(f'  {k}: {v}次 ({v/len(tier_df)*100:.1f}%)')
