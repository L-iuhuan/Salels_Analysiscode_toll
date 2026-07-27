# 实验 1.3 设计方案：产品生命周期因子初次校准——解释层与PIT代理层拆分

**实验编号**: 1.3
**设计日期**: 2026-06-15
**方案来源**: `测试方案_多维度分层预测校准_v1.3.md` 行486-539（含v1.4补丁）
**状态**: 设计完成，待执行

---

## 1. 背景与动机

### 1.1 v1.3修订背景

`gold_product_portrait.csv` 是基于当前全量历史（截至2026-05）生成的快照。若直接将其字段（当前画像/综合风险等级/管理层摘要）作为历史回测特征，会把未来信息泄漏进训练过程，导致虚假WAPE改善。

v1.3要求将生命周期信息拆分为两层：
- **A. 当前解释层**：允许立即使用当前快照，但仅用于解释、备注、人工复核，不得进入历史回测选模。
- **B. PIT代理建模层**：必须从原始明细按每个回测截点重新计算point-in-time代理特征，才可进入回测建模。

### 1.2 实验定位

本实验是生命周期因子进入预测框架的**首次校准实验**。核心目标是回答两个独立问题：

| 层 | 核心问题 | 成功度量 |
|---|---|---|
| 1.3A 解释层 | 当前画像/风险能否解释WAPE/Bias/低置信度？ | 解释相关性，不追求WAPE改善 |
| 1.3B 建模层 | PIT代理特征能否在holdout中改善预测？ | holdout WAPE改善≥1pp才可进入Phase 2 |

---

## 2. 假设 (Hypothesis)

### 2.1 1.3A 解释层假设

- **H1**: 当前画像（如"衰退期"/"夕阳产品"）占比高的产品线，WAPE/低置信度标签更差 → 生命周期阶段与可预测性相关。
- **H2**: 当前综合风险等级与holdout WAPE恶化正相关 → 风险评分可作为holdout恶化早期预警。
- **H3**: 管理层摘要（投资区/观察区/退出区/警告区）的分布与人工复核优先级一致 → 可作为自动化备注触发器。

### 2.2 1.3B PIT建模层假设

- **H4**: PIT代理增长率(growth_proxy)与下一季度实际增长率正相关 → 可用于幅度修正。
- **H5**: PIT毛利率变化与下一季度营收-毛利质量相关 → 可辅助偏差校准。
- **H6**: PIT客户集中度上升预示单点风险 → 可辅助置信度下调。

---

## 3. 范围 (Scope)

### 3.1 数据源

| 数据 | 路径 | 用途 |
|---|---|---|
| 当前产品画像 | `output/gold/gold_product_portrait.csv` | 1.3A解释层 |
| 原始发货明细 | `data/财务分析-5月（6.3）.xlsx`, sheet `总表` | 1.3B PIT代理特征回算 |
| 修正版基线 | `experiment_log/05_exp_0.2_baseline_lock/output/baseline_corrected_customer_20260612/baseline_corrected_selected_methods.csv` | 1.3B修正基准 |
| 低置信度清单 | `experiment_log/09_exp_1.0_hierarchy_granularity/output/hierarchy_low_confidence_flags.csv` | 1.3A交叉验证 |
| 基线指标 | `experiment_log/05_exp_0.2_baseline_lock/output/baseline_metrics_recomputed.csv` | 1.3A/B对比基线 |

### 3.2 目标产品线

全部17条产品线。按`测试方案_v1.3`预分类：

| 分层 | 产品线数 | 当前WAPE范围 |
|---|---|---|
| A | 4 | 10.0%-18.8% |
| B | 2 | 14.6%-33.1% |
| C | 11 | 33.1%-97.7% |

### 3.3 时间粒度与被预测变量

- **时间粒度**: 季度（3个月桶），12个历史桶 H01-H12
- **预测指标**: 销售额（RMB 未税金额小计）
- **字段口径**: 严格遵守 `experiment_log/00_master/field_spec_locked_20260612.md`

### 3.4 回测折次

