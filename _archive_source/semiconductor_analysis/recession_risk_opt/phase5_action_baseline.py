"""
Phase 5: 业务行动基线
======================
从历史数据中提取衰退前后的业务行动模式，建立风险等级→行动建议的框架。

分析维度:
1. 衰退后恢复模式：区分"快速恢复"、"缓慢恢复"、"持续恶化"三类
2. 恢复期行动特征：价格调整、毛利率修复、客户结构变化等
3. 行动基线矩阵：各风险等级对应的预期行动
"""

import os, sys, warnings
from datetime import datetime
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
# 中文字体配置
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DengXian', 'Noto Sans SC']
plt.rcParams['axes.unicode_minus'] = False
plt.rcParams['font.family'] = 'sans-serif'
from sklearn.cluster import KMeans
from collections import defaultdict, Counter

warnings.filterwarnings('ignore')

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(PROJECT_ROOT))
OUTPUT_DIR = os.path.join(os.path.dirname(PROJECT_ROOT), 'test_output')
os.makedirs(OUTPUT_DIR, exist_ok=True)

np.random.seed(42)

FEATURE_LABELS = {
    'recent_margin': '毛利率',
    'growth_rate': '销量增速',
    'slope_ratio': '毛利率趋势',
    'f1_score': 'F1 毛利率斜率',
    'f3_score': 'F3 订货波动',
    'f4_score': 'F4 增速衰减',
    'f5_score': 'F5 自比健康度',
    'f6_score': 'F6 ASP趋势',
    'asp_slope': 'ASP趋势',
    'consecutive_months': '连续下降月数',
    'cv': '订货变异系数',
}

DECLINE_RECOVERY_WINDOW = 12  # 衰退前后各看12个月


def load_data():
    """加载完整数据"""
    raw = pd.read_pickle(os.path.join(PROJECT_ROOT, 'data', 'samples.pkl'))
    print(f"数据加载: {raw.shape}")
    return raw


def classify_recovery(df):
    """
    对每个经历过衰退的产品，分析其恢复模式。
    恢复模式分类:
    - 快速恢复: 衰退后6个月内恢复到衰退前水平的80%以上
    - 缓慢恢复: 衰退后12个月内部分恢复
    - 持续恶化: 衰退后继续恶化或未恢复
    """
    print("\n" + "=" * 60)
    print("分析衰退恢复模式")
    print("=" * 60)

    recovery_patterns = []

    for prod, grp in df.groupby('product_id'):
        grp = grp.sort_values('date_month').reset_index(drop=True)
        if grp['y_decline_6m'].max() != 1:
            continue

        # 找到首次衰退点
        decline_idx = grp['y_decline_6m'].values.argmax()
        if decline_idx < 3:
            continue

        # 衰退前毛利率基线（衰退前3-9月的均值）
        pre_margins = grp['recent_margin'].iloc[max(0, decline_idx-9):decline_idx].dropna().values
        if len(pre_margins) < 3:
            continue
        baseline_margin = np.median(pre_margins)

        # 衰退后轨迹
        post = grp.iloc[decline_idx:decline_idx + 13]  # 衰退后最多12个月
        post_margins = post['recent_margin'].values
        post_months = post['date_month'].values

        # 找最低点和恢复情况
        min_margin = np.min(post_margins) if len(post_margins) > 0 else np.nan
        min_idx = np.argmin(post_margins) if len(post_margins) > 0 else -1

        # 6个月后恢复率
        if len(post_margins) >= 7:
            margin_6m = post_margins[6]
            recovery_6m = margin_6m / baseline_margin if baseline_margin > 0 else np.nan
        else:
            margin_6m = np.nan
            recovery_6m = np.nan

        # 12个月后恢复率
        if len(post_margins) >= 13:
            margin_12m = post_margins[12]
            recovery_12m = margin_12m / baseline_margin if baseline_margin > 0 else np.nan
        else:
            margin_12m = np.nan
            recovery_12m = np.nan

        # 衰退持续时间（从衰退开始到恢复>80%基线）
        duration = None
        for i in range(1, len(post_margins)):
            if post_margins[i] >= baseline_margin * 0.8:
                duration = i
                break

        # 产品生命周期阶段
        portrait = grp['portrait'].iloc[decline_idx] if decline_idx < len(grp) else '未知'

        # 恢复模式分类
        if recovery_6m is not None and recovery_6m >= 0.8:
            pattern = '快速恢复'
        elif recovery_12m is not None and recovery_12m >= 0.6:
            pattern = '缓慢恢复'
        elif duration is not None and duration <= 12:
            pattern = '缓慢恢复'
        else:
            pattern = '持续恶化'

        recovery_patterns.append({
            'product_id': prod,
            'decline_month': grp['date_month'].iloc[decline_idx],
            'decline_portrait': portrait,
            'baseline_margin': baseline_margin,
            'min_margin': min_margin,
            'margin_drop_pct': (baseline_margin - min_margin) / baseline_margin * 100 if baseline_margin > 0 else np.nan,
            'recovery_6m': recovery_6m,
            'recovery_12m': recovery_12m,
            'recovery_duration_months': duration,
            'pattern': pattern,
            'total_history_months': len(grp),
        })

    rdf = pd.DataFrame(recovery_patterns)
    print(f"有衰退历史的产品: {len(rdf)}")

    if len(rdf) == 0:
        print("无有效数据，跳过")
        return rdf

    # 分布
    pattern_counts = rdf['pattern'].value_counts()
    for pat, cnt in pattern_counts.items():
        print(f"  {pat}: {cnt} ({cnt/len(rdf)*100:.1f}%)")

    return rdf


