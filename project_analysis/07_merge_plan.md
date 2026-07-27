# 07 项目合并与重组方案 v2(终稿,经多智能体辩论裁决)

> 原则:**不做代码重构,只做整理重组**。骨架选型经用户拍板、方案细节经 oracle 评审 +
> 三委员辩论 + council 综合裁决。本版为执行依据,取代 v1。

## 0. 决策记录

| # | 决策 | 结果 |
|---|---|---|
| D1 | 骨架选型 | **以③看板流水线便携结构为骨架**——用户确认③的代码与看板修改是最新且最终确认状态;dashboard 即为 V9(7/26),无需再做 C面等价选型验证 |
| D2 | unified 定版 | 同一输入跑候选版本对比后定版(指标见 §6) |
| D3 | 配置级修改 | 批准,逐处记录(原 3 处;辩论后增至 **4 处**,见 §4) |
| D4 | 归档策略 | 全部归档不删除(含 6 个 LeetCode 文件) |

## 1. 分支归纳(四层,终版)

| 层 | 项目 | 组成 |
|---|---|---|
| T1 生产 | **sales_analytics_platform**(主) | ③骨架 + ②核心模块覆盖 + ①文档/测试资产 |
| T1 生产 | **forecasting**(次) | ①quarterly(6/12 权威) + ①unified(定版后) + ①scripts 预测工具 + 实验归档 |
| T2 卫星 | recession_risk_opt | 已重组完成,冒烟通过;CSV 契约对接平台 |
| T3 归档 | deep_dive_h1_report、product_lifecycle_legacy_v28 | 只读保存 |
| T4 处置 | _orphans(49) + 源副本①②③④ + 散件 + rar | _archive_source/(不删除) |

## 2. 目标结构(主项目)

```
sales_analytics_platform\           (= ③骨架升级)
├─ run_chain.py            (编排器;增加 data 联接+联接自检,见§4修改#4)
├─ chain_config.json
├─ run.bat / run.sh        (调 run_chain;②的中文bat改写为调 run_chain 或归档)
├─ processing\             (分析代码 = ③的6/22基线 + ②的47个更新模块覆盖)
│  ├─ run_all.py           (②③完全相同,不动)
│  ├─ config\              (保留③settings.py的PKG_ROOT;pricing修复保留)
│  ├─ shared/ data_pipeline/ product_lifecycle/ customer_analysis/
│  │  cross_reference/ b2b_v2/ analysis/ reports/ core/  ← ②新版覆盖
│  └─ (optimizer 不迁入:全库无外部引用者,归档)
├─ dashboard\              (V9 最终版 + template.html,不动)
├─ test\                   (放【包根】,不放进processing——council P0裁决)
├─ conftest.py             (包根,源自①,注入 processing/ 入 sys.path + 排除batch_a_test)
├─ docs\                   (①README/AGENTS/PIPELINE_NODE_MAP + ③diff存档/S1S2报告)
├─ data\                   (用户放 xlsx + 部门-人员.md)
├─ output\                 (运行生成;processing/output 为指向此的目录联接)
├─ README.md  requirements.txt  test_smoke.py
forecasting\
├─ quarterly/   (①版,生产核心,--data/--sheet/--config CLI 干净)
├─ unified/     (定版后的最终版;3处路径改相对/CLI,见§4修改#1-3)
│  └─ _archive/ (其余4个版本)
├─ utils/       (chart_data.py, final_forecast.py)
├─ _archive/    (eda_v1-3 / longtail全族含generate_report / quantile实验 / optimizer)
└─ README.md  requirements.txt  test_smoke.py
```

**架构依据(council 共识)**:③的 junction+PKG_ROOT 是解决"前段产出落到单一 output/"的正确机制;
项目间仅 CSV 文件契约,无代码交叉依赖;②平铺式虽自然但用户已确认③为最终形态。

## 3. 原子覆盖组与顺序(council 裁决)

**铁律:按组原子覆盖,每步清 `__pycache__`,每步跑对应 stage 验证,失败整组回滚。**

| 序 | 原子组 | 验证 |
|---|---|---|
| 1 | config 三件套(保留③settings.py;__init__.py 若被覆盖需确认不导回旧路径) | `from config.settings import *; print(DATA_DIR)` |
| 2 | shared/ + data_pipeline/(silver 校验和涉此二,必须同换) | `--stage silver --force-silver` |
| 3 | analysis/(pricing 6件套与 shared/pricing.py 薄层同版) | import 检查 |
| 4 | product_lifecycle/ + cross_reference/ + reports/ | `--stage product`、`--stage cross_ref` |
| 5 | customer_analysis/ + b2b_v2/(LEFT JOIN 耦合,最复杂,最后) | `--stage customer` |
| 6 | core/ + run_all.py(确认②③相同) | `--pipeline` DI 模式 |
| 7 | test/ 落包根 + 根 conftest.py | `pytest test/ -v` 收集不崩 |

