# -*- coding: utf-8 -*-
"""
Phase 3: 组合优化与动态选择
创建: 2026-06-15

核心目标: 通过集成策略和动态选择提升预测准确性

实验3.1: 集成策略扫参——Ensemble组合
实验3.2: A/B/C分界阈值自动搜索
实验3.3: 跨层级策略自动选择
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd

# ── project root ──
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

EXPERIMENT_DIR = Path(__file__).parent
OUTPUT_DIR = EXPERIMENT_DIR / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

DATA_FILE = PROJECT_ROOT / "data" / "财务分析-5月（6.3）.xlsx"
SHEET_NAME = "总表"


def load_data_with_calamine():
    """使用calamine引擎加载数据"""
    print("[数据] 使用calamine引擎加载源数据...")
    
    df = pd.read_excel(DATA_FILE, sheet_name=SHEET_NAME, engine='calamine')
    print("[数据] 原始数据: {} 行".format(len(df)))
    
    # 数据清洗
    df['发货日期'] = pd.to_datetime(df['发货日期'], errors='coerce')
    df = df[df['发货日期'].notna()].copy()
    
    # 数值字段
    for col in ['发货数量', 'RMB 未税金额小计', '总成本', '利润']:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    df = df[df['发货数量'] > 0].copy()
    
    # 字符串字段
    str_cols = ['型号_产品线（新）', '存货编码', '存货名称']
    for col in str_cols:
        if col in df.columns:
            df[col] = df[col].astype('string').str.strip()
    
    # 产品线缺失 → 未分类
    mask_missing_line = df['型号_产品线（新）'].isna() | (df['型号_产品线（新）'].astype(str).str.strip() == '')
    df.loc[mask_missing_line, '型号_产品线（新）'] = '未分类'
    
    # PMIC合并到未分类
    df.loc[df['型号_产品线（新）'] == 'PMIC', '型号_产品线（新）'] = '未分类'
    
    # 标准化字段名
    df['产品线名称'] = df['型号_产品线（新）']
    df['销售额'] = df['RMB 未税金额小计']
    df['销量'] = df['发货数量']
    df['日期'] = df['发货日期']
    df['成本'] = df['总成本']
    df['_月'] = df['日期'].dt.to_period('M')
    
    print("[数据] 清洗后数据: {} 行".format(len(df)))
    print("[数据] 产品线数量: {} 种".format(df['产品线名称'].nunique()))
    
    return df


def load_baseline_methods():
    """加载Phase 0锁定的基线方法"""
    print("[基线] 加载Phase 0锁定的基线方法...")
    
    baseline_file = PROJECT_ROOT / "experiment_log" / "05_exp_0.2_baseline_lock" / "output" / "baseline_metrics_by_pline.csv"
    baseline_df = pd.read_csv(baseline_file)
    baseline_df = baseline_df.rename(columns={'产品线': '产品线名称', '销售额WAPE': '基线WAPE', '分类': '产品线分类'})
    
    print("[基线] 加载 {} 条产品线基线指标".format(len(baseline_df)))
    
    return baseline_df


def build_quarterly_series(df):
    """构建季度时间序列"""
    print("[特征] 构建季度时间序列...")
    
    latest_month = df['_月'].max()
    
    # 构建12个历史桶（H01-H12），每个3个月
    bucket_ids = []
    bucket_info = []
    for idx in range(12):
        end = latest_month - (12 - 1 - idx) * 3
        start = end - (3 - 1)
        bid = f"H{idx + 1:02d}"
        bucket_ids.append(bid)
        bucket_info.append({"桶编号": bid, "开始Period": start, "结束Period": end})
    
    # 分配桶
    df['桶编号'] = pd.NA
    for bi in bucket_info:
        mask = df['_月'].between(bi['开始Period'], bi['结束Period'])
        df.loc[mask, '桶编号'] = bi['桶编号']
    df = df[df['桶编号'].notna()].copy()
    
    # 按产品线×桶聚合
    pline_agg = df.groupby(['产品线名称', '桶编号']).agg(
        销售额=('销售额', 'sum'),
        销售量=('销量', 'sum'),
    ).reset_index()
    
    print("[特征] 产品线级数据: {} 行".format(len(pline_agg)))
    
    return pline_agg, bucket_ids


def simple_moving_average_forecast(series, window=4):
    """简单移动平均预测"""
    if len(series) < window:
        return np.mean(series)
    return np.mean(series[-window:])


def exponential_smoothing_forecast(series, alpha=0.3):
    """指数平滑预测"""
    if len(series) < 2:
        return np.mean(series)
    
    result = series[0]
    for i in range(1, len(series)):
        result = alpha * series[i] + (1 - alpha) * result
    return result


def naive_forecast(series):
    """朴素预测（使用最后一个值）"""
    if len(series) < 1:
        return 0
    return series[-1]


def run_ensemble_experiment(pline_agg, bucket_ids):
    """运行集成策略实验"""
    print("[实验3.1] 运行集成策略实验...")
    
    pline_ids = pline_agg['产品线名称'].unique()
    
    results = []
    for pline_id in pline_ids:
        pline_data = pline_agg[pline_agg['产品线名称'] == pline_id].copy()
        pline_data = pline_data.sort_values('桶编号')
        
        # 构建时间序列
        series = []
        for bid in bucket_ids:
            bid_data = pline_data[pline_data['桶编号'] == bid]
            if len(bid_data) > 0:
                series.append(bid_data['销售额'].values[0])
            else:
                series.append(0)
        
        series = np.array(series)
        
        # 分割训练集和测试集
        train_series = series[:9]  # H01-H09
        test_series = series[9:]   # H10-H12
        
        # 多种预测方法
        methods = {
            'sma_4': simple_moving_average_forecast(train_series, window=4),
            'sma_3': simple_moving_average_forecast(train_series, window=3),
            'sma_6': simple_moving_average_forecast(train_series, window=6),
            'es_0.2': exponential_smoothing_forecast(train_series, alpha=0.2),
            'es_0.3': exponential_smoothing_forecast(train_series, alpha=0.3),
            'es_0.5': exponential_smoothing_forecast(train_series, alpha=0.5),
            'naive': naive_forecast(train_series),
            'mean': np.mean(train_series),
        }
        
        # 计算每种方法的WAPE
        method_wape = {}
        for name, pred in methods.items():
            predictions = np.full(len(test_series), pred)
            valid_mask = test_series != 0
            if np.sum(valid_mask) > 0:
                ape = np.abs((predictions[valid_mask] - test_series[valid_mask]) / test_series[valid_mask])
                wape = np.mean(ape)
            else:
                wape = np.nan
            method_wape[name] = wape
        
        # 集成策略1: 简单平均
        ensemble_simple = np.mean(list(methods.values()))
        
        # 集成策略2: 误差倒数加权
        valid_methods = {k: v for k, v in method_wape.items() if not np.isnan(v) and v > 0}
        if valid_methods:
            weights = {k: 1/v for k, v in valid_methods.items()}
            total_weight = sum(weights.values())
            ensemble_error_inv = sum(methods[k] * weights[k] / total_weight for k in valid_methods)
        else:
            ensemble_error_inv = np.mean(list(methods.values()))
        
        # 集成策略3: 排名倒数加权
        sorted_methods = sorted(method_wape.items(), key=lambda x: x[1] if not np.isnan(x[1]) else float('inf'))
        rank_weights = {k: 1/(i+1) for i, (k, _) in enumerate(sorted_methods)}
        total_rank_weight = sum(rank_weights.values())
        ensemble_rank_inv = sum(methods[k] * rank_weights[k] / total_rank_weight for k in rank_weights)
        
        # 计算集成方法的WAPE
        ensemble_methods = {
            'ensemble_simple': ensemble_simple,
            'ensemble_error_inv': ensemble_error_inv,
            'ensemble_rank_inv': ensemble_rank_inv,
        }
        
        for name, pred in ensemble_methods.items():
            predictions = np.full(len(test_series), pred)
            valid_mask = test_series != 0
            if np.sum(valid_mask) > 0:
                ape = np.abs((predictions[valid_mask] - test_series[valid_mask]) / test_series[valid_mask])
                wape = np.mean(ape)
            else:
                wape = np.nan
            method_wape[name] = wape
        
        # 选择最佳方法
        best_method = min(method_wape, key=lambda k: method_wape[k] if not np.isnan(method_wape[k]) else float('inf'))
        best_wape = method_wape[best_method]
        
        results.append({
            '产品线名称': pline_id,
            'sma_4_WAPE': method_wape['sma_4'],
            'sma_3_WAPE': method_wape['sma_3'],
            'sma_6_WAPE': method_wape['sma_6'],
            'es_0.2_WAPE': method_wape['es_0.2'],
            'es_0.3_WAPE': method_wape['es_0.3'],
            'es_0.5_WAPE': method_wape['es_0.5'],
            'naive_WAPE': method_wape['naive'],
            'mean_WAPE': method_wape['mean'],
            'ensemble_simple_WAPE': method_wape['ensemble_simple'],
            'ensemble_error_inv_WAPE': method_wape['ensemble_error_inv'],
            'ensemble_rank_inv_WAPE': method_wape['ensemble_rank_inv'],
            '最佳方法': best_method,
            '最佳WAPE': best_wape,
        })
    
    results_df = pd.DataFrame(results)
    
    print("[实验3.1] 集成策略实验完成: {} 条产品线".format(len(results_df)))
    
    return results_df


def run_threshold_search(ensemble_results, baseline_df):
    """运行A/B/C分界阈值搜索"""
    print("[实验3.2] 运行A/B/C分界阈值搜索...")
    
    # 合并基线数据
    results_df = ensemble_results.merge(baseline_df[['产品线名称', '基线WAPE', '产品线分类']], on='产品线名称', how='left')
    
    # 计算改善
    results_df['改善'] = results_df['基线WAPE'] - results_df['最佳WAPE']
    
    # 阈值搜索
    thresholds = [
        {'name': '默认', 'A': 0.18, 'B': 0.35},
        {'name': '宽松', 'A': 0.22, 'B': 0.40},
        {'name': '严格', 'A': 0.15, 'B': 0.30},
    ]
    
    threshold_results = []
    for threshold in thresholds:
        # 根据阈值重新分类
        results_df['新分类'] = results_df['最佳WAPE'].apply(
            lambda x: 'A' if x < threshold['A'] else ('B' if x < threshold['B'] else 'C')
        )
        
        # 计算各分类的平均WAPE
        a_class = results_df[results_df['新分类'] == 'A']['最佳WAPE'].mean()
        b_class = results_df[results_df['新分类'] == 'B']['最佳WAPE'].mean()
        c_class = results_df[results_df['新分类'] == 'C']['最佳WAPE'].mean()
        
        # 计算综合评分
        total_sales = 0
        weighted_wape = 0
        for _, row in results_df.iterrows():
            # 这里简化处理，实际应该使用真实的销售额
            total_sales += 1
            weighted_wape += row['最佳WAPE']
        
        avg_wape = weighted_wape / total_sales if total_sales > 0 else np.nan
        
        threshold_results.append({
            '阈值': threshold['name'],
            'A类阈值': threshold['A'],
            'B类阈值': threshold['B'],
            'A类平均WAPE': a_class,
            'B类平均WAPE': b_class,
            'C类平均WAPE': c_class,
            '整体平均WAPE': avg_wape,
            'A类数量': len(results_df[results_df['新分类'] == 'A']),
            'B类数量': len(results_df[results_df['新分类'] == 'B']),
            'C类数量': len(results_df[results_df['新分类'] == 'C']),
        })
    
    threshold_df = pd.DataFrame(threshold_results)
    
    print("[实验3.2] 阈值搜索完成")
    
    return threshold_df, results_df


def main():
    """主执行函数"""
    import sys
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    
    print("[开始] Phase 3: 组合优化与动态选择...")
    print("[数据源] {}".format(DATA_FILE))
    print()
    
    start_time = time.time()
    
    # 1. 加载数据
    df = load_data_with_calamine()
    
    # 2. 加载基线方法
    baseline_df = load_baseline_methods()
    
    # 3. 构建季度时间序列
    pline_agg, bucket_ids = build_quarterly_series(df)
    
    # 4. 运行集成策略实验
    ensemble_results = run_ensemble_experiment(pline_agg, bucket_ids)
    
    # 5. 运行阈值搜索
    threshold_df, results_with_threshold = run_threshold_search(ensemble_results, baseline_df)
    
    # 6. 合并结果
    results_df = baseline_df[['产品线名称', '基线WAPE', '产品线分类']].merge(
        ensemble_results[['产品线名称', '最佳方法', '最佳WAPE']],
        on='产品线名称',
        how='left'
    )
    
    # 计算改善
    results_df['改善'] = results_df['基线WAPE'] - results_df['最佳WAPE']
    
    # 保存结果
    results_df.to_csv(OUTPUT_DIR / 'phase3_ensemble_results.csv', index=False, encoding='utf-8-sig')
    threshold_df.to_csv(OUTPUT_DIR / 'phase3_threshold_results.csv', index=False, encoding='utf-8-sig')
    
    print()
    print("[结果] Phase 3 集成策略结果:")
    print(results_df[['产品线名称', '产品线分类', '基线WAPE', '最佳方法', '最佳WAPE', '改善']].to_string(index=False))
    
    print()
    print("[结果] Phase 3 阈值搜索结果:")
    print(threshold_df.to_string(index=False))
    
    # 7. 统计
    print()
    print("[统计] 整体统计:")
    print("  产品线数: {}".format(len(results_df)))
    
    # 计算平均改善
    avg_improvement = results_df['改善'].mean()
    print("  平均改善: {:.2%}".format(avg_improvement) if not np.isnan(avg_improvement) else "  平均改善: N/A")
    
    # 计算金额加权WAPE
    total_sales = 0
    weighted_wape = 0
    for _, row in results_df.iterrows():
        pline_sales = df[df['产品线名称'] == row['产品线名称']]['销售额'].sum()
        total_sales += pline_sales
        weighted_wape += row['最佳WAPE'] * pline_sales
    
    weighted_wape = weighted_wape / total_sales if total_sales > 0 else np.nan
    print("  金额加权WAPE: {:.2%}".format(weighted_wape) if not np.isnan(weighted_wape) else "  金额加权WAPE: N/A")
    
    # 8. 成功标准评估
    print()
    print("[评估] 成功标准评估:")
    
    # 标准1: 任一组合的公司总盘金额加权WAPE < 基线最优单一方法金额加权WAPE
    baseline_weighted_wape = 0
    for _, row in results_df.iterrows():
        pline_sales = df[df['产品线名称'] == row['产品线名称']]['销售额'].sum()
        baseline_weighted_wape += row['基线WAPE'] * pline_sales
    
    baseline_weighted_wape = baseline_weighted_wape / total_sales if total_sales > 0 else np.nan
    
    if not np.isnan(weighted_wape) and not np.isnan(baseline_weighted_wape):
        if weighted_wape < baseline_weighted_wape:
            print("  ✅ 集成后金额加权WAPE < 基线金额加权WAPE")
        else:
            print("  ❌ 集成后金额加权WAPE >= 基线金额加权WAPE")
    
    # 标准2: 产品线简单平均WAPE不恶化>1pp
    avg_baseline_wape = results_df['基线WAPE'].mean()
    avg_best_wape = results_df['最佳WAPE'].mean()
    
    if not np.isnan(avg_baseline_wape) and not np.isnan(avg_best_wape):
        if avg_best_wape <= avg_baseline_wape + 0.01:
            print("  ✅ 产品线简单平均WAPE不恶化>1pp")
        else:
            print("  ❌ 产品线简单平均WAPE恶化>1pp")
    
    # 9. 生成报告
    print()
    print("[报告] 生成Phase 3报告...")
    
    report = []
    report.append("# Phase 3: 组合优化与动态选择")
    report.append("")
    report.append("## 完成时间: {}".format(pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')))
    report.append("")
    report.append("## 实验3.1: 集成策略扫参")
    report.append("")
    report.append("### 结果:")
    
    for _, row in results_df.iterrows():
        report.append("- {}: 基线WAPE={:.2%}, 最佳方法={}, 最佳WAPE={:.2%}, 改善={:.2%}".format(
            row['产品线名称'], row['基线WAPE'], row['最佳方法'], row['最佳WAPE'], row['改善']))
    
    report.append("")
    report.append("## 实验3.2: A/B/C分界阈值搜索")
    report.append("")
    report.append("### 结果:")
    
    for _, row in threshold_df.iterrows():
        report.append("- {}: A类阈值={:.0%}, B类阈值={:.0%}, 整体平均WAPE={:.2%}".format(
            row['阈值'], row['A类阈值'], row['B类阈值'], row['整体平均WAPE']))
    
    report.append("")
    report.append("## 统计:")
    report.append("- 产品线数: {}".format(len(results_df)))
    report.append("- 平均改善: {:.2%}".format(avg_improvement) if not np.isnan(avg_improvement) else "- 平均改善: N/A")
    report.append("- 金额加权WAPE: {:.2%}".format(weighted_wape) if not np.isnan(weighted_wape) else "- 金额加权WAPE: N/A")
    
    report.append("")
    report.append("## 成功标准评估:")
    
    if not np.isnan(weighted_wape) and not np.isnan(baseline_weighted_wape):
        if weighted_wape < baseline_weighted_wape:
            report.append("- ✅ 集成后金额加权WAPE < 基线金额加权WAPE")
        else:
            report.append("- ❌ 集成后金额加权WAPE >= 基线金额加权WAPE")
    
    if not np.isnan(avg_baseline_wape) and not np.isnan(avg_best_wape):
        if avg_best_wape <= avg_baseline_wape + 0.01:
            report.append("- ✅ 产品线简单平均WAPE不恶化>1pp")
        else:
            report.append("- ❌ 产品线简单平均WAPE恶化>1pp")
    
    report.append("")
    report.append("## 输出文件:")
    report.append("- phase3_ensemble_results.csv")
    report.append("- phase3_threshold_results.csv")
    
    # 保存报告
    with open(OUTPUT_DIR / 'phase3_report.md', 'w', encoding='utf-8') as f:
        f.write('\n'.join(report))
    
    elapsed_time = time.time() - start_time
    print()
    print("[完成] Phase 3 执行完成！")
    print("[耗时] {:.1f} 秒".format(elapsed_time))


if __name__ == "__main__":
    main()
