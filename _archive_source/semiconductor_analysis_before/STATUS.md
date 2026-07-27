# 功能状态一览

> 单一真相源：所有功能实现状态只在此维护。
> 最后更新：2026-05-22 | 批次A 已部署 | Week 1 完成

## 图例

| 标记 | 含义 |
|------|------|
| ✅ 已实现 | 代码已部署，生产可用 |
| 🔧 部分实现 | 核心逻辑存在，边界条件或配置未完整 |
| 📋 规划中 | 已在方案中设计，未编码 |
| ❌ 已废弃 | 曾经实现但因数据/策略原因移除 |

---

## 一、共享数据管道 (shared/)

| 功能 | 状态 | 实现位置 | 说明 |
|------|------|---------|------|
| ERP列名映射 | ✅ 已实现 | `data_cleaning.py:rename_erp_columns` | `ERP_COL_MAP` 定义映射字典 |
| 负销量过滤 | ✅ 已实现 | `data_cleaning.py:filter_negative_qty` | 剔除 qty < 0 记录 |
| 毛利率Winsorization | ✅ 已实现 | `data_cleaning.py:winsorize_margins` | 钳制 [-50%, 75%] |
| 样品单识别 | 🔧 部分实现 | `data_cleaning.py:identify_sample_orders` | Z分数法，未接入主管道 |
| 双通道月度聚合 | ✅ 已实现 | `data_cleaning.py:monthly_aggregate_double_pass` | 一次调用输出3张Silver表 |
| Silver层新品标记传播 | ✅ 已实现 | `data_cleaning.py:line 165-166` | 动态agg携带"新品标记"至product_monthly |
| Silver层CSV缓存 | ✅ 已实现 | `run_all.py:stage_silver` | 可跳过重算 (`SKIP_SILVER_IF_EXISTS`) |

## 二、产品生命周期系统 (product_lifecycle/)

| 功能 | 状态 | 实现位置 | 说明 |
|------|------|---------|------|
| 新品判定（ERP优先+自动回退） | ✅ 已实现 | `profiling.py:line 161-173` | 近12月ERP标记优先 |
| 九宫格画像分类 | ✅ 已实现 | `profiling.py:line 795-941` | 销量动能×盈利健康交叉定位 |
| 6因子衰退风险评分 | ✅ 已实现 | `profiling.py:line 838-938` | 实际为5因子(CM+HL已移除) |
| 全量指标计算 (40+列) | ✅ 已实现 | `profiling.py:run_profiling` | 含ASP/弹性/CV/频次等 |
| ETS时序预测 | ✅ 已实现 | `profiling.py:line 583-633` | ETS+节假日调整+置信区间 |
| 价格弹性系数 | ✅ 已实现 | `pricing.py:calc_price_elasticity` | 百分比变化中位数+IQR过滤 |
| 比较参照组均值 | ✅ 已实现 | `profiling.py:line 659-765` | 多级兜底(品类→系列→全公司) |
| 历史画像追踪 | ✅ 已实现 | `run.py:line 877-902` | 过去12月滚动画像快照 |
| 退市产品检测 | ✅ 已实现 | `profiling.py:line 767-791` | 停售12月+月龄≥3月 |
| RFM客户分群 | ✅ 已实现 | `customer_analysis.py:rfm_customer_segmentation` | 传统R/F/M五分法 |
| 产品关联分析 | ✅ 已实现 | `customer_analysis.py:product_association_analysis` | 支持度/置信度/提升度 |
| 数据质量标记 | ✅ 已实现 | `profiling.py:line 943-960` | ZP/NM/SL/CV/AS/GC/ZS/NH |
| 参数从Excel加载 | 🔧 部分实现 | `run.py:load_config_from_xlsx` | 兼容v2.8格式，默认走settings.py |
| 产品小类参照组 | 🔧 部分实现 | `run.py:ref_priority` | 配置为 `型号_产品品类`，非真正产品小类 |

## 三、客户分析系统 (customer_analysis/)

