# 实验 0.2 修正版: 客户/SKU字段口径修正后基线重跑

## 元信息
- 日期: 2026-06-12
- 数据文件: `data/财务分析-5月（6.3）.xlsx`
- 工作表: `总表`
- 输出目录: `output/baseline_corrected_customer_20260612/`
- 触发原因: 原基线中产品×客户层级使用 `代理商/直供名称` 作为客户键，需改为最终客户口径。

## 字段口径修正

| 业务含义 | 修正后口径 |
|---|---|
| 客户建模键 | `预测客户名称` = `终端客户简称` → `代理商/直供名称` → `实际终端客户` → `未知终端客户` |
| 客户分层 | `终端客户名称_客户类别`，只作分类，不作客户名称 |
| SKU建模键 | `SKU预测键` = `存货编码` → `存货名称` |
| SKU展示 | `存货名称_展示` |
| 成本 | 原始`总成本`映射为标准`成本` |
| 订单号 | `ERP订单号` |

## 执行命令

```powershell
python quarterly_forecast_package\run_quarterly_forecast.py `
  --config experiment_log\03_exp_0.1_env_setup\output\forecast_config.locked.json `
  --output experiment_log\05_exp_0.2_baseline_lock\output\baseline_corrected_customer_20260612
```

## 执行结果

| 指标 | 修正后结果 |
|---|---:|
| 产品线数 | 17 |
| 候选方法数 | 552 |
| 回测明细行数 | 56,304 |
| 排行榜行数 | 9,384 |
| 产品线简单平均WAPE | 29.63% |
| 产品线中位数WAPE | 20.15% |
| 公司总盘金额加权WAPE | 9.50% |
| 公司总盘金额加权Bias | -4.52% |
| BT04-BT06金额加权WAPE | 10.18% |

## 与原基线的主要差异

- 简单平均WAPE从约30.63%变为29.63%。
- 金额加权WAPE从约9.87%变为9.50%。
- 客户相关层级现在使用最终客户口径，不再直接使用代理商/直供名称。
- SKU层级现在使用`存货编码`优先，而不是仅用`存货名称`。

## 输出文件

- `output/baseline_corrected_customer_20260612/预测方法排行榜.csv`
- `output/baseline_corrected_customer_20260612/预测方法回测明细.csv`
- `output/baseline_corrected_customer_20260612/产品线季度历史与预测.csv`
- `output/baseline_corrected_customer_20260612/产品级价格与预测贡献.csv`
- `output/baseline_corrected_customer_20260612/baseline_corrected_summary.csv`
- `output/baseline_corrected_customer_20260612/baseline_corrected_selected_methods.csv`

## 结论

修正字段口径后，基线重跑完成。后续实验应以本修正版基线为对照，不再引用旧0.2中涉及产品×客户层级的客户口径结论。