def analyze_action_signatures(df, rdf):
    """
    分析衰退前后的"行动特征"：
    - ASP变化（价格调整）
    - 毛利率变化（成本/定价调整）
    - 客户集中度变化（客户管理）
    - 订货模式变化（库存管理）
    """
    print("\n" + "=" * 60)
    print("提取行动特征基线")
    print("=" * 60)

    if len(rdf) == 0:
        return pd.DataFrame()

    action_records = []

    for _, row in rdf.iterrows():
        prod = row['product_id']
        decline_month = row['decline_month']
        pattern = row['pattern']

        pdf = df[df['product_id'] == prod].sort_values('date_month').reset_index(drop=True)
        decline_idx = pdf[pdf['date_month'] == decline_month].index[0] if decline_month in pdf['date_month'].values else -1
        if decline_idx < 0:
            continue

        # 衰退前6个月 vs 衰退后6个月 的指标变化
        pre_slice = pdf.iloc[max(0, decline_idx-6):decline_idx] if decline_idx >= 6 else pdf.iloc[:decline_idx]
        post_slice = pdf.iloc[decline_idx:min(len(pdf), decline_idx+7)]

        def median_or_nan(s):
            vals = s.dropna().values
            return np.median(vals) if len(vals) > 0 else np.nan

        action = {
            'product_id': prod,
            'decline_month': decline_month,
            'pattern': pattern,
        }

        # 关键指标变化
        metrics = {
            'recent_margin': '毛利率',
            'asp_slope': 'ASP趋势',
            'growth_rate': '销量增速',
            'consecutive_months': '连续下降月数',
        }
        for col, label in metrics.items():
            if col in pdf.columns:
                pre_val = median_or_nan(pre_slice[col])
                post_val = median_or_nan(post_slice[col])
                action[f'pre_{col}'] = pre_val
                action[f'post_{col}'] = post_val
                if pre_val is not None and not np.isnan(pre_val) and pre_val != 0:
                    action[f'change_{col}'] = (post_val - pre_val) / abs(pre_val) * 100
                else:
                    action[f'change_{col}'] = np.nan

        # 定价行为判断
        if 'asp_slope' in pdf.columns:
            pre_asp = median_or_nan(pre_slice['asp_slope'])
            post_asp = median_or_nan(post_slice['asp_slope'])
            if not np.isnan(pre_asp) and not np.isnan(post_asp):
                if post_asp > pre_asp + 0.02:
                    action['pricing_action'] = '提价'
                elif post_asp < pre_asp - 0.02:
                    action['pricing_action'] = '降价'
                else:
                    action['pricing_action'] = '价格稳定'
            else:
                action['pricing_action'] = '数据不足'

        action_records.append(action)

    adf = pd.DataFrame(action_records)
    print(f"有效行动记录: {len(adf)}")

    # 各恢复模式的行动特征
    if len(adf) > 0:
        print("\n各恢复模式的行动特征:")
        for pattern_name in ['快速恢复', '缓慢恢复', '持续恶化']:
            subset = adf[adf['pattern'] == pattern_name]
            if len(subset) == 0:
                continue
            print(f"\n  [{pattern_name}] ({len(subset)}个产品):")
            for col in ['recent_margin', 'asp_slope', 'growth_rate']:
                pre_avg = subset[f'pre_{col}'].mean()
                post_avg = subset[f'post_{col}'].mean()
                chg_avg = subset[f'change_{col}'].mean()
                print(f"    {FEATURE_LABELS.get(col, col)}: {pre_avg:.4f} -> {post_avg:.4f} ({chg_avg:+.1f}%)")

    return adf


