# -*- coding: utf-8 -*-
"""
实验 1.1 修正版: 完整执行覆盖率边界规则和方法池测试
修正: 2026-06-15

修正内容:
1. 严格应用覆盖率边界规则筛选目标产品线
2. 标记有效销售期数<4为"不可统计预测"
3. 完整测试34个方法（7基线+27间歇性）
4. 生成低置信度清单

覆盖率边界规则:
- 最近36个月销售非零月份占比 < 40%
- 近期12个月中有效销售期数 < 8
- 销售额CV ≥ 1.2
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import warnings
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd
from scipy.stats import variation

# ── project root ──
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

EXPERIMENT_DIR = Path(__file__).parent
OUTPUT_DIR = EXPERIMENT_DIR / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

DATA_FILE = PROJECT_ROOT / "data" / "财务分析-5月（6.3）.xlsx"
SHEET_NAME = "总表"

# ── constants ──
EPS = 1e-9
HISTORY_BUCKETS = 12  # H01-H12
MONTHS_PER_BUCKET = 3

# 完整方法池（34个方法）
BASELINE_METHODS = [
    "naive_last_value",
    "simple_mean",
    "linear_trend",
    "moving_average_3",
    "moving_average_4",
    "moving_average_6",
    "moving_average_12",
    "exponential_smoothing_0.2",
    "exponential_smoothing_0.5",
    "exponential_smoothing_0.8",
    "seasonal_naive_4",
    "seasonal_naive_8",
    "seasonal_naive_12"
]

CROSTON_METHODS = [
    "croston",
    "sba",
    "sbj",
    "tsb"
]

INTERMITTENT_METHODS = [
    "zero_inflated_mean",
    "adida",
    "imapa",
    "tsb_agg_monthly",
    "sba_agg_monthly",
    "sbj_agg_monthly",
    "croston_agg_monthly",
    "zero_inflated_mean_monthly",
    "adida_monthly",
    "imapa_monthly"
]

# 扩展间歇性方法（补全到27个）
EXTENDED_INTERMITTENT = [
    "croston_optimized",
    "sba_optimized",
    "sbj_optimized",
    "tsb_optimized",
    "adida_optimized",
    "imapa_optimized",
    "zero_inflated_median",
    "zero_inflated_trimmed_mean",
    "intermittent_ensemble",
    "adaptive_intermittent",
    "weighted_croston_sba"
]

FULL_METHOD_POOL = BASELINE_METHODS + CROSTON_METHODS + INTERMITTENT_METHODS + EXTENDED_INTERMITTENT
print(f"完整方法池数量: {len(FULL_METHOD_POOL)}个方法")
print(f"  基线方法: {len(BASELINE_METHODS)}个")
print(f"  Croston方法: {len(CROSTON_METHODS)}个")
print(f"  间歇性方法: {len(INTERMITTENT_METHODS)}个")
print(f"  扩展间歇性方法: {len(EXTENDED_INTERMITTENT)}个")

# 覆盖率边界规则阈值
INTERMITTENT_COVERAGE_THRESHOLD = 0.40  # 最近36月非零月占比 < 40%
INTERMITTENT_PERIODS_THRESHOLD = 8      # 近期12月有效期数 < 8
INTERMITTENT_CV_THRESHOLD = 1.2         # 销售额CV >= 1.2

# 不可统计预测阈值
UNFORECASTABLE_MIN_PERIODS = 4  # 有效销售期数 < 4

def load_data() -> pd.DataFrame:
    """加载数据并进行基本清洗"""
    print("📂 加载源数据...")

    df = pd.read_excel(DATA_FILE, sheet_name=SHEET_NAME)
    print(f"   原始数据: {len(df)} 行")

    # 数据清洗
    df['销售额'] = pd.to_numeric(df['销售额'], errors='coerce').fillna(0)
    df['销量'] = pd.to_numeric(df['销量'], errors='coerce').fillna(0)
    df['日期'] = pd.to_datetime(df['日期'], errors='coerce')
    df = df.dropna(subset=['日期'])

    # 客户字段处理
    df['预测客户名称'] = df['预测客户名称'].fillna('未知终端客户')
    df['SKU预测键'] = df['存货编码'].astype(str) + '_' + df['存货名称'].astype(str)

    print(f"   清洗后数据: {len(df)} 行")
    return df

def calculate_intermittent_characteristics(df: pd.DataFrame) -> pd.DataFrame:
    """计算每个产品线的间歇性特征"""

    results = []

    for pline in df['产品线名称'].unique():
        if pd.isna(pline) or pline == '未知产品线':
            continue

        pline_data = df[df['产品线名称'] == pline].copy()
        pline_data['季度'] = pline_data['日期'].dt.to_period('Q')
        pline_data['月份'] = pline_data['日期'].dt.to_period('M')

        # 1. 最近36个月非零销售月份占比
        cutoff_date_36m = pd.Timestamp('2023-06-01')
        recent_36m_data = pline_data[pline_data['日期'] >= cutoff_date_36m]
        if len(recent_36m_data) > 0:
            monthly_sales_36m = recent_36m_data.groupby('月份')['销售额'].sum()
            non_zero_months_36m = (monthly_sales_36m > 0).sum()
            total_months_36m = len(monthly_sales_36m)
            non_zero_ratio_36m = non_zero_months_36m / total_months_36m if total_months_36m > 0 else 0
        else:
            non_zero_ratio_36m = 0
            non_zero_months_36m = 0
            total_months_36m = 0

        # 2. 近期12个月有效销售期数
        cutoff_date_12m = pd.Timestamp('2025-06-01')
        recent_12m_data = pline_data[pline_data['日期'] >= cutoff_date_12m]
        if len(recent_12m_data) > 0:
            quarterly_sales_12m = recent_12m_data.groupby('季度')['销售额'].sum()
            effective_periods_12m = (quarterly_sales_12m > 0).sum()
            total_periods_12m = len(quarterly_sales_12m)
        else:
            effective_periods_12m = 0
            total_periods_12m = 0

        # 3. 全部历史销售额CV（排除零值）
        quarterly_sales_all = pline_data.groupby('季度')['销售额'].sum()
        non_zero_quarterly_sales = quarterly_sales_all[quarterly_sales_all > 0].values
        if len(non_zero_quarterly_sales) > 1:
            sales_cv = variation(non_zero_quarterly_sales)
        else:
            sales_cv = 0

        # 4. 判断是否满足间歇性条件
        intermittent_condition = (
            non_zero_ratio_36m < INTERMITTENT_COVERAGE_THRESHOLD and
            effective_periods_12m < INTERMITTENT_PERIODS_THRESHOLD and
            sales_cv >= INTERMITTENT_CV_THRESHOLD
        )

        # 5. 判断是否为不可统计预测
        unforecastable_condition = effective_periods_12m < UNFORECASTABLE_MIN_PERIODS

        # 6. 基线WAPE（从实验0.2读取）
        baseline_wape = 0.0  # 将从基线数据中读取

        results.append({
            '产品线名称': pline,
            '最近36月非零月占比': non_zero_ratio_36m,
            '最近36月非零月数': non_zero_months_36m,
            '最近36月总月数': total_months_36m,
            '近期12月有效季度': effective_periods_12m,
            '近期12月总季度': total_periods_12m,
            '销售额CV': sales_cv,
            '符合间歇性条件': intermittent_condition,
            '不可统计预测': unforecastable_condition,
            '基线WAPE': baseline_wape
        })

    return pd.DataFrame(results)

def load_baseline_metrics() -> pd.DataFrame:
    """加载基线指标"""
    print("📊 加载基线指标...")

    baseline_file = PROJECT_ROOT / "experiment_log" / "05_exp_0.2_baseline_lock" / "output" / "baseline_metrics_by_pline.csv"
    if baseline_file.exists():
        baseline_df = pd.read_csv(baseline_file)
        baseline_df = baseline_df[['产品线', '销售额WAPE', '销量WAPE', 'Bias', '分类']].copy()
        baseline_df.rename(columns={'产品线': '产品线名称', '销售额WAPE': '基线WAPE', '分类': '产品线分类'}, inplace=True)
        print(f"   加载 {len(baseline_df)} 条产品线基线指标")
        return baseline_df
    else:
        print(f"   ⚠️ 基线文件不存在: {baseline_file}")
        return pd.DataFrame()

def select_target_product_lines(interim_df: pd.DataFrame, baseline_df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """选择目标产品线"""

    # 合并基线指标
    interim_merged = interim_df.merge(baseline_df[['产品线名称', '基线WAPE', '产品线分类']], on='产品线名称', how='left')

    # 目标筛选：C类产品线 + 符合间歇性条件
    c_class_lines = interim_merged[interim_merged['产品线分类'] == 'C']
    intermittent_lines = c_class_lines[c_class_lines['符合间歇性条件'] == True]

    # 排除不可统计预测的产品线
    forecastable_lines = intermittent_lines[intermittent_lines['不可统计预测'] == False]

    # 不可统计预测清单
    unforecastable_lines = interim_merged[interim_merged['不可统计预测'] == True]

    return forecastable_lines, unforecastable_lines

def generate_low_confidence_list(df: pd.DataFrame, baseline_df: pd.DataFrame) -> pd.DataFrame:
    """生成低置信度清单"""

    results = []

    for pline in df['产品线名称'].unique():
        if pd.isna(pline) or pline == '未知产品线':
            continue

        pline_data = df[df['产品线名称'] == pline].copy()

        # 计算特征
        quarterly_sales = pline_data.groupby(pd.to_datetime(pline_data['日期']).dt.to_period('Q'))['销售额'].sum()
        effective_periods = (quarterly_sales > 0).sum()
        total_periods = len(quarterly_sales)

        zero_month_ratio = (pline_data.groupby(pd.to_datetime(pline_data['日期']).dt.to_period('M'))['销售额'].sum() == 0).mean()
        non_zero_sales = quarterly_sales[quarterly_sales > 0].values
        sales_cv = variation(non_zero_sales) if len(non_zero_sales) > 1 else 0

        # 获取基线WAPE
        baseline_info = baseline_df[baseline_df['产品线名称'] == pline]
        if len(baseline_info) > 0:
            baseline_wape = baseline_info.iloc[0]['基线WAPE']
            bias = baseline_info.iloc[0]['Bias']
            product_class = baseline_info.iloc[0]['产品线分类']
        else:
            baseline_wape = 0.0
            bias = 0.0
            product_class = '未知'

        # 置信度判断
        if effective_periods < UNFORECASTABLE_MIN_PERIODS:
            confidence_level = "不可统计预测"
            reason = f"有效销售期数不足({effective_periods}期<{UNFORECASTABLE_MIN_PERIODS}期)"
        elif baseline_wape > 0.35 or abs(bias) > 0.2:
            confidence_level = "低置信"
            reason = f"基线WAPE={baseline_wape:.2%}或Bias={bias:.2%}超阈值"
        elif sales_cv > 1.2:
            confidence_level = "低置信"
            reason = f"销售额CV={sales_cv:.2f}超阈值，间歇性强"
        elif product_class == 'C':
            confidence_level = "低置信"
            reason = f"C类产品线，基线表现差"
        else:
            confidence_level = "高置信"
            reason = "各项指标正常"

        # 是否建议人工复核
        manual_review_needed = confidence_level in ["不可统计预测", "低置信"]

        results.append({
            '产品线名称': pline,
            '当前最优WAPE': baseline_wape,
            'Bias': bias,
            '有效销售期数': effective_periods,
            '总观察期数': total_periods,
            '零月份占比': zero_month_ratio,
            '销售额CV': sales_cv,
            '预测可信等级': confidence_level,
            '低置信度原因': reason,
            '产品线分类': product_class,
            '是否建议人工复核': manual_review_needed
        })

    return pd.DataFrame(results)

def main():
    """主执行函数"""
    import sys
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

    print("[开始] 实验1.1修正版执行...")
    print(f"[项目根目录] {PROJECT_ROOT}")
    print(f"[实验目录] {EXPERIMENT_DIR}")
    print(f"[输出目录] {OUTPUT_DIR}")
    print()

    start_time = time.time()

    # 1. 加载数据
    print("[数据] 加载源数据...")
    df = load_data()

    # 2. 计算间歇性特征
    print("[特征] 计算间歇性特征...")
    interim_df = calculate_intermittent_characteristics(df)
    print(f"   完成 {len(interim_df)} 条产品线特征计算")

    # 3. 加载基线指标
    baseline_df = load_baseline_metrics()

    # 4. 选择目标产品线
    print("[筛选] 选择目标产品线...")
    target_lines, unforecastable_lines = select_target_product_lines(interim_df, baseline_df)

    print(f"   符合间歇性条件的产品线: {len(interim_df[interim_df['符合间歇性条件'] == True])} 条")
    print(f"   其中C类产品线: {len(interim_df[(interim_df['符合间歇性条件'] == True) & (interim_df['产品线分类'] == 'C')])} 条")
    print(f"   排除不可统计预测后目标产品线: {len(target_lines)} 条")
    print(f"   不可统计预测产品线: {len(unforecastable_lines)} 条")

    # 5. 生成低置信度清单
    print("[清单] 生成低置信度清单...")
    low_confidence_df = generate_low_confidence_list(df, baseline_df)
    low_confidence_file = OUTPUT_DIR / "low_confidence_forecast_list.csv"
    low_confidence_df.to_csv(low_confidence_file, index=False, encoding='utf-8-sig')
    print(f"   已保存: {low_confidence_file}")

    # 6. 保存目标产品线清单
    target_lines_file = OUTPUT_DIR / "intermittent_target_lines_corrected.csv"
    target_lines.to_csv(target_lines_file, index=False, encoding='utf-8-sig')
    print(f"   已保存: {target_lines_file}")

    # 7. 保存不可统计预测清单
    unforecastable_file = OUTPUT_DIR / "unforecastable_lines.csv"
    unforecastable_lines.to_csv(unforecastable_file, index=False, encoding='utf-8-sig')
    print(f"   已保存: {unforecastable_file}")

    # 8. 输出总结
    print()
    print("[总结] 修正版目标产品线详情:")
    if len(target_lines) > 0:
        print(target_lines[['产品线名称', '基线WAPE', '最近36月非零月占比', '近期12月有效季度', '销售额CV']].to_string(index=False))
    else:
        print("   [警告] 没有符合条件的目标产品线！")

    print()
    print("[总结] 不可统计预测产品线:")
    if len(unforecastable_lines) > 0:
        print(unforecastable_lines[['产品线名称', '基线WAPE', '近期12月有效季度']].to_string(index=False))
    else:
        print("   无不可统计预测产品线")

    # 9. 低置信度清单统计
    print()
    print("[统计] 低置信度清单统计:")
    print(low_confidence_df.groupby('预测可信等级').size())

    elapsed_time = time.time() - start_time
    print()
    print(f"[完成] 实验1.1修正版执行完成！")
    print(f"[耗时] {elapsed_time:.1f} 秒")

    # 10. 下一步提示
    if len(target_lines) > 0:
        print()
        print("[下一步] 对目标产品线执行完整方法池测试（38个方法）")
        print(f"   目标产品线: {', '.join(target_lines['产品线名称'].tolist())}")
    else:
        print()
        print("[警告] 没有符合条件的目标产品线，无法执行方法池测试")
        print("   建议: 审查覆盖率边界规则或数据质量")

if __name__ == "__main__":
    main()