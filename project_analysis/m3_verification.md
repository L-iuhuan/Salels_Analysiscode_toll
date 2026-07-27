# M3 验证报告 — 平台全链 + golden-diff(2026-07-27)

## 结论:PASS —— 合并未引入任何结果级回归

平台(③骨架+②覆盖)在相同输入(②的 财务分析-6月(7.6).xlsx)下全链运行成功,
产出与② 2026-07-05 基线在数据层面一致。

## 运行记录

| 运行 | 命令 | 结果 |
|---|---|---|
| #1 | `run_chain.py --data ... --force-silver` | exit=1:③的 pricing_customer.py pandas-3 修复在 pandas 2.3.1 下抛 `ValueError: empty group due to unobserved categories`(dropna 把"占比"全NaN客户整组抹掉) |
| #2 | `run_chain.py --data ...`(无 --force-silver) | exit=0,但 golden-diff 出现 10 张 gold 系统性差异(见"重大发现") |
| #3 | `run_chain.py --data ... --force-silver` | exit=0(处理 1104.9s + 看板 381.3s),golden-diff 收敛 |

## 代码修改台账(累计 5 处)

- #1~#3:M1 已记录(③的 settings.py PKG_ROOT、pricing pandas-3 修复保留③版、test/落包根+conftest)
- #4:run_chain.py `ensure_output_junction` 增加 data 联接+自检+py3.11 兼容 `_is_junction_or_link`(council P0)
- #5(本次):pricing_customer.py L199 groupby 加 `observed=True`。③原修复(dropna)在 pandas 2.3.1 下反而引入空类别组崩溃;observed=True 与②原版(无dropna,idxmax返NaN链尾剔除)输出逐值等价,且兼容 pandas 3.x

## 重大发现:silver 缓存模式行为分歧(pipeline 既有怪癖,②③原样继承)

运行#2(复用 silver 缓存)与基线出现系统性差异,根因:
- `run_all.py:144-146` 缓存命中时 `return True, None, None` → customer 阶段 `raw_data=None`
  → `run_pipeline.py:82-95` 从源文件重载 raw,客户编号=终端客户简称,**无 fillna("未知客户")**
  → groupby 丢弃 NaN 键 → "未知客户"失去归属(未知/未知)
- 全新运行(--force-silver):`run_all.py:207` 对内存 raw 执行 fillna → "未知客户"成为真实键
  → 归属 翁创伟/代理(②基线行为)

连锁影响(仅缓存模式):gold_kpi_daily 客户数每日少1、翁创伟全维度统计偏低、品类擅长少1行、
RFM 分位数边界微移致4个边缘客户 M_得分±1、渠道价格对比客户数偏移。

**处置**:不修改代码(遵守不重构铁律)。验证协议必须强制 `--force-silver`(council 原协议正确,
运行#2 是我的协议违规)。此怪癖将写入使用说明:日常复跑若复用缓存,客户归属口径会与全新运行不同。

## golden-diff 终态(运行#3 vs ② 2026-07-05 基线)

| 层 | 结果 |
|---|---|
| silver(4数据文件) | **逐字节完全一致** |
| gold(30张) | **28 字节级一致** + 定价合理性分析(全部差异≤1e-6 相对容差,浮点格式噪声)+ 交叉销售建议(9格,同分并列推荐项相邻互换,品种/理由集合完全一致) |
| Excel 报告×2 | sheet 结构完全一致 |
| 看板 | 48 共有变量中 43 完全一致;5 个差异均非数据:ALL(V9 TABS.STATE 命名空间 vs V8 B_CUSTS)、E_SEL_MONTHS(默认选中月 V9=['2026-06'] vs V8=['2026-05'])、D_DEPT_LIST(0.1分舍入)、F_PRODUCT_LIST(426项名称与字段值全同,仅顺序)、PROD_CHANGE(39客户集合一致,嵌套列表同分项排序抖动) |

残留排序抖动为 pipeline 固有(同分并列项顺序依赖内部迭代序),②自身两次运行亦会如此,非合并引入。

## 附带说明

- ② gold 目录的 `cross_product_customer_health.csv`(6/14)、`品类迁移.csv`(6/15) 为旧残留,
  ②自己的 7/5 基线运行也未产出(条件输出未触发),平台行为与之一致。
- 工具:`_tools/m3_golden_diff.py`(四层比对)、`m3_diff_inspect.py`、`m3_residual_inspect*.py`、`m3_xlsx_probe.py`
- 日志:`m3_platform_run.log`(#1/#2)、`m3_platform_run2.log`(#3)、`m3_golden_diff_report.json`
