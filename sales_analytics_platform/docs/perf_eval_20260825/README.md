# 性能评估与优化 · 总览（2026-08-25）

> 本分支 `perf/20260825-speedup` 汇总 2026-08-25 的全链路性能评估、优化改动、测试工具与验证文档。
> **master 未受任何影响**；本分支内容是否合入，请在主力开发机审查 `git diff master..perf/20260825-speedup` 后再评估。

---

## 1. 这是什么

对 `sales_analytics_platform`（前段数据处理 + 后段看板）做的一次完整性能评估与优化，
共三个批次，全部改动带 `[批次⑤]/[批次⑥]/[批次⑦]` 注释标记：

| 批次 | 内容 | 文档 |
|---|---|---|
| ⑤ | 看板循环过滤→groupby 预分组（P1）+ 输出路径统一（缺陷A）+ pandas category 崩溃修复（缺陷B） | [批次⑤_P1看板性能优化与缺陷修复_20260825.md](../批次⑤_P1看板性能优化与缺陷修复_20260825.md) |
| ⑥ | ETS 预测多进程并行（P3）+ gold 子模块向量化（P4）+ 节假日比率缓存（P5）+ Excel 导出优化（P2）+ 看板残留循环 | [批次⑥_全链路性能优化_20260825.md](../批次⑥_全链路性能优化_20260825.md) |
| ⑦ | 两份 Excel 报告加开关（**默认关闭**）+ 提价机会只输出有效行（用户拍板） | [批次⑦_Excel开关与提价机会过滤_20260825.md](../批次⑦_Excel开关与提价机会过滤_20260825.md) |

## 2. 性能结果（真实数据：财务分析-7月，199,681 行 / 3,196 客户 / 824 产品）

| 阶段 | 优化前（7月报告基线） | 三批之后 |
|---|---|---|
| 前段全链（silver→…→cross_ref） | ~500s | **129s** |
| 后段看板 | — | **52.6s** |
| **端到端** | **560s** | **~182s（-68%）** |

## 3. 等价性验证（全部通过）

- 合成数据同规模 A/B（同一 silver 来源、同一输入，HEAD vs 优化后）：
  gold 28/28 CSV、silver 4/4 CSV **字节级一致**；两份 Excel 报告 26+7 sheet **逐格一致**；
  看板 46/46 数据变量一致。
- 真实数据：全链 + 看板 exit=0，审计全过；gold 29/29 CSV 与过滤前一致
  （唯一差异 = 批次⑦ 预期的提价机会过滤，505/505 行与原子集字节一致）；看板 46/46 一致。

## 4. tools/ — 复现与验证工具

| 脚本 | 用途 |
|---|---|
| `gen_synthetic_data.py` | 生成与生产同规模的合成 ERP 数据（191,725 行/3,142 客户/818 产品），用于无真实数据时回归 |
| `compare_outputs.py` | 两个 output 目录的 CSV 逐字节/排序后内容比对（黄金回归用） |
| `compare_dashboard.py` | 两个 dashboard_a.html 的 46 个数据变量规范化 JSON 比对 |
| `compare_xlsx.py` | 两份 xlsx 报告逐 sheet 逐格内容比对（二进制因 zip 时间戳不可直接比） |
| `prof_by_file.py` / `prof_funcs.py` / `prof_top.py` | cProfile 结果按文件/按项目函数/按 tottime 聚合归因 |

复现流程：clone 本分支 → `pip install -r requirements.txt` → 生成或放入数据 →
`python processing/run_all.py --data <数据.xlsx>` → `python dashboard/generate_dashboard.py --no-cache` →
用 compare_* 与基线产物对比。

## 5. 关键教训（合入前必读）

1. **数字逐位回归是硬门槛**：本仓库所有优化都按"输出零变化"验证；object 列中的 Python float
   不能按列 dtype 降级处理（Excel 写入器首版因此出错，详见批次⑥文档第三节.4）。
2. **silver 来源会影响产物（既有问题，未修）**：内存构建（object dtype）与 parquet 重载
  （category dtype）的 silver 产出不同 gold 结果（categorical groupby 默认 observed=False
  叉积：提价机会 8 万行↔263 万行）。生产环境 = category 行为。批次⑦ 的过滤只是止血，
  建议后续统一口径（`observed=True` 需业务确认）。
3. **pandas 版本**：`requirements.txt` 已锁 `<2.3.2`（2.3.2+ category 算术崩溃；
  portrait.py / pricing_actions.py 已加防御）。
4. **基线必须保鲜**：回归对照的基线产物要用与当前完全相同的代码路径生成，
  陈旧基线会造成假阳性/假阴性（本次亲自踩过，详见批次⑥文档第二节）。
5. **Excel 报告默认已关闭**（批次⑦）：需要时在 `config/settings.py` 将
  `EXCEL_REPORT` 对应键改 `True`。

## 6. 本分支不包含（.gitignore 已挡）

真实/合成数据文件（*.xlsx）、output 产物、*.prof、运行日志（仅供本地审计，
位于原测试机 `C:\Users\17986\AppData\Local\Temp\opencode\Salels_Analysiscode_toll`，
含 `_baseline_local/`、`_ref_cat/`、`_ref_real/` 黄金参照，需要时可打包索取）。

## 7. 合入建议

1. 主力机 `git fetch && git diff master..perf/20260825-speedup --stat` 总览；
2. 按批次文档逐个 review（⑤→⑥→⑦，每批可独立合入）；
3. 合入后用真实数据跑一次 `scripts/golden_diff.py` + 本目录 compare_* 工具终验；
4. 批次⑦ 改变了默认行为（不生成 Excel + 提价机会过滤），合入前请团队知会一声。