| 折次 | 训练期 | 预测桶 | PIT数据截止 |
|---|---|---|---|
| BT01 | H01-H06 | H07 | H01-H06 |
| BT02 | H01-H07 | H08 | H01-H07 |
| BT03 | H01-H08 | H09 | H01-H08 |
| BT04 | H01-H09 | H10 | H01-H09 |
| BT05 | H01-H10 | H11 | H01-H10 |
| BT06 | H01-H11 | H12 | H01-H11 |

---

## 4. 产品画像字段映射与两用规则

### 4.1 字段牌照表

来自 `gold_product_portrait.csv` 的全部关键字段及两层可用性：

| 字段 | 中文名 | 1.3A解释层 | 1.3B PIT建模 | PIT重算规则 |
|---|---|---|---|---|
| `产品名称` | 产品标识 | ✅ | ✅ | 映射键 |
| `所属参照组` | 参照组→映射产品线 | ✅ | ✅ | 映射键 |
| `当前画像` | 11种生命周期阶段 | ✅ | ⚠️ | 只能生成`proxy_lifecycle_stage` |
| `综合风险等级` | 低/中/高/极高风险 | ✅ | ⚠️ | 只能生成`proxy_risk_level` |
| `综合评分` | 0-100风险评分 | ✅ | ⚠️ | 只能生成`proxy_risk_score` |
| `管理层摘要` | 投资区/观察区/退出区/警告区 | ✅ | ❌ | 管理判断，不可回溯 |
| `通用策略建议` | 策略文本 | ✅ | ❌ | 管理判断 |
| `特情说明` | 特情文本 | ✅ | ❌ | 管理判断 |
| `近12月销量` | trailing 12m qty | ✅ | ✅ | 截点前12月聚合 |
| `前12月销量` | previous 12m qty | ✅ | ✅ | 截点前13-24月聚合 |
| `近12月销售额` | trailing 12m sales | ✅ | ✅ | 截点前12月聚合 |
| `前12月销售额` | previous 12m sales | ✅ | ✅ | 截点前13-24月聚合 |
| `近12月增长率%` | sales growth 12m | ✅ | ✅ | 近12月/前12月 - 1 |
| `增速方向` | 加速/减速/平稳 | ✅ | ⚠️ | 可PIT重算proxy |
| `近12月毛利率%` | trailing 12m margin | ✅ | ✅ | 截点前利润/销售额 |
| `前12月毛利率%` | previous 12m margin | ✅ | ✅ | 截点前13-24月 |
| `毛利率同比变化(pp)` | margin YoY change | ✅ | ✅ | PIT直接可算 |
| `毛利率趋势斜率%/月` | margin slope | ✅ | ✅ | 截点前12月回归 |
| `营收-毛利综合判断` | 双增/增收不增利/减收增利/双降 | ✅ | ⚠️ | 用PIT销售增长和毛利变化规则重算 |
| `客户集中度-前1大%` | Top1 customer share | ✅ | ✅ | 截点前12月聚合 |
| `客户集中度-前3大%` | Top3 customer share | ✅ | ✅ | 截点前12月聚合 |
| `是否已达6K` | 累计6K件阈值 | ✅ | ✅ | 截点前累计销量判断 |
| `帕累托分类` | 常规/重点/潜力产品 | ✅ | ✅ | 截点前销售额占比 |
| `数据质量标记` | SL/NM/ZS/NH等 | ✅ | ❌ | 当前数据质量，不可回溯 |

### 4.2 产品→产品线映射规则

`所属参照组` → 产品线的映射：
1. 优先匹配 `型号_产品线（新）` 中已有产品线名称
2. 若参照组名不直接等于产品线名，使用预注册映射表（从实验0.3中提取）
3. 无映射产品归入对应产品线的"未映射子类"桶

---

## 5. 实验1.3A：当前解释层校准（不宣称预测改善）

### 5.1 方法设计

#### Step A1: 加载与聚合
```python
# 读取当前快照
portrait = pd.read_csv('output/gold/gold_product_portrait.csv')

# 产品→产品线映射
portrait['产品线'] = portrait['所属参照组'].map(reference_to_pline)

# 按产品线聚合解释特征
pline_explain = portrait.groupby('产品线').agg({
    '产品名称': 'count',                        # SKU数
    '当前画像': lambda x: x.value_counts().to_dict(),  # 画像分布
    '综合风险等级': lambda x: x.value_counts().to_dict(),  # 风险分布
    '管理层摘要': lambda x: x.value_counts().to_dict(),  # 摘要分布
    '近12月销售额': 'sum',                       # 最近12月产品线总销售额
    '近12月增长率%': 'mean',                     # 平均增长率
    '近12月毛利率%': 'mean',                     # 平均毛利率
    '客户集中度-前1大%': 'mean',                 # 平均客户集中度
    '综合评分': 'mean',                          # 平均风险评分
    '增速衰减(pp)': 'mean',                      # 平均增速衰减
})
```

