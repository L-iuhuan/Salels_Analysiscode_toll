# 衰退风险优化(客户/产品衰退预警)

> 本分支由代码考古重组自动生成(2026-07-27),原始文件均未移动/修改,此处为副本。
> 聚类与链路依据: `project_analysis/02_clusters.md`、`project_analysis/03_data_flow.md`

## 功能说明
基于主流水线 silver/gold 产出的二次建模:phase1-5 因子挖掘与回测、phaseA 严重度分布与交叉验证、
phaseB1a 严重度回归、v3.1 校准与最终优化;generate_snapshot.py 产出产品风险快照 Excel。
样本数据(data/samples.pkl 3.1MB + samples.csv 4.9MB)与模型配置(models/*.json)已随包。

## 输入文件
- `data/samples.pkl` / `data/samples.csv`(已随包)
- 重新取数时需 main_pipeline 的 output/silver/*.csv 与 output/gold/gold_product_portrait.csv

## 输出文件
- `reports/产品风险快照表_增强版_{日期}.xlsx`
- `output/phaseA*/phaseB*` 图表与 md(产出目录已清空,运行后重新生成)

## 运行方法
```bat
python recession_risk_opt\pipeline.py
python recession_risk_opt\generate_snapshot.py
```

注意目录结构:脚本已按原始布局放入 `recession_risk_opt/` 子目录(脚本内部写死
`PROJECT_ROOT=上级目录`、读 `output/silver/`、写 `recession_risk_opt/output/`),
样例输入(silver 2 张 + gold 1 张)已放在分支根的 `output/` 下。
冒烟测试结果(2026-07-27):phaseB1a **通过**(产出 pkl/md/png 齐全);
但脚本自身的模型质量门槛未达标(R2=-0.07<0.30, Spearman=0.23<0.50),属业务口径问题,见
`recession_risk_opt/output/phaseB1a_severity_regression.md`。

也可以直接双击 `run.bat`(Windows)或执行 `bash run.sh`。

## 注意事项
- 存疑:`models/best_config.json` 在原项目中被引用但文件不存在于原位置(可能由 phase3 重新生成)
- 存疑:个别 f-string 输出路径(如 `{}/c6_factor_raw.csv`)静态分析未能解析,运行时自行确认
- backtest_results/ 仅保留测试报告 md,折数据 CSV 与图未复制(属产出物)

## 目录来源
- 复制文件数: 35
- 说明: 衰退风险:phase1-5 + phaseA/B + snapshot;样本数据已随包(samples.pkl 3MB)
