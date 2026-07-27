#!/usr/bin/env python
# run_1.3_lifecycle_calibration.py — 实验 1.3: 产品生命周期因子初次校准
# Layer split: 1.3A Explanation (current) + 1.3B PIT Proxy Modeling
# 创建: 2026-06-15

import pandas as pd
import numpy as np
import os
import sys
import json
from pathlib import Path
from datetime import datetime, timedelta
from scipy import stats as scipy_stats
import warnings
warnings.filterwarnings('ignore')

# ── Paths ──────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[2]
BASE = str(PROJECT_ROOT)
EXP_DIR = os.path.join(BASE, 'experiment_log', '14_exp_1.3_lifecycle_calibration')
OUTPUT_DIR = os.path.join(EXP_DIR, 'output')
os.makedirs(OUTPUT_DIR, exist_ok=True)

RAW_EXCEL = os.path.join(BASE, 'data', '财务分析-5月（6.3）.xlsx')
SHEET_NAME = '总表'
GOLD_PORTRAIT = os.path.join(BASE, 'output', 'gold', 'gold_product_portrait.csv')
BASELINE_SELECTED = os.path.join(BASE, 'experiment_log', '05_exp_0.2_baseline_lock', 'output',
                                 'baseline_corrected_customer_20260612',
                                 'baseline_corrected_selected_methods.csv')
BASELINE_BACKTEST = os.path.join(BASE, 'experiment_log', '05_exp_0.2_baseline_lock', 'output',
                                 'baseline_corrected_customer_20260612',
                                 '预测方法回测明细.csv')
BASELINE_METRICS_PLINE = os.path.join(BASE, 'experiment_log', '05_exp_0.2_baseline_lock',
                                      'output', 'baseline_metrics_by_pline.csv')
BASELINE_HOLDOUT_PLINE = os.path.join(BASE, 'experiment_log', '05_exp_0.2_baseline_lock',
                                      'output', 'baseline_holdout_by_pline.csv')
LOW_CONF_FLAGS = os.path.join(BASE, 'experiment_log', '09_exp_1.0_hierarchy_granularity',
                               'output', 'hierarchy_low_confidence_flags.csv')
FIELD_SPEC = os.path.join(BASE, 'experiment_log', '00_master', 'field_spec_locked_20260612.md')

# ── Column mapping (from raw Excel position analysis) ──────────────
COL_SHIP_DATE = '发货日期'
COL_PROD_NAME = '存货名称'
COL_PROD_CODE = '存货编码'
COL_SHIP_QTY = '发货数量'
COL_SALES_AMT = 'RMB 未税金额小计'
COL_PROFIT = '利润'
COL_PROD_LINE = '型号_产品线（新）'
COL_CUST_SHORT = '终端客户简称'
COL_AGENT = '代理商/直供名称'
COL_ACTUAL_CUST = '实际终端客户'

# ── Backtest fold cutoff definitions ─────────────────────────────
# Bucket mapping: H01=2023-06~08, H02=2023-09~11, ..., H12=2026-03~05
BUCKET_MONTH_MAP = {
    'H01': (pd.Timestamp('2023-06-01'), pd.Timestamp('2023-08-31')),
    'H02': (pd.Timestamp('2023-09-01'), pd.Timestamp('2023-11-30')),
    'H03': (pd.Timestamp('2023-12-01'), pd.Timestamp('2024-02-29')),
    'H04': (pd.Timestamp('2024-03-01'), pd.Timestamp('2024-05-31')),
    'H05': (pd.Timestamp('2024-06-01'), pd.Timestamp('2024-08-31')),
    'H06': (pd.Timestamp('2024-09-01'), pd.Timestamp('2024-11-30')),
    'H07': (pd.Timestamp('2024-12-01'), pd.Timestamp('2025-02-28')),
    'H08': (pd.Timestamp('2025-03-01'), pd.Timestamp('2025-05-31')),
    'H09': (pd.Timestamp('2025-06-01'), pd.Timestamp('2025-08-31')),
    'H10': (pd.Timestamp('2025-09-01'), pd.Timestamp('2025-11-30')),
    'H11': (pd.Timestamp('2025-12-01'), pd.Timestamp('2026-02-28')),
    'H12': (pd.Timestamp('2026-03-01'), pd.Timestamp('2026-05-31')),
}

# Fold → cutoff: last day of training period
FOLD_CUTOFF = {
    'BT01': pd.Timestamp('2024-11-30'),  # end of H06
    'BT02': pd.Timestamp('2025-02-28'),  # end of H07
    'BT03': pd.Timestamp('2025-05-31'),  # end of H08
    'BT04': pd.Timestamp('2025-08-31'),  # end of H09
    'BT05': pd.Timestamp('2025-11-30'),  # end of H10
    'BT06': pd.Timestamp('2026-02-28'),  # end of H11
}

FOLD_VALIDATION_BUCKET = {
    'BT01': 'H07', 'BT02': 'H08', 'BT03': 'H09',
    'BT04': 'H10', 'BT05': 'H11', 'BT06': 'H12',
}

# ── Parameter grid (from user spec) ──────────────────────────────
ALPHA_VALS = [0.1, 0.3, 0.5, 0.7, 0.9, 1.1, 1.3]   # 7 values
BETA_VALS  = [-0.1, 0.0, 0.1, 0.2, 0.3]             # 5 values
GAMMA_VALS = [-0.1, 0.0, 0.1, 0.2, 0.3]             # 5 values
DELTA_VALS = [-0.1, 0.0, 0.1, 0.2, 0.3]             # 5 values

# Product line → tier mapping
PLINE_TIER = {
    'POE电源管理': 'A', '充电与控制电源管理': 'A', '步进电机驱动': 'A', '硬件锂电保护': 'A',
    'dTOF模组': 'B', '有刷直流电机驱动': 'B', '电脑&计算电源管理': 'B', '车规电机驱动': 'B',
    '车规电源管理': 'B', '通用电源管理': 'A', '音频功放': 'B', '磁传感': 'A',
    '电机驱动': 'A', '新显示MLED驱动': 'C', '无刷直流电机驱动': 'C', '电源模组': 'C',
    '未分类': 'C',
}

# ── Operation log ─────────────────────────────────────────────────
op_log = []

def log_op(step, action, result, file_path='', rows=0):
    global op_log
    op_log.append({
        '时间': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        '步骤': step,
        '操作': action,
        '结果': result,
        '文件': file_path,
        '行数': rows,
    })

def save_operation_log():
    df = pd.DataFrame(op_log)
    path = os.path.join(OUTPUT_DIR, 'operation_log.csv')
    df.to_csv(path, index=False, encoding='utf-8-sig')
    print(f"  [LOG] Saved operation log: {path} ({len(df)} entries)")

# ── Utility functions ─────────────────────────────────────────────

def build_product_line_mapping(raw_df):
    """从原始明细构建 存货名称→型号_产品线（新） 映射"""
    mapping = raw_df[[COL_PROD_NAME, COL_PROD_LINE]].dropna(subset=[COL_PROD_NAME, COL_PROD_LINE])
    mapping = mapping.drop_duplicates(subset=[COL_PROD_NAME])
    return dict(zip(mapping[COL_PROD_NAME], mapping[COL_PROD_LINE]))

def build_customer_key(raw_df):
    """
    构建预测客户名称: 终端客户简称 → 代理商/直供名称 → 实际终端客户 → '未知终端客户'
    """
    cust = raw_df[COL_CUST_SHORT].fillna('')
    cust = cust.replace('', np.nan)
    cust = cust.fillna(raw_df[COL_AGENT])
    cust = cust.fillna(raw_df[COL_ACTUAL_CUST])
    cust = cust.fillna('未知终端客户')
    return cust

def compute_wape(predicted, actual):
    """金额加权 WAPE"""
    mask = actual.abs() > 1e-9
    if mask.sum() == 0:
        return np.nan
    return (predicted[mask] - actual[mask]).abs().sum() / actual[mask].abs().sum()

