# 客户分析系统 — 全面审查测试报告

**日期**: 2026-05-23
**数据源**: 所有的出货明细5.9.xlsx (337,525行清洗后)
**运行模式**: 完整五阶段管道 (silver → product → customer → kpi → cross_ref), 19个Gold表

---

## 1. 测试概要

| 项目 | 结果 |
|------|------|
| 管道退出码 | 0 (成功) |
| 执行阶段 | 5/5 (全部通过) |
| 总运行时间 | ~5分 |
| 阻塞性错误 | 无 |
| 预期warning | statsmodels ETS收敛警告 (高波动客户), CSV类型混合警告 |

---

## 2. 各阶段输出统计

### 2.1 Silver层

| 表 | 行数 | 说明 |
|---|------|------|
| cleaned_rows | 337,525 | 清洗后行级数据 |
| customer_monthly | 8,612 | 每客户每月聚合 |
| product_monthly | 21,453 | 每产品每月聚合 |
| customer_x_product | 94,609 | 每客户×产品×月聚合, **含产品一级分类** |

### 2.2 产品生命周期

| 指标 | 值 |
|------|-----|
| 产品总数 | 919 |
| 有效分析产品 | 794 |
| 新品观察 | 111 |
| 常规/稳定产品 | 633 |
| 预警/衰退产品 | 256 |
| 高风险(>50分) | 178 |

### 2.3 客户分析

| 指标 | 值 |
|------|-----|
| 客户总数 | 310 |
| CRM匹配率 | ~60%+ (含fuzzy) |
| **渠道类型覆盖率** | **310/310 (100%)** ← 从0%修复 |
| 渠道分布 | 299代理 / 11直供 |
| 集团覆盖 | 27/310 (8.7%, 6个集团) |
| ETS预测客户 | ~200 (历史≥12月) |

### 2.4 Gold层输出 (19个文件)

| 文件 | 大小 | 类型 | 状态 |
|------|------|------|------|
| 客户全景.csv | 325 KB | 核心画像 | ✅ |
| 客户产品桥接.csv | 14.7 MB | 关联明细 | ✅ |
| 客户组合健康度.csv | 33.8 KB | 组合分析 | ✅ |
| 客户月度趋势.csv | 1 MB | Phase 4 趋势 | ✅ |
| 品类迁移.csv | 275 KB | Phase 4 迁移 | ✅ 之前缺失 |
| 品类接受度.csv | 29.5 KB | Phase 4 品类 | ✅ 之前缺失 |
| 客户预测.csv | 51 KB | Phase 4 预测 | ✅ |
| 价格离散度.csv | 140 KB | Phase 3 价格 | ✅ |
| 渠道价格对比.csv | 16 KB | Phase 3 价格 | ✅ 之前缺失 |
| 业务员定价偏离.csv | 1.2 KB | Phase 3 价格 | ✅ |
| 市场细分价格.csv | 0.9 KB | Phase 3 价格 | ✅ |
| 跨客户价格差异.csv | 96 KB | Phase 3 价格 | ✅ |
| 提价机会.csv | 383 KB | 定价建议 | ✅ |
| 降价策略试算.csv | 164 KB | 定价建议 | ✅ |
| 集团聚合.csv | 1.7 KB | 集团聚合 | ✅ |
| 客户组合健康度.csv | 87 KB | 交叉关联 | ✅ |
| gold_kpi_daily.csv | 679 KB | KPI通道 | ✅ |
| gold_product_portrait.csv | 526 KB | 产品画像 | ✅ |
| SKU生命周期.csv | 22 KB | 产品 | ✅ |

---

## 3. 已修复问题清单

### Sprint 1-3 修复 (会话1)