#### Step A2: 与基线指标交叉分析

```python
# 加载基线指标
baseline = pd.read_csv('baseline_metrics_recomputed.csv')
lowconf = pd.read_csv('hierarchy_low_confidence_flags.csv')

# 合并分析
analysis = pline_explain.merge(baseline, on='产品线').merge(lowconf, on='产品线', how='left')
```

分析维度：
1. **当前画像分布 vs WAPE**: 衰退期/夕阳产品占比 vs CV WAPE、BT04-06 holdout WAPE
2. **综合风险评分 vs Bias**: 平均风险评分 vs 金额加权Bias
3. **管理层摘要 vs 低置信度**: 退出区/警告区占比 vs 低置信度标签
4. **客户集中度 vs holdout恶化**: Top1集中度 vs BT04-06恶化幅度
5. **毛利率趋势 vs 毛利预测偏差**: 毛利率趋势斜率 vs 毛利额预测偏差

### 5.2 输出规格

**主输出**: `output/lifecycle_current_explanation_calibration.csv`

| 字段 | 类型 | 说明 |
|---|---|---|
| 产品线 | str | 产品线名称 |
| 分层 | str | A/B/C |
| SKU数 | int | 该产品线下的SKU数量 |
| 衰退夕阳占比 | float | 衰退期+夕阳产品占该线SKU百分比 |
| 预警新品占比 | float | 预警增长+新品观察+隐性衰退占该线SKU百分比 |
| 高风险极高占比 | float | 高风险+极高风险SKU百分比 |
| 退出警告区占比 | float | 退出区+警告区SKU百分比 |
| 平均风险评分 | float | 综合评分均值 |
| 平均客户集中度Top1 | float | 前1大客户份额均值 |
| 平均增速衰减 | float | 增速衰减(pp)均值 |
| 平均毛利率趋势斜率 | float | 毛利率趋势斜率均值 |
| CV_WAPE | float | 交叉验证WAPE |
| BT04_06_WAPE | float | holdout近似WAPE |
| 金额加权Bias | float | 金额加权偏差 |
| 低置信度标签 | str | 低置信度/不可预测/正常 |
| 解释力评估 | str | 强解释/中等解释/弱解释/无相关性 |

**解释力评估规则**:
- 衰退夕阳占比>30% 且 WAPE>35% → "强解释：衰退结构推高WAPE"
- 高风险占比>30% 且 holdout恶化>5pp → "强解释：风险集中导致holdout恶化"
- 退出警告区占比>50% 且 Bias极端 → "中等解释：管理区间预示偏差方向"
- 无显著相关 → "弱解释：画像字段与预测性能无显著关联"

### 5.3 成功标准

| 标准 | 判定 |
|---|---|
| 解释覆盖 | ≥14/17产品线有画像数据覆盖 |
| 解释相关性 | ≥3条产品线的解释力评估为"强解释"或"中等解释" |
| 人工复核触发 | ≥2条产品线触发可操作的人工复核建议 |
| 不宣称预测改善 | 本输出不得包含"改善WAPE"等建模宣称 |

---

## 6. 实验1.3B：PIT代理特征建模校准（可验证预测价值）

### 6.1 PIT代理特征定义

每个回测折次的cutoff处，对每个SKU计算以下13个PIT代理特征：