def compute_bias(predicted, actual):
    """金额加权 Bias"""
    mask = actual.abs() > 1e-9
    if mask.sum() == 0:
        return np.nan
    return (predicted[mask] - actual[mask]).sum() / actual[mask].abs().sum()

# ═══════════════════════════════════════════════════════════════════
# SECTION 1.3A: Current Explanation Layer Calibration
# ═══════════════════════════════════════════════════════════════════

def section_1_3A(portrait, product_line_map):
    """
    1.3A 当前解释层校准：
    - 聚合当前画像信息到产品线层级
    - 与基线WAPE/Bias/holdout做相关性分析
    - 输出解释力评估
    """
    print("\n" + "=" * 80)
    print("SECTION 1.3A: CURRENT EXPLANATION LAYER CALIBRATION")
    print("=" * 80)

    # ── A1. Map products to product lines ──
    print("\n[A1] Mapping products to product lines...")
    portrait = portrait.copy()
    portrait['产品线'] = portrait['产品名称'].map(product_line_map)

    mapped = portrait['产品线'].notna().sum()
    unmapped = portrait['产品线'].isna().sum()
    print(f"  Products mapped: {mapped}/{len(portrait)} ({mapped/len(portrait)*100:.1f}%)")
    print(f"  Products unmapped: {unmapped}")
    log_op('1.3A-A1', '产品→产品线映射',
           f'映射{mapped}/{len(portrait)}({mapped/len(portrait)*100:.1f}%), 未映射{unmapped}',
           GOLD_PORTRAIT, len(portrait))

    # Filter only mapped products
    portrait_mapped = portrait[portrait['产品线'].notna()].copy()

    # ── A2. Aggregate portrait features by product line ──
    print("\n[A2] Aggregating portrait features by product line...")
    plines = portrait_mapped['产品线'].unique()
    print(f"  Product lines with data: {len(plines)}")

    # Count features
    pline_skus = portrait_mapped.groupby('产品线').size().reset_index(name='SKU数')

    # Portrait distribution (11 lifecycle stages)
    portrait_pivot = portrait_mapped.groupby(['产品线', '当前画像']).size().unstack(fill_value=0)
    # Key portrait ratios
    portrait_ratios = pd.DataFrame(index=plines)
    portrait_ratios.index.name = '产品线'
    n = pline_skus.set_index('产品线')['SKU数']
    portrait_ratios['健康扩张占比'] = portrait_pivot.get('健康扩张', 0) / n
    portrait_ratios['成长型占比'] = portrait_pivot.get('成长型', 0) / n
    portrait_ratios['现金牛占比'] = portrait_pivot.get('现金牛', 0) / n
    portrait_ratios['衰退期占比'] = portrait_pivot.get('衰退期', 0) / n
    portrait_ratios['夕阳产品占比'] = portrait_pivot.get('夕阳产品', 0) / n
    portrait_ratios['衰退夕阳占比'] = (portrait_pivot.get('衰退期', 0) +
                                        portrait_pivot.get('夕阳产品', 0)) / n
    portrait_ratios['预警增长占比'] = portrait_pivot.get('预警增长', 0) / n
    portrait_ratios['新品观察占比'] = portrait_pivot.get('新品观察', 0) / n
    portrait_ratios['隐性衰退占比'] = portrait_pivot.get('隐性衰退', 0) / n
    portrait_ratios['预警新品占比'] = (portrait_pivot.get('预警增长', 0) +
                                        portrait_pivot.get('新品观察', 0) +
                                        portrait_pivot.get('隐性衰退', 0)) / n
    portrait_ratios['清仓偶发占比'] = portrait_pivot.get('清仓/偶发', 0) / n

    # Risk distribution
    risk_pivot = portrait_mapped.groupby(['产品线', '综合风险等级']).size().unstack(fill_value=0)
    portrait_ratios['高风险占比'] = risk_pivot.get('高风险', 0) / n
    portrait_ratios['极高风险占比'] = risk_pivot.get('极高风险', 0) / n
    portrait_ratios['高风险极高占比'] = (risk_pivot.get('高风险', 0) +
                                          risk_pivot.get('极高风险', 0)) / n
    portrait_ratios['低风险占比'] = risk_pivot.get('低风险', 0) / n

    # Management summary distribution
    mgmt_pivot = portrait_mapped.groupby(['产品线', '管理层摘要']).size().unstack(fill_value=0)
    portrait_ratios['退出区占比'] = mgmt_pivot.get('退出区', 0) / n
    portrait_ratios['警告区占比'] = mgmt_pivot.get('警告区', 0) / n
    portrait_ratios['退出警告区占比'] = (mgmt_pivot.get('退出区', 0) +
                                          mgmt_pivot.get('警告区', 0)) / n
    portrait_ratios['投资区占比'] = mgmt_pivot.get('投资区', 0) / n
    portrait_ratios['观察区占比'] = mgmt_pivot.get('观察区', 0) / n

    # Revenue-profit diagnosis
    rp_pivot = portrait_mapped.groupby(['产品线', '营收-毛利综合判断']).size().unstack(fill_value=0)
    portrait_ratios['双增占比'] = rp_pivot.get('双增', 0) / n
    portrait_ratios['双降占比'] = rp_pivot.get('双降', 0) / n

    # Continuous features
    cont_agg = portrait_mapped.groupby('产品线').agg(
        平均风险评分=('综合评分', lambda x: x.dropna().mean() if len(x.dropna()) > 0 else np.nan),
        平均客户集中度Top1=('客户集中度-前1大%', lambda x: x.dropna().mean() if len(x.dropna()) > 0 else np.nan),
        平均客户集中度Top3=('客户集中度-前3大%', lambda x: x.dropna().mean() if len(x.dropna()) > 0 else np.nan),
        平均近12月增长率=('近12月增长率%', lambda x: x.dropna().mean() if len(x.dropna()) > 0 else np.nan),
        平均近12月毛利率=('近12月毛利率%', lambda x: x.dropna().mean() if len(x.dropna()) > 0 else np.nan),
        平均毛利率趋势斜率=('毛利率趋势斜率%/月', lambda x: x.dropna().mean() if len(x.dropna()) > 0 else np.nan),
        平均增速衰减=('增速衰减(pp)', lambda x: x.dropna().mean() if len(x.dropna()) > 0 else np.nan),
        近12月总销售额=('近12月销售额', 'sum'),
        近12月总销量=('近12月销量', 'sum'),
        已达6K占比=('是否已达6K', lambda x: (x == '是').mean() if '是否已达6K' in portrait_mapped.columns else np.nan),
    )

    # Merge all
    # pline_skus already has '产品线' as a regular column (from reset_index at line 190),
    # so no additional reset_index needed — it would add a spurious 'index' column
    cont_agg = cont_agg.reset_index()  # groupby.agg() produces index='产品线', reset to column
    portrait_ratios = portrait_ratios.reset_index()  # index named '产品线', reset to column
    explain_df = pline_skus.merge(portrait_ratios, on='产品线', how='left')
    explain_df = explain_df.merge(cont_agg, on='产品线', how='left')

    # Add tier
    explain_df['分层'] = explain_df['产品线'].map(PLINE_TIER).fillna('C')

    print(f"  Explanation features for {len(explain_df)} product lines")

    # ── A3. Load baseline metrics ──
    print("\n[A3] Loading baseline metrics for correlation analysis...")
    baseline_pline = pd.read_csv(BASELINE_METRICS_PLINE)
    print(f"  Baseline metrics: {len(baseline_pline)} product lines")
    # Columns: 产品线, 销售额WAPE, 销售额MAPE, Bias, ...

    holdout_pline = pd.read_csv(BASELINE_HOLDOUT_PLINE)
    print(f"  Holdout metrics: {len(holdout_pline)} product lines")
    # Columns: 产品线, approximate_recent_holdout_BT04_BT06_wape, ...

    # Rename for clarity
    baseline_pline = baseline_pline.rename(columns={
        '销售额WAPE': 'CV_WAPE',
        'Bias': '金额加权Bias',
    })

    holdout_pline = holdout_pline.rename(columns={
        'approximate_recent_holdout_BT04_BT06_wape': 'BT04_06_WAPE',
    })

    # Merge
    explain_df = explain_df.merge(
        baseline_pline[['产品线', 'CV_WAPE', '金额加权Bias']], on='产品线', how='left'
    )
    explain_df = explain_df.merge(
        holdout_pline[['产品线', 'BT04_06_WAPE']], on='产品线', how='left'
    )

    # ── A4. Load low confidence flags ──
    print("\n[A4] Loading low confidence flags...")
    lowconf = pd.read_csv(LOW_CONF_FLAGS)
    print(f"  Low confidence flags: {len(lowconf)}")
    # Columns: 产品线, 产品线分层, 标记类型, 标记原因, 建议

    explain_df = explain_df.merge(
        lowconf[['产品线', '标记类型']], on='产品线', how='left'
    )
    explain_df['标记类型'] = explain_df['标记类型'].fillna('正常')

    # ── A5. Correlation analysis ──
    print("\n[A5] Computing correlations between portrait features and prediction performance...")
    corr_features = [
        ('衰退夕阳占比', 'CV_WAPE'),
        ('衰退夕阳占比', 'BT04_06_WAPE'),
        ('衰退夕阳占比', '金额加权Bias'),
        ('高风险极高占比', 'CV_WAPE'),
        ('高风险极高占比', 'BT04_06_WAPE'),
        ('高风险极高占比', '金额加权Bias'),
        ('退出警告区占比', 'CV_WAPE'),
        ('退出警告区占比', 'BT04_06_WAPE'),
        ('退出警告区占比', '金额加权Bias'),
        ('平均风险评分', 'CV_WAPE'),
        ('平均风险评分', 'BT04_06_WAPE'),
        ('平均风险评分', '金额加权Bias'),
        ('平均客户集中度Top1', 'CV_WAPE'),
        ('平均客户集中度Top1', 'BT04_06_WAPE'),
        ('平均客户集中度Top1', '金额加权Bias'),
        ('平均增速衰减', 'CV_WAPE'),
        ('平均增速衰减', 'BT04_06_WAPE'),
        ('平均毛利率趋势斜率', 'CV_WAPE'),
        ('平均毛利率趋势斜率', 'BT04_06_WAPE'),
        ('预警新品占比', 'CV_WAPE'),
        ('预警新品占比', 'BT04_06_WAPE'),
        ('已达6K占比', 'CV_WAPE'),
        ('已达6K占比', 'BT04_06_WAPE'),
    ]

    correlations = []
    valid = explain_df.dropna(subset=['CV_WAPE', 'BT04_06_WAPE', '金额加权Bias'])
    print(f"  Valid product lines for correlation: {len(valid)}")

    for feat, metric in corr_features:
        data = valid[[feat, metric]].dropna()
        if len(data) >= 5:
            r, p = scipy_stats.pearsonr(data[feat], data[metric])
            correlations.append({
                '画像维度': feat,
                '对比指标': metric,
                'Pearson_r': round(r, 4),
                'p_value': round(p, 4),
                '有效样本': len(data),
            })
        else:
            correlations.append({
                '画像维度': feat,
                '对比指标': metric,
                'Pearson_r': np.nan,
                'p_value': np.nan,
                '有效样本': len(data),
            })

    corr_df = pd.DataFrame(correlations)
    print(f"  Correlation pairs computed: {len(corr_df)}")

    # ── A6. Explanation force assessment per product line ──
    print("\n[A6] Assessing explanation force per product line...")
    assessments = []
    for _, row in valid.iterrows():
        pline = row['产品线']
        tier = row['分层']
        decay_pct = row.get('衰退夕阳占比', 0)
        risk_pct = row.get('高风险极高占比', 0)
        exit_warn_pct = row.get('退出警告区占比', 0)
        cv_wape = row['CV_WAPE']
        holdout_wape = row['BT04_06_WAPE']
        bias = row['金额加权Bias']
        top1 = row.get('平均客户集中度Top1', 0)
        risk_score = row.get('平均风险评分', 0)

        reasons = []
        force = '弱解释'

        # Rule-based assessment
        if not pd.isna(decay_pct) and not pd.isna(cv_wape):
            if decay_pct > 0.3 and cv_wape > 0.35:
                force = '强解释'
                reasons.append(f'衰退夕阳占比{decay_pct:.0%}推高WAPE={cv_wape:.1%}')
            elif decay_pct > 0.2 and cv_wape > 0.30:
                if force == '弱解释':
                    force = '中等解释'
                reasons.append(f'衰退夕阳占比{decay_pct:.0%}与WAPE={cv_wape:.1%}正相关')

        if not pd.isna(risk_pct) and not pd.isna(cv_wape):
            if risk_pct > 0.3 and holdout_wape > 0.4:
                force = '强解释'
                reasons.append(f'高风险占比{risk_pct:.0%}推高holdout WAPE={holdout_wape:.1%}')
            elif risk_pct > 0.2:
                if force == '弱解释':
                    force = '中等解释'
                reasons.append(f'高风险占比{risk_pct:.0%}与预测性能相关')

        if not pd.isna(exit_warn_pct) and not pd.isna(bias):
            if exit_warn_pct > 0.5 and abs(bias) > 0.15:
                if force == '弱解释':
                    force = '中等解释'
                reasons.append(f'退出警告区占比{exit_warn_pct:.0%}预示偏差方向Bias={bias:.1%}')

        if not pd.isna(top1) and top1 > 0.7:
            if force == '弱解释':
                force = '中等解释'
            reasons.append(f'客户集中度Top1={top1:.0%}，单点风险显著')

        if not pd.isna(risk_score) and risk_score > 50 and cv_wape > 0.3:
            if force == '弱解释':
                force = '中等解释'
            reasons.append(f'风险评分={risk_score:.0f}与高WAPE一致')

        # Manual review trigger
        review_trigger = ''
        if '强解释' in force or '中等解释' in force:
            review_trigger = '建议人工复核：' + '；'.join(reasons[:3])
        elif cv_wape > 0.5:
            review_trigger = '高WAPE产品线，即使画像不解释也需复核'

        assessments.append({
            '产品线': pline,
            '分层': tier,
            'CV_WAPE': cv_wape,
            'BT04_06_WAPE': holdout_wape,
            '金额加权Bias': bias,
            '衰退夕阳占比': decay_pct,
            '高风险极高占比': risk_pct,
            '退出警告区占比': exit_warn_pct,
            '平均风险评分': risk_score,
            '平均客户集中度Top1': top1,
            '解释力评估': force,
            '解释原因': '；'.join(reasons) if reasons else '无显著画像-性能关联',
            '人工复核建议': review_trigger,
        })

    assess_df = pd.DataFrame(assessments)

    # ── A7. Build final explanation calibration output ──
    print("\n[A7] Building final output...")
    # Merge full explanation features with assessment
    final_cols = [
        '产品线', '分层', 'SKU数', '衰退夕阳占比', '预警新品占比', '高风险极高占比',
        '退出警告区占比', '平均风险评分', '平均客户集中度Top1',
        '平均近12月增长率', '平均增速衰减', '平均毛利率趋势斜率',
        '近12月总销售额', '已达6K占比',
        'CV_WAPE', 'BT04_06_WAPE', '金额加权Bias', '标记类型',
    ]
    available_cols = [c for c in final_cols if c in explain_df.columns]
    output_df = explain_df[available_cols].copy()

    # Merge assessment
    output_df = output_df.merge(
        assess_df[['产品线', '解释力评估', '解释原因', '人工复核建议']],
        on='产品线', how='left'
    )

    # Sort by tier then WAPE
    tier_order = {'A': 0, 'B': 1, 'C': 2}
    output_df['_tier_sort'] = output_df['分层'].map(tier_order)
    output_df = output_df.sort_values(['_tier_sort', 'CV_WAPE']).drop(columns=['_tier_sort'])

    # Save
    out_path = os.path.join(OUTPUT_DIR, 'lifecycle_current_explanation_calibration.csv')
    output_df.to_csv(out_path, index=False, encoding='utf-8-sig')
    print(f"  Saved: {out_path} ({len(output_df)} rows)")

    # Save correlations
    corr_out = os.path.join(OUTPUT_DIR, 'lifecycle_explanation_correlations.csv')
    corr_df.to_csv(corr_out, index=False, encoding='utf-8-sig')
    print(f"  Saved: {corr_out} ({len(corr_df)} rows)")

    # ── A8. Success criteria check ──
    print("\n[A8] 1.3A Success Criteria:")
    coverage = len(explain_df)
    strong_medium = len(assess_df[assess_df['解释力评估'].isin(['强解释', '中等解释'])])
    review_triggers = len(assess_df[assess_df['人工复核建议'].str.len() > 0])
    print(f"  解释覆盖: {coverage}/17 -> {'PASS' if coverage >= 14 else 'FAIL'}")
    print(f"  强/中等解释线数: {strong_medium} -> {'PASS' if strong_medium >= 3 else 'FAIL'}")
    print(f"  人工复核触发线数: {review_triggers} -> {'PASS' if review_triggers >= 2 else 'FAIL'}")

    log_op('1.3A-A8', '1.3A成功标准判定',
           f'覆盖{coverage}/17, 强中解释{strong_medium}, 复核触发{review_triggers}',
           out_path, len(output_df))

    return output_df, assess_df, corr_df


