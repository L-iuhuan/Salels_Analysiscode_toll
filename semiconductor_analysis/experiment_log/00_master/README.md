# 实验日志目录结构

## 目录说明

所有实验记录（日志、脚本、输出）统一放在 `experiment_log/` 下，按编号归档。

```
experiment_log/
├── 00_master/                              # 主日志和会话总结
│   ├── master_log.md                       # 实验主日志（索引所有实验）
│   ├── phase_0_gate.md                     # Phase 0 Gate检查清单
│   ├── session_20260612_phase0_validation.md
│   └── README.md                           # 本文件
│
├── 01_exp_0.0_trivial_baselines/           # 实验0.0: 平凡基线
│   ├── exp_0.0_log.md
│   ├── run_0.0_trivial_baselines.py
│   └── output/trivial_baselines_wape.csv
│
├── 02_exp_0.0.5_coverage_diagnosis/        # 实验0.0.5: 覆盖诊断
│   ├── exp_0.0.5_log.md
│   ├── run_0.0.5_v2.py
│   └── output/product_line_coverage_diagnosis.csv
│
├── 03_exp_0.1_env_setup/                   # 实验0.1: 环境设置
│   ├── exp_0.1_log.md
│   └── output/forecast_config.locked.json
│
├── 04_exp_0.1.5_method_filter/             # 实验0.1.5: 方法筛选
│   ├── exp_0.1.5_log.md
│   ├── run_0.1.5_v2.py
│   └── output/filtered_method_pool.csv
│
├── 05_exp_0.2_baseline_lock/               # 实验0.2: 基线锁定
│   ├── exp_0.2_log.md
│   ├── run_0.2_baseline_lock.py
│   └── output/
│       ├── baseline_lock_20260612.json
│       ├── baseline_metrics_by_pline.csv
│       ├── baseline_metrics_recomputed.csv
│       ├── baseline_holdout_by_pline.csv
│       ├── baseline_validation_flags.csv
│       ├── filtered_method_pool.csv
│       ├── forecast_config.locked.json
│       ├── sku_multi_line_conflicts.csv
│       └── negative_gross_profit_forecasts.csv
│
├── 06_exp_0.2.5_full_rerun/                # 实验0.2.5: 全量复跑验证
│   ├── exp_0.2.5_log.md
│   └── output/baseline_full_rerun_20260612/
│       ├── 产品线季度历史与预测.csv
│       ├── 预测方法排行榜.csv
│       ├── 预测方法回测明细.csv
│       ├── 候选预测方法清单.csv
│       ├── 产品级价格与预测贡献.csv
│       ├── 数据质量与映射诊断.csv
│       ├── 操作日志.csv
│       ├── 产品线季度预测图表.html
│       └── 产品线季度历史与预测_含方法回测.xlsx
│
├── 07_exp_0.3_lifecycle_alignment/         # 实验0.3: 生命周期对齐
│   ├── exp_0.3_log.md
│   ├── run_0.3_v3.py
│   └── output/
│       ├── lifecycle_features_by_pline.csv
│       └── lifecycle_features_by_refgroup.csv
│
└── 08_exp_0.0.6_hierarchy_eligibility/     # 实验0.0.6: 层级准入
    ├── exp_0.0.6_log.md
    ├── run_0.0.6.py
    └── output/hierarchy_eligibility_by_pline.csv
```

## 编号规则

- **00_master**: 主日志、Gate检查、会话总结
- **01-08**: Phase 0实验（按时间顺序）
- **09+**: Phase 1及后续实验

## 每个实验目录包含

1. `exp_X.X_log.md`: 实验日志（假设、设计、结果、结论）
2. `run_X.X.py`: 实验脚本（如有）
3. `output/`: 实验输出文件（如有）

## 快速查找

| 需求 | 文件 |
|---|---|
| 查看所有实验索引 | `00_master/master_log.md` |
| 查看Phase 0 Gate状态 | `00_master/phase_0_gate.md` |
| 查看本次会话总结 | `00_master/session_20260612_phase0_validation.md` |
| 查看层级准入白名单 | `08_exp_0.0.6_hierarchy_eligibility/output/hierarchy_eligibility_by_pline.csv` |
| 查看基线WAPE | `05_exp_0.2_baseline_lock/output/baseline_metrics_recomputed.csv` |
| 查看全量复跑结果 | `06_exp_0.2.5_full_rerun/output/baseline_full_rerun_20260612/` |

## output/目录（业务数据）

```
output/
├── silver/     # 中间数据层
├── gold/       # 业务数据层
├── optimization/  # 优化结果
└── report/     # 业务报告
```

`output/` 只保留业务数据和报告，实验相关输出全部在 `experiment_log/` 下。
