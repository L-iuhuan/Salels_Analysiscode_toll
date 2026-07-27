# 2026H1 销售深度分析报告群

> 本分支由代码考古重组自动生成(2026-07-27),原始文件均未移动/修改,此处为副本。
> 聚类与链路依据: `project_analysis/02_clusters.md`、`project_analysis/03_data_flow.md`

## 功能说明
为撰写《2026H1销售分析报告_完全+附录.docx》而做的一组深度分析:
scout/diag 数据探查 → analysis1-4 四维分析 → deep_*(整体/行动/品线/ZXKX 四路深挖,经 run_* 包装器捕获日志)
→ bridge/res 片段稿 → make_word.py 拼装 docx → fix_*.py 格式修补。

## 输入文件
- 财务分析-5月(6.3).xlsx / 财务分析-6月(7.6).xlsx(**未随包**)
- output/silver/silver_customer_x_product.csv(主流水线产物)

## 输出文件
- 中间稿:deep_*.md / res_part1-4.md / res_bridge*.md / asp_check.md 等
- 最终:2026H1销售分析报告_完全+附录.docx

## 运行方法
```bat
python run_deep.py     :: 等价 deep_all.py,日志入 deep_err.txt
python run_action.py
python run_sp.py
python run_zxkx.py
python make_word.py
```

也可以直接双击 `run.bat`(Windows)或执行 `bash run.sh`。

## 注意事项
- **不可直接运行**:全部脚本硬编码 `C:/Users/45091/Desktop/...` 路径(源自另一台电脑),运行前须批量替换为本机路径
- fix_word_归档/ 下 5 个 fix_word_* 是对 docx 的迭代修补,建议以 make_word.py+append_word_appendix.py 为准
- 报告类产出,无严格数据契约,不建议纳入常规流水线;价值在于分析口径(md 中间稿)

## 目录来源
- 复制文件数: 35
- 说明: H1报告链:deep_*→md→make_word→docx;含大量硬编码桌面路径
