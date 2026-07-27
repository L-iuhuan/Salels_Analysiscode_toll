# 会话总结: Phase 0深度验证与v1.4补丁

## 会话信息
- 日期: 2026-06-12
- 目标: 深度验证Phase 0基线，发现并修复问题，准备Phase 1
- 结果: 发现WAPE口径错误，完成v1.4补丁修订，全量复跑验证通过

---

## 操作时间线

### 1. Phase 0日志审查
- 读取实验0.0, 0.0.5, 0.1.5, 0.2, 0.3的日志文件
- 读取基线输出文件（baseline_lock_20260612.json, baseline_metrics_by_pline.csv等）
- 发现"全局WAPE=30.63%"的口径问题

### 2. WAPE口径诊断
- 发现原"全局WAPE"实为17线简单平均，非金额加权
- 重算金额加权WAPE ≈ 9.87%
- 创建baseline_metrics_recomputed.csv

### 3. 数据质量诊断
- 客户层级缺失率: 全历史15.1%, 2024+为0%
- 品类缺失率: 0.0385%
- SKU跨线冲突: 14个SKU属于2条产品线
- 负毛利预测: 1条（新显示MLED驱动）
- 创建baseline_validation_flags.csv, sku_multi_line_conflicts.csv, negative_gross_profit_forecasts.csv

### 4. 代码修复
- 修复run_quarterly_forecast.py和run_customer_forecast.py的PROJECT_ROOT路径问题
- 修改run_0.2_baseline_lock.py，新增5个验证输出

### 5. 测试方案修订
- 创建v1.4补丁，修订测试方案v1.3
- 核心修订: WAPE口径、生命周期两层、层级准入、客户时段规则、Gate标准

### 6. 层级准入诊断
- 创建run_0.0.6.py
- 生成hierarchy_eligibility_by_pline.csv
- 17条产品线×6层级准入白名单

### 7. 全量复跑验证
- 从原始Excel重新运行552方法
- 输出到output/test/baseline_full_rerun_20260612/
- 验证: 产品线/方法/选中方法/WAPE完全一致

### 8. 实验记录补齐
- 创建exp_0.0.6_log.md
- 创建exp_0.2.5_log.md
- 更新master_log.md

---

## 关键发现

### 发现1: WAPE口径混淆
- **问题**: 原"全局WAPE=30.63%"实为17线简单平均，非金额加权
- **影响**: 可能误导决策，认为基线表现差
- **修正**: 双口径报告，金额加权≈9.87%，简单平均≈30.63%

### 发现2: 客户层级时段差异
- **问题**: 全历史缺失率15.1%，但2024+缺失率为0%
- **影响**: 全历史回测需加Unknown桶，2024+可直接用
- **修正**: 分时段处理规则

### 发现3: SKU跨线冲突
- **问题**: 14个SKU属于2条产品线
- **影响**: 底层聚合可能重复计算
- **修正**: 使用产品线+SKU复合键

### 发现4: 负毛利预测
- **问题**: 1条预测出现负毛利
- **影响**: 业务不可接受
- **修正**: 标记人工复核，不自动裁剪

### 发现5: 品类层可用性低
- **问题**: 仅53%产品线可用品类月度层级
- **影响**: 品类层实验范围受限
- **修正**: 按准入白名单运行

### 发现6: PMIC严重受限
- **问题**: 仅2个层级可用
- **影响**: PMIC作为特殊线单独处理
- **修正**: 白名单标记，Phase 1单独策略

### 发现7: 基线完全可复现
- **验证**: 全量复跑552方法，所有指标完全一致
- **意义**: 基线可信，可作为Phase 1对比基准

---

## 文件变更清单

### 新增文件
```
experiment_log/phase_0_baseline/exp_0.0.6_hierarchy_eligibility/
  ├── exp_0.0.6_log.md
  └── run_0.0.6.py

experiment_log/phase_0_baseline/exp_0.2.5_full_rerun/
  └── exp_0.2.5_log.md

output/test/
  ├── baseline_metrics_recomputed.csv
  ├── baseline_holdout_by_pline.csv
  ├── baseline_validation_flags.csv
  ├── sku_multi_line_conflicts.csv
  ├── negative_gross_profit_forecasts.csv
  ├── hierarchy_eligibility_by_pline.csv
  └── baseline_full_rerun_20260612/
      ├── 产品线季度历史与预测.csv
      ├── 预测方法排行榜.csv
      ├── 预测方法回测明细.csv
      ├── 候选预测方法清单.csv
      ├── 产品级价格与预测贡献.csv
      ├── 数据质量与映射诊断.csv
      ├── 操作日志.csv
      ├── 产品线季度预测图表.html
      └── 产品线季度历史与预测_含方法回测.xlsx
```

### 修改文件
```
experiment_log/master_log.md (v1.4补丁更新)
experiment_log/phase_0_baseline/exp_0.2_baseline_lock/run_0.2_baseline_lock.py (新增验证输出)
quarterly_forecast_package/run_quarterly_forecast.py (修复PROJECT_ROOT)
quarterly_forecast_package/run_customer_forecast.py (修复PROJECT_ROOT)
测试方案_多维度分层预测校准_v1.3.md (v1.4补丁内嵌)
```

---

## Phase 1准备状态

| 准备项 | 状态 | 文件/说明 |
|---|---|---|
| 基线可复现 | ✅ | exp_0.2.5验证通过 |
| 层级准入白名单 | ✅ | hierarchy_eligibility_by_pline.csv |
| WAPE双口径 | ✅ | baseline_metrics_recomputed.csv |
| 数据问题清单 | ✅ | validation_flags/sku_conflicts/negative_gp |
| Gate 0通过 | ✅ | 8/8 PASS |
| 实验记录完整 | ✅ | master_log.md已更新 |

**结论: Phase 1可开始。建议从实验1.0（层级与时间粒度对比）开始。**

---

## 下一步建议

1. **实验1.0**: 层级与时间粒度对比
   - 输入: hierarchy_eligibility_by_pline.csv
   - 输出: hierarchy_granularity_comparison.csv, hierarchy_granularity_holdout.csv
   - 范围: 只对准入表标记为可用的层级运行

2. **实验1.1**: 间歇性方法（仅C类/稀疏线）

3. **实验1.2-1.4**: 按需执行

---

## 会话元数据
- 总操作数: ~50次工具调用
- 关键决策: 7个
- 新增文件: 15个
- 修改文件: 5个
- 总耗时: 约2小时