| # | 问题 | 文件 | 修复类型 |
|---|------|------|---------|
| 1 | 重复导入 `CUSTOMER_TIER_MAP` (行281-282) | `customer_master.py` | Bug修复 |
| 2 | 评分回退阈值与settings不一致 (旧值S≥80等) | `scoring.py` | Bug修复 |
| 3 | `calc_slope()` 参数名不匹配 (thr→min_pts) | `trend_analysis.py` | Bug修复 |
| 4 | `calc_slope()` 返回float非tuple导致解包错误 | `trend_analysis.py` | Bug修复 |
| 5 | `pred_int` 返回dict非ndarray导致KeyError | `trend_analysis.py` | Bug修复 |
| 6 | `model_info` 缺少'mape'键 | `trend_analysis.py` | Bug修复 |
| 7 | KeyError '代理商/直供名称' (列已被ERP_COL_MAP重命名) | `run_pipeline.py` | Bug修复 |
| 8 | UnboundLocalError 'customers' (变量使用前未定义) | `portrait.py` | Bug修复 |
| 9 | PermissionError ~$ temp文件 | `data_cleaning.py` | Bug修复 |
| 10 | 渠道类型100%未知 (推导逻辑方向反转) | `portrait.py` | 功能修复 |
| 11 | 评分分布集中在C档 (非活跃客户默认50→25) | `scoring.py` | 参数调优 |
| 12 | 评分阈值S≥80/A≥60/B≥40/C<0 → S≥36/A≥30/B≥26/C<26 | `settings.py` | 参数调优 |
| 13 | 双轴矩阵固定50分界 → 活跃客户中位数相对分位 | `scoring.py` | 参数调优 |
| 14 | 增长动能维度中位仅8.5 (新增6月短窗口回退) | `portrait.py` | 功能增强 |
| 15 | 效率维度零区分度 (移除物流成本率/订单处理成本率) | `settings.py` | 功能增强 |
| 16 | CRM字段映射: 全角括号vs半角括号 | `customer_master.py` | Bug修复 |
| 17 | CRM字段映射: 缺失"拓尔销售"字段 | `customer_master.py` | 功能增强 |
| 18 | `agg()` 中None值导致TypeError | `price_deep_dive.py` | Bug修复 |
| 19 | ETS预测NaN→int转换错误 | `shared/forecasting.py` | Bug修复 |
| 20 | Excel NaN写入错误 | `trend_analysis.py` | Bug修复 |

### 会话2修复 (本次)

| # | 问题 | 文件 | 修复类型 | 说明 |
|---|------|------|---------|------|
| 21 | **渠道类型100%未知(根因)**: `_dim_base_info()`中`cust_info`回退DataFrame含所有客户ID，使渠道推导函数从未被调用 | `portrait.py` | Bug修复 | `cust_info`回退含所有客户→`row["渠道类型"]=info.get("渠道类型","未知")`始终返回"未知"→`_derive_channel()`从未执行 |
| 22 | **run_all.py管道渠道类型仍然未知**: `skip_silver=True`时`raw_data=None`→渠道推导无原始数据 | `run_pipeline.py` | Bug修复 | 当加载缓存的Silver层时，补充从源Excel读取渠道推导所需原始列 |
| 23 | **run_all.py stage_silver缺失产品线列传递**: `customer_x_product`无`产品一级分类`→品类迁移/品类接受度无法生成 | `run_all.py` | Bug修复 | `monthly_aggregate_double_pass`后缺少将`产品一级分类`合并到CXPR的步骤(已在`silver.py:build_silver_layer()`中存在但`run_all.py`的`stage_silver()`中没有) |
| 24 | **客户层级收入分箱回退逻辑错误**: `calc_customer_tier()`使用"近12月收入"(我方销售额)反推客户规模，KA客户采购额低时会错误分入低档。且`.any()`条件导致回退从未执行 | `scoring.py` | Bug修复 | 移除收入分箱回退。原因: 我方销售额≠客户自身总营收。CRM未匹配直接标"未分类"，待CRM数据补充 |

---

## 4. 参数化改进清单

