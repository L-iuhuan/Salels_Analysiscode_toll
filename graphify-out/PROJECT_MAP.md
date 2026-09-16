# 项目结构导读地图（PROJECT_MAP）

> 生成于 2026-09-16，基于 graphify 知识图谱（16,906 节点/30,908 辗/1,224 社区）的全量扫描。
> **用途**：agent 了解本项目时的第一入口。先读此图，再查 graph.json / graphify query，可避免被归档副本误导。

## 一、一句话现状

拓尔微销售数据分析工作区 = **一个活跃主平台**（sales_analytics_platform）+ **一个活跃预测子系统**（forecasting）+ **三层历史沉淀**（占全部代码的 66%），全部子项目共享同一数据源（DSE 加密的《财务分析》Excel → silver 层）。

## 二、项目演化谱系（从归档命名考古）

```
semiconductor_analysis（根项目，早期）
  ├─ 工作文件/semiconductor_analysis（中期工作分支）
  ├─ project_branches/（平行分支群，各自迭代后废弃）
  │    ├─ main_pipeline（管道分支 → 演化为主平台前身）
  │    ├─ dashboard_chain（看板链分支）
  │    ├─ quarterly_forecast（季度预测分支）
  │    ├─ product_lifecycle_legacy_v28（生命周期 v2.8/v2.9）
  │    └─ eda_forecast / deep_dive_h1_report / recession_risk_opt（专题分支）
  └─ ▼ 汇聚演化 ▼
     sales_analytics_platform（当前主平台：批处理+看板+问答）
     forecasting（当前预测子系统：quarterly/unified）
qa_tool（本地问答）→ qa_tool_old（已被 qa_tool 取代）
```

## 三、区域权重与查询策略

| 区域 | 节点占比 | 性质 | agent 查询建议 |
|---|---|---|---|
| `_archive_source/` | **66%** | **搁置的方案库**（预测/因子/风险/生命周期等已完成工作，因专注看板流水线而搁置；vendored Chart.js ×4 除外） | 📚 **有高参考价值**：先查 `ARCHIVE_DOC_INDEX.md` 卡片目录锁定文档再精读；代码需评估活性（见第四节） |
| `sales_analytics_platform/` | 10% | **活跃主平台** | ✅ 代码片段首选 |
| `forecasting/` | 8% | **活跃预测子系统** | ✅ 预测逻辑首选 |
| `project_analysis/ docs/ 分析报告/` | 9% | 活跃文档（方案/台账/实验记录） | ✅ 设计意图与决策依据 |
| `_deprecated/ qa_tool_old/` | ~1% | 显式封存（qa_tool_old 含 .venv 噪声） | ❌ 禁止参考（宪法 S7） |

## 四、副本陷阱清单（同名实现 ×多份）

以下概念在归档与活跃区各有一份以上实现，**看 source_file 前缀辨别活性**：

- `Pipeline`（×4：main_pipeline 归档副本 ×3 + 平台活版 ×1）——God node 榜首全是归档副本
- Chart.js（×12 社区：quarterly_forecast、工作文件、归档各有一份 vendored 拷贝）
- `价格分析函数`（×37）：dashboard_chain 归档 vs 平台 `processing/` 活版
- `_derive_channel()`（×3 变体）：规则略有差异，平台版为准
- `with_retry()`（×65）、`_ensure_period_dtype()`（×30）：工具函数多副本
- 测试基础设施（×3：before/归档/工作文件）

## 五、数据源拓扑（一源多枝）

```
《财务分析-8月.xlsx》(DSE加密, 含冻结总表 2020-2026.05 + 活跃 24-26 表)
   └─ read_excel_auto / excel_com(COM解密)          ← 读取枢纽
        └─ silver_cleaned_rows.parquet               ← 数据契约落点
             ├─ sales_analytics_platform（看板/画像/生命周期）
             ├─ forecasting/quarterly（产品线预测）
             ├─ qa_tool（本地问答）
             └─ 月度分析报告流水线（分析报告/202608_*）
```

关键枢纽函数：`generate_gold_tables()`（中介中心性 0.020，桥接 14+ 社区）、`read_excel_auto()`（0.017）。

## 六、给 agent 的操作建议

**做预测类任务的三步检索流**：
1. **扫目录**：读 `graphify-out/ARCHIVE_DOC_INDEX.md`（343 篇归档文档卡片，预测相关 81 篇集中在「预测方法与实验」「实验日志与设计」「因子工程与调优」三块）→ 锁定 2-3 篇候选
2. **精读原文**：按卡片路径读全文（历史实验结论可直接复用，避免重做已证伪的方向）
3. **对照现状**：与活跃区 `project_analysis/预测能力提升规划备忘_20260910.md`（E1-E23 实验全记录）交叉核对，确认哪些历史结论已被新实验覆盖

**通用规则**：
- **找代码**：先限定 `sales_analytics_platform/` 或 `forecasting/` 前缀，再 graphify query / codegraph；命中归档代码时查第四节副本清单辨活性
- **懂设计**：读 `docs/` + `project_analysis/`（活跃文档区），决策依据在台账与备忘
- **问血缘**：AST 边（imports/calls）可信；语义边（INFERRED）需核对 source_file
- **图谱局限**：883 个归档文档节点与概念层的连接边大量悬空（未入图）——**归档文档检索以 ARCHIVE_DOC_INDEX 为准，不要依赖 graphify query 查归档文档内容**；5,758 条悬空边、若干归档 PDF 未入图

---
*数据来源：graphify-out/graph.json（2026-09-16 全量构建）；维护：代码大改后跑 `graphify . --update`（AST 增量免费，语义层有缓存）。*