# ═══════════════════════════════════════════════════════════════════
# SECTION 1.3B: PIT Proxy Feature Modeling Calibration
# ═══════════════════════════════════════════════════════════════════

def compute_pit_features_per_sku(raw_df, cutoff_date):
    """
    Compute PIT proxy features per SKU at a given cutoff date.
    Strict anti-leakage: all data must be <= cutoff_date.

    Returns DataFrame indexed by SKU with 13 PIT features.
    """
    # ── 1. Temporal cutoff ──
    train = raw_df[raw_df[COL_SHIP_DATE] <= cutoff_date].copy()
    assert train[COL_SHIP_DATE].max() <= cutoff_date, \
        f"FUTURE LEAKAGE! Max date {train[COL_SHIP_DATE].max()} > cutoff {cutoff_date}"

    # ── 2. Time windows ──
    # Trail 12m: months (cutoff_month - 11) through cutoff_month
    cutoff_month = cutoff_date.to_period('M')
    trail_start = cutoff_month - 11
    trail_end = cutoff_month
    prev_start = cutoff_month - 23
    prev_end = cutoff_month - 12

    train['发货月份'] = train[COL_SHIP_DATE].dt.to_period('M')

    trail_mask = (train['发货月份'] >= trail_start) & (train['发货月份'] <= trail_end)
    prev_mask = (train['发货月份'] >= prev_start) & (train['发货月份'] <= prev_end)

    trail_data = train[trail_mask]
    prev_data = train[prev_mask]

    if len(trail_data) == 0:
        return pd.DataFrame()

    # ── 3. Per-SKU aggregation ──
    def safe_div(a, b):
        return np.where(np.abs(b) > 1, a / b, np.nan)

    # Trail 12m
    trail_agg = trail_data.groupby(COL_PROD_CODE).agg(
        trail12_sales=(COL_SALES_AMT, 'sum'),
        trail12_qty=(COL_SHIP_QTY, 'sum'),
        trail12_profit=(COL_PROFIT, 'sum'),
        trail12_top1_cust=(COL_SALES_AMT, lambda x: _top_customer_share(x, trail_data, COL_PROD_CODE, COL_CUST_SHORT)),
    ).reset_index()

    # Trail 12m margin
    trail_agg['trail12_margin'] = safe_div(trail_agg['trail12_profit'], trail_agg['trail12_sales'])

    # Prev 12m
    prev_agg = prev_data.groupby(COL_PROD_CODE).agg(
        prev12_sales=(COL_SALES_AMT, 'sum'),
        prev12_profit=(COL_PROFIT, 'sum'),
    ).reset_index()
    prev_agg['prev12_margin'] = safe_div(prev_agg['prev12_profit'], prev_agg['prev12_sales'])

    # Merge
    feats = trail_agg.merge(prev_agg, on=COL_PROD_CODE, how='left')

    # ── 4. Derived features ──
    # F07: Sales growth
    feats['pit_sales_growth'] = safe_div(
        feats['trail12_sales'] - feats['prev12_sales'],
        np.abs(feats['prev12_sales'])
    )
    # Clip extreme growth
    feats['pit_sales_growth'] = feats['pit_sales_growth'].clip(-0.99, 5.0)

    # F08: Margin change (percentage points)
    feats['pit_margin_change'] = feats['trail12_margin'] - feats['prev12_margin']

    # F09: Margin slope (monthly OLS slope of monthly margin over trail12)
    feats['pit_margin_slope'] = np.nan

    # Compute monthly margin slope per SKU (skip if insufficient data)
    if len(trail_data) > 0:
        monthly = trail_data.copy()
        monthly['发货月份'] = monthly[COL_SHIP_DATE].dt.to_period('M')
        for sku, grp in monthly.groupby(COL_PROD_CODE):
            m_agg = grp.groupby('发货月份').agg(
                monthly_sales=(COL_SALES_AMT, 'sum'),
                monthly_profit=(COL_PROFIT, 'sum'),
            )
            m_agg['monthly_margin'] = safe_div(m_agg['monthly_profit'], m_agg['monthly_sales'])
            m_agg = m_agg.dropna(subset=['monthly_margin'])
            if len(m_agg) >= 6:
                x = np.arange(len(m_agg)).astype(float)
                y = m_agg['monthly_margin'].values
                slope, _, _, _, _ = scipy_stats.linregress(x, y)
                feats.loc[feats[COL_PROD_CODE] == sku, 'pit_margin_slope'] = slope

    # F10: Top1 share already computed in trail_agg
    feats = feats.rename(columns={'trail12_top1_cust': 'pit_top1_share'})

    # F11: Top3 share (not computed per SKU, will compute at product line level later)
    feats['pit_top3_share'] = np.nan

    # F12: Reached 6K (cumulative qty since beginning >= 6000)
    cum_qty = train.groupby(COL_PROD_CODE)[COL_SHIP_QTY].sum().reset_index()
    cum_qty.columns = [COL_PROD_CODE, 'cum_qty']
    cum_qty['pit_reached_6k'] = (cum_qty['cum_qty'] >= 6000).astype(int)
    feats = feats.merge(cum_qty[[COL_PROD_CODE, 'pit_reached_6k']], on=COL_PROD_CODE, how='left')

    # F13: Revenue-profit diagnosis
    def diag_fn(row):
        g = row.get('pit_sales_growth', 0) or 0
        m = row.get('pit_margin_change', 0) or 0
        if g >= 0 and m >= 0:
            return '双增'
        elif g >= 0 and m < 0:
            return '增收不增利'
        elif g < 0 and m >= 0:
            return '减收增利'
        else:
            return '双降'

    feats['pit_rev_profit_diag'] = feats.apply(diag_fn, axis=1)

    return feats