| # | 参数 | 原位置 | 新位置 | 说明 |
|---|------|--------|--------|------|
| 1 | 反向指标列表 (5个) | `scoring.py`硬编码 | `settings.py:SCORE_REVERSE_INDICATORS` | 新增 |
| 2 | 生命周期→评分映射 | `scoring.py`硬编码 | `settings.py:SCORE_LIFECYCLE_MAP` | 新增 |
| 3 | 稳定性→评分映射 | `scoring.py`硬编码 | `settings.py:SCORE_STABILITY_MAP` | 新增 |
| 4 | 客户层级→评分映射 | `scoring.py`硬编码 | `settings.py:SCORE_TIER_SCORE_MAP` | 新增 |
| 5 | 非活跃默认分(25) | `scoring.py`硬编码 | `settings.py:SCORE_INACTIVE_DEFAULT` | 新增 |
| 6 | 机会/风险混合权重 | `scoring.py`硬编码 | `settings.py:SCORE_OPPORTUNITY/RISK_BLEND_WEIGHTS` | 新增 |
| 7 | 采购中断预警真值 | `scoring.py`硬编码 | `settings.py:CHURN_WARNING_TRUE_VALUES` | 新增 |
| 8 | MA窗口大小(min_pts) | `trend_analysis.py`硬编码 | `settings.py:TREND_MA_WINDOWS` | 新增 |
| 9 | 斜率方向阈值(±0.02) | `trend_analysis.py`硬编码 | `settings.py:TREND_SLOPE_THRESHOLDS` | 新增 |
| 10 | 品类迁移min_share | `trend_analysis.py`参数默认值 | `settings.py:TREND_CATEGORY_MIGRATION` | 新增 |
| 11 | 预测月数/min_history | `trend_analysis.py`参数默认值 | `settings.py:TREND_FORECAST` | 新增 |
| 12 | 价格CV阈值(0.3/0.15) | `price_deep_dive.py`硬编码 | `settings.py:PRICE_DISPERSION_THRESHOLDS` | 新增 |
| 13 | 价格偏离标记阈值(±10%) | `price_deep_dive.py`硬编码 | `settings.py:PRICE_DEVIATION_THRESHOLDS` | 新增 |
| 14 | 最少客户数(2) | `price_deep_dive.py`参数默认值 | `settings.py:PRICE_ANALYSIS_MIN_CUSTOMERS` | 新增 |
| 15 | 集团活跃/休眠阶段列表 | `group_aggregation.py`硬编码 | `settings.py:GROUP_LIFECYCLE_ACTIVE/DORMANT_STAGES` | 新增 |
| 16 | 集团风险阈值 | `group_aggregation.py`硬编码 | `settings.py:GROUP_RISK_THRESHOLDS` | 新增 |
| 17 | 客户分析窗口(12/24/6月) | `portrait.py`硬编码 | `settings.py:CUSTOMER_ANALYSIS_WINDOW` | 已有(之前未使用) |

---

## 5. 回退方案总览

详见 [docs/fallback_logic.md](docs/fallback_logic.md)，共19项回退方案:

| 优先级 | 回退项 | 当前触发率 | 状态 |
|--------|--------|-----------|------|
| 🔴 高 | CRM匹配(4) | 34.9%未匹配 | 通过fuzzy匹配部分补偿 |
| 🔴 高 | 集团识别(5) | 88.4%未覆盖 | 手工映射为主，自动检测为辅 |
| 🟡 中 | 客户层级(2) | CRM匹配失败→"未分类"(收入分箱已移除) | 无回退，需补充CRM数据 |
| 🟡 中 | 业务员列检测(15) | 正常(21人) | 正常运作 |
| 🟢 低 | 渠道类型(1) | **0%未知** ← 已修复 | 三级降级有效: CRM→交易推导→默认 |
| 🟢 低 | 收入增长率(3) | 短窗口待统计 | 正常运作 |
| 🟢 低 | 其他13项 | 正常/不触发 | 已全部实现 |

---

## 6. 边界验证结果

