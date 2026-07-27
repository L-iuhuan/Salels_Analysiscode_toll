# 02 功能聚类报告

- 脚本总数: 562(唯一内容 356)
- 聚类单元(variant_key)总数: **393**
- 其中跨项目多版本组: 136(完全相同副本组 89,内容分叉组 47)
- 唯一脚本: 257
- 标签分布: normal=538, temp(临时脚本)=18, junk(与数据分析无关)=6

> 说明: 「项目根前缀」指 semiconductor_analysis/、semiconductor_analysis_before/、
> 工作文件/semiconductor_analysis/ —— 三者被识别为同一项目的不同年代副本。

## A. 内容分叉的多版本组(需人工关注)

### `analysis/pricing/pricing_bands.py` — 价格分析函数 — ASP趋势、弹性计算、价格偏离度、价格带分布

**推荐保留: `工作文件/semiconductor_analysis/analysis/pricing/pricing_bands.py`** — 内容有差异,推荐非备份目录中最后修改(2026-06-16)的版本

| 文件 | 行数 | 最后修改 | main | 标签 | 与推荐版差异 |
|---|---|---|---|---|---|
| 工作文件/semiconductor_analysis/analysis/pricing/pricing_bands.py | 139 | 2026-06-16 | × | normal | (推荐) |
| semiconductor_analysis/analysis/pricing/pricing_bands.py | 135 | 2026-05-24 | × | normal | 行数少4行 |

### `analysis/pricing/pricing_customer.py` — 价格分析函数 — ASP趋势、弹性计算、价格偏离度、价格带分布

**推荐保留: `工作文件/semiconductor_analysis/analysis/pricing/pricing_customer.py`** — 内容有差异,推荐非备份目录中最后修改(2026-06-12)的版本

| 文件 | 行数 | 最后修改 | main | 标签 | 与推荐版差异 |
|---|---|---|---|---|---|
| 工作文件/semiconductor_analysis/analysis/pricing/pricing_customer.py | 226 | 2026-06-12 | × | normal | (推荐) |
| semiconductor_analysis/analysis/pricing/pricing_customer.py | 226 | 2026-05-24 | × | normal | 结构相近 |

### `analysis/pricing/pricing_lifecycle.py` — 价格分析函数 — ASP趋势、弹性计算、价格偏离度、价格带分布

**推荐保留: `工作文件/semiconductor_analysis/analysis/pricing/pricing_lifecycle.py`** — 内容有差异,推荐非备份目录中最后修改(2026-06-13)的版本

| 文件 | 行数 | 最后修改 | main | 标签 | 与推荐版差异 |
|---|---|---|---|---|---|
| 工作文件/semiconductor_analysis/analysis/pricing/pricing_lifecycle.py | 291 | 2026-06-13 | × | normal | (推荐) |
| semiconductor_analysis/analysis/pricing/pricing_lifecycle.py | 291 | 2026-05-24 | × | normal | 结构相近 |

### `analysis/scoring.py` — 客户评价体系评分模块（v2.0） — 与客户分析解耦版本

**推荐保留: `工作文件/semiconductor_analysis/analysis/scoring.py`** — 内容有差异,推荐非备份目录中最后修改(2026-06-14)的版本

| 文件 | 行数 | 最后修改 | main | 标签 | 与推荐版差异 |
|---|---|---|---|---|---|
| 工作文件/semiconductor_analysis/analysis/scoring.py | 391 | 2026-06-14 | × | normal | (推荐) |
| semiconductor_analysis/analysis/scoring.py | 317 | 2026-05-24 | × | normal | 行数少74行 |

### `b2b_v2/actions/rules_engine.py` — 分层策略引擎 v4.3 — 数据验证修正版

**推荐保留: `工作文件/semiconductor_analysis/b2b_v2/actions/rules_engine.py`** — 内容有差异,推荐非备份目录中最后修改(2026-06-22)的版本

| 文件 | 行数 | 最后修改 | main | 标签 | 与推荐版差异 |
|---|---|---|---|---|---|
| 工作文件/semiconductor_analysis/b2b_v2/actions/rules_engine.py | 971 | 2026-06-22 | × | normal | (推荐) |
| semiconductor_analysis/b2b_v2/actions/rules_engine.py | 204 | 2026-05-23 | × | normal | 行数少767行; 摘要差异: 行动建议引擎 — L1 紧急告警 + L2 策略建议 |

### `b2b_v2/actions/run.py` — 行动建议汇总入口 — 串联 L1 告警 + 6策略引擎 + L3 交叉销售

**推荐保留: `工作文件/semiconductor_analysis/b2b_v2/actions/run.py`** — 内容有差异,推荐非备份目录中最后修改(2026-06-13)的版本

| 文件 | 行数 | 最后修改 | main | 标签 | 与推荐版差异 |
|---|---|---|---|---|---|
| 工作文件/semiconductor_analysis/b2b_v2/actions/run.py | 53 | 2026-06-13 | × | normal | (推荐) |
| semiconductor_analysis/b2b_v2/actions/run.py | 49 | 2026-05-24 | × | normal | 行数少4行; 摘要差异: 行动建议汇总入口 — 串联 L1/L2 告警+策略 + L3 交叉销售 |

### `b2b_v2/anomaly/rules.py` — 规则检测器 — 6个独立异常检测器

**推荐保留: `工作文件/semiconductor_analysis/b2b_v2/anomaly/rules.py`** — 内容有差异,推荐非备份目录中最后修改(2026-06-22)的版本

| 文件 | 行数 | 最后修改 | main | 标签 | 与推荐版差异 |
|---|---|---|---|---|---|
| 工作文件/semiconductor_analysis/b2b_v2/anomaly/rules.py | 336 | 2026-06-22 | × | normal | (推荐) |
| semiconductor_analysis/b2b_v2/anomaly/rules.py | 350 | 2026-05-25 | × | normal | 行数多14行 |

### `b2b_v2/behavior/volatility.py` — Task 5: 采购波动性/稳定性指标 (Volatility Metrics).

**推荐保留: `工作文件/semiconductor_analysis/b2b_v2/behavior/volatility.py`** — 内容有差异,推荐非备份目录中最后修改(2026-06-13)的版本

| 文件 | 行数 | 最后修改 | main | 标签 | 与推荐版差异 |
|---|---|---|---|---|---|
| 工作文件/semiconductor_analysis/b2b_v2/behavior/volatility.py | 181 | 2026-06-13 | × | normal | (推荐) |
| semiconductor_analysis/b2b_v2/behavior/volatility.py | 177 | 2026-05-24 | × | normal | 行数少4行 |

### `b2b_v2/profitability/true_profit_estimator.py` — Task 6: 真实利润贡献度 (True Profit).

**推荐保留: `工作文件/semiconductor_analysis/b2b_v2/profitability/true_profit_estimator.py`** — 内容有差异,推荐非备份目录中最后修改(2026-06-13)的版本