def _top_customer_share(sales_series, full_data, sku_col, cust_col):
    """Compute top-1 customer share for a given SKU's sales series"""
    # sales_series is the sales for this SKU; we need to reconstruct the customer breakdown
    # This is a simplified approach - use the full_data grouped by SKU+customer
    # But in groupby.agg, we only get the sales series. A better approach:
    # We'll compute this outside the agg.
    return np.nan  # Placeholder - computed separately below


def compute_pit_features_by_pline(raw_df, cutoff_date, product_line_map):
    """
    Compute PIT proxy features from raw data, aggregated to product line level.
    Returns DataFrame with one row per product line per cutoff.
    """
    # ── 1. Temporal cutoff ──
    train = raw_df[raw_df[COL_SHIP_DATE] <= cutoff_date].copy()
    assert train[COL_SHIP_DATE].max() <= cutoff_date, \
        f"FUTURE LEAKAGE! Max date {train[COL_SHIP_DATE].max()} > cutoff {cutoff_date}"

    # ── 2. Time windows ──
    cutoff_month = cutoff_date.to_period('M')
    trail_start = cutoff_month - 11
    trail_end = cutoff_month
    prev_start = cutoff_month - 23
    prev_end = cutoff_month - 12

    train['发货月份'] = train[COL_SHIP_DATE].dt.to_period('M')
    train['产品线'] = train[COL_PROD_NAME].map(product_line_map)
    train = train[train['产品线'].notna()].copy()

    trail_mask = (train['发货月份'] >= trail_start) & (train['发货月份'] <= trail_end)
    prev_mask = (train['发货月份'] >= prev_start) & (train['发货月份'] <= prev_end)

    # ── 3. Per product line aggregation ──
    # Trail 12m aggregation
    trail_pline = train[trail_mask].groupby('产品线').agg(
        trail12_sales=(COL_SALES_AMT, 'sum'),
        trail12_qty=(COL_SHIP_QTY, 'sum'),
        trail12_profit=(COL_PROFIT, 'sum'),
    ).reset_index()

    # Prev 12m aggregation
    prev_pline = train[prev_mask].groupby('产品线').agg(
        prev12_sales=(COL_SALES_AMT, 'sum'),
        prev12_qty=(COL_SHIP_QTY, 'sum'),
        prev12_profit=(COL_PROFIT, 'sum'),
    ).reset_index()

    # Merge
    feats = trail_pline.merge(prev_pline, on='产品线', how='left')

    # ── 4. Customer concentration (Top1 and Top3) ──
    # Build customer key
    train_cust = train.copy()
    train_cust['预测客户名称'] = build_customer_key(train_cust)

    # Top1 share per product line in trail 12m
    trail_cust = train_cust[trail_mask]
    cust_sales = trail_cust.groupby(['产品线', '预测客户名称'])[COL_SALES_AMT].sum().reset_index()
    cust_sales_ranked = cust_sales.sort_values([COL_SALES_AMT], ascending=False)
    # Top1 per product line
    top1 = cust_sales_ranked.groupby('产品线').head(1).groupby('产品线')[COL_SALES_AMT].sum()
    top3 = cust_sales_ranked.groupby('产品线').head(3).groupby('产品线')[COL_SALES_AMT].sum()
    total = cust_sales_ranked.groupby('产品线')[COL_SALES_AMT].sum()

    top1_share = (top1 / total.replace(0, np.nan)).reset_index()
    top1_share.columns = ['产品线', 'pit_top1_share']
    top3_share = (top3 / total.replace(0, np.nan)).reset_index()
    top3_share.columns = ['产品线', 'pit_top3_share']

    feats = feats.merge(top1_share, on='产品线', how='left')
    feats = feats.merge(top3_share, on='产品线', how='left')

    # ── 5. Derived features ──
    def safe_div(a, b):
        return np.where(np.abs(b) > 1, a / b, np.nan)

    # F04: trail12 margin
    feats['pit_trail12_margin'] = safe_div(feats['trail12_profit'], feats['trail12_sales'])

    # F06: prev12 margin
    feats['pit_prev12_margin'] = safe_div(feats['prev12_profit'], feats['prev12_sales'])

    # F07: sales growth
    feats['pit_sales_growth'] = safe_div(
        feats['trail12_sales'] - feats['prev12_sales'],
        np.abs(feats['prev12_sales'])
    )
    feats['pit_sales_growth'] = feats['pit_sales_growth'].clip(-0.99, 5.0)

    # F08: margin change
    feats['pit_margin_change'] = feats['pit_trail12_margin'] - feats['pit_prev12_margin']

    # F09: margin slope (per product line monthly slope)
    feats['pit_margin_slope'] = np.nan
    monthly_pline = train[trail_mask].groupby(['产品线', '发货月份']).agg(
        monthly_sales=(COL_SALES_AMT, 'sum'),
        monthly_profit=(COL_PROFIT, 'sum'),
    ).reset_index()
    monthly_pline['monthly_margin'] = safe_div(monthly_pline['monthly_profit'],
                                                monthly_pline['monthly_sales'])
    for pline, grp in monthly_pline.groupby('产品线'):
        grp_clean = grp.dropna(subset=['monthly_margin']).sort_values('发货月份')
        if len(grp_clean) >= 6:
            x = np.arange(len(grp_clean)).astype(float)
            y = grp_clean['monthly_margin'].values
            # Filter out inf
            mask = np.isfinite(y)
            if mask.sum() >= 6:
                slope, _, _, _, _ = scipy_stats.linregress(x[mask], y[mask])
                feats.loc[feats['产品线'] == pline, 'pit_margin_slope'] = slope

    # F12: reached 6K ratio
    cum_qty = train.groupby(['产品线', COL_PROD_CODE])[COL_SHIP_QTY].sum().reset_index()
    cum_qty['reached_6k'] = (cum_qty[COL_SHIP_QTY] >= 6000).astype(int)
    k6_ratio = cum_qty.groupby('产品线')['reached_6k'].mean().reset_index()
    k6_ratio.columns = ['产品线', 'pit_reached_6k_ratio']
    feats = feats.merge(k6_ratio, on='产品线', how='left')

    # F13: Revenue-profit diagnosis ratios
    # Count per SKU then aggregate
    # First compute per SKU growth and margin change
    sku_trail = train[trail_mask].groupby([COL_PROD_CODE, '产品线']).agg(
        sku_trail_sales=(COL_SALES_AMT, 'sum'),
        sku_trail_profit=(COL_PROFIT, 'sum'),
    ).reset_index()
    sku_prev = train[prev_mask].groupby([COL_PROD_CODE]).agg(
        sku_prev_sales=(COL_SALES_AMT, 'sum'),
        sku_prev_profit=(COL_PROFIT, 'sum'),
    ).reset_index()
    sku_feats = sku_trail.merge(sku_prev, on=COL_PROD_CODE, how='left')
    sku_feats['sku_growth'] = safe_div(
        sku_feats['sku_trail_sales'] - sku_feats['sku_prev_sales'],
        np.abs(sku_feats['sku_prev_sales'])
    )
    sku_feats['sku_margin'] = safe_div(sku_feats['sku_trail_profit'], sku_feats['sku_trail_sales'])
    sku_feats['sku_margin_prev'] = safe_div(sku_feats['sku_prev_profit'], sku_feats['sku_prev_sales'])
    sku_feats['sku_margin_chg'] = sku_feats['sku_margin'] - sku_feats['sku_margin_prev']

    def diag_fn(g, m):
        if pd.isna(g) or pd.isna(m):
            return '未知'
        if g >= 0 and m >= 0:
            return '双增'
        elif g >= 0 and m < 0:
            return '增收不增利'
        elif g < 0 and m >= 0:
            return '减收增利'
        else:
            return '双降'

    sku_feats['diag'] = sku_feats.apply(
        lambda r: diag_fn(r.get('sku_growth', np.nan), r.get('sku_margin_chg', np.nan)), axis=1
    )
    diag_counts = sku_feats.groupby(['产品线', 'diag']).size().unstack(fill_value=0)
    total_sku = diag_counts.sum(axis=1)
    for d in ['双增', '双降', '增收不增利', '减收增利']:
        if d in diag_counts.columns:
            feats[f'pit_diag_{d}'] = feats['产品线'].map(
                (diag_counts[d] / total_sku).to_dict()
            )
        else:
            feats[f'pit_diag_{d}'] = 0.0

    # Fill NaN
    for c in ['pit_top1_share', 'pit_top3_share', 'pit_reached_6k_ratio']:
        if c in feats.columns:
            feats[c] = feats[c].fillna(0)

    return feats


