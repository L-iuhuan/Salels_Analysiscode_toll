# -*- coding: utf-8 -*-
"""阶段五c:为每个分支生成 README.md + requirements.txt,并输出 05_branches_report.md。
requirements 从卡片 all_ext_imports_top 自动推导(排除标准库,映射 pip 名)。
"""
import json, os, csv

ROOT = r"E:\3-其他资料\数据分析"
BRANCHES = os.path.join(ROOT, "project_branches")
ANALYSIS_DIR = os.path.join(ROOT, "project_analysis")
cards = json.load(open(os.path.join(ANALYSIS_DIR, "01_function_cards.json"), encoding="utf-8"))
rep = json.load(open(os.path.join(ANALYSIS_DIR, "05_branches_report.json"), encoding="utf-8"))

STDLIB = {"os", "sys", "re", "json", "csv", "math", "time", "datetime", "collections", "itertools",
          "functools", "pathlib", "shutil", "subprocess", "argparse", "warnings", "hashlib",
          "importlib", "typing", "pickle", "copy", "random", "string", "io", "abc", "enum",
          "dataclasses", "concurrent", "threading", "multiprocessing", "queue", "logging",
          "traceback", "gc", "operator", "textwrap", "unicodedata", "struct", "base64", "urllib"}
PIP_NAME = {"sklearn": "scikit-learn", "chinese_calendar": "chinese-calendar",
            "calamine": "python-calamine", "docx": "python-docx", "PIL": "Pillow",
            "bs4": "beautifulsoup4", "yaml": "pyyaml"}
FLOOR = {"pandas": "pandas>=1.3", "numpy": "numpy>=1.21", "openpyxl": "openpyxl>=3.0",
         "statsmodels": "statsmodels>=0.13", "matplotlib": "matplotlib>=3.5",
         "scikit-learn": "scikit-learn>=1.0", "rapidfuzz": "rapidfuzz>=2.0",
         "chinese-calendar": "chinese-calendar>=1.8"}
OPTIONAL = {"python-calamine": "python-calamine  # 可选:Excel读取加速5-10倍"}

def branch_libs(branch):
    """扫描分支内 py 文件,从卡片推导第三方库集合"""
    libs = set()
    bdir = os.path.join(BRANCHES, branch)
    card_by_tail = {}
    for c in cards:
        card_by_tail[c["file"].split("/")[-1]] = c  # 按文件名粗匹配(同名文件内容相同或相近)
    for dp, dn, fn in os.walk(bdir):
        dn[:] = [d for d in dn if d != "__pycache__"]
        for f in fn:
            if f.endswith(".py") and f in card_by_tail:
                for m in card_by_tail[f].get("all_ext_imports_top", []):
                    top = m.split(".")[0]
                    if top not in STDLIB and not top.startswith("_"):
                        libs.add(top)
    return libs

def write_requirements(branch, extra=()):
    path = os.path.join(BRANCHES, branch, "requirements.txt")
    if os.path.exists(path):
        return "已存在(源自原始项目),未覆盖"
    libs = branch_libs(branch) | set(extra)
    lines = ["# 自动生成:基于分支内脚本的 import 静态推导", ""]
    pkgs = sorted({PIP_NAME.get(l, l) for l in libs})
    for p in pkgs:
        if p in OPTIONAL:
            lines.append("# " + OPTIONAL[p])
        else:
            lines.append(FLOOR.get(p, p))
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return f"生成 {len(pkgs)} 个依赖"

