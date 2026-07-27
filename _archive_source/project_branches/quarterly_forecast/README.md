# 季度预测包(产品线 + 客户双维度)

> 本分支由代码考古重组自动生成(2026-07-27),原始文件均未移动/修改,此处为副本。
> 聚类与链路依据: `project_analysis/02_clusters.md`、`project_analysis/03_data_flow.md`

## 功能说明
直接读取原始出货明细 Excel,用 statsmodels ETS 等方法做季度级历史拟合与未来 4 季度预测,
含方法回测排行榜;产品线维度(run_quarterly_forecast.py)与客户维度(run_customer_forecast.py)双入口。
原包自带 README.txt / 使用说明.md / 实施方案文档。

## 输入文件
- 原始出货明细 Excel(**未随包**,见 data_说明.txt);`forecast_config*.json`(已随包)

## 输出文件
- `output/quarterly_forecast*/产品线|客户季度历史与预测.csv` 等 8 类 CSV
- 季度预测图表 HTML、含方法回测 xlsx
- `预测方案总行版.csv`(下游 unified_forecast 分支的输入)

## 运行方法
```bat
python run_quarterly_forecast.py
python run_customer_forecast.py
```

也可以直接双击 `run.bat`(Windows)或执行 `bash run.sh`。

## 注意事项
- 原包 output/ 已清空(产出物不复制);chartjs.min.js/chart_template.html 已随包
- 配置:forecast_config.default.json / forecast_config_customer.json

## 目录来源
- 复制文件数: 15
- 说明: 产品线+客户双维度季度预测(statsmodels ETS)