def section_1_3B(raw_df, product_line_map):
    """
    1.3B: PIT proxy feature modeling calibration.
    - Compute PIT features per cutoff
    - Parameter search on BT01-BT03
    - Apply correction to all folds
    - Evaluate vs baseline
    """
    print("\n" + "=" * 80)
    print("SECTION 1.3B: PIT PROXY FEATURE MODELING CALIBRATION")
    print("=" * 80)

    # ── B1. Load baseline backtest detail ──
    print("\n[B1] Loading baseline backtest detail...")
    selected = pd.read_csv(BASELINE_SELECTED)
    backtest = pd.read_csv(BASELINE_BACKTEST)

    # Filter to selected methods only
    bt_selected = backtest.merge(selected[['产品线', '方法ID']], on=['产品线', '方法ID'], how='inner')
    print(f"  Selected backtest rows: {len(bt_selected)}")
    print(f"  Folds: {sorted(bt_selected['回测折次'].unique())}")

    # Build baseline lookup: 产品线 × 回测折次 → 预测销售额, 实际销售额
    baseline_lookup = {}
    for _, row in bt_selected.iterrows():
        key = (row['产品线'], row['回测折次'])
        baseline_lookup[key] = {
            'predicted': row['预测销售额'],
            'actual': row['实际销售额'],
        }

    # ── B2. Compute PIT features per cutoff ──
    print("\n[B2] Computing PIT features per cutoff...")
    all_pit_features = []
    folds = ['BT01', 'BT02', 'BT03', 'BT04', 'BT05', 'BT06']

    for fold in folds:
        cutoff = FOLD_CUTOFF[fold]
        print(f"  {fold}: cutoff={cutoff.date()}")
        pit_df = compute_pit_features_by_pline(raw_df, cutoff, product_line_map)
        pit_df['回测折次'] = fold
        all_pit_features.append(pit_df)

    pit_all = pd.concat(all_pit_features, ignore_index=True)
    print(f"  Total PIT feature rows: {len(pit_all)}")

    # ── B3. Compute proxy variables for correction ──
    print("\n[B3] Computing proxy variables...")
    # Merge PIT features with baseline predictions
    pit_all = pit_all.merge(
        bt_selected[['产品线', '回测折次', '预测销售额', '实际销售额']],
        on=['产品线', '回测折次'], how='left'
    )

    # Proxy variables
    pit_all['growth_proxy'] = pit_all['pit_sales_growth'].fillna(0).clip(-1, 3)
    pit_all['margin_proxy'] = pit_all['pit_margin_change'].fillna(0).clip(-0.5, 0.5)
    # Concentration proxy: change in top1 share (use absolute level as proxy when no previous)
    # We'll use deviation from 0.5 (rough midpoint) as a simple proxy
    pit_all['concentration_proxy'] = (pit_all['pit_top1_share'].fillna(0) - 0.5).clip(-0.5, 0.5)
    # Risk proxy: composite of negative growth, margin decline, high concentration
    pit_all['risk_proxy'] = (
        np.maximum(0, -pit_all['growth_proxy']) * 0.4 +
        np.maximum(0, -pit_all['margin_proxy']) * 0.3 +
        np.maximum(0, pit_all['pit_top1_share'].fillna(0) - 0.6) * 0.3
    ).clip(0, 1)

    # Track PIT coverage
    pit_coverage = pit_all.groupby('产品线').agg(
        total_folds=('回测折次', 'nunique'),
        has_sales_growth=('pit_sales_growth', lambda x: x.notna().sum()),
        has_margin_change=('pit_margin_change', lambda x: x.notna().sum()),
    ).reset_index()
    print(f"  Product lines with PIT data: {len(pit_coverage)}")

    # ── B4. Parameter search on BT01-BT03 (training folds) ──
    print("\n[B4] Parameter search (BT01-BT03 only)...")
    train_data = pit_all[pit_all['回测折次'].isin(['BT01', 'BT02', 'BT03'])].copy()
    # Only use product lines with sufficient data
    train_data = train_data.dropna(subset=['预测销售额', '实际销售额'])
    print(f"  Training rows: {len(train_data)}")

    param_results = []
    total_combos = len(ALPHA_VALS) * len(BETA_VALS) * len(GAMMA_VALS) * len(DELTA_VALS)
    print(f"  Parameter grid: {len(ALPHA_VALS)}×{len(BETA_VALS)}×{len(GAMMA_VALS)}×{len(DELTA_VALS)} = {total_combos} combinations")

    combo_idx = 0
    for alpha in ALPHA_VALS:
        for beta in BETA_VALS:
            for gamma in GAMMA_VALS:
                for delta in DELTA_VALS:
                    combo_idx += 1
                    params = {'alpha': alpha, 'beta': beta, 'gamma': gamma, 'delta': delta}

                    # Apply correction
                    train_data_temp = train_data.copy()
                    adj = (1 +
                           alpha * train_data_temp['growth_proxy'].fillna(0) +
                           beta * train_data_temp['margin_proxy'].fillna(0) +
                           gamma * train_data_temp['concentration_proxy'].fillna(0) +
                           delta * train_data_temp['risk_proxy'].fillna(0))
                    adj = adj.clip(0.5, 1.5)
                    train_data_temp['corrected_forecast'] = train_data_temp['预测销售额'] * adj

                    # Compute CV WAPE (amount-weighted)
                    cv_wape = compute_wape(train_data_temp['corrected_forecast'],
                                           train_data_temp['实际销售额'])
                    cv_bias = compute_bias(train_data_temp['corrected_forecast'],
                                           train_data_temp['实际销售额'])

                    # Baseline WAPE on same data
                    base_wape = compute_wape(train_data_temp['预测销售额'],
                                             train_data_temp['实际销售额'])

                    param_results.append({
                        'alpha': alpha, 'beta': beta, 'gamma': gamma, 'delta': delta,
                        'CV_WAPE': cv_wape if not np.isnan(cv_wape) else 999,
                        'CV_Bias': cv_bias,
                        'Baseline_CV_WAPE': base_wape,
                    })

                    if combo_idx % 100 == 0:
                        print(f"    Progress: {combo_idx}/{total_combos}")

    param_df = pd.DataFrame(param_results)
    param_df = param_df.sort_values('CV_WAPE')

    # Best global parameter
    best_global = param_df.iloc[0]
    print(f"\n  Best global params: α={best_global['alpha']}, β={best_global['beta']}, "
          f"γ={best_global['gamma']}, δ={best_global['delta']}")
    print(f"  Best CV WAPE: {best_global['CV_WAPE']:.4f} (baseline: {best_global['Baseline_CV_WAPE']:.4f})")

    # ── B5. Per-product-line parameter search ──
    print("\n[B5] Per-product-line parameter search (BT01-BT03)...")
    pline_best_params = {}
    for pline in train_data['产品线'].unique():
        pline_data = train_data[train_data['产品线'] == pline].copy()
        if len(pline_data) < 3:
            pline_best_params[pline] = {
                'alpha': best_global['alpha'], 'beta': best_global['beta'],
                'gamma': best_global['gamma'], 'delta': best_global['delta'],
            }
            continue

        best_wape = 999
        best_p = None
        for _, pr in param_df.head(50).iterrows():  # Only search top-50 global combos
            params = {'alpha': pr['alpha'], 'beta': pr['beta'],
                      'gamma': pr['gamma'], 'delta': pr['delta']}
            adj = (1 +
                   params['alpha'] * pline_data['growth_proxy'].fillna(0) +
                   params['beta'] * pline_data['margin_proxy'].fillna(0) +
                   params['gamma'] * pline_data['concentration_proxy'].fillna(0) +
                   params['delta'] * pline_data['risk_proxy'].fillna(0))
            adj = adj.clip(0.5, 1.5)
            corrected = pline_data['预测销售额'] * adj
            w = compute_wape(corrected, pline_data['实际销售额'])
            if not np.isnan(w) and w < best_wape:
                best_wape = w
                best_p = params

        if best_p is None:
            best_p = {'alpha': best_global['alpha'], 'beta': best_global['beta'],
                      'gamma': best_global['gamma'], 'delta': best_global['delta']}
        pline_best_params[pline] = best_p

    # ── B6. Full-fold backtest with corrections ──
    print("\n[B6] Full-fold backtest (BT01-BT06)...")
    all_folds_data = pit_all.copy()
    all_folds_data = all_folds_data.dropna(subset=['预测销售额', '实际销售额'])

    # Group 1: No correction (baseline)
    # Group 2: Global correction
    # Group 3: Per-line correction

    results = []
    for _, row in all_folds_data.iterrows():
        pline = row['产品线']
        fold = row['回测折次']
        base = row['预测销售额']
        actual = row['实际销售额']

        # Global correction
        adj_global = (1 +
                      best_global['alpha'] * (row['growth_proxy'] or 0) +
                      best_global['beta'] * (row['margin_proxy'] or 0) +
                      best_global['gamma'] * (row['concentration_proxy'] or 0) +
                      best_global['delta'] * (row['risk_proxy'] or 0))
        adj_global = np.clip(adj_global, 0.5, 1.5)
        corrected_global = base * adj_global

        # Per-line correction
        bp = pline_best_params.get(pline, best_global)
        adj_pline = (1 +
                     bp['alpha'] * (row['growth_proxy'] or 0) +
                     bp['beta'] * (row['margin_proxy'] or 0) +
                     bp['gamma'] * (row['concentration_proxy'] or 0) +
                     bp['delta'] * (row['risk_proxy'] or 0))
        adj_pline = np.clip(adj_pline, 0.5, 1.5)
        corrected_pline = base * adj_pline

        results.append({
            '产品线': pline,
            '回测折次': fold,
            'base_forecast': base,
            'corrected_forecast_global': corrected_global,
            'corrected_forecast_pline': corrected_pline,
            'actual': actual,
            'growth_proxy': row['growth_proxy'],
            'margin_proxy': row['margin_proxy'],
            'concentration_proxy': row['concentration_proxy'],
            'risk_proxy': row['risk_proxy'],
        })

    results_df = pd.DataFrame(results)

    # ── B7. Save PIT proxy features ──
    print("\n[B7] Saving PIT proxy features...")
    pit_out_cols = [
        '产品线', '回测折次',
        'trail12_sales', 'trail12_qty', 'trail12_profit', 'pit_trail12_margin',
        'prev12_sales', 'pit_prev12_margin',
        'pit_sales_growth', 'pit_margin_change', 'pit_margin_slope',
        'pit_top1_share', 'pit_top3_share', 'pit_reached_6k_ratio',
        'pit_diag_双增', 'pit_diag_双降',
    ]
    available_pit = [c for c in pit_out_cols if c in pit_all.columns]
    pit_output = pit_all[available_pit].copy()
    # Merge with results
    pit_output = pit_output.merge(
        results_df[['产品线', '回测折次', 'base_forecast', 'corrected_forecast_global',
                     'corrected_forecast_pline', 'actual']],
        on=['产品线', '回测折次'], how='left'
    )
    pit_out_path = os.path.join(OUTPUT_DIR, 'lifecycle_pit_proxy_features.csv')
    pit_output.to_csv(pit_out_path, index=False, encoding='utf-8-sig')
    print(f"  Saved: {pit_out_path} ({len(pit_output)} rows)")
    log_op('1.3B-B7', '保存PIT代理特征', f'{len(pit_output)}行', pit_out_path, len(pit_output))

    # ── B8. Evaluation metrics ──
    print("\n[B8] Computing evaluation metrics...")

    # Split folds
    cv_folds = ['BT01', 'BT02', 'BT03']
    holdout_folds = ['BT04', 'BT05', 'BT06']

    def compute_group_metrics(df, forecast_col):
        """Compute WAPE and Bias for a given forecast column"""
        cv = df[df['回测折次'].isin(cv_folds)]
        ho = df[df['回测折次'].isin(holdout_folds)]
        all_f = df

        # Amount-weighted WAPE
        aw_cv = compute_wape(cv[forecast_col], cv['actual'])
        aw_ho = compute_wape(ho[forecast_col], ho['actual'])
        aw_all = compute_wape(all_f[forecast_col], all_f['actual'])

        # Simple mean WAPE (per product line)
        def simple_mean_wape(data):
            wapes = []
            for pline, grp in data.groupby('产品线'):
                w = compute_wape(grp[forecast_col], grp['actual'])
                if not np.isnan(w):
                    wapes.append(w)
            return np.mean(wapes) if wapes else np.nan

        sm_cv = simple_mean_wape(cv)
        sm_ho = simple_mean_wape(ho)
        sm_all = simple_mean_wape(all_f)

        # Bias
        bias_all = compute_bias(all_f[forecast_col], all_f['actual'])
        bias_ho = compute_bias(ho[forecast_col], ho['actual'])

        return {
            '金额加权WAPE_CV': aw_cv, '金额加权WAPE_Holdout': aw_ho, '金额加权WAPE_全折': aw_all,
            '简单平均WAPE_CV': sm_cv, '简单平均WAPE_Holdout': sm_ho, '简单平均WAPE_全折': sm_all,
            '金额加权Bias_全折': bias_all, '金额加权Bias_Holdout': bias_ho,
        }

    base_metrics = compute_group_metrics(results_df, 'base_forecast')
    global_metrics = compute_group_metrics(results_df, 'corrected_forecast_global')
    pline_metrics = compute_group_metrics(results_df, 'corrected_forecast_pline')

    # ── B9. Build recommendation table ──
    print("\n[B9] Building recommendation table...")
    recommendations = []
    for pline in sorted(results_df['产品线'].unique()):
        pline_data = results_df[results_df['产品线'] == pline]
        bp = pline_best_params.get(pline, best_global)
        tier = PLINE_TIER.get(pline, 'C')

        # Compute per-line metrics
        base_wape_all = compute_wape(pline_data['base_forecast'], pline_data['actual'])
        global_wape_all = compute_wape(pline_data['corrected_forecast_global'], pline_data['actual'])
        pline_wape_all = compute_wape(pline_data['corrected_forecast_pline'], pline_data['actual'])

        cv_data = pline_data[pline_data['回测折次'].isin(cv_folds)]
        ho_data = pline_data[pline_data['回测折次'].isin(holdout_folds)]

        cv_improve = (compute_wape(cv_data['corrected_forecast_pline'], cv_data['actual']) or 999) - \
                     (compute_wape(cv_data['base_forecast'], cv_data['actual']) or 999)
        ho_improve = (compute_wape(ho_data['corrected_forecast_pline'], ho_data['actual']) or 999) - \
                     (compute_wape(ho_data['base_forecast'], ho_data['actual']) or 999)
        if np.isnan(cv_improve):
            cv_improve = 0
        if np.isnan(ho_improve):
            ho_improve = 0

        # Overfitting check
        is_overfit = cv_improve < -0.01 and ho_improve >= 0

        # PIT coverage
        pit_cov = pit_coverage[pit_coverage['产品线'] == pline]
        pit_status = '充足' if len(pit_cov) > 0 and pit_cov.iloc[0]['total_folds'] >= 5 else '不足'

        # Recommendation
        if cv_improve < -0.01 and ho_improve < -0.01:
            action = '进入Phase 2深化'
        elif cv_improve < -0.01 and ho_improve >= 0:
            action = '降级为解释/置信度标记（过拟合风险）'
        elif cv_improve >= 0:
            action = '排除出建模路径（无改善）'
        else:
            action = '待进一步分析'

        recommendations.append({
            '产品线': pline, '分层': tier,
            '全局alpha': best_global['alpha'], '全局beta': best_global['beta'],
            '全局gamma': best_global['gamma'], '全局delta': best_global['delta'],
            '按线alpha': bp['alpha'], '按线beta': bp['beta'],
            '按线gamma': bp['gamma'], '按线delta': bp['delta'],
            '基线WAPE': base_wape_all if not np.isnan(base_wape_all) else 999,
            '全局修正WAPE': global_wape_all if not np.isnan(global_wape_all) else 999,
            '按线修正WAPE': pline_wape_all if not np.isnan(pline_wape_all) else 999,
            'CV改善(pp)': round(cv_improve * 100, 2),
            'Holdout改善(pp)': round(ho_improve * 100, 2),
            '是否过拟合': '是' if is_overfit else '否',
            'PIT覆盖状态': pit_status,
            '推荐动作': action,
        })

    rec_df = pd.DataFrame(recommendations)
    rec_out = os.path.join(OUTPUT_DIR, 'lifecycle_calibration_recommendation.csv')
    rec_df.to_csv(rec_out, index=False, encoding='utf-8-sig')
    print(f"  Saved: {rec_out} ({len(rec_df)} rows)")

    # ── B10. Save parameter search detail ──
    print("\n[B10] Saving parameter search detail...")
    param_out = os.path.join(OUTPUT_DIR, 'lifecycle_param_search_detail.csv')
    param_df.to_csv(param_out, index=False, encoding='utf-8-sig')
    print(f"  Saved: {param_out} ({len(param_df)} rows)")
    log_op('1.3B-B10', '保存参数搜索明细', f'{len(param_df)}行', param_out, len(param_df))

    # ── B11. Success criteria check ──
    print("\n[B11] 1.3B Success Criteria:")
    # PIT feature generation
    pit_lines = pit_all['产品线'].nunique()
    print(f"  PIT特征生成: {pit_lines}/17 -> {'PASS' if pit_lines >= 12 else 'FAIL'}")

    # PIT coverage (missing rate)
    missing = pit_all['pit_sales_growth'].isna().mean()
    print(f"  PIT缺失率: {missing:.1%} -> {'PASS' if missing < 0.3 else 'FAIL'}")

    # Amount-weighted improvement
    aw_improve_global = (global_metrics['金额加权WAPE_CV'] - base_metrics['金额加权WAPE_CV']) * 100
    aw_improve_pline = (pline_metrics['金额加权WAPE_CV'] - base_metrics['金额加权WAPE_CV']) * 100
    print(f"  金额加权CV改善(全局): {aw_improve_global:.2f}pp")
    print(f"  金额加权CV改善(按线): {aw_improve_pline:.2f}pp")

    # Holdout
    ho_improve_global = (global_metrics['金额加权WAPE_Holdout'] - base_metrics['金额加权WAPE_Holdout']) * 100
    ho_improve_pline = (pline_metrics['金额加权WAPE_Holdout'] - base_metrics['金额加权WAPE_Holdout']) * 100
    print(f"  Holdout改善(全局): {ho_improve_global:.2f}pp -> {'PASS' if ho_improve_global < -1 else 'FAIL'}")
    print(f"  Holdout改善(按线): {ho_improve_pline:.2f}pp -> {'PASS' if ho_improve_pline < -1 else 'FAIL'}")

    # Simple mean WAPE
    sm_change = (pline_metrics['简单平均WAPE_全折'] - base_metrics['简单平均WAPE_全折']) * 100
    print(f"  简单平均WAPE变化: {sm_change:.2f}pp")

    # A-class protection
    a_data = results_df[results_df['产品线'].isin(
        [p for p, t in PLINE_TIER.items() if t == 'A']
    )]
    if len(a_data) > 0:
        a_base = compute_wape(a_data['base_forecast'], a_data['actual'])
        a_pline = compute_wape(a_data['corrected_forecast_pline'], a_data['actual'])
        a_change = (a_pline - a_base) * 100 if not (np.isnan(a_base) or np.isnan(a_pline)) else 0
        print(f"  A类WAPE变化: {a_change:.2f}pp -> {'PASS' if a_change < 2 else 'FAIL'}")

    # ── B12. Summary metrics ──
    print("\n" + "=" * 80)
    print("1.3B PERFORMANCE SUMMARY")
    print("=" * 80)
    print(f"{'指标':<30s} {'基线':>10s} {'全局修正':>10s} {'按线修正':>10s}")
    print(f"{'-'*60}")
    for key in ['金额加权WAPE_CV', '金额加权WAPE_Holdout', '金额加权WAPE_全折',
                 '简单平均WAPE_CV', '简单平均WAPE_Holdout', '简单平均WAPE_全折',
                 '金额加权Bias_全折', '金额加权Bias_Holdout']:
        b = base_metrics.get(key, np.nan)
        g = global_metrics.get(key, np.nan)
        p = pline_metrics.get(key, np.nan)
        print(f"{key:<30s} {b:>10.4f} {g:>10.4f} {p:>10.4f}")

    log_op('1.3B-B12', '1.3B性能总结',
           f'全局改善={aw_improve_global:.2f}pp, Holdout改善={ho_improve_global:.2f}pp',
           rec_out, len(rec_df))

    return results_df, rec_df, param_df, pit_all, base_metrics, global_metrics, pline_metrics