| 特征ID | 特征名 | 说明 | 计算规则 |
|---|---|---|---|
| F01 | `pit_trail12_sales` | 近12月销售额 | cutoff前12月 SUM(RMB未税金额小计) |
| F02 | `pit_trail12_qty` | 近12月销量 | cutoff前12月 SUM(发货数量) |
| F03 | `pit_trail12_gp` | 近12月毛利额 | cutoff前12月 SUM(利润) |
| F04 | `pit_trail12_margin` | 近12月毛利率 | F03 / F01（分母0则NaN） |
| F05 | `pit_prev12_sales` | 前12月销售额 | cutoff前13-24月 SUM |
| F06 | `pit_prev12_margin` | 前12月毛利率 | 前12月利润/销售额 |
| F07 | `pit_sales_growth` | 近12月销售增长率 | (F01 - F05) / abs(F05)，分母0则clip |
| F08 | `pit_margin_change` | 毛利率同比变化 | F04 - F06 |
| F09 | `pit_margin_slope` | 毛利率趋势斜率 | 近12月月度毛利率OLS回归斜率，样本<6则NaN |
| F10 | `pit_top1_share` | 客户集中度Top1 | 近12月最大客户销售额/总销售额 |
| F11 | `pit_top3_share` | 客户集中度Top3 | 近12月前3大客户销售额/总销售额 |
| F12 | `pit_reached_6k` | 是否已达6K | cutoff前累计销量 ≥ 6000 → 1，否则0 |
| F13 | `pit_rev_profit_diag` | 营收毛利综合判断 | 基于F07和F08规则映射：双增/增收不增利/减收增利/双降 |

**PIT聚合到产品线**:
- 连续值（销售额/销量/毛利/增长率等）：先按产品线求和，再计算比率
- 占比值（毛利率/集中度）：按产品线加权平均（权重=近12月销售额）
- 标志值（是否达6K/诊断）：按SKU数占比

### 6.2 幅度修正模型

```python
def lifecycle_amplitude_correction(
    base_forecast: float,
    growth_proxy: float,       # PIT增长率，[-1, +∞)
    margin_proxy: float,       # PIT毛利率变化，[-1, +1]
    concentration_proxy: float, # PIT Top1集中度变化，[-1, +1]
    risk_proxy: float,         # PIT代理风险上调因子
    params: dict,              # {alpha, beta, gamma, delta}
) -> float:
    """
    生命周期幅度修正：只调幅度，不改变预测方向。
    
    Args:
        base_forecast: 基线方法预测值（锁定，不重新选模）
        growth_proxy: 近12月销售额增长率
        margin_proxy: 毛利率同比变化(pp) / 100
        concentration_proxy: (Top1集中度 - 上期Top1集中度)
        risk_proxy: 代理风险上调方向因子
        params: 待搜索的α/β/γ/δ参数
    
    Returns:
        修正后预测值
    """
    alpha, beta, gamma, delta = (
        params['alpha'], params['beta'], 
        params['gamma'], params['delta']
    )
    
    adjustment = (
        1 + 
        alpha * growth_proxy + 
        beta * margin_proxy + 
        gamma * concentration_proxy + 
        delta * risk_proxy
    )
    
    # 钳制在 [0.5, 1.5]，防止极端修正
    adjustment = np.clip(adjustment, 0.5, 1.5)
    
    return base_forecast * adjustment
```

### 6.3 参数搜索

参数空间：
```
alpha:   [-0.5, -0.3, -0.1, 0.0, 0.1, 0.3, 0.5]
beta:    [-0.3, -0.1, 0.0, 0.1, 0.3]
gamma:   [-0.3, -0.1, 0.0, 0.1, 0.3]
delta:   [-0.2, -0.1, 0.0, 0.1, 0.2]
```

搜索策略：
1. **全局搜索**: 在BT01-BT03训练折上网格搜索，选训练WAPE最低参数组合。
2. **按产品线搜索**: 在全局搜索后，对每条产品线微调参数。
3. **组合搜索**: 固定α/β后搜索γ/δ（两阶段，降低组合爆炸）。

**关键约束**: 参数搜索只使用BT01-BT03训练折。BT04-BT06作为holdout不参与参数选择。

### 6.4 实验设计

| 组 | 产品线范围 | 预测基础 | 修正 | 参数搜索 | 评估 |
|---|---|---|---|---|---|
| 对照组 | 17条 | 基线锁定方法 | 无修正 | — | 基线WAPE |
| 实验组-全局 | 17条 | 同上 | 全局最佳αβγδ | BT01-BT03网格搜索 | 全局WAPE |
| 实验组-按线 | 17条 | 同上 | 每线最佳αβγδ | BT01-BT03按线微调 | 产品线WAPE |

