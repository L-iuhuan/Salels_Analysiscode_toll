# forecasting(预测系统)

> 由预测族多版本合并而成(2026-07-27)。与销售分析平台(sales_analytics_platform)相互独立,
> 仅通过 CSV 文件契约衔接。原始多版本散件已归档于 _archive_source/。

## 结构

```
quarterly/    季度预测(生产核心)——产品线维度 run_quarterly_forecast.py + 客户维度
              run_customer_forecast.py,statsmodels 多种方法回测选优。
              干净的 CLI: --data/--sheet/--config/--output,直接读原始出货明细 Excel。
unified/      统一预测——读 quarterly 的"预测方案总排行.csv"做统一汇总。
              （定版进行中: v3(75KB)与 system(66KB)两候选,待同输入跑对比后保留其一,
              另一候选与 backup_v1-3 一并入 _archive/。）
utils/        预测辅助工具(chart_data.py / final_forecast.py / generate_chart_html.py,
              读平台 silver_cleaned_rows.csv)。
_archive/     历史草稿:eda_analysis v1-3、longtail_forecast 全族(含 generate_report)、
              quantile_prediction 实验、optimizer 子系统(全库无引用)。
```

## 运行方法

```bat
cd quarterly
python run_quarterly_forecast.py --data "数据文件.xlsx"     :: 产品线维度
python run_customer_forecast.py                             :: 客户维度(配置: forecast_config_customer.json)
cd ..\unified
python unified_forecast_v3.py                               :: 定版后为准(需先跑 quarterly)
```

## ⚠️ 死路径警示（发版评审 2026-08-26 新增）

以下模块硬编码指向**已删除**的 `semiconductor_analysis/output/...` 路径，
且 `sales_analytics_platform` 主流水线**零引用**——手动运行会立刻报错：

- `utils/final_forecast.py`（指向已删除的 semiconductor_analysis/output/）
- `utils/chart_data.py`（同上）
- `utils/generate_chart_html.py`（同上）
- `unified/unified_forecast_system.py`（依赖 quarterly/output/ 悬空产物）

**处置状态（等用户拍板，见台账未决#12）**：在用 → 修路径；不用 → 按 S7 移入 `_deprecated/` 封存登记。
**拍板前请勿直接运行上述四个模块。** quarterly/ 为生产核心不受影响。

## 注意事项

- quarterly 的 output/ 未入库(属产出物);原始基线输出仍在 _archive_source/semiconductor_analysis/quarterly_forecast_package/output/
- unified 系列的 DATA_FILE/SHEET_NAME/RANKING_FILE 硬编码绝对路径,定版时按批准口径(配置级修正#1-3)改为相对/CLI,逐处记录到 project_analysis/
- 平台→预测数据衔接:utils/ 工具读 sales_analytics_platform/output/silver/silver_cleaned_rows.csv
