# 项目宪法（PROJECT CHARTER）

> 版本：v1.0 | 日期：2026-08-18 | 来源：council 多模型对抗审查裁决（alpha/gamma 有效，beta 失效）
> 适用范围：本仓库全部施工批次（⓪→④b）。**违反红线即阻塞，不得合入；违反强规须记录例外原因。**

---

## 一、红线（违反即阻塞，4 条）

| # | 条文 | 检查方式 |
|---|---|---|
| R1 | **`[STAGE n/total]` 与 `[n/m]` 子阶段输出协议不得改动**——格式、位置、层级关系保持原样（Tauri 壳 kanban-runner 前端步骤条/进度条依赖） | 跑 run_chain.py，解析 stdout 验证协议格式不变 |
| R2 | **数据与产出文件不入仓库**——`data/`、`output/`、`*.xlsx`、`*.csv`、`*.html`、`*.parquet`、`*.duckdb` 一律不提交；唯一例外是 baseline 指标摘要 JSON | `git ls-files` 中无数据/产出文件命中 |
| R3 | **输入变化必须触发重算，不得静默复用旧缓存**——指纹 = 源 Excel（路径+大小+mtime+SHA256）+ `settings*.py` 拼接哈希 + 代码指纹（git HEAD） | 复制 Excel 改一行金额再跑，断言指纹更新且 Silver 重新生成；改 settings_customer 阈值，断言 Gold 重新生成 |
| R4 | **任何代码/配置变更后必须通过 golden-diff 回归**——数值字段容差 1e-6，计数/字符串/日期字段严格相等；意外漂移 = 阻塞 | `scripts/golden_diff.py` 报告零意外漂移 |

## 二、强规（必须遵守，例外须记录，6 条）