| 文件 | 行数 | 最后修改 | main | 标签 | 与推荐版差异 |
|---|---|---|---|---|---|
| 工作文件/semiconductor_analysis/b2b_v2/profitability/true_profit_estimator.py | 75 | 2026-06-13 | × | normal | (推荐) |
| semiconductor_analysis/b2b_v2/profitability/true_profit_estimator.py | 183 | 2026-05-24 | × | normal | 行数多108行; 摘要差异: Task 6: 估算真实利润贡献度 (Estimated True Profit |

### `config/__init__.py` — 包初始化,导出settings模块中的项目根目录、数据目录、输出目录等全局配置变量

**推荐保留: `工作文件/semiconductor_analysis/config/__init__.py`** — 内容有差异,推荐非备份目录中最后修改(2026-05-23)的版本

| 文件 | 行数 | 最后修改 | main | 标签 | 与推荐版差异 |
|---|---|---|---|---|---|
| 工作文件/semiconductor_analysis/config/__init__.py | 15 | 2026-05-23 | × | normal | (推荐) |
| semiconductor_analysis/config/__init__.py | 15 | 2026-05-23 | × | normal | 结构相近 |
| semiconductor_analysis_before/config/__init__.py | 19 | 2026-05-19 | × | normal | 行数多4行; 摘要差异: 旧版配置模块初始化,导出settings配置变量(含V28_DIR等遗留字段) |

### `config/settings.py` — 统一配置文件（v2.0 — 全面注释版）

**推荐保留: `工作文件/semiconductor_analysis/config/settings.py`** — 内容有差异,推荐非备份目录中最后修改(2026-07-03)的版本

| 文件 | 行数 | 最后修改 | main | 标签 | 与推荐版差异 |
|---|---|---|---|---|---|
| 工作文件/semiconductor_analysis/config/settings.py | 159 | 2026-07-03 | × | normal | (推荐) |
| semiconductor_analysis/config/settings.py | 153 | 2026-06-03 | × | normal | 行数少6行 |
| semiconductor_analysis_before/config/settings.py | 401 | 2026-05-22 | × | normal | 行数多242行; 摘要差异: 统一配置文件 |

### `config/settings_customer.py` — ── 客户分析配置（分拆自 config/settings.py P1-A）── 设计意图：客户分析涉及客户等级、渠道、

**推荐保留: `工作文件/semiconductor_analysis/config/settings_customer.py`** — 内容有差异,推荐非备份目录中最后修改(2026-06-15)的版本

| 文件 | 行数 | 最后修改 | main | 标签 | 与推荐版差异 |
|---|---|---|---|---|---|
| 工作文件/semiconductor_analysis/config/settings_customer.py | 801 | 2026-06-15 | × | normal | (推荐) |
| semiconductor_analysis/config/settings_customer.py | 765 | 2026-05-24 | × | normal | 行数少36行 |

### `cross_reference/__init__.py` — 导出跨参考模块的run函数,用于执行交叉引用分析

**推荐保留: `工作文件/semiconductor_analysis/cross_reference/__init__.py`** — 内容有差异,推荐非备份目录中最后修改(2026-05-22)的版本

| 文件 | 行数 | 最后修改 | main | 标签 | 与推荐版差异 |
|---|---|---|---|---|---|
| 工作文件/semiconductor_analysis/cross_reference/__init__.py | 1 | 2026-05-22 | × | normal | (推荐) |
| semiconductor_analysis/cross_reference/__init__.py | 1 | 2026-05-22 | × | normal | 结构相近 |
| semiconductor_analysis_before/cross_reference/__init__.py | 1 | 2026-05-19 | × | normal | 摘要差异: 旧版交叉引用模块,导出run_cross_reference函数 |

### `cross_reference/run_cross_ref.py` — 交叉关联层

**推荐保留: `工作文件/semiconductor_analysis/cross_reference/run_cross_ref.py`** — 内容有差异,推荐非备份目录中最后修改(2026-06-03)的版本

| 文件 | 行数 | 最后修改 | main | 标签 | 与推荐版差异 |
|---|---|---|---|---|---|
| 工作文件/semiconductor_analysis/cross_reference/run_cross_ref.py | 176 | 2026-06-03 | √ | normal | (推荐) |
| semiconductor_analysis/cross_reference/run_cross_ref.py | 176 | 2026-06-03 | √ | normal | 结构相近 |
| semiconductor_analysis_before/cross_reference/run_cross_ref.py | 172 | 2026-05-15 | √ | normal | 行数少4行 |

### `customer_analysis/__init__.py` — 导出客户分析模块:客户RFM_PI评分模型、pipeline运行函数、画像计算和Gold表生成

**推荐保留: `工作文件/semiconductor_analysis/customer_analysis/__init__.py`** — 内容有差异,推荐非备份目录中最后修改(2026-05-23)的版本

| 文件 | 行数 | 最后修改 | main | 标签 | 与推荐版差异 |
|---|---|---|---|---|---|
| 工作文件/semiconductor_analysis/customer_analysis/__init__.py | 10 | 2026-05-23 | × | normal | (推荐) |
| semiconductor_analysis/customer_analysis/__init__.py | 10 | 2026-05-23 | × | normal | 结构相近 |
| semiconductor_analysis_before/customer_analysis/__init__.py | 12 | 2026-05-20 | × | normal | 行数多2行; 摘要差异: 旧版客户分析模块,导出RFM_PI/机会评分/风险评分模型及pipeline函数 |

### `customer_analysis/gold.py` — Gold 层表生成

**推荐保留: `工作文件/semiconductor_analysis/customer_analysis/gold.py`** — 内容有差异,推荐非备份目录中最后修改(2026-06-17)的版本

| 文件 | 行数 | 最后修改 | main | 标签 | 与推荐版差异 |
|---|---|---|---|---|---|
| 工作文件/semiconductor_analysis/customer_analysis/gold.py | 464 | 2026-06-17 | × | normal | (推荐) |
| semiconductor_analysis/customer_analysis/gold.py | 321 | 2026-05-24 | × | normal | 行数少143行 |

### `customer_analysis/models.py` — 客户分析评分模型

**推荐保留: `工作文件/semiconductor_analysis/customer_analysis/models.py`** — 内容有差异,推荐非备份目录中最后修改(2026-05-24)的版本

| 文件 | 行数 | 最后修改 | main | 标签 | 与推荐版差异 |
|---|---|---|---|---|---|
| 工作文件/semiconductor_analysis/customer_analysis/models.py | 10 | 2026-05-24 | × | normal | (推荐) |
| semiconductor_analysis/customer_analysis/models.py | 10 | 2026-05-24 | × | normal | 结构相近 |
| semiconductor_analysis_before/customer_analysis/models.py | 247 | 2026-05-22 | × | normal | 行数多237行 |

### `customer_analysis/portrait.py` — 客户全景画像计算

**推荐保留: `工作文件/semiconductor_analysis/customer_analysis/portrait.py`** — 内容有差异,推荐非备份目录中最后修改(2026-06-16)的版本

| 文件 | 行数 | 最后修改 | main | 标签 | 与推荐版差异 |
|---|---|---|---|---|---|
| 工作文件/semiconductor_analysis/customer_analysis/portrait.py | 476 | 2026-06-16 | × | normal | (推荐) |
| semiconductor_analysis/customer_analysis/portrait.py | 449 | 2026-05-24 | × | normal | 行数少27行 |

### `customer_analysis/price_deep_dive.py` — 价格深度分析模块（Phase 3）

**推荐保留: `工作文件/semiconductor_analysis/customer_analysis/price_deep_dive.py`** — 内容有差异,推荐非备份目录中最后修改(2026-06-17)的版本

| 文件 | 行数 | 最后修改 | main | 标签 | 与推荐版差异 |
|---|---|---|---|---|---|
| 工作文件/semiconductor_analysis/customer_analysis/price_deep_dive.py | 583 | 2026-06-17 | × | normal | (推荐) |
| semiconductor_analysis/customer_analysis/price_deep_dive.py | 410 | 2026-05-25 | × | normal | 行数少173行 |

### `customer_analysis/run_kpi_daily.py` — 准实时KPI通道 — 单独入口，独立于主管道运行

**推荐保留: `工作文件/semiconductor_analysis/customer_analysis/run_kpi_daily.py`** — 内容有差异,推荐非备份目录中最后修改(2026-06-12)的版本

| 文件 | 行数 | 最后修改 | main | 标签 | 与推荐版差异 |
|---|---|---|---|---|---|
| 工作文件/semiconductor_analysis/customer_analysis/run_kpi_daily.py | 119 | 2026-06-12 | √ | normal | (推荐) |
| semiconductor_analysis/customer_analysis/run_kpi_daily.py | 118 | 2026-05-24 | √ | normal | 行数少1行 |
| semiconductor_analysis_before/customer_analysis/run_kpi_daily.py | 95 | 2026-05-15 | √ | normal | 行数少24行; 摘要差异: 准实时KPI通道 |

### `customer_analysis/run_pipeline.py` — 客户销售分析管道 — 编排层

**推荐保留: `工作文件/semiconductor_analysis/customer_analysis/run_pipeline.py`** — 内容有差异,推荐非备份目录中最后修改(2026-06-12)的版本

| 文件 | 行数 | 最后修改 | main | 标签 | 与推荐版差异 |
|---|---|---|---|---|---|
| 工作文件/semiconductor_analysis/customer_analysis/run_pipeline.py | 222 | 2026-06-12 | √ | normal | (推荐) |
| semiconductor_analysis/customer_analysis/run_pipeline.py | 193 | 2026-05-24 | √ | normal | 行数少29行 |
| semiconductor_analysis_before/customer_analysis/run_pipeline.py | 582 | 2026-05-22 | √ | normal | 行数多360行; 摘要差异: 客户销售分析管道 |

### `customer_analysis/trend_analysis.py` — 趋势分析深化模块（Phase 4）

**推荐保留: `工作文件/semiconductor_analysis/customer_analysis/trend_analysis.py`** — 内容有差异,推荐非备份目录中最后修改(2026-06-15)的版本

| 文件 | 行数 | 最后修改 | main | 标签 | 与推荐版差异 |
|---|---|---|---|---|---|
| 工作文件/semiconductor_analysis/customer_analysis/trend_analysis.py | 308 | 2026-06-15 | × | normal | (推荐) |
| semiconductor_analysis/customer_analysis/trend_analysis.py | 308 | 2026-05-24 | × | normal | 结构相近 |

### `product_lifecycle/nine_grid.py` — 九宫格画像定位 — 产品生命周期专属

**推荐保留: `工作文件/semiconductor_analysis/product_lifecycle/nine_grid.py`** — 内容有差异,推荐非备份目录中最后修改(2026-05-24)的版本

| 文件 | 行数 | 最后修改 | main | 标签 | 与推荐版差异 |
|---|---|---|---|---|---|
| 工作文件/semiconductor_analysis/product_lifecycle/nine_grid.py | 127 | 2026-05-24 | × | normal | (推荐) |
| semiconductor_analysis/product_lifecycle/nine_grid.py | 127 | 2026-05-24 | × | normal | 结构相近 |
| semiconductor_analysis_before/product_lifecycle/nine_grid.py | 106 | 2026-05-21 | × | normal | 行数少21行 |

### `product_lifecycle/notes.py` — 特情说明生成 — 产品生命周期专属（v4.0）

**推荐保留: `工作文件/semiconductor_analysis/product_lifecycle/notes.py`** — 内容有差异,推荐非备份目录中最后修改(2026-06-03)的版本

| 文件 | 行数 | 最后修改 | main | 标签 | 与推荐版差异 |
|---|---|---|---|---|---|
| 工作文件/semiconductor_analysis/product_lifecycle/notes.py | 155 | 2026-06-03 | × | normal | (推荐) |
| semiconductor_analysis/product_lifecycle/notes.py | 155 | 2026-06-03 | × | normal | 结构相近 |
| semiconductor_analysis_before/product_lifecycle/notes.py | 133 | 2026-05-21 | × | normal | 行数少22行; 摘要差异: 特情说明生成 — 产品生命周期专属（v2.9） |

### `product_lifecycle/profiling.py` — 产品画像核心引擎 — v4.0: 4因子(毛利率斜率+增速衰减+自比健康度+订货量变化)风险评分

**推荐保留: `工作文件/semiconductor_analysis/product_lifecycle/profiling.py`** — 内容有差异,推荐非备份目录中最后修改(2026-06-03)的版本

| 文件 | 行数 | 最后修改 | main | 标签 | 与推荐版差异 |
|---|---|---|---|---|---|
| 工作文件/semiconductor_analysis/product_lifecycle/profiling.py | 1188 | 2026-06-03 | × | normal | (推荐) |
| semiconductor_analysis/product_lifecycle/profiling.py | 1188 | 2026-06-03 | × | normal | 结构相近 |
| semiconductor_analysis_before/product_lifecycle/profiling.py | 1025 | 2026-05-22 | × | normal | 行数少163行; 摘要差异: 产品画像核心引擎 — 从v2.8的run_profiling解耦重写 |

### `product_lifecycle/run.py` — 产品生命周期分析 — v2.8解耦重写版

**推荐保留: `工作文件/semiconductor_analysis/product_lifecycle/run.py`** — 内容有差异,推荐非备份目录中最后修改(2026-06-03)的版本

| 文件 | 行数 | 最后修改 | main | 标签 | 与推荐版差异 |
|---|---|---|---|---|---|
| 工作文件/semiconductor_analysis/product_lifecycle/run.py | 562 | 2026-06-03 | √ | normal | (推荐) |
| semiconductor_analysis/product_lifecycle/run.py | 562 | 2026-06-03 | √ | normal | 结构相近 |
| semiconductor_analysis_before/product_lifecycle/run.py | 1019 | 2026-05-22 | √ | normal | 行数多457行 |

### `quarterly_forecast_package/run_customer_forecast.py` — 客户维度滚动季度历史分析与预测（KA/AA客户）

**推荐保留: `semiconductor_analysis/quarterly_forecast_package/run_customer_forecast.py`** — 内容有差异,推荐非备份目录中最后修改(2026-06-12)的版本

| 文件 | 行数 | 最后修改 | main | 标签 | 与推荐版差异 |
|---|---|---|---|---|---|
| semiconductor_analysis/quarterly_forecast_package/run_customer_forecast.py | 974 | 2026-06-12 | √ | normal | (推荐) |
| 工作文件/semiconductor_analysis/quarterly_forecast_package/run_customer_forecast.py | 974 | 2026-06-11 | √ | normal | 结构相近 |

### `quarterly_forecast_package/run_quarterly_forecast.py` — 产品线滚动季度历史分析与预测

**推荐保留: `semiconductor_analysis/quarterly_forecast_package/run_quarterly_forecast.py`** — 内容有差异,推荐非备份目录中最后修改(2026-06-12)的版本

| 文件 | 行数 | 最后修改 | main | 标签 | 与推荐版差异 |
|---|---|---|---|---|---|
| semiconductor_analysis/quarterly_forecast_package/run_quarterly_forecast.py | 1158 | 2026-06-12 | √ | normal | (推荐) |
| 工作文件/semiconductor_analysis/quarterly_forecast_package/run_quarterly_forecast.py | 1124 | 2026-06-11 | √ | normal | 行数少34行 |

### `reports/gold_exporter.py` — Gold 层表写入器 — CSV + 格式化 Excel 报告

**推荐保留: `工作文件/semiconductor_analysis/reports/gold_exporter.py`** — 内容有差异,推荐非备份目录中最后修改(2026-06-17)的版本

| 文件 | 行数 | 最后修改 | main | 标签 | 与推荐版差异 |
|---|---|---|---|---|---|
| 工作文件/semiconductor_analysis/reports/gold_exporter.py | 306 | 2026-06-17 | × | normal | (推荐) |
| semiconductor_analysis/reports/gold_exporter.py | 292 | 2026-05-24 | × | normal | 行数少14行 |

### `run_all.py` — 主管道编排脚本:按序执行silver数据清洗、product产品生命周期、customer客户分析、kpi准实时指标、cross_ref交叉关联五个阶段

**推荐保留: `工作文件/semiconductor_analysis/run_all.py`** — 内容有差异,推荐非备份目录中最后修改(2026-06-22)的版本

| 文件 | 行数 | 最后修改 | main | 标签 | 与推荐版差异 |
|---|---|---|---|---|---|
| 工作文件/semiconductor_analysis/run_all.py | 442 | 2026-06-22 | √ | normal | (推荐) |
| semiconductor_analysis/run_all.py | 431 | 2026-06-03 | √ | normal | 行数少11行; 摘要差异: 半导体分析统一运行入口 |
| semiconductor_analysis_before/run_all.py | 230 | 2026-05-20 | √ | normal | 行数少212行; 摘要差异: 半导体分析统一运行入口 |

### `run_customer.py` — 一键运行：客户分析

**推荐保留: `工作文件/semiconductor_analysis/run_customer.py`** — 内容有差异,推荐非备份目录中最后修改(2026-05-25)的版本

| 文件 | 行数 | 最后修改 | main | 标签 | 与推荐版差异 |
|---|---|---|---|---|---|
| 工作文件/semiconductor_analysis/run_customer.py | 14 | 2026-05-25 | × | normal | (推荐) |
| semiconductor_analysis/run_customer.py | 14 | 2026-05-25 | × | normal | 结构相近 |
| semiconductor_analysis_before/run_customer.py | 5 | 2026-05-20 | × | normal | 行数少9行 |

### `run_product.py` — 一键运行：产品生命周期分析

**推荐保留: `工作文件/semiconductor_analysis/run_product.py`** — 内容有差异,推荐非备份目录中最后修改(2026-05-27)的版本

| 文件 | 行数 | 最后修改 | main | 标签 | 与推荐版差异 |
|---|---|---|---|---|---|
| 工作文件/semiconductor_analysis/run_product.py | 15 | 2026-05-27 | √ | normal | (推荐) |
| semiconductor_analysis/run_product.py | 15 | 2026-05-27 | √ | normal | 结构相近 |
| semiconductor_analysis_before/run_product.py | 5 | 2026-05-20 | × | normal | 行数少10行; 无main保护 |

### `shared/__init__.py` — 导出共享工具模块:数据清洗、计算工具、分类器、风险评分、定价、预测和客户分析函数

**推荐保留: `工作文件/semiconductor_analysis/shared/__init__.py`** — 内容有差异,推荐非备份目录中最后修改(2026-06-02)的版本

| 文件 | 行数 | 最后修改 | main | 标签 | 与推荐版差异 |
|---|---|---|---|---|---|
| 工作文件/semiconductor_analysis/shared/__init__.py | 54 | 2026-06-02 | × | normal | (推荐) |
| semiconductor_analysis/shared/__init__.py | 54 | 2026-06-02 | × | normal | 结构相近 |
| semiconductor_analysis_before/shared/__init__.py | 48 | 2026-05-20 | × | normal | 行数少6行; 摘要差异: 旧版共享工具模块,导出数据清洗/计算/分类/风险评分/定价/预测等函数 |

### `shared/calc_utils.py` — 共享计算工具:斜率/月龄/增长率/集中度/HHI指数/分位切割等统计分析函数

**推荐保留: `工作文件/semiconductor_analysis/shared/calc_utils.py`** — 内容有差异,推荐非备份目录中最后修改(2026-05-24)的版本

| 文件 | 行数 | 最后修改 | main | 标签 | 与推荐版差异 |
|---|---|---|---|---|---|
| 工作文件/semiconductor_analysis/shared/calc_utils.py | 156 | 2026-05-24 | × | normal | (推荐) |
| semiconductor_analysis/shared/calc_utils.py | 156 | 2026-05-24 | × | normal | 结构相近 |
| semiconductor_analysis_before/shared/calc_utils.py | 156 | 2026-05-15 | × | normal | 摘要差异: 旧版共享计算工具:与新版calc_utils功能基本一致,slope排序参数略有 |

### `shared/customer_analysis.py` — 客户分析函数 — 从v2.8提取的RFM分群和产品关联分析

**推荐保留: `工作文件/semiconductor_analysis/shared/customer_analysis.py`** — 内容有差异,推荐非备份目录中最后修改(2026-05-24)的版本

| 文件 | 行数 | 最后修改 | main | 标签 | 与推荐版差异 |
|---|---|---|---|---|---|
| 工作文件/semiconductor_analysis/shared/customer_analysis.py | 179 | 2026-05-24 | × | normal | (推荐) |
| semiconductor_analysis/shared/customer_analysis.py | 179 | 2026-05-24 | × | normal | 结构相近 |
| semiconductor_analysis_before/shared/customer_analysis.py | 179 | 2026-05-19 | × | normal | 结构相近 |

### `shared/data_cleaning.py` — 共享数据清洗管道

**推荐保留: `工作文件/semiconductor_analysis/shared/data_cleaning.py`** — 内容有差异,推荐非备份目录中最后修改(2026-07-03)的版本

| 文件 | 行数 | 最后修改 | main | 标签 | 与推荐版差异 |
|---|---|---|---|---|---|
| 工作文件/semiconductor_analysis/shared/data_cleaning.py | 429 | 2026-07-03 | × | normal | (推荐) |
| semiconductor_analysis/shared/data_cleaning.py | 398 | 2026-06-03 | × | normal | 行数少31行 |
| semiconductor_analysis_before/shared/data_cleaning.py | 227 | 2026-05-22 | × | normal | 行数少202行; 摘要差异: 旧版共享数据清洗管道 |

### `shared/forecasting.py` — 预测函数 — 从v2.8提取的ETS预测和加权移动平均

**推荐保留: `工作文件/semiconductor_analysis/shared/forecasting.py`** — 内容有差异,推荐非备份目录中最后修改(2026-05-25)的版本

| 文件 | 行数 | 最后修改 | main | 标签 | 与推荐版差异 |
|---|---|---|---|---|---|
| 工作文件/semiconductor_analysis/shared/forecasting.py | 253 | 2026-05-25 | × | normal | (推荐) |
| semiconductor_analysis/shared/forecasting.py | 253 | 2026-05-25 | × | normal | 结构相近 |
| semiconductor_analysis_before/shared/forecasting.py | 226 | 2026-05-19 | × | normal | 行数少27行 |

### `shared/pricing.py` — 价格分析函数 — 向后兼容重导出层

**推荐保留: `工作文件/semiconductor_analysis/shared/pricing.py`** — 内容有差异,推荐非备份目录中最后修改(2026-05-24)的版本

| 文件 | 行数 | 最后修改 | main | 标签 | 与推荐版差异 |
|---|---|---|---|---|---|
| 工作文件/semiconductor_analysis/shared/pricing.py | 14 | 2026-05-24 | × | normal | (推荐) |
| semiconductor_analysis/shared/pricing.py | 14 | 2026-05-24 | × | normal | 结构相近 |
| semiconductor_analysis_before/shared/pricing.py | 1070 | 2026-05-22 | × | normal | 行数多1056行; 摘要差异: 价格分析函数 — ASP趋势、弹性计算、价格偏离度、价格带分布 |

### `shared/risk_scoring.py` — 风险评分函数 — v4.0 4因子模型 (优化版)

**推荐保留: `工作文件/semiconductor_analysis/shared/risk_scoring.py`** — 内容有差异,推荐非备份目录中最后修改(2026-06-03)的版本

| 文件 | 行数 | 最后修改 | main | 标签 | 与推荐版差异 |
|---|---|---|---|---|---|
| 工作文件/semiconductor_analysis/shared/risk_scoring.py | 373 | 2026-06-03 | × | normal | (推荐) |
| semiconductor_analysis/shared/risk_scoring.py | 373 | 2026-06-03 | × | normal | 结构相近 |
| semiconductor_analysis_before/shared/risk_scoring.py | 203 | 2026-05-21 | × | normal | 行数少170行; 摘要差异: 风险评分函数 — v2.9 5因子模型 |

### `test/batch_a_test.py` — Batch A end-to-end test: 新品标记传播 + 爬坡期配置验证

**推荐保留: `工作文件/semiconductor_analysis/test/batch_a_test.py`** — 内容有差异,推荐非备份目录中最后修改(2026-05-22)的版本

| 文件 | 行数 | 最后修改 | main | 标签 | 与推荐版差异 |
|---|---|---|---|---|---|
| 工作文件/semiconductor_analysis/test/batch_a_test.py | 208 | 2026-05-22 | × | normal | (推荐) |
| semiconductor_analysis/test/batch_a_test.py | 208 | 2026-05-22 | × | normal | 结构相近 |
| semiconductor_analysis_before/test/batch_a_test.py | 207 | 2026-05-22 | × | normal | 行数少1行 |

### `test/conftest.py` — 共享测试基础设施：路径、中间件(pickle)管理、日志、测试结果结构

**推荐保留: `工作文件/semiconductor_analysis/test/conftest.py`** — 内容有差异,推荐非备份目录中最后修改(2026-05-24)的版本

| 文件 | 行数 | 最后修改 | main | 标签 | 与推荐版差异 |
|---|---|---|---|---|---|
| 工作文件/semiconductor_analysis/test/conftest.py | 210 | 2026-05-24 | × | normal | (推荐) |
| semiconductor_analysis/test/conftest.py | 210 | 2026-05-24 | × | normal | 结构相近 |
| semiconductor_analysis_before/test/conftest.py | 208 | 2026-05-22 | × | normal | 行数少2行 |

### `test/fallback.py` — -*- coding: utf-8 -*-

**推荐保留: `工作文件/semiconductor_analysis/test/fallback.py`** — 内容有差异,推荐非备份目录中最后修改(2026-05-24)的版本

| 文件 | 行数 | 最后修改 | main | 标签 | 与推荐版差异 |
|---|---|---|---|---|---|
| 工作文件/semiconductor_analysis/test/fallback.py | 301 | 2026-05-24 | √ | normal | (推荐) |
| semiconductor_analysis/test/fallback.py | 301 | 2026-05-24 | √ | normal | 结构相近 |
| semiconductor_analysis_before/test/fallback.py | 301 | 2026-05-22 | √ | normal | 结构相近 |

### `test/phase1_load.py` — Phase 1：加载 & Silver 构建

**推荐保留: `工作文件/semiconductor_analysis/test/phase1_load.py`** — 内容有差异,推荐非备份目录中最后修改(2026-05-24)的版本

| 文件 | 行数 | 最后修改 | main | 标签 | 与推荐版差异 |
|---|---|---|---|---|---|
| 工作文件/semiconductor_analysis/test/phase1_load.py | 151 | 2026-05-24 | √ | normal | (推荐) |
| semiconductor_analysis/test/phase1_load.py | 151 | 2026-05-24 | √ | normal | 结构相近 |
| semiconductor_analysis_before/test/phase1_load.py | 150 | 2026-05-22 | √ | normal | 行数少1行 |

### `test/phase2_validate.py` — -*- coding: utf-8 -*-

**推荐保留: `工作文件/semiconductor_analysis/test/phase2_validate.py`** — 内容有差异,推荐非备份目录中最后修改(2026-05-24)的版本

| 文件 | 行数 | 最后修改 | main | 标签 | 与推荐版差异 |
|---|---|---|---|---|---|
| 工作文件/semiconductor_analysis/test/phase2_validate.py | 490 | 2026-05-24 | √ | normal | (推荐) |
| semiconductor_analysis/test/phase2_validate.py | 490 | 2026-05-24 | √ | normal | 结构相近 |
| semiconductor_analysis_before/test/phase2_validate.py | 490 | 2026-05-22 | √ | normal | 结构相近 |

### `test/phase3_visualize.py` — Phase 3：可视化图表生成（01-15）

**推荐保留: `工作文件/semiconductor_analysis/test/phase3_visualize.py`** — 内容有差异,推荐非备份目录中最后修改(2026-06-03)的版本

| 文件 | 行数 | 最后修改 | main | 标签 | 与推荐版差异 |
|---|---|---|---|---|---|
| 工作文件/semiconductor_analysis/test/phase3_visualize.py | 1050 | 2026-06-03 | √ | normal | (推荐) |
| semiconductor_analysis/test/phase3_visualize.py | 1050 | 2026-06-03 | √ | normal | 结构相近 |
| semiconductor_analysis_before/test/phase3_visualize.py | 385 | 2026-05-22 | √ | normal | 行数少665行; 摘要差异: -*- coding: utf-8 -*- |

### `test/run_all_tests.py` — -*- coding: utf-8 -*-

**推荐保留: `工作文件/semiconductor_analysis/test/run_all_tests.py`** — 内容有差异,推荐非备份目录中最后修改(2026-05-24)的版本

| 文件 | 行数 | 最后修改 | main | 标签 | 与推荐版差异 |
|---|---|---|---|---|---|
| 工作文件/semiconductor_analysis/test/run_all_tests.py | 208 | 2026-05-24 | √ | normal | (推荐) |
| semiconductor_analysis/test/run_all_tests.py | 208 | 2026-05-24 | √ | normal | 结构相近 |
| semiconductor_analysis_before/test/run_all_tests.py | 174 | 2026-05-22 | √ | normal | 行数少34行 |

### `test/test_week1_modules.py` — Week 1 单元测试: 客户旅程阶段 (Task 1), 波动性指标 (Task 5), 真实利润估算 (Task 6).

**推荐保留: `工作文件/semiconductor_analysis/test/test_week1_modules.py`** — 内容有差异,推荐非备份目录中最后修改(2026-05-24)的版本

| 文件 | 行数 | 最后修改 | main | 标签 | 与推荐版差异 |
|---|---|---|---|---|---|
| 工作文件/semiconductor_analysis/test/test_week1_modules.py | 339 | 2026-05-24 | √ | normal | (推荐) |
| semiconductor_analysis/test/test_week1_modules.py | 339 | 2026-05-24 | √ | normal | 结构相近 |
| semiconductor_analysis_before/test/test_week1_modules.py | 339 | 2026-05-22 | √ | normal | 结构相近 |

## B. 完全相同的多副本组(仅保留一份即可)

| 模块 | 副本数 | 副本位置 | 推荐保留 |
|---|---|---|---|
| analysis/__init__.py | 2 | semiconductor_analysis/analysis/__init__.py<br>工作文件/semiconductor_analysis/analysis/__init__.py | semiconductor_analysis/analysis/__init__.py |
| analysis/b2b_adapters.py | 2 | semiconductor_analysis/analysis/b2b_adapters.py<br>工作文件/semiconductor_analysis/analysis/b2b_adapters.py | semiconductor_analysis/analysis/b2b_adapters.py |
| analysis/c6_production_mapping.py | 2 | semiconductor_analysis/analysis/c6_production_mapping.py<br>工作文件/semiconductor_analysis/analysis/c6_production_mapping.py | semiconductor_analysis/analysis/c6_production_mapping.py |
| analysis/gold_builders.py | 2 | semiconductor_analysis/analysis/gold_builders.py<br>工作文件/semiconductor_analysis/analysis/gold_builders.py | semiconductor_analysis/analysis/gold_builders.py |
| analysis/pricing/__init__.py | 2 | semiconductor_analysis/analysis/pricing/__init__.py<br>工作文件/semiconductor_analysis/analysis/pricing/__init__.py | semiconductor_analysis/analysis/pricing/__init__.py |
| analysis/pricing/pricing_actions.py | 2 | semiconductor_analysis/analysis/pricing/pricing_actions.py<br>工作文件/semiconductor_analysis/analysis/pricing/pricing_actions.py | semiconductor_analysis/analysis/pricing/pricing_actions.py |
| analysis/pricing/pricing_insights.py | 2 | semiconductor_analysis/analysis/pricing/pricing_insights.py<br>工作文件/semiconductor_analysis/analysis/pricing/pricing_insights.py | semiconductor_analysis/analysis/pricing/pricing_insights.py |
| analysis/pricing/pricing_trends.py | 2 | semiconductor_analysis/analysis/pricing/pricing_trends.py<br>工作文件/semiconductor_analysis/analysis/pricing/pricing_trends.py | semiconductor_analysis/analysis/pricing/pricing_trends.py |
| analysis/rfm_pi.py | 2 | semiconductor_analysis/analysis/rfm_pi.py<br>工作文件/semiconductor_analysis/analysis/rfm_pi.py | semiconductor_analysis/analysis/rfm_pi.py |
| b2b_v2/__init__.py | 2 | semiconductor_analysis/b2b_v2/__init__.py<br>工作文件/semiconductor_analysis/b2b_v2/__init__.py | semiconductor_analysis/b2b_v2/__init__.py |
| b2b_v2/actions/__init__.py | 2 | semiconductor_analysis/b2b_v2/actions/__init__.py<br>工作文件/semiconductor_analysis/b2b_v2/actions/__init__.py | semiconductor_analysis/b2b_v2/actions/__init__.py |
| b2b_v2/actions/cross_sell.py | 2 | semiconductor_analysis/b2b_v2/actions/cross_sell.py<br>工作文件/semiconductor_analysis/b2b_v2/actions/cross_sell.py | semiconductor_analysis/b2b_v2/actions/cross_sell.py |
| b2b_v2/anomaly/__init__.py | 2 | semiconductor_analysis/b2b_v2/anomaly/__init__.py<br>工作文件/semiconductor_analysis/b2b_v2/anomaly/__init__.py | semiconductor_analysis/b2b_v2/anomaly/__init__.py |
| b2b_v2/anomaly/inventory.py | 2 | semiconductor_analysis/b2b_v2/anomaly/inventory.py<br>工作文件/semiconductor_analysis/b2b_v2/anomaly/inventory.py | semiconductor_analysis/b2b_v2/anomaly/inventory.py |
| b2b_v2/anomaly/isolation_forest.py | 2 | semiconductor_analysis/b2b_v2/anomaly/isolation_forest.py<br>工作文件/semiconductor_analysis/b2b_v2/anomaly/isolation_forest.py | semiconductor_analysis/b2b_v2/anomaly/isolation_forest.py |
| b2b_v2/anomaly/run.py | 2 | semiconductor_analysis/b2b_v2/anomaly/run.py<br>工作文件/semiconductor_analysis/b2b_v2/anomaly/run.py | semiconductor_analysis/b2b_v2/anomaly/run.py |
| b2b_v2/behavior/__init__.py | 2 | semiconductor_analysis/b2b_v2/behavior/__init__.py<br>工作文件/semiconductor_analysis/b2b_v2/behavior/__init__.py | semiconductor_analysis/b2b_v2/behavior/__init__.py |
| b2b_v2/journey/__init__.py | 2 | semiconductor_analysis/b2b_v2/journey/__init__.py<br>工作文件/semiconductor_analysis/b2b_v2/journey/__init__.py | semiconductor_analysis/b2b_v2/journey/__init__.py |
| b2b_v2/journey/stage_classifier.py | 2 | semiconductor_analysis/b2b_v2/journey/stage_classifier.py<br>工作文件/semiconductor_analysis/b2b_v2/journey/stage_classifier.py | semiconductor_analysis/b2b_v2/journey/stage_classifier.py |
| b2b_v2/profitability/__init__.py | 2 | semiconductor_analysis/b2b_v2/profitability/__init__.py<br>工作文件/semiconductor_analysis/b2b_v2/profitability/__init__.py | semiconductor_analysis/b2b_v2/profitability/__init__.py |
| config/settings_product.py | 2 | semiconductor_analysis/config/settings_product.py<br>工作文件/semiconductor_analysis/config/settings_product.py | semiconductor_analysis/config/settings_product.py |
| core/__init__.py | 2 | semiconductor_analysis/core/__init__.py<br>工作文件/semiconductor_analysis/core/__init__.py | semiconductor_analysis/core/__init__.py |
| core/config.py | 2 | semiconductor_analysis/core/config.py<br>工作文件/semiconductor_analysis/core/config.py | semiconductor_analysis/core/config.py |
| core/interfaces.py | 2 | semiconductor_analysis/core/interfaces.py<br>工作文件/semiconductor_analysis/core/interfaces.py | semiconductor_analysis/core/interfaces.py |
| core/pipeline.py | 2 | semiconductor_analysis/core/pipeline.py<br>工作文件/semiconductor_analysis/core/pipeline.py | semiconductor_analysis/core/pipeline.py |
| customer_analysis/customer_master.py | 2 | semiconductor_analysis/customer_analysis/customer_master.py<br>工作文件/semiconductor_analysis/customer_analysis/customer_master.py | semiconductor_analysis/customer_analysis/customer_master.py |
| customer_analysis/dimensions.py | 2 | semiconductor_analysis/customer_analysis/dimensions.py<br>工作文件/semiconductor_analysis/customer_analysis/dimensions.py | semiconductor_analysis/customer_analysis/dimensions.py |
| customer_analysis/group_aggregation.py | 2 | semiconductor_analysis/customer_analysis/group_aggregation.py<br>工作文件/semiconductor_analysis/customer_analysis/group_aggregation.py | semiconductor_analysis/customer_analysis/group_aggregation.py |
| customer_analysis/report.py | 2 | semiconductor_analysis/customer_analysis/report.py<br>工作文件/semiconductor_analysis/customer_analysis/report.py | semiconductor_analysis/customer_analysis/report.py |
| customer_analysis/scoring.py | 2 | semiconductor_analysis/customer_analysis/scoring.py<br>工作文件/semiconductor_analysis/customer_analysis/scoring.py | semiconductor_analysis/customer_analysis/scoring.py |
| customer_analysis/silver.py | 2 | semiconductor_analysis/customer_analysis/silver.py<br>工作文件/semiconductor_analysis/customer_analysis/silver.py | semiconductor_analysis/customer_analysis/silver.py |
| data_pipeline/__init__.py | 2 | semiconductor_analysis/data_pipeline/__init__.py<br>工作文件/semiconductor_analysis/data_pipeline/__init__.py | semiconductor_analysis/data_pipeline/__init__.py |
| data_pipeline/aggregator.py | 2 | semiconductor_analysis/data_pipeline/aggregator.py<br>工作文件/semiconductor_analysis/data_pipeline/aggregator.py | semiconductor_analysis/data_pipeline/aggregator.py |
| data_pipeline/cleaner.py | 2 | semiconductor_analysis/data_pipeline/cleaner.py<br>工作文件/semiconductor_analysis/data_pipeline/cleaner.py | semiconductor_analysis/data_pipeline/cleaner.py |
| data_pipeline/loader.py | 2 | semiconductor_analysis/data_pipeline/loader.py<br>工作文件/semiconductor_analysis/data_pipeline/loader.py | semiconductor_analysis/data_pipeline/loader.py |
| data_pipeline/validator.py | 2 | semiconductor_analysis/data_pipeline/validator.py<br>工作文件/semiconductor_analysis/data_pipeline/validator.py | semiconductor_analysis/data_pipeline/validator.py |
| optimizer/__init__.py | 2 | semiconductor_analysis/optimizer/__init__.py<br>工作文件/semiconductor_analysis/optimizer/__init__.py | semiconductor_analysis/optimizer/__init__.py |
| optimizer/blindspot_analysis_rest.py | 2 | semiconductor_analysis/optimizer/blindspot_analysis_rest.py<br>工作文件/semiconductor_analysis/optimizer/blindspot_analysis_rest.py | semiconductor_analysis/optimizer/blindspot_analysis_rest.py |
| optimizer/blindspot_diagnosis.py | 2 | semiconductor_analysis/optimizer/blindspot_diagnosis.py<br>工作文件/semiconductor_analysis/optimizer/blindspot_diagnosis.py | semiconductor_analysis/optimizer/blindspot_diagnosis.py |
| optimizer/comprehensive_eval.py | 2 | semiconductor_analysis/optimizer/comprehensive_eval.py<br>工作文件/semiconductor_analysis/optimizer/comprehensive_eval.py | semiconductor_analysis/optimizer/comprehensive_eval.py |
| optimizer/comprehensive_eval_part2.py | 2 | semiconductor_analysis/optimizer/comprehensive_eval_part2.py<br>工作文件/semiconductor_analysis/optimizer/comprehensive_eval_part2.py | semiconductor_analysis/optimizer/comprehensive_eval_part2.py |
| optimizer/config.py | 2 | semiconductor_analysis/optimizer/config.py<br>工作文件/semiconductor_analysis/optimizer/config.py | semiconductor_analysis/optimizer/config.py |
| optimizer/crossval.py | 2 | semiconductor_analysis/optimizer/crossval.py<br>工作文件/semiconductor_analysis/optimizer/crossval.py | semiconductor_analysis/optimizer/crossval.py |
| optimizer/data_loader.py | 2 | semiconductor_analysis/optimizer/data_loader.py<br>工作文件/semiconductor_analysis/optimizer/data_loader.py | semiconductor_analysis/optimizer/data_loader.py |
| optimizer/evaluate_solutions_2024.py | 2 | semiconductor_analysis/optimizer/evaluate_solutions_2024.py<br>工作文件/semiconductor_analysis/optimizer/evaluate_solutions_2024.py | semiconductor_analysis/optimizer/evaluate_solutions_2024.py |
| optimizer/metrics.py | 2 | semiconductor_analysis/optimizer/metrics.py<br>工作文件/semiconductor_analysis/optimizer/metrics.py | semiconductor_analysis/optimizer/metrics.py |
| optimizer/recent_eval_and_solutions.py | 2 | semiconductor_analysis/optimizer/recent_eval_and_solutions.py<br>工作文件/semiconductor_analysis/optimizer/recent_eval_and_solutions.py | semiconductor_analysis/optimizer/recent_eval_and_solutions.py |
| optimizer/reporter.py | 2 | semiconductor_analysis/optimizer/reporter.py<br>工作文件/semiconductor_analysis/optimizer/reporter.py | semiconductor_analysis/optimizer/reporter.py |
| optimizer/run_pipeline.py | 2 | semiconductor_analysis/optimizer/run_pipeline.py<br>工作文件/semiconductor_analysis/optimizer/run_pipeline.py | semiconductor_analysis/optimizer/run_pipeline.py |
| optimizer/scoring_v2.py | 2 | semiconductor_analysis/optimizer/scoring_v2.py<br>工作文件/semiconductor_analysis/optimizer/scoring_v2.py | semiconductor_analysis/optimizer/scoring_v2.py |
| optimizer/threshold_search.py | 2 | semiconductor_analysis/optimizer/threshold_search.py<br>工作文件/semiconductor_analysis/optimizer/threshold_search.py | semiconductor_analysis/optimizer/threshold_search.py |
| optimizer/weight_search.py | 2 | semiconductor_analysis/optimizer/weight_search.py<br>工作文件/semiconductor_analysis/optimizer/weight_search.py | semiconductor_analysis/optimizer/weight_search.py |
| product_lifecycle/__init__.py | 3 | semiconductor_analysis/product_lifecycle/__init__.py<br>semiconductor_analysis_before/product_lifecycle/__init__.py<br>工作文件/semiconductor_analysis/product_lifecycle/__init__.py | semiconductor_analysis/product_lifecycle/__init__.py |
| product_lifecycle/report.py | 2 | semiconductor_analysis/product_lifecycle/report.py<br>工作文件/semiconductor_analysis/product_lifecycle/report.py | semiconductor_analysis/product_lifecycle/report.py |
| recession_risk_opt/archive/analysis/analyze_results.py | 2 | semiconductor_analysis/recession_risk_opt/archive/analysis/analyze_results.py<br>工作文件/semiconductor_analysis/recession_risk_opt/archive/analysis/analyze_results.py | semiconductor_analysis/recession_risk_opt/archive/analysis/analyze_results.py |
| recession_risk_opt/archive/analysis/factor_exploration.py | 2 | semiconductor_analysis/recession_risk_opt/archive/analysis/factor_exploration.py<br>工作文件/semiconductor_analysis/recession_risk_opt/archive/analysis/factor_exploration.py | semiconductor_analysis/recession_risk_opt/archive/analysis/factor_exploration.py |
| recession_risk_opt/archive/analysis/orthogonal_check.py | 2 | semiconductor_analysis/recession_risk_opt/archive/analysis/orthogonal_check.py<br>工作文件/semiconductor_analysis/recession_risk_opt/archive/analysis/orthogonal_check.py | semiconductor_analysis/recession_risk_opt/archive/analysis/orthogonal_check.py |
| recession_risk_opt/archive/demo/demo_tiered_risk.py | 2 | semiconductor_analysis/recession_risk_opt/archive/demo/demo_tiered_risk.py<br>工作文件/semiconductor_analysis/recession_risk_opt/archive/demo/demo_tiered_risk.py | semiconductor_analysis/recession_risk_opt/archive/demo/demo_tiered_risk.py |
| recession_risk_opt/archive/runners/run_stage5.py | 2 | semiconductor_analysis/recession_risk_opt/archive/runners/run_stage5.py<br>工作文件/semiconductor_analysis/recession_risk_opt/archive/runners/run_stage5.py | semiconductor_analysis/recession_risk_opt/archive/runners/run_stage5.py |
| recession_risk_opt/archive/runners/stage5_final.py | 2 | semiconductor_analysis/recession_risk_opt/archive/runners/stage5_final.py<br>工作文件/semiconductor_analysis/recession_risk_opt/archive/runners/stage5_final.py | semiconductor_analysis/recession_risk_opt/archive/runners/stage5_final.py |
| recession_risk_opt/archive/tests/test_consec_decline.py | 2 | semiconductor_analysis/recession_risk_opt/archive/tests/test_consec_decline.py<br>工作文件/semiconductor_analysis/recession_risk_opt/archive/tests/test_consec_decline.py | semiconductor_analysis/recession_risk_opt/archive/tests/test_consec_decline.py |
| recession_risk_opt/backtest_framework.py | 2 | semiconductor_analysis/recession_risk_opt/backtest_framework.py<br>工作文件/semiconductor_analysis/recession_risk_opt/backtest_framework.py | semiconductor_analysis/recession_risk_opt/backtest_framework.py |
| recession_risk_opt/generate_snapshot.py | 2 | semiconductor_analysis/recession_risk_opt/generate_snapshot.py<br>工作文件/semiconductor_analysis/recession_risk_opt/generate_snapshot.py | semiconductor_analysis/recession_risk_opt/generate_snapshot.py |
| recession_risk_opt/models/risk_scorer.py | 2 | semiconductor_analysis/recession_risk_opt/models/risk_scorer.py<br>工作文件/semiconductor_analysis/recession_risk_opt/models/risk_scorer.py | semiconductor_analysis/recession_risk_opt/models/risk_scorer.py |
| recession_risk_opt/phase1_customer_factors.py | 2 | semiconductor_analysis/recession_risk_opt/phase1_customer_factors.py<br>工作文件/semiconductor_analysis/recession_risk_opt/phase1_customer_factors.py | semiconductor_analysis/recession_risk_opt/phase1_customer_factors.py |
| recession_risk_opt/phase2_f1_repair.py | 2 | semiconductor_analysis/recession_risk_opt/phase2_f1_repair.py<br>工作文件/semiconductor_analysis/recession_risk_opt/phase2_f1_repair.py | semiconductor_analysis/recession_risk_opt/phase2_f1_repair.py |
| recession_risk_opt/phase3_model_comparison.py | 2 | semiconductor_analysis/recession_risk_opt/phase3_model_comparison.py<br>工作文件/semiconductor_analysis/recession_risk_opt/phase3_model_comparison.py | semiconductor_analysis/recession_risk_opt/phase3_model_comparison.py |
| recession_risk_opt/phase4_case_review.py | 2 | semiconductor_analysis/recession_risk_opt/phase4_case_review.py<br>工作文件/semiconductor_analysis/recession_risk_opt/phase4_case_review.py | semiconductor_analysis/recession_risk_opt/phase4_case_review.py |
| recession_risk_opt/phase5_action_baseline.py | 2 | semiconductor_analysis/recession_risk_opt/phase5_action_baseline.py<br>工作文件/semiconductor_analysis/recession_risk_opt/phase5_action_baseline.py | semiconductor_analysis/recession_risk_opt/phase5_action_baseline.py |
| recession_risk_opt/phaseA_check_cross_validation.py | 2 | semiconductor_analysis/recession_risk_opt/phaseA_check_cross_validation.py<br>工作文件/semiconductor_analysis/recession_risk_opt/phaseA_check_cross_validation.py | semiconductor_analysis/recession_risk_opt/phaseA_check_cross_validation.py |
| recession_risk_opt/phaseA_data_check.py | 2 | semiconductor_analysis/recession_risk_opt/phaseA_data_check.py<br>工作文件/semiconductor_analysis/recession_risk_opt/phaseA_data_check.py | semiconductor_analysis/recession_risk_opt/phaseA_data_check.py |
| recession_risk_opt/phaseA_severity_distribution.py | 2 | semiconductor_analysis/recession_risk_opt/phaseA_severity_distribution.py<br>工作文件/semiconductor_analysis/recession_risk_opt/phaseA_severity_distribution.py | semiconductor_analysis/recession_risk_opt/phaseA_severity_distribution.py |
| recession_risk_opt/phaseB1a_severity_regression.py | 2 | semiconductor_analysis/recession_risk_opt/phaseB1a_severity_regression.py<br>工作文件/semiconductor_analysis/recession_risk_opt/phaseB1a_severity_regression.py | semiconductor_analysis/recession_risk_opt/phaseB1a_severity_regression.py |
| recession_risk_opt/pipeline.py | 2 | semiconductor_analysis/recession_risk_opt/pipeline.py<br>工作文件/semiconductor_analysis/recession_risk_opt/pipeline.py | semiconductor_analysis/recession_risk_opt/pipeline.py |
| recession_risk_opt/v31_calibration.py | 2 | semiconductor_analysis/recession_risk_opt/v31_calibration.py<br>工作文件/semiconductor_analysis/recession_risk_opt/v31_calibration.py | semiconductor_analysis/recession_risk_opt/v31_calibration.py |
| recession_risk_opt/v31_final_optimization.py | 2 | semiconductor_analysis/recession_risk_opt/v31_final_optimization.py<br>工作文件/semiconductor_analysis/recession_risk_opt/v31_final_optimization.py | semiconductor_analysis/recession_risk_opt/v31_final_optimization.py |
| reports/__init__.py | 2 | semiconductor_analysis/reports/__init__.py<br>工作文件/semiconductor_analysis/reports/__init__.py | semiconductor_analysis/reports/__init__.py |
| scripts/chart_data.py | 2 | semiconductor_analysis/scripts/chart_data.py<br>工作文件/semiconductor_analysis/scripts/chart_data.py | semiconductor_analysis/scripts/chart_data.py |
| scripts/final_forecast.py | 2 | semiconductor_analysis/scripts/final_forecast.py<br>工作文件/semiconductor_analysis/scripts/final_forecast.py | semiconductor_analysis/scripts/final_forecast.py |
| scripts/generate_chart_html.py | 2 | semiconductor_analysis/scripts/generate_chart_html.py<br>工作文件/semiconductor_analysis/scripts/generate_chart_html.py | semiconductor_analysis/scripts/generate_chart_html.py |
| shared/classifiers.py | 3 | semiconductor_analysis/shared/classifiers.py<br>semiconductor_analysis_before/shared/classifiers.py<br>工作文件/semiconductor_analysis/shared/classifiers.py | semiconductor_analysis/shared/classifiers.py |
| shared/timing.py | 2 | semiconductor_analysis/shared/timing.py<br>工作文件/semiconductor_analysis/shared/timing.py | semiconductor_analysis/shared/timing.py |
| test/__init__.py | 3 | semiconductor_analysis/test/__init__.py<br>semiconductor_analysis_before/test/__init__.py<br>工作文件/semiconductor_analysis/test/__init__.py | semiconductor_analysis/test/__init__.py |
| test/test_analysis_scoring.py | 2 | semiconductor_analysis/test/test_analysis_scoring.py<br>工作文件/semiconductor_analysis/test/test_analysis_scoring.py | semiconductor_analysis/test/test_analysis_scoring.py |
| test/test_gold_builders.py | 2 | semiconductor_analysis/test/test_gold_builders.py<br>工作文件/semiconductor_analysis/test/test_gold_builders.py | semiconductor_analysis/test/test_gold_builders.py |
| test/test_gold_exporter.py | 2 | semiconductor_analysis/test/test_gold_exporter.py<br>工作文件/semiconductor_analysis/test/test_gold_exporter.py | semiconductor_analysis/test/test_gold_exporter.py |
| test/test_pipeline.py | 2 | semiconductor_analysis/test/test_pipeline.py<br>工作文件/semiconductor_analysis/test/test_pipeline.py | semiconductor_analysis/test/test_pipeline.py |
| test/test_validator.py | 2 | semiconductor_analysis/test/test_validator.py<br>工作文件/semiconductor_analysis/test/test_validator.py | semiconductor_analysis/test/test_validator.py |
| test/validation_suite.py | 2 | semiconductor_analysis/test/validation_suite.py<br>工作文件/semiconductor_analysis/test/validation_suite.py | semiconductor_analysis/test/validation_suite.py |

## C. 唯一脚本(无跨项目副本)

### semiconductor_analysis

| 文件 | 摘要 | 行数 | main | 标签 | 结论 |
|---|---|---|---|---|---|
| _debug_f1f.py | -*- coding: utf-8 -*- | 31 | × | normal | 唯一版本,建议保留 |
| _debug_mw.py | -*- coding: utf-8 -*- Find lines with  | 11 | × | normal | 唯一版本,建议保留 |
| _explore_shipping.py | Only read key columns to speed up | 18 | × | normal | 唯一版本,建议保留 |
| _step1_c6_compute.py | c6 factor computation from 出货明细修正版.xls | 185 | × | normal | 唯一版本,建议保留 |
| _step2_test_c6.py | Task 2+3: c6 single-factor test + deci | 266 | × | normal | 唯一版本,建议保留 |
| conftest.py | pytest 根配置 | 13 | × | normal | 唯一版本,建议保留 |
| detailed_excel_analysis.py | Excel文件详细分析脚本 | 235 | √ | normal | 唯一版本,建议保留 |
| linked_list_cycle.py | LeetCode算法练习:判断链表是否有环并返回环入口(与数据分析无关) | 148 | √ | junk | 与数据分析无关,建议移出项目 |
| lru_cache_decorator.py | LeetCode缓存装饰器练习:实现线程安全的LRU缓存装饰器(与数据分析无 | 267 | √ | junk | 与数据分析无关,建议移出项目 |
| majority_element.py | LeetCode算法练习:摩尔投票法找出出现次数超过一半的元素(与数据分析无 | 81 | √ | junk | 与数据分析无关,建议移出项目 |
| optimize_duplicates.py | 算法优化练习:对比O(n³)到O(n)多种方法查找重复元素的性能差异(与数据 | 233 | √ | junk | 与数据分析无关,建议移出项目 |
| parse_excel_file.py | Excel文件解析脚本 | 71 | √ | normal | 唯一版本,建议保留 |
| race_condition_clear_demo.py | 线程并发演示:展示竞态条件问题及Lock/原子操作解决方案(与数据分析无关) | 219 | √ | junk | 与数据分析无关,建议移出项目 |
| safe_divide.py | 安全除法工具函数:避免除零和非数字类型报错,可设置默认值 | 114 | √ | normal | 唯一版本,建议保留 |
| thread_race_condition_demo.py | 线程竞态条件演示:展示Lock/Queue等方法解决并发访问共享变量问题(与 | 236 | √ | junk | 与数据分析无关,建议移出项目 |
| unified_forecast_system.py | Unified Forecast System - v2 Rewrite | 1525 | × | normal | 唯一版本,建议保留 |
| unified_forecast_system_backup_v1.py | Unified Forecast System - Optimized Re | 877 | × | normal | 唯一版本,建议保留 |
| unified_forecast_system_backup_v2.py | Unified Forecast System - v2 Rewrite | 1265 | × | normal | 唯一版本,建议保留 |
| unified_forecast_system_backup_v3.py | Unified Forecast System - v2 Rewrite | 1508 | × | normal | 唯一版本,建议保留 |
| unified_forecast_v3.py | Unified Forecast System v3 - Rebuilt w | 1843 | × | normal | 唯一版本,建议保留 |

### semiconductor_analysis/data

| 文件 | 摘要 | 行数 | main | 标签 | 结论 |
|---|---|---|---|---|---|
| decrypt_excel.py | decrypt_excel.py - ASE透明加密Excel文件静默解密工 | 909 | √ | normal | 唯一版本,建议保留 |

### semiconductor_analysis/experiment_log/00_master

| 文件 | 摘要 | 行数 | main | 标签 | 结论 |
|---|---|---|---|---|---|
| field_check_20260612.py | -*- coding: utf-8 -*- | 37 | × | normal | 唯一版本,建议保留 |
| field_check_period_20260612.py | -*- coding: utf-8 -*- | 24 | × | normal | 唯一版本,建议保留 |
| run_phase1_correction.py | Phase 1 完整修正脚本 | 328 | √ | normal | 唯一版本,建议保留 |
| summarize_corrected_runs_20260612.py | -*- coding: utf-8 -*- | 29 | × | normal | 唯一版本,建议保留 |

### semiconductor_analysis/experiment_log/01_exp_0.0_trivial_baselines

| 文件 | 摘要 | 行数 | main | 标签 | 结论 |
|---|---|---|---|---|---|
| run_0.0_trivial_baselines.py | run_0.0.py — 实验 0.0: 平凡基线建立 创建: 2026-0 | 166 | × | normal | 唯一版本,建议保留 |

### semiconductor_analysis/experiment_log/02_exp_0.0.5_coverage_diagnosis

| 文件 | 摘要 | 行数 | main | 标签 | 结论 |
|---|---|---|---|---|---|
| run_0.0.5_v2.py | run_0.0.5_v2.py — 实验 0.0.5: 产品线覆盖与字段一致 | 248 | × | normal | 唯一版本,建议保留 |

### semiconductor_analysis/experiment_log/04_exp_0.1.5_method_filter

| 文件 | 摘要 | 行数 | main | 标签 | 结论 |
|---|---|---|---|---|---|
| run_0.1.5_v2.py | run_0.1.5_v2.py — 实验 0.1.5: 方法预筛选（修订版） | 138 | × | normal | 唯一版本,建议保留 |

### semiconductor_analysis/experiment_log/05_exp_0.2_baseline_lock

| 文件 | 摘要 | 行数 | main | 标签 | 结论 |
|---|---|---|---|---|---|
| run_0.2_baseline_lock.py | run_0.2.py — 实验 0.2: 基线回测锁定 创建: 2026-0 | 538 | × | normal | 唯一版本,建议保留 |

### semiconductor_analysis/experiment_log/07_exp_0.3_lifecycle_alignment

| 文件 | 摘要 | 行数 | main | 标签 | 结论 |
|---|---|---|---|---|---|
| run_0.3_v3.py | run_0.3_v3.py — 实验 0.3: 产品生命周期数据提取与对齐  | 244 | × | normal | 唯一版本,建议保留 |

### semiconductor_analysis/experiment_log/08_exp_0.0.6_hierarchy_eligibility

| 文件 | 摘要 | 行数 | main | 标签 | 结论 |
|---|---|---|---|---|---|
| run_0.0.6.py | -*- coding: utf-8 -*- run_0.0.6.py — 实 | 408 | × | normal | 唯一版本,建议保留 |

### semiconductor_analysis/experiment_log/09_exp_1.0_hierarchy_granularity

| 文件 | 摘要 | 行数 | main | 标签 | 结论 |
|---|---|---|---|---|---|
| run_1.0_hierarchy_granularity.py | 实验 1.0: 预测层级与时间粒度对比（严格版，v1.4测试方案对齐） | 716 | √ | normal | 唯一版本,建议保留 |

### semiconductor_analysis/experiment_log/10_exp_0.0.7_corrected_hierarchy_eligibility

| 文件 | 摘要 | 行数 | main | 标签 | 结论 |
|---|---|---|---|---|---|
| run_0.0.7_corrected_hierarchy_eligibility.py | -*- coding: utf-8 -*- run_0.0.7_correc | 668 | √ | normal | 唯一版本,建议保留 |

### semiconductor_analysis/experiment_log/11_exp_1.1_intermittent_demand

| 文件 | 摘要 | 行数 | main | 标签 | 结论 |
|---|---|---|---|---|---|
| run_1.1_corrected.py | 实验 1.1 修正版: 完整执行覆盖率边界规则和方法池测试 | 396 | √ | normal | 唯一版本,建议保留 |
| run_1.1_full_corrected.py | 实验 1.1 完整修正版: 严格应用覆盖率边界规则 | 388 | √ | normal | 唯一版本,建议保留 |
| run_1.1_intermittent_demand.py | 实验 1.1: 间歇性需求方法评估 | 924 | √ | normal | 唯一版本,建议保留 |

### semiconductor_analysis/experiment_log/13_exp_1.2_window_optimization

| 文件 | 摘要 | 行数 | main | 标签 | 结论 |
|---|---|---|---|---|---|
| run_1.2_window_optimization.py | 实验 1.2: 移动平均窗口自适应优化 | 992 | √ | normal | 唯一版本,建议保留 |

### semiconductor_analysis/experiment_log/14_exp_1.3_lifecycle_calibration

| 文件 | 摘要 | 行数 | main | 标签 | 结论 |
|---|---|---|---|---|---|
| run_1.3_lifecycle_calibration.py | run_1.3_lifecycle_calibration.py — 实验  | 1267 | √ | normal | 唯一版本,建议保留 |

### semiconductor_analysis/experiment_log/15_exp_1.4_new_product_layering

| 文件 | 摘要 | 行数 | main | 标签 | 结论 |
|---|---|---|---|---|---|
| run_1.4_new_product_layering.py | 实验 1.4: 新品/老品分层预测初探 | 317 | √ | normal | 唯一版本,建议保留 |

### semiconductor_analysis/experiment_log/20_exp_2.1_hierarchical_reconciliation

| 文件 | 摘要 | 行数 | main | 标签 | 结论 |
|---|---|---|---|---|---|
| run_2.1_hierarchical_reconciliation.py | 实验 2.1: 分层调和——单产品线验证 | 550 | √ | normal | 唯一版本,建议保留 |

### semiconductor_analysis/experiment_log/21_exp_2.2_hierarchical_all_plines

| 文件 | 摘要 | 行数 | main | 标签 | 结论 |
|---|---|---|---|---|---|
| run_2.2_hierarchical_all_plines.py | 实验 2.2: 分层调和——全产品线扩展 | 530 | √ | normal | 唯一版本,建议保留 |

### semiconductor_analysis/experiment_log/22_exp_2.3_pit_factor_deepening

| 文件 | 摘要 | 行数 | main | 标签 | 结论 |
|---|---|---|---|---|---|
| run_2.3_pit_factor_deepening.py | 实验 2.3: 产品生命周期PIT代理因子深化——池化降维建模 | 378 | √ | normal | 唯一版本,建议保留 |

### semiconductor_analysis/experiment_log/23_phase2_redesign

| 文件 | 摘要 | 行数 | main | 标签 | 结论 |
|---|---|---|---|---|---|
| run_phase2_redesign.py | Phase 2 重新设计: 分层调和实验 | 296 | √ | normal | 唯一版本,建议保留 |

### semiconductor_analysis/experiment_log/24_phase2_final_validation

| 文件 | 摘要 | 行数 | main | 标签 | 结论 |
|---|---|---|---|---|---|
| run_phase2_final_validation.py | Phase 2 最终验证: 层级调和是否有效 | 500 | √ | normal | 唯一版本,建议保留 |

### semiconductor_analysis/experiment_log/25_phase3_ensemble

| 文件 | 摘要 | 行数 | main | 标签 | 结论 |
|---|---|---|---|---|---|
| run_phase3_ensemble.py | Phase 3: 组合优化与动态选择 | 484 | √ | normal | 唯一版本,建议保留 |

### semiconductor_analysis/experiment_log/26_phase4_final

| 文件 | 摘要 | 行数 | main | 标签 | 结论 |
|---|---|---|---|---|---|
| run_phase4_final.py | Phase 4: 最终验收 | 262 | √ | normal | 唯一版本,建议保留 |

### semiconductor_analysis/experiment_log/experiment_log_extra_quantile_prediction

| 文件 | 摘要 | 行数 | main | 标签 | 结论 |
|---|---|---|---|---|---|
| run_1.2_quantile_forecasting.py | 实验 1.2: 区间预测（Quantile Forecasting） | 842 | √ | normal | 唯一版本,建议保留 |

### semiconductor_analysis_before/src

| 文件 | 摘要 | 行数 | main | 标签 | 结论 |
|---|---|---|---|---|---|
| __init__.py | src/ — 高级分析模块包 | 15 | × | normal | 唯一版本,建议保留 |

### semiconductor_analysis_before/src/actions

| 文件 | 摘要 | 行数 | main | 标签 | 结论 |
|---|---|---|---|---|---|
| __init__.py | 行动建议模块（预留） | 1 | × | normal | 唯一版本,建议保留 |

### semiconductor_analysis_before/src/anomaly

| 文件 | 摘要 | 行数 | main | 标签 | 结论 |
|---|---|---|---|---|---|
| __init__.py | 异常检测模块（预留） | 1 | × | normal | 唯一版本,建议保留 |

### semiconductor_analysis_before/src/behavior

| 文件 | 摘要 | 行数 | main | 标签 | 结论 |
|---|---|---|---|---|---|
| __init__.py | 采购行为分析 | 2 | × | normal | 唯一版本,建议保留 |
| volatility.py | Task 5: 采购波动性/稳定性指标 (Volatility Metric | 173 | × | normal | 唯一版本,建议保留 |

### semiconductor_analysis_before/src/journey

| 文件 | 摘要 | 行数 | main | 标签 | 结论 |
|---|---|---|---|---|---|
| __init__.py | 客户旅程阶段模型 | 2 | × | normal | 唯一版本,建议保留 |
| stage_classifier.py | Task 1: 客户旅程阶段分类器 (Customer Journey St | 340 | × | normal | 唯一版本,建议保留 |

### semiconductor_analysis_before/src/profitability

| 文件 | 摘要 | 行数 | main | 标签 | 结论 |
|---|---|---|---|---|---|
| __init__.py | 利润分析 | 2 | × | normal | 唯一版本,建议保留 |
| true_profit_estimator.py | Task 6: 估算真实利润贡献度 (Estimated True Prof | 168 | × | normal | 唯一版本,建议保留 |

### semiconductor_analysis_before/test/templates

| 文件 | 摘要 | 行数 | main | 标签 | 结论 |
|---|---|---|---|---|---|
| __init__.py | 测试用例模板包 | 6 | × | normal | 唯一版本,建议保留 |
| test_case_template.py | 测试用例模板 | 109 | × | normal | 唯一版本,建议保留 |

### 产品生命周期评估

| 文件 | 摘要 | 行数 | main | 标签 | 结论 |
|---|---|---|---|---|---|
| run_v2.8.py | 产品生命周期量化评估工具 v2.8 | 3088 | √ | normal | 唯一版本,建议保留 |

### 产品生命周期评估/backup

| 文件 | 摘要 | 行数 | main | 标签 | 结论 |
|---|---|---|---|---|---|
| build_config.py | 构建新 config.xlsx：融合新旧参数，格式统一 | 322 | × | normal | 唯一版本,建议保留 |
| build_html.py | -*- coding: utf-8 -*- 读取JSON数据 | 563 | × | normal | 唯一版本,建议保留 |
| excel_helper.py | Excel辅助工具:基于openpyxl读写xlsx文件、按关键字更新单元格 | 96 | √ | normal | 唯一版本,建议保留 |
| generate_dashboard_v4.py | -*- coding: utf-8 -*- | 335 | √ | normal | 唯一版本,建议保留 |
| run.py | 产品生命周期量化评估工具 v2.6 | 1802 | √ | normal | 唯一版本,建议保留 |
| run_v2.7_增强版_20260510_before_fix.py | 产品生命周期量化评估工具 v2.8 | 2814 | √ | normal | 唯一版本,建议保留 |
| run_v2.7_增强版_backup_20260510.py | 产品生命周期量化评估工具 v2.7.1 春节调整版 | 2510 | √ | normal | 唯一版本,建议保留 |
| run_v2.7_增强版_before_20260510_141955.py | 产品生命周期量化评估工具 v2.8 | 2554 | √ | normal | 唯一版本,建议保留 |
| run_v2.8.py | 产品生命周期量化评估工具 v2.8 | 2800 | √ | normal | 唯一版本,建议保留 |
| 模型测试.py | 完整历史数据（5-6年）的模型对比测试 – 针对A类主力SKU | 203 | × | normal | 唯一版本,建议保留 |

### 产品生命周期评估/产品生命周期量化评估方案_v2.9

| 文件 | 摘要 | 行数 | main | 标签 | 结论 |
|---|---|---|---|---|---|
| generate_v4.py | generate_v4.py — 产品生命周期全景看板 v4 HTML 生成 | 643 | √ | normal | 唯一版本,建议保留 |
| run_v2.8.py | 产品生命周期量化评估工具 v2.8 | 3110 | √ | normal | 唯一版本,建议保留 |

### 工作文件

| 文件 | 摘要 | 行数 | main | 标签 | 结论 |
|---|---|---|---|---|---|
| eda_analysis.py | 智数分析专家团 - 数据科学工程师赛奇（Sage） | 229 | × | normal | 唯一版本,建议保留 |
| eda_analysis_v2.py | 智数分析专家团 - 数据科学工程师赛奇（Sage） | 430 | × | normal | 唯一版本,建议保留 |
| eda_analysis_v3.py | 智数分析专家团 - 数据科学工程师赛奇（Sage） | 438 | × | normal | 唯一版本,建议保留 |

### 工作文件/longtail_forecast

| 文件 | 摘要 | 行数 | main | 标签 | 结论 |
|---|---|---|---|---|---|
| generate_report.py | Generate the longtail customer quarter | 775 | × | normal | 唯一版本,建议保留 |
| run_longtail_forecast.py | 智数分析专家团 - 数据科学工程师赛奇（Sage） | 621 | √ | normal | 唯一版本,建议保留 |

### 工作文件/longtail_forecast/v2

| 文件 | 摘要 | 行数 | main | 标签 | 结论 |
|---|---|---|---|---|---|
| gen_dashboard.py | 读取回测摘要 读取预测总表 | 595 | × | normal | 唯一版本,建议保留 |
| run_full_forecast_v2.py | 全客户增强预测系统 v2 — 多方法×多维度×极致回测 | 1637 | × | normal | 唯一版本,建议保留 |

### 工作文件/longtail_forecast/v3

| 文件 | 摘要 | 行数 | main | 标签 | 结论 |
|---|---|---|---|---|---|
| generate_report.py | Generate comprehensive all-customer fo | 518 | × | normal | 唯一版本,建议保留 |
| run_full_forecast_v3.py | 全客户增强预测系统 v3 — 全客户口径 | 600+方法 | 双重优化 | 782 | × | normal | 唯一版本,建议保留 |

### 工作文件/semiconductor_analysis

| 文件 | 摘要 | 行数 | main | 标签 | 结论 |
|---|---|---|---|---|---|
| analysis1.py | -*- coding: utf-8 -*- | 97 | × | normal | 唯一版本,建议保留 |
| analysis2.py | -*- coding: utf-8 -*- | 148 | × | normal | 唯一版本,建议保留 |
| analysis3.py | -*- coding: utf-8 -*- | 112 | × | normal | 唯一版本,建议保留 |
| analysis4.py | -*- coding: utf-8 -*- | 127 | × | normal | 唯一版本,建议保留 |
| append_word_appendix.py | Word: 追加附件-销售产品清单,不动其他内容,保存为"分析+附件"版 | 143 | × | normal | 唯一版本,建议保留 |
| asp_check.py | -*- coding: utf-8 -*- | 48 | × | normal | 唯一版本,建议保留 |
| audit.py | -*- coding: utf-8 -*- | 84 | × | normal | 唯一版本,建议保留 |
| audit_pline.py | -*- coding: utf-8 -*- | 54 | × | normal | 唯一版本,建议保留 |
| bridge2.py | -*- coding: utf-8 -*- | 47 | × | normal | 唯一版本,建议保留 |
| bridge3.py | -*- coding: utf-8 -*- | 62 | × | normal | 唯一版本,建议保留 |
| deep_action.py | -*- coding: utf-8 -*- | 186 | × | normal | 唯一版本,建议保留 |
| deep_all.py | -*- coding: utf-8 -*- | 261 | × | normal | 唯一版本,建议保留 |
| deep_sales_products.py | -*- coding: utf-8 -*- | 52 | × | normal | 唯一版本,建议保留 |
| deep_zxkx.py | -*- coding: utf-8 -*- | 101 | × | normal | 唯一版本,建议保留 |
| diag.py | -*- coding: utf-8 -*- | 49 | × | normal | 唯一版本,建议保留 |
| fix_fonts.py | Word: 按字体方案统一设置所有文字,只改字体属性不动内容 | 147 | × | normal | 唯一版本,建议保留 |
| fix_header_repeat.py | Word: 所有表格首行设为跨页重复表头,只改格式不动内容 | 26 | × | normal | 唯一版本,建议保留 |
| fix_price.py | -*- coding: utf-8 -*- | 86 | × | normal | 唯一版本,建议保留 |
| fix_valign.py | Word: 所有表格单元格垂直居中 | 27 | × | normal | 唯一版本,建议保留 |
| fix_word_24.py | 只替换Word报告2.4段:老文本→方案A统一表,不动其他内容 | 163 | × | normal | 唯一版本,建议保留 |
| fix_word_75.py | Word: 7.5钩子vs产品差→判定表 | 110 | × | normal | 唯一版本,建议保留 |
| fix_word_bridge.py | 只替换Word报告里的毛利桥勾稽链文字→勾稽表,不动其他内容 | 168 | × | normal | 唯一版本,建议保留 |
| fix_word_ch9.py | Word: 第九章 销售引导卡片→统一表格 | 128 | × | normal | 唯一版本,建议保留 |
| fix_word_zxkx.py | Word: 8.4中兴康讯→四维度深度模块 | 130 | × | normal | 唯一版本,建议保留 |
| generate_v4.py | generate_v4.py — 产品生命周期全景看板 v4 HTML 生成 | 651 | √ | normal | 唯一版本,建议保留 |
| ka_list.py | -*- coding: utf-8 -*- | 40 | × | normal | 唯一版本,建议保留 |
| make_word.py | -*- coding: utf-8 -*- | 433 | × | normal | 唯一版本,建议保留 |
| peek.py | 临时调试脚本:快速打印Excel所有Sheet的名称、最大行列数及前3行数据 | 20 | × | temp | 临时脚本,建议归档不入流水线 |
| recompute_asp.py | -*- coding: utf-8 -*- | 106 | × | normal | 唯一版本,建议保留 |
| run2.py | -*- coding: utf-8 -*- | 7 | × | normal | 唯一版本,建议保留 |
| run3.py | -*- coding: utf-8 -*- | 7 | × | normal | 唯一版本,建议保留 |
| run4.py | -*- coding: utf-8 -*- | 7 | × | normal | 唯一版本,建议保留 |
| run_action.py | 临时入口脚本:通过subprocess调用deep_action.py并捕获 | 6 | × | temp | 临时脚本,建议归档不入流水线 |
| run_audit.py | 临时入口脚本:通过subprocess调用audit.py并捕获其返回码和s | 5 | × | temp | 临时脚本,建议归档不入流水线 |
| run_deep.py | 临时入口脚本:通过subprocess调用deep_all.py并捕获其st | 6 | × | temp | 临时脚本,建议归档不入流水线 |
| run_sp.py | 临时入口脚本:通过subprocess调用deep_sales_produc | 6 | × | temp | 临时脚本,建议归档不入流水线 |
| run_zxkx.py | 临时入口脚本:通过subprocess调用deep_zxkx.py并捕获其返 | 6 | × | temp | 临时脚本,建议归档不入流水线 |
| runall.py | -*- coding: utf-8 -*- | 7 | × | normal | 唯一版本,建议保留 |
| scout.py | -*- coding: utf-8 -*- | 46 | × | normal | 唯一版本,建议保留 |
| test.py | -*- coding: utf-8 -*- | 73 | × | normal | 唯一版本,建议保留 |
| verify.py | -*- coding: utf-8 -*- | 75 | × | normal | 唯一版本,建议保留 |
| verify_word.py | Check headings | 55 | × | normal | 唯一版本,建议保留 |

### 工作文件/semiconductor_analysis/b2b_v2/actions

| 文件 | 摘要 | 行数 | main | 标签 | 结论 |
|---|---|---|---|---|---|
| category_aptitude.py | 品类擅长分析 v4.15 — 每位销售在各产品线的能力指数 | 145 | × | normal | 唯一版本,建议保留 |
| negative_margin.py | 负毛利深度分析模块 | 239 | × | normal | 唯一版本,建议保留 |
| product_insights.py | 客户产品洞察模块 — 为6策略引擎提供产品级深度分析数据 | 386 | × | normal | 唯一版本,建议保留 |
| sales_profiling.py | 销售能力画像 v4.13 — 8维能力评分（业绩+能力双轮驱动） | 302 | × | normal | 唯一版本,建议保留 |

### 工作文件/semiconductor_analysis/customer_analysis

| 文件 | 摘要 | 行数 | main | 标签 | 结论 |
|---|---|---|---|---|---|
| period_analysis.py | 周期经营分析模块 v4.16 | 201 | × | normal | 唯一版本,建议保留 |
| rd_recommendation.py | 产品研发建议模块 v4.16 | 81 | × | normal | 唯一版本,建议保留 |

### 工作文件/semiconductor_analysis/dashboard

| 文件 | 摘要 | 行数 | main | 标签 | 结论 |
|---|---|---|---|---|---|
| _patch_dashboard.py | 就地修补 dashboard_a.html： | 48 | × | normal | 唯一版本,建议保留 |
| audit_alerts.py | 1. 审计告警数据 | 54 | × | normal | 唯一版本,建议保留 |
| audit_cats.py | 临时检查脚本:审计客户全景CSV中cc字段与cat_rev品类数量是否匹配, | 30 | × | temp | 临时脚本,建议归档不入流水线 |
| audit_cats2.py | 临时检查脚本:将品类数量矛盾审计结果和样例写入audit_output.tx | 36 | × | temp | 临时脚本,建议归档不入流水线 |
| audit_data.py | 1. Check Top5 for first 3 customers | 31 | × | normal | 唯一版本,建议保留 |
| audit_deep.py | 临时检查脚本:深度审计CETV和大华集团品类收入详情,检查cc与品类条数不匹 | 39 | × | temp | 临时脚本,建议归档不入流水线 |
| audit_final.py | === 1. Check new product count mismatc | 50 | × | normal | 唯一版本,建议保留 |
| audit_html.py | Extract embedded B_CUSTS | 38 | × | normal | 唯一版本,建议保留 |
| audit_new.py | 1. Check 新品标记 distribution | 48 | × | normal | 唯一版本,建议保留 |
| audit_rhythm.py | 临时检查脚本:审计采购节律字段(距上次采购天数/常规平均采购间隔/零采购月占 | 76 | × | temp | 临时脚本,建议归档不入流水线 |
| audit_small.py | 临时检查脚本:审计新品标记产品中金额小于1万元的小额记录及显示为0.0万的边 | 19 | × | temp | 临时脚本,建议归档不入流水线 |
| build_data.py | 数据预聚合脚本：读取 Gold 层 CSV → 生成 6 个轻量 JSON  | 288 | × | normal | 唯一版本,建议保留 |
| check_col.py | Check original Excel last column | 26 | × | normal | 唯一版本,建议保留 |
| check_cust.py | 临时检查脚本:从Excel财务数据提取KA客户的YTD收入利润并打印Top5 | 33 | × | temp | 临时脚本,建议归档不入流水线 |
| check_data.py | 临时检查脚本:检查b_custs.json中是否存在script标签、转义符 | 34 | × | temp | 临时脚本,建议归档不入流水线 |
| check_kpi.py | 1. Check 收入增长率 vs YoY同比增速 | 62 | × | normal | 唯一版本,建议保留 |
| check_kpi2.py | The KPI values are hardcoded in HTML - | 30 | × | normal | 唯一版本,建议保留 |
| check_names.py | 临时检查脚本:检查客户名称中是否含有单引号/双引号/反斜杠等非法字符 | 7 | × | temp | 临时脚本,建议归档不入流水线 |
| data_inventory.py | 审计 generate_dashboard.py 中所有数据源使用情况 | 89 | × | normal | 唯一版本,建议保留 |
| final_audit.py | 1. Verify silver YTD | 65 | × | normal | 唯一版本,建议保留 |
| final_check.py | 临时检查脚本:验证dashboard_a.html中KPI变量、占位符和核心 | 14 | × | temp | 临时脚本,建议归档不入流水线 |
| find_col.py | Find ALL columns with 品类 or 品线 Also pr | 9 | × | normal | 唯一版本,建议保留 |
| find_col2.py | 临时检查脚本:在Excel中查找含'品类'或'品线'关键字的列及其列索引位置 | 12 | × | temp | 临时脚本,建议归档不入流水线 |
| find_col3.py | Read ALL columns (no nrows limit) | 16 | × | normal | 唯一版本,建议保留 |
| find_col4.py | Check sheets Read sheet "总表" | 21 | × | normal | 唯一版本,建议保留 |
| find_col5.py | 临时检查脚本:遍历所有Sheet找出列数超过50的主数据表并列出其最后5列和 | 21 | × | temp | 临时脚本,建议归档不入流水线 |
| generate_dashboard.py | 看板生成器V8:从Gold CSV和Raw Excel读取数据,计算YTD/ | 1775 | × | normal | 唯一版本,建议保留 |
| verify_raw.py | Read raw "24-26" sheet | 52 | × | normal | 唯一版本,建议保留 |
| verify_syntax.py | Find SECOND script section (inline dat | 26 | × | normal | 唯一版本,建议保留 |
| verify_ytd.py | 临时检查脚本:验证silver月度表中2026年YTD收入利润汇总与各月明细 | 29 | × | temp | 临时脚本,建议归档不入流水线 |

### 工作文件/semiconductor_analysis/experiment_log/phase_0_baseline/exp_0.0.5_coverage_diagnosis

| 文件 | 摘要 | 行数 | main | 标签 | 结论 |
|---|---|---|---|---|---|
| run_0.0.5_v2.py | run_0.0.5_v2.py — 实验 0.0.5: 产品线覆盖与字段一致 | 230 | × | normal | 唯一版本,建议保留 |

### 工作文件/semiconductor_analysis/experiment_log/phase_0_baseline/exp_0.0_trivial_baselines

| 文件 | 摘要 | 行数 | main | 标签 | 结论 |
|---|---|---|---|---|---|
| run_0.0_trivial_baselines.py | run_0.0.py — 实验 0.0: 平凡基线建立 创建: 2026-0 | 156 | × | normal | 唯一版本,建议保留 |

### 工作文件/semiconductor_analysis/experiment_log/phase_0_baseline/exp_0.1.5_method_filter

| 文件 | 摘要 | 行数 | main | 标签 | 结论 |
|---|---|---|---|---|---|
| run_0.1.5_v2.py | run_0.1.5_v2.py — 实验 0.1.5: 方法预筛选（修订版） | 125 | × | normal | 唯一版本,建议保留 |

### 工作文件/semiconductor_analysis/experiment_log/phase_0_baseline/exp_0.2_baseline_lock

| 文件 | 摘要 | 行数 | main | 标签 | 结论 |
|---|---|---|---|---|---|
| run_0.2_baseline_lock.py | run_0.2.py — 实验 0.2: 基线回测锁定 创建: 2026-0 | 157 | × | normal | 唯一版本,建议保留 |

### 工作文件/semiconductor_analysis/experiment_log/phase_0_baseline/exp_0.3_lifecycle_alignment

| 文件 | 摘要 | 行数 | main | 标签 | 结论 |
|---|---|---|---|---|---|
| run_0.3_v3.py | run_0.3_v3.py — 实验 0.3: 产品生命周期数据提取与对齐  | 230 | × | normal | 唯一版本,建议保留 |

### 工作文件/semiconductor_analysis/output/test

| 文件 | 摘要 | 行数 | main | 标签 | 结论 |
|---|---|---|---|---|---|
| run_0.0.5_coverage_diagnosis.py | run_0.0.5.py — 实验 0.0.5: 产品线覆盖与字段一致性诊断 | 177 | × | normal | 唯一版本,建议保留 |
| run_0.0.5_v2.py | run_0.0.5_v2.py — 实验 0.0.5: 产品线覆盖与字段一致 | 230 | × | normal | 唯一版本,建议保留 |
| run_0.0_trivial_baselines.py | run_0.0.py — 实验 0.0: 平凡基线建立 创建: 2026-0 | 156 | × | normal | 唯一版本,建议保留 |
| run_0.1.5_method_filter.py | run_0.1.5.py — 实验 0.1.5: 方法预筛选 从552种候选 | 169 | × | normal | 唯一版本,建议保留 |
| run_0.1.5_v2.py | run_0.1.5_v2.py — 实验 0.1.5: 方法预筛选（修订版） | 125 | × | normal | 唯一版本,建议保留 |
| run_0.2_baseline_lock.py | run_0.2.py — 实验 0.2: 基线回测锁定 创建: 2026-0 | 157 | × | normal | 唯一版本,建议保留 |
| run_0.3_lifecycle.py | run_0.3.py — 实验 0.3: 产品生命周期数据提取与对齐 创建: | 240 | × | normal | 唯一版本,建议保留 |
| run_0.3_v2.py | run_0.3_v2.py — 实验 0.3: 产品生命周期数据提取与对齐  | 230 | × | normal | 唯一版本,建议保留 |
| run_0.3_v3.py | run_0.3_v3.py — 实验 0.3: 产品生命周期数据提取与对齐  | 230 | × | normal | 唯一版本,建议保留 |

### 工作文件/semiconductor_analysis/test_output

| 文件 | 摘要 | 行数 | main | 标签 | 结论 |
|---|---|---|---|---|---|
| check_data.py | Read ranking | 52 | × | normal | 唯一版本,建议保留 |

### 看板流水线

| 文件 | 摘要 | 行数 | main | 标签 | 结论 |
|---|---|---|---|---|---|
| run_chain.py | 看板流水线 · 一键编排器 | 193 | √ | normal | 唯一版本,建议保留 |

### 看板流水线/dashboard

| 文件 | 摘要 | 行数 | main | 标签 | 结论 |
|---|---|---|---|---|---|
| generate_dashboard.py | -*- coding: utf-8 -*- | 2073 | × | normal | 唯一版本,建议保留 |

### 看板流水线/processing

| 文件 | 摘要 | 行数 | main | 标签 | 结论 |
|---|---|---|---|---|---|
| run_all.py | 主管道编排脚本:按序执行silver数据清洗、product产品生命周期、c | 442 | √ | normal | 唯一版本,建议保留 |

### 看板流水线/processing/analysis

| 文件 | 摘要 | 行数 | main | 标签 | 结论 |
|---|---|---|---|---|---|
| __init__.py | P1-D: 分析核心模块 | 1 | × | normal | 唯一版本,建议保留 |
| b2b_adapters.py | B2B v2 模块适配器 — 实现 core.interfaces 的 Pr | 77 | × | normal | 唯一版本,建议保留 |
| c6_production_mapping.py | c6 production mapping function. | 86 | × | normal | 唯一版本,建议保留 |
| gold_builders.py | Gold 层辅助表构建器 | 148 | × | normal | 唯一版本,建议保留 |
| rfm_pi.py | RFM-π 评分模型（B2B 芯片行业适配版） | 130 | × | normal | 唯一版本,建议保留 |
| scoring.py | 客户评价体系评分模块（v2.0） — 与客户分析解耦版本 | 391 | × | normal | 唯一版本,建议保留 |

### 看板流水线/processing/analysis/pricing

| 文件 | 摘要 | 行数 | main | 标签 | 结论 |
|---|---|---|---|---|---|
| __init__.py | P1-D: 价格分析模块（从 shared/ 搬迁） | 1 | × | normal | 唯一版本,建议保留 |
| pricing_actions.py | 价格分析函数 — ASP趋势、弹性计算、价格偏离度、价格带分布 | 215 | × | normal | 唯一版本,建议保留 |
| pricing_bands.py | 价格分析函数 — ASP趋势、弹性计算、价格偏离度、价格带分布 | 139 | × | normal | 唯一版本,建议保留 |
| pricing_customer.py | 价格分析函数 — ASP趋势、弹性计算、价格偏离度、价格带分布 | 229 | × | normal | 唯一版本,建议保留 |
| pricing_insights.py | 价格分析函数 — ASP趋势、弹性计算、价格偏离度、价格带分布 | 137 | × | normal | 唯一版本,建议保留 |
| pricing_lifecycle.py | 价格分析函数 — ASP趋势、弹性计算、价格偏离度、价格带分布 | 291 | × | normal | 唯一版本,建议保留 |
| pricing_trends.py | 价格分析函数 — ASP趋势、弹性计算、价格偏离度、价格带分布 | 150 | × | normal | 唯一版本,建议保留 |

### 看板流水线/processing/b2b_v2

| 文件 | 摘要 | 行数 | main | 标签 | 结论 |
|---|---|---|---|---|---|
| __init__.py | src/ — 高级分析模块包 | 15 | × | normal | 唯一版本,建议保留 |

### 看板流水线/processing/b2b_v2/actions

| 文件 | 摘要 | 行数 | main | 标签 | 结论 |
|---|---|---|---|---|---|
| __init__.py | 行动建议模块 | 8 | × | normal | 唯一版本,建议保留 |
| category_aptitude.py | 品类擅长分析 v4.15 — 每位销售在各产品线的能力指数 | 145 | × | normal | 唯一版本,建议保留 |
| cross_sell.py | L3 交叉销售推荐 — 基于产品关联 + 库龄压力，推荐可推品种 | 236 | × | normal | 唯一版本,建议保留 |
| negative_margin.py | 负毛利深度分析模块 | 239 | × | normal | 唯一版本,建议保留 |
| product_insights.py | 客户产品洞察模块 — 为6策略引擎提供产品级深度分析数据 | 386 | × | normal | 唯一版本,建议保留 |
| rules_engine.py | 分层策略引擎 v4.3 — 数据验证修正版 | 971 | × | normal | 唯一版本,建议保留 |
| run.py | 行动建议汇总入口 — 串联 L1 告警 + 6策略引擎 + L3 交叉销售 | 53 | × | normal | 唯一版本,建议保留 |
| sales_profiling.py | 销售能力画像 v4.13 — 8维能力评分（业绩+能力双轮驱动） | 302 | × | normal | 唯一版本,建议保留 |

### 看板流水线/processing/b2b_v2/anomaly

| 文件 | 摘要 | 行数 | main | 标签 | 结论 |
|---|---|---|---|---|---|
| __init__.py | 异常检测模块 | 9 | × | normal | 唯一版本,建议保留 |
| inventory.py | 库龄数据层 — 加载、BOM拆分、估算降级、客户维度映射 | 466 | × | normal | 唯一版本,建议保留 |
| isolation_forest.py | Isolation Forest 兜底检测器 | 134 | × | normal | 唯一版本,建议保留 |
| rules.py | 规则检测器 — 6个独立异常检测器 | 336 | × | normal | 唯一版本,建议保留 |
| run.py | 异常检测汇总入口 — 串联所有检测器，返回合并异常日志 | 86 | × | normal | 唯一版本,建议保留 |

### 看板流水线/processing/b2b_v2/behavior

| 文件 | 摘要 | 行数 | main | 标签 | 结论 |
|---|---|---|---|---|---|
| __init__.py | 采购行为分析 | 2 | × | normal | 唯一版本,建议保留 |
| volatility.py | Task 5: 采购波动性/稳定性指标 (Volatility Metric | 181 | × | normal | 唯一版本,建议保留 |

### 看板流水线/processing/b2b_v2/journey

| 文件 | 摘要 | 行数 | main | 标签 | 结论 |
|---|---|---|---|---|---|
| __init__.py | 客户旅程阶段模型 | 2 | × | normal | 唯一版本,建议保留 |
| stage_classifier.py | Task 1: 客户旅程阶段分类器 (Customer Journey St | 390 | × | normal | 唯一版本,建议保留 |

### 看板流水线/processing/b2b_v2/profitability

| 文件 | 摘要 | 行数 | main | 标签 | 结论 |
|---|---|---|---|---|---|
| __init__.py | 利润分析 | 2 | × | normal | 唯一版本,建议保留 |
| true_profit_estimator.py | Task 6: 真实利润贡献度 (True Profit). | 75 | × | normal | 唯一版本,建议保留 |

### 看板流水线/processing/config

| 文件 | 摘要 | 行数 | main | 标签 | 结论 |
|---|---|---|---|---|---|
| __init__.py | 包初始化,导出settings模块中的项目根目录、数据目录、输出目录等全局配 | 15 | × | normal | 唯一版本,建议保留 |
| settings.py | 统一配置文件（v2.0 — 全面注释版） | 163 | × | normal | 唯一版本,建议保留 |
| settings_customer.py | ── 客户分析配置（分拆自 config/settings.py P1-A） | 801 | × | normal | 唯一版本,建议保留 |
| settings_product.py | ── 产品生命周期配置（分拆自 config/settings.py P1- | 213 | × | normal | 唯一版本,建议保留 |

### 看板流水线/processing/core

| 文件 | 摘要 | 行数 | main | 标签 | 结论 |
|---|---|---|---|---|---|
| __init__.py | core — 核心接口、配置与管线编排（P2-B 依赖注入） | 1 | × | normal | 唯一版本,建议保留 |
| config.py | 应用配置 — AppConfig 数据类 | 122 | × | normal | 唯一版本,建议保留 |
| interfaces.py | 半导体分析管线 — Protocol 接口定义（P2-B） | 108 | × | normal | 唯一版本,建议保留 |
| pipeline.py | Pipeline — 半导体分析管线依赖注入容器（P2-B） | 290 | × | normal | 唯一版本,建议保留 |

### 看板流水线/processing/cross_reference

| 文件 | 摘要 | 行数 | main | 标签 | 结论 |
|---|---|---|---|---|---|
| __init__.py | 导出跨参考模块的run函数,用于执行交叉引用分析 | 1 | × | normal | 唯一版本,建议保留 |
| run_cross_ref.py | 交叉关联层 | 176 | √ | normal | 唯一版本,建议保留 |

### 看板流水线/processing/customer_analysis

| 文件 | 摘要 | 行数 | main | 标签 | 结论 |
|---|---|---|---|---|---|
| __init__.py | 导出客户分析模块:客户RFM_PI评分模型、pipeline运行函数、画像计 | 10 | × | normal | 唯一版本,建议保留 |
| customer_master.py | 终端客户主数据加载与整合 | 360 | × | normal | 唯一版本,建议保留 |
| dimensions.py | 客户分析维度计算包装层 | 144 | × | normal | 唯一版本,建议保留 |
| gold.py | Gold 层表生成 | 464 | × | normal | 唯一版本,建议保留 |
| group_aggregation.py | 集团聚合模块 | 251 | × | normal | 唯一版本,建议保留 |
| models.py | 客户分析评分模型 | 10 | × | normal | 唯一版本,建议保留 |
| period_analysis.py | 周期经营分析模块 v4.16 | 201 | × | normal | 唯一版本,建议保留 |
| portrait.py | 客户全景画像计算 | 476 | × | normal | 唯一版本,建议保留 |
| price_deep_dive.py | 价格深度分析模块（Phase 3） | 583 | × | normal | 唯一版本,建议保留 |
| rd_recommendation.py | 产品研发建议模块 v4.16 | 81 | × | normal | 唯一版本,建议保留 |
| report.py | Excel 报告生成 + 统一 Gold 输出层 | 35 | × | normal | 唯一版本,建议保留 |
| run_kpi_daily.py | 准实时KPI通道 — 单独入口，独立于主管道运行 | 119 | √ | normal | 唯一版本,建议保留 |
| run_pipeline.py | 客户销售分析管道 — 编排层 | 222 | √ | normal | 唯一版本,建议保留 |
| scoring.py | 客户评价体系评分模块（v2.0） | 20 | × | normal | 唯一版本,建议保留 |
| silver.py | 客户分析 Silver 层构建 | 40 | × | normal | 唯一版本,建议保留 |
| trend_analysis.py | 趋势分析深化模块（Phase 4） | 308 | × | normal | 唯一版本,建议保留 |

### 看板流水线/processing/data_pipeline

| 文件 | 摘要 | 行数 | main | 标签 | 结论 |
|---|---|---|---|---|---|
| __init__.py | data_pipeline — Validation and orchest | 1 | × | normal | 唯一版本,建议保留 |
| aggregator.py | 数据聚合器 — DefaultAggregator | 18 | × | normal | 唯一版本,建议保留 |
| cleaner.py | 数据清洗器 — DefaultCleaner | 36 | × | normal | 唯一版本,建议保留 |
| loader.py | Excel/CSV 数据加载器 — ExcelDataLoader | 36 | × | normal | 唯一版本,建议保留 |
| validator.py | SimpleValidator — 轻量级数据验证器（纯 pandas，无额 | 166 | × | normal | 唯一版本,建议保留 |

### 看板流水线/processing/product_lifecycle

| 文件 | 摘要 | 行数 | main | 标签 | 结论 |
|---|---|---|---|---|---|
| __init__.py | 导出产品生命周期模块:运行分析函数、产品九宫格分类和策略备注生成 | 4 | × | normal | 唯一版本,建议保留 |
| nine_grid.py | 九宫格画像定位 — 产品生命周期专属 | 127 | × | normal | 唯一版本,建议保留 |
| notes.py | 特情说明生成 — 产品生命周期专属（v4.0） | 155 | × | normal | 唯一版本,建议保留 |
| profiling.py | 产品画像核心引擎 — v4.0: 4因子(毛利率斜率+增速衰减+自比健康度+ | 1188 | × | normal | 唯一版本,建议保留 |
| report.py | 产品生命周期报告生成（Excel 输出） | 392 | × | normal | 唯一版本,建议保留 |
| run.py | 产品生命周期分析 — v2.8解耦重写版 | 562 | √ | normal | 唯一版本,建议保留 |

### 看板流水线/processing/reports

| 文件 | 摘要 | 行数 | main | 标签 | 结论 |
|---|---|---|---|---|---|
| __init__.py | 报告输出模块 — CSV/Excel 写入 | 1 | × | normal | 唯一版本,建议保留 |
| gold_exporter.py | Gold 层表写入器 — CSV + 格式化 Excel 报告 | 306 | × | normal | 唯一版本,建议保留 |

### 看板流水线/processing/shared

| 文件 | 摘要 | 行数 | main | 标签 | 结论 |
|---|---|---|---|---|---|
| __init__.py | 导出共享工具模块:数据清洗、计算工具、分类器、风险评分、定价、预测和客户分析 | 54 | × | normal | 唯一版本,建议保留 |
| calc_utils.py | 共享计算工具:斜率/月龄/增长率/集中度/HHI指数/分位切割等统计分析函数 | 156 | × | normal | 唯一版本,建议保留 |
| classifiers.py | 分类函数 — 从v2.8提取的通用分类器 | 83 | × | normal | 唯一版本,建议保留 |
| customer_analysis.py | 客户分析函数 — 从v2.8提取的RFM分群和产品关联分析 | 179 | × | normal | 唯一版本,建议保留 |
| data_cleaning.py | 共享数据清洗管道 | 429 | × | normal | 唯一版本,建议保留 |
| forecasting.py | 预测函数 — 从v2.8提取的ETS预测和加权移动平均 | 253 | × | normal | 唯一版本,建议保留 |
| pricing.py | 价格分析函数 — 向后兼容重导出层 | 14 | × | normal | 唯一版本,建议保留 |
| risk_scoring.py | 风险评分函数 — v4.0 4因子模型 (优化版) | 373 | × | normal | 唯一版本,建议保留 |
| timing.py | Simple timing utilities for pipeline p | 79 | × | normal | 唯一版本,建议保留 |


## D. 存疑(同日内分叉,无法按时间判断)

- `test/batch_a_test.py`
