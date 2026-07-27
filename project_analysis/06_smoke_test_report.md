# 06 冒烟测试报告

> 策略(经用户确认):生成 + 有条件执行。样例数据齐备且 <50MB 的分支实际执行;
> 其余分支生成 test_smoke.py 并标注未执行原因,补数据后可直接 `python test_smoke.py`。

## 执行结果总览

| 分支 | 状态 | 说明 |
|---|---|---|
| recession_risk_opt | ✅ **已执行,通过** | phaseB1a 完整跑通:phaseB1a_results.pkl(7133行)+ 3 PNG + 1 MD |
| main_pipeline | ⏭ 未执行(缺数据) | 需财务分析 xlsx(219MB,未随包);补齐后自动跑 silver 阶段并校验 4 张 CSV |
| dashboard_chain | ⏭ 未执行(缺数据) | data/ 下无 xlsx |
| deep_dive_h1_report | ⏭ 未执行(硬编码路径) | 需先批量替换 C:/Users/45091/Desktop 路径 |
| eda_forecast | ⏭ 未执行(缺数据+需改路径) | 216MB xlsx 未随包,脚本头部路径变量需修改 |
| quarterly_forecast | ⏭ 未执行(缺数据) | 需原始出货明细 Excel |
| unified_forecast | ⏭ 未执行(依赖上游) | 需先运行 quarterly_forecast 分支 |
| product_lifecycle_legacy_v28 | ⏭ 未执行(缺数据) | 需 137MB 出货明细 xlsx |

## 已执行详情:recession_risk_opt

- 运行: `python recession_risk_opt/phaseB1a_severity_regression.py`(分支根目录)
- 结构修复: 脚本写死 `PROJECT_ROOT=上级的上级`、读 `output/silver/`、写 `recession_risk_opt/output/`,
  已将脚本移入 `recession_risk_opt/` 子目录、样例输入置于分支根 `output/`,与原始布局一致
- 样例输入(从 ① output/ 复制的小文件): silver_product_monthly.csv(2.3MB)、
  silver_customer_x_product.csv(10.4MB)、gold_product_portrait.csv(0.5MB)、data/samples.pkl(3.1MB)
- 产出校验: pkl 存在且 7133 行 ✓;phaseB1a_*.png × 3 ✓;phaseB1a_severity_regression.md ✓
- **业务发现(非测试失败)**: 脚本内部质量门槛未达标 — OOF R2=-0.0715(门槛 0.30)、
  Spearman=0.2321(门槛 0.50),特征 decline_depth 权重 13.4% 远低于目标 75%。
  该模型在当前数据上预测力不足,建议使用前重新评估口径(已在分支 README 标注)。

## 修复过程记录(供复核)

1. test_smoke.py 打印子进程 stderr 时 GBK 控制台编码崩溃 → 模板加 stdout/stderr reconfigure(utf-8, replace)
2. phaseB1a FileNotFoundError → 发现脚本路径假设(须位于 <根>/recession_risk_opt/ 下)→ 重组分支结构
