# 会话记录: 字段修正、旧结果作废与0.2/1.0重跑

## 日期
2026-06-12

## 用户确认的字段口径

| 业务含义 | 字段口径 |
|---|---|
| 客户名称 | `终端客户简称`优先，缺失时用`代理商/直供名称`，再缺失用`实际终端客户`，仍缺失归`未知终端客户` |
| 客户分层 | `终端客户名称_客户类别`，仅分类 |
| SKU | `存货编码`优先，缺失时用`存货名称` |
| 成本 | 原始`总成本`映射为标准`成本` |
| 订单号 | `ERP订单号` |

## 执行内容

1. 修正`quarterly_forecast_package/run_quarterly_forecast.py`字段口径：
   - 新增`预测客户名称`派生列。
   - 新增`SKU预测键`派生列。
   - 产品×客户层级改用`预测客户名称`。
   - 产品/SKU层级改用`SKU预测键`。
   - 订单数继续使用`ERP订单号`。
2. 修正`forecast_config.locked.json`字段映射。
3. 归档旧1.0错误输出到：
   - `experiment_log/09_exp_1.0_hierarchy_granularity/output_invalid_customer_field_20260612/`
4. 重写严格版1.0脚本，按测试方案比较：
   - 产品线×季度
   - 产品线×月度→季度汇总
   - 产品品类×月度→产品线汇总
   - SKU×月度→产品线汇总
5. 重跑修正版0.2基线。
6. 重跑严格版1.0。
7. 写入修正版日志。

## 修正版0.2结果

| 指标 | 结果 |
|---|---:|
| 产品线数 | 17 |
| 方法数 | 552 |
| 回测明细 | 56,304 |
| 产品线简单平均WAPE | 29.63% |
| 公司金额加权WAPE | 9.50% |
| BT04-BT06金额加权WAPE | 10.18% |
| 金额加权Bias | -4.52% |

## 严格版1.0结果

推荐非基线层级的产品线：

| 产品线 | 推荐方案 | 改善 |
|---|---|---:|
| POE电源管理 | SKU×月度→产品线汇总 | 17.8pp |
| 电脑&计算电源管理 | 产品线×月度→季度汇总 | 11.6pp |
| 通用电源管理 | SKU×月度→产品线汇总 | 3.0pp |
| 音频功放 | SKU×月度→产品线汇总 | 21.1pp |

低置信度产品线：
- 新显示MLED驱动
- 无刷直流电机驱动
- 未分类
- 电源模组

## 文件变更

- `quarterly_forecast_package/run_quarterly_forecast.py`
- `experiment_log/03_exp_0.1_env_setup/output/forecast_config.locked.json`
- `experiment_log/05_exp_0.2_baseline_lock/exp_0.2_corrected_customer_log.md`
- `experiment_log/05_exp_0.2_baseline_lock/output/baseline_corrected_customer_20260612/`
- `experiment_log/09_exp_1.0_hierarchy_granularity/run_1.0_hierarchy_granularity.py`
- `experiment_log/09_exp_1.0_hierarchy_granularity/exp_1.0_log.md`
- `experiment_log/09_exp_1.0_hierarchy_granularity/output/`
- `experiment_log/09_exp_1.0_hierarchy_granularity/output_invalid_customer_field_20260612/`

## 决策

1. 旧1.0结果不可引用，仅保留归档。
2. 后续实验以修正版0.2基线为对照。
3. 后续1.1-1.4按严格版1.0推荐层级分产品线运行。
4. 联合预测输出是后续最终输出/专题，不混入1.0层级选择实验。