# ═══════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════

def main():
    start_time = datetime.now()
    print("=" * 80)
    print("EXPERIMENT 1.3: PRODUCT LIFECYCLE FACTOR CALIBRATION")
    print("Layer: 1.3A (Explanation) + 1.3B (PIT Proxy Modeling)")
    print(f"Start: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    # ── Step 0: Load data ──
    print("\n[Step 0] Loading data sources...")

    # 0a. Load gold product portrait
    print("  [0a] Loading gold_product_portrait.csv...")
    if not os.path.exists(GOLD_PORTRAIT):
        raise FileNotFoundError(f"Required file not found: {GOLD_PORTRAIT}")
    portrait = pd.read_csv(GOLD_PORTRAIT)
    print(f"    Products: {len(portrait)}, Columns: {len(portrait.columns)}")
    log_op('0a', '加载产品画像', f'{len(portrait)}产品', GOLD_PORTRAIT, len(portrait))

    # 0b. Load raw Excel for mapping and PIT
    print("  [0b] Loading raw Excel...")
    if not os.path.exists(RAW_EXCEL):
        raise FileNotFoundError(f"Required file not found: {RAW_EXCEL}")
    raw_df = pd.read_excel(RAW_EXCEL, sheet_name=SHEET_NAME)
    print(f"    Raw rows: {len(raw_df)}, Columns: {len(raw_df.columns)}")
    # Ensure date parsing
    raw_df[COL_SHIP_DATE] = pd.to_datetime(raw_df[COL_SHIP_DATE], errors='coerce')
    raw_df = raw_df.dropna(subset=[COL_SHIP_DATE])
    # Filter only positive quantities
    raw_df = raw_df[raw_df[COL_SHIP_QTY] > 0].copy()
    print(f"    After filtering positive qty: {len(raw_df)} rows")
    log_op('0b', '加载原始Excel', f'{len(raw_df)}行(正数量过滤后)', RAW_EXCEL, len(raw_df))

    # 0c. Build product → product line mapping
    print("  [0c] Building product→product line mapping...")
    product_line_map = build_product_line_mapping(raw_df)
    print(f"    Unique product mappings: {len(product_line_map)}")
    log_op('0c', '构建产品映射', f'{len(product_line_map)}产品映射')

    # 0d. Verify baseline data exists
    for f in [BASELINE_SELECTED, BASELINE_BACKTEST, BASELINE_METRICS_PLINE,
              BASELINE_HOLDOUT_PLINE, LOW_CONF_FLAGS]:
        if not os.path.exists(f):
            print(f"    WARNING: File not found: {f}")

    log_op('0d', '验证基线数据', '完成基线文件检查')

    # ── Step 1: 1.3A Explanation Layer ──
    explain_result, assess_result, corr_result = section_1_3A(portrait, product_line_map)

    # ── Step 2: 1.3B PIT Proxy Modeling (skipped for initial 1.3A validation) ──
    # results_pit = section_1_3B(raw_df, product_line_map)
    # results_df, rec_df, param_df, pit_all, base_m, global_m, pline_m = results_pit

    # ── Step 3: Write summary to operation log ──
    save_operation_log()

    # ── Done ──
    elapsed = (datetime.now() - start_time).total_seconds()
    print("\n" + "=" * 80)
    print(f"EXPERIMENT 1.3 COMPLETE")
    print(f"Elapsed: {elapsed:.1f}s ({elapsed/60:.1f} min)")
    print(f"Outputs in: {OUTPUT_DIR}")
    print("=" * 80)

    # List outputs
    for f in sorted(os.listdir(OUTPUT_DIR)):
        fpath = os.path.join(OUTPUT_DIR, f)
        size = os.path.getsize(fpath)
        print(f"  {f} ({size:,} bytes)")


if __name__ == '__main__':
    main()