def build_action_matrix(rdf, adf, df):
    """构建业务行动基线矩阵"""
    print("\n" + "=" * 60)
    print("构建行动基线矩阵")
    print("=" * 60)

    matrix = {}
    risk_levels = [
        ('低风险', 0, 34, '维持正常运营'),
        ('中风险', 35, 52, '加强监控，2周复查'),
        ('高风险', 53, 58, '准备干预，1周复查'),
        ('极高风险', 59, 100, '紧急干预，立即行动'),
    ]

    # 从恢复模式数据中推导行动建议
    for level_name, lo, hi, urgency in risk_levels:
        entry = {
            '风险等级': level_name,
            '风险分范围': f'{lo}-{hi}',
            '响应周期': urgency,
        }

        if level_name == '低风险':
            entry['建议行动'] = [
                '维持正常运营',
                '季度回顾因子趋势',
                '自动生成正常业务报告',
            ]
        elif level_name == '中风险':
            entry['建议行动'] = [
                '启动2周监控周期',
                '检查F1毛利率趋势和F3订货波动',
                '客户拜访确认订单预期',
                '如有2月以上连续下降，启动预警',
            ]
        elif level_name == '高风险':
            entry['建议行动'] = [
                '每周监控风险分变化',
                '成本复盘和价格策略调整',
                '客户挽留行动（重点客户拜访）',
                '准备安全库存调整方案',
                '启动跨部门（产品+销售+财务）会议',
            ]
        else:  # 极高风险
            entry['建议行动'] = [
                '立即启动退市/清仓评估',
                '促销清仓或替代新品导入',
                '评估是否做最后一批采购',
                '通知销售团队停止新项目导入',
                '启动产品生命周期终止流程',
            ]

        # 从历史数据中推导关键触发因子
        if level_name in ['高风险', '极高风险'] and len(rdf) > 0:
            # 看这些产品衰退前哪些因子上升最快
            decline_prods = rdf[rdf['pattern'].isin(['快速恢复', '缓慢恢复', '持续恶化'])]
            common_factors = []
            for p in decline_prods['product_id'].unique():
                pdf = df[df['product_id'] == p].sort_values('date_month')
                if len(pdf) < 6:
                    continue
                decline_m = p if isinstance(p, str) else str(p)
                # 获取衰退前最后一个有效因子得分
                last_row = pdf.iloc[-1]
                high_factors = []
                for fcol in ['f1_score', 'f4_score', 'f5_score']:
                    if fcol in pdf.columns and last_row[fcol] > 55:
                        high_factors.append(FEATURE_LABELS.get(fcol, fcol))
                common_factors.append(high_factors)

            if common_factors:
                all_factors = [f for sublist in common_factors for f in sublist]
                top = Counter(all_factors).most_common(3)
                entry['触发因子'] = [t[0] for t in top]
                entry['触发因子频率'] = {t[0]: f'{t[1]/len(common_factors)*100:.0f}%' for t in top}

        matrix[level_name] = entry

    return matrix


