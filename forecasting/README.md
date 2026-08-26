# forecasting/ 目录警示（发版评审 2026-08-26）

## ⚠️ 本目录部分模块为死路径，运行必崩

以下模块硬编码指向**已删除**的 `semiconductor_analysis/output/...` 路径，
且 `sales_analytics_platform` 主流水线**零引用**——手动运行会立刻报错：

- `utils/final_forecast.py`（指向已删除的 semiconductor_analysis/output/）
- `utils/chart_data.py`（同上）
- `utils/generate_chart_html.py`（同上）
- `unified/unified_forecast_system.py`（依赖 quarterly/output/，同样悬空）

## 处置状态（等用户拍板，见台账未决#12）

- 在用 → 修路径
- 不用 → 按 S7 移入 `_deprecated/` 封存登记

**在拍板前请勿直接运行上述模块。**
