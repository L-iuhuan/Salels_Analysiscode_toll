# 05 分支提取报告

| 分支 | 复制文件数 | requirements | 说明 |
|---|---|---|---|
| project_branches/main_pipeline/ | 152 | 已存在(源自原始项目),未覆盖 | 主流水线:silver→product→customer→kpi→cross_ref |
| project_branches/dashboard_chain/ | 95 | 已存在(源自原始项目),未覆盖 | 看板便携包:processing→generate_dashboard→dashboard_a.html |
| project_branches/deep_dive_h1_report/ | 35 | 生成 4 个依赖 | H1报告链:deep_*→md→make_word→docx;含大量硬编码桌面路径 |
| project_branches/eda_forecast/ | 6 | 生成 5 个依赖 | EDA迭代终版v3 + 长尾/全量出货预测 |
| project_branches/recession_risk_opt/ | 35 | 生成 7 个依赖 | 衰退风险:phase1-5 + phaseA/B + snapshot;样本数据已随包(samples.pkl 3MB) |
| project_branches/quarterly_forecast/ | 15 | 生成 3 个依赖 | 产品线+客户双维度季度预测(statsmodels ETS) |
| project_branches/unified_forecast/ | 5 | 生成 4 个依赖 | 统一预测系统;依赖 quarterly_forecast 分支的输出CSV |
| project_branches/product_lifecycle_legacy_v28/ | 38 | 生成 10 个依赖 | v2.8旧项目存档(config.xlsx驱动);v2.9迭代在子目录 |
| project_branches/_orphans/ | 49 | 不需要 | 孤儿收容:temp/junk/debug/uncertain 四类 |

## 未找到文件

第二轮修正后无缺失。