### 6.5 输出规格

**主输出**: `output/lifecycle_pit_proxy_features.csv`

| 字段 | 类型 | 说明 |
|---|---|---|
| 产品线 | str | 产品线名称 |
| 折次 | str | BT01-BT06 |
| pit_trail12_sales | float | PIT近12月销售额 |
| pit_trail12_margin | float | PIT近12月毛利率 |
| pit_sales_growth | float | PIT销售额增长率 |
| pit_margin_change | float | PIT毛利率变化 |
| pit_margin_slope | float | PIT毛利率趋势斜率 |
| pit_top1_share | float | PIT客户集中度Top1 |
| pit_top3_share | float | PIT客户集中度Top3 |
| pit_reached_6k_ratio | float | 已达6K产品占比 |
| pit_diag_double_growth | float | 双增产品占比 |
| pit_diag_double_decline | float | 双降产品占比 |
| base_forecast | float | 基线预测值 |
| corrected_forecast | float | 修正后预测值 |
| actual | float | 实际销售额 |
| base_wape | float | 基线在该折的单个WAPE贡献 |
| corrected_wape | float | 修正后在该折的单个WAPE贡献 |

**辅助输出**: `output/lifecycle_calibration_recommendation.csv`

| 字段 | 说明 |
|---|---|
| 产品线 | 产品线名称 |
| 分层 | A/B/C |
| 全局alpha/beta/gamma/delta | 全局最优参数 |
| 按线alpha/beta/gamma/delta | 产品线级最优参数 |
| CV改善(pp) | 基线WAPE - 修正WAPE（BT01-BT03） |
| holdout改善(pp) | 基线BT04-06 WAPE - 修正BT04-06 WAPE |
| 是否过拟合 | CV改善>1pp 且 holdout改善≤0 |
| PIT覆盖状态 | PIT特征是否有足够样本 |
| 推荐动作 | 进入Phase2 / 降级解释层 / 排除 |

### 6.6 成功标准

| 标准 | 阈值 | 判定 |
|---|---|---|
| PIT特征生成 | 所有特征至少12/17产品线可生成 | 基础可用 |
| PIT覆盖 | 缺失率<30%（每产品线每折至少1个有效样本） | 覆盖率达标 |
| 全局改善 | 公司总盘金额加权WAPE下降 ≥1pp | PIT代理因子有预测价值 |
| 产品线平均 | 产品线简单平均WAPE不恶化>1pp | 非头部独占改善 |
| holdout验证 | BT04-BT06近似holdout同向改善 | 非过拟合 |
| A类保护 | A类产品线不恶化>2pp | 非牺牲稳定线换改善 |
| **综合判定** | 全满足 → PIT因子进入Phase 2深化 | |
| **降级处理** | CV改善但holdout不改善 → 降级为解释/置信度标记 | |
| **排除处理** | 指标上升或参数搜索失败 → 排除出建模路径 | |

---

## 7. 输出文件总览

| 文件 | 路径 | 层 | 行数预计 |
|---|---|---|---|
| 当前解释校准表 | `output/lifecycle_current_explanation_calibration.csv` | 1.3A | ~17行 |
| PIT代理特征表 | `output/lifecycle_pit_proxy_features.csv` | 1.3B | ~102行（17×6折） |
| 校准推荐表 | `output/lifecycle_calibration_recommendation.csv` | 1.3B | ~17行 |
| 操作日志 | `output/operation_log.csv` | 共享 | 动态 |
| 参数搜索结果 | `output/lifecycle_param_search_detail.csv` | 1.3B | ~300行（网格） |

---

## 8. 防泄漏与质量保证

### 8.1 未来信息泄漏防护清单

| 泄漏源 | 防护措施 |
|---|---|
| 当前画像字段用于历史回测 | 1.3B严禁使用`当前画像`/`综合风险等级`/`管理层摘要` |
| PIT特征使用未来数据 | PIT特征严格按cutoff时间截断，代码中加assert检查 |
| 参数搜索使用holdout | 参数搜索只在BT01-BT03训练折上进行 |
| 当前毛利率用于历史修正 | 必须用PIT重算的`pit_trail12_margin`，不得用当前快照的`近12月毛利率%` |
| 客户集中度用全历史 | 必须用cutoff前12月的数据聚合客户份额 |

