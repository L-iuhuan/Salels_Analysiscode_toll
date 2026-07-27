# -*- coding: utf-8 -*-
import pandas as pd
from pathlib import Path
root = Path(r'E:\3-其他资料\数据分析\semiconductor_analysis')
base_dir = root/'experiment_log'/'05_exp_0.2_baseline_lock'/'output'/'baseline_corrected_customer_20260612'
rank = pd.read_csv(base_dir/'预测方法排行榜.csv')
detail = pd.read_csv(base_dir/'预测方法回测明细.csv')
sel = rank[rank['是否最终选中'].astype(str)=='是'].copy()
sel_ids = set(zip(sel['产品线'], sel['方法ID']))
mask = detail.apply(lambda r: (r['产品线'], r['方法ID']) in sel_ids, axis=1)
sel_detail = detail[mask].copy()
weighted_wape = sel_detail['销售额绝对误差'].sum() / sel_detail['实际销售额'].abs().sum()
weighted_bias = sel_detail['销售额误差'].sum() / sel_detail['实际销售额'].sum()
holdout = sel_detail[sel_detail['回测折次'].isin(['BT04','BT05','BT06'])]
holdout_wape = holdout['销售额绝对误差'].sum() / holdout['实际销售额'].abs().sum()
summary = pd.DataFrame([{
    'selected_lines': len(sel),
    'ranking_rows': len(rank),
    'detail_rows': len(detail),
    'simple_mean_wape': sel['销售额WAPE'].mean(),
    'median_wape': sel['销售额WAPE'].median(),
    'amount_weighted_wape': weighted_wape,
    'amount_weighted_bias': weighted_bias,
    'bt04_06_amount_weighted_wape': holdout_wape,
}])
summary.to_csv(base_dir/'baseline_corrected_summary.csv', index=False, encoding='utf-8-sig')
sel[['产品线','方法ID','方法名称','方法层级','销售额WAPE','销售额偏差率','综合评分']].to_csv(base_dir/'baseline_corrected_selected_methods.csv', index=False, encoding='utf-8-sig')
print(summary.to_string(index=False))
print(sel[['产品线','方法层级','销售额WAPE','销售额偏差率']].to_string(index=False))
