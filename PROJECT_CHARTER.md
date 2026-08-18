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

## 三、建议（默认遵守，可不阻塞，5 条）

| # | 条文 | 检查方式 |
|---|---|---|
| A1 | 估算值必须标注 `data_source=estimated`，看板显著位置提示 | 数据测试断言估算表含该列；HTML 含提示文本 |
| A2 | 每阶段输出通过 schema 校验（列名、非空关键列、数值合计范围），校验失败视为阶段失败 | `tests/test_silver_schema.py` 等契约测试 |
| A3 | 依赖完整声明并锁版本上限（如 `pandas>=2.2,<3.0`），禁止裸 `>=` | `pip check` 无缺失；review requirements.txt |
| A4 | 死代码确认即删，不留"以防万一"注释代码 | 每批验收 `grep` 无残留引用 |
| A5 | 修改台账制度延续：每批变更追加到既有台账文件 | 检查台账更新记录 |

## 四、宪法自身的变更

本宪法的增删改视为一次独立变更：须单独提交、commit message 注明 `charter:`，并在施工总计划中记录变更原因。