README = {
"main_pipeline": dict(
    title="主流水线(半导体销售分析)",
    purpose="""读取 ERP 出货明细 Excel(财务分析-N月.xlsx),产出三层数据资产:
- **Silver 层**(output/silver/):4 张清洗聚合 CSV(行级明细 + 客户月度 + 产品月度 + 客户×产品)
- **Gold 层**(output/gold/):产品画像、客户画像、KPI 等分析结果 CSV(可直接导入 BI)
- **报告层**(output/report/):Excel 分析报告(自动保留最近 10 份)

五个阶段: `silver → product → customer → kpi → cross_ref`,由 run_all.py 统一编排。
本分支以最新工作版(工作文件/semiconductor_analysis,代码至 2026-07-03)为基准提取。""",
    inputs="""- `data/财务分析-N月.xlsx`(**未随包**,见 data/README_数据说明.txt;程序自动取 data/ 下第一个 .xlsx)
  - 必需 Sheet:出货明细(默认名见 config/settings.py 的 DATA_SHEET_NAME);可选 Sheet:客户信息表
- `data/部门-人员-职务对应.md`(已随包,渠道/人员映射)""",
    outputs="""- `output/silver/silver_cleaned_rows.csv` 等 4 张(注意:行级 CSV 体积可达 200MB+)
- `output/gold/*.csv`(gold_product_portrait、gold_kpi_daily、客户画像等)
- `output/report/*.xlsx`""",
    run="""```bat
python run_all.py                                  :: 全流程
python run_all.py --stage silver,customer          :: 仅指定阶段
python run_all.py --force-silver                   :: 配置变更后强制重算 Silver
python run_all.py --data "D:\\path\\数据.xlsx"      :: 指定源数据
```
中文一键入口:`1_全量重跑.bat` / `3_只跑客户分析.bat` / `4_只跑产品分析.bat` 等。""",
    notes="""- **Silver 缓存**:`SKIP_SILVER_IF_EXISTS=True` 时,若 output/silver/ 已有 3 张 CSV 且配置未变(校验和比对),silver 阶段自动跳过;改了清洗逻辑或列映射需 `--force-silver`
- **CSV 编码**:全部 UTF-8 with BOM,Excel 直接打开不乱码
- 报表自动清理:output/report/ 仅保留最近 10 份
- 依赖自动安装:run_all.py 启动时检测缺失包并自动 pip install -r requirements.txt
- docs/ 下有旧版 README/AGENTS/PIPELINE_NODE_MAP 三份参考文档(来自 2026-06-03 固化版,结构基本一致)"""),
"dashboard_chain": dict(
    title="看板流水线(便携包)",
    purpose="""「数据处理 → HTML 单页看板」一键流水线,原始项目自带完整编排器,可整体拷贝到任何 Windows 机器。
前段 processing/run_all.py(与主流水线同一套代码)产出 output/{silver,gold,report};
后段 dashboard/generate_dashboard.py(V8)产出 dashboard/dashboard_a.html(KPI/趋势/品类/客户排行/生命周期)。""",
    inputs="""- `data/*.xlsx`(自动取最新一份;**当前 data/ 下没有 xlsx,需自行放入**)
- `data/部门-人员-职务对应.md`(已随包;缺失时看板 F 面人员映射为空,不阻断)""",
    outputs="""- `dashboard/dashboard_a.html`(单文件看板,浏览器直接打开)
- `output/{silver,gold,report}/*`(中间产物,可另作分析)""",
    run="""```bat
python run_chain.py                        :: 全流程
python run_chain.py --skip-processing      :: 数据没变,只重生成看板(快)
python run_chain.py --force-silver         :: 强制重算 Silver
```""",
    notes="""- run_chain.py 会自动把 processing/output 做目录联接(mklink /J)到包根 output/,无需管理员权限
- 本包与 main_pipeline 分支同源(2026-06-22 快照),如需最新分析逻辑可同步 main_pipeline 的 processing 代码
- 原包自带 README.md / requirements.txt,保留未动"""),
"deep_dive_h1_report": dict(
    title="2026H1 销售深度分析报告群",
    purpose="""为撰写《2026H1销售分析报告_完全+附录.docx》而做的一组深度分析:
scout/diag 数据探查 → analysis1-4 四维分析 → deep_*(整体/行动/品线/ZXKX 四路深挖,经 run_* 包装器捕获日志)
→ bridge/res 片段稿 → make_word.py 拼装 docx → fix_*.py 格式修补。""",
    inputs="""- 财务分析-5月(6.3).xlsx / 财务分析-6月(7.6).xlsx(**未随包**)
- output/silver/silver_customer_x_product.csv(主流水线产物)""",
    outputs="""- 中间稿:deep_*.md / res_part1-4.md / res_bridge*.md / asp_check.md 等
- 最终:2026H1销售分析报告_完全+附录.docx""",
    run="""```bat
python run_deep.py     :: 等价 deep_all.py,日志入 deep_err.txt
python run_action.py
python run_sp.py
python run_zxkx.py
python make_word.py
```""",
    notes="""- **不可直接运行**:全部脚本硬编码 `C:/Users/45091/Desktop/...` 路径(源自另一台电脑),运行前须批量替换为本机路径
- fix_word_归档/ 下 5 个 fix_word_* 是对 docx 的迭代修补,建议以 make_word.py+append_word_appendix.py 为准
- 报告类产出,无严格数据契约,不建议纳入常规流水线;价值在于分析口径(md 中间稿)"""),
"eda_forecast": dict(
    title="EDA 与出货预测实验",
    purpose="""对 5 月财务数据的探索性分析(EDA,三版迭代,保留终版 v3)与出货预测实验:
长尾产品预测(run_longtail_forecast.py)+ 全量出货预测 v3(run_full_forecast_v3.py)。""",
    inputs="- 财务分析-5月(6.3)(1).xlsx(**未随包**,见 data_说明.txt)",
    outputs="- eda_results.txt / customer_agg.csv / customer_activity.csv / 预测结果 CSV",
    run="""```bat
python eda_analysis_v3.py
python run_full_forecast_v3.py
python run_longtail_forecast.py
```""",
    notes="""- _archive/ 内有 v1/v2 旧迭代,仅供对照
- 脚本头部有数据路径变量,运行前先改路径
- 实验性代码,预测口径后被 quarterly_forecast 分支正规化"""),
"recession_risk_opt": dict(
    title="衰退风险优化(客户/产品衰退预警)",
    purpose="""基于主流水线 silver/gold 产出的二次建模:phase1-5 因子挖掘与回测、phaseA 严重度分布与交叉验证、
phaseB1a 严重度回归、v3.1 校准与最终优化;generate_snapshot.py 产出产品风险快照 Excel。
样本数据(data/samples.pkl 3.1MB + samples.csv 4.9MB)与模型配置(models/*.json)已随包。""",
    inputs="""- `data/samples.pkl` / `data/samples.csv`(已随包)
- 重新取数时需 main_pipeline 的 output/silver/*.csv 与 output/gold/gold_product_portrait.csv""",
    outputs="""- `reports/产品风险快照表_增强版_{日期}.xlsx`
- `output/phaseA*/phaseB*` 图表与 md(产出目录已清空,运行后重新生成)""",
    run="""```bat
python pipeline.py
python generate_snapshot.py
```""",
    notes="""- 存疑:`models/best_config.json` 在原项目中被引用但文件不存在于原位置(可能由 phase3 重新生成)
- 存疑:个别 f-string 输出路径(如 `{}/c6_factor_raw.csv`)静态分析未能解析,运行时自行确认
- backtest_results/ 仅保留测试报告 md,折数据 CSV 与图未复制(属产出物)"""),
"quarterly_forecast": dict(
    title="季度预测包(产品线 + 客户双维度)",
    purpose="""直接读取原始出货明细 Excel,用 statsmodels ETS 等方法做季度级历史拟合与未来 4 季度预测,
含方法回测排行榜;产品线维度(run_quarterly_forecast.py)与客户维度(run_customer_forecast.py)双入口。
原包自带 README.txt / 使用说明.md / 实施方案文档。""",
    inputs="- 原始出货明细 Excel(**未随包**,见 data_说明.txt);`forecast_config*.json`(已随包)",
    outputs="""- `output/quarterly_forecast*/产品线|客户季度历史与预测.csv` 等 8 类 CSV
- 季度预测图表 HTML、含方法回测 xlsx
- `预测方案总行版.csv`(下游 unified_forecast 分支的输入)""",
    run="""```bat
python run_quarterly_forecast.py
python run_customer_forecast.py
```""",
    notes="""- 原包 output/ 已清空(产出物不复制);chartjs.min.js/chart_template.html 已随包
- 配置:forecast_config.default.json / forecast_config_customer.json"""),
"unified_forecast": dict(
    title="统一预测系统(多版本存档)",
    purpose="""整合预测入口的统一系统,读 quarterly_forecast 分支产出的 `预测方案总行版.csv` 做进一步汇总。
存在 5 个年代版本:**存疑,未能从静态分析确认最终版**——按修改时间与命名,建议先核对
`unified_forecast_v3.py`,backup_v1-v3 已移入 _archive/。""",
    inputs="- quarterly_forecast 分支的 `output/quarterly_forecast_customer/预测方案总行版.csv`",
    outputs="- 统一预测结果 CSV(具体见脚本内配置)",
    run="""```bat
python unified_forecast_v3.py
```""",
    notes="""- 与 semiconductor_analysis 根目录的 测试方案_多维度分层预测校准_v1.3.md 配套阅读
- 存疑:unified_forecast_system.py 与 unified_forecast_v3.py 关系不明(可能 v3 是重写版)"""),
"product_lifecycle_legacy_v28": dict(
    title="产品生命周期评估 v2.8(已淘汰,存档)",
    purpose="""2026 年 4-5 月的独立旧项目:config.xlsx 驱动的产品生命周期九宫格评估,产出 Excel 报告 + HTML 看板。
**已被 main_pipeline 分支的 product_lifecycle/ 包取代**,本分支仅供追溯历史口径。
v2.9 迭代(风险模型改造)在子目录 产品生命周期量化评估方案_v2.9/。""",
    inputs="""- `config.xlsx`(已随包,阈值/列映射配置)
- `所有的出货明细5.9.xlsx`(137MB,**未随包**,见 data_说明.txt)""",
    outputs="- output_v2.8_*.xlsx + 配套 HTML 看板(桑基图/画像分布/风险分布)",
    run="""```bat
python run_v2.8.py
```""",
    notes="""- backup_code/ 收集了 backup/ 下的历史代码(v2.7 系列、build_html 等),outputs 未复制
- 根目录另有 426MB 同名 .rar 归档(按你的决定未解压、未复制)
- 新旧口径对照:新 product_lifecycle 的九宫格阈值见 main_pipeline/config/settings_product.py"""),
"_orphans": dict(
    title="孤儿收容区(待人工判断)",
    purpose="""无法归入任何链路、或被判定为临时/无关的脚本,按四类存放:
- `temp_临时检查/`(33 个):dashboard 审计、列查找、校验类一次性脚本,仅读取 silver/gold 做人工核查
- `junk_与数据分析无关/`(6 个):LeetCode 练习、线程 demo(建议直接删除)
- `debug_存疑/`(8 个):_debug/_step 探索脚本、parse_excel_file 等用途不明工具
- `uncertain_存疑/`(5 个):runall/run2-4、generate_v4 等无法从静态分析判定归属的入口脚本""",
    inputs="- 不适用", outputs="- 不适用",
    run="""不建议运行。如需复活某个脚本,请先读代码确认输入/输出,再移入对应分支。""",
    notes="""- 客户销售情况分析/ 目录(纯方案设计文档,无代码)未复制,原文仍在 E:\\3-其他资料\\数据分析\\客户销售情况分析\\
- 判断依据见 project_analysis/01_function_cards.json 与 02_clusters.md"""),
}

