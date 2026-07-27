# 半导体销售多维度分层预测——资料索引

> 生成日期: 2026-06-11
> 目的: 为构建Agent驱动的多维度分层预测系统，汇总搜索到的外部技能/库/论文/工具

---

## 一、间歇性/稀疏需求预测方法

### 核心库

| 库名 | 安装 | 版本 | 功能 |
|---|---|---|---|
| **statsforecast** (Nixtla) | `pip install statsforecast` | 1.9+ | CrostonOptimized, ADIDA, TSB, IMAPA, 多序列并行, cross-validation |
| **intermittent-forecast** | `pip install intermittent-forecast` | 1.0.0 (2025-05) | Croston(SBA/SBJ/TSB)+ADIDA+IMAPA, 自动参数优化 |

### 方法清单

| 方法 | 原理 | 适用场景 |
|---|---|---|
| Croston (原始) | 分离需求量与需求间隔，分别做指数平滑 | 间歇性最经典基线 |
| Croston SBA (Syntetos-Boylan) | 对Croston的偏倚修正 | 需求量较小且有偏的场景 |
| Croston SBJ | SBA的进一步修正 | 极高稀疏度 |
| TSB (Teunter-Syntetos-Babai) | 用需求概率替代需求间隔，每期更新 | 频繁0值且需及时响应新需求 |
| ADIDA | 先时间聚合消除0值→SES预测→等比例分解 | 聚合粒度选择是关键超参 |
| IMAPA | 多种聚合粒度分别ADIDA→取均值/中位数 | 不确定最佳聚合窗口时使用 |

### 参考教程

- **Forecasting Intermittent Time Series in Python** (datasciencewithmarco.com)
  - Croston vs ADIDA vs TSB vs SES 对比代码
  - 包含MAE对比benchmark

---

## 二、分层时间序列调和

### 核心库

| 库名 | 安装 | 版本 | 功能 |
|---|---|---|---|
| **hierarchicalforecast** (Nixtla) | `pip install hierarchicalforecast` | 1.5.1 (2026-03) | ⭐最完整: BottomUp/TopDown/MiddleOut/MinTrace(wls/ols)/ERM + BOOTSTRAP/NORMALITY/PERMBU概率调和 |
| **scikit-hts** | `pip install scikit-hts` | 0.5.12 (2021停更) | 较早实现, 支持Prophet/SARIMAX基模型, Dask分布式 |
| **Salesforce Merlion** | `pip install merlion` | - | 企业级, Spark UDF实现MinTrace调和 |

### 调和策略矩阵

| 策略 | 数学 | 适用 |
|---|---|---|
| BottomUp | sum(底层预测) | 底层预测准, 上层可能不准 |
| TopDown (avg_proportions) | 顶层×历史比例 | 上层准, 底层结构可能失真 |
| TopDown (forecast_proportions) | 顶层×预测比例 | 比例动态调整 |
| MiddleOut | 中间层锚定, 上下分别 | 中间层最可靠时 |
| MinTrace (OLS) | 全局最小化调和后方差 | 理论最优, 需要协方差矩阵 |
| MinTrace (WLS) | 忽略协方差的对角版本 | 更稳定的近似 |
| ERM | 基于经验风险的调和 | 小样本下稳健 |

### 关键论文

- **Optimal Reconciliation** (Hyndman et al. 2011 → Wickramasuriya et al. 2019)
  - MinTrace的数学基础，解决了"底层预测和≠上层预测"的形式化问题
- **M5 Accuracy Competition** (Makridakis et al., 2021)
  - 零售场景分层预测最佳实践
  - 结论: 大多数队伍用BottomUp或混合策略, 调和后精度提升显著
- **HierarchicalForecast: A Reference Framework** (Olivares et al., 2024)
  - hierarchicalforecast库的学术论文

---

## 三、预测可诊断性评估

### 核心库

| 库名 | 安装 | 版本 | 功能 |
|---|---|---|---|
| **tsfresh** | `pip install tsfresh` | 0.21+ | 从时序提取1200+特征: 熵, 自相关, 非线性, 峰度, 断点检测等 |
| **dependence-forecastability** | `git clone` | 2026-03 | ⭐专门的前诊断工具: Readiness报告, 信息horizon, 季节性暗示, ForecastPrepContract |

### 诊断维度设计

| 诊断维度 | 指标/方法 | 来源 |
|---|---|---|
| 充足度 | 有效桶数, 非零桶占比, 最新桶距今距离 | 业务规则 |
| 稳定度 | 销量CV, 趋势斜率一致性, 结构性断点 | tsfresh + 统计 |
| 可结构化度 | 季节模式检测, 趋势方向, 头部客户占比 | tsfresh + 业务 |
| 信息horizon | 多长窗口内有预测信号 | dependence-forecastability |
| 可预测性综合 | 回测MASE/Naive基准比 | Hyndman MASE方法 |

### 参考讨论

- **stats.stackexchange: Assessing forecastability** (2012)
  - MASE缩放误差、CV、Approximate Entropy、STL残差比等方法的综述

---

## 四、Agent自动化编排

### 参考架构

| 项目 | Stars | 技术栈 | 特点 |
|---|---|---|---|
| **manufacturing-agents** (YUHAO-corn) | 156 | LangChain+LangGraph+Streamlit | 制造业6Agent: 需求预测/成本/供应链/市场/决策/风险 |
| **supply-chain-agents** (aksh-ay06) | - | LangChain+LangGraph+Ollama | CPG供应链, Supervisor模式路由到3个Agent |
| **genai-demand-planner** (virbahu) | - | Python+Streamlit | LLM增强特征提取+需求计划 |

### 用于OpenCode的agent化思路

```
入口: 新数据文件路径
  ├── Agent 1: 数据探查 → 字段映射, 缺失统计, 异常检测
  ├── Agent 2: 可诊断性评分 → A/B/C分级
  ├── Agent 3: 方法匹配与回测 → 根据等级选方法池, 独立回测
  ├── Agent 4: 调和与组合寻优 → hierarchicalforecast + 阈值搜索
  ├── Agent 5: 检验与否定 → WAPE阈值/Bias/0预测检查
  └── Agent 6: 输出 → CSV/Excel/HTML图表
```

---

## 五、现有系统对照

### 已有能力
- 552种候选方法的回测框架 ✅
- 16产品线 × 12+4季度桶 ✅
- 41 KA/AA客户维度预测 ✅
- 产品级单价与成本模型 ✅
- HTML可视化 ✅
- 锁定方法快速刷新 ✅

### 待补充
- 间歇性预测深度（3→15+变体）⬜
- 分层调和层 ⬜
- 预测前诊断打分 ⬜
- C类产品线专项策略 ⬜
- 客户KM/MM维度 ⬜
- 新品/老品分层 ⬜
- Agent化编排 ⬜

---

## 六、待探索方向

- 产品生命周期数据 (已有项目, 待整合)
- 客户分析数据 (尚未完成)
- 细分市场替代方案
- 产品品类维度