def generate_report(rdf, adf, matrix):
    """生成 Phase 5 报告"""
    lines = []
    def L(s=""):
        lines.append(s)

    L("# Phase 5: 业务行动基线报告")
    L()
    L(f"**生成日期**: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    L('**目标**: 从历史数据提取衰退前后的业务行动模式, 建立风险等级到行动建议的基线框架')
    L()
    L("---")
    L()

    # 1. 衰退恢复模式分析
    L("## 1. 衰退恢复模式分析")
    L()

    if len(rdf) > 0:
        pattern_counts = rdf['pattern'].value_counts()
        L(f"共 {len(rdf)} 个产品经历过衰退，恢复模式分布如下：")
        L()
        L("| 恢复模式 | 产品数 | 占比 | 典型特征 |")
        L("|---------|-------|------|---------|")
        for pat in ['快速恢复', '缓慢恢复', '持续恶化']:
            cnt = pattern_counts.get(pat, 0)
            pct = cnt / len(rdf) * 100
            if pat == '快速恢复':
                desc = '衰退后6月内恢复到基线80%以上'
            elif pat == '缓慢恢复':
                desc = '衰退后12月内部分恢复'
            else:
                desc = '衰退后持续恶化，未有效恢复'
            L(f"| {pat} | {cnt} | {pct:.1f}% | {desc} |")
        L()

        # 各模式的关键指标对比
        L("### 各恢复模式衰退前后关键指标变化")
        L()
        L("| 指标 | 快速恢复(前→后) | 缓慢恢复(前→后) | 持续恶化(前→后) |")
        L("|------|----------------|----------------|----------------|")
        for col, label in [('recent_margin', '毛利率'), ('asp_slope', 'ASP趋势'), ('growth_rate', '销量增速')]:
            parts = []
            for pat in ['快速恢复', '缓慢恢复', '持续恶化']:
                subset = adf[adf['pattern'] == pat] if len(adf) > 0 else pd.DataFrame()
                if len(subset) > 0:
                    pre = subset[f'pre_{col}'].mean()
                    post = subset[f'post_{col}'].mean()
                    chg = subset[f'change_{col}'].mean()
                    parts.append(f"{pre:.4f} → {post:.4f} ({chg:+.1f}%)")
                else:
                    parts.append("—")
            L(f"| {label} | {parts[0]} | {parts[1]} | {parts[2]} |")

        L()
        L(f"分析发现:")
        L()
        if len(adf) > 0:
            for pat in ['快速恢复', '缓慢恢复', '持续恶化']:
                subset = adf[adf['pattern'] == pat]
                if len(subset) == 0:
                    continue
                asp_avg = subset['change_asp_slope'].mean() if 'change_asp_slope' in subset.columns else np.nan
                margin_avg = subset['change_recent_margin'].mean()
                growth_avg = subset['change_growth_rate'].mean() if 'change_growth_rate' in subset.columns else np.nan
                L(f"- **{pat}** ({len(subset)}个): 毛利率变化{margin_avg:+.1f}%, 销量增速变化{growth_avg:+.1f}%")

    L()

    # 2. 行动推荐矩阵
    L("## 2. 行动推荐矩阵")
    L()
    L("| 风险等级 | 风险分范围 | 响应周期 | 建议行动 |")
    L("|---------|----------|---------|---------|")

    for level in ['低风险', '中风险', '高风险', '极高风险']:
        entry = matrix[level]
        actions = '<br>'.join(entry['建议行动'])
        L(f"| {level} | {entry['风险分范围']} | {entry['响应周期']} | {actions} |")

    L()

    # 触发因子
    L("### 关键触发因子（基于历史数据）")
    L()
    L("以下因子在历史衰退案例中频繁出现，可作为预警触发条件：")
    L()
    L("| 风险等级 | 触发因子 | 出现频率 |")
    L("|---------|---------|---------|")
    for level in ['高风险', '极高风险']:
        entry = matrix.get(level, {})
        if '触发因子' in entry:
            for factor, freq in zip(entry['触发因子'], entry.get('触发因子频率', {}).values()):
                L(f"| {level} | {factor} | {freq} |")

    L()

    # 3. 恢复周期分布
    L("## 3. 恢复周期分布")
    L()
    if len(rdf) > 0 and rdf['recovery_duration_months'].notna().sum() > 0:
        durations = rdf['recovery_duration_months'].dropna()
        L(f"- **平均恢复周期**: {durations.mean():.1f}个月")
        L(f"- **中位恢复周期**: {durations.median():.0f}个月")
        L(f"- **恢复周期范围**: {durations.min():.0f} ~ {durations.max():.0f}个月")
        L(f"- **75%产品在{durations.quantile(0.75):.0f}个月内恢复**")
    L()

    # 恢复率分布
    L("### 衰退后6个月 vs 12个月恢复率")
    L()
    L("| 恢复模式 | 6月恢复率(均值) | 12月恢复率(均值) |")
    L("|---------|----------------|-----------------|")
    for pat in ['快速恢复', '缓慢恢复', '持续恶化']:
        subset = rdf[rdf['pattern'] == pat]
        if len(subset) == 0:
            continue
        r6 = subset['recovery_6m'].mean()
        r12 = subset['recovery_12m'].mean()
        r6_str = f"{r6:.1%}" if not np.isnan(r6) else "N/A"
        r12_str = f"{r12:.1%}" if not np.isnan(r12) else "N/A"
        L(f"| {pat} | {r6_str} | {r12_str} |")

    L()

    # 4. 行动检查清单
    L("## 4. 行动检查清单")
    L()
    L("基于历史数据，归纳各风险等级的可行行动检查清单：")
    L()

    checklists = {
        '低风险': [
            "□ 因子趋势无异常（F1-F6均在正常范围）",
            "□ 毛利率稳定或上升",
            "□ 客户订单正常",
        ],
        '中风险': [
            "□ 检查F1毛利率趋势是否连续3月为负",
            "□ 检查F3订货波动是否持续升高",
            "□ 与客户确认未来3月订单预期",
            "□ 评估是否需要调整安全库存",
        ],
        '高风险': [
            "□ 启动周度风险监控",
            "□ 成本复盘：原材料/制造成本是否有上涨空间",
            "□ 价格策略调整评估",
            "□ 重点客户拜访或挽留行动",
            "□ 跨部门会议（产品+销售+财务）",
            "□ 准备替代供应商/替代方案",
        ],
        '极高风险': [
            "□ 启动退市/清仓评估",
            "□ 通知销售团队停止新项目导入",
            "□ 评估最后批量采购数量",
            "□ 产品生命周期终止流程启动",
            "□ 替代新品导入计划",
            "□ 客户替代方案沟通",
        ],
    }

    for level, items in checklists.items():
        L(f"### {level}")
        L()
        for item in items:
            L(f"- {item}")
        L()

    # 5. 模型改进建议
    L("## 5. 模型改进建议")
    L()
    L("### 短期改进（数据层面）")
    L()
    L("1. **c6 客户因子缺失处理**: 62.5%缺失率，建议探索替代客户指标（如：Top3客户订单占比变化、活跃客户数变化）")
    L("2. **新品冷启动**: 数据不足12个月的产品漏报率高（3/3漏报案例数据不足8个月），建议单独建新品模型或使用行业参照")
    L()
    L("### 中期改进（模型层面）")
    L()
    L("1. **误报优化**: 误报产品（TMI8721-Q1, TMI8262）因子得分极高但未衰退，需引入验证层（如：衰退概率需维持3月以上才预警）")
    L('2. **多阶段预警**: 当前是6月前瞻标签，建议拆分为[衰退信号](3月前)和[衰退确认](当月)两阶段')
    L()
    L("### 长期改进（业务层面）")
    L()
    L("1. **行动效果追踪**: 记录业务干预（调价/促销/客户拜访）后产品的恢复轨迹，量化行动效果")
    L("2. **行业对标**: 加入行业数据看产品表现是否优于/差于行业整体")

    report_path = os.path.join(OUTPUT_DIR, 'phase5_report.md')
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print(f"报告已写入: {report_path}")
    return report_path


def plot_recovery_patterns(rdf):
    """绘制恢复模式分布图"""
    if len(rdf) == 0:
        return

    fig, axes = plt.subplots(1, 3, figsize=(15, 5))

    # 1. 恢复模式饼图
    ax = axes[0]
    pattern_counts = rdf['pattern'].value_counts()
    colors = {'快速恢复': '#2ecc71', '缓慢恢复': '#f39c12', '持续恶化': '#e74c3c'}
    ax.pie(pattern_counts.values, labels=pattern_counts.index, autopct='%1.1f%%',
           colors=[colors.get(p, 'gray') for p in pattern_counts.index])
    ax.set_title('衰退恢复模式分布', fontsize=12)

    # 2. 恢复周期直方图
    ax = axes[1]
    durations = rdf['recovery_duration_months'].dropna()
    if len(durations) > 0:
        ax.hist(durations, bins=range(0, 25, 3), color='#3498db', alpha=0.7, edgecolor='white')
        ax.axvline(durations.median(), color='red', linestyle='--', label=f"中位数={durations.median():.0f}月")
        ax.set_xlabel('恢复周期(月)')
        ax.set_ylabel('产品数')
        ax.set_title('衰退恢复周期分布', fontsize=12)
        ax.legend()

    # 3. 恢复率对比箱线图
    ax = axes[2]
    box_data = []
    labels = []
    for pat in ['快速恢复', '缓慢恢复', '持续恶化']:
        subset = rdf[rdf['pattern'] == pat]['recovery_6m'].dropna()
        if len(subset) > 0:
            box_data.append(subset.values)
            labels.append(pat)
    if box_data:
        bp = ax.boxplot(box_data, labels=labels, patch_artist=True)
        for patch, color in zip(bp['boxes'], ['#2ecc71', '#f39c12', '#e74c3c']):
            patch.set_facecolor(color)
        ax.axhline(y=0.8, color='blue', linestyle=':', alpha=0.5, label='恢复基线(80%)')
        ax.set_ylabel('6月恢复率')
        ax.set_title('各模式6月恢复率对比', fontsize=12)
        ax.legend()
        ax.set_ylim(0, 2)

    plt.tight_layout()
    path = os.path.join(OUTPUT_DIR, 'phase5_recovery_patterns.png')
    plt.savefig(path, dpi=150)
    plt.close()
    print(f"恢复模式图已保存: {path}")


def main():
    print("=" * 60)
    print("Phase 5: 业务行动基线")
    print("=" * 60)

    # 1. 加载数据
    df = load_data()

    # 2. 需要 y_decline_6m 标签（从 Phase 1 输出加载）
    phase1 = pd.read_csv(os.path.join(OUTPUT_DIR, 'phase1_customer_factors.csv'), encoding='utf-8-sig')
    df = df.merge(phase1[['product_id', 'date_month', 'y_decline_6m']],
                  on=['product_id', 'date_month'], how='left')

    print(f"合并标签后: {df.shape}")
    print(f"衰退标签分布: {df['y_decline_6m'].value_counts().to_dict()}")

    # 3. 分析恢复模式
    rdf = classify_recovery(df)

    # 4. 分析行动特征
    adf = analyze_action_signatures(df, rdf)

    # 5. 构建行动矩阵
    matrix = build_action_matrix(rdf, adf, df)

    # 6. 可视化
    plot_recovery_patterns(rdf)

    # 7. 报告
    report_path = generate_report(rdf, adf, matrix)

    print(f"\nPhase 5 完成!")
    return 0


if __name__ == '__main__':
    sys.exit(main())