def w(branch, name, content):
    p = os.path.join(BRANCHES, branch, name)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(content)

req_notes = {}
for b, rd in README.items():
    if b != "_orphans":
        req_notes[b] = write_requirements(b)
    body = f"""# {rd['title']}

> 本分支由代码考古重组自动生成(2026-07-27),原始文件均未移动/修改,此处为副本。
> 聚类与链路依据: `project_analysis/02_clusters.md`、`project_analysis/03_data_flow.md`

## 功能说明
{rd['purpose']}

## 输入文件
{rd['inputs']}

## 输出文件
{rd['outputs']}

## 运行方法
{rd['run']}

也可以直接双击 `run.bat`(Windows)或执行 `bash run.sh`。

## 注意事项
{rd['notes']}

## 目录来源
- 复制文件数: {rep['branches'][b]['files_copied']}
- 说明: {rep['branches'][b]['note']}
"""
    w(b, "README.md", body)

md = ["# 05 分支提取报告\n", "| 分支 | 复制文件数 | requirements | 说明 |", "|---|---|---|---|"]
for b in rep["branches"]:
    md.append(f"| project_branches/{b}/ | {rep['branches'][b]['files_copied']} | "
              f"{req_notes.get(b, '不需要')} | {rep['branches'][b]['note']} |")
if rep.get("skipped_big"):
    md.append("\n## 未复制的大文件(>50MB,README 中已注明位置)\n")
    for s in rep["skipped_big"]:
        md.append(f"- {s['file']} ({s['mb']}MB)")
md.append("\n## 未找到文件\n")
md.append("第二轮修正后无缺失。" if not rep["missing"] else "\n".join(f"- {m}" for m in rep["missing"]))
with open(os.path.join(ANALYSIS_DIR, "05_branches_report.md"), "w", encoding="utf-8") as f:
    f.write("\n".join(md) + "\n")
print(json.dumps(req_notes, ensure_ascii=False, indent=1))