| 功能 | 状态 | 实现位置 | 说明 |
|------|------|---------|------|
| 客户全景画像 (10维60+指标) | ✅ 已实现 | `run_pipeline.py:calc_customer_portrait` | 含经营势能/产品覆盖/产品线分布 |
| RFM-π评分 | ✅ 已实现 | `models.py:score_rfm_pi` | R(30%)/F(20%)/M(30%)/π(20%) |
| RFM-π渠道隔离评分 | ✅ 已实现 | `models.py:score_rfm_pi` | 按渠道分组qcut + 渠道特定权重，<5客户回退为统一评分 |
| 机会评分 (5因子) | ✅ 已实现 | `models.py:score_opportunity` | Min-Max归一化→0-100分 |
| 风险评分 (5因子) | ✅ 已实现 | `models.py:score_risk` | Min-Max归一化→0-100分 |
| 采购健康度 (间隔/中断预警) | ✅ 已实现 | `pricing.py:calc_purchase_interval/churn_warning` | 倍数可配 |
| 产品集中度 | ✅ 已实现 | `pricing.py:calc_product_concentration` | Top5集中度+强依赖标记 |
| 品类接受度 | ✅ 已实现 | `pricing.py:calc_category_acceptance` | 依赖产品线列存在 |
| SKU生命周期状态机 | ✅ 已实现 | `pricing.py:calc_sku_lifecycle_stage` | 5种阶段+导入试销 |
| 客户生命周期阶段 | ✅ 已实现 | `pricing.py:calc_customer_lifecycle_stage` | 6种阶段+爬坡期参数化 |
| 新品Cohort追踪 | ✅ 已实现 | `pricing.py:calc_new_product_cohort` | ERP优先+自动回退 |
| 价格偏离度 | ✅ 已实现 | `pricing.py:calc_price_deviation` | vs市场中位价 |
| 价格带分布 | ✅ 已实现 | `pricing.py:calc_price_band_distribution` | 低价/中价/高价带 |
| 跨客户价格离散度 | ✅ 已实现 | `pricing.py:calc_cross_customer_price_dispersion` | CV法 |
| 提价空间分析 | ✅ 已实现 | `pricing.py:calc_markup_opportunity` | 3条件过滤 |
| 降价策略试算 | ✅ 已实现 | `pricing.py:calc_markdown_recommendation` | 4档弹性试算 |
| 行动建议生成 | ✅ 已实现 | `pricing.py:generate_action_suggestions` | 规则引擎 |
| 客户组合健康度 | ✅ 已实现 | `run_pipeline.py:line 342-371` | 各画像产品金额占比 |
| 客户×产品桥接 | ✅ 已实现 | `run_pipeline.py:line 327-339` | 引用产品生命周期画像 |
| 准实时KPI通道 | 🔧 部分实现 | `run_kpi_daily.py` | 独立路径，未接入主管道 |
| 品类接受度条件性输出 | ✅ 已实现 | `run_pipeline.py:line 386-390` | 缺品类列时不生成 |
| B2B v2: 客户旅程阶段 (Task 1) | ✅ 已实现 | `src/journey/stage_classifier.py` | 7阶段分类器, 优先级排序+成熟期排名修正 |
| B2B v2: 采购波动性指标 (Task 5) | ✅ 已实现 | `src/behavior/volatility.py` | CV/跌幅/零月比/R²+三档稳定性 |
| B2B v2: 估算真实利润 (Task 6) | ✅ 已实现 | `src/profitability/true_profit_estimator.py` | 4项服务成本扣除+利润等级 |
| B2B v2: 集成至管道 | ✅ 已实现 | `run_pipeline.py:generate_gold_tables` | 合并入客户全景.csv, 从settings.py读配置 |
| B2B v2: 单元测试 | ✅ 已实现 | `test/test_week1_modules.py` | 28项测试覆盖正常/边界/空数据/渠道分组 |

## 四、价格治理 (shared/pricing.py)

| 功能 | 状态 | 说明 |
|------|------|------|
| ASP趋势计算 | ✅ 已实现 | 最小二乘斜率 |
| 价格弹性系数 | ✅ 已实现 | 中位数+IQR过滤 |
| 订单频次趋势 | ✅ 已实现 | 近3月 vs 前9月 |
| 价格偏离度 | ✅ 已实现 | vs市场中位价 |
| 价格带分布 | ✅ 已实现 | P25/P75分界 |
| 价格离散度(CV) | ✅ 已实现 | CV>0.3标记混乱 |
| 采购间隔/中断预警 | ✅ 已实现 | 可配倍数 |
| 产品集中度 | ✅ 已实现 | TopN集中度 |
| 品类接受度 | ✅ 已实现 | 依赖品类列 |
| SKU生命周期状态机 | ✅ 已实现 | 5阶段 |
| 客户生命周期 | ✅ 已实现 | 6阶段+参数化 |
| 新品Cohort | ✅ 已实现 | ERP优先+回退 |
| 提价空间 | ✅ 已实现 | 3条件过滤 |
| 降价策略 | ✅ 已实现 | 弹性试算 |
| 行动建议 | ✅ 已实现 | 规则引擎 |

## 五、运行管道

| 功能 | 状态 | 实现位置 | 说明 |
|------|------|---------|------|
| 一键运行全部 | ✅ 已实现 | `run_all.py` | `--stage` / `--skip-*` / `--force-silver` |
| 单独运行产品 | ✅ 已实现 | `run_product.py` | 调用 `product_lifecycle.run.run()` |
| 单独运行客户 | ✅ 已实现 | `run_customer.py` | 调用 `customer_analysis.run_pipeline.run()` |
| 分阶段执行 | ✅ 已实现 | `run_all.py:stage_*` | silver/product/customer/kpi/cross_ref |
| Excel报告生成 | ✅ 已实现 | `run_pipeline.py:generate_reports` | 格式化+预警清单 |
| Gold层CSV输出 | ✅ 已实现 | `run_pipeline.py:generate_gold_tables` | 8张CSV表 |

## 六、交叉关联 (cross_reference/)

| 功能 | 状态 | 说明 |
|------|------|------|
| 交叉关联计算 | 🔧 部分实现 | `run_cross_ref.py` 存在但未在主文档分析范围 |

## 七、测试框架

| 功能 | 状态 | 说明 |
|------|------|------|
| 三阶段测试流程 | ✅ 已实现 | Phase 1-3 方法论已文档化 |
| 中间件pickle缓存 | ✅ 已实现 | `output/test_diag/_intermediate.pkl` |
| 诊断CSV输出 | ✅ 已实现 | `diag_cohort.csv` / `diag_customer_stages.csv` / `diag_product_portrait.csv` |
| 可视化图表 | ✅ 已实现 | 5张PNG 150dpi |
| 测试报告模板 | ✅ 已实现 | `BATCH_A_TEST_REPORT.md` |
| 结构化测试摘要 | ✅ 已实现 | `test_summary.json` |
| 独立测试脚本目录 | ✅ 已实现 | `test/batch_a_test.py` | Batch A回归测试已迁入 `test/` |
| pytest/CI集成 | 📋 规划中 | 当前为手动执行 |

## 八、已废弃功能

| 功能 | 废弃版本 | 原因 |
|------|---------|------|
| 回款信用评分 | v1.0 | 客户整体回款状况好，不分层无意义 |
| 因子2(客户集中度) | v2.9 | 依赖客户字段，移除后5因子 |
| 因子5(历史对照) | v2.9 | 49%产品标记HL无区分度，替换为自比健康度 |