| 边界场景 | 测试方式 | 结果 |
|---------|---------|------|
| 渠道类型全部未知 | 推导逻辑修正后测试 | ✅ **100%覆盖** (299代理/11直供) |
| CRM回退DataFrame含所有客户 | `_dim_base_info()`增加CRM→交易推导降级判断 | ✅ |
| skip_silver=True时raw_data缺失 | `run_pipeline.py`补充源文件读取 | ✅ |
| run_all.py stage_silver缺产品线列 | 增加产品线列传递 (`silver.py`同类逻辑已存在) | ✅ |
| ETS预测全部NaN | forecasting.py NaN保护 | ✅ 安全返回0 |
| Excel写入NaN/INF | trend_analysis.py safe_round | ✅ 写入None |
| scoring分类字段缺失 | if col存在检查 | ✅ 跳过指标 |
| price_deep_dive品类列缺失 | agg_dict条件构建 | ✅ 不崩溃 |
| 非活跃客户评分虚高 | 默认50→25调优 | ✅ S级从4.8%调整至7.9% |
| agg()中None值 | 重构为条件agg_dict | ✅ 修复 |
| groupby后无数据 | 空DataFrame检查 | ✅ 返回空 |

---

## 7. 验证结论与建议

### 合理判定
1. **评分分布**: S(7.9%)/A(20.1%)/B(23.8%)/C(48.1%) — 分布合理，压缩中间区域是数据本身的特征
2. **渠道类型**: 三级降级策略有效，CRM + 交易推导覆盖全部客户 (299代理/11直供)
3. **趋势分析**: 月趋势/品类迁移/ETS预测均已正常生成
4. **价格分析**: 跨客户价格差异/渠道对比/业务员偏离/市场细分价格全部正常输出

### 数据可靠性说明
1. **ESTIMATED_COST参数**: 可靠性低(固定估算)，已停用效率维度的成本指标
2. **价格弹性-1.0**: 固定值，需后续实证估计替换
3. **CRM匹配率**: 仍有约120客户无终端主数据，影响客户层级/区域/负责人准确性
4. **集团覆盖率8.7%**: 手工映射仅6个集团，需业务提供更完整的集团-子公司关系

### 改进建议（待数据补充后）

| 建议 | 优先级 | 预期收益 |
|------|--------|---------|
| 降低CRM fuzzy阈值至85% | 高 | 新增~20客户匹配 |
| 从CRM代理商账号扩展集团关系 | 高 | 集团覆盖率可提升至30%+ |
| 补充终端客户主数据(渠道/层级) | 高 | 客户属性完整性提升 |
| 接入真实成本数据(物流/仓储) | 中 | 效率运营维度可恢复真实指标 |
| 价格弹性实证估计(OLS log-log) | 中 | 定价建议准确性提升 |
| 增长动能增加YoY同比指标 | 低 | 减少季节性干扰 |

---

## 8. 文件变更清单

| 文件 | 变更类型 | 变更内容 |
|------|---------|---------|
| `config/settings.py` | 重写+扩展 | 全面参数注释+新增17组参数 |
| `customer_analysis/scoring.py` | 修改 | 参数化硬编码值，导入新增settings |
| `customer_analysis/portrait.py` | 修改 | 窗口参数化，变量名修复，**渠道类型三级降级修复**(CRM→交易推导→默认) |
| `customer_analysis/trend_analysis.py` | 修改 | MA/斜率/预测参数化，NaN安全处理 |
| `customer_analysis/price_deep_dive.py` | 修改 | CV/偏离阈值参数化，agg bug修复 |
| `customer_analysis/gold.py` | 修改 | 默认值注释说明 |
| `customer_analysis/group_aggregation.py` | 修改 | 生命周期阶段/风险阈值参数化 |
| `customer_analysis/customer_master.py` | 修改 | 重复导入修复 |
| `shared/forecasting.py` | 修改 | NaN预测值安全处理 |
| `customer_analysis/run_pipeline.py` | 修改 | 原始数据提取逻辑修正, **skip_silver路径补充渠道推导原始数据** |
| `run_all.py` | 修改 | **stage_silver增加产品线列传递**(品类迁移/品类接受度依赖) |
| `customer_analysis/scoring.py` | 修改 | **移除客户层级收入分箱回退**(错误地用我方采购额反推客户规模) |
| `docs/fallback_logic.md` | 新增+修改 | 19项回退方案完整文档; **客户层级文档修正**(移除收入分箱) |
| `docs/test_report.md` | 新增+更新 | 全面审查测试报告 |
