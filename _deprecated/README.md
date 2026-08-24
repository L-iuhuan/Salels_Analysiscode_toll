# _deprecated — 废弃文件封存区

> **本目录内的一切文件，禁止在后续开发中参考、引用、复制、import、读取。**
> 它们保留在这里只为历史可查，不代表任何有效口径或有效实现。
> 需要有效信息时，去看 `project_analysis\` 的正式文档和 `sales_analytics_platform\` 的现役代码。

## 规则（宪法 S7）

1. 任何文件/目录**不得直接删除**；废弃文件一律移入本目录（尽量保留原相对路径结构），并在下表登记。
2. 登记必填：原路径、移入日期、移入原因、决策人。
3. 代码中禁止出现对 `_deprecated` 的任何引用（grep 检查）。
4. 物理删除仅在"确认不可逆废弃"后，单独 commit 执行并在 message 注明。

## 登记表

| 原路径 | 移入日期 | 移入原因 | 决策人 |
|---|---|---|---|
| processing/core/pipeline.py | 2026-08-19 | 半成本品 DI 编排器，生产不使用（run_all.py 的 --pipeline 分支已移除，批次②.5） | 批次②.5 council裁决 |
| processing/core/config.py | 2026-08-19 | 独立配置系统，未与 config/settings.py 同步，仅 core/pipeline.py 使用 | 批次②.5 council裁决 |
| processing/core/interfaces.py | 2026-08-19 | 5 个无实现 Protocol，纯死代码，无活引用 | 批次②.5 council裁决 |
| processing/core/__init__.py | 2026-08-19 | core 包随 pipeline/config/interfaces 整体废弃 | 批次②.5 council裁决 |
| processing/data_pipeline/loader.py | 2026-08-19 | DI 包装器，仅 core/pipeline.py 使用 | 批次②.5 council裁决 |
| processing/data_pipeline/cleaner.py | 2026-08-19 | DI 包装器，仅 core/pipeline.py 使用 | 批次②.5 council裁决 |
| processing/data_pipeline/aggregator.py | 2026-08-19 | DI 包装器，仅 core/pipeline.py 使用 | 批次②.5 council裁决 |
| processing/analysis/b2b_adapters.py | 2026-08-19 | B2B 适配器无人使用，生产 gold.py 直接调 b2b_v2 | 批次②.5 council裁决 |
| test/test_pipeline.py | 2026-08-19 | 测试 mock 而非真实契约；批次④b 补真实编排测试 | 批次②.5 council裁决 |
| 长库龄存货明细.xlsx（根目录散件） | 2026-08-24 | 未注册散件，非平台输入；如后续需要长库龄分析，从封存取回 | 用户拍板（仓库卫生整理） |
| 2026年7月销售经营分析_数据附件.xlsx（根目录散件） | 2026-08-24 | 未注册散件；文件名与流水线输入（财务分析-x月.xlsx）不同构。若为7月跑批输入，从封存取回放入 `sales_analytics_platform\data\` 并核对列结构（注意 data\ 多文件时自动探测取字母序第一个的风险） | 用户拍板（仓库卫生整理） |
