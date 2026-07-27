# 主流水线(半导体销售分析)

> 本分支由代码考古重组自动生成(2026-07-27),原始文件均未移动/修改,此处为副本。
> 聚类与链路依据: `project_analysis/02_clusters.md`、`project_analysis/03_data_flow.md`

## 功能说明
读取 ERP 出货明细 Excel(财务分析-N月.xlsx),产出三层数据资产:
- **Silver 层**(output/silver/):4 张清洗聚合 CSV(行级明细 + 客户月度 + 产品月度 + 客户×产品)
- **Gold 层**(output/gold/):产品画像、客户画像、KPI 等分析结果 CSV(可直接导入 BI)
- **报告层**(output/report/):Excel 分析报告(自动保留最近 10 份)

五个阶段: `silver → product → customer → kpi → cross_ref`,由 run_all.py 统一编排。
本分支以最新工作版(工作文件/semiconductor_analysis,代码至 2026-07-03)为基准提取。

## 输入文件
- `data/财务分析-N月.xlsx`(**未随包**,见 data/README_数据说明.txt;程序自动取 data/ 下第一个 .xlsx)
  - 必需 Sheet:出货明细(默认名见 config/settings.py 的 DATA_SHEET_NAME);可选 Sheet:客户信息表
- `data/部门-人员-职务对应.md`(已随包,渠道/人员映射)

## 输出文件
- `output/silver/silver_cleaned_rows.csv` 等 4 张(注意:行级 CSV 体积可达 200MB+)
- `output/gold/*.csv`(gold_product_portrait、gold_kpi_daily、客户画像等)
- `output/report/*.xlsx`

## 运行方法
```bat
python run_all.py                                  :: 全流程
python run_all.py --stage silver,customer          :: 仅指定阶段
python run_all.py --force-silver                   :: 配置变更后强制重算 Silver
python run_all.py --data "D:\path\数据.xlsx"      :: 指定源数据
```
中文一键入口:`1_全量重跑.bat` / `3_只跑客户分析.bat` / `4_只跑产品分析.bat` 等。

也可以直接双击 `run.bat`(Windows)或执行 `bash run.sh`。

## 注意事项
- **Silver 缓存**:`SKIP_SILVER_IF_EXISTS=True` 时,若 output/silver/ 已有 3 张 CSV 且配置未变(校验和比对),silver 阶段自动跳过;改了清洗逻辑或列映射需 `--force-silver`
- **CSV 编码**:全部 UTF-8 with BOM,Excel 直接打开不乱码
- 报表自动清理:output/report/ 仅保留最近 10 份
- 依赖自动安装:run_all.py 启动时检测缺失包并自动 pip install -r requirements.txt
- docs/ 下有旧版 README/AGENTS/PIPELINE_NODE_MAP 三份参考文档(来自 2026-06-03 固化版,结构基本一致)

## 目录来源
- 复制文件数: 152
- 说明: 主流水线:silver→product→customer→kpi→cross_ref
