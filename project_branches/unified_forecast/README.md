# 统一预测系统(多版本存档)

> 本分支由代码考古重组自动生成(2026-07-27),原始文件均未移动/修改,此处为副本。
> 聚类与链路依据: `project_analysis/02_clusters.md`、`project_analysis/03_data_flow.md`

## 功能说明
整合预测入口的统一系统,读 quarterly_forecast 分支产出的 `预测方案总行版.csv` 做进一步汇总。
存在 5 个年代版本:**存疑,未能从静态分析确认最终版**——按修改时间与命名,建议先核对
`unified_forecast_v3.py`,backup_v1-v3 已移入 _archive/。

## 输入文件
- quarterly_forecast 分支的 `output/quarterly_forecast_customer/预测方案总行版.csv`

## 输出文件
- 统一预测结果 CSV(具体见脚本内配置)

## 运行方法
```bat
python unified_forecast_v3.py
```

也可以直接双击 `run.bat`(Windows)或执行 `bash run.sh`。

## 注意事项
- 与 semiconductor_analysis 根目录的 测试方案_多维度分层预测校准_v1.3.md 配套阅读
- 存疑:unified_forecast_system.py 与 unified_forecast_v3.py 关系不明(可能 v3 是重写版)

## 目录来源
- 复制文件数: 5
- 说明: 统一预测系统;依赖 quarterly_forecast 分支的输出CSV
