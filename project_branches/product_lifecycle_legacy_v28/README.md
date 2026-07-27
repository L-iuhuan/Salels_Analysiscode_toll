# 产品生命周期评估 v2.8(已淘汰,存档)

> 本分支由代码考古重组自动生成(2026-07-27),原始文件均未移动/修改,此处为副本。
> 聚类与链路依据: `project_analysis/02_clusters.md`、`project_analysis/03_data_flow.md`

## 功能说明
2026 年 4-5 月的独立旧项目:config.xlsx 驱动的产品生命周期九宫格评估,产出 Excel 报告 + HTML 看板。
**已被 main_pipeline 分支的 product_lifecycle/ 包取代**,本分支仅供追溯历史口径。
v2.9 迭代(风险模型改造)在子目录 产品生命周期量化评估方案_v2.9/。

## 输入文件
- `config.xlsx`(已随包,阈值/列映射配置)
- `所有的出货明细5.9.xlsx`(137MB,**未随包**,见 data_说明.txt)

## 输出文件
- output_v2.8_*.xlsx + 配套 HTML 看板(桑基图/画像分布/风险分布)

## 运行方法
```bat
python run_v2.8.py
```

也可以直接双击 `run.bat`(Windows)或执行 `bash run.sh`。

## 注意事项
- backup_code/ 收集了 backup/ 下的历史代码(v2.7 系列、build_html 等),outputs 未复制
- 根目录另有 426MB 同名 .rar 归档(按你的决定未解压、未复制)
- 新旧口径对照:新 product_lifecycle 的九宫格阈值见 main_pipeline/config/settings_product.py

## 目录来源
- 复制文件数: 38
- 说明: v2.8旧项目存档(config.xlsx驱动);v2.9迭代在子目录