| # | 条文 | 检查方式 |
|---|---|---|
| S1 | **列引用按语义名匹配，禁止列索引硬编码**——禁止 `raw_all_cols[66]`、`iloc[:,4]` 之类写法；列名优先级规则入配置 | `grep "raw_all_cols\[[0-9]"` 无命中；打乱 Excel 列顺序断言输出不变 |
| S2 | **年份、sheet 名、周期标识必须从数据动态推导**——禁止硬编码 `2024/2025/2026`、`24-26`、`25h1/25h2/26h1`；一律由 `DATA_SHEET_NAME` / `_latest_period` 推导 | `grep -R "202[4-9]"` 在 dashboard/ processing/ 业务逻辑中无命中；用 2027 年数据跑通看板 |
| S3 | **清洗口径全链路唯一**——`build_silver_layer()` 是唯一 Silver 构建入口；链式运行与单模块独立运行必须产出一致结果 | 分别用 run_chain 与单跑 run_pipeline 跑同一月数据，关键合计差异 < 0.01% |
| S4 | **阶段失败必须非零退出并阻断下游**——任一 stage 缺关键产物，`run_chain.py` 返回非 0，禁止继续生成看板 | 破坏性测试：删必要列，断言退出码 ≠ 0 且 dashboard_a.html 未更新 |
| S5 | **看板只消费预聚合数据**（批次③起生效）——`--dashboard-only` 模式下对 `data/*.xlsx` 读取次数必须为 0 | 文件访问审计：`--dashboard-only` 运行期间无 `data/*.xlsx` 读取 |
| S6 | **文件放置纪律**——工程文档入 `project_analysis\`，平台文档入 `sales_analytics_platform\`；产出文件不散落根目录；每批开工打 `pre-batch-N` tag、验收通过打 `batch-N-done` tag 并推送 | 每批验收时检查根目录无新增散件；`git tag` 有对应记录 |
| S7 | **废弃文件不直接删除**——一律移入 `_deprecated\`（保留原相对路径）并在 `_deprecated\README.md` 登记表记录（原路径/日期/原因/决策人）；`_deprecated\` 内文件**禁止后续开发参考、引用、复制、import**；物理删除须"确认不可逆废弃"后单独 commit | grep 代码无 `_deprecated` 引用；登记表与实际文件一致 |
| S8 | **等价性验证必须用生产数据路径做 before/after 对拍**——重构/向量化的对拍输入必须经 `load_silver_table`（生产 dtype 语义：categorical/float32/observed=False）加载；禁止用 read_csv 默认推断的临时数据做对拍输入（批次②.5 曾因此漏过 6 处漂移，被 golden_diff 门禁拦截） | 对拍脚本注明输入来源；抽查 dtype 与生产一致 |

## 三、建议（默认遵守，可不阻塞，5 条）

| # | 条文 | 检查方式 |
|---|---|---|
| A1 | 估算值必须标注 `data_source=estimated`，看板显著位置提示 | 数据测试断言估算表含该列；HTML 含提示文本 |
| A2 | 每阶段输出通过 schema 校验（列名、非空关键列、数值合计范围），校验失败视为阶段失败 | `tests/test_silver_schema.py` 等契约测试 |
| A3 | 依赖完整声明并锁版本上限（如 `pandas>=2.2,<3.0`），禁止裸 `>=` | `pip check` 无缺失；review requirements.txt |
| A4 | 死代码确认即删，不留"以防万一"注释代码 | 每批验收 `grep` 无残留引用 |
| A5 | 修改台账制度延续：每批变更追加到既有台账文件 | 检查台账更新记录 |

## 四、项目结构与文件归类约定（每个子目录都有卫生要求）

**总原则**：新增文件必须先属于某目录的约定类别；不属于任何类别的，先修订本约定，再放置。子目录结构变更必须同步更新 `使用说明.md`。

| 目录 | 允许内容 | 禁止 |
|---|---|---|
| 根目录 | `使用说明.md`、`PROJECT_CHARTER.md`、`.gitignore`、登记保留的 rar | 新增任何散件（脚本/文档/数据/截图） |
| `sales_analytics_platform\` | 平台代码、`data\`（输入）、`output\`（产出，gitignore）、平台 README/说明、bat | 工程文档（应入 project_analysis） |
| `forecasting\` | 预测系统代码与其归档 `_archive\` | 平台相关文件 |
| `project_analysis\` | 全部工程文档：诊断/裁决/计划/台账/验证报告 | 数据文件、产出文件 |
| `_archive_source\` | 只读源副本 | 任何修改（只读封存） |
| `_deprecated\` | 废弃封存文件 + README 登记表 | 被代码引用、被开发参考 |
| `scripts\`（批次⓪建） | 工具脚本（freeze_baseline / golden_diff / impact_rehearsal 等） | 业务逻辑代码 |
| `docs\`（批次⓪建） | 数据契约等接口文档（DATA_CONTRACT.md） | 进度类文档（入 project_analysis） |
| `baseline\`（批次⓪建） | 基线摘要 JSON（入库）+ 基线数据（gitignore） | 手工编辑基线 |
| `kanban\` | 独立 git 仓库（已 gitignore） | 纳入本仓库 |

**子目录卫生细则**：每个子目录只允许上表约定类别的文件；临时文件当日清理或移 `_deprecated\`；发现目录内出现约定外文件时，当次施工会话内必须归位，不得留到下次。

## 五、命名规则

| 对象 | 规则 | 示例 |
|---|---|---|
| 工程文档 | `主题_YYYYMMDD.md`，入 `project_analysis\` | `施工总计划_20260818.md` |
| 固定名文档 | 仅三个：根目录 `使用说明.md` / `PROJECT_CHARTER.md`、各包 `README.md` | — |
| 工具脚本 | 小写蛇形 `动词_宾语.py`，入 `scripts\` | `freeze_baseline.py` |
| git tag | `pre-batch-N`（开工）/ `batch-N-done`（验收） | `pre-batch-0` |
| git 分支 | `batch/N-短描述`，单批单分支，验收合入 master；禁止跨批搬运半成品 | `batch/0-baseline` |
| commit message | `类型: 中文描述`，类型 ∈ docs / fix / feat / refactor / chore / charter | `docs: 施工总计划` |
| 基线目录 | `baseline\YYYYMMDD\` | `baseline\20260818\` |

## 六、文档化与进度纪律（防上下文遗忘、防分支偏离）

1. **`project_analysis\施工进度台账.md` 是唯一进度事实源。** 每次施工会话**开工先读**（顺序：台账 → 本宪法 → 施工总计划），**收工必写**（已完成 / 下一步 / 未决 / 偏离记录）。
2. **重要决策当日文档化**：写入台账"决策记录"表，不允许只留在对话或记忆里。
3. **偏离管理**：施工中需要偏离《施工总计划》时，先在台账"偏离记录"写明原因与影响再继续；偏离触及红线（R1–R4）的一律停止，等待裁决。
4. **分支纪律**：单批单分支（`batch/N-短描述`），验收通过才合入 master 并打 `batch-N-done`；禁止在多个批次分支间 cherry-pick 半成品；长期不合入的分支（>2 周）须在台账登记原因。
5. **宪法/计划/台账的变更单独 commit**，不与代码变更混杂。

## 七、宪法自身的变更

本宪法的增删改视为一次独立变更：须单独提交、commit message 注明 `charter:`，并在施工总计划中记录变更原因。
