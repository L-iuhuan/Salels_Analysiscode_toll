# 看板流水线(便携包)

> 本分支由代码考古重组自动生成(2026-07-27),原始文件均未移动/修改,此处为副本。
> 聚类与链路依据: `project_analysis/02_clusters.md`、`project_analysis/03_data_flow.md`

## 功能说明
「数据处理 → HTML 单页看板」一键流水线,原始项目自带完整编排器,可整体拷贝到任何 Windows 机器。
前段 processing/run_all.py(与主流水线同一套代码)产出 output/{silver,gold,report};
后段 dashboard/generate_dashboard.py(V8)产出 dashboard/dashboard_a.html(KPI/趋势/品类/客户排行/生命周期)。

## 输入文件
- `data/*.xlsx`(自动取最新一份;**当前 data/ 下没有 xlsx,需自行放入**)
- `data/部门-人员-职务对应.md`(已随包;缺失时看板 F 面人员映射为空,不阻断)

## 输出文件
- `dashboard/dashboard_a.html`(单文件看板,浏览器直接打开)
- `output/{silver,gold,report}/*`(中间产物,可另作分析)

## 运行方法
```bat
python run_chain.py                        :: 全流程
python run_chain.py --skip-processing      :: 数据没变,只重生成看板(快)
python run_chain.py --force-silver         :: 强制重算 Silver
```

也可以直接双击 `run.bat`(Windows)或执行 `bash run.sh`。

## 注意事项
- run_chain.py 会自动把 processing/output 做目录联接(mklink /J)到包根 output/,无需管理员权限
- 本包与 main_pipeline 分支同源(2026-06-22 快照),如需最新分析逻辑可同步 main_pipeline 的 processing 代码
- 原包自带 README.md / requirements.txt,保留未动

## 目录来源
- 复制文件数: 95
- 说明: 看板便携包:processing→generate_dashboard→dashboard_a.html
