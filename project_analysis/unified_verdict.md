# unified 预测定版裁决(2026-07-27)

## 结论:定版 `unified_forecast_system.py`;`unified_forecast_v3.py` 因量级 bug 淘汰入 _archive

## 对比实验

同输入(①的 财务分析-5月(6.3).xlsx + ①quarterly 排行榜 6/11),两候选各自全量运行,
产物收割于 `project_analysis\unified_compare\{v3,system}\`,对比脚本 `_tools\unified_compare*.py`。

| 指标 | v3 | system | 说明 |
|---|---|---|---|
| 预测 horizon | F01-F04 四个季度桶(2026-06~2027-05) | 同 | 桶结构完全一致 |
| 12个月预测总额 | 2.79 亿 | **8.18 亿** | 实际 TTM(最近4季度)≈7.70 亿 |
| 占实际 TTM | **36%(失真)** | **106%(合理,含增长)** | 裁决性指标 |
| 产品 WAPE 中位 | 0.1152 | **0.0652** | system 更优 |
| 产品 WAPE≤0.2 占比 | 87.0% | 80.3% | 同一回测口径下 v3 略高,但其量级错误使该指标失去意义 |
| 列完整性 | 19 列 | **20 列(多 产品名称)** | system 更全 |
| 客户覆盖 | 42(KA/AA 40 + KM/MM 聚合桶) | **82(KM/MM 展开到客户)** | system 粒度更细 |
| 产品线覆盖 | 17(含"未分类") | 16(剔除"未分类") | 差异已知,剔除未分类属合理清洗 |
| 确定性复现 | — | **与 6/17 基线字节级一致** | system 可复现自身历史输出 |
| 两路径对账 | 产品=客户=2.79 亿 | 产品 8.179 亿 vs 客户 8.181 亿(-0.0%) | 各自内部一致 |

## v3 淘汰原因:月度/季度单位错误(证据链)

1. `unified_forecast_v3.py:623-624` 回测在**月度**序列上(`train_months=6, predict_months=3`);
2. L636-637 注释写 `# Generate 4-quarter forecast (12 months)`,但 `forecast_multi(trimmed, ..., horizon=4)`
   在月度序列上产出的是 **4 个月**的预测;
3. 4 个月度值被直接写入 4 个季度桶(F01-F04)→ 总量 = 4 个月销售 ≈ 全年 1/3;
4. 数值证据:总额比值 0.34、产品线级 0.15-0.58(通用电源管理 0.31)、40 个 KA/AA 客户全部 0.12-0.30、
   SKU 级 F01/上季度实际中位比值 v3=0.15 vs system=0.44(≈1/3 关系),全层级一致指向同一单位错误。

## system 注意事项(非阻塞)

- SKU 级结构迁移显著:legacy 3010xx 收缩、3350xx 新品放量(总量合理,系生命周期方法选取结果)。
- 客户路径 KM/MM 展开后行数 24336(v3 为 5952),下游消费方需知晓粒度差异。
- 置信度分布比 v3 更保守(中 5883/高 3452/低 2444),因 KM/MM 展开样本回测 WAPE 天然偏高。

## 产物位置

- 正式版:`forecasting\unified\unified_forecast_system.py`
- 淘汰归档:`forecasting\unified\_archive\unified_forecast_v3.py`(bug 记录于本文)
- 技术报告:`semiconductor_analysis\output\unified_forecast\预测系统技术报告.md`(6/17,随 system 产物)
- ① output\unified_forecast 当前为 system 于 7/27 的复跑产物(与 6/17 基线一致)