## 4. 配置级修改清单(4 处,逐处记录到 M1 执行日志)

| # | 文件 | 修改 | 说明 |
|---|---|---|---|
| 1 | forecasting/unified/*.py | `DATA_FILE` 绝对路径→相对/CLI | D3 原批准 |
| 2 | forecasting/unified/*.py | `SHEET_NAME="总表"` → 与所读数据文件实际 sheet 对齐(定版时确认) | D3 原批准 |
| 3 | forecasting/unified/*.py | `RANKING_FILE` 绝对路径→相对/CLI | D3 原批准 |
| 4 | sales_analytics_platform/run_chain.py | `ensure_output_junction()` **增加 data 联接**(processing/data→包根data)+ 运行前联接自检(失效则终止提示重建) | **council 三席一致判 P0 致命**:run_pipeline.py/run_kpi_daily.py/customer_master.py 的本地 DATA_DIR 回退逻辑当前指向空目录,仅靠显式 --data 掩盖。此修改超出原 D3 的 3 处,**需你确认追加** |

> 另知悉(非修改项):`customer_master.py` 的 CRM 主数据加载函数在全库无调用者,
> ②③均静默关闭——属共同缺失而非合并回归,验证基线比对时不会因此产生差异。
> `generate_v4.py`(V8的C面外部报告生成器)被 V9 内置 C面取代,归档不迁入。

## 5. 结果一致性验证协议 v2(M3,council 加强版)

**前置(全部强制)**:
- 记录 `python --version` / pandas 版本,基线重跑与合并后重跑必须同环境
- 验证用输入**显式 `--data` 指定同一 xlsx**(②入口取 listdir[0]、③入口取 mtime 最新,不指定会选到不同文件)
- 删除 output/silver/ 并全程 `--force-silver`(防缓存假通过)
- junction 自检通过

**比对项**:
1. silver 4 张(**含 silver_cleaned_rows.csv**)+ gold N 张:列名集合一致;按主键排序后哈希;数值列和容差 ≤1e-6
2. 客户粒度抽样 100 个(S/A/B/C 覆盖):综合价值分/风险评级/生命周期/双轴分类 逐行比对
3. 产品粒度抽样 50 个:当前画像/综合风险等级/毛利率趋势斜率 逐行比对
4. output/report 的 Excel 报告:sheet 名、行列数、关键单元格抽检
5. 看板 dashboard_a.html:canonical JSON 比对(排除时间戳/绝对路径/耗时字段;浮点统一精度;容忍条目顺序不确定性——③docs 有成熟方法)
6. 预测输出:预测方法排行榜.csv 按 (产品线,方法,评分) triplet 集合比对

## 6. unified 定版方案(M2 内,council 指标)

同一输入分别跑 v3 与 system 两候选,按优先级判定:
- **P0 WAPE**(加权绝对百分比误差,回测窗口)
- **P0 覆盖率**(可预测客户数/产品线数)
- **P1 输出列完整性**(销售额/量/成本/毛利/毛利率,精度一致)
- **P1 零预测客户处理**合理性
- **P2 与 quarterly triplet 一致性**
定版后按 §4 #1-3 改路径;建议同时统一为 CLI 参数模式(与 quarterly 风格一致)。其余 4 版入 _archive。

## 7. 执行计划 M0–M5

- **M0 冻结**:哈希清单已备(00_file_inventory.csv);建 _archive_source/
- **M1 平台合并**:③拷为 sales_analytics_platform → 按§3七组原子覆盖 → §4修改#4 → test/落包根+根conftest → docs合并 → 入口统一(中文bat改写为调run_chain或归档,逐条记录)
- **M2 预测合并**:quarterly 换①版 → unified 跑对比定版+3处路径修改 → utils/_archive 归位(补 longtail generate_report 等漏件)
- **M3 验证**:按§5全项执行(需你在 data/ 放入 xlsx 配合;看板 --skip-processing 快速比对)
- **M4 归档**:①②③④+散件+orphans → _archive_source/;generate_v4.py、build_data.py、audit临时脚本随源归档;rar 维持登记
- **M5 Git 化**:git init + .gitignore(data/、output/、*.xlsx、__pycache__) + 首次提交 + 月度工作流 README

## 8. 静默风险登记(验证时知悉,非阻断)

1. dashboard V9 硬编码 sheet_name="24-26"(③既有,换数据文件需确认 sheet 名)
2. customer_master CRM 整合两版均静默关闭(见§4注)
3. junction 在拷贝/git clone 后失效 → 已用§4修改#4的自检覆盖
4. ③骨架的 config 缓存校验和只哈希 settings.py+data_cleaning.py,覆盖其他模块不触发 silver 失效 → 验证协议已强制 --force-silver 覆盖此盲点