### 8.2 数据质量检查

| 检查项 | 检查方式 |
|---|---|
| PIT特征生成后的日期验证 | assert max(发货日期) <= cutoff_date |
| 产品线映射完整性 | 报告未映射产品数量和占比 |
| 毛利率分母为0保护 | F04 = F03 / max(abs(F01), 1) |
| 增长率分母为0保护 | F07 = (F01-F05) / max(abs(F05), 1) |
| 客户键一致性 | 使用`预测客户名称`字段，遵守field_spec |

### 8.3 字段口径

严格遵守 `experiment_log/00_master/field_spec_locked_20260612.md`：
- 销售额: `RMB 未税金额小计`
- 销量: `发货数量`
- 产品线: `型号_产品线（新）`
- 客户: `预测客户名称`
- 日期: `发货日期`
- 成本/利润: `成本` / `利润`

---

## 9. 技术实现要点

### 9.1 PIT特征回算伪代码

```python
def compute_pit_features(raw_df, cutoff_date, product_line_map):
    """
    对指定cutoff日期，从原始明细计算所有PIT代理特征
    
    Args:
        raw_df: 原始发货明细DataFrame
        cutoff_date: 截点日期
        product_line_map: SKU→产品线映射dict
    
    Returns:
        DataFrame with PIT features per product per pline
    """
    # 1. 截断数据
    train = raw_df[raw_df['发货日期'] <= cutoff_date].copy()
    assert train['发货日期'].max() <= cutoff_date, "FUTURE LEAKAGE DETECTED!"
    
    # 2. 分近12月和前12月
    cutoff_month = cutoff_date.to_period('M')
    trail_start = cutoff_month - 11  # 近12月
    trail_end = cutoff_month
    prev_start = cutoff_month - 23    # 前12月
    prev_end = cutoff_month - 12
    
    # 3. 按SKU聚合
    ...
```

### 9.2 参数搜索效率优化

- 全局网格搜索: max 7×5×5×5 = 875组合，每组合需全量17线BT01-BT03回测
- 预计耗时: 875组合 × 17线 × 3折 ≈ 45K WAPE计算
- 优化措施: 先全局后分线（先粗筛top-10%参数，再按线微调）

### 9.3 运行顺序依赖

```
Step 0: 加载基线数据和锁定的最佳方法
Step 1: 1.3A解释层分析（不依赖重算，直接跑）
Step 2: PIT特征生成（为每个cutoff重算，最耗时）
Step 3: PIT特征覆盖检查（<14线覆盖则降级）
Step 4: 参数搜索（仅BT01-BT03）
Step 5: 全折回测（BT01-BT06，实验组和对照组）
Step 6: holdout验证和成功标准判定
Step 7: 写输出
```

### 9.4 依赖库

- pandas, numpy (核心)
- scipy (斜率回归)
- 无需 statsforecast/hierarchicalforecast/tsfresh（本实验不引入新预测模型）

---

## 10. 预计时间

| 步骤 | 预计耗时 | 说明 |
|---|---|---|
| 1.3A解释层分析 | 0.5h | 纯聚合+相关性分析 |
| PIT特征回算 | 1-1.5h | 6个cutoff × 17产品线 × ~900产品 |
| 参数搜索 | 1-2h | 取决于是否做按线微调 |
| 全量回测 | 0.5-1h | 两组×6折 |
| 分析+写输出 | 0.5h | |
| **总计** | **3.5-5.5h** | |

---

## 11. 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| PIT特征生成失败或覆盖<50% | 1.3B降级 | 降级为仅解释层，不做建模宣称 |
| 参数搜索发现最优αβγδ接近0 | H4-H6假设被推翻 | 记录为"PIT代理因子无信息增量"，排除出建模 |
| CV改善但holdout恶化 | 过拟合 | 降级为解释层，标记过拟合风险 |
| 某产品线PIT特征全部缺失 | 该线无修正 | 该线维持基线方法，不做修正 |
| 产品→产品线映射不完整 | 部分线聚合偏差 | 参考实验0.3的映射表，输出未映射清单 |

---

**状态**: 设计完成，待执行
**下一实验**: 实验1.4（新品/老品分层预测初探）
