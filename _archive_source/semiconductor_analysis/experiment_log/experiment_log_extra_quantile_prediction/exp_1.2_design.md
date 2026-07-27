# 实验 1.2 设计方案：区间预测（Quantile Forecasting）

**实验日期**: 2026-06-12
**实验编号**: 1.2
**实验名称**: 区间预测（Quantile Forecasting）

---

## 1. 假设 (Hypothesis)

点预测无法充分表达低置信度预测的不确定性。通过提供预测区间（如50%/80%/95%分位数），可以：
1. 量化预测不确定性，为决策提供风险评估
2. 区间覆盖率可以验证预测质量，比单一WAPE更全面
3. 对低置信度产品线，区间预测比强行点预测更有业务价值

## 2. 范围 (Scope)

- **目标产品线**: 全部17条产品线（包括低置信C类线）
- **重点评估**: 低置信C类线（新显示MLED驱动、无刷直流电机驱动、未分类、电源模组）
- **数据源**: `data/财务分析-5月（6.3）.xlsx`, sheet `总表`
- **时间粒度**: 季度（3个月桶），12个历史桶 H01-H12
- **预测指标**: 销售额（RMB 未税金额小计）
- **字段口径**: 严格遵守 `experiment_log/00_master/field_spec_locked_20260612.md`

## 3. 方法池 (Method Pool)

### 3.1 分位数预测方法
| 方法 | 分位数 | 说明 |
|---|---|---|
| 基于统计预测的区间预测 | - | 使用statsforecast的分位数预测功能 |
| Bootstrap残差重采样 | - | 对基线最佳方法进行Bootstrap分位数 |
| Naive分位数扩展 | - | 基于点预测+历史误差分布 |

### 3.2 分位数定义
| 分位数 | 区间 | 业务含义 |
|---|---|---|
| 10% / 90% | 80%置信区间 | 宽区间，覆盖大部分情况 |
| 25% / 75% | 50%置信区间 | 中等区间，平衡精度和覆盖 |
| 5% / 95% | 90%置信区间 | 窄区间，核心预期范围 |

## 4. 回测设计 (Backtest Design)

- **回测方式**: 扩展窗口 (expanding window)
- **折数**: BT01-BT06
- **Horizon**: 1 季度
- **训练/预测映射**: 与实验1.1相同

## 5. 评估指标 (Evaluation Metrics)

### 5.1 区间覆盖指标
| 指标 | 说明 | 理想值 |
|---|---|---|
| 覆盖率(Coverage) | 实际值落在区间内的比例 | 接近名义覆盖率 |
| 覆盖偏差(Coverage Bias) | 覆盖率 - 名义覆盖率 | 0 |

### 5.2 区间宽度指标
| 指标 | 说明 | 理想值 |
|---|---|---|
| 区间平均宽度 | 区间上界-下界的平均值 | 越小越好（在保证覆盖率前提下） |
| 区间宽度标准化 | 区间宽度 / 实际值均值 | 越小越好 |

### 5.3 分位数评分
| 指标 | 说明 | 理想值 |
|---|---|---|
| 分位数损失(Quantile Loss) | Pinball Loss | 越小越好 |
| 连续分级概率评分(CRPS) | 分布预测质量 | 越小越好 |

## 6. 成功标准 (Success Criteria)

| 标准 | 阈值 | 说明 |
|---|---|---|
| 区间覆盖准确性 | 覆盖率偏差 < 5% | 80%置信区间实际覆盖率在75%-85%之间 |
| 低置信线改善 | 区间覆盖准确性优于基线点预测 | C类线区间预测质量优于盲目点预测 |
| 区间宽度合理性 | 平均宽度 < 实际值标准差的2倍 | 区间不过宽，有实用价值 |

## 7. 输出文件 (Outputs)

| 文件 | 路径 | 说明 |
|---|---|---|
| 区间预测明细 | `output/quantile_backtest_detail.csv` | 每线每方法每折的分位数预测值 |
| 区间覆盖评估 | `output/quantile_coverage_metrics.csv` | 每线每方法的覆盖率、宽度、评分 |
| 区间推荐表 | `output/quantile_recommendation.csv` | 每线推荐区间方法及vs基线对比 |
| 操作日志 | `output/operation_log.csv` | 每一步操作记录 |

