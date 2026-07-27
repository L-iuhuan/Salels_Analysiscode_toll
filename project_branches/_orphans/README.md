# 孤儿收容区(待人工判断)

> 本分支由代码考古重组自动生成(2026-07-27),原始文件均未移动/修改,此处为副本。
> 聚类与链路依据: `project_analysis/02_clusters.md`、`project_analysis/03_data_flow.md`

## 功能说明
无法归入任何链路、或被判定为临时/无关的脚本,按四类存放:
- `temp_临时检查/`(33 个):dashboard 审计、列查找、校验类一次性脚本,仅读取 silver/gold 做人工核查
- `junk_与数据分析无关/`(6 个):LeetCode 练习、线程 demo(建议直接删除)
- `debug_存疑/`(8 个):_debug/_step 探索脚本、parse_excel_file 等用途不明工具
- `uncertain_存疑/`(5 个):runall/run2-4、generate_v4 等无法从静态分析判定归属的入口脚本

## 输入文件
- 不适用

## 输出文件
- 不适用

## 运行方法
不建议运行。如需复活某个脚本,请先读代码确认输入/输出,再移入对应分支。

也可以直接双击 `run.bat`(Windows)或执行 `bash run.sh`。

## 注意事项
- 客户销售情况分析/ 目录(纯方案设计文档,无代码)未复制,原文仍在 E:\3-其他资料\数据分析\客户销售情况分析\
- 判断依据见 project_analysis/01_function_cards.json 与 02_clusters.md

## 目录来源
- 复制文件数: 49
- 说明: 孤儿收容:temp/junk/debug/uncertain 四类
