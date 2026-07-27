# 功能状态一览

> 单一真相源：所有功能实现状态只在此维护。
> 最后更新：2026-05-24 | P2-A 验证层 + P2-C report.py | Sprint 2 进行中

## 图例

| 标记 | 含义 |
|------|------|
| ✅ 已实现 | 代码已部署，生产可用 |
| 🔧 部分实现 | 核心逻辑存在，边界条件或配置未完整 |
| 📋 规划中 | 已在方案中设计，未编码 |
| ❌ 已废弃 | 曾经实现但因数据/策略原因移除 |

---

## 目录结构 (P1-D)

| 旧路径 | 新路径 | 状态 |
|--------|--------|------|
| `src/` | `b2b_v2/` | ✅ P1-D 已完成重命名 |
| `shared/pricing*.py` | `analysis/pricing/` | ✅ P1-D 已完成搬迁 |
| `shared/pricing.py` | 保留为向后兼容重导出层 | ✅ |
| `data_pipeline/` | 新增（验证层） | ✅ P2-A 已完成 |
| `shared/` 其他 | 原位保留（calc_utils/classifiers/forecasting等） | 📋 P2 待搬迁 |

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
| 配置拆分 (P1-A) | ✅ 已实现 | `config/settings*.py` | `settings.py`→shared(146行)+product(183行)+customer(760行), 零行为变更, 向后兼容 |

## 二、产品生命周期系统 (product_lifecycle/)

| 功能 | 状态 | 实现位置 | 说明 |
|------|------|---------|------|
| 新品判定（ERP优先+自动回退） | ✅ 已实现 | `profiling.py:line 161-173` | 近12月ERP标记优先 |
| 九宫格画像分类 | ✅ 已实现 | `profiling.py:line 795-941` | 销量动能×盈利健康交叉定位 |
| 4因子衰退风险评分(v4.0) | ✅ 已实现 | `profiling.py:_compute_risk_layer` | 毛利率斜率+增速衰减+自比健康度+订货量变化, 权重[0.100,0.600,0.200,0.100], 阈值[55,65,68] |
| 全量指标计算 (40+列) | ✅ 已实现 | `profiling.py:run_profiling` | 含ASP/弹性/CV/频次等 |
| ETS时序预测 | ✅ 已实现 | `profiling.py:line 583-633` | ETS+节假日调整+置信区间 |
| 价格弹性系数 | ✅ 已实现 | `pricing.py:calc_price_elasticity` | 百分比变化中位数+IQR过滤 |
| 比较参照组均值 | ✅ 已实现 | `profiling.py:line 659-765` | 多级兜底(品类→系列→全公司) |
| 历史画像追踪 | ✅ 已实现 | `run.py:run_analysis` | 过去12月滚动画像快照 |
| 退市产品检测 | ✅ 已实现 | `profiling.py:line 767-791` | 停售12月+月龄≥3月 |
| RFM客户分群 | ✅ 已实现 | `customer_analysis.py:rfm_customer_segmentation` | 传统R/F/M五分法 |
| 产品关联分析 | ✅ 已实现 | `customer_analysis.py:product_association_analysis` | 支持度/置信度/提升度 |
| 数据质量标记 | ✅ 已实现 | `profiling.py:line 943-960` | ZP/NM/SL/CV/AS/GC/ZS/NH |
| 参数从Excel加载 | 🔧 部分实现 | `run.py:load_config_from_xlsx` | 兼容v2.8格式，默认走settings.py |
| 产品小类参照组 | 🔧 部分实现 | `run.py:ref_priority` | 配置为 `型号_产品品类`，非真正产品小类 |
| Excel报告输出 (P2-C) | ✅ 已实现 | `report.py:write_excel_report` | 从 `run.py` 提取364行→独立 `report.py`，run.py从531行 |
| run.py瘦身 (P2-C) | ✅ 已实现 | `run.py` | 892行→531行（-40.4%），行为零变更 |

## 三、客户分析系统 (customer_analysis/)

| 功能 | 状态 | 实现位置 | 说明 |
|------|------|---------|------|
| 客户全景画像 (10维60+指标) | ✅ 已实现 | `portrait.py:calc_customer_portrait` | 拆分为9个维度辅助函数（_dim_base_info/_dim_momentum等） |
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
| 客户组合健康度 | ✅ 已实现 | `gold.py:_build_portfolio_health` | 各画像产品金额占比 |
| 客户×产品桥接 | ✅ 已实现 | `gold.py:_build_customer_product_bridge` | 引用产品生命周期画像 |
| 准实时KPI通道 | 🔧 部分实现 | `run_kpi_daily.py` | 独立路径，未接入主管道 |
| 品类接受度条件性输出 | ✅ 已实现 | `gold.py:generate_gold_tables` | P1-C: 纯数据生成，CSV写入移至 report.py |

