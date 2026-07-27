# -*- coding: utf-8 -*-
"""
实验 1.4: 新品/老品分层预测初探
创建: 2026-06-15

假设: 新品（首次出货 < 12个月）和老品（出货 > 24个月）的预测行为模式不同，
      分开预测再汇总优于混在一起预测。

方法:
1. 使用"是否新品"字段区分新品和老品
2. 对老品部分用基线方法预测（数据稳定）
3. 对新品部分用最近3桶均值 + 增长趋势方向
4. 两组合并后与基线对比

成功标准:
- 实验组公司总盘金额加权WAPE和产品线简单平均WAPE至少一个改善，另一个不恶化>1pp
- 新品部分WAPE改善 ≥ 5个百分点
- 如果无效 → 记录为"新品分层在该数据集上无显著收益"
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
    str_cols = ['型号_产品线（新）', '存货编码', '存货名称', '是否新品']
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
    
    # 新品标记：是否新品 = "是" 为新品，其余（NaN或<NA>或空）为老品
    # 使用fillna将<NA>转换为False
    df['是否新品标记'] = (df['是否新品'] == '是').fillna(False)
    
    print("[数据] 清洗后数据: {} 行".format(len(df)))
    print("[数据] 产品线数量: {} 种".format(df['产品线名称'].nunique()))
    print("[数据] 新品数量: {} 个SKU".format(df[df['是否新品标记'] == True]['存货编码'].nunique()))
    print("[数据] 老品数量: {} 个SKU".format(df[df['是否新品标记'] == False]['存货编码'].nunique()))
    
    return df


def build_quarterly_series_by_product(df, target_lines):
    """构建产品级季度时间序列"""
    print("[特征] 构建产品级季度时间序列...")
    
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
    
    # 筛选目标产品线
    df_target = df[df['产品线名称'].isin(target_lines)].copy()
    
    # 分配桶
    df_target['桶编号'] = pd.NA
    for bi in bucket_info:
        mask = df_target['_月'].between(bi['开始Period'], bi['结束Period'])
        df_target.loc[mask, '桶编号'] = bi['桶编号']
    df_target = df_target[df_target['桶编号'].notna()].copy()
    
    # 按产品×桶聚合
    product_agg = df_target.groupby(['产品线名称', '存货编码', '是否新品标记', '桶编号'], dropna=False).agg(
        销售额=('销售额', 'sum'),
        销售量=('销量', 'sum'),
    ).reset_index()
    
    print("[特征] 产品级数据: {} 条记录".format(len(product_agg)))
    
    return product_agg, bucket_ids


def run_new_product_experiment(product_agg, bucket_ids):
    """执行新品/老品分层实验"""
    print("[实验1.4] 执行新品/老品分层实验...")
    
    results = []
    
    for pline in product_agg['产品线名称'].unique():
        pline_data = product_agg[product_agg['产品线名称'] == pline].copy()
        
        # 分离新品和老品
        # 新品：是否新品标记 == True
        # 老品：是否新品标记 == False 或 NaN
        new_products = pline_data[pline_data['是否新品标记'] == True]
        old_products = pline_data[pline_data['是否新品标记'] != True]  # 包括False和NaN
        
        # 计算新品和老品的预测
        new_predictions = []
        new_actuals = []
        old_predictions = []
        old_actuals = []
        
        # 新品预测：最近3桶均值
        for sku in new_products['存货编码'].unique():
            sku_data = new_products[new_products['存货编码'] == sku].sort_values('桶编号')
            if len(sku_data) >= 3:
                last_3 = sku_data.tail(3)['销售额'].values
                pred = np.mean(last_3)
                actual = sku_data.tail(1)['销售额'].values[0]
                new_predictions.append(pred)
                new_actuals.append(actual)
        
        # 老品预测：使用所有桶的均值（模拟基线方法）
        for sku in old_products['存货编码'].unique():
            sku_data = old_products[old_products['存货编码'] == sku].sort_values('桶编号')
            if len(sku_data) >= 3:
                all_sales = sku_data['销售额'].values
                pred = np.mean(all_sales)
                actual = sku_data.tail(1)['销售额'].values[0]
                old_predictions.append(pred)
                old_actuals.append(actual)
        
        # 计算WAPE
        new_wape = calculate_wape(np.array(new_predictions), np.array(new_actuals)) if new_predictions else np.nan
        old_wape = calculate_wape(np.array(old_predictions), np.array(old_actuals)) if old_predictions else np.nan
        
        # 计算整体WAPE（新品+老品合并）
        all_predictions = new_predictions + old_predictions
        all_actuals = new_actuals + old_actuals
        combined_wape = calculate_wape(np.array(all_predictions), np.array(all_actuals)) if all_predictions else np.nan
        
        results.append({
            '产品线名称': pline,
            '新品SKU数': len(new_products['存货编码'].unique()),
            '老品SKU数': len(old_products['存货编码'].unique()),
            '新品WAPE': new_wape,
            '老品WAPE': old_wape,
            '合并WAPE': combined_wape,
            '新品样本数': len(new_predictions),
            '老品样本数': len(old_predictions),
        })
    
    return pd.DataFrame(results)


def calculate_wape(predictions, actuals):
    """计算WAPE（过滤零值）"""
    if len(predictions) == 0 or len(actuals) == 0:
        return np.nan
    
    valid_mask = actuals != 0
    if np.sum(valid_mask) == 0:
        return np.nan
    
    ape = np.abs((predictions[valid_mask] - actuals[valid_mask]) / actuals[valid_mask])
    return np.mean(ape)


def main():
    """主执行函数"""
    import sys
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    
    print("[开始] 实验1.4: 新品/老品分层预测初探...")
    print("[数据源] {}".format(DATA_FILE))
    print()
    
    start_time = time.time()
    
    # 1. 加载数据
    df = load_data_with_calamine()
    
    # 2. 加载基线数据获取产品线分类
    baseline_file = PROJECT_ROOT / "experiment_log" / "05_exp_0.2_baseline_lock" / "output" / "baseline_metrics_by_pline.csv"
    baseline_df = pd.read_csv(baseline_file)
    baseline_df = baseline_df.rename(columns={'产品线': '产品线名称', '销售额WAPE': '基线WAPE', '分类': '产品线分类'})
    
    # C类产品线
    c_class_lines = baseline_df[baseline_df['产品线分类'] == 'C']['产品线名称'].tolist()
    print("[筛选] C类产品线: {} 条".format(len(c_class_lines)))
    
    # 3. 构建产品级季度时间序列
    product_agg, bucket_ids = build_quarterly_series_by_product(df, c_class_lines)
    
    # 4. 执行新品/老品分层实验
    experiment_results = run_new_product_experiment(product_agg, bucket_ids)
    
    if len(experiment_results) > 0:
        # 保存结果
        experiment_results.to_csv(OUTPUT_DIR / 'new_product_experiment_results.csv', index=False, encoding='utf-8-sig')
        
        print()
        print("[实验1.4] 新品/老品分层实验结果:")
        print(experiment_results.to_string(index=False))
        
        # 计算整体统计
        total_new_products = experiment_results['新品SKU数'].sum()
        total_old_products = experiment_results['老品SKU数'].sum()
        avg_new_wape = experiment_results['新品WAPE'].mean()
        avg_old_wape = experiment_results['老品WAPE'].mean()
        avg_combined_wape = experiment_results['合并WAPE'].mean()
        
        print()
        print("[统计] 整体统计:")
        print("  新品SKU总数: {}".format(total_new_products))
        print("  老品SKU总数: {}".format(total_old_products))
        print("  平均新品WAPE: {:.2%}".format(avg_new_wape) if not np.isnan(avg_new_wape) else "  平均新品WAPE: N/A")
        print("  平均老品WAPE: {:.2%}".format(avg_old_wape) if not np.isnan(avg_old_wape) else "  平均老品WAPE: N/A")
        print("  平均合并WAPE: {:.2%}".format(avg_combined_wape) if not np.isnan(avg_combined_wape) else "  平均合并WAPE: N/A")
        
        # 评估成功标准
        print()
        print("[评估] 成功标准:")
        
        # 检查是否有足够的新品样本
        if total_new_products > 0:
            print("  新品样本充足: {} 个SKU".format(total_new_products))
            
            # 计算新品WAPE改善
            if not np.isnan(avg_new_wape) and not np.isnan(avg_old_wape):
                improvement = avg_old_wape - avg_new_wape
                print("  新品WAPE vs 老品WAPE: {:.2%} vs {:.2%}".format(avg_new_wape, avg_old_wape))
                print("  改善: {:.2%}".format(improvement))
                
                if improvement >= 0.05:
                    print("  [通过] 新品WAPE改善 ≥ 5个百分点")
                else:
                    print("  [未通过] 新品WAPE改善 < 5个百分点")
            else:
                print("  [警告] WAPE计算不足，无法评估")
        else:
            print("  [警告] 新品样本不足，无法评估")
    
    # 5. 生成报告
    print()
    print("[报告] 生成实验1.4报告...")
    
    report = []
    report.append("# 实验1.4: 新品/老品分层预测初探")
    report.append("")
    report.append("## 完成时间: {}".format(pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')))
    report.append("")
    report.append("## 实验方法:")
    report.append("- 使用'是否新品'字段区分新品和老品")
    report.append("- 新品预测: 最近3桶均值")
    report.append("- 老品预测: 所有桶均值（模拟基线方法）")
    report.append("")
    report.append("## 实验结果:")
    report.append("- C类产品线: {} 条".format(len(c_class_lines)))
    report.append("- 新品SKU总数: {}".format(total_new_products))
    report.append("- 老品SKU总数: {}".format(total_old_products))
    report.append("")
    report.append("## 输出文件:")
    report.append("- new_product_experiment_results.csv")
    
    # 保存报告
    with open(OUTPUT_DIR / 'experiment_1.4_report.md', 'w', encoding='utf-8') as f:
        f.write('\n'.join(report))
    
    elapsed_time = time.time() - start_time
    print()
    print("[完成] 实验1.4执行完成！")
    print("[耗时] {:.1f} 秒".format(elapsed_time))


if __name__ == "__main__":
    main()
