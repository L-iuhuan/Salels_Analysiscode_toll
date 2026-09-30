# -*- coding: utf-8 -*-
"""读取冒烟：quarterly read_raw_data 直读快照 parquet + field_map 验证"""
import sys
from pathlib import Path
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'E:\3-其他资料\数据分析\forecasting\quarterly')

import run_quarterly_forecast as rq

cfg = rq.load_config(Path(r'E:\3-其他资料\数据分析\forecasting\quarterly\forecast_config.platform.json'))
log = rq.OperationLog()
df = rq.read_raw_data(Path(cfg['data_path']), log, sheet_name=cfg.get('sheet_name', 0), field_map=cfg.get('field_map'))
print('读取成功: 行数=%d 列数=%d' % (len(df), len(df.columns)))
print('列:', list(df.columns))
print('发货日期范围:', df['发货日期'].min(), '~', df['发货日期'].max())
print('近3行样例:')
print(df[['发货日期', '存货名称', '发货数量', 'RMB 未税金额小计', '成本', '利润']].head(3).to_string())
