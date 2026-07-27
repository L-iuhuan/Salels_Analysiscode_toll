# EDA 与出货预测实验

> 本分支由代码考古重组自动生成(2026-07-27),原始文件均未移动/修改,此处为副本。
> 聚类与链路依据: `project_analysis/02_clusters.md`、`project_analysis/03_data_flow.md`

## 功能说明
对 5 月财务数据的探索性分析(EDA,三版迭代,保留终版 v3)与出货预测实验:
长尾产品预测(run_longtail_forecast.py)+ 全量出货预测 v3(run_full_forecast_v3.py)。

## 输入文件
- 财务分析-5月(6.3)(1).xlsx(**未随包**,见 data_说明.txt)

## 输出文件
- eda_results.txt / customer_agg.csv / customer_activity.csv / 预测结果 CSV

## 运行方法
```bat
python eda_analysis_v3.py
python run_full_forecast_v3.py
python run_longtail_forecast.py
```

也可以直接双击 `run.bat`(Windows)或执行 `bash run.sh`。

## 注意事项
- _archive/ 内有 v1/v2 旧迭代,仅供对照
- 脚本头部有数据路径变量,运行前先改路径
- 实验性代码,预测口径后被 quarterly_forecast 分支正规化

## 目录来源
- 复制文件数: 6
- 说明: EDA迭代终版v3 + 长尾/全量出货预测