| B2B v2: 集成至管道 | ✅ 已实现 | `gold.py:generate_gold_tables` | P1-C: 合并入客户全景字典，由 report.py 写 CSV |
| B2B v2: 单元测试 | ✅ 已实现 | `test/test_week1_modules.py` | 28项测试覆盖正常/边界/空数据/渠道分组 |
| 验证层单元测试 (P2-A) | ✅ 已实现 | `test/test_validator.py` | 28项测试覆盖4节点+通用检查+边界 |
| 终端客户主数据整合 | ✅ 已实现 | `customer_master.py` | `load_customer_master()` + `enrich_customer_portrait()` 三阶匹配 |
| 分析窗口过滤 | ✅ 已实现 | `silver.py:build_silver_layer` | 按CUSTOMER_ANALYSIS_WINDOW.start_date过滤 |
| 渠道类型推导（数据规则） | ✅ 已实现 | `portrait.py:_derive_channel` | 客户信息表缺失时从交易数据推导 |
| 客户属性映射补充 | ✅ 已实现 | `portrait.py:calc_customer_portrait` | 从交易数据回退映射所属区域/业务负责人 |
| ASP_跌幅%截断 | ✅ 已实现 | `portrait.py:_dim_asp_comparison` | 截断至-METRIC_CAPS.asp_decline_max_pct |
| 产品线列传递至Silver层 | ✅ 已实现 | `silver.py:build_silver_layer` | 产品一级分类带入customer_x_product |
| 客户主数据关键词映射优化 | ✅ 已实现 | `customer_master.py` | 审核状态/ERP编号/客户类别 |
| 真实利润率零收入修复 | ✅ 已实现 | `true_profit_estimator.py` | 营收为0时服务成本置零 |
| 5维度评分卡 | ✅ 已实现 | `scoring.py:calc_composite_scores` | 价值/增长/稳定/潜力/效率→综合S/A/B/C |
| 客户层级映射 (KA/AA/KM/MM) | ✅ 已实现 | `scoring.py:calc_customer_tier` | CRM客户类别优先→收入分箱回退 |
| 双轴行动矩阵 | ✅ 已实现 | `scoring.py:_classify_dual_axis` | 价值贡献×增长动能→明星/金牛/培育/瘦狗 |
| 机会评级 (维度法) | ✅ 已实现 | `scoring.py:calc_composite_scores` | 增长60%+潜力40%→极高/高/中/低 |
| 机会评级 (维度法) | ✅ 已实现 | `scoring.py:calc_composite_scores` | 增长60%+潜力40%→极高/高/中/低 |
| 风险评级 (维度法) | ✅ 已实现 | `scoring.py:calc_composite_scores` | (100-稳定)×70%+(100-效率)×30%→极高/高/中/低 |
| 模糊匹配优化 (rapidfuzz) | ✅ 已实现 | `customer_master.py:enrich_customer_portrait` | 模糊匹配率23.5%→61.3% |
| 集团聚合 | ✅ 已实现 | `group_aggregation.py` | 手工映射+自动前缀检测, 输出集团聚合.csv |

## 四、价格治理 (analysis/pricing/) — P1-B+P1-D 已完成

> P1-D: 从 `shared/pricing*.py` 搬迁至 `analysis/pricing/`。
> `shared/pricing.py` 保留为向后兼容重导出层。

| 新文件 | 行数 | 功能 |
|--------|------|------|
| `pricing_trends.py` | 150 | ASP趋势、价格弹性、订单频次 |
| `pricing_bands.py` | 135 | 价格带分布、跨客户价格离散度 |
| `pricing_customer.py` | 226 | 采购间隔、中断预警、集中度、品类接受度 |
| `pricing_lifecycle.py` | 282 | SKU/客户生命周期阶段、新品Cohort追踪 |
| `pricing_insights.py` | 137 | 机会信号、风险信号 |
| `pricing_actions.py` | 215 | 提价空间、降价策略、行动建议 |
| `pricing.py` | 14 | **重导出层** — `from shared.pricing import *` 保持向后兼容 |

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
| Excel报告生成 | ✅ 已实现 | `report.py:generate_reports` | 格式化+预警清单 |
| Gold层CSV输出 | ✅ 已实现 | `report.py:save_gold_tables` | P1-C: 统一输出入口，gold.py 只生成字典 |
| 数据验证层 (P2-A) | ✅ 已实现 | `data_pipeline/validator.py` | SimpleValidator 4节点验证 (V1-V4)，warn+continue |

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
| 因子3(订货波动性CV) | v4.0 | F3与衰退相关性弱，v4.0移除 |
| 因子6(ASP趋势) | v4.0 | F6与衰退相关性弱，v4.0移除 |
| c6因子 redistribute | v4.0 | 评估确认对无c6产品覆盖无益，不作 redistribution |