## 8. 实验步骤

### Step 1: 加载数据和产品线
- 读取原始Excel数据
- 加载17条产品线清单
- 标记低置信C类线

### Step 2: 清洗和派生字段
- 严格遵守字段规范
- 派生`预测客户名称`、`SKU预测键`等

### Step 3: 构建季度序列
- 构建12个历史季度桶
- 计算每条产品线的销售额序列

### Step 4: 基线点预测加载
- 加载修正版0.2基线最佳方法
- 作为分位数预测的基础

### Step 5: 分位数预测回测
- 使用statsforecast的分位数预测功能
- 或使用Bootstrap残差重采样
- 生成10%/25%/75%/90%分位数预测

### Step 6: 计算区间覆盖指标
- 计算每个分位数区间的覆盖率
- 计算区间宽度和标准化宽度
- 计算分位数损失和CRPS

### Step 7: 评估和推荐
- 按产品线评估区间预测质量
- 对比低置信C类线的表现
- 生成推荐方法

### Step 8: 写入输出
- 写入所有CSV输出
- 更新实验日志

## 9. 技术实现要点

### 9.1 statsforecast分位数预测
```python
from statsforecast import StatsForecast
from statsforecast.models import AutoETS, AutoARIMA, HistoricAverage

# 配置分位数
quantiles = [0.1, 0.25, 0.75, 0.9]

# 使用分位数预测
models = [
    AutoETS(season_length=1),
    AutoARIMA(season_length=1),
    HistoricAverage()
]

sf = StatsForecast(
    df=train_df,
    models=models,
    freq='Q',
    n_jobs=1
)

# 预测分位数
preds = sf.forecast(h=1, level=[80, 50, 90])  # 80%置信区间等
```

### 9.2 Bootstrap残差重采样
```python
def bootstrap_residuals(y_train, n_bootstrap=1000, horizon=1):
    """基于残差重采样的分位数预测"""
    # 1. 拟合基线模型
    point_pred = baseline_method(y_train, horizon)
    residuals = y_train - point_pred

    # 2. 重采样残差
    bootstrap_preds = []
    for i in range(n_bootstrap):
        sampled_residuals = np.random.choice(residuals, size=horizon, replace=True)
        bootstrap_pred = point_pred + sampled_residuals
        bootstrap_preds.append(bootstrap_pred)

    # 3. 计算分位数
    bootstrap_preds = np.array(bootstrap_preds)
    q10 = np.percentile(bootstrap_preds, 10, axis=0)
    q25 = np.percentile(bootstrap_preds, 25, axis=0)
    q75 = np.percentile(bootstrap_preds, 75, axis=0)
    q90 = np.percentile(bootstrap_preds, 90, axis=0)

    return q10, q25, q75, q90
```

### 9.3 覆盖率计算
```python
def compute_coverage(actuals, lower_bounds, upper_bounds):
    """计算区间覆盖率"""
    in_interval = (actuals >= lower_bounds) & (actuals <= upper_bounds)
    coverage = np.mean(in_interval)
    return coverage
```

## 10. 预期结果

1. **区间覆盖准确性**: 80%置信区间实际覆盖率应在75%-85%之间
2. **低置信线改善**: C类线区间预测应提供有意义的区间，而非盲目点预测
3. **区间宽度合理性**: 区间宽度应在合理范围内，不过宽
4. **业务价值**: 为决策提供风险评估，帮助理解预测不确定性

## 11. 注意事项

- 此实验评估全部17条产品线，但重点关注低置信C类线
- 分位数预测假设误差分布相对稳定，对于极稀疏数据可能不适用
- 区间宽度与覆盖率的权衡：更宽的区间保证覆盖，但实用性降低
- 修正版0.2基线作为基础，使用其最佳方法进行分位数扩展

---

**状态**: 设计完成，待实现
**预计时间**: 2-3小时